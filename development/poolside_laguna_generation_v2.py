"""Versioned Poolside generation profile with bounded, typed retry feedback.

This adapter only prepares prompts and validates candidates. The existing
executor remains responsible for all observations against the local DVWA.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import ValidationError

import qwen_api_generation
import run_qwen_api_experiments as active
from qwen_api_runtime import APIRuntimeFailure


PROMPT_VERSION = "poolside-laguna-sqli-generation-v2-typed-feedback"
RETRY_POLICY_ID = "poolside-family-fallback-and-format-feedback-v2"
MAX_RETRIES_PER_SLOT = 2
MAX_HISTORY_PER_SLOT = 2
MAX_EXCERPT_CHARS = 400

# Each primary family is assigned by candidate slot and is shared by conditions
# A/B. Families are described rather than supplied as ready-made SQL payloads.
PRIMARY_FAMILIES = {
    "single_error": (
        "Append one unmatched single quote to the existing benign numeric input value.",
        "Append one unmatched double quote to the existing benign numeric input value.",
        "Append one unmatched backtick to the existing benign numeric input value.",
        "Append one unmatched closing parenthesis to the existing benign numeric input value.",
        "Append one unmatched opening parenthesis to the existing benign numeric input value.",
        "Append one single quote followed by one unmatched closing parenthesis.",
        "Append one double quote followed by one unmatched closing parenthesis.",
        "Append one single quote followed by one unmatched opening parenthesis.",
        "Append one double quote followed by one unmatched opening parenthesis.",
        "Append one backtick followed by one unmatched closing parenthesis.",
    ),
    "boolean_pair": (
        "Use a numeric AND equality predicate; keep both values structurally identical and make one comparison true and the other false.",
        "Use a numeric OR equality predicate; keep both values structurally identical and make one comparison true and the other false.",
        "Group a numeric equality predicate in parentheses; return a matched true/false pair.",
        "Use a numeric greater-than predicate; make the paired comparisons have opposite truth values.",
        "Use a numeric less-than predicate; make the paired comparisons have opposite truth values.",
        "Use a numeric negated-equality predicate; make the paired comparisons have opposite truth values.",
        "Use a numeric not-equal predicate with the same expression shape in both values.",
        "Use a parenthesized numeric AND equality predicate; make the paired comparisons have opposite truth values.",
        "Use a parenthesized numeric OR equality predicate; make the paired comparisons have opposite truth values.",
        "Use a numeric greater-than-or-equal predicate; make the paired comparisons have opposite truth values.",
    ),
    "single_time": (
        "Use a numeric AND expression containing exactly one literal SLEEP(2).",
        "Use a numeric OR expression containing exactly one literal SLEEP(2).",
        "Use a single-quoted AND expression containing exactly one literal SLEEP(2).",
        "Use a single-quoted OR expression containing exactly one literal SLEEP(2).",
        "Group a numeric AND expression in parentheses and include exactly one literal SLEEP(2).",
        "Group a numeric OR expression in parentheses and include exactly one literal SLEEP(2).",
        "Use a numeric XOR expression containing exactly one literal SLEEP(2).",
        "Use a numeric AND NOT expression containing exactly one literal SLEEP(2).",
        "Use an IF expression with a constant true condition and exactly one literal SLEEP(2) branch.",
        "Use a CASE WHEN expression with a constant true condition and exactly one literal SLEEP(2) result.",
    ),
}

FALLBACK_FAMILIES = {
    "single_error": (
        "Use an unmatched opening parenthesis followed by one single quote at the existing benign numeric input boundary.",
        "Use an unmatched opening parenthesis followed by one double quote at the existing benign numeric input boundary.",
    ),
    "boolean_pair": (
        "Use a numeric less-than-or-equal predicate with matched opposite truth values.",
        "Use a numeric XOR equality predicate with matched opposite truth values.",
    ),
    "single_time": (
        "Use an IF expression with the SQL TRUE keyword as its constant condition and exactly one literal SLEEP(2) branch.",
        "Use a CASE WHEN expression with the SQL TRUE keyword as its constant condition and exactly one literal SLEEP(2) result.",
    ),
}


class DuplicateJSONKey(ValueError):
    """Raised when a reply contains ambiguous repeated JSON object keys."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey
        result[key] = value
    return result


