"""Versioned Qwen API response analysis for synthetic SQLi diagnosis.

The locked Ollama A prompts are source material. This module adapts their
messages for a chat API, validates the answer locally, and never sends labels.
"""

from __future__ import annotations

import copy
import json

from jsonschema import Draft202012Validator, ValidationError

import analysis_v5_pilot_cases as cases
import analyze_response_v2 as response_v2
from qwen_api_client import ChatSettings, encoded_payload, request_payload


PROMPT_VERSION = "qwen38-api-sqli-analysis-diagnosis-v1"


def prepare(document: dict, locked_row: dict, settings: ChatSettings) -> dict:
    """Adapt one locked no-RAG request without changing its evidence or labels."""
    if not cases.eligible(document) or locked_row["profile"] != "A":
        raise ValueError("Only eligible A/no-RAG cases may reach the API")
    old = locked_row["request"]
    if old["model"] != "qwen2.5:7b" or len(old["messages"]) != 2:
        raise ValueError("Unexpected frozen request")
    schema = copy.deepcopy(old["format"])
    Draft202012Validator.check_schema(schema)
    messages = copy.deepcopy(old["messages"])
    # The gateway's schema-enforcement support is unknown, so include the
    # exact output contract in the prompt and check it again after the call.
    messages[0]["content"] += (
        "\nReturn one JSON object only, without markdown or extra text. "
        "Its structure must match this JSON Schema: "
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )
    payload = request_payload(messages, settings)
    return {"prompt_version": PROMPT_VERSION, "locked_request_sha256": locked_row["request_sha256"],
            "schema": schema, "payload": payload}


def _unique_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _roles(technique):
    return {"error-based": ("baseline", "candidate"),
            "boolean-based blind": ("true_condition", "false_condition"),
            "time-based blind": ("candidate", "no_delay_control")}[technique]


def parse(document: dict, schema: dict, api_result: dict) -> dict:
    """Keep the raw model claim while rejecting fabricated trial/evidence IDs."""
    base = {"status": "analysis_error", "decision": None, "error": None,
            "warnings": [], "trial_assessments": [], "model_output": None}
    if api_result.get("status") != "ok":
        return {**base, "error": "api-" + str(api_result.get("status")),
                "halt": bool(api_result.get("halt"))}
    try:
        output = json.loads(api_result["content"], object_pairs_hook=_unique_keys,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        Draft202012Validator(schema).validate(output)
    except (KeyError, TypeError, ValueError, ValidationError):
        return {**base, "error": "invalid-json-or-schema"}
    known = {row["observation_id"] for row in document["observations"]}
    all_refs = output["evidence_refs"] + [ref for row in output["trial_assessments"]
                                            for ref in row["evidence_refs"]]
    if not set(all_refs).issubset(known):
        return {**base, "error": "unknown-observation-reference", "model_output": output}
    trial_ids = sorted({row["trial"] for row in document["observations"]})
    actual_ids = [row["trial"] for row in output["trial_assessments"]]
    if sorted(actual_ids) != trial_ids:
        return {**base, "error": "trial-set-mismatch", "model_output": output}
    roles = _roles(document["technique"])
    expected_refs = set()
    for assessment in output["trial_assessments"]:
        trial = assessment["trial"]
        required = {row["observation_id"] for row in document["observations"]
                    if row["trial"] == trial and row["role"] in roles}
        if not required.issubset(set(assessment["evidence_refs"])):
            return {**base, "error": "missing-trial-evidence", "model_output": output}
        if set(assessment["evidence_refs"]) - {row["observation_id"] for row in document["observations"]
                                               if row["trial"] == trial}:
            return {**base, "error": "cross-trial-evidence", "model_output": output}
        expected_refs.update(required)
    if not expected_refs.issubset(set(output["evidence_refs"])):
        return {**base, "error": "missing-top-level-evidence", "model_output": output}
    warnings = response_v2.audit_model_summary(output)
    pos, neg = response_v2.REASON_CODES[document["technique"]]
    if output["reason_code"] != {"positive": pos, "negative": neg,
                                  "inconclusive": "insufficient_evidence"}[output["decision"]]:
        warnings.append("reason-code-decision-mismatch")
    return {**base, "status": "ok", "decision": output["decision"],
            "trial_assessments": output["trial_assessments"], "model_output": output,
            "warnings": sorted(set(warnings))}


def payload_bytes(prepared: dict) -> bytes:
    return encoded_payload(prepared["payload"])
