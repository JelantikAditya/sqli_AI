"""Validate and package one reproducible LLM or SecLists candidate batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = Path(__file__).with_name("experiment_scenarios.json")
SCHEMA_VERSION = "1.0.0"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        document = json.load(source)
    if not isinstance(document, dict):
        raise ValueError("Candidate batch must be a JSON object.")
    return document


def validate_batch(batch: dict, source_list: Path | None) -> dict:
    if batch.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}.")

    with SCENARIOS_PATH.open("r", encoding="utf-8") as source:
        catalog = json.load(source)
    scenario_map = {item["scenario_id"]: item for item in catalog["scenarios"]}
    scenario_id = batch.get("scenario_id")
    if not isinstance(scenario_id, str) or scenario_id not in scenario_map:
        raise ValueError("scenario_id must be one of S1 through S12.")
    scenario = scenario_map[scenario_id]

    source = batch.get("source")
    rag_mode = batch.get("rag_mode")
    provenance = batch.get("provenance")
    candidates = batch.get("candidates")
    if not isinstance(source, str) or source not in {"LLM", "SecLists"}:
        raise ValueError("source must be LLM or SecLists.")
    if not isinstance(rag_mode, str):
        raise ValueError("rag_mode must be a string.")
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object.")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 10:
        raise ValueError("candidates must contain between 1 and 10 items.")

    if source == "SecLists":
        if rag_mode != "not_applicable":
            raise ValueError("SecLists batches must use rag_mode not_applicable.")
        required = ("repository", "revision", "list_path", "list_sha256")
        if any(not isinstance(provenance.get(key), str) or not provenance[key] for key in required):
            raise ValueError("SecLists provenance needs repository, revision, list_path, and list_sha256.")
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", provenance["revision"]):
            raise ValueError("SecLists revision must be an immutable 40- or 64-character commit SHA.")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", provenance["list_sha256"]):
            raise ValueError("list_sha256 must be a 64-character SHA-256 digest.")
        if source_list is None:
            raise ValueError("Pass --source-list to verify SecLists line provenance.")
        source_bytes = source_list.read_bytes()
        actual_digest = hashlib.sha256(source_bytes).hexdigest()
        if actual_digest.lower() != provenance["list_sha256"].lower():
            raise ValueError("SecLists file digest does not match provenance.list_sha256.")
        source_lines = source_bytes.decode("utf-8", "replace").splitlines()
        allowed_provenance = set(required)
    else:
        if rag_mode not in {"on", "off"}:
            raise ValueError("LLM batches must use rag_mode on or off.")
        required = (
            "comparison_id",
            "model",
            "prompt_version",
            "temperature",
            "seed",
            "knowledge_base_id",
            "retrieved_chunk_ids",
            "retrieval_top_k",
        )
        if any(key not in provenance for key in required):
            raise ValueError(
                "LLM provenance needs model, prompt_version, temperature, seed, "
                "knowledge_base_id, retrieved_chunk_ids, retrieval_top_k, and comparison_id."
            )
        if not isinstance(provenance["comparison_id"], str) or not provenance["comparison_id"]:
            raise ValueError("provenance.comparison_id must identify the paired RAG-off/RAG-on run.")
        allowed_provenance = set(required) | {
            "provider",
            "generation_config_id",
            "prompt_sha256",
        }
        if "provider" in provenance and (
            not isinstance(provenance["provider"], str) or not provenance["provider"]
        ):
            raise ValueError("provenance.provider must be a non-empty string when provided.")
        if "generation_config_id" in provenance and (
            not isinstance(provenance["generation_config_id"], str)
            or not provenance["generation_config_id"]
        ):
            raise ValueError("provenance.generation_config_id must be a non-empty string when provided.")
        if not isinstance(provenance["model"], str) or not provenance["model"]:
            raise ValueError("provenance.model must be a non-empty string.")
        if not isinstance(provenance["prompt_version"], str) or not provenance["prompt_version"]:
            raise ValueError("provenance.prompt_version must be a non-empty string.")
        if (
            isinstance(provenance["temperature"], bool)
            or not isinstance(provenance["temperature"], (int, float))
            or not math.isfinite(provenance["temperature"])
            or provenance["temperature"] < 0
        ):
            raise ValueError("provenance.temperature must be numeric.")
        if provenance["seed"] is not None and (
            isinstance(provenance["seed"], bool) or not isinstance(provenance["seed"], int)
        ):
            raise ValueError("provenance.seed must be an integer or null.")
        retrieved_ids = provenance.get("retrieved_chunk_ids", [])
        knowledge_base_id = provenance.get("knowledge_base_id")
        if not isinstance(retrieved_ids, list) or any(not isinstance(item, str) for item in retrieved_ids):
            raise ValueError("retrieved_chunk_ids must be an array of strings.")
        if any(not item for item in retrieved_ids):
            raise ValueError("retrieved_chunk_ids cannot contain empty values.")
        if len(set(retrieved_ids)) != len(retrieved_ids):
            raise ValueError("retrieved_chunk_ids must be unique.")
        retrieval_top_k = provenance["retrieval_top_k"]
        if rag_mode == "on" and (
            not isinstance(knowledge_base_id, str)
            or not knowledge_base_id
            or not retrieved_ids
            or isinstance(retrieval_top_k, bool)
            or not isinstance(retrieval_top_k, int)
            or retrieval_top_k < 1
        ):
            raise ValueError("RAG-on requires knowledge_base_id, retrieved chunks, and a positive retrieval_top_k.")
        if rag_mode == "off" and (
            knowledge_base_id is not None or retrieved_ids or retrieval_top_k is not None
        ):
            raise ValueError("RAG-off must not include a knowledge base or retrieved chunks.")
        if "prompt_sha256" in provenance and not re.fullmatch(
            r"[0-9a-fA-F]{64}", str(provenance["prompt_sha256"])
        ):
            raise ValueError("prompt_sha256 must be a 64-character SHA-256 digest.")

    unexpected_provenance = set(provenance) - allowed_provenance
    if unexpected_provenance:
        raise ValueError(
            "Unsupported provenance field(s): " + ", ".join(sorted(unexpected_provenance))
        )

    seen_ids: set[str] = set()
    normalized_candidates: list[dict] = []
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise ValueError(f"Candidate {index} must be an object.")
        candidate_id = candidate.get("candidate_id")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id.strip()
            or candidate_id != candidate_id.strip()
            or candidate_id in seen_ids
        ):
            raise ValueError(f"Candidate {index} needs a unique non-empty candidate_id.")
        seen_ids.add(candidate_id)

        if scenario["probe_kind"] == "boolean_pair":
            values = (candidate.get("true_payload"), candidate.get("false_payload"))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"Candidate {candidate_id} needs true_payload and false_payload.")
            if "payload" in candidate:
                raise ValueError(f"Boolean candidate {candidate_id} cannot also define payload.")
        else:
            value = candidate.get("payload")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Candidate {candidate_id} needs a non-empty payload.")
            if "true_payload" in candidate or "false_payload" in candidate:
                raise ValueError(f"Non-boolean candidate {candidate_id} cannot define a payload pair.")

        fields = [candidate.get(key) for key in ("payload", "true_payload", "false_payload")]
        if any(isinstance(value, str) and "REPLACE_WITH_" in value for value in fields):
            raise ValueError("Replace all payload placeholders before preparing a batch.")

        prepared = {
            "candidate_id": candidate_id,
            "scenario_id": scenario_id,
            "source": source,
            "rag_mode": rag_mode,
            "provenance": provenance,
        }
        for field in ("payload", "true_payload", "false_payload"):
            if field in candidate:
                prepared[field] = candidate[field]

        if source == "SecLists":
            if scenario["probe_kind"] == "boolean_pair":
                line_numbers = candidate.get("source_line_numbers")
                if (
                    not isinstance(line_numbers, list)
                    or len(line_numbers) != 2
                    or any(
                        isinstance(number, bool)
                        or not isinstance(number, int)
                        or not 1 <= number <= len(source_lines)
                        for number in line_numbers
                    )
                ):
                    raise ValueError(
                        f"Boolean SecLists candidate {candidate_id} needs two valid source_line_numbers."
                    )
                if candidate["true_payload"] != source_lines[line_numbers[0] - 1]:
                    raise ValueError(f"Candidate {candidate_id} true_payload does not match its SecLists line.")
                if candidate["false_payload"] != source_lines[line_numbers[1] - 1]:
                    raise ValueError(f"Candidate {candidate_id} false_payload does not match its SecLists line.")
                prepared["provenance"] = {**provenance, "source_line_numbers": line_numbers}
            else:
                line_number = candidate.get("source_line_number")
                if (
                    isinstance(line_number, bool)
                    or not isinstance(line_number, int)
                    or not 1 <= line_number <= len(source_lines)
                ):
                    raise ValueError(f"Candidate {candidate_id} has an invalid source_line_number.")
                if candidate["payload"] != source_lines[line_number - 1]:
                    raise ValueError(f"Candidate {candidate_id} payload does not match its SecLists line.")
                prepared["provenance"] = {**provenance, "source_line_number": line_number}

        normalized_candidates.append(prepared)

    if source_list is not None and source != "SecLists":
        raise ValueError("--source-list is only valid for SecLists batches.")

    return {"schema_version": SCHEMA_VERSION, "candidates": normalized_candidates}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Candidate batch JSON")
    parser.add_argument("--source-list", type=Path, help="Exact local SecLists file used for line verification")
    parser.add_argument("--output", type=Path, help="Optional destination under results/raw")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    batch = read_json(args.input)
    payload_document = validate_batch(batch, args.source_list)

    raw_directory = ROOT / "results" / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    if args.output:
        output_path = args.output.resolve()
    else:
        source_tag = batch["source"].lower()
        rag_tag = batch["rag_mode"].replace("_", "-")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = (raw_directory / f"candidates-{batch['scenario_id']}-{source_tag}-{rag_tag}-{timestamp}-{uuid4().hex[:6]}.json").resolve()
    if not output_path.is_relative_to(raw_directory.resolve()):
        raise SystemExit("Output must stay inside results/raw/.")

    with output_path.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(payload_document, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(f"Prepared candidate batch: {output_path}")
    print(json.dumps({"scenario_id": batch["scenario_id"], "source": batch["source"], "rag_mode": batch["rag_mode"], "candidate_count": len(payload_document["candidates"])}))


if __name__ == "__main__":
    main()
