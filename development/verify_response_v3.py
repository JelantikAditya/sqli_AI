"""Independent measured-evidence verifier and agreement gate; never rewrites Qwen."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_VERSION = "measured-evidence-decimal-v3"
COMBINATION_POLICY = "binary-agreement-else-abstain-v3"
REASONS = {
    "error-based": {"positive": "new_database_diagnostic", "negative": "no_new_database_diagnostic"},
    "boolean-based blind": {"positive": "boolean_difference", "negative": "no_boolean_difference"},
    "time-based blind": {"positive": "matched_delay", "negative": "no_matched_delay"},
}
ROLES = {
    "error-based": ("baseline", "candidate"),
    "boolean-based blind": ("true_condition", "false_condition"),
    "time-based blind": ("candidate", "no_delay_control"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def valid_blind_status(observation):
    return observation["http_status"] == 200 or (
        observation["http_status"] == 404 and set(observation["content_markers"]) == {"user_id_missing"})


def verify(document):
    """Use HTTP measurements only. No scenario, expected label, executor signal or model output."""
    result = {"verifier_version": VERIFIER_VERSION, "status": "input_invalid", "decision": "not_evaluable",
              "reason_code": "input_invalid", "observed_trials": [], "positive_trial_count": 0,
              "negative_trial_count": 0, "trial_assessments": [], "issues": []}
    schema = json.loads((ROOT / "schemas/qwen-analysis-input.schema.json").read_text(encoding="utf-8"))
    if not Draft202012Validator(schema).is_valid(document):
        result["issues"].append("input_schema_invalid")
        return result
    numbers = [document["time_threshold_ms"], *(o["elapsed_ms"] for o in document["observations"] if o["elapsed_ms"] is not None)]
    if any(not math.isfinite(number) for number in numbers):
        result["issues"].append("non_finite_measurement")
        return result
    ids = [o["observation_id"] for o in document["observations"]]
    if len(ids) != len(set(ids)):
        result["issues"].append("duplicate_observation_id")
        return result
    if document["runtime_status"] != "valid" or not document["baseline_valid"]:
        result.update(status="runtime_invalid", reason_code="runtime_invalid")
        return result
    technique = document["technique"]
    trials = sorted({o["trial"] for o in document["observations"]})
    result["observed_trials"] = trials
    required_roles = set(ROLES[technique]) | {"baseline"}
    for trial in trials:
        observations = [o for o in document["observations"] if o["trial"] == trial]
        roles = [o["role"] for o in observations]
        if len(roles) != len(set(roles)) or set(roles) - required_roles:
            result["issues"].append(f"trial_{trial}_ambiguous_roles")
            return result
        by_role = {o["role"]: o for o in observations}
        row = {"trial": trial, "outcome": "unknown", "evidence_refs": [o["observation_id"] for o in observations],
               "checks": {}, "candidate_minus_control_ms": None}
        if set(roles) != required_roles or any(o[key] is None for o in observations
                                             for key in ("http_status", "elapsed_ms", "response_sha256")):
            row["checks"]["complete_measurements"] = False
            result["issues"].append(f"trial_{trial}_incomplete_measurements")
            result["trial_assessments"].append(row)
            continue
        left, right = (by_role[role] for role in ROLES[technique])
        row["evidence_refs"] = [left["observation_id"], right["observation_id"]]
        if technique == "error-based":
            row["checks"] = {"new_database_diagnostic": bool(set(right["diagnostics"]) - set(left["diagnostics"]))}
        else:
            row["checks"] = {
                "valid_http_statuses": valid_blind_status(left) and valid_blind_status(right),
                "no_sql_diagnostics": not left["diagnostics"] and not right["diagnostics"],
            }
            left_markers, right_markers = set(left["content_markers"]), set(right["content_markers"])
            if technique == "boolean-based blind":
                row["checks"]["ordered_boolean_markers"] = (
                    left_markers == {"user_id_exists"} and right_markers == {"user_id_missing"})
            else:
                # Compare the supplied decimal measurements without binary-float drift.
                delta = Decimal(str(left["elapsed_ms"])) - Decimal(str(right["elapsed_ms"]))
                row["candidate_minus_control_ms"] = str(delta)
                row["checks"]["matching_valid_markers"] = (
                    left_markers == right_markers and left_markers in ({"user_id_exists"}, {"user_id_missing"}))
                row["checks"]["delta_reaches_threshold"] = delta >= Decimal(str(document["time_threshold_ms"]))
        row["outcome"] = "positive" if all(row["checks"].values()) else "negative"
        result["trial_assessments"].append(row)
    result["positive_trial_count"] = sum(r["outcome"] == "positive" for r in result["trial_assessments"])
    result["negative_trial_count"] = sum(r["outcome"] == "negative" for r in result["trial_assessments"])
    if trials != [1, 2, 3] or any(r["outcome"] == "unknown" for r in result["trial_assessments"]):
        result.update(status="incomplete", decision="inconclusive", reason_code="insufficient_evidence")
    elif result["positive_trial_count"] in (0, 3):
        decision = "positive" if result["positive_trial_count"] == 3 else "negative"
        result.update(status="complete", decision=decision, reason_code=REASONS[technique][decision])
    else:
        result.update(status="mixed", decision="inconclusive", reason_code="insufficient_evidence")
    return result


def combine(record):
    """Preserve the entire input ledger record and add separate verified/system decisions."""
    document = record["evidence"]
    verified = verify(document)
    raw = record.get("model_output")
    raw_claim = record.get("system_claim")
    # A completed status alone cannot make a fabricated or mismatched record usable.
    usable = (verified["decision"] != "not_evaluable" and record.get("analysis_status") == "completed"
              and isinstance(raw, dict))
    if usable:
        output_schema = json.loads((ROOT / "schemas/qwen-analysis-output.schema.json").read_text(encoding="utf-8"))
        usable = Draft202012Validator(output_schema).is_valid(raw) and raw.get("decision") == raw_claim
        if usable:
            known = {o["observation_id"] for o in document["observations"]}
            refs = set(raw["evidence_refs"])
            for assessment in raw.get("trial_assessments", []):
                refs.update(assessment["evidence_refs"])
            required = {ref for trial in verified["trial_assessments"] for ref in trial["evidence_refs"]}
            usable = (refs.issubset(known) and required.issubset(set(raw["evidence_refs"]))
                      and record.get("audit", {}).get("input_sha256") == digest(document))
    if verified["decision"] == "not_evaluable":
        decision, code = "not_evaluable", verified["reason_code"]
    elif not usable:
        decision, code = "inconclusive", "model_analysis_unavailable"
    elif verified["decision"] == raw_claim and raw_claim in ("positive", "negative"):
        decision, code = raw_claim, verified["reason_code"]
    elif verified["decision"] == "inconclusive":
        decision, code = "inconclusive", "insufficient_evidence"
    elif raw_claim == "inconclusive":
        decision, code = "inconclusive", "model_abstention"
    else:
        decision, code = "inconclusive", "model_verifier_disagreement"
    return {
        "schema_version": "3.0.0", "scope": "development-hybrid-candidate-not-formal",
        "combination_policy": COMBINATION_POLICY,
        "llm_record": copy.deepcopy(record), "llm_record_sha256": digest(record),
        "verification": verified,
        "combined": {"decision": decision, "reason_code": code,
                     "binary_decision_eligible": decision in ("positive", "negative"),
                     "model_usable": bool(usable), "raw_model_claim": raw_claim,
                     "raw_claim_preserved": True, "model_explanation_verified": False},
    }
