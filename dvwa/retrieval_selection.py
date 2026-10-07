"""Versioned, auditable selection of SQLi reference context from an existing index."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = Path(__file__).with_name("retrieval_policy.json")
SECTION_HEADER = re.compile(
    r"(?im)^\s*(references|bibliography|daftar pustaka|appendix(?:\s+[A-Z0-9]+)?)(?:\s*[:.]\s*[^\n]*)?\s*$"
)


def load_policy() -> tuple[dict, str]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported retrieval policy schema.")
    if not 1 <= policy["candidate_pool_size"] <= 200:
        raise ValueError("Retrieval candidate pool must be between 1 and 200.")
    if not 0 < policy["duplicate_overlap_threshold"] <= 1:
        raise ValueError("Duplicate overlap threshold must be in (0, 1].")
    if not 0 <= policy["minimum_selection_score"] <= sum(policy["cue_weights"].values()):
        raise ValueError("Minimum selection score must fit the configured cue weights.")
    # Changes to matching/selection code must also change the recorded policy identity.
    policy["selector_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    return policy, digest


def curation_path(manifest: dict, policy_sha256: str) -> Path:
    return Path(manifest["resolved_store_path"]) / f"curation-{policy_sha256[:16]}.json"


def prepare_curation(manifest: dict) -> Path:
    """Annotate reference sections without changing PDF bytes, vectors or chunk text."""
    import chromadb
    from pypdf import PdfReader

    policy, policy_sha256 = load_policy()
    for package, expected in manifest.get("pdf_extractor_versions", {}).items():
        if version(package) != expected:
            raise ValueError(f"Use the original {package} version {expected} to annotate this index.")
    collection = chromadb.PersistentClient(path=manifest["resolved_store_path"]).get_collection(
        manifest["collection_name"], embedding_function=None
    )
    records = collection.get(include=["documents", "metadatas"])
    grouped = defaultdict(list)
    for chunk_id, text, metadata in zip(records["ids"], records["documents"], records["metadatas"]):
        grouped[metadata["source_path"]].append((chunk_id, text, metadata))

    annotations = {}
    for source_path, chunks in grouped.items():
        source = (ROOT / source_path).resolve()
        if not source.is_relative_to((ROOT / "sources").resolve()):
            raise ValueError("Curation PDF paths must stay inside sources/.")
        expected_hashes = {metadata["source_sha256"] for _, _, metadata in chunks}
        if expected_hashes != {hashlib.sha256(source.read_bytes()).hexdigest()}:
            raise ValueError(f"Reference changed since indexing: {source_path}")
        if source_path in policy["excluded_source_paths"]:
            for chunk_id, _, _ in chunks:
                annotations[chunk_id] = {"section": "excluded_source", "reason": policy["source_exclusion_reason"]}
            continue

        reader = PdfReader(str(source))
        pages = {}
        current_section = "body"
        for number, page in enumerate(reader.pages, 1):
            raw = page.extract_text() or ""
            normalized = " ".join(raw.split())
            boundaries = [(0, current_section)]
            for header in SECTION_HEADER.finditer(raw):
                current_section = "body" if header.group(1).lower().startswith("appendix") else "references"
                position = len(" ".join(raw[:header.start()].split()))
                boundaries.append((position, current_section))
            pages[number] = (normalized, boundaries)

        for chunk_id, text, metadata in chunks:
            page_text, boundaries = pages[metadata["page_number"]]
            start = page_text.find(text)
            section = "unclassified"
            if start >= 0:
                end = start + len(text)
                kinds = {
                    kind for index, (boundary, kind) in enumerate(boundaries)
                    if boundary < end
                    and (boundaries[index + 1][0] if index + 1 < len(boundaries) else len(page_text)) > start
                }
                section = "mixed_references" if len(kinds) > 1 else next(iter(kinds), "unclassified")
                # Author addresses and publication metadata should not occupy model context.
                emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
                if section == "body" and (len(emails) >= 2 or
                    sum(word in text.lower() for word in ("received:", "accepted:", "copyright:", "licensee")) >= 2):
                    section = "front_matter"
            annotations[chunk_id] = {"section": section}

    document = {
        "schema_version": "1.0.0",
        "knowledge_base_id": manifest["knowledge_base_id"],
        "policy_version": policy["policy_version"],
        "policy_sha256": policy_sha256,
        "annotation_sha256": hashlib.sha256(json.dumps(annotations, sort_keys=True).encode()).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "section_counts": dict(Counter(item["section"] for item in annotations.values())),
        "chunks": annotations,
    }
    output = curation_path(manifest, policy_sha256)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return output


def load_curation(manifest: dict, policy_sha256: str) -> dict:
    if manifest.get("synthetic_fixture"):
        return {"chunks": {}, "annotation_sha256": None}
    path = curation_path(manifest, policy_sha256)
    if not path.is_file():
        raise ValueError("Prepare index annotations first with dvwa/retrieval_selection.py --manifest <path>.")
    document = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(document["chunks"], sort_keys=True).encode()).hexdigest()
    if (document["knowledge_base_id"] != manifest["knowledge_base_id"]
        or document["policy_sha256"] != policy_sha256 or document["annotation_sha256"] != digest):
        raise ValueError("Curation annotation identity or hash does not match this index/policy.")
    return document


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", " ".join(text.split()))


def technical_cues(text: str, technique: str) -> dict[str, bool]:
    text = normalize(text)
    if technique == "error-based":
        explicit = r"error-based"
        # Require an actual database-error phrase, not keywords across sentences.
        evidence = (r"\b(?:sql(?:\s+engine)?|database|dbms)(?:['’]s)?"
                    r"(?:\s+(?:syntax|server|engine))?\s+(?:errors?|exceptions?)\b"
                    r"|\berror messages?\s+(?:returned\s+)?(?:from|by)\s+(?:the\s+)?(?:database|dbms|sql)\b")
    elif technique == "boolean-based blind":
        explicit = r"boolean-based|boolean.{0,12}blind|blind.{0,12}boolean"
        evidence = r"\btrue\b.{0,60}\bfalse\b|\bfalse\b.{0,60}\btrue\b|binary responses|truth-value"
    elif technique == "time-based blind":
        explicit = r"time-based|time delay|time-delay"
        evidence = r"\bsleep\b|\bdelay\b|\blatency\b|response time"
    else:
        raise ValueError("Choose a SQLi technique from the scenario catalog.")
    return {
        "technique": bool(re.search(explicit, text)),
        "primary_evidence": bool(re.search(evidence, text)),
        "response_observation": bool(re.search(r"http|html|web\s?page|response|server", text)),
        "validation": bool(re.search(r"false positive|baseline|benign|actually|execut|validat|jitter|traffic", text)),
    }


def shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", normalize(text))
    width = min(5, len(words))
    return {tuple(words[start:start + width]) for start in range(len(words) - width + 1)} if width else set()


def duplicate_overlap(first: str, second: str) -> float:
    left, right = shingles(first), shingles(second)
    return len(left & right) / min(len(left), len(right)) if left and right else 0.0


def lexical_candidates(collection, candidates: list[dict], query_vector: list[float],
                       technique: str, policy: dict, curation: dict) -> list[dict]:
    """Recover technical passages that dense top-N search missed, using existing vectors."""
    if not policy.get("lexical_expansion", False):
        return []
    existing = {item["chunk_id"] for item in candidates}
    records = collection.get(include=["documents", "metadatas"])
    extra_ids = []
    for chunk_id, text, metadata in zip(records["ids"], records["documents"], records["metadatas"]):
        section = curation["chunks"].get(chunk_id, {}).get("section", "unclassified")
        if curation["annotation_sha256"] is None:
            section = "body"
        if (chunk_id in existing or section != "body"
            or metadata.get("source_path") in policy["excluded_source_paths"]):
            continue
        cues = technical_cues(text, technique)
        if cues["technique"] or cues["primary_evidence"]:
            extra_ids.append(chunk_id)
    if not extra_ids:
        return []
    extra = collection.get(ids=extra_ids, include=["documents", "metadatas", "embeddings"])
    query_norm = math.sqrt(sum(value * value for value in query_vector))
    additions = []
    for chunk_id, text, metadata, vector in zip(extra["ids"], extra["documents"], extra["metadatas"], extra["embeddings"]):
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not norm or not query_norm or len(vector) != len(query_vector):
            raise ValueError("Stored embedding cannot be compared with this query vector.")
        cosine = sum(float(value) * query_value for value, query_value in zip(vector, query_vector)) / (norm * query_norm)
        additions.append({"chunk_id": chunk_id, "text": text, "metadata": metadata,
                          "distance": max(0.0, min(2.0, 1 - cosine)), "candidate_origin": "lexical"})
    return additions


def select_chunks(candidates: list[dict], technique: str, top_k: int, policy: dict, curation: dict) -> tuple[list, list]:
    eligible, rejected = [], []
    for candidate in candidates:
        chunk = dict(candidate)
        section = curation["chunks"].get(chunk["chunk_id"], {}).get("section", "unclassified")
        if curation["annotation_sha256"] is None:
            section = "body"  # Only the explicitly marked synthetic smoke fixture.
        reason = None
        if section == "excluded_source" or chunk["metadata"].get("source_path") in policy["excluded_source_paths"]:
            reason = "excluded_source"
        elif section in policy["excluded_sections"]:
            reason = section
        cues = technical_cues(chunk["text"], technique)
        if reason is None and not (cues["technique"] or cues["primary_evidence"]):
            reason = "no_technique_evidence"
        if reason:
            rejected.append({"chunk_id": chunk["chunk_id"], "reason": reason})
            continue
        chunk["section"] = section
        chunk["technical_cues"] = cues
        chunk["selection_score"] = sum(policy["cue_weights"][name] for name, matched in cues.items() if matched)
        if chunk["selection_score"] < policy["minimum_selection_score"]:
            rejected.append({"chunk_id": chunk["chunk_id"], "reason": "insufficient_technical_evidence"})
            continue
        eligible.append(chunk)

    # A deterministic, inspectable heuristic; its score is not a probability of relevance.
    eligible.sort(key=lambda item: (-item["selection_score"], item["distance"], item["chunk_id"]))
    selected = []
    for chunk in eligible:
        duplicate = next((item for item in selected if duplicate_overlap(chunk["text"], item["text"])
                          >= policy["duplicate_overlap_threshold"]), None)
        if duplicate:
            rejected.append({"chunk_id": chunk["chunk_id"], "reason": "duplicate_context", "duplicate_of": duplicate["chunk_id"]})
        elif len(selected) < top_k:
            selected.append(chunk)
        else:
            rejected.append({"chunk_id": chunk["chunk_id"], "reason": "outside_top_k"})
    return selected, rejected


if __name__ == "__main__":
    from rag_pipeline import read_manifest
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    path = prepare_curation(read_manifest(args.manifest))
    result = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({"curation_path": str(path), "section_counts": result["section_counts"],
                      "policy_version": result["policy_version"]}))
