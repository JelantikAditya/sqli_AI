"""Build the proposal JSON corpus into its own persistent Chroma collection."""

from datetime import datetime, timezone
import json
from pathlib import Path

from knowledge_corpus import (DEFAULT_CORPUS, ROOT, build_config, knowledge_base_id,
                              prepare_documents, validate_corpus)
from rag_pipeline import embed_texts, embedding_input_format


def build(corpus_path: Path = DEFAULT_CORPUS, model: str = "nomic-embed-text", batch_size: int = 4) -> Path:
    import chromadb

    if model.split(":", 1)[0] != "nomic-embed-text" or batch_size < 1:
        raise ValueError("Proposal build requires Nomic embeddings and a positive batch size.")
    if corpus_path.resolve() != DEFAULT_CORPUS.resolve():
        raise ValueError("Save the reviewed proposal corpus at knowledge/sqli-entries.json.")
    corpus, lock = validate_corpus(corpus_path)
    documents = prepare_documents(corpus, lock)
    config = build_config(corpus, corpus_path, model, embedding_input_format(model))
    identity = knowledge_base_id(config)
    store = ROOT / "data/vectorstore" / identity
    client = chromadb.PersistentClient(path=str(store))
    collection = client.get_or_create_collection("sqli_knowledge", embedding_function=None,
        metadata={"hnsw:space": "cosine", "knowledge_base_id": identity})
    for start in range(0, len(documents), batch_size):
        batch = documents[start:start + batch_size]
        vectors = embed_texts(model, [item["text"] for item in batch], batch_size)
        collection.upsert(ids=[item["id"] for item in batch], embeddings=vectors,
                          documents=[item["text"] for item in batch], metadatas=[item["metadata"] for item in batch])
    if collection.count() != len(documents):
        raise ValueError("Structured collection count differs from the validated corpus.")
    manifest = {**config, "knowledge_base_id": identity, "collection_name": "sqli_knowledge",
                "store_path": store.relative_to(ROOT).as_posix(), "chunk_count": len(documents),
                "entry_count": len(documents), "corpus_path": "knowledge/sqli-entries.json",
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "curation": corpus["curation"],
                "sources": lock["sources"]}
    manifest_path = store / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # A stable pointer selects the structured corpus; old PDF indexes remain diagnostics.
    active = ROOT / "knowledge/active-index.local.json"
    active.write_text(json.dumps({"knowledge_base_id": identity,
                                 "manifest_path": manifest_path.relative_to(ROOT).as_posix()}, indent=2) + "\n", encoding="utf-8")
    return manifest_path
