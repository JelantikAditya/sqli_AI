"""Shared local Ollama and Chroma helpers for the TA RAG pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = Path(__file__).with_name("experiment_scenarios.json")
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def local_ollama_url() -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("OLLAMA_BASE_URL has an invalid port.") from exc
    if (
        parsed.scheme != "http"
        or host not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Ollama must use a local HTTP URL such as http://127.0.0.1:11434.")
    return base_url


def post_ollama(endpoint: str, payload: dict, timeout: int = 180) -> dict:
    url = local_ollama_url() + endpoint
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {message}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Cannot reach local Ollama at {url}: {reason}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama returned a response that was not a JSON object.")
    return result


def embed_texts(model: str, texts: list[str], batch_size: int = 16) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = post_ollama(
            "/api/embed",
            {"model": model, "input": batch},
            timeout=300,
        )
        values = response.get("embeddings")
        if not isinstance(values, list) or len(values) != len(batch):
            raise RuntimeError("Ollama embedding response count did not match input count.")
        for vector in values:
            if not isinstance(vector, list) or not vector:
                raise RuntimeError("Ollama returned an empty embedding vector.")
            embeddings.append(vector)
    return embeddings


def load_catalog() -> dict:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as source:
        return json.load(source)


def scenario_query(scenario: dict) -> str:
    return (
        f"DVWA black-box SQL injection validation. Security level: {scenario['security_level']}. "
        f"Technique: {scenario['sqli_type']}. HTTP method: {scenario['method']}. "
        f"Input endpoint: {scenario['input_path']}. Result endpoint: {scenario['result_path']}. "
        f"Parameter: {scenario['parameter']}. Probe kind: {scenario['probe_kind']}. "
        "Find relevant research knowledge about this SQL injection technique, "
        "DVWA behavior, and black-box validation evidence."
    )


def read_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported knowledge base manifest.")
    store_path = Path(manifest["store_path"])
    if not store_path.is_absolute():
        store_path = ROOT / store_path
    store_path = store_path.resolve()
    allowed_store = (ROOT / "data" / "vectorstore").resolve()
    if not store_path.is_relative_to(allowed_store):
        raise ValueError("Knowledge base store_path must stay under data/vectorstore/.")
    manifest["resolved_store_path"] = str(store_path)
    return manifest


def retrieve_chunks(query: str, manifest: dict, top_k: int) -> dict:
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("Install requirements-rag.txt to use ChromaDB.") from exc

    query_embedding = embed_texts(manifest["embedding_model"], [query])[0]
    client = chromadb.PersistentClient(path=manifest["resolved_store_path"])
    collection = client.get_collection(name=manifest["collection_name"])
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    ids = (results.get("ids") or [[]])[0]
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    chunks = [
        {
            "chunk_id": chunk_id,
            "text": documents[index],
            "metadata": metadatas[index],
            "distance": distances[index],
        }
        for index, chunk_id in enumerate(ids)
    ]
    return {
        "knowledge_base_id": manifest["knowledge_base_id"],
        "collection_name": manifest["collection_name"],
        "embedding_model": manifest["embedding_model"],
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "top_k_requested": top_k,
        "chunks": chunks,
    }
