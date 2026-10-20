"""Pilot r2: explicit error categories and paired scoring; preserve the original freeze."""

from __future__ import annotations

import argparse
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import time

from jsonschema import Draft202012Validator, ValidationError
from tokenizers import Tokenizer

import analysis_v5_pilot_cases as dataset
import analysis_v5_pilot as prior
import preflight_analysis_v5_context as context
import verify_analysis_v5_context as previous_verifier

rag = dataset.rag
ROOT = rag.ROOT
OUT = ROOT / "results/processed/analysis-v5-pilot-20261020-r2"
RAW = ROOT / "results/raw/development/analysis-v5-pilot-20261020-r2"
REVIEW = ROOT / "outputs/analysis-v5-pilot-review-r2"
GUIDE = ROOT / "docs/paket-pilot-analisis-v5-r2-2026-10-20.md"
IDENTICAL_ARTIFACTS = (
    "inputs.lock.json", "labels.ai.lock.json", "schedule.lock.json",
    "prepared-requests.lock.json", "request-audit.lock.json", "schedule-audit.lock.json",
)
PROFILES = dataset.PROFILES
CLASSES = ("positive", "negative", "inconclusive")
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 768}
TIMEOUT = 240
read, digest, write_new = context.read, context.digest, context.write_new


def utc():
    return datetime.now(timezone.utc).isoformat()


def prepare_requests(cases):
    projection = rag.project_corpus()
    receipts = read(context.previous.RAW / "retrieval.json")
    chunks = {c["chunk_id"]: c for c in projection["chunks"]}
    result = []
    for case in cases:
        doc = case["input"]
        receipt = receipts[hashlib.sha256(rag.query_for(doc).encode()).hexdigest()]
        a = rag.prepared_request(doc, "A", projection=projection)["request"]
        b2 = rag.prepared_request(doc, "B", receipt, projection=projection)["request"]
        b3 = copy.deepcopy(b2)
        view = json.loads(b3["messages"][1]["content"])
        view["reference_context"] = [{"chunk_id": r["chunk_id"], "reference_text": chunks[r["chunk_id"]]["text"]}
                                      for r in receipt["candidate_pool"][:3]]
        b3["messages"][1]["content"] = json.dumps(view, ensure_ascii=False, allow_nan=False)
        for profile, payload in zip(PROFILES, (a, b2, b3)):
            result.append({"case_id": case["case_id"], "profile": profile, "request": payload,
                           "request_sha256": rag.sha(payload), "rank_receipt_sha256": rag.sha(receipt)})
    return result


def audit_requests(cases, requests, tokenizer):
    """Preflight ALL actual requests before any call; fail the whole run on any excess."""
    indexed = {(r["case_id"], r["profile"]): r for r in requests}
    if len(indexed) != len(requests) or set(indexed) != {(c["case_id"], p) for c in cases for p in PROFILES}:
        raise ValueError("Incomplete or duplicate request matrix.")
    audit = []
    for case in cases:
        doc = case["input"]
        common = None
        for profile, k in zip(PROFILES, (0, 2, 3)):
            row = indexed[(case["case_id"], profile)]
            payload = row["request"]
            if row["request_sha256"] != rag.sha(payload):
                raise ValueError("Request hash mismatch.")
            if (set(payload) != {"model", "messages", "format", "stream", "options"}
                    or payload["model"] != context.MODEL or payload["options"] != OPTIONS or payload["stream"] is not False):
                raise ValueError("Request configuration changed, including a possible early stop override.")
            view = json.loads(payload["messages"][1]["content"])
            if set(view) != {"measured_evidence", "reference_context"} or len(view["reference_context"]) != k:
                raise ValueError("Unexpected user projection or reference count.")
            if view["measured_evidence"] != rag.base.v1.paired_view(doc):
                raise ValueError("Measured evidence changed or was trimmed.")
            normalized = copy.deepcopy(payload)
            del view["reference_context"]
            normalized["messages"][1]["content"] = json.dumps(view, ensure_ascii=False, allow_nan=False)
            if common is not None and normalized != common:
                raise ValueError("A/B2/B3 differ outside reference_context.")
            common = normalized
            reference_view = json.loads(payload["messages"][1]["content"])["reference_context"]
            if (len(json.dumps(reference_view, ensure_ascii=False).encode()) > rag.MAX_REFERENCE_BYTES
                    or sum(len(m["content"].encode()) for m in payload["messages"]) > rag.MAX_MESSAGE_BYTES):
                raise ValueError("Byte guard exceeded; do not trim evidence or references.")
            n = len(tokenizer.encode(context.serialized_chat(payload), add_special_tokens=False).ids)
            margin = OPTIONS["num_ctx"] - OPTIONS["num_predict"] - n
            if margin < 0:
                raise ValueError("Context budget exceeded before sending any requests; no truncation permitted.")
            audit.append({"case_id": case["case_id"], "profile": profile,
                "runtime_eligible": dataset.eligible(doc), "request_sha256": row["request_sha256"],
                "prompt_tokens": n, "reserved_output_tokens": OPTIONS["num_predict"], "reserved_headroom": margin,
                "common_request_sha256_without_reference_context": rag.sha(normalized),
                "system_prompt_sha256": rag.sha(payload["messages"][0]), "schema_sha256": rag.sha(payload["format"]),
                "measured_evidence_sha256": rag.sha(view["measured_evidence"]),
                "reference_context_sha256": rag.sha(reference_view), "evidence_or_chunks_trimmed": False})
    return audit


