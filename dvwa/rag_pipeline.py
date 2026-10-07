"""Shared local Ollama and Chroma helpers for the TA RAG pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = Path(__file__).with_name("experiment_scenarios.json")
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
QUERY_VERSION = "sqli-injection-point-query-v3"


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


def embedding_input_format(model: str) -> str:
    return "nomic-search-prefix-v1" if model.split(":", 1)[0] == "nomic-embed-text" else "raw-v1"


def embed_texts(
    model: str,
    texts: list[str],
    batch_size: int = 16,
    *,
    task: str = "document",
    input_format: str | None = None,
) -> list[list[float]]:
    if batch_size < 1 or task not in {"document", "query"}:
        raise ValueError("Use a positive batch size and task document or query.")
    input_format = input_format or embedding_input_format(model)
    if input_format not in {"raw-v1", "nomic-search-prefix-v1"}:
        raise ValueError("Unknown embedding input format.")
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        # Nomic requires distinct instructions for indexed text and search queries.
        if input_format == "nomic-search-prefix-v1":
            batch = [f"search_{task}: {text}" for text in batch]
        response = post_ollama(
            "/api/embed",
            # Fail visibly when a chunk exceeds context rather than silently cutting it.
            {"model": model, "input": batch, "truncate": False},
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


def active_manifest_path() -> Path:
    pointer = ROOT / "knowledge/active-index.local.json"
    if not pointer.is_file():
        raise ValueError("Build the proposal corpus first with dvwa/build_knowledge_base.py.")
    selected = json.loads(pointer.read_text(encoding="utf-8"))
    path = (ROOT / selected["manifest_path"]).resolve()
    manifest = read_manifest(path)
    if manifest["knowledge_base_id"] != selected["knowledge_base_id"]:
        raise ValueError("Active index pointer identity mismatch.")
    return path


def injection_point_context(scenario: dict, zap_report: Path | None = None) -> dict:
    # Only safe coordinates enter the query; values, cookies and labels never do.
    point = {"method": scenario["method"], "path": scenario["input_path"],
             "parameter": scenario["parameter"], "source": "scenario-catalog-smoke"}
    if zap_report is None:
        return point
    data = zap_report.read_bytes()
    report = json.loads(data)
    if report.get("run_metadata", {}).get("security_level") != scenario["security_level"]:
        raise ValueError("Normalized ZAP report level does not match the selected scenario.")
    matching = [item for item in report.get("candidate_injection_points", [])
                if (item.get("path"), item.get("method"), item.get("parameter"))
                == (point["path"], point["method"], point["parameter"])]
    if not matching:
        raise ValueError("No matching injection point in this normalized ZAP report.")
    return {**point, "source": "normalized-zap", "report_sha256": hashlib.sha256(data).hexdigest(),
            "source_observation_id": matching[0].get("source_observation_id"),
            "verification_status": matching[0].get("verification_status", "unverified")}


def scenario_query(scenario: dict, mode: str = "proposal", injection_point: dict | None = None) -> str:
    if mode == "proposal":
        point = injection_point or injection_point_context(scenario)
        return (scenario_query(scenario, mode="focused")
                + f" Injection point: HTTP {point['method']}; input path {point['path']}; "
                f"parameter {point['parameter']}; probe kind {scenario['probe_kind']}.")
    if mode == "focused":
        # Transport and level stay in scenario metadata/the generator prompt. Retrieve
        # general technique knowledge without feeding expected vulnerability labels.
        queries = {
            "error-based": (
                "Error-based SQL injection. SQL engine error messages returned in HTTP responses; "
                "interpreting database syntax errors; validating an injection point with a "
                "benign baseline and execution evidence."
            ),
            "boolean-based blind": (
                "Boolean-based blind SQL injection. True and false conditions producing different "
                "HTTP response content; mapping binary responses and comparing benign controls "
                "while accounting for dynamic page content."
            ),
            "time-based blind": (
                "Time-based blind SQL injection. Conditional database delays and response time; "
                "repeated latency measurements compared with a benign baseline; distinguishing "
                "SQL-induced delays from network jitter and server load."
            ),
        }
        return queries[scenario["sqli_type"]]
    if mode != "legacy":
        raise ValueError("Query mode must be focused or legacy.")
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


def retrieve_chunks(
    query: str, manifest: dict, top_k: int, *, technique: str | None = None, mode: str = "proposal"
) -> dict:
    if mode == "proposal":
        from retrieve_structured_knowledge import retrieve
        if technique is None:
            technique = next((kind for kind in ("error-based", "boolean-based blind", "time-based blind")
                              if kind in query.lower()), None)
        return retrieve(query, manifest, top_k, technique)
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("Install requirements-rag.txt to use ChromaDB.") from exc
    if not 1 <= top_k <= 10 or mode not in {"focused", "legacy"}:
        raise ValueError("Use top_k between 1 and 10 and mode focused or legacy.")
    policy = curation = None
    policy_sha256 = None
    if mode == "focused":
        from retrieval_selection import load_policy, load_curation, lexical_candidates, select_chunks
        if technique is None:
            technique = next((kind for kind in ("error-based", "boolean-based blind", "time-based blind")
                              if kind in query.lower()), None)
        if technique is None:
            raise ValueError("Specify the SQLi technique for focused context selection.")
        policy, policy_sha256 = load_policy()
        curation = load_curation(manifest, policy_sha256)

    query_embedding = embed_texts(
        manifest["embedding_model"],
        [query],
        task="query",
        # Older manifests were indexed without prefixes; retain their matching format.
        input_format=manifest.get("embedding_input_format", "raw-v1"),
    )[0]
    client = chromadb.PersistentClient(path=manifest["resolved_store_path"])
    collection = client.get_collection(name=manifest["collection_name"], embedding_function=None)
    collection_count = collection.count()
    if not collection_count:
        raise ValueError("The knowledge base collection is empty.")
    pool_size = min(collection_count, policy["candidate_pool_size"] if policy else top_k)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=pool_size,
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
            "candidate_origin": "semantic",
        }
        for index, chunk_id in enumerate(ids)
    ]
    lexical_additions = []
    if policy:
        lexical_additions = lexical_candidates(collection, chunks, query_embedding, technique, policy, curation)
        chunks.extend(lexical_additions)
    candidate_pool = [{"chunk_id": item["chunk_id"], "distance": item["distance"],
                       "origin": item["candidate_origin"]} for item in chunks]
    rejected = []
    if policy:
        chunks, rejected = select_chunks(chunks, technique, top_k, policy, curation)
    return {
        "knowledge_base_id": manifest["knowledge_base_id"],
        "collection_name": manifest["collection_name"],
        "embedding_model": manifest["embedding_model"],
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "top_k_requested": top_k,
        "retrieval_mode": mode,
        "selection_policy": policy,
        "selection_policy_sha256": policy_sha256,
        "curation_annotation_sha256": curation["annotation_sha256"] if curation else None,
        "candidate_pool": candidate_pool,
        "semantic_pool_size": pool_size,
        "lexical_added_count": len(lexical_additions),
        "rejected_candidates": rejected,
        "rejection_counts": dict(Counter(item["reason"] for item in rejected)),
        "shortfall": max(0, top_k - len(chunks)),
        "chunks": chunks,
    }