def _response_diagnostic(content: str, schema: dict) -> dict:
    """Return a small typed reason without repairing or interpreting payloads."""
    try:
        document = json.loads(content, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        return {"code": "invalid_json", "line": exc.lineno, "column": exc.colno}
    except DuplicateJSONKey:
        return {"code": "duplicate_json_key"}
    except (TypeError, ValueError):
        return {"code": "invalid_json"}

    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator(schema).validate(document)
    except ValidationError as exc:
        return {"code": "schema_mismatch", "path": "/" + "/".join(map(str, exc.absolute_path))}
    return {"code": "candidate_rejected"}


def _request_family(probe_kind: str, slot_id: int, retry_index: int) -> tuple[str, int, str]:
    if probe_kind not in PRIMARY_FAMILIES or probe_kind not in FALLBACK_FAMILIES:
        raise ValueError("Unsupported Poolside generation probe kind.")
    primary = PRIMARY_FAMILIES[probe_kind]
    if not 1 <= slot_id <= len(primary):
        raise ValueError("Candidate slot is outside the frozen v2 family schedule.")
    if type(retry_index) is not int or not 0 <= retry_index <= MAX_RETRIES_PER_SLOT:
        raise ValueError("retry_index must be 0, 1, or 2.")
    if retry_index == 0:
        return primary[slot_id - 1], slot_id, "primary"
    fallback_index = retry_index - 1
    return FALLBACK_FAMILIES[probe_kind][fallback_index], slot_id, f"fallback-{fallback_index + 1}"


def _remember_duplicate(parsed: dict, response: dict, rejected: list) -> None:
    """Cache only parser-confirmed duplicates, which are safe for its key function."""
    if parsed["status"] != "no_valid_distinct_candidate":
        return
    try:
        response_candidates = json.loads(response["content"], object_pairs_hook=_unique_object).get("candidates", [])
    except (KeyError, TypeError, ValueError, AttributeError):
        return
    duplicate_indices = {
        item.get("index") for item in parsed.get("audit", {}).get("suggestions", [])
        if item.get("status") == "duplicate_structure"
    }
    for index, candidate in enumerate(response_candidates, 1):
        if index in duplicate_indices and candidate not in rejected:
            rejected.append(candidate)
            if len(rejected) >= MAX_HISTORY_PER_SLOT:
                break


def make_generation_callback(api, attempt_directory: Path, scenario: dict,
                             retrieval: dict | None, baseline: dict, config: dict):
    """Build the Poolside v2 callback with bounded feedback isolated per slot."""
    projected_retrieval = active.safe_retrieval(retrieval, config)
    history_by_slot: dict[int, list[dict]] = {}
    duplicate_exclusions_by_slot: dict[int, list] = {}

    def generate(previous, attempted, retry_index, rejection_code):
        if type(retry_index) is not int or not 0 <= retry_index <= MAX_RETRIES_PER_SLOT:
            raise ValueError("retry_index must be 0, 1, or 2.")
        slot_id = len(attempted) + 1
        history = history_by_slot.setdefault(slot_id, [])
        duplicate_exclusions = duplicate_exclusions_by_slot.setdefault(slot_id, [])
        family, family_index, phase = _request_family(scenario["probe_kind"], slot_id, retry_index)

        prepared, messages = active.generation_messages(
            scenario, attempted, projected_retrieval, baseline,
            active.feedback_projection(previous), retry_index, rejection_code)
        prepared.update(prompt_version=PROMPT_VERSION, retry_policy_id=RETRY_POLICY_ID,
                        family_index=family_index, family=family,
                        family_phase=phase, generation_attempt=retry_index)
        task = json.loads(messages[1]["content"])
        task["variation_family"] = {"index": family_index, "description": family, "phase": phase}
        task["generation_attempt"] = retry_index
        task["validation_feedback"] = list(history)
        task["same_slot_rejected_suggestions"] = list(duplicate_exclusions)
        messages[1]["content"] = json.dumps(task, ensure_ascii=False, separators=(",", ":"))

        api_result, checkpoint = api.chat("generation", messages, attempt_directory)
        parsed = qwen_api_generation.parse(
            prepared, [*attempted, *duplicate_exclusions], scenario["probe_kind"], api_result)
        candidate = parsed["candidate"]
        final_status = parsed["status"]
        if candidate is not None:
            try:
                active.validate_candidate_policy(candidate, scenario["probe_kind"], scenario["scenario_id"])
            except (KeyError, ValueError):
                final_status = "invalid_candidate_policy"

        audit = {
            **parsed["audit"],
            "status": final_status,
            "prompt_version": PROMPT_VERSION,
            "retry_policy_id": RETRY_POLICY_ID,
            "checkpoint": checkpoint,
            "variation_family": family,
            "family_phase": phase,
            "generation_attempt": retry_index,
            "same_slot_feedback_count": len(history),
            "same_slot_duplicate_exclusion_count": len(duplicate_exclusions),
        }

        if final_status == "generated" and candidate is not None:
            history_by_slot.pop(slot_id, None)
            duplicate_exclusions_by_slot.pop(slot_id, None)
            value = candidate["payload"] if scenario["scenario_id"] == "S1" else candidate
            return value, audit

        if final_status == "model_service_error":
            raise APIRuntimeFailure("api_generation_response_unusable", {
                **checkpoint, "parse_status": final_status})

        if parsed["status"] == "no_valid_distinct_candidate":
            _remember_duplicate(parsed, api_result, duplicate_exclusions)

        content = api_result.get("content") if isinstance(api_result, dict) else ""
        content = content if isinstance(content, str) else ""
        diagnostic = (_response_diagnostic(content, prepared["schema"])
                      if parsed["status"] == "invalid_candidate_format"
                      else {"code": final_status})
        entry = {
            "attempt": retry_index,
            "status": final_status,
            "diagnostic": diagnostic,
            "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "response_excerpt_untrusted": content[:MAX_EXCERPT_CHARS],
        }
        history.append(entry)
        del history[:-MAX_HISTORY_PER_SLOT]
        audit.update(same_slot_feedback_count_after_request=len(history),
                     same_slot_duplicate_exclusion_count_after_request=len(duplicate_exclusions),
                     validation_diagnostic=diagnostic)
        return None, {**audit, "rejection_code": final_status}

    return generate