def audit_schedule(cases, schedule):
    case_map = {c["case_id"]: c for c in cases}
    if schedule != dataset.schedule(cases):
        raise ValueError("Schedule differs from the prespecified seed/order algorithm.")
    if len(schedule) != len(cases) * 3:
        raise ValueError("Schedule incomplete.")
    result = {}
    for name, eligible in (("all", None), ("eligible", True), ("invalid", False)):
        selected = [r for r in schedule if eligible is None or dataset.eligible(case_map[r["case_id"]]["input"]) == eligible]
        counts = Counter((r["profile"], r["position_within_case"]) for r in selected)
        if len(set(counts.values())) != 1 or len(counts) != 9:
            raise ValueError("Profile positions are unbalanced.")
        result[name] = {p: {str(i): counts[(p, i)] for i in (1, 2, 3)} for p in PROFILES}
    return result


def protocol():
    result = prior.protocol()
    result.update({
        "pilot_id": OUT.name, "protocol_revision": 2, "supersedes_for_future_execution": prior.OUT.name,
        "review_basis": "forwarded review; authorship/independence and researcher adoption not established",
        "content_errors": "missing content, invalid JSON/schema, unknown observation ID, unfinished generation, runtime length stop, or conservative output-budget rejection => analysis_error and continue",
        "output_completion": {
            "generation-not-finished": "done is not true",
            "generation-length-limit": "done=true and done_reason=length; runtime reports a length stop",
            "unexpected-completion-reason": "done=true with a reason other than stop or length",
            "invalid-generation-token-count": "non-integer, boolean, missing or nonpositive eval_count",
            "output-budget-rejection": "done=true, done_reason=stop, integer eval_count >= 768; conservative budget policy, not proof of incomplete JSON",
            "accepted_runtime_metadata": "done=true, done_reason=stop, 0 < eval_count < 768; content must also pass JSON/schema and known-ID checks",
            "precedence": "prompt-count mismatch, unfinished, runtime length stop, other completion reason, invalid token count, budget rejection, content/schema, unknown ID",
        },
        "structural_errors": "missing required field, invalid JSON/schema, or any nonexistent observation ID => analysis_error; verdict/trials get no credit and the attempted-case denominator remains",
        "semantic_warnings": "existing IDs with wrong/missing support, missing/duplicate expected trial entries within a schema-valid array, wrong trial outcome, tally/reason/feedback contradiction => warning only; keep raw verdict",
        "reason_code_accuracy": "code equals the code for the reference decision and technique; denominator all attempted eligible cases, including errors",
        "reason_code_consistency": "code agrees with the model's own raw decision and technique; denominator all attempted eligible cases, including errors; this is not reference accuracy",
        "paired_transitions": "A/B3 wrong-to-correct, correct-to-wrong, both-correct and both-wrong, with case IDs; analysis errors count as wrong, unmatched starts as interrupted errors; report missing and unfinished pairs separately",
        "coverage_limits": [
            "runtime-invalid dataset cases have empty observations; full-positive runtime-invalid input is not represented in the 42 cases",
            "baseline-invalid dataset flags agree with baseline diagnostics; contradictory upstream flags are not represented",
            "input gate validates schema and trusts runtime_status/baseline_valid supplied upstream; it does not independently establish flag/diagnostic consistency",
            "upstream executor is responsible for deriving truthful runtime/baseline validity from its checks; this pilot does not verify that derivation end to end",
            "four positive boolean cases mainly vary accepted HTTP 200/404 patterns; mechanism diversity is limited",
            "pilot-032 combines control diagnostics and negative timing delta; use per-trial assessments for diagnosis",
        ],
    })
    result["companions"] = [
        item.replace("reason code accuracy,", "reason code reference accuracy and internal consistency,")
        for item in result["companions"]
    ] + ["paired A/B3 correctness transitions with case IDs"]
    return result


