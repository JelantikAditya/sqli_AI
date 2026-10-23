"""Audit the saved cause of the P4 A/R2/S12 FPR abstention."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from analyze_response import confirmation_result, trial_rule_signals
from experiment_dataset import load_runs
from run_decision_policy import RUN_DECISION_POLICY


RUN_DIR = ROOT / "results/raw/formal/poolside-laguna-p4-recovery1-20261023"
UNIT_ID = "poolside-laguna-p4-20261023-a-s12-r2"
METRICS = ROOT / "results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01/metrics-P4-VAL01.json"
OUTPUT = ROOT / "docs/evidence/poolside-p4-a-r2-s12-fpr-abstention-diagnostic-2026-10-23.json"
THRESHOLD = Decimal("1500")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def audit():
    ledger_path = RUN_DIR / "ledger.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    completion = next(event for event in reversed(events)
                      if event.get("unit_id") == UNIT_ID
                      and event.get("event_type") == "attempt_completed")
    adaptive_path = (RUN_DIR / completion["adaptive_result_path"]).resolve()
    require(adaptive_path.is_relative_to(RUN_DIR.resolve()),
            "Adaptive result path escaped the source run directory.")
    adaptive_sha = sha256(adaptive_path)
    require(adaptive_sha == completion["adaptive_result_sha256"],
            "Saved adaptive result failed its ledger hash check.")

    adaptive = json.loads(adaptive_path.read_text(encoding="utf-8"))
    matches = [record for record in adaptive["candidate_records"]
               if record["context"].get("candidate_id") == "candidate-004"]
    require(len(matches) == 1, "Expected exactly one candidate-004 analysis.")
    record = matches[0]
    require(record["context"]["condition_id"] == "A"
            and record["context"]["scenario_id"] == "S12"
            and record["context"]["replicate"] == 2,
            "Candidate context does not identify A/S12/R2.")

    evidence = record["evidence"]
    require(evidence["runtime_status"] == "valid" and evidence["baseline_valid"],
            "Saved evidence is not a valid complete runtime observation.")
    require(evidence["technique"] == "time-based blind"
            and Decimal(str(evidence["time_threshold_ms"])) == THRESHOLD,
            "Saved time-based technique or threshold differs from the protocol.")

    by_trial = {}
    for observation in evidence["observations"]:
        by_trial.setdefault(observation["trial"], {})[observation["role"]] = observation
    require(set(by_trial) == {1, 2, 3}, "Saved evidence does not contain all three trials.")

    trial_signals = trial_rule_signals(evidence)
    trial_details = []
    for trial in (1, 2, 3):
        group = by_trial[trial]
        candidate = group["candidate"]
        control = group["no_delay_control"]
        candidate_markers = set(candidate["content_markers"])
        control_markers = set(control["content_markers"])
        delta = Decimal(str(candidate["elapsed_ms"])) - Decimal(str(control["elapsed_ms"]))
        valid_blind_status = lambda row: (
            row["http_status"] == 200 or
            (row["http_status"] == 404 and set(row["content_markers"]) == {"user_id_missing"})
        )
        require(candidate_markers == control_markers
                and candidate_markers in ({"user_id_exists"}, {"user_id_missing"})
                and valid_blind_status(candidate) and valid_blind_status(control)
                and not candidate["diagnostics"] and not control["diagnostics"],
                f"Trial {trial} lacks a valid matched candidate/control pair.")
        expected_positive = delta >= THRESHOLD
        require(trial_signals[trial] == expected_positive,
                f"Project rule evaluator disagrees with the independently shown delta for trial {trial}.")
        trial_details.append({
            "trial": trial,
            "candidate_elapsed_ms": str(Decimal(str(candidate["elapsed_ms"]))),
            "no_delay_control_elapsed_ms": str(Decimal(str(control["elapsed_ms"]))),
            "candidate_minus_control_ms": str(delta),
            "threshold_ms": str(THRESHOLD),
            "candidate_http_status": candidate["http_status"],
            "control_http_status": control["http_status"],
            "matched_content_markers": sorted(candidate_markers),
            "candidate_and_control_have_sql_diagnostics": False,
            "executor_trial_outcome": "positive" if trial_signals[trial] else "negative",
            "model_trial_outcome": None,
        })

    assessments = {item["trial"]: item["outcome"]
                   for item in record["model_output"]["trial_assessments"]}
    for item in trial_details:
        item["model_trial_outcome"] = assessments[item["trial"]]
    require([item["executor_trial_outcome"] for item in trial_details]
            == ["negative", "negative", "negative"],
            "Expected the saved executor evidence to be consistently negative.")
    require([item["model_trial_outcome"] for item in trial_details]
            == ["negative", "negative", "positive"],
            "The saved model assessments differ from the reviewed mismatch.")
    require(record["system_claim"] == "inconclusive"
            and record["evidence_status"] == "CONSISTENT_NEGATIVE"
            and {"trial_assessment_evidence_mismatch", "model_claim_evidence_mismatch"}
            <= set(record["analysis_warnings"]),
            "The saved candidate claim or mismatch warnings differ from the reviewed blocker.")

    loaded = load_runs(RUN_DIR)
    source_run = next(run for run in loaded if run["unit_id"] == UNIT_ID)
    require(source_run["analysis_summary"]["system_decision"] == "inconclusive",
            "Run-level decision no longer matches the saved candidate abstention.")

    metric_payload = json.loads(METRICS.read_text(encoding="utf-8"))
    withheld = metric_payload["fpr"]["withheld_replicate_detail"]
    a_r2 = next(row for row in metric_payload["fpr"]["condition_replicates"]
                if row["condition_id"] == "A" and row["replicate"] == 2)
    require(withheld["condition_id"] == "A" and withheld["scenario_id"] == "S12"
            and withheld["replicate"] == 2 and not a_r2["eligible"] and a_r2["fpr"] is None,
            "VAL-01 metrics no longer withhold A/R2 due to S12.")

    return {
        "schema": "poolside-p4-fpr-abstention-diagnostic-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "condition_id": "A", "scenario_id": "S12", "replicate": 2,
            "candidate_id": "candidate-004", "technique": "time-based blind",
        },
        "source_integrity": {
            "execution_ledger_sha256": sha256(ledger_path),
            "adaptive_result_sha256": adaptive_sha,
            "adaptive_result_sha256_matches_ledger": True,
            "val01_metrics_sha256": sha256(METRICS),
        },
        "recomputed_from_saved_evidence_only": True,
        "trial_comparisons": trial_details,
        "finding": {
            "executor_evidence_status": record["evidence_status"],
            "model_system_claim": record["system_claim"],
            "analysis_warnings": sorted(record["analysis_warnings"]),
            "mismatch_confirmed": True,
            "parser_or_delta_calculation_error_found": False,
            "run_decision_policy_id": RUN_DECISION_POLICY["policy_id"],
            "run_decision": source_run["analysis_summary"]["system_decision"],
            "policy_effect": RUN_DECISION_POLICY["fpr_inconclusive"],
            "formal_fpr_a_r2": None,
            "formal_fpr_a_eligible": metric_payload["fpr"]["eligible"],
            "required_to_change_formal_result": (
                "A separately authorized protocol amendment or new eligible formal observation; "
                "the saved model claim and metric artifacts are not rewritten by this audit."
            ),
        },
        "activity_counts": {"api_requests": 0, "dvwa_requests": 0, "database_resets": 0},
    }


if __name__ == "__main__":
    result = audit()
    write_new(OUTPUT, result)
    print(json.dumps({
        "status": "diagnostic_confirmed_no_metric_rewrite",
        "output": str(OUTPUT),
        "trial_deltas_ms": [row["candidate_minus_control_ms"] for row in result["trial_comparisons"]],
        "model_vs_executor": [
            [row["model_trial_outcome"], row["executor_trial_outcome"]]
            for row in result["trial_comparisons"]
        ],
        "formal_fpr_a_eligible": result["finding"]["formal_fpr_a_eligible"],
    }, indent=2))
