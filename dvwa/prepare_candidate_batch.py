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


def transform_seclists_payload(source_line: str, transform: dict, boolean_branch: str | None = None) -> str:
    """Apply the one reviewed, deterministic wrapper used for DVWA's id field."""
    if not isinstance(transform, dict) or set(transform) != {
        "rule_id", "wrapper", "placeholder_values"
    }:
        raise ValueError("source_transform must define rule_id, wrapper, and placeholder_values.")
    if transform["rule_id"] != "seclists-mariadb-id-fragment-v1":
        raise ValueError("Unsupported SecLists source_transform rule_id.")

    wrappers = {
        "quoted_id": ("1' ", " #"),
        "numeric_id": ("1 ", " #"),
    }
    if transform["wrapper"] not in wrappers:
        raise ValueError("source_transform.wrapper must be quoted_id or numeric_id.")

    template = source_line
    if boolean_branch is not None:
        if boolean_branch not in {"true", "false"}:
            raise ValueError("boolean_branch must be true or false.")
        equality = "[RANDNUM]=[RANDNUM]"
        if template.count(equality) != 1:
            raise ValueError("Boolean SecLists transform requires exactly one [RANDNUM]=[RANDNUM] condition.")
        replacement = "1=1" if boolean_branch == "true" else "1=2"
        template = template.replace(equality, replacement, 1)
    values = transform["placeholder_values"]
    allowed_names = {
        "RANDNUM", "RANDNUM1", "RANDNUM2", "RANDNUM3", "RANDNUM4", "RANDNUM5",
        "RANDSTR", "ORIGVALUE", "SLEEPTIME", "DELIMITER_START", "DELIMITER_STOP",
    }
    if not isinstance(values, dict) or any(
        name not in allowed_names or not isinstance(value, str) or not value
        for name, value in values.items()
    ):
        raise ValueError("placeholder_values must map supported SecLists placeholders to non-empty strings.")
    numeric_names = {"RANDNUM", "RANDNUM1", "RANDNUM2", "RANDNUM3", "RANDNUM4", "RANDNUM5", "ORIGVALUE", "SLEEPTIME"}
    for name, value in values.items():
        if name in numeric_names and not re.fullmatch(r"[0-9]{1,6}", value):
            raise ValueError(f"SecLists placeholder {name} must be a small integer.")
        if name == "SLEEPTIME" and not 1 <= int(value) <= 2:
            raise ValueError("SLEEPTIME is capped at two seconds for the local pilot.")
        if name in {"RANDSTR", "DELIMITER_START", "DELIMITER_STOP"} and not re.fullmatch(r"[A-Za-z0-9]{1,16}", value):
            raise ValueError(f"SecLists placeholder {name} must be a short alphanumeric marker.")

    placeholders = set(re.findall(r"\[([A-Z_0-9]+)\]", template))
    if placeholders - set(values):
        raise ValueError("source_transform is missing placeholder values: " + ", ".join(sorted(placeholders - set(values))))
    for name, value in values.items():
        template = template.replace(f"[{name}]", value)

    if re.search(r"[\[\]]", template):
        raise ValueError("Unreplaced placeholder remains after SecLists transformation.")
    if ";" in template or "--" in template or "#" in template:
        raise ValueError("SecLists source line contains a statement separator or comment marker.")

    prefix, suffix = wrappers[transform["wrapper"]]
    fragment = template.strip()
    if not fragment:
        raise ValueError("SecLists source line cannot be empty after transformation.")
    if fragment.upper().startswith("RLIKE "):
        # RLIKE rows are expression suffixes and need an explicit left operand.
        fragment = "AND 1 " + fragment
    elif not fragment.upper().startswith("AND "):
        fragment = "AND " + fragment
    return prefix + fragment + suffix


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
        allowed_provenance = set(required) | {"selection_rule_id", "selection_manifest_sha256"}
        selection_rule_id = provenance.get("selection_rule_id")
        manifest_digest = provenance.get("selection_manifest_sha256")
        if (selection_rule_id is None) != (manifest_digest is None):
            raise ValueError("SecLists selection_rule_id and selection_manifest_sha256 must be provided together.")
        if selection_rule_id is not None:
            if not isinstance(selection_rule_id, str) or not selection_rule_id:
                raise ValueError("selection_rule_id must be a non-empty string.")
            if not isinstance(manifest_digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", manifest_digest):
                raise ValueError("selection_manifest_sha256 must be a SHA-256 digest.")
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
            "retrieval_query_version",
            "retrieval_policy_sha256",
            "retrieval_curation_sha256",
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
        # Preserve selection provenance in runner logs; RAG-off carries no retrieval state.
        for field in ("retrieval_query_version", "retrieval_policy_sha256", "retrieval_curation_sha256"):
            if field not in provenance:
                continue  # Existing batches remain readable.
            value = provenance[field]
            if rag_mode == "off" and value is not None:
                raise ValueError(f"RAG-off requires {field} to be null.")
            if rag_mode == "on" and (not isinstance(value, str) or not value):
                raise ValueError(f"RAG-on requires a non-empty {field} when provided.")
            if rag_mode == "on" and field.endswith("sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                raise ValueError(f"{field} must be a SHA-256 digest.")

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

        source_transform = candidate.get("source_transform")
        if source_transform is not None and source != "SecLists":
            raise ValueError("source_transform is only supported for SecLists candidates.")
        if scenario["probe_kind"] == "boolean_pair":
            if "payload" in candidate:
                raise ValueError(f"Boolean candidate {candidate_id} cannot also define payload.")
            if source_transform is None:
                values = (candidate.get("true_payload"), candidate.get("false_payload"))
                if any(not isinstance(value, str) or not value.strip() for value in values):
                    raise ValueError(f"Candidate {candidate_id} needs true_payload and false_payload.")
        else:
            if "true_payload" in candidate or "false_payload" in candidate:
                raise ValueError(f"Non-boolean candidate {candidate_id} cannot define a payload pair.")
            value = candidate.get("payload")
            if source_transform is None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"Candidate {candidate_id} needs a non-empty payload.")

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
            if source_transform is not None and (
                not isinstance(source_transform, dict)
                or source_transform.get("rule_id") != "seclists-mariadb-id-fragment-v1"
            ):
                raise ValueError(f"Candidate {candidate_id} has an unsupported source_transform.")
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
                if source_transform is not None:
                    if line_numbers[0] != line_numbers[1]:
                        raise ValueError("Derived SecLists boolean pairs must point to the same source template line.")
                    expected_true = transform_seclists_payload(
                        source_lines[line_numbers[0] - 1], source_transform, "true"
                    )
                    expected_false = transform_seclists_payload(
                        source_lines[line_numbers[1] - 1], source_transform, "false"
                    )
                    for field, expected in (("true_payload", expected_true), ("false_payload", expected_false)):
                        supplied = candidate.get(field)
                        if supplied is not None and supplied != expected:
                            raise ValueError(f"Candidate {candidate_id} {field} does not match its deterministic transform.")
                        prepared[field] = expected
                else:
                    if candidate["true_payload"] != source_lines[line_numbers[0] - 1]:
                        raise ValueError(f"Candidate {candidate_id} true_payload does not match its SecLists line.")
                    if candidate["false_payload"] != source_lines[line_numbers[1] - 1]:
                        raise ValueError(f"Candidate {candidate_id} false_payload does not match its SecLists line.")
                prepared["provenance"] = {**provenance, "source_line_numbers": line_numbers}
                if source_transform is not None:
                    prepared["provenance"]["source_transform"] = source_transform
            else:
                line_number = candidate.get("source_line_number")
                if (
                    isinstance(line_number, bool)
                    or not isinstance(line_number, int)
                    or not 1 <= line_number <= len(source_lines)
                ):
                    raise ValueError(f"Candidate {candidate_id} has an invalid source_line_number.")
                if source_transform is not None:
                    expected = transform_seclists_payload(source_lines[line_number - 1], source_transform)
                    supplied = candidate.get("payload")
                    if supplied is not None and supplied != expected:
                        raise ValueError(f"Candidate {candidate_id} payload does not match its deterministic transform.")
                    prepared["payload"] = expected
                elif candidate["payload"] != source_lines[line_number - 1]:
                    raise ValueError(f"Candidate {candidate_id} payload does not match its SecLists line.")
                prepared["provenance"] = {**provenance, "source_line_number": line_number}
                if source_transform is not None:
                    prepared["provenance"]["source_transform"] = source_transform

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
