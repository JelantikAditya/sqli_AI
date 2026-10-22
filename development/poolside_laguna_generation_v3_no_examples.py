"""Poolside Laguna generation profile that removes retrieved payload examples.

The pinned structured RAG chunks remain unchanged. This profile projects them
to explanatory fields before the chunks enter generation prompts.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import poolside_laguna_generation_v2 as base_profile


PROMPT_VERSION = "poolside-laguna-sqli-generation-v3-rag-no-payload-examples"
RETRY_POLICY_ID = base_profile.RETRY_POLICY_ID
RETRIEVAL_CONTEXT_POLICY_ID = "structured-chunks-remove-payload-examples-v1"


def strip_payload_examples(retrieval: dict | None) -> tuple[dict | None, int]:
    """Return a copy of retrieved chunks with only the payload_examples field removed."""
    if retrieval is None:
        return None, 0
    if not isinstance(retrieval, dict) or not isinstance(retrieval.get("chunks"), list):
        raise ValueError("Retrieval must contain a chunks list.")

    projected = copy.deepcopy(retrieval)
    removed = 0
    for item in projected["chunks"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ValueError("Each retrieved chunk must contain text.")
        try:
            document = json.loads(item["text"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Retrieved structured knowledge is not valid JSON.") from exc
        if not isinstance(document, dict):
            raise ValueError("Retrieved structured knowledge must be a JSON object.")
        if "payload_examples" in document:
            document.pop("payload_examples")
            removed += 1
        item["text"] = json.dumps(document, ensure_ascii=False, separators=(",", ":"))

    return projected, removed


def make_generation_callback(api, attempt_directory: Path, scenario: dict,
                             retrieval: dict | None, baseline: dict, config: dict):
    projected_retrieval, removed_count = strip_payload_examples(retrieval)
    generate_with_base_profile = base_profile.make_generation_callback(
        api, attempt_directory, scenario, projected_retrieval, baseline, config)

    def generate(previous, attempted, retry_index, rejection_code):
        candidate, audit = generate_with_base_profile(
            previous, attempted, retry_index, rejection_code)
        audit = {
            **audit,
            "prompt_version": PROMPT_VERSION,
            "retrieval_context_policy_id": RETRIEVAL_CONTEXT_POLICY_ID,
            "payload_examples_removed_from_retrieved_chunks": removed_count,
        }
        return candidate, audit

    return generate
