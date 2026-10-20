"""Predeclare and run a small paired synthetic development pilot, without DVWA."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
import analyze_response as frozen
from rag_pipeline import load_catalog, local_ollama_url
import analyze_response_v1 as prototype

EXPERIMENT_ID = "response-analysis-dev-v1-20261019"
PROFILES = ("frozen-v8", "measured-pairs-v1")
INVENTORY = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, document):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def check_protected_sources():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    require(all(digest(ROOT / name) == value for name, value in inventory.items()), "A protected formal source changed.")
    return len(inventory)


def synthetic_cases():
    """Fresh measurements, predeclared labels, and no copied formal/U01 responses."""
    rng = random.Random(20261019)
    catalog = {scenario["scenario_id"]: scenario for scenario in load_catalog()["scenarios"]}
    definitions = [
        ("S1", "error-three", (1, 1, 1), "positive"),
        ("S1", "error-generic-http", (0, 0, 0), "negative"),
        ("S2", "boolean-opposed", (1, 1, 1), "positive"),
        ("S2", "boolean-both-missing", (0, 0, 0), "negative"),
        ("S3", "time-delayed", (1, 1, 1), "positive"),
        ("S3", "time-tiny-or-negative", (0, 0, 0), "negative"),
        ("S2", "boolean-mixed-one", (0, 1, 0), "inconclusive"),
        ("S3", "time-mixed-two", (1, 0, 1), "inconclusive"),
        ("S1", "error-incomplete", (1, 1), "inconclusive"),
        ("S3", "invalid-baseline", (0, 0, 0), None),
    ]
    public, private = [], []
    for index, (sid, diagnostic_name, signals, expected) in enumerate(definitions, 1):
        scenario = catalog[sid]
        observations = []

        def observation(trial, role, markers, diagnostics=None, status=200, elapsed=None):
            number = len(observations) + 1
            observations.append({
                "observation_id": f"obs-{number:03d}", "trial": trial, "role": role,
                "http_status": status, "elapsed_ms": round(rng.uniform(5, 19), 2) if elapsed is None else elapsed,
                "response_sha256": hashlib.sha256(f"synthetic-{index}-{number}-{rng.getrandbits(128)}".encode()).hexdigest(),
                "diagnostics": diagnostics or [], "content_markers": markers,
            })

        for trial, signal in enumerate(signals, 1):
            observation(trial, "baseline", ["benign_record"] if sid == "S1" else ["user_id_exists"])
            if sid == "S1":
                observation(trial, "candidate", [], ["mysql_unknown_column"] if signal else [],
                            status=500 if diagnostic_name == "error-generic-http" else 200)
            elif sid == "S2":
                observation(trial, "true_condition", ["user_id_exists"] if signal else ["user_id_missing"],
                            status=200 if signal else 404)
                observation(trial, "false_condition", ["user_id_missing"], status=404)
            else:
                control = round(rng.uniform(30, 60), 2)
                delta = rng.randint(170000, 230000) / 100 if signal else rng.randint(-1100, 1100) / 100
                markers = ["user_id_exists"] if trial == 2 else ["user_id_missing"]
                status = 200 if trial == 2 else 404
                observation(trial, "candidate", markers, status=status, elapsed=round(control + delta, 2))
                observation(trial, "no_delay_control", markers, status=status, elapsed=control)
        document = {
            "schema_version": "1.0.0", "technique": scenario["sqli_type"],
            "injection_point": {key: scenario[key] for key in ("method", "input_path", "result_path", "parameter")},
            "runtime_status": "invalid" if expected is None else "valid", "baseline_valid": expected is not None,
            "time_threshold_ms": 1500, "observations": observations,
        }
        context = {"experiment_id": EXPERIMENT_ID, "run_id": f"synthetic-{index:03d}", "attempt_id": "pilot-1",
                   "candidate_id": "candidate-001", "scenario_id": sid, "replicate": 1,
                   "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        frozen.validate_input(document)
        # Evaluator labels are checked before inference and never passed to a builder.
        confirmation = frozen.confirmation_result(document)
        derived = {"CONSISTENT_POSITIVE": "positive", "CONSISTENT_NEGATIVE": "negative",
                   "MIXED_EVIDENCE": "inconclusive", "INCOMPLETE_CONFIRMATIONS": "inconclusive",
                   "RUNTIME_INVALID": None}[confirmation["evidence_status"]]
        require(expected == derived, "A synthetic label disagrees with the protocol.")
        case_id = f"case-{index:03d}"
        public.append({"case_id": case_id, "input": document, "context": context})
        private.append({"case_id": case_id, "diagnostic_name": diagnostic_name, "expected_claim": expected})
    return public, private


def prepare(output):
    require(not output.exists(), "Use a new pilot output directory.")
    protected = check_protected_sources()
    public, private = synthetic_cases()
    requests = []
    for case in public:
        requests.append({"case_id": case["case_id"], "frozen_messages": frozen.build_messages(case["input"]),
                         "prototype": prototype.prepared_request(case["input"], seed=42)})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "inputs.json", public)
    write_json(output / "evaluation.private.json", private)
    write_json(output / "prepared-requests.json", requests)
    sources = [Path(__file__).resolve(), Path(prototype.__file__).resolve(), ROOT / "dvwa/analyze_response.py",
               ROOT / "dvwa/langchain_runtime.py", ROOT / "schemas/qwen-analysis-input.schema.json",
               ROOT / "schemas/qwen-analysis-output.schema.json", ROOT / "schemas/analysis-ledger.schema.json"]
    write_json(output / "manifest.json", {
        "scope": "synthetic-development-pilot-not-formal-not-independent-holdout", "experiment_id": EXPERIMENT_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "profiles": list(PROFILES),
        "model": prototype.MODEL, "seed": 42, "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 768},
        "case_count": len(public), "planned_model_calls": 18, "no_automatic_retry": True,
        "analysis_retrieval": "disabled-for-both-profiles", "dvwa_requests": 0,
        "protected_source_count": protected,
        "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sources},
        "artifact_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()},
    })
    print(json.dumps({"output": str(output), "status": "prepared-and-frozen", "cases": len(public),
                      "planned_model_calls": 18, "dvwa_requests": 0}), flush=True)


def run(output):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    require(not (output / "replay.jsonl").exists(), "This pilot was already started; do not overwrite or retry it.")
    require(all(digest(ROOT / name) == value for name, value in manifest["source_sha256"].items()), "Pilot source changed after freeze.")
    require(all(digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Pilot inputs changed after freeze.")
    check_protected_sources()
    with urlopen(local_ollama_url() + "/api/tags", timeout=5) as response:
        models = json.load(response)["models"]
    current = next((model for model in models if model["name"] == prototype.MODEL), None)
    require(current is not None, "The preinstalled Qwen model is not available.")
    write_json(output / "runtime.json", {"model": prototype.MODEL, "digest": current["digest"], "details": current.get("details")})
    cases = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
    labels = {case["case_id"]: case for case in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    rows = []
    started = time.monotonic()
    with (output / "replay.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for index, case in enumerate(cases):
            # Alternate first profile to reduce a fixed warmup/order advantage.
            for profile in PROFILES if index % 2 == 0 else reversed(PROFILES):
                print(json.dumps({"case_id": case["case_id"], "profile": profile, "status": "starting"}), flush=True)
                call_started = time.monotonic()
                analyzer = frozen.analyze_with_qwen if profile == PROFILES[0] else prototype.analyze_with_qwen
                record = analyzer(copy.deepcopy(case["input"]), copy.deepcopy(case["context"]), seed=42)
                expected = labels[case["case_id"]]["expected_claim"]
                row = {"case_id": case["case_id"], "profile": profile, "expected_claim": expected,
                       "matches_expected": record["system_claim"] == expected,
                       "elapsed_seconds": time.monotonic() - call_started, "record": record}
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                rows.append(row)
                print(json.dumps({"case_id": case["case_id"], "profile": profile, "actual": record["system_claim"],
                                  "expected": expected, "matches": row["matches_expected"],
                                  "analysis_status": record["analysis_status"],
                                  "seconds": round(row["elapsed_seconds"], 2)}), flush=True)
                if record["audit"]["provenance"].get("analysis_error") == "model-service-unavailable":
                    raise RuntimeError("Model service unavailable; partial results retained without retry.")
    summaries = []
    for profile in PROFILES:
        selected = [r for r in rows if r["profile"] == profile]
        valid = [r for r in selected if r["expected_claim"] is not None]
        negative = [r for r in valid if r["expected_claim"] == "negative"]
        positive = [r for r in valid if r["expected_claim"] == "positive"]
        summaries.append({
            "profile": profile, "cases": len(selected), "matches": sum(r["matches_expected"] for r in selected),
            "valid_cases": len(valid), "valid_matches": sum(r["matches_expected"] for r in valid),
            "analysis_errors": sum(r["record"]["analysis_status"] == "analysis_error" for r in valid),
            "false_positive_on_three_negative_fixtures": sum(r["record"]["system_claim"] == "positive" for r in negative),
            "false_negative_on_three_positive_fixtures": sum(r["record"]["system_claim"] == "negative" for r in positive),
            "abstention_on_binary_fixtures": sum(r["record"]["system_claim"] == "inconclusive" for r in negative + positive),
            "warning_counts": dict(Counter(w for r in selected for w in r["record"]["analysis_warnings"])),
            "total_elapsed_seconds": sum(r["elapsed_seconds"] for r in selected),
            "median_valid_case_seconds": statistics.median(r["elapsed_seconds"] for r in valid),
        })
    protected = check_protected_sources()
    write_json(output / "summary.json", {
        "scope": manifest["scope"], "experiment_id": EXPERIMENT_ID, "model": prototype.MODEL,
        "model_digest": current["digest"], "manifest_sha256": digest(output / "manifest.json"),
        "dvwa_requests": 0, "formal_metrics_recomputed": False, "protected_sources_unchanged": protected,
        "total_wall_seconds": time.monotonic() - started, "profiles": summaries,
        "results": [{"case_id": r["case_id"], "profile": r["profile"], "expected_claim": r["expected_claim"],
                     "actual_claim": r["record"]["system_claim"], "matches": r["matches_expected"],
                     "analysis_status": r["record"]["analysis_status"]} for r in rows],
    })
    print(json.dumps({"status": "completed", "summary": str(output / "summary.json"), "profiles": summaries}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true", help="Run the already frozen development pilot using local Qwen only.")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Keep pilot artifacts in results/raw/development.")
    run(destination) if args.call_model else prepare(destination)
