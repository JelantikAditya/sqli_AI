"""Predeclare a shadow agreement gate on new cases, with an immutable v2 replay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import analyze_response_v2 as model
import response_analysis_pilot as pilot
import verify_response_v3 as gate

ROOT = pilot.ROOT
EXPERIMENT_ID = "response-analysis-hybrid-v3-20261019"
V2_DATA = ROOT / "results/raw/development/response-analysis-v2-20261019"


def new_cases():
    """Hand-declared expected outcomes remain separate from measurements and verifier."""
    rng = random.Random(2026101903)
    catalog = {s["scenario_id"]: s for s in pilot.load_catalog()["scenarios"]}
    definitions = []
    for sid in ("S1", "S2", "S3"):
        definitions.extend([
            (sid, "positive", (1, 1, 1), (1, 2, 3), "positive"),
            (sid, "negative", (0, 0, 0), (1, 2, 3), "negative"),
            (sid, "mixed-one", (1, 0, 0), (1, 2, 3), "inconclusive"),
            (sid, "mixed-two", (0, 1, 1), (1, 2, 3), "inconclusive"),
            (sid, "incomplete", (0,) if sid == "S3" else (1, 1),
             (2,) if sid == "S3" else (1, 3) if sid == "S2" else (1, 2), "inconclusive"),
        ])
    definitions.extend([
        ("S3", "decimal-exact-threshold", (1, 1, 1), (1, 2, 3), "positive"),
        ("S3", "decimal-below-threshold", (0, 0, 0), (1, 2, 3), "negative"),
        ("S3", "unmatched-control", (0, 0, 0), (1, 2, 3), "negative"),
        ("S1", "preexisting-diagnostic", (0, 0, 0), (1, 2, 3), "negative"),
        ("S2", "invalid-blind-status", (0, 0, 0), (1, 2, 3), "negative"),
        ("S3", "baseline-invalid", (0, 0, 0), (1, 2, 3), None),
    ])
    public, labels = [], []
    for index, (sid, name, signals, trials, expected) in enumerate(definitions, 1):
        scenario = catalog[sid]
        observations = []

        def observe(trial, role, *, markers=None, diagnostics=None, status=200, elapsed=None):
            number = len(observations) + 1
            observations.append({
                "observation_id": f"obs-{number:03d}", "trial": trial, "role": role,
                "http_status": status, "elapsed_ms": round(rng.uniform(3, 17), 2) if elapsed is None else elapsed,
                "response_sha256": hashlib.sha256(f"v3-{index}-{number}-{rng.getrandbits(128)}".encode()).hexdigest(),
                "diagnostics": diagnostics or [], "content_markers": markers or [],
            })

        for trial, signal in zip(trials, signals):
            existing = ["mysql_unknown_column"] if name == "preexisting-diagnostic" else []
            observe(trial, "baseline", markers=["benign_record"] if sid == "S1" else ["user_id_exists"], diagnostics=existing)
            if sid == "S1":
                observe(trial, "candidate", diagnostics=existing or (["mysql_xpath_error"] if signal else []), status=500)
            elif sid == "S2":
                positive_markers = bool(signal) or name == "invalid-blind-status"
                observe(trial, "true_condition", markers=["user_id_exists"] if positive_markers else ["user_id_missing"],
                        status=404 if name == "invalid-blind-status" or not positive_markers else 200)
                observe(trial, "false_condition", markers=["user_id_missing"], status=404)
            else:
                control = round(rng.uniform(40, 70), 2)
                delta = rng.randint(1750, 2200) if signal else -2
                if name == "decimal-exact-threshold":
                    control, delta = 548.2, 1500
                elif name == "decimal-below-threshold":
                    control, delta = 0.07, 1499.99
                elif name == "unmatched-control":
                    delta = 2500
                # Positive timing controls deliberately include valid HTTP 404/missing.
                missing = name not in ("decimal-exact-threshold", "decimal-below-threshold", "unmatched-control")
                markers, status = (["user_id_missing"], 404) if missing else (["user_id_exists"], 200)
                observe(trial, "candidate", markers=markers, status=status, elapsed=round(control + delta, 2))
                observe(trial, "no_delay_control", markers=["user_id_missing"] if name == "unmatched-control" else markers,
                        status=404 if name == "unmatched-control" else status, elapsed=control)
        document = {
            "schema_version": "1.0.0", "technique": scenario["sqli_type"],
            "injection_point": {key: scenario[key] for key in ("method", "input_path", "result_path", "parameter")},
            "runtime_status": "valid" if expected is not None else "invalid", "baseline_valid": expected is not None,
            "time_threshold_ms": 1500, "observations": observations,
        }
        model.frozen.validate_input(document)
        case_id = f"hybrid-{index:03d}"
        context = {"experiment_id": EXPERIMENT_ID, "run_id": case_id, "attempt_id": "shadow-1",
                   "candidate_id": "candidate-001", "scenario_id": sid, "replicate": 1,
                   "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        public.append({"case_id": case_id, "dataset": "new-synthetic-validation", "input": document, "context": context})
        labels.append({"case_id": case_id, "diagnostic_name": name, "expected_claim": expected,
                       "expected_trials": {str(t): "positive" if s else "negative" for t, s in zip(trials, signals)}})
    return public, labels


def history_inventory():
    inventory = {}
    for version in ("v1", "v2"):
        folder = ROOT / f"results/processed/response-analysis-dev-{version}-20261019"
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        for name, value in provenance["local_source_sha256"].items():
            inventory[f"{provenance['source_directory']}/{name}"] = value
    pilot.require(all(pilot.digest(ROOT / name) == value for name, value in inventory.items()), "Historical v1/v2 artifact changed.")
    return inventory


def prepare(output):
    pilot.require(not output.exists(), "Use a new v3 output directory.")
    protected, history = pilot.check_protected_sources(), history_inventory()
    cases, labels = new_cases()
    pilot.require(Counter(label["expected_claim"] for label in labels) ==
                  Counter({"positive": 4, "negative": 7, "inconclusive": 9, None: 1}), "Predeclared fixture counts changed.")
    requests = [{"case_id": case["case_id"], "prepared": model.prepared_request(case["input"])} for case in cases]
    for case, step in zip(cases, requests):
        pilot.require(json.loads(step["prepared"]["request"]["messages"][1]["content"]) == model.v1.paired_view(case["input"]),
                      "Unexpected model input or evaluator metadata.")
    old_rows = [json.loads(line) for line in (V2_DATA / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    replay = [{"case_id": row["case_id"], "dataset": row["dataset"], "expected_claim": row["expected_claim"],
               "expected_trials": None, "hybrid": gate.combine(row["record"]), "elapsed_seconds": 0}
              for row in old_rows if row["profile"] == "explicit-contract-v2"]
    output.mkdir(parents=True, exist_ok=False)
    pilot.write_json(output / "inputs.json", cases)
    pilot.write_json(output / "evaluation.private.json", labels)
    pilot.write_json(output / "prepared-requests.json", requests)
    with (output / "regression.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for row in replay:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    sources = [Path(__file__), Path(gate.__file__), Path(model.__file__), Path(model.v1.__file__), Path(pilot.__file__),
               ROOT / "development/audit_hybrid_v3.py",
               ROOT / "development/test_verify_response_v3.py", ROOT / "dvwa/analyze_response.py",
               ROOT / "dvwa/confirmation_policy.py", ROOT / "dvwa/langchain_runtime.py", ROOT / "dvwa/rag_pipeline.py",
               ROOT / "dvwa/run_decision_policy.py", ROOT / "dvwa/experiment_scenarios.json",
               ROOT / "schemas/qwen-analysis-input.schema.json", ROOT / "schemas/qwen-analysis-output.schema.json",
               ROOT / "schemas/analysis-ledger.schema.json"]
    expected_digest = json.loads((V2_DATA / "runtime.json").read_text(encoding="utf-8"))["digest"]
    pilot.write_json(output / "manifest.json", {
        "scope": "development-shadow-hybrid-not-independent-holdout-not-formal", "experiment_id": EXPERIMENT_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model": model.MODEL, "expected_model_digest": expected_digest,
        "options": requests[0]["prepared"]["request"]["options"], "raw_model_prompt_unchanged_from_v2": True,
        "combination_policy": gate.COMBINATION_POLICY, "verifier_version": gate.VERIFIER_VERSION,
        "combination_table": {"matching_binary": "retain_binary", "conflicting_binary": "inconclusive",
                              "either_inconclusive": "inconclusive", "model_error": "inconclusive",
                              "verifier_invalid": "not_evaluable"},
        "new_cases": len(cases), "valid_cases": 20, "planned_model_calls": 20, "runtime_invalid_skips": 1,
        "opened_regression_records": len(replay), "dvwa_requests": 0, "retrieval": "disabled",
        "no_automatic_retry": True, "adaptation_after_first_inference": False,
        "development_checks": ["preserve-all-raw-records", "independent-verifier-matches-predeclared-fixtures",
                               "no-combined-positive-without-both-positive", "no-combined-negative-without-both-negative"],
        "empirical_readiness_criteria": {"combined_positive_controls_correct": "4/4", "negative_fixture_binary_coverage": "7/7",
                                         "combined_verdict_matches": "20/20", "analysis_errors": 0},
        "automatic_promotion_to_formal": False, "primary_formal_fpr_recomputed": False,
        "labels": "hand-declared-outside-model-and-verifier; fixture-conformance-not-independent-accuracy-proof",
        "protected_source_count": protected, "history_sha256": history,
        "source_sha256": {p.resolve().relative_to(ROOT).as_posix(): pilot.digest(p) for p in sources},
        "artifact_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
    })
    print(json.dumps({"status": "prepared-and-frozen", "new_cases": len(cases), "model_calls": 20,
                      "regression_records": len(replay), "dvwa_requests": 0}), flush=True)


def decision(row, layer):
    return row["hybrid"]["llm_record"]["system_claim"] if layer == "raw_qwen_v2" else row["hybrid"][layer]["decision"]


def metrics(rows, layer):
    valid = [r for r in rows if r["expected_claim"] is not None]
    positive = [r for r in valid if r["expected_claim"] == "positive"]
    negative = [r for r in valid if r["expected_claim"] == "negative"]
    uncertain = [r for r in valid if r["expected_claim"] == "inconclusive"]
    binary = positive + negative
    matches = lambda selected: sum(decision(r, layer) == r["expected_claim"] for r in selected)
    covered = lambda selected: sum(decision(r, layer) in ("positive", "negative") for r in selected)
    return {
        "layer": layer, "valid_cases": len(valid), "verdict_matches": matches(valid),
        "positive_fixtures": len(positive), "negative_fixtures": len(negative), "inconclusive_fixtures": len(uncertain),
        "correct_positive": matches(positive), "correct_negative": matches(negative), "correct_inconclusive": matches(uncertain),
        "false_positive_on_negative_fixtures": sum(decision(r, layer) == "positive" for r in negative),
        "false_negative_on_positive_fixtures": sum(decision(r, layer) == "negative" for r in positive),
        "abstention_on_positive_fixtures": sum(decision(r, layer) == "inconclusive" for r in positive),
        "abstention_on_negative_fixtures": sum(decision(r, layer) == "inconclusive" for r in negative),
        "binary_decisions_on_inconclusive_fixtures": covered(uncertain),
        "binary_decisions": covered(valid), "binary_fixture_decisions": covered(binary), "binary_fixture_total": len(binary),
        "positive_fixture_binary_coverage_count": covered(positive), "negative_fixture_binary_coverage_count": covered(negative),
        "binary_decision_coverage": covered(valid) / len(valid) if valid else None,
        "runtime_invalid_cases": len(rows) - len(valid),
    }


def summarize(output, wall_seconds=None):
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    regression = [json.loads(line) for line in (output / "regression.jsonl").read_text(encoding="utf-8").splitlines()]
    pilot.require(len(rows) == 21, "New evaluation incomplete; retain partial outputs without retry.")
    groups = [{"dataset": "new-synthetic-validation", "profiles": [metrics(rows, layer) for layer in ("raw_qwen_v2", "verification", "combined")]}]
    for dataset in ("new-validation", "opened-v1-regression"):
        selected = [r for r in regression if r["dataset"] == dataset]
        groups.append({"dataset": f"opened-v2-replay:{dataset}",
                       "profiles": [metrics(selected, layer) for layer in ("raw_qwen_v2", "verification", "combined")]})
    combined = groups[0]["profiles"][2]
    errors = sum(r["hybrid"]["llm_record"]["analysis_status"] == "analysis_error" for r in rows)
    criteria = {"positive_controls_4_of_4": combined["correct_positive"] == 4,
                "negative_binary_coverage_7_of_7": combined["negative_fixture_binary_coverage_count"] == 7,
                "combined_verdicts_20_of_20": combined["verdict_matches"] == 20, "no_analysis_errors": errors == 0}
    pilot.write_json(output / "summary.json", {
        "scope": "development-shadow-hybrid-not-independent-holdout-not-formal", "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": pilot.digest(output / "manifest.json"), "groups": groups,
        "model_calls": sum("raw_model_content" in r["hybrid"]["llm_record"]["audit"]["provenance"] for r in rows),
        "new_records": len(rows), "regression_records": len(regression), "total_wall_seconds": wall_seconds,
        "analysis_errors": errors, "empirical_criterion_results": criteria,
        "all_empirical_readiness_criteria_met": all(criteria.values()), "formal_metrics_recomputed": False,
        "dvwa_requests": 0, "raw_model_claims_replaced": False, "automatic_promotion_to_formal": False,
        "protected_sources_unchanged": pilot.check_protected_sources(), "history_artifacts_unchanged": len(history_inventory()),
        "results": [{"case_id": r["case_id"], "expected_claim": r["expected_claim"],
                     "raw_claim": decision(r, "raw_qwen_v2"), "verifier_decision": decision(r, "verification"),
                     "combined_decision": decision(r, "combined"), "combined_reason_code": r["hybrid"]["combined"]["reason_code"]}
                    for r in rows],
    })
    print(json.dumps({"status": "completed", "new_profiles": groups[0]["profiles"], "readiness": criteria}), flush=True)


def run(output):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    pilot.require(not (output / "replay.jsonl").exists(), "Already started; no automatic retry or overwrite.")
    for key in ("source_sha256", "history_sha256"):
        pilot.require(all(pilot.digest(ROOT / name) == value for name, value in manifest[key].items()), "Pinned source/history changed.")
    pilot.require(all(pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Frozen artifact changed.")
    pilot.check_protected_sources()
    with build_opener(ProxyHandler({})).open(pilot.local_ollama_url() + "/api/tags", timeout=5) as response:
        models = json.load(response)["models"]
    current = next((m for m in models if m["name"] == model.MODEL), None)
    pilot.require(current is not None and current["digest"] == manifest["expected_model_digest"], "Qwen digest differs from v2.")
    pilot.write_json(output / "runtime.json", {"model": model.MODEL, "digest": current["digest"], "details": current.get("details")})
    cases = {c["case_id"]: c for c in json.loads((output / "inputs.json").read_text(encoding="utf-8"))}
    labels = {r["case_id"]: r for r in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    steps = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    with (output / "replay.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for step in steps:
            case = cases[step["case_id"]]
            print(json.dumps({"case_id": case["case_id"], "status": "starting"}), flush=True)
            call_started = time.monotonic()
            raw = model.analyze_with_qwen(copy.deepcopy(case["input"]), copy.deepcopy(case["context"]), prepared=step["prepared"])
            hybrid = gate.combine(raw)
            label = labels[case["case_id"]]
            row = {"case_id": case["case_id"], "dataset": case["dataset"], "expected_claim": label["expected_claim"],
                   "expected_trials": label["expected_trials"], "hybrid": hybrid, "elapsed_seconds": time.monotonic() - call_started}
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            print(json.dumps({"case_id": case["case_id"], "expected": label["expected_claim"], "raw": raw["system_claim"],
                              "verifier": hybrid["verification"]["decision"], "combined": hybrid["combined"]["decision"],
                              "seconds": round(row["elapsed_seconds"], 2)}), flush=True)
            if raw["audit"]["provenance"].get("analysis_error") == "model-service-unavailable":
                raise RuntimeError("Model service unavailable; partial output retained without retry.")
    summarize(output, time.monotonic() - started)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Use development result directory.")
    run(destination) if args.call_model else prepare(destination)
