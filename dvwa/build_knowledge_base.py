"""Build proposal JSON knowledge; PDF indexing is an explicit diagnostic option."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from rag_pipeline import ROOT, DEFAULT_EMBEDDING_MODEL, embed_texts, embedding_input_format, local_ollama_url


SCHEMA_VERSION = "1.0.0"


def chunk_text(
    text: str, words_per_chunk: int, overlap_words: int, max_chars_per_chunk: int = 1200
) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = words_per_chunk - overlap_words
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + words_per_chunk]).strip()
        if chunk:
            # PDF tables, URLs and unspaced text can exceed context despite a word limit.
            # Split oversized windows with overlap; preserve all text rather than truncate.
            char_overlap = max_chars_per_chunk * overlap_words // words_per_chunk
            char_start = 0
            while char_start < len(chunk):
                char_end = min(char_start + max_chars_per_chunk, len(chunk))
                if char_end < len(chunk):
                    boundary = chunk.rfind(" ", char_start + max_chars_per_chunk // 2, char_end)
                    if boundary != -1:
                        char_end = boundary
                chunks.append(chunk[char_start:char_end].strip())
                if char_end == len(chunk):
                    break
                # Bound overlap by half this segment to guarantee forward progress.
                char_start = char_end - min(char_overlap, (char_end - char_start) // 2)
        if start + words_per_chunk >= len(words):
            break
    return chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "knowledge/sqli-entries.json")
    parser.add_argument("--experimental-pdf", action="store_true", help="Diagnostic PDF index; excluded from proposal generation")
    parser.add_argument("--sources", type=Path, default=ROOT / "sources")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--words-per-chunk", type=int, default=220)
    parser.add_argument("--overlap-words", type=int, default=40)
    parser.add_argument("--max-chars-per-chunk", type=int, default=1200)
    parser.add_argument("--batch-size", type=int, default=16)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.experimental_pdf:
        from build_structured_knowledge import build
        manifest = build(args.corpus, args.embedding_model, args.batch_size)
        print(f"Proposal knowledge base manifest: {manifest}")
        return
    sources_dir = args.sources.resolve()
    allowed_sources = (ROOT / "sources").resolve()
    if not sources_dir.is_relative_to(allowed_sources):
        raise SystemExit("PDF input must stay inside the read-only sources/ directory.")
    if args.words_per_chunk < 50 or not 0 <= args.overlap_words < args.words_per_chunk:
        raise SystemExit("Use at least 50 words per chunk and overlap smaller than chunk size.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive.")
    if args.max_chars_per_chunk < 300:
        raise SystemExit("--max-chars-per-chunk must be at least 300.")
    local_ollama_url()

    try:
        from pypdf import PdfReader
        import chromadb
    except ImportError as exc:
        raise SystemExit("Install requirements-rag.txt before building the knowledge base.") from exc

    pdf_paths = sorted(sources_dir.rglob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDF references found under {sources_dir}.")

    chunks: list[dict] = []
    source_records = []
    for pdf_path in pdf_paths:
        pdf_bytes = pdf_path.read_bytes()
        file_digest = hashlib.sha256(pdf_bytes).hexdigest()
        reader = PdfReader(str(pdf_path))
        relative_path = pdf_path.relative_to(ROOT).as_posix()
        page_count = len(reader.pages)
        source_chunk_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for chunk_index, content in enumerate(
                chunk_text(page_text, args.words_per_chunk, args.overlap_words, args.max_chars_per_chunk),
                start=1,
            ):
                stable_key = (
                    f"{file_digest}:{page_number}:{chunk_index}:"
                    f"{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
                )
                chunk_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
                chunks.append(
                    {
                        "id": chunk_id,
                        "text": content,
                        "metadata": {
                            "source_path": relative_path,
                            "source_sha256": file_digest,
                            "page_number": page_number,
                            "chunk_index": chunk_index,
                            "title": pdf_path.stem[:300],
                        },
                    }
                )
                source_chunk_count += 1
        source_records.append(
            {
                "source_path": relative_path,
                "source_sha256": file_digest,
                "page_count": page_count,
                "chunk_count": source_chunk_count,
            }
        )

    if not chunks:
        raise SystemExit("PDFs were found, but no extractable text was produced.")

    source_fingerprint = hashlib.sha256(
        json.dumps(source_records, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    build_config = {
        "schema_version": SCHEMA_VERSION,
        "embedding_model": args.embedding_model,
        "embedding_input_format": embedding_input_format(args.embedding_model),
        # Extractor versions can change decoded text; include them in the build ID.
        "pdf_extractor_versions": {"pypdf": version("pypdf"), "fonttools": version("fonttools")},
        "words_per_chunk": args.words_per_chunk,
        "overlap_words": args.overlap_words,
        "max_chars_per_chunk": args.max_chars_per_chunk,
        "source_fingerprint": source_fingerprint,
    }
    knowledge_base_id = "sqli-kb-" + hashlib.sha256(
        json.dumps(build_config, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    store_path = Path("data/vectorstore") / knowledge_base_id
    absolute_store_path = ROOT / store_path
    absolute_store_path.mkdir(parents=True, exist_ok=True)
    collection_name = "sqli_" + re.sub(r"[^a-zA-Z0-9_-]", "_", args.embedding_model)[:40]
    client = chromadb.PersistentClient(path=str(absolute_store_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": args.embedding_model,
            "knowledge_base_id": knowledge_base_id,
        },
    )

    print(f"Prepared {len(chunks)} chunks from {len(pdf_paths)} PDFs; indexing...", flush=True)
    for start in range(0, len(chunks), args.batch_size):
        batch = chunks[start : start + args.batch_size]
        vectors = embed_texts(args.embedding_model, [item["text"] for item in batch], args.batch_size)
        collection.upsert(
            ids=[item["id"] for item in batch],
            embeddings=vectors,
            documents=[item["text"] for item in batch],
            metadatas=[item["metadata"] for item in batch],
        )
        if start // args.batch_size % 10 == 0 or start + len(batch) == len(chunks):
            print(f"Indexed {start + len(batch)}/{len(chunks)} chunks", flush=True)

    manifest = {
        **build_config,
        "purpose": "experimental-pdf-smoke",
        "knowledge_base_id": knowledge_base_id,
        "collection_name": collection_name,
        "store_path": store_path.as_posix(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ollama_base_url": local_ollama_url(),
        "sources": source_records,
        "page_count": sum(item["page_count"] for item in source_records),
        "chunk_count": len(chunks),
    }
    manifest_path = absolute_store_path / "manifest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(manifest, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(f"Knowledge base manifest: {manifest_path}")
    print(json.dumps({"knowledge_base_id": knowledge_base_id, "pdf_count": len(source_records), "page_count": manifest["page_count"], "chunk_count": len(chunks), "collection_name": collection_name}, ensure_ascii=False))
    from rag_pipeline import read_manifest
    from retrieval_selection import prepare_curation
    print(f"Retrieval curation: {prepare_curation(read_manifest(manifest_path))}")


if __name__ == "__main__":
    main()
