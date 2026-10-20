"""Freeze, verify, and explicitly execute a synthetic development pilot, without verdict correction."""

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
import preflight_analysis_v5_context as context
import verify_analysis_v5_context as previous_verifier

rag = dataset.rag
ROOT = rag.ROOT
OUT = ROOT / "results/processed/analysis-v5-pilot-20261020"
RAW = ROOT / "results/raw/development/analysis-v5-pilot-20261020"
REVIEW = ROOT / "outputs/analysis-v5-pilot-review"
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
    return {"pilot_id": OUT.name, "scope": "synthetic-development-contract-conformance",
        "data_origin": "AI-authored response features, not DVWA HTTP captures", "independent_holdout": False,
        "researcher_review": "pending", "researcher_adoption": "not-recorded",
        "planned_cases": 42, "eligible_cases": 36, "invalid_gate_cases": 6,
        "eligible_per_technique": 12, "eligible_per_technique_per_reference_class": 4,
        "planned_model_calls": 108, "gate_skipped_slots": 18,
        "profiles": {"A": {"top_k": 0}, "B2": {"top_k": 2}, "B3": {"top_k": 3}},
        "model": context.MODEL, "model_digest": context.EXPECTED_DIGEST, "options": OPTIONS,
        "schedule_seed": dataset.SEED, "profile_orders": "all six permutations, balanced within eligible technique",
        "retrieval": "frozen Nomic cosine ranking reused only for exactly matching label-free technique/injection-point queries",
        "B3_limit": "all three eligible chunks, complete technique context; no ranking-selectivity attribution",
        "reference_labels": "contract-derived AI labels outside requests, pending researcher review",
        "input_gate": "schema must pass; runtime_status=valid AND baseline_valid=true before every model call",
        "budget": "recount every locked request with pinned tokenizer; abort whole execution before first call on excess; never trim",
        "timeout_seconds": TIMEOUT, "content_retries": 0, "transport_retries": 0,
        "execution": "one sequential session, no resume or repeating any started slot under this run directory",
        "content_errors": "missing content, invalid JSON/schema, unknown observation ID, incomplete/length-exhausted generation => analysis_error and continue",
        "transport_errors": "record attempt as analysis_error and halt session without retry; all remaining valid slots unattempted",
        "prompt_count_mismatch": "analysis_error on attempted case; halt session, retain raw response",
        "interruption": "persist attempt_started before call; unmatched started attempt is interrupted analysis_error; never silently rerun",
        "semantic_audit": "retain schema-valid raw decision even if tally, reason, references or trial logic contradict; report warnings separately",
        "primary": {"comparison": "A versus B3", "metric": "raw three-class decision accuracy",
            "numerator": "attempted eligible cases with schema-valid raw decision equal to reference decision",
            "denominator": "all attempted eligible cases per profile, including analysis errors and interrupted attempts",
            "complete_denominator_per_profile": 36,
            "pairing": "paired correctness difference across all 36 identical eligible inputs; any missing attempt makes conclusion incomplete",
            "direction": "B3 accuracy minus A accuracy, percentage points", "content_errors_receive_credit": False},
        "companions": ["3x4 reference/output matrix with analysis_error column", "per-class false claims and abstentions",
            "binary coverage on all attempted cases and separately on binary-reference cases", "analysis error rate",
            "trial accuracy using all expected available trials, including trials in errored attempts",
            "reason code accuracy, semantic warning count, durations, tokens, completion", "B2 descriptive comparison"],
        "coverage": "positive/negative non-error decisions divided by all attempted eligible cases; inconclusive is abstention",
        "trial_scoring": "each expected available trial scores 1 only for exactly one assessment with correct outcome; missing/duplicate/errored trial scores 0",
        "conclusion_rule": {"prerequisite": "all 108 eligible slots attempted and finalized, no input gate violations",
            "improvement_on_this_dataset": "B3 raw accuracy > A raw accuracy, with positive correct count not lower, negative false-positive count not higher, binary-reference coverage not lower, and analysis-error count not higher",
            "tradeoff": "accuracy increases but at least one companion guard worsens",
            "no_improvement": "B3 raw accuracy <= A raw accuracy",
            "incomplete": "any planned eligible attempt missing or unfinished; descriptive attempted denominators only"},
        "formal_metrics": "does not replace proposal FPR ablation or PSR LLM/SecLists, and does not change R1/R2/R3",
        "execution_started_at_freeze": False}


