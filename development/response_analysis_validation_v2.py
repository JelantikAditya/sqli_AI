"""Freeze and evaluate v1/v2 on new synthetic cases, plus a separate v1 regression set."""

from __future__ import annotations

import argparse
import copy
import json
import random
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import analyze_response_v1 as v1
import analyze_response_v2 as v2
import response_analysis_pilot as pilot

ROOT = pilot.ROOT
EXPERIMENT_ID = "response-analysis-dev-v2-20261019"
PROFILES = {"measured-pairs-v1": v1, "explicit-contract-v2": v2}
V1_DATA = ROOT / "results/raw/development/response-analysis-v1-20261019"


def new_cases():
    """Predeclared measurements, including control confounders and threshold boundaries."""
    rng = random.Random(2026101902)
    catalog = {s["scenario_id"]: s for s in pilot.load_catalog()["scenarios"]}
    definitions = []
    for sid in ("S1", "S2", "S3"):
        definitions.extend([
            (sid, "consistent-positive", (1, 1, 1), (1, 2, 3), "positive"),
            (sid, "consistent-negative", (0, 0, 0), (1, 2, 3), "negative"),
            (sid, "mixed", (1, 0, 1) if sid == "S2" else (0, 0, 1), (1, 2, 3), "inconclusive"),
            (sid, "incomplete", (0,) if sid == "S2" else (1, 1),
             (2,) if sid == "S2" else (1, 3), "inconclusive"),
        ])
    definitions.extend([
        ("S3", "exact-threshold", (1, 1, 1), (1, 2, 3), "positive"),
        ("S3", "below-threshold", (0, 0, 0), (1, 2, 3), "negative"),
        ("S3", "unmatched-markers", (0, 0, 0), (1, 2, 3), "negative"),
        ("S1", "preexisting-diagnostic", (0, 0, 0), (1, 2, 3), "negative"),
        ("S3", "invalid-baseline", (0, 0, 0), (1, 2, 3), None),
    ])
    public, labels = [], []
    for index, (sid, name, signals, trials, expected) in enumerate(definitions, 1):
        scenario = catalog[sid]
        observations = []

        def observation(trial, role, *, markers=None, diagnostics=None, status=200, elapsed=None):
            number = len(observations) + 1
            observations.append({
                "observation_id": f"obs-{number:03d}", "trial": trial, "role": role,
                "http_status": status, "elapsed_ms": round(rng.uniform(12, 35), 2) if elapsed is None else elapsed,
                "response_sha256": pilot.hashlib.sha256(f"v2-new-{index}-{number}-{rng.getrandbits(128)}".encode()).hexdigest(),
                "diagnostics": diagnostics or [], "content_markers": markers or [],
            })

        for trial, signal in zip(trials, signals):
            baseline_diagnostics = ["mysql_xpath_error"] if name == "preexisting-diagnostic" else []
            observation(trial, "baseline", markers=["benign_record"] if sid == "S1" else ["user_id_exists"],
                        diagnostics=baseline_diagnostics)
            if sid == "S1":
                diagnostics = baseline_diagnostics or (["mysql_syntax_error"] if signal else [])
                observation(trial, "candidate", diagnostics=diagnostics, status=500)
            elif sid == "S2":
                # Reversed markers are negative despite different HTTP bodies.
                observation(trial, "true_condition", markers=["user_id_exists"] if signal else ["user_id_missing"],
                            status=200 if signal else 404)
                observation(trial, "false_condition", markers=["user_id_missing"] if signal else ["user_id_exists"],
                            status=404 if signal else 200)
            else:
                # Integral controls avoid a floating-point subtraction ambiguity at 1500 ms.
                control = rng.randint(60, 110)
                delta = 1500 if name == "exact-threshold" else 1499.99 if name == "below-threshold" else (
                    1800 if name == "unmatched-markers" else rng.randint(1600, 2100) if signal else -7)
                observation(trial, "candidate", markers=["user_id_exists"], elapsed=round(control + delta, 2))
                observation(trial, "no_delay_control", markers=["user_id_missing"] if name == "unmatched-markers"
                            else ["user_id_exists"], status=404 if name == "unmatched-markers" else 200, elapsed=control)
        document = {
            "schema_version": "1.0.0", "technique": scenario["sqli_type"],
            "injection_point": {key: scenario[key] for key in ("method", "input_path", "result_path", "parameter")},
            "runtime_status": "valid" if expected is not None else "invalid", "baseline_valid": expected is not None,
            "time_threshold_ms": 1500, "observations": observations,
        }
        context = {"experiment_id": EXPERIMENT_ID, "run_id": f"new-{index:03d}", "attempt_id": "validation-1",
                   "candidate_id": "candidate-001", "scenario_id": sid, "replicate": 1,
                   "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        v1.frozen.validate_input(document)
        status = v1.frozen.confirmation_result(document)["evidence_status"]
        derived = {"CONSISTENT_POSITIVE": "positive", "CONSISTENT_NEGATIVE": "negative",
                   "MIXED_EVIDENCE": "inconclusive", "INCOMPLETE_CONFIRMATIONS": "inconclusive",
                   "RUNTIME_INVALID": None}[status]
        pilot.require(derived == expected, "A predeclared synthetic label disagrees with the protocol.")
        case_id = f"new-{index:03d}"
        public.append({"case_id": case_id, "dataset": "new-validation", "input": document, "context": context})
        labels.append({"case_id": case_id, "diagnostic_name": name, "expected_claim": expected})
    return public, labels


def regression_cases():
    cases = json.loads((V1_DATA / "inputs.json").read_text(encoding="utf-8"))
    labels = json.loads((V1_DATA / "evaluation.private.json").read_text(encoding="utf-8"))
    for case in cases:
        case["case_id"] = "regression-" + case["case_id"]
        case["dataset"] = "opened-v1-regression"
    for label in labels:
        label["case_id"] = "regression-" + label["case_id"]
    return cases, labels


def audit_request(case, prepared):
    # Only measured facts enter the model. Context and evaluator labels stay outside.
    view = json.loads(prepared["request"]["messages"][1]["content"])
    pilot.require(view == v1.paired_view(case["input"]), "Model input is not the allowlisted measured view.")
    pilot.require(prepared["request"]["options"] == {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 768},
                  "Unequal model options.")
    pilot.require(len(prepared["request"]["messages"]) == 2, "Unexpected retrieval/context message.")


def prepare(output):
    pilot.require(not output.exists(), "Use a new validation output directory.")
    protected = pilot.check_protected_sources()
    public, labels = new_cases()
    regression, regression_labels = regression_cases()
    public.extend(regression)
    labels.extend(regression_labels)
    schedule = []
    for index, case in enumerate(public):
        profiles = list(PROFILES) if case["dataset"] == "new-validation" else ["explicit-contract-v2"]
        if index % 2:
            profiles.reverse()
        for profile in profiles:
            prepared = PROFILES[profile].prepared_request(case["input"], seed=42)
            audit_request(case, prepared)
            schedule.append({"case_id": case["case_id"], "profile": profile, "prepared": prepared})
    output.mkdir(parents=True, exist_ok=False)
    pilot.write_json(output / "inputs.json", public)
    pilot.write_json(output / "evaluation.private.json", labels)
    pilot.write_json(output / "prepared-requests.json", schedule)
    sources = [Path(__file__).resolve(), Path(v2.__file__).resolve(), Path(v1.__file__).resolve(), Path(pilot.__file__).resolve(),
               ROOT / "dvwa/analyze_response.py", ROOT / "dvwa/confirmation_policy.py", ROOT / "dvwa/rag_pipeline.py",
               ROOT / "dvwa/langchain_runtime.py", ROOT / "dvwa/run_decision_policy.py",
               ROOT / "schemas/qwen-analysis-input.schema.json", ROOT / "schemas/qwen-analysis-output.schema.json",
               ROOT / "schemas/analysis-ledger.schema.json", ROOT / "dvwa/experiment_scenarios.json"]
    source_artifacts = [V1_DATA / name for name in ("inputs.json", "evaluation.private.json", "runtime.json", "manifest.json")]
    old_runtime = json.loads((V1_DATA / "runtime.json").read_text(encoding="utf-8"))
    pilot.write_json(output / "manifest.json", {
        "scope": "predeclared-synthetic-development-validation-not-independent-holdout-not-formal",
        "experiment_id": EXPERIMENT_ID, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profiles": list(PROFILES), "new_case_count": len(public) - len(regression), "regression_case_count": len(regression),
        "scheduled_records": len(schedule), "planned_model_calls": 41,
        "model": v2.MODEL, "expected_model_digest": old_runtime["digest"],
        "options": {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 768},
        "analysis_retrieval": "disabled-for-both-profiles", "dvwa_requests": 0,
        "no_automatic_retry": True, "adaptation_after_first_inference": False,
        "comparison": "v1-vs-v2-on-identical-new-cases; opened-v1-cases-regression-only",
        "success_criteria": {"new_v2_verdicts_correct": "16/16", "new_v2_trial_assessments_correct": "44/44",
                             "decision_reason_code_mismatches": 0, "model_tally_mismatches": 0,
                             "regression_v2_verdicts_correct": "9/9", "analysis_errors": 0,
                             "automatic_promotion_to_formal": False},
        "protected_source_count": protected,
        "source_sha256": {p.relative_to(ROOT).as_posix(): pilot.digest(p) for p in sources},
        "regression_source_sha256": {p.relative_to(ROOT).as_posix(): pilot.digest(p) for p in source_artifacts},
        "artifact_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
    })
    print(json.dumps({"status": "prepared-and-frozen", "directory": str(output), "planned_model_calls": 41,
                      "new_cases": 17, "regression_cases": 10, "dvwa_requests": 0}), flush=True)


def metrics(rows):
    valid = [r for r in rows if r["expected_claim"] is not None]
    completed = [r for r in valid if r["record"]["analysis_status"] == "completed"]
    trial_correct = trial_total = reason_correct = 0
    warnings = Counter()
    for row in valid:
        record = row["record"]
        output = record["model_output"]
        signals = v1.frozen.trial_rule_signals(record["evidence"])
        trial_total += len(signals)
        by_trial = {}
        duplicates = set()
        for assessment in (output or {}).get("trial_assessments", []):
            if assessment["trial"] in by_trial:
                duplicates.add(assessment["trial"])
            by_trial[assessment["trial"]] = assessment
        for trial, signal in signals.items():
            assessment = by_trial.get(trial)
            trial_correct += bool(assessment and trial not in duplicates and assessment["outcome"] == (
                "positive" if signal else "negative"))
        if output:
            codes = dict(zip(("positive", "negative"), v2.REASON_CODES[record["evidence"]["technique"]]))
            reason_correct += output["reason_code"] == codes.get(output["decision"], "insufficient_evidence")
        warnings.update(record["analysis_warnings"])
        warnings.update(record["audit"]["provenance"].get("development_contract_warnings", []))
    return {
        "records": len(rows), "valid_cases": len(valid), "valid_verdict_matches": sum(r["matches_expected"] for r in valid),
        "trial_assessments_correct": trial_correct, "trial_assessments_total": trial_total,
        "completed_outputs": len(completed), "decision_reason_code_consistent": reason_correct,
        "analysis_errors": sum(r["record"]["analysis_status"] == "analysis_error" for r in valid),
        "invalid_evidence_reference": sum(r["record"]["analysis_status"] == "invalid_evidence_reference" for r in valid),
        "false_positive_on_negative_fixtures": sum(r["expected_claim"] == "negative" and r["record"]["system_claim"] == "positive" for r in valid),
        "false_negative_on_positive_fixtures": sum(r["expected_claim"] == "positive" and r["record"]["system_claim"] == "negative" for r in valid),
        "abstention_on_binary_fixtures": sum(r["expected_claim"] in ("positive", "negative") and r["record"]["system_claim"] == "inconclusive" for r in valid),
        "binary_decisions_on_inconclusive_fixtures": sum(r["expected_claim"] == "inconclusive" and r["record"]["system_claim"] in ("positive", "negative") for r in valid),
        "binary_decision_coverage": sum(r["record"]["system_claim"] in ("positive", "negative") for r in valid) / len(valid) if valid else None,
        "runtime_invalid_skips": sum(r["record"]["analysis_status"] == "runtime_invalid" for r in rows),
        "warning_counts": dict(warnings), "total_elapsed_seconds": sum(r["elapsed_seconds"] for r in rows),
        "median_valid_case_seconds": statistics.median(r["elapsed_seconds"] for r in valid) if valid else None,
        "done_reasons": dict(Counter(r["record"]["audit"]["provenance"].get("runtime_metrics", {}).get("done_reason") for r in valid)),
    }


def summarize(output, *, wall_seconds=None):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    pilot.require(len(rows) == manifest["scheduled_records"], "Validation is incomplete; retain partial ledger.")
    summaries = []
    for dataset in ("new-validation", "opened-v1-regression"):
        for profile in PROFILES:
            selected = [r for r in rows if r["dataset"] == dataset and r["profile"] == profile]
            if selected:
                summaries.append({"dataset": dataset, "profile": profile, **metrics(selected)})
    protected = pilot.check_protected_sources()
    summary = {
        "scope": manifest["scope"], "experiment_id": EXPERIMENT_ID, "manifest_sha256": pilot.digest(output / "manifest.json"),
        "model": v2.MODEL, "model_digest": manifest["expected_model_digest"], "profiles": summaries,
        "scheduled_records": len(rows), "model_calls": sum("raw_model_content" in r["record"]["audit"]["provenance"] for r in rows),
        "total_wall_seconds": wall_seconds, "dvwa_requests": 0, "formal_metrics_recomputed": False,
        "protected_sources_unchanged": protected, "model_claims_replaced": False,
        "prototype_promoted_to_formal_runner": False,
        "results": [{"case_id": r["case_id"], "dataset": r["dataset"], "profile": r["profile"],
                     "expected_claim": r["expected_claim"], "actual_claim": r["record"]["system_claim"],
                     "matches": r["matches_expected"], "analysis_status": r["record"]["analysis_status"],
                     "reason_code": (r["record"]["model_output"] or {}).get("reason_code"),
                     "warnings": r["record"]["analysis_warnings"],
                     "contract_warnings": r["record"]["audit"]["provenance"].get("development_contract_warnings", [])}
                    for r in rows],
    }
    pilot.write_json(output / "summary.json", summary)
    print(json.dumps({"status": "completed", "profiles": summaries, "summary": str(output / "summary.json")}), flush=True)


def run(output):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    pilot.require(not (output / "replay.jsonl").exists(), "Already started; do not overwrite or retry this validation.")
    for key in ("source_sha256", "regression_source_sha256"):
        pilot.require(all(pilot.digest(ROOT / name) == value for name, value in manifest[key].items()), "Pinned source changed.")
    pilot.require(all(pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Frozen artifact changed.")
    pilot.check_protected_sources()
    opener = build_opener(ProxyHandler({}))
    with opener.open(pilot.local_ollama_url() + "/api/tags", timeout=5) as response:
        models = json.load(response)["models"]
    current = next((m for m in models if m["name"] == v2.MODEL), None)
    pilot.require(current is not None and current["digest"] == manifest["expected_model_digest"], "Qwen model digest differs from v1.")
    pilot.write_json(output / "runtime.json", {"model": v2.MODEL, "digest": current["digest"], "details": current.get("details")})
    cases = {c["case_id"]: c for c in json.loads((output / "inputs.json").read_text(encoding="utf-8"))}
    labels = {c["case_id"]: c for c in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    schedule = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    with (output / "replay.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for step in schedule:
            case, module = cases[step["case_id"]], PROFILES[step["profile"]]
            prepared = module.prepared_request(case["input"], seed=42)
            pilot.require(prepared == step["prepared"], "Request changed after freeze.")
            audit_request(case, prepared)
            print(json.dumps({"case_id": case["case_id"], "profile": step["profile"], "status": "starting"}), flush=True)
            call_started = time.monotonic()
            kwargs = {"prepared": step["prepared"]} if module is v2 else {}
            record = module.analyze_with_qwen(copy.deepcopy(case["input"]), copy.deepcopy(case["context"]), seed=42, **kwargs)
            expected = labels[case["case_id"]]["expected_claim"]
            row = {"case_id": case["case_id"], "dataset": case["dataset"], "profile": step["profile"],
                   "expected_claim": expected, "matches_expected": record["system_claim"] == expected,
                   "elapsed_seconds": time.monotonic() - call_started, "record": record}
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            print(json.dumps({"case_id": case["case_id"], "profile": step["profile"], "actual": record["system_claim"],
                              "expected": expected, "matches": row["matches_expected"], "status": record["analysis_status"],
                              "seconds": round(row["elapsed_seconds"], 2)}), flush=True)
            if record["audit"]["provenance"].get("analysis_error") == "model-service-unavailable":
                raise RuntimeError("Model unavailable; partial outputs retained without retry.")
    summarize(output, wall_seconds=time.monotonic() - started)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Keep validation artifacts in development results.")
    run(destination) if args.call_model else prepare(destination)
