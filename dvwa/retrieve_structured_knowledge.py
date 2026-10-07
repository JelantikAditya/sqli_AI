"""Semantic top-k retrieval across complete proposal JSON entries."""

import hashlib
import json
from pathlib import Path

from knowledge_corpus import CORPUS_KIND, ROOT, TECHNIQUES, prepare_documents, validate_corpus


def retrieval_policy() -> tuple[dict, str]:
    policy = {"version": "proposal-semantic-top-k-v1", "metric": "cosine",
              "technique_filter": False, "reranking": False, "lexical_expansion": False,
              "unit": "complete-json-pattern", "selector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return policy, hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def retrieve(query: str, manifest: dict, top_k: int, technique: str) -> dict:
    import chromadb
    from rag_pipeline import embed_texts

    if manifest.get("corpus_kind") != CORPUS_KIND or manifest.get("purpose") != "proposal-rag":
        raise ValueError("Proposal retrieval requires the structured OWASP/PayloadsAllTheThings index; PDF indexes are diagnostic only.")
    if technique not in TECHNIQUES or not 1 <= top_k <= 10:
        raise ValueError("Choose one proposal SQLi technique and top_k between 1 and 10.")
    corpus_path = ROOT / manifest["corpus_path"]
    corpus, lock = validate_corpus(corpus_path)
    if (hashlib.sha256(corpus_path.read_bytes()).hexdigest() != manifest["corpus_sha256"]
        or corpus["source_lock_sha256"] != manifest["source_lock_sha256"]):
        raise ValueError("Corpus identity changed; build a new structured index.")
    expected = {item["id"]: item for item in prepare_documents(corpus, lock)}
    collection = chromadb.PersistentClient(path=manifest["resolved_store_path"]).get_collection(
        manifest["collection_name"], embedding_function=None)
    if collection.count() != len(expected):
        raise ValueError("Index count differs from the validated proposal corpus.")
    available = len(expected)
    vector = embed_texts(manifest["embedding_model"], [query], task="query",
                         input_format=manifest["embedding_input_format"])[0]
    results = collection.query(query_embeddings=[vector], n_results=min(top_k, available),
        include=["documents", "metadatas", "distances"])
    chunks = []
    for chunk_id, text, metadata, distance in zip(results["ids"][0], results["documents"][0],
            results["metadatas"][0], results["distances"][0]):
        original = expected.get(chunk_id)
        if original is None or text != original["text"] or metadata != original["metadata"]:
            raise ValueError("Stored knowledge entry differs from the validated corpus.")
        chunks.append({"chunk_id": chunk_id, "text": text, "metadata": metadata,
                       "source_refs": json.loads(metadata["source_refs_json"]),
                       "distance": distance, "candidate_origin": "semantic", "section": "structured-knowledge"})
    policy, policy_sha256 = retrieval_policy()
    return {"knowledge_base_id": manifest["knowledge_base_id"], "collection_name": manifest["collection_name"],
            "embedding_model": manifest["embedding_model"], "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "top_k_requested": top_k, "retrieval_mode": "proposal", "selection_policy": policy,
            "selection_policy_sha256": policy_sha256, "curation_annotation_sha256": manifest["corpus_sha256"],
            "source_lock_sha256": manifest["source_lock_sha256"], "candidate_pool": [
                {"chunk_id": item["chunk_id"], "distance": item["distance"], "origin": "semantic"} for item in chunks],
            "semantic_pool_size": available, "lexical_added_count": 0, "rejected_candidates": [],
            "rejection_counts": {}, "shortfall": max(0, top_k - len(chunks)), "chunks": chunks}