def parse_output(document, request, response, expected_prompt):
    base = {"status": "analysis_error", "decision": None, "error": None, "warnings": [],
            "trial_assessments": [], "model_output": None}
    if not isinstance(response, dict):
        return {**base, "error": "malformed-runtime-response"}
    if response.get("prompt_eval_count") != expected_prompt:
        return {**base, "error": "prompt-count-mismatch", "halt": True}
    if response.get("done") is not True:
        return {**base, "error": "generation-not-finished"}
    if response.get("done_reason") == "length":
        return {**base, "error": "generation-length-limit"}
    if response.get("done_reason") != "stop":
        return {**base, "error": "unexpected-completion-reason"}
    if type(response.get("eval_count")) is not int or response["eval_count"] <= 0:
        return {**base, "error": "invalid-generation-token-count"}
    # Kebijakan konservatif: JSON lengkap pada batas pun ditolak karena anggaran,
    # tanpa menyimpulkan bahwa isi JSON pasti terpotong.
    if response["eval_count"] >= OPTIONS["num_predict"]:
        return {**base, "error": "output-budget-rejection"}
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return {**base, "error": "missing-model-content"}
    try:
        output = json.loads(message["content"])
        Draft202012Validator(request["format"]).validate(output)
    except (ValueError, TypeError, ValidationError):
        return {**base, "error": "invalid-json-or-schema"}
    known = {o["observation_id"] for o in document["observations"]}
    refs = output["evidence_refs"] + [ref for t in output["trial_assessments"] for ref in t["evidence_refs"]]
    if not set(refs).issubset(known):
        return {**base, "error": "unknown-observation-reference", "model_output": output}
    warnings = rag.base.audit_model_summary(output)
    expected = dataset.expected_trials(document)
    actual = output["trial_assessments"]
    if sorted(t["trial"] for t in actual) != [t["trial"] for t in expected]:
        warnings.append("trial-set-mismatch")
    for trial in expected:
        assessments = [r for r in actual if r["trial"] == trial["trial"]]
        if len(assessments) != 1 or not set(trial["evidence_refs"]).issubset(assessments[0]["evidence_refs"]):
            warnings.append("missing-or-incorrect-trial-citations")
        if len(assessments) == 1:
            if set(assessments[0]["evidence_refs"]) - set(trial["evidence_refs"]):
                warnings.append("unrelated-trial-citations")
            if assessments[0]["outcome"] != trial["outcome"]:
                warnings.append("trial-outcome-evidence-mismatch")
    expected_refs = {ref for t in expected for ref in t["evidence_refs"]}
    if not expected_refs.issubset(output["evidence_refs"]):
        warnings.append("incomplete-top-level-citations")
    if set(output["evidence_refs"]) - expected_refs:
        warnings.append("unrelated-top-level-citations")
    pos, neg = rag.base.REASON_CODES[document["technique"]]
    if output["reason_code"] != {"positive": pos, "negative": neg, "inconclusive": "insufficient_evidence"}[output["decision"]]:
        warnings.append("reason-code-decision-mismatch")
    if output["feedback_action"] != ("none" if output["decision"] == "positive" else "revise_candidate"):
        warnings.append("feedback-decision-mismatch")
    return {**base, "status": "ok", "decision": output["decision"], "trial_assessments": actual,
            "model_output": output, "warnings": sorted(set(warnings))}


