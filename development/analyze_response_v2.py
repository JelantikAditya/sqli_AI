"""Development-only explicit model tally and verdict contract; no claim override."""

from __future__ import annotations

import copy
import hashlib
import json

from jsonschema import Draft202012Validator, ValidationError

import analyze_response_v1 as v1

frozen = v1.frozen
MODEL = v1.MODEL
PROMPT_VERSION = "sqli-response-analysis-dev-v2-explicit-tally-contract"
PREPROCESSING_VERSION = v1.PREPROCESSING_VERSION
REASON_CODES = {
    "error-based": ("new_database_diagnostic", "no_new_database_diagnostic"),
    "boolean-based blind": ("boolean_difference", "no_boolean_difference"),
    "time-based blind": ("matched_delay", "no_matched_delay"),
}


def build_messages(document):
    messages = v1.build_messages(document)
    # Preserve v1's technique rules and measured input; change only the output contract.
    prefix, separator, _ = messages[0]["content"].partition("First return trial_assessments")
    if not separator:
        raise ValueError("The pinned v1 instruction prefix changed.")
    positive_code, negative_code = REASON_CODES[document["technique"]]
    messages[0]["content"] = prefix + (
        "Return JSON in this order: trial_assessments, confirmation_summary, decision, "
        "reason_code, reason, evidence_refs, feedback_action. "
        "First assess each displayed comparison exactly once, citing BOTH observation IDs. "
        "Do not invent a missing trial. Then fill confirmation_summary from your own trial_assessments: "
        "observed_trials lists the actual trial numbers in increasing order; positive_trial_count counts "
        "outcome=positive; negative_trial_count counts outcome=negative. The counts must sum to the "
        "number of assessments. This summary is your calculation, not an extra observation. "
        "Select the decision using this table, checking trial completeness FIRST:\n"
        "observed_trials | positive_trial_count | decision | reason_code\n"
        "anything other than exactly [1,2,3] | any | inconclusive | insufficient_evidence\n"
        f"exactly [1,2,3] | 3 | positive | {positive_code}\n"
        f"exactly [1,2,3] | 0 | negative | {negative_code}\n"
        "exactly [1,2,3] | 1 or 2 | inconclusive | insufficient_evidence\n"
        "Mixed evidence is not a majority vote. Two positive trials cannot establish positive. "
        "One positive trial prevents negative. An absent trial requires inconclusive even if every "
        "available trial agrees. Complete negative measurements are not missing evidence. "
        "Copy the literal reason_code from the selected row; insufficient_evidence belongs ONLY to "
        "inconclusive. The short factual reason must agree with your counts and selected decision. "
        "Top-level evidence_refs must cite both sides of every available comparison. "
        "feedback_action is none for positive, revise_candidate otherwise. "
        "Do not infer the target security level or calculate experiment metrics."
    )
    return messages


def output_schema(document):
    model_schema = v1.output_schema(document)
    summary = {
        "type": "object", "additionalProperties": False,
        "required": ["observed_trials", "positive_trial_count", "negative_trial_count"],
        "properties": {
            "observed_trials": {"type": "array", "minItems": 1, "maxItems": 3,
                                "items": {"type": "integer", "minimum": 1}},
            "positive_trial_count": {"type": "integer", "minimum": 0, "maximum": 3},
            "negative_trial_count": {"type": "integer", "minimum": 0, "maximum": 3},
        },
    }
    properties = model_schema["properties"]
    order = ("trial_assessments", "confirmation_summary", "decision", "reason_code", "reason",
             "evidence_refs", "feedback_action")
    properties["confirmation_summary"] = summary
    model_schema["properties"] = {key: properties[key] for key in order}
    model_schema["required"] = list(order)
    # No conditional schema forces a verdict or code: inconsistencies remain measurable.
    return model_schema


def prepared_request(document, *, seed=42):
    prepared = v1.prepared_request(document, seed=seed)
    prepared["request"]["messages"] = build_messages(document)
    prepared["request"]["format"] = output_schema(document)
    prepared["provenance"].update({
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": frozen.sha256(prepared["request"]["messages"]),
        "schema_sha256": frozen.sha256(prepared["request"]["format"]),
        "contract_version": "explicit-model-tally-and-literal-reason-codes-v2",
        "model_tally_source": "model-output-only-not-executor",
        "claim_override": False,
    })
    return prepared


def audit_model_summary(output):
    """Audit the model's own tally without changing its tally, verdict or reason code."""
    assessments = output["trial_assessments"]
    summary = output["confirmation_summary"]
    trials = [item["trial"] for item in assessments]
    positive = sum(item["outcome"] == "positive" for item in assessments)
    issues = []
    if (summary["observed_trials"] != sorted(trials)
            or len(set(trials)) != len(trials)
            or summary["positive_trial_count"] != positive
            or summary["negative_trial_count"] != len(assessments) - positive):
        issues.append("model_confirmation_summary_mismatch")
    # This expected value is audit-only and is never assigned to system_claim.
    expected = "inconclusive"
    if summary["observed_trials"] == [1, 2, 3]:
        expected = {0: "negative", 3: "positive"}.get(summary["positive_trial_count"], "inconclusive")
    if output["decision"] != expected:
        issues.append("model_summary_decision_mismatch")
    return issues


def parse_response(document, context, prepared, response):
    provenance = copy.deepcopy(prepared["provenance"])
    output = None
    if response is not None:
        provenance["model"] = response.get("model", MODEL)
        provenance["runtime_metrics"] = {key: response.get(key) for key in
                                          ("done", "done_reason", "prompt_eval_count", "eval_count", "total_duration")}
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            provenance["raw_model_content"] = content
            provenance["raw_model_content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
            try:
                parsed = frozen.canonicalize_duplicate_evidence_refs(json.loads(content), provenance)
                Draft202012Validator(prepared["request"]["format"]).validate(parsed)
                provenance["model_confirmation_summary"] = copy.deepcopy(parsed["confirmation_summary"])
                provenance["development_contract_warnings"] = audit_model_summary(parsed)
                # The frozen ledger stores its original six fields. The extra model
                # tally remains in provenance and the complete raw response above.
                output = {key: value for key, value in parsed.items() if key != "confirmation_summary"}
            except (ValueError, TypeError, ValidationError):
                provenance["analysis_error"] = "invalid-model-json-or-schema"
        else:
            provenance["analysis_error"] = "missing-model-content"
    record = frozen.normalize_analysis(document, output, context, provenance)
    return record


def analyze_with_qwen(document, context, *, seed=42, prepared=None):
    def prepare(state):
        frozen.validate_input(document)
        frozen.validate_case(document, context)
        actual = prepared_request(document, seed=seed)
        if prepared is not None and actual != prepared:
            raise ValueError("Prepared request changed after freeze.")
        return {**state, "prepared": actual,
                "should_call": document["runtime_status"] == "valid" and document["baseline_valid"]}

    def call_model(state):
        state["response"] = None
        if state["should_call"]:
            try:
                state["response"] = v1.post_ollama("/api/chat", state["prepared"]["request"], timeout=180)
            except RuntimeError:
                state["prepared"]["provenance"]["analysis_error"] = "model-service-unavailable"
        return state

    def parse(state):
        return parse_response(document, context, state["prepared"], state["response"])

    return v1.invoke_serial((prepare, call_model, parse), {"document": document, "context": context})
