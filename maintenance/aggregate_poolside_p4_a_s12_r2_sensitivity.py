"""Rebuild the post-result P4 A/S12/R2 sensitivity FPR without altering U05."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
sys.path.insert(0, str(ROOT / "dvwa"))

import run_poolside_laguna_p4_a_s12_r2_amendment as runner
from aggregate_metrics import aggregate
from experiment_dataset import load_runs


SOURCE_REPLICATE3_DIR = ROOT / "results/raw/formal/poolside-laguna-p4-replicate3-20261023"
PRIMARY_METRICS_PATH = ROOT / "results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01/metrics-P4-VAL01.json"
RESULT_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-sensitivity-result-2026-10-23.json"
REPORT_PATH = ROOT / "docs/poolside-laguna-p4-a-s12-r2-sensitivity-result-2026-10-23.md"
SOURCE_UNIT_ID = "poolside-laguna-p4-20261023-a-s12-r2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8-sig") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_hashes(completion: dict) -> dict[str, str]:
    adaptive = Path(completion["adaptive_result_path"]).resolve()
    validation = Path(completion["validation_log_path"]).resolve()
    batch = Path(completion["runner_batch_path"]).resolve()
    required_paths = {
        "recovery1_ledger": runner.SOURCE_LEDGER_PATH,
        "replicate3_ledger": SOURCE_REPLICATE3_DIR / "ledger.jsonl",
        "primary_val01_metrics": PRIMARY_METRICS_PATH,
        "original_blocker_diagnostic": runner.SOURCE_DIAGNOSTIC_PATH,
        "frozen_package": runner.PACKAGE_PATH,
        "method_approval": runner.METHOD_APPROVAL_PATH,
        "freeze_approval": runner.FREEZE_APPROVAL_PATH,
        "execution_proposal": ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-execution-proposal-2026-10-23.json",
        "execution_approval": runner.EXECUTION_APPROVAL_PATH,
        "supplement_ledger": runner.SUPPLEMENT_OUTPUT / "ledger.jsonl",
        "supplement_result": runner.SUPPLEMENT_OUTPUT / "poolside-p4-a-s12-r2-amendment-result.json",
        "supplement_runtime_snapshot": runner.SUPPLEMENT_OUTPUT / "poolside-p4-a-s12-r2-amendment-runtime.snapshot.json",
        "supplement_adaptive_result": adaptive,
        "supplement_validation_log": validation,
        "supplement_candidate_batch": batch,
        "discovery_report": ROOT / "results/raw/formal-discovery/poolside-laguna-p4-20261023/replicate-2/impossible/zap-discovery.normalized.json",
    }
    for label, path in required_paths.items():
        require(Path(path).is_file(), f"Missing evidence file for {label}.")
    require(adaptive.is_relative_to(runner.SUPPLEMENT_OUTPUT.resolve())
            and validation.is_relative_to(runner.SUPPLEMENT_OUTPUT.resolve())
            and batch.is_relative_to(runner.SUPPLEMENT_OUTPUT.resolve()),
            "Supplement evidence path escaped its output directory.")
    return {label: sha256(path) for label, path in required_paths.items()}


def select_fpr_units(runs: list[dict]) -> list[dict]:
    return [run for run in runs
            if run["condition_id"] in {"A", "B"}
            and run["scenario_id"] in {"S10", "S11", "S12"}
            and run["status"] == "completed"]


def build_report() -> tuple[dict, str]:
    require(not RESULT_PATH.exists() and not REPORT_PATH.exists(),
            "Refusing to overwrite an existing sensitivity result or report.")

    package_hash = sha256(runner.PACKAGE_PATH)
    package = read_json(runner.PACKAGE_PATH)
    artifacts = runner.source_artifacts()
    expected_artifacts = package.get("artifact_sha256", {})
    require(set(expected_artifacts) == set(artifacts)
            and all(expected_artifacts[name] == sha256(path)
                    for name, path in artifacts.items()),
            "One or more hash-bound package artifacts changed after freeze.")
    runner.validate_approval(runner.METHOD_APPROVAL_PATH, kind="method", package_hash=package_hash)
    runner.validate_approval(runner.FREEZE_APPROVAL_PATH, kind="freeze", package_hash=package_hash)
    runner.validate_approval(runner.EXECUTION_APPROVAL_PATH, kind="execution", package_hash=package_hash)
    diagnostic = read_json(runner.SOURCE_DIAGNOSTIC_PATH)
    runner.verify_original_blocker(diagnostic)
    runner.base.verify_plan_inputs(require_frozen=True)

    execution_proposal = read_json(
        ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-execution-proposal-2026-10-23.json")
    execution_approval = read_json(runner.EXECUTION_APPROVAL_PATH)
    require(execution_approval.get("execution_proposal_sha256") == sha256(
        ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-execution-proposal-2026-10-23.json"),
        "Execution approval no longer binds the approved execution proposal.")
    require(execution_proposal.get("maximum_spend_usd") == 0
            and execution_proposal.get("cost_enforcement_disclosure", {}).get(
                "local_hard_dollar_cap_available") is False,
            "Execution proposal cost disclosure is missing or changed.")

    recovery1_runs = load_runs(runner.SOURCE_RUN_DIR)
    replicate3_runs = load_runs(SOURCE_REPLICATE3_DIR)
    source_fpr_runs = select_fpr_units(recovery1_runs + replicate3_runs)
    require(len(source_fpr_runs) == 18,
            "Expected 18 completed A/B negative-scenario units across source R1/R2 and R3 ledgers.")
    original = [run for run in source_fpr_runs if run["unit_id"] == SOURCE_UNIT_ID]
    require(len(original) == 1 and original[0]["analysis_summary"]["system_decision"] == "inconclusive",
            "The original complete-but-inconclusive A/S12/R2 source unit changed.")

    primary_metrics = read_json(PRIMARY_METRICS_PATH)
    primary_fpr = primary_metrics.get("fpr", {})
    baseline_fpr = aggregate(source_fpr_runs, []) ["fpr"]
    metric_keys = ("condition_id", "replicate", "FP", "TN", "unresolved_scenarios",
                   "decision_coverage", "eligible", "reason", "fpr")
    for row in baseline_fpr["condition_replicates"]:
        saved = next((item for item in primary_fpr.get("condition_replicates", [])
                      if item.get("condition_id") == row["condition_id"]
                      and item.get("replicate") == row["replicate"]), None)
        require(saved is not None and {key: row.get(key) for key in metric_keys}
                == {key: saved.get(key) for key in metric_keys},
                "Reconstructed original FPR rows do not exactly match frozen VAL-01.")

    supplement_runs = load_runs(runner.SUPPLEMENT_OUTPUT)
    require(len(supplement_runs) == 1, "Supplement must contain exactly one run unit.")
    supplement = supplement_runs[0]
    require((supplement["condition_id"], supplement["scenario_id"], supplement["replicate"])
            == ("A", "S12", 2)
            and supplement["status"] == "completed"
            and supplement["metric_eligible"] is True,
            "Supplement is not a completed metric-eligible A/S12/R2 unit.")

    events = [json.loads(line) for line in (runner.SUPPLEMENT_OUTPUT / "ledger.jsonl")
              .read_text(encoding="utf-8").splitlines() if line.strip()]
    completion = next(event for event in reversed(events)
                      if event.get("event_type") == "attempt_completed")
    require(completion.get("generated_candidate_count") == 10
            and completion.get("unique_candidate_count") == 10
            and completion.get("duplicate_candidate_count") == 0
            and completion.get("budget_complete") is True
            and completion.get("metric_eligible") is True
            and completion.get("system_decision") == "negative"
            and completion.get("database_reset_performed") is True
            and completion.get("api_request_count") == 24
            and completion.get("attempt_number") == 1
            and completion.get("retry_of_attempt_id") is None,
            "Supplement ledger violates approved completeness, budget, reset, or no-retry controls.")

    adaptive_path = Path(completion["adaptive_result_path"])
    adaptive = read_json(adaptive_path)
    run_summary = adaptive.get("run_summary", {})
    require(run_summary.get("candidate_count") == 10
            and run_summary.get("valid_executed_count") == 10
            and run_summary.get("analysis_completed_count") == 10
            and run_summary.get("system_positive_count") == 0
            and run_summary.get("inconclusive_count") == 0
            and run_summary.get("runtime_invalid_count") == 0
            and run_summary.get("system_decision") == "negative",
            "Supplement adaptive result does not support the negative run decision.")
    candidate_records = adaptive.get("candidate_records", [])
    require(len(candidate_records) == 10
            and all(item.get("system_claim") == "negative"
                    and item.get("evidence_status") == "CONSISTENT_NEGATIVE"
                    and not item.get("analysis_warnings") for item in candidate_records),
            "Candidate-level claims or evidence differ from the approved sensitivity result.")

    sensitivity_runs = [run for run in source_fpr_runs if run["unit_id"] != SOURCE_UNIT_ID]
    sensitivity_runs += supplement_runs
    require(len(sensitivity_runs) == 18, "Sensitivity matrix must retain 18 unique FPR units.")
    sensitivity_fpr = aggregate(sensitivity_runs, []) ["fpr"]
    fpr_a = next(row for row in sensitivity_fpr["summary"] if row["condition_id"] == "A")
    fpr_b = next(row for row in sensitivity_fpr["summary"] if row["condition_id"] == "B")
    require(sensitivity_fpr["eligible"] is True
            and fpr_a == {"condition_id": "A", "mean": 0.0, "sample_sd": 0.0, "n": 3, "eligible": True}
            and fpr_b == {"condition_id": "B", "mean": 0.0, "sample_sd": 0.0, "n": 3, "eligible": True},
            "Sensitivity FPR does not match the expected all-negative complete matrix.")

    withheld = primary_fpr.get("withheld_replicate_detail", {})
    require(not primary_fpr.get("eligible")
            and withheld.get("scenario_id") == "S12"
            and withheld.get("replicate") == 2
            and withheld.get("run_decision") == "inconclusive",
            "Frozen primary VAL-01 no longer withholds the original A/R2 result.")

    result_path = runner.SUPPLEMENT_OUTPUT / "poolside-p4-a-s12-r2-amendment-result.json"
    result_summary = read_json(result_path)
    http_statuses = {}
    api_results = list(runner.SUPPLEMENT_OUTPUT.glob("attempts/**/api-calls/*/result.json"))
    for path in api_results:
        response = read_json(path)
        response_result = response.get("result", {})
        key = str(response_result.get("http_status", "missing"))
        http_statuses[key] = http_statuses.get(key, 0) + 1
        require(response_result.get("status") == "ok" and key == "200",
                "One or more provider API calls did not return HTTP 200.")
    require(len(api_results) == completion["api_request_count"] == result_summary["api_calls_used"],
            "API-call artifact count differs from ledger or runner summary.")

    hashes = source_hashes(completion)
    report = {
        "schema": "poolside-laguna-p4-a-s12-r2-sensitivity-result-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "completed-post-result-sensitivity-only",
        "amendment_id": runner.AMENDMENT_ID,
        "package_sha256": package_hash,
        "source_artifact_sha256": hashes,
        "primary_result": {
            "source_metrics_path": runner.relative(PRIMARY_METRICS_PATH),
            "source_metrics_sha256": sha256(PRIMARY_METRICS_PATH),
            "fpr_a_eligible": primary_fpr.get("summary", [])[0].get("eligible"),
            "fpr_a_summary": next(item for item in primary_fpr["summary"]
                                   if item["condition_id"] == "A"),
            "original_a_r2": {"decision": "inconclusive", "decision_coverage": 2/3,
                               "fpr": None, "eligible": False},
            "modified": False,
        },
        "replacement_unit": {
            "condition_id": "A", "scenario_id": "S12", "replicate": 2,
            "candidate_budget": 10, "candidate_count": 10, "unique_candidate_count": 10,
            "duplicate_candidate_count": 0, "analysis_completed_count": 10,
            "system_decision": "negative", "binary_decision_eligible": True,
            "metric_eligible": True, "database_reset_performed": True,
            "logical_probe_submissions": completion["logical_probe_submissions"],
            "http_request_calls": completion["http_request_calls"],
            "provider": result_summary["model"], "api_calls_used": result_summary["api_calls_used"],
            "api_call_ceiling": result_summary["api_call_ceiling"],
            "api_http_status_counts": http_statuses,
            "completion_tokens_used": result_summary["completion_tokens_used"],
            "completion_token_ceiling": result_summary["completion_token_ceiling"],
            "usage_totals": result_summary["usage_totals"],
            "attempt_number": completion["attempt_number"],
            "automatic_retry_or_replacement": False,
            "sensitivity_only": True,
        },
        "sensitivity_matrix": {
            "scope": "A/B, scenarios S10-S12, replicates 1-3; only original A/S12/R2 is replaced in this separate matrix",
            "original_unit_remains_in_primary_source": True,
            "candidate_sets_merged": False,
            "human_annotations_used_for_fpr": False,
            "fpr": sensitivity_fpr,
        },
        "cost": {
            "configured_maximum_spend_usd": 0,
            "actual_provider_spend_usd": None,
            "actual_spend_note": "Provider billing was not metered in the run artifacts. Execution proceeded under the user's assurance that the Poolside API/account remained free; the local runner has no hard dollar cap.",
        },
        "interpretation": {
            "primary_fpr_a_remains_withheld": True,
            "sensitivity_fpr_a_mean": fpr_a["mean"],
            "sensitivity_fpr_a_sample_sd": fpr_a["sample_sd"],
            "sensitivity_fpr_a_n": fpr_a["n"],
            "not_a_confirmatory_replacement": True,
            "psr_recalculated": False,
            "fpr_b_unchanged_from_primary": fpr_b == next(
                item for item in primary_fpr["summary"] if item["condition_id"] == "B"),
        },
    }
    summary = (
        "# Hasil sensitivitas FPR P4 A/S12/R2\n\n"
        "Analisis ini adalah sensitivitas pascahasil yang disetujui secara terpisah. Hasil primer U05 tidak diubah.\n\n"
        "Unit pengganti A/S12/R2 menyelesaikan 10 kandidat unik dan seluruh analisis; semua klaim sistem negatif. "
        "Run valid dan eligible menurut kebijakan yang dibekukan. Ledger mencatat satu reset database DVWA, "
        f"{result_summary['api_calls_used']} dari {result_summary['api_call_ceiling']} request API, dan "
        f"{result_summary['completion_tokens_used']} dari {result_summary['completion_token_ceiling']} completion token.\n\n"
        "Pada matriks sensitivitas, keputusan negatif menghasilkan FPR A/R2 sebesar 0/3. Mean tiga replikasi "
        "A adalah **0%** dengan sample SD 0 dan n=3. FPR B tetap 0% dengan n=3. FPR A pada hasil primer "
        "VAL-01 tetap tertahan karena unit asli A/S12/R2 masih inconclusive; angka sensitivitas tidak menggantikannya.\n\n"
        "Anotasi manusia tidak dipakai untuk FPR dan PSR tidak dihitung ulang. Pengeluaran aktual tidak tersedia "
        "di artefak provider. Anggaran ditetapkan USD 0 berdasarkan kondisi API/akun gratis yang dilaporkan pengguna; "
        "runner tidak memiliki hard cap dolar.\n\n"
        f"Bukti terstruktur: `{RESULT_PATH.relative_to(ROOT).as_posix()}`.\n"
    )
    return report, summary


def main() -> int:
    report, summary = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULT_PATH.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(report, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    with REPORT_PATH.open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(summary)
    print(json.dumps({
        "status": report["status"],
        "fpr_a_sensitivity_mean": report["interpretation"]["sensitivity_fpr_a_mean"],
        "fpr_a_eligible": report["sensitivity_matrix"]["fpr"]["eligible"],
        "result_path": RESULT_PATH.relative_to(ROOT).as_posix(),
        "report_path": REPORT_PATH.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
