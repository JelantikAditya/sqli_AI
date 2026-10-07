"""Verify real Ollama embeddings and persistent Chroma retrieval with synthetic text."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from importlib.metadata import version

import chromadb

from rag_pipeline import ROOT, DEFAULT_EMBEDDING_MODEL, embed_texts, embedding_input_format
from rag_pipeline import load_catalog, read_manifest, retrieve_chunks, scenario_query


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    store = ROOT / "data" / "vectorstore" / "rag-smoke-nomic"
    manifest_path = store / "manifest.json"
    output = ROOT / "outputs" / "rag-local-smoke"
    output.mkdir(parents=True, exist_ok=True)

    if not args.verify_existing:
        # Synthetic fixtures test plumbing; they are not research references.
        documents = [
            "DVWA Low error-based SQL injection black-box validation uses GET id on "
            "/vulnerabilities/sqli/. Compare the normal response with a SQL syntax "
            "error or database exception. Human review must validate the evidence.",
            "Boolean-based blind SQL injection compares true and false conditions on "
            "/vulnerabilities/sqli_blind/. Different existence responses are evidence.",
            "Astronomy studies stars, galaxies and planetary orbits in the solar system.",
        ]
        vectors = embed_texts(DEFAULT_EMBEDDING_MODEL, documents, batch_size=3)
        if any(len(vector) != 768 or not all(math.isfinite(value) for value in vector)
               for vector in vectors):
            raise RuntimeError("Expected three finite 768-dimensional Nomic embeddings.")
        client = chromadb.PersistentClient(path=str(store))
        collection = client.get_or_create_collection(
            name="rag_smoke", metadata={"hnsw:space": "cosine"}, embedding_function=None
        )
        collection.upsert(
            ids=["error-based", "boolean-blind", "astronomy"],
            documents=documents,
            embeddings=vectors,
            metadatas=[{"source": "synthetic-smoke", "fixture": True}] * 3,
        )
        manifest = {
            "schema_version": "1.0.0",
            "knowledge_base_id": "synthetic-rag-smoke",
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "embedding_input_format": embedding_input_format(DEFAULT_EMBEDDING_MODEL),
            "store_path": store.relative_to(ROOT).as_posix(),
            "collection_name": "rag_smoke",
            "synthetic_fixture": True,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    manifest = read_manifest(manifest_path)
    # A separate --verify-existing invocation reopens the saved store in a fresh process.
    client = chromadb.PersistentClient(path=manifest["resolved_store_path"])
    count = client.get_collection("rag_smoke", embedding_function=None).count()
    scenario = next(item for item in load_catalog()["scenarios"] if item["scenario_id"] == "S1")
    query = scenario_query(scenario)
    retrieval = retrieve_chunks(query, manifest, top_k=3, mode="focused")
    if count != 3 or retrieval["chunks"][0]["chunk_id"] != "error-based":
        raise RuntimeError("S1 did not retrieve the expected error-based fixture first.")
    result = {
        "passed": True,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "fresh_process_reopen": args.verify_existing,
        "chromadb_version": version("chromadb"),
        "pypdf_version": version("pypdf"),
        "document_count": count,
        "embedding_dimensions": 768,
        "query": query,
        "retrieval": retrieval,
        "interpretation": "Synthetic integration smoke test; not formal SQLi/RAG evaluation.",
    }
    filename = "reopen.json" if args.verify_existing else "seed.json"
    (output / filename).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "fresh_process_reopen": args.verify_existing,
                      "document_count": count, "embedding_dimensions": 768,
                      "ranked_ids": [item["chunk_id"] for item in retrieval["chunks"]]}))


if __name__ == "__main__":
    main()