def run_slots(cases, schedule, requests, audit, client, emit):
    """Client sees only locked request, never labels; no retry path exists."""
    docs = {c["case_id"]: c["input"] for c in cases}
    reqs = {(r["case_id"], r["profile"]): r["request"] for r in requests}
    counts = {(r["case_id"], r["profile"]): r for r in audit}
    # No lazy per-slot preflight: reject any bad budget before first external call.
    for row in audit:
        if row["prompt_tokens"] + OPTIONS["num_predict"] > OPTIONS["num_ctx"]:
            raise ValueError("Context budget exceeded before any call.")
    for slot in schedule:
        doc = docs[slot["case_id"]]
        event = {**slot, "recorded_at_utc": utc()}
        if not dataset.eligible(doc):
            emit({**event, "event": "skipped", "status": "input_invalid", "attempted": False})
            continue
        request = reqs[(slot["case_id"], slot["profile"])]
        emit({**event, "event": "attempt_started", "attempted": True, "request_sha256": rag.sha(request)})
        started = time.monotonic()
        try:
            response = client(copy.deepcopy(request))
        except Exception as exc:
            emit({**event, "event": "finished", "attempted": True, "status": "analysis_error", "decision": None,
                  "error": "transport-error", "exception_type": type(exc).__name__,
                  "elapsed_seconds": time.monotonic() - started, "trial_assessments": [], "halt": True})
            return "halted-transport-error"
        emit({**event, "event": "response_received", "response": response,
              "elapsed_seconds": time.monotonic() - started})
        parsed = parse_output(doc, request, response, counts[(slot["case_id"], slot["profile"])]["prompt_tokens"])
        emit({**event, "event": "finished", "attempted": True, **parsed,
              "elapsed_seconds": time.monotonic() - started,
              "runtime_metrics": {k: response.get(k) for k in ("prompt_eval_count", "eval_count", "done", "done_reason")} if isinstance(response, dict) else {}})
        if parsed.get("halt"):
            return "halted-context-mismatch"
    return "completed"


