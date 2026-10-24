"""Laguna generation profile with explicit normalized-structure feedback.

The v4 family scheduler and existing parser remain authoritative. This profile
adds compact structural signatures to make accepted and rejected shapes clear
to the model on each request, while adapting the requested pattern to the
scenario's injection boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import poolside_laguna_generation_v4 as v4
from qwen_api_runtime import APIRuntimeFailure


PROMPT_VERSION = "poolside-laguna-sqli-generation-v5-explicit-structure-feedback"
RETRY_POLICY_ID = "poolside-unit-wide-unseen-family-structure-feedback-v5"
RETRIEVAL_CONTEXT_POLICY_ID = v4.RETRIEVAL_CONTEXT_POLICY_ID
MAX_RETRIES_PER_SLOT = v4.MAX_RETRIES_PER_SLOT
MAX_FAMILIES_PER_PROBE = v4.MAX_FAMILIES_PER_PROBE
MAX_HISTORY_PER_SLOT = v4.MAX_HISTORY_PER_SLOT
MAX_EXCERPT_CHARS = v4.MAX_EXCERPT_CHARS
FAMILIES = v4.FAMILIES


def structure_signature(candidate: dict | str, probe_kind: str) -> str:
    """Render the parser's structure normalization as readable prompt feedback."""
    if isinstance(candidate, str):
        candidate = {"payload": candidate}
    values = v4.parser.candidate_values(candidate, probe_kind)
    normalized = [re.sub(r"\s+", " ", re.sub(
        r"(?<![A-Za-z_])\d+(?:\.\d+)?", "<n>", value.lower())).strip()
        for value in values]
    if probe_kind == "boolean_pair":
        return f"true: {normalized[0]} || false: {normalized[1]}"
    return normalized[0]


def _family_pattern(probe_kind: str, family) -> str:
    """Expose only an abstract, number-normalized family pattern to the model."""
    candidate = v4._candidate(probe_kind, family.reference_values)
    return structure_signature(candidate, probe_kind)


def _avoid_signatures(attempted: list, rejected: list, probe_kind: str) -> list[str]:
    signatures = []
    for candidate in [*attempted, *rejected]:
        try:
            signature = structure_signature(candidate, probe_kind)
        except (KeyError, TypeError, ValueError):
            continue
        if signature not in signatures:
            signatures.append(signature)
    return signatures


def strip_payload_examples(retrieval: dict | None) -> tuple[dict | None, int]:
    """Keep the Q2 retrieval projection and its read-only source behavior."""
    return v4.strip_payload_examples(retrieval)


