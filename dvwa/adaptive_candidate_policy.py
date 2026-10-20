"""Technique-aware candidate validation and evidence adapters for adaptive pilots."""

from __future__ import annotations

import hashlib
import json
import re

from validation_loop import (blind_response_signature, matched_no_delay_payload,
                             sanitized_review_excerpt, sql_error_markers)


def candidate_values(candidate: dict, probe_kind: str) -> tuple[str, ...]:
    """Return the ordered values that identify one logical candidate."""
    if not isinstance(candidate, dict):
        raise ValueError("An adaptive candidate must be an object.")
    if probe_kind == "boolean_pair":
        values = (candidate.get("true_payload"), candidate.get("false_payload"))
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Boolean candidates need true and false parameter values.")
        if values[0] == values[1]:
            raise ValueError("Boolean true and false values must differ.")
        if candidate.get("payload") is not None:
            raise ValueError("Boolean candidates cannot also define payload.")
    else:
        value = candidate.get("payload")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Error and timing candidates need a parameter value.")
        if candidate.get("true_payload") is not None or candidate.get("false_payload") is not None:
            raise ValueError("Only Boolean candidates may define paired values.")
        values = (value,)
    for value in values:
        if len(value) > 256 or any(ord(char) < 32 for char in value) or ";" in value:
            raise ValueError("Candidate values must be bounded single-line parameters without stacked statements.")
        if re.search(r"\b(?:drop|delete|insert|update|truncate|alter|create|grant|revoke|load_file|xp_cmdshell|sys_exec)\b|\binto\s+(?:out|dump)file\b", value, re.I):
            raise ValueError("Candidate is outside the read-only local SQLi policy.")
    if probe_kind != "single_time" and any(re.search(r"\b(?:sleep|benchmark|waitfor|pg_sleep|dbms_lock)\b", value, re.I) for value in values):
        raise ValueError("Timing expressions are allowed only for time-based scenarios.")
    if probe_kind == "single_time":
        if re.search(r"\b(?:benchmark|waitfor|pg_sleep|dbms_lock)\b", values[0], re.I):
            raise ValueError("Time candidates may use only the bounded literal SLEEP form.")
        matched_no_delay_payload(values[0])
    return values


def candidate_key(candidate: dict, probe_kind: str) -> str:
    values = candidate_values(candidate, probe_kind)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def observation_document(scenario: dict, captured: list[dict], confirmations: int,
                         time_threshold_ms: float) -> dict:
    """Translate executor callbacks into the versioned Qwen analysis input."""
    roles = {"baseline": "baseline", "candidate": "candidate", "control": "no_delay_control",
             "true_condition": "true_condition", "false_condition": "false_condition"}
    technique = scenario["sqli_type"]
    observations = []
    for index, item in enumerate(captured, 1):
        response = item["response"]
        role = roles[item["role"]]
        markers = []
        signature = blind_response_signature(response)
        if signature == (True, False):
            markers.append("user_id_exists")
        elif signature == (False, True):
            markers.append("user_id_missing")
        if "first name:" in response["body"].lower():
            markers.append("benign_record")
        diagnostics = (list(item["indicators"]) if technique == "error-based"
                       else sql_error_markers(response["body"]))
        observations.append({"observation_id": f"obs-{index:03d}", "trial": item["trial"],
                             "role": role, "http_status": response["status"],
                             "elapsed_ms": response["elapsed_ms"],
                             "response_sha256": response["body_sha256"],
                             "review_excerpt": sanitized_review_excerpt(response["body"]),
                             "diagnostics": sorted(diagnostics),
                             "content_markers": sorted(markers)})
    return {"schema_version": "1.0.0", "technique": technique,
            "injection_point": {key: scenario[key] for key in ("method", "input_path", "result_path", "parameter")},
            "runtime_status": "valid", "baseline_valid": True,
            "time_threshold_ms": time_threshold_ms, "observations": observations}


def candidate_probe_payload(candidate: dict, role: str) -> str:
    """Map evidence roles to the exact safe value submitted to the executor."""
    if role == "baseline":
        return "1"
    if role in {"candidate", "single"}:
        return candidate["payload"]
    if role in {"control", "no_delay_control"}:
        return matched_no_delay_payload(candidate["payload"])
    if role == "true_condition":
        return candidate["true_payload"]
    if role == "false_condition":
        return candidate["false_payload"]
    raise ValueError("Unknown observation role: " + str(role))