def summarize(cases, labels, schedule, events):
    """Errors stay in denominators; abstentions never become implicit negative claims."""
    docs = {c["case_id"]: c["input"] for c in cases}
    truth = {c["case_id"]: c for c in labels["cases"]}
    starts, finished, skipped = {}, {}, set()
    for event in events:
        sid = event["slot_id"]
        if event["event"] == "attempt_started":
            if sid in starts:
                raise ValueError("Duplicate attempt detected; retries are prohibited.")
            starts[sid] = event
        elif event["event"] == "finished":
            if sid not in starts or sid in finished:
                raise ValueError("Unstarted or duplicate final record.")
            finished[sid] = event
        elif event["event"] == "skipped":
            if sid in skipped or sid in starts:
                raise ValueError("Duplicate skip or attempted invalid slot.")
            skipped.add(sid)
    profile_results = {}
    correct_pairs = {p: {} for p in PROFILES}
    for profile in PROFILES:
        planned = [r for r in schedule if r["profile"] == profile and dataset.eligible(docs[r["case_id"]])]
        matrix = {c: {o: 0 for o in (*CLASSES, "analysis_error")} for c in CLASSES}
        attempted = correct = trial_n = trial_correct = reason_correct = reason_consistent = warnings = 0
        for slot in planned:
            sid, cid = slot["slot_id"], slot["case_id"]
            if sid not in starts:
                continue
            attempted += 1
            record = finished.get(sid, {"status": "analysis_error", "error": "interrupted-attempt", "trial_assessments": []})
            outcome = record["decision"] if record["status"] == "ok" else "analysis_error"
            matrix[truth[cid]["decision"]][outcome] += 1
            is_correct = outcome == truth[cid]["decision"]
            correct += is_correct
            correct_pairs[profile][cid] = int(is_correct)
            warnings += bool(record.get("warnings"))
            expected = truth[cid]["trial_assessments"]
            trial_n += len(expected)
            for trial in expected:
                actual = [r for r in record.get("trial_assessments", []) if r["trial"] == trial["trial"]]
                trial_correct += record["status"] == "ok" and len(actual) == 1 and actual[0]["outcome"] == trial["outcome"]
            pos, neg = rag.base.REASON_CODES[docs[cid]["technique"]]
            code = {"positive": pos, "negative": neg, "inconclusive": "insufficient_evidence"}[truth[cid]["decision"]]
            reason_correct += record["status"] == "ok" and record.get("model_output", {}).get("reason_code") == code
            if record["status"] == "ok":
                own_code = {"positive": pos, "negative": neg, "inconclusive": "insufficient_evidence"}[record["decision"]]
                reason_consistent += record["model_output"]["reason_code"] == own_code
        errors = sum(row["analysis_error"] for row in matrix.values())
        binary_claims = sum(row[o] for row in matrix.values() for o in ("positive", "negative"))
        binary_ref_n = sum(sum(matrix[c].values()) for c in ("positive", "negative"))
        binary_ref_covered = sum(matrix[c][o] for c in ("positive", "negative") for o in ("positive", "negative"))
        per_class = {}
        for reference_class, cells in matrix.items():
            denominator = sum(cells.values())
            per_class[reference_class] = {"attempted": denominator, "outputs": cells,
                "correct": cells[reference_class], "abstentions": cells["inconclusive"],
                "analysis_errors": cells["analysis_error"],
                "abstention_rate": cells["inconclusive"] / denominator if denominator else None}
            if reference_class == "positive":
                per_class[reference_class]["wrong_negative_claims"] = cells["negative"]
            elif reference_class == "negative":
                per_class[reference_class]["wrong_positive_claims"] = cells["positive"]
        final_rows = [finished[r["slot_id"]] for r in planned if r["slot_id"] in finished]
        runtime = {"finalized_attempts": len(final_rows),
            "wall_seconds_sum": sum(r.get("elapsed_seconds", 0) for r in final_rows),
            "prompt_tokens_sum": sum(r.get("runtime_metrics", {}).get("prompt_eval_count") or 0 for r in final_rows),
            "generated_tokens_sum": sum(r.get("runtime_metrics", {}).get("eval_count") or 0 for r in final_rows),
            "completion_reasons": dict(Counter(str(r.get("runtime_metrics", {}).get("done_reason", "unavailable")) for r in final_rows)),
            "analysis_error_types": dict(Counter(r.get("error", "unknown") for r in final_rows if r["status"] == "analysis_error"))}
        profile_results[profile] = {"planned_eligible": len(planned), "attempted_eligible": attempted,
            "unattempted_eligible": len(planned) - attempted,
            "unfinished_attempts": sum(r["slot_id"] in starts and r["slot_id"] not in finished for r in planned),
            "raw_correct": correct, "raw_accuracy": correct / attempted if attempted else None,
            "reference_output_matrix": matrix, "per_reference_class": per_class, "analysis_errors": errors,
            "analysis_error_rate": errors / attempted if attempted else None,
            "binary_coverage_numerator": binary_claims, "binary_coverage_denominator": attempted,
            "binary_coverage": binary_claims / attempted if attempted else None,
            "binary_reference_coverage_numerator": binary_ref_covered, "binary_reference_coverage_denominator": binary_ref_n,
            "binary_reference_coverage": binary_ref_covered / binary_ref_n if binary_ref_n else None,
            "trial_correct": trial_correct, "trial_denominator": trial_n,
            "trial_accuracy": trial_correct / trial_n if trial_n else None,
            "reason_code_correct": reason_correct, "reason_code_denominator": attempted,
            "reason_code_accuracy": reason_correct / attempted if attempted else None,
            "reason_code_consistent": reason_consistent, "reason_code_consistency_denominator": attempted,
            "reason_code_consistency": reason_consistent / attempted if attempted else None,
            "semantic_warning_cases": warnings, "runtime": runtime}
    a, b = (profile_results[p] for p in ("A", "B3"))
    complete = all(r["attempted_eligible"] == r["planned_eligible"] and not r["unfinished_attempts"] for r in profile_results.values())
    # A gate violation invalidates any conclusion, even if all 108 eligible slots finished.
    gate_violations = [sid for sid, r in starts.items() if not dataset.eligible(docs[r["case_id"]])]
    paired = sorted(set(correct_pairs["A"]) & set(correct_pairs["B3"]))
    delta = sum(correct_pairs["B3"][cid] - correct_pairs["A"][cid] for cid in paired) / len(paired) if paired else None
    transitions = {name: [] for name in ("wrong_to_correct", "correct_to_wrong", "both_correct", "both_wrong")}
    names = {(0, 1): "wrong_to_correct", (1, 0): "correct_to_wrong", (1, 1): "both_correct", (0, 0): "both_wrong"}
    for cid in paired:
        transitions[names[(correct_pairs["A"][cid], correct_pairs["B3"][cid])]].append(cid)
    eligible_ids = {c["case_id"] for c in cases if dataset.eligible(c["input"])}
    unfinished_pairs = sorted({r["case_id"] for r in schedule if r["profile"] in ("A", "B3")
                               and r["slot_id"] in starts and r["slot_id"] not in finished})
    guards = {"positive_correct_not_lower": b["reference_output_matrix"]["positive"]["positive"] >= a["reference_output_matrix"]["positive"]["positive"],
        "negative_false_positive_not_higher": b["reference_output_matrix"]["negative"]["positive"] <= a["reference_output_matrix"]["negative"]["positive"],
        "binary_reference_coverage_not_lower": (b["binary_reference_coverage"] or 0) >= (a["binary_reference_coverage"] or 0),
        "analysis_errors_not_higher": b["analysis_errors"] <= a["analysis_errors"]}
    conclusion = "incomplete"
    if complete and not gate_violations:
        conclusion = ("improvement-on-this-synthetic-dataset" if all(guards.values()) else "accuracy-increase-with-tradeoff") if delta > 0 else "no-raw-accuracy-improvement"
    return {"scope": "synthetic-development-only", "profiles": profile_results,
        "primary": {"comparison": "A-versus-B3", "paired_attempted_cases": len(paired),
            "paired_accuracy_difference_percentage_points": 100 * delta if delta is not None else None,
            "paired_correctness_transitions": {name: {"count": len(ids), "case_ids": ids} for name, ids in transitions.items()},
            "unpaired_eligible_case_ids": sorted(eligible_ids - set(paired)),
            "unfinished_pair_case_ids": unfinished_pairs,
            "complete": complete, "guards": guards, "conclusion": conclusion},
        "input_gate_violations": gate_violations, "skipped_invalid_slots": len(skipped),
        "labels_researcher_review": labels["researcher_review"], "formal_FPR_or_PSR_claim": False}