def parse_output(document, request, response, expected_prompt):
    base = {"status": "analysis_error", "decision": None, "error": None, "warnings": [],
            "trial_assessments": [], "model_output": None}
    if not isinstance(response, dict):
        return {**base, "error": "malformed-runtime-response"}
    # A complete JSON object still counts as an output error if the runtime exhausted its allowance.
    if response.get("prompt_eval_count") != expected_prompt:
        return {**base, "error": "prompt-count-mismatch", "halt": True}
    if (response.get("done") is not True or response.get("done_reason") != "stop"
            or type(response.get("eval_count")) is not int or not 0 < response["eval_count"] < OPTIONS["num_predict"]):
        return {**base, "error": "incomplete-or-exhausted-output"}
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
    if not {ref for t in expected for ref in t["evidence_refs"]}.issubset(output["evidence_refs"]):
        warnings.append("incomplete-top-level-citations")
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
        attempted = correct = trial_n = trial_correct = reason_correct = warnings = 0
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
            "semantic_warning_cases": warnings, "runtime": runtime}
    a, b = (profile_results[p] for p in ("A", "B3"))
    complete = all(r["attempted_eligible"] == r["planned_eligible"] and not r["unfinished_attempts"] for r in profile_results.values())
    # A gate violation invalidates any conclusion, even if all 108 eligible slots finished.
    gate_violations = [sid for sid, r in starts.items() if not dataset.eligible(docs[r["case_id"]])]
    paired = sorted(set(correct_pairs["A"]) & set(correct_pairs["B3"]))
    delta = sum(correct_pairs["B3"][cid] - correct_pairs["A"][cid] for cid in paired) / len(paired) if paired else None
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
            "complete": complete, "guards": guards, "conclusion": conclusion},
        "input_gate_violations": gate_violations, "skipped_invalid_slots": len(skipped),
        "labels_researcher_review": labels["researcher_review"], "formal_FPR_or_PSR_claim": False}