def make_generation_callback(api, attempt_directory: Path, scenario: dict,
                             retrieval: dict | None, baseline: dict, config: dict):
    projected_retrieval, removed_count = strip_payload_examples(retrieval)
    projected_context = v4.active.safe_retrieval(projected_retrieval, config)
    probe_kind = scenario["probe_kind"]
    requested_family_ids: set[str] = set()
    duplicate_exclusions_by_slot: dict[int, list] = {}
    history_by_slot: dict[int, list[dict]] = {}

    def generate(previous, attempted, retry_index, rejection_code):
        if type(retry_index) is not int or not 0 <= retry_index <= MAX_RETRIES_PER_SLOT:
            raise ValueError("retry_index must be 0, 1, or 2.")
        slot_id = len(attempted) + 1
        if not 1 <= slot_id <= 10:
            raise ValueError("Candidate slot is outside the frozen v5 family schedule.")
        duplicate_exclusions = duplicate_exclusions_by_slot.setdefault(slot_id, [])
        family = v4._family_for_request(
            probe_kind, slot_id, [*attempted, *duplicate_exclusions], requested_family_ids)
        requested_family_ids.add(family.family_id)
        history = history_by_slot.setdefault(slot_id, [])

        prepared, messages = v4.active.generation_messages(
            scenario, attempted, projected_context, baseline,
            v4.active.feedback_projection(previous), retry_index, rejection_code)
        family_index = len(requested_family_ids)
        family_pattern = _family_pattern(probe_kind, family)
        prepared.update(
            prompt_version=PROMPT_VERSION,
            retry_policy_id=RETRY_POLICY_ID,
            family_id=family.family_id,
            family_structural_key=family.structural_key,
            family_index=family_index,
            family=family.description,
            generation_attempt=retry_index,
        )
        task = json.loads(messages[1]["content"])
        phase = ("primary" if retry_index == 0
                 and family.family_id == FAMILIES[probe_kind][slot_id - 1].family_id
                 else "unseen-structural-fallback")
        task["variation_family"] = {
            "index": family_index,
            "description": family.description,
            "phase": phase,
        }
        task["variation_contract"] = {
            "requested_family_pattern": family_pattern,
            "avoid_structural_signatures": _avoid_signatures(
                attempted, duplicate_exclusions, probe_kind),
            "novelty_rule": (
                "The existing parser normalizes case, whitespace, and numeric literals. "
                "A candidate that differs only by those changes repeats the same SQL structure. "
                "Use the requested family pattern and do not reuse any listed signature."
            ),
            "boundary_rule": (
                "Adapt quoting or a trailing comment only as needed for this scenario's input boundary. "
                "Keep the requested operator, predicate, grouping, and function structure."
            ),
            "output_rule": (
                "Return exactly one JSON object matching output_schema, containing one candidate. "
                "No prose or markdown."
            ),
        }
        task["generation_attempt"] = retry_index
        task["validation_feedback"] = list(history)
        task["same_slot_rejected_suggestions"] = list(duplicate_exclusions)
        messages[1]["content"] = json.dumps(task, ensure_ascii=False, separators=(",", ":"))

        api_result, checkpoint = api.chat("generation", messages, attempt_directory)
        parsed = v4.parser.parse(
            prepared, [*attempted, *duplicate_exclusions], probe_kind, api_result)
        candidate = parsed["candidate"]
        final_status = parsed["status"]
        if candidate is not None:
            try:
                v4.active.validate_candidate_policy(candidate, probe_kind, scenario["scenario_id"])
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
            "family_pattern": family_pattern,
            "family_phase": phase,
            "generation_attempt": retry_index,
            "unit_family_count": len(requested_family_ids),
            "same_slot_feedback_count": len(history),
            "unit_duplicate_exclusion_count": len(duplicate_exclusions),
            "retrieval_context_policy_id": RETRIEVAL_CONTEXT_POLICY_ID,
            "payload_examples_removed_from_retrieved_chunks": removed_count,
        }
        if final_status == "generated" and candidate is not None:
            audit["accepted_structure_signature"] = structure_signature(candidate, probe_kind)
            value = candidate["payload"] if scenario["scenario_id"] == "S1" else candidate
            duplicate_exclusions_by_slot.pop(slot_id, None)
            history_by_slot.pop(slot_id, None)
            return value, audit
        if final_status == "model_service_error":
            raise APIRuntimeFailure("api_generation_response_unusable", {
                **checkpoint, "parse_status": final_status})

        if parsed["status"] == "no_valid_distinct_candidate":
            v4._remember_duplicate(parsed, api_result, duplicate_exclusions)
        elif final_status == "invalid_candidate_policy" and candidate is not None \
                and candidate not in duplicate_exclusions:
            duplicate_exclusions.append(candidate)
        content = api_result.get("content") if isinstance(api_result, dict) else ""
        content = content if isinstance(content, str) else ""
        diagnostic = (v4._response_diagnostic(content, prepared["schema"])
                      if parsed["status"] == "invalid_candidate_format"
                      else {"code": final_status})
        history.append({
            "attempt": retry_index,
            "status": final_status,
            "diagnostic": diagnostic,
            "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "response_excerpt_untrusted": content[:MAX_EXCERPT_CHARS],
        })
        del history[:-MAX_HISTORY_PER_SLOT]
        audit.update(
            same_slot_feedback_count_after_request=len(history),
            unit_duplicate_exclusion_count_after_request=len(duplicate_exclusions),
            validation_diagnostic=diagnostic,
        )
        return None, {**audit, "rejection_code": final_status}

    return generate