def copy_new(source, target):
    with target.open("xb") as stream:
        stream.write(source.read_bytes())


def audit_frozen_contract(cases, labels):
    """Compare retained labels with actual frozen executor rules, outside requests."""
    truth = {row["case_id"]: row for row in labels["cases"]}
    trials = eligible = 0
    for case in cases:
        doc, label = case["input"], truth[case["case_id"]]
        if not dataset.eligible(doc):
            if label["decision"] is not None or label["trial_assessments"]:
                raise ValueError("Invalid input has a model reference label.")
            continue
        eligible += 1
        signals = rag.base.frozen.trial_rule_signals(doc)
        actual = {trial: "positive" if positive else "negative" for trial, positive in signals.items()}
        retained = {row["trial"]: row["outcome"] for row in label["trial_assessments"]}
        if actual != retained or len(retained) != len(label["trial_assessments"]):
            raise ValueError("Retained trial labels differ from frozen executor signals.")
        decision = "inconclusive"
        if sorted(signals) == [1, 2, 3]:
            decision = {0: "negative", 3: "positive"}.get(sum(signals.values()), "inconclusive")
        if decision != label["decision"]:
            raise ValueError("Retained decision differs from frozen confirmation contract.")
        trials += len(signals)
    return {"cases_checked": len(cases), "eligible_cases_checked": eligible,
        "eligible_trial_assessments_checked": trials, "labels_match_frozen_executor": True,
        "frozen_analysis_source_sha256": digest(ROOT / "dvwa/analyze_response.py"),
        "independent_human_validation": False, "model_calls": 0, "dvwa_requests": 0}


def frozen_files():
    pinned = prior.frozen_files()
    for path in (Path(__file__), ROOT / "development/test_analysis_v5_pilot_rev2.py",
                 GUIDE, prior.OUT / "manifest.lock.json"):
        pinned[path.relative_to(ROOT).as_posix()] = digest(path)
    return dict(sorted(pinned.items()))