def frozen_files():
    previous = read(context.OUT / "preflight-manifest.json")
    paths = {ROOT / p for p in previous["source_sha256"]}
    paths.update(ROOT / p for p in read(context.previous.RAW / "design.json")["source_sha256"])
    paths.update([Path(__file__), Path(dataset.__file__), Path(previous_verifier.__file__), Path(context.__file__),
        ROOT / "development/test_analysis_v5_pilot.py", ROOT / "docs/paket-pilot-analisis-v5-2026-10-20.md",
        context.OUT / "pilot-profile.candidate.json", context.OUT / "preflight-manifest.json",
        context.OUT / "completion-manifest.json", context.previous.RAW / "projection.json",
        context.previous.RAW / "retrieval.json", context.RAW / "tokenizer.json", context.RAW / "tokenizer-receipt.json",
        context.RAW / "model-show.json", context.RAW / "runtime-before.json"])
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def freeze():
    previous_verifier.verify()
    if OUT.exists() or REVIEW.exists():
        raise ValueError("Frozen pilot already exists. Preserve it and use a new version for revisions.")
    cases, labels = dataset.build_cases()
    requests = prepare_requests(cases)
    tokenizer = Tokenizer.from_file(str(context.RAW / "tokenizer.json"))
    audit = audit_requests(cases, requests, tokenizer)
    schedule = dataset.schedule(cases)
    balance = audit_schedule(cases, schedule)
    # Preserve all previous tracked and local results used by earlier work.
    preserved = dict(read(context.OUT / "preservation-baseline.json")["files"])
    for folder in (context.OUT, context.RAW, context.previous.OUT, context.previous.RAW):
        for path in folder.rglob("*"):
            if path.is_file():
                preserved[path.relative_to(ROOT).as_posix()] = digest(path)
    OUT.mkdir(parents=True)
    for name, value in (("protocol.lock.json", protocol()), ("inputs.lock.json", cases),
            ("labels.ai.lock.json", labels), ("schedule.lock.json", schedule),
            ("prepared-requests.lock.json", requests), ("request-audit.lock.json", audit),
            ("schedule-audit.lock.json", balance), ("preservation.lock.json", preserved)):
        write_new(OUT / name, value)
    composition = Counter((r["technique"], r["decision"] or "input_invalid") for r in labels["cases"])
    summary = {"status": "frozen-offline-pending-researcher-review", "created_at_utc": utc(),
        "cases": len(cases), "eligible": sum(dataset.eligible(c["input"]) for c in cases),
        "composition": [{"technique": t, "reference": d, "count": n} for (t, d), n in composition.items()],
        "scheduled_slots": len(schedule), "planned_model_calls": 108, "gate_skipped_slots": 18,
        "actual_case_requests_audited": len(audit), "maximum_prompt_tokens": max(r["prompt_tokens"] for r in audit),
        "minimum_reserved_headroom": min(r["reserved_headroom"] for r in audit),
        "same_request_except_reference_context": True, "model_calls_executed": 0, "dvwa_requests": 0,
        "researcher_review": "pending", "independent_holdout": False}
    write_new(OUT / "readiness-summary.json", summary)
    REVIEW.mkdir(parents=True)
    lines = ["# Review paket pilot v5", "", "Seluruh kasus dan label adalah sintetis buatan AI. Review peneliti masih pending.", "",
        "Periksa label pada tabel ini, kebijakan metrik/error pada protocol.lock.json, dan request aktual. Jangan masukkan label ini ke prompt/retrieval.", "",
        "| ID | Teknik | Referensi kontrak | Asesmen trial | Alasan |", "| --- | --- | --- | --- | --- |"]
    for row in labels["cases"]:
        trials = ", ".join(f"{r['trial']}:{r['outcome']}" for r in row["trial_assessments"])
        lines.append(f"| {row['case_id']} | {row['technique']} | {row['decision'] or 'input_invalid'} | {trials} | {row['rationale']} |")
    lines += ["", "Perubahan setelah freeze memerlukan versi paket baru dan hash baru sebelum inferensi.", ""]
    (REVIEW / "cases.review.md").write_text("\n".join(lines), encoding="utf-8")
    for cid in ("pilot-001", "pilot-013", "pilot-025", "pilot-029", "pilot-042"):
        for row in requests:
            if row["case_id"] == cid:
                write_new(REVIEW / f"{cid}.{row['profile']}.request.json", row["request"])
    manifest = {"freeze_version": 1, "created_at_utc": utc(), "source_sha256": frozen_files(),
        "artifact_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for folder in (OUT, REVIEW)
                            for p in folder.iterdir() if p.is_file()},
        "environment": {p: version(p) for p in ("tokenizers", "jsonschema", "chromadb")},
        "model_calls_executed_at_freeze": 0}
    write_new(OUT / "manifest.lock.json", manifest)
    print(json.dumps(summary))


def verify():
    manifest = read(OUT / "manifest.lock.json")
    for group in ("source_sha256", "artifact_sha256"):
        for name, expected in manifest[group].items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Frozen source/artifact changed: {name}")
    for package, expected in manifest["environment"].items():
        if version(package) != expected:
            raise ValueError("Pinned Python dependency version differs.")
    preserved = read(OUT / "preservation.lock.json")
    for name, expected in preserved.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Preserved artifact changed: {name}")
    previous_verifier.verify()
    cases, labels = dataset.build_cases()
    requests = prepare_requests(cases)
    audit = audit_requests(cases, requests, Tokenizer.from_file(str(context.RAW / "tokenizer.json")))
    for name, expected in (("inputs.lock.json", cases), ("labels.ai.lock.json", labels),
            ("protocol.lock.json", protocol()), ("schedule.lock.json", dataset.schedule(cases)),
            ("prepared-requests.lock.json", requests), ("request-audit.lock.json", audit),
            ("schedule-audit.lock.json", audit_schedule(cases, dataset.schedule(cases)))):
        if read(OUT / name) != expected:
            raise ValueError(f"Reproduced pilot differs: {name}")
    print(json.dumps({"status": "pilot-offline-verification-passed", "cases": len(cases),
                      "actual_requests": len(audit), "preserved_files": len(preserved), "model_calls": 0}))
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
    args = parser.parse_args()
    freeze() if args.freeze else execute() if args.execute else score_saved() if args.score_saved else verify()
