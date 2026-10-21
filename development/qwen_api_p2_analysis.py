"""Versioned API adapter for P2 SQLi evidence analysis.

Uses the explicit measured-evidence contract from analyze_response_v2, with
no retrieval context and no claim correction. This module prepares requests
only; it does not call the API.
"""

from __future__ import annotations

import copy
import hashlib
import json

from jsonschema import Draft202012Validator

import analysis_v5_pilot_cases as cases
import analyze_response_v2 as contract
from qwen_api_analysis import parse as parse_response
from qwen_api_client import ChatSettings, encoded_payload, request_payload


PROMPT_VERSION = "qwen38-api-p2-explicit-evidence-v1"
MAX_OUTPUT_TOKENS = 2048
TIMEOUT_SECONDS = 90


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def default_settings() -> ChatSettings:
    """Freeze the P2 API settings selected from the completed diagnosis."""
    return ChatSettings(max_tokens=MAX_OUTPUT_TOKENS, timeout_seconds=TIMEOUT_SECONDS)


def prepare(document: dict, settings: ChatSettings | None = None) -> dict:
    """Render one eligible no-RAG input with the explicit v2 evidence contract."""
    if not cases.eligible(document):
        raise ValueError("Only runtime-valid cases with a valid baseline may reach the API")

    prepared = contract.prepared_request(document)
    if prepared["provenance"]["prompt_version"] != contract.PROMPT_VERSION:
        raise ValueError("The pinned analysis contract version changed")

    schema = copy.deepcopy(prepared["request"]["format"])
    Draft202012Validator.check_schema(schema)
    messages = copy.deepcopy(prepared["request"]["messages"])
    if len(messages) != 2 or messages[0]["role"] != "system" or messages[1]["role"] != "user":
        raise ValueError("Unexpected base analysis message structure")

    paired_view = contract.v1.paired_view(document)
    if json.loads(messages[1]["content"]) != paired_view:
        raise ValueError("Measured evidence projection changed")
    if "reference_context" in messages[1]["content"]:
        raise ValueError("P2 is a no-RAG analysis condition")

    # The gateway's JSON Schema enforcement is not assumed. Include the schema
    # in the prompt and validate the returned object locally as well.
    messages[0]["content"] += (
        "\nReturn one JSON object only, without markdown or extra text. "
        "Its structure must match this JSON Schema: "
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )
    settings = settings or default_settings()
    payload = request_payload(messages, settings)
    return {
        "prompt_version": PROMPT_VERSION,
        "base_contract_version": contract.PROMPT_VERSION,
        "document_sha256": canonical_hash(document),
        "system_prompt_sha256": canonical_hash(messages[0]),
        "schema_sha256": canonical_hash(schema),
        "schema": schema,
        "payload": payload,
        "request_sha256": hashlib.sha256(encoded_payload(payload)).hexdigest(),
        "claim_override": False,
        "rag_mode": "off",
    }


def parse(document: dict, prepared: dict, api_result: dict) -> dict:
    """Validate structure and references while preserving the raw model verdict."""
    if prepared["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Prepared request uses a different P2 prompt version")
    if prepared["document_sha256"] != canonical_hash(document):
        raise ValueError("Prepared request is bound to a different evidence document")
    return parse_response(document, prepared["schema"], api_result)