def freeze(review_file):
    cases, labels, requests, audit = prior.verify()
    if OUT.exists() or REVIEW.exists():
        raise ValueError("Revision already exists; preserve it and use a new version.")
    review_file = Path(review_file)
    # Simpan masukan review persis seperti diterima, tanpa menganggapnya approval.
    feedback_bytes = review_file.read_bytes()
    contract_audit = audit_frozen_contract(cases, labels)
    parent = read(prior.OUT / "manifest.lock.json")
    preserved = dict(read(prior.OUT / "preservation.lock.json"))
    preserved.update(parent["source_sha256"])
    preserved.update(parent["artifact_sha256"])
    preserved[(prior.OUT / "manifest.lock.json").relative_to(ROOT).as_posix()] = digest(prior.OUT / "manifest.lock.json")
    OUT.mkdir(parents=True)
    for name in IDENTICAL_ARTIFACTS:
        copy_new(prior.OUT / name, OUT / name)
    REVIEW.mkdir(parents=True)
    for source in prior.REVIEW.iterdir():
        if source.is_file():
            copy_new(source, REVIEW / source.name)
    feedback_path = OUT / "review-feedback.source.txt"
    with feedback_path.open("xb") as stream:
        stream.write(feedback_bytes)
    feedback = {
        "origin": "review text forwarded by user", "independent_human_authorship": "not-established",
        "researcher_adoption": "not-recorded", "researcher_review": "pending",
        "source_sha256": digest(feedback_path), "received_source_filename": review_file.name,
        "source_scope_limit": "reviewer had not verified frozen code, actual requests or protocol.lock.json",
        "reported_label_changes": 0, "reported_trial_assessments_checked": 102,
        "F-01": "retain conservative 768-token budget rejection; distinguish it from incomplete generation and JSON errors",
        "F-02": "separate structural errors from semantic warnings and reference reason accuracy from internal consistency",
        "additional_reporting": "paired A/B3 correctness transitions and explicit dataset coverage limitations",
    }
    write_new(OUT / "review-feedback.lock.json", feedback)
    write_new(OUT / "frozen-contract-audit.lock.json", contract_audit)
    write_new(OUT / "protocol.lock.json", protocol())
    write_new(OUT / "preservation.lock.json", dict(sorted(preserved.items())))
    summary = {**read(prior.OUT / "readiness-summary.json"), "pilot_id": OUT.name,
        "protocol_revision": 2, "created_at_utc": utc(), "parent_pilot_id": prior.OUT.name,
        "parent_manifest_sha256": digest(prior.OUT / "manifest.lock.json"),
        "identical_parent_artifacts": list(IDENTICAL_ARTIFACTS),
        "corpus_sha256": digest(rag.checker.CORPUS), "preserved_files": len(preserved),
        "review_feedback_recorded": True, "researcher_adoption": "not-recorded"}
    write_new(OUT / "readiness-summary.json", summary)
    manifest = {"freeze_version": 2, "created_at_utc": utc(), "source_sha256": frozen_files(),
        "parent_manifest_sha256": digest(prior.OUT / "manifest.lock.json"),
        "artifact_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for folder in (OUT, REVIEW)
                            for p in sorted(folder.iterdir()) if p.is_file()},
        "environment": {p: version(p) for p in ("tokenizers", "jsonschema", "chromadb")},
        "model_calls_executed_at_freeze": 0}
    write_new(OUT / "manifest.lock.json", manifest)
    print(json.dumps(summary))


def verify():
    # Parent, formal evidence, labels, prompts and corpus must remain reproducible.
    prior.verify()
    manifest = read(OUT / "manifest.lock.json")
    if manifest["parent_manifest_sha256"] != digest(prior.OUT / "manifest.lock.json"):
        raise ValueError("Parent manifest changed.")
    for group in ("source_sha256", "artifact_sha256"):
        for name, expected in manifest[group].items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Frozen revision source/artifact changed: {name}")
    for package, expected in manifest["environment"].items():
        if version(package) != expected:
            raise ValueError("Pinned Python dependency version differs.")
    preserved = read(OUT / "preservation.lock.json")
    for name, expected in preserved.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Preserved artifact changed: {name}")
    for name in IDENTICAL_ARTIFACTS:
        if (OUT / name).read_bytes() != (prior.OUT / name).read_bytes():
            raise ValueError(f"Revision changed a retained artifact: {name}")
    feedback = read(OUT / "review-feedback.lock.json")
    if feedback["source_sha256"] != digest(OUT / "review-feedback.source.txt"):
        raise ValueError("Forwarded review text differs.")
    cases, labels = dataset.build_cases()
    if read(OUT / "frozen-contract-audit.lock.json") != audit_frozen_contract(cases, labels):
        raise ValueError("Frozen contract audit does not reproduce.")
    requests = prepare_requests(cases)
    audit = audit_requests(cases, requests, Tokenizer.from_file(str(context.RAW / "tokenizer.json")))
    for name, expected in (("inputs.lock.json", cases), ("labels.ai.lock.json", labels),
            ("protocol.lock.json", protocol()), ("schedule.lock.json", dataset.schedule(cases)),
            ("prepared-requests.lock.json", requests), ("request-audit.lock.json", audit),
            ("schedule-audit.lock.json", audit_schedule(cases, dataset.schedule(cases)))):
        if read(OUT / name) != expected:
            raise ValueError(f"Reproduced revision differs: {name}")
    print(json.dumps({"status": "pilot-r2-offline-verification-passed", "cases": len(cases),
        "actual_requests": len(audit), "preserved_files": len(preserved),
        "identical_parent_artifacts": len(IDENTICAL_ARTIFACTS), "model_calls": 0, "dvwa_requests": 0}))
    return cases, labels, requests, audit


def execute():
    cases, labels, requests, audit = verify()
    # Runtime binding is checked only on explicit --execute. No stop=['{'] probe is reused.
    inventory = context.api("/api/tags")
    model = next(m for m in inventory["models"] if m["name"] == context.MODEL)
    if model["digest"] != context.EXPECTED_DIGEST:
        raise ValueError("Installed Qwen model digest changed.")
    shown = context.api("/api/show", {"model": context.MODEL, "verbose": True})
    old_show = read(context.RAW / "model-show.json")
    for key in ("template", "parameters", "model_info"):
        if shown.get(key) != old_show.get(key):
            raise ValueError("Installed runtime template/model configuration changed.")
    runtime_version = context.api("/api/version")
    if runtime_version != read(context.RAW / "runtime-before.json")["version"]:
        raise ValueError("Ollama version differs from the pinned context evidence.")
    RAW.mkdir(parents=True, exist_ok=False)
    write_new(RAW / "runtime-before.json", {"model": model, "version": runtime_version, "at_utc": utc(),
        "manifest_sha256": digest(OUT / "manifest.lock.json")})
    schedule = read(OUT / "schedule.lock.json")
    events = []
    with (RAW / "events.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        def emit(event):
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            events.append(event)
            if event["event"] in ("finished", "skipped"):
                print(json.dumps({k: event[k] for k in ("slot_id", "case_id", "profile", "status")}), flush=True)
        status = run_slots(cases, schedule, requests, audit, lambda req: context.api("/api/chat", req), emit)
    summary = summarize(cases, labels, schedule, events)
    summary["session_status"] = status
    summary["events_sha256"] = digest(RAW / "events.jsonl")
    write_new(RAW / "summary.json", summary)
    print(json.dumps(summary))


def score_saved():
    cases, labels, requests, audit = verify()
    # A killed process can leave only a partial final JSONL line; retain the bytes and classify its started attempt as interrupted.
    data = (RAW / "events.jsonl").read_text(encoding="utf-8")
    events = []
    lines = data.splitlines()
    for i, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except ValueError:
            if i != len(lines) - 1 or data.endswith("\n"):
                raise
    print(json.dumps(summarize(cases, labels, read(OUT / "schedule.lock.json"), events)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--execute", action="store_true")
    actions.add_argument("--score-saved", action="store_true")
    parser.add_argument("--review-file", type=Path, help="Forwarded review source; required only with --freeze")
    args = parser.parse_args()
    if args.freeze and not args.review_file:
        parser.error("--freeze requires --review-file")
    if args.review_file and not args.freeze:
        parser.error("--review-file is only allowed with --freeze")
    freeze(args.review_file) if args.freeze else execute() if args.execute else score_saved() if args.score_saved else verify()
