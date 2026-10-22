"""Read-only reconciliation of the approved P3 v3 pilot after execution stops."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "qwen38-api-p3-v3-pilot-20261022"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def audit():
    directory = ROOT / "results/raw/pilot" / EXPERIMENT
    # A final result is required. This auditor cannot resume or repair a live run.
    result = read(directory / "bounded-execution-result.json")
    checkpoint = read(directory / "checkpoint.json")
    events = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    approval = read(ROOT / "docs/evidence/p3-v3-execution-approval-2026-10-22.json")
    baseline = read(ROOT / approval["preservation_baseline"])
    budget = read(directory / "explicit-budget.snapshot.json")
    runtime = read(directory / "api-runtime-snapshot.json")
    config = read(directory / "bounded-config.snapshot.json")
    mismatches = []

    def check(name, passed):
        if not passed:
            mismatches.append(name)

    check("approval_bound_artifacts", all(digest(ROOT / name) == expected
          for name, expected in approval["bound_artifact_sha256"].items()))
    check("baseline_hash", digest(ROOT / approval["preservation_baseline"])
          == approval["preservation_baseline_sha256"])
    changed = [name for name, expected in baseline["files"].items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != expected]
    changed_sources = [name for name, expected in baseline["runtime_source_sha256"].items()
                       if digest(ROOT / name) != expected]
    check("historical_data_preserved", not changed)
    check("frozen_runtime_preserved", not changed_sources)
    check("result_checkpoint_counts", result["status_counts"] == checkpoint["status_counts"])
    check("no_active_unit", not any(checkpoint["status_counts"][key] for key in ("running", "retried")))
    check("ledger_sequences", all(event["sequence"] == index
          and event["experiment_id"] == EXPERIMENT for index, event in enumerate(events, 1)))
    check("ledger_event_ids", len({e["event_id"] for e in events}) == len(events))
    check("no_replacement_attempt", not any(e["event_type"] == "attempt_retried" for e in events))
    check("runtime_source_snapshot", runtime["source_sha256"] == budget["runtime_source_sha256"])
    check("bounded_config_hash", canonical_digest(config) == runtime["runtime_config_sha256"])

    calls = []
    for started in sorted(directory.glob("attempts/**/request-started.json")):
        request = read(started.parent / "request.json")
        returned = read(started.parent / "result.json") if (started.parent / "result.json").exists() else None
        value = returned.get("result", returned) if returned else {}
        check("request_hash:" + started.parent.name,
              canonical_digest(request["payload"]) == request["request_sha256"]
              == read(started)["request_sha256"])
        calls.append({"call_id": request["call_id"], "stage": request["stage"],
                      "unit_id": started.parents[3].name,
                      "status": value.get("status", "missing-result"),
                      "http_status": value.get("http_status"),
                      "reported_model": value.get("reported_model"),
                      "elapsed_seconds": value.get("elapsed_seconds"),
                      "usage": value.get("usage")})
    calls.sort(key=lambda c: c["call_id"])
    check("sequential_call_numbers", [int(c["call_id"].split("-")[0]) for c in calls]
          == list(range(1, len(calls) + 1)))
    check("call_counter", len(calls) == result["api_calls_used"] <= budget["max_api_calls"])
    check("every_request_has_result", all(c["status"] != "missing-result" for c in calls))

    finished = [e for e in events if e["event_type"] in {"attempt_completed", "attempt_invalid"}]
    units = []
    adaptive_paths = {p.parents[1].name: p for p in directory.glob("attempts/**/qwen-api-adaptive-result.json")}
    for e in finished:
        details = {key: e.get(key) for key in (
            "unit_id", "event_type", "failure_code", "failure_details", "metric_eligible",
            "exclusion_reason", "generated_candidate_count", "candidate_generation_failed_count",
            "valid_candidates_executed", "http_request_calls", "logical_probe_submissions",
            "database_reset_performed", "api_request_count")}
        unit_calls = [c for c in calls if c["unit_id"] == e["unit_id"]]
        if e["event_type"] == "attempt_invalid":
            # The ledger writes fallback zeros when transport fails before adaptive artifacts are assembled.
            for key in ("generated_candidate_count", "candidate_generation_failed_count",
                        "valid_candidates_executed"):
                details[key] = None
            details["invalid_event_candidate_aggregates_reliable"] = False
        details["API_requests_from_checkpoints"] = len(unit_calls)
        details["API_stage_counts"] = dict(Counter(c["stage"] for c in unit_calls))
        if e["unit_id"] in adaptive_paths:
            adaptive = read(adaptive_paths[e["unit_id"]])
            details["adaptive_stop_reason"] = adaptive["stop_reason"]
            details["candidate_analysis_statuses"] = dict(Counter(
                c["analysis_status"] for c in adaptive["candidate_records"]))
            details["generation_event_statuses"] = dict(Counter(
                event["data"]["status"] for event in adaptive["events"] if event["kind"] == "generation"))
        units.append(details)
    design_exclusions = [e for e in events if e["event_type"] == "run_excluded" and not e.get("attempt_id")]
    operational_exclusions = [e for e in events if e["event_type"] == "run_excluded" and e.get("attempt_id")]
    numeric_usage = [c["usage"]["total_tokens"] for c in calls
                     if isinstance(c["usage"], dict) and isinstance(c["usage"].get("total_tokens"), int)]
    starts = [e for e in events if e["event_type"] == "attempt_started"]
    elapsed = ((datetime.fromisoformat(finished[-1]["recorded_at_utc"])
                - datetime.fromisoformat(starts[0]["recorded_at_utc"])).total_seconds()
               if starts and finished else None)
    summary = {
        "schema": "p3-v3-execution-audit-v1",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment_id": EXPERIMENT, "execution_result": result,
        "execution_started_at_utc": starts[0]["recorded_at_utc"] if starts else None,
        "execution_stopped_at_utc": finished[-1]["recorded_at_utc"] if finished else None,
        "elapsed_seconds": elapsed, "API_requests": len(calls),
        "API_stage_counts": dict(Counter(c["stage"] for c in calls)),
        "API_status_counts": dict(Counter(c["status"] for c in calls)),
        "HTTP_status_counts": dict(Counter(str(c["http_status"]) for c in calls)),
        "returned_total_tokens": sum(numeric_usage), "requests_with_reported_tokens": len(numeric_usage),
        "requests_without_reported_tokens": len(calls) - len(numeric_usage),
        "HTTP_request_calls": sum(e.get("http_request_calls") or 0 for e in finished),
        "HTTP_count_missing_units": [e["unit_id"] for e in finished if e.get("http_request_calls") is None],
        "logical_probe_submissions_known": sum(e.get("logical_probe_submissions") or 0 for e in finished),
        "logical_probe_count_missing_units": [e["unit_id"] for e in finished if e.get("logical_probe_submissions") is None],
        "database_resets_recorded": sum(bool(e.get("database_reset_performed")) for e in finished),
        "design_exclusions": len(design_exclusions), "operational_exclusions": len(operational_exclusions),
        "units": units, "calls": calls,
        "preserved_historical_files": len(baseline["files"]), "changed_historical_files": changed,
        "changed_runtime_sources": changed_sources, "reconciliation_mismatches": mismatches,
        "reconciliation_passed": not mismatches, "automatic_replacement_attempts_started": 0,
        "formal_eligible": False, "human_validation": "pending",
        "interpretation": "Development pilot only. Transport success does not establish candidate validity, attack success or formal FPR/PSR. Missing usage or missing probe aggregates are not zero.",
        "source_artifact_sha256": {p.relative_to(ROOT).as_posix(): digest(p)
                                   for p in sorted(directory.rglob("*")) if p.is_file()},
        "approval_receipt_sha256": digest(ROOT / "docs/evidence/p3-v3-execution-approval-2026-10-22.json"),
        "audit_script_sha256": digest(Path(__file__)),
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/evidence/p3-v3-execution-audit-r2-2026-10-22.json")
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT / "docs/evidence"):
        parser.error("Audit receipt must remain under docs/evidence.")
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: summary[key] for key in (
        "experiment_id", "execution_result", "elapsed_seconds", "API_requests", "API_stage_counts",
        "API_status_counts", "HTTP_request_calls", "operational_exclusions", "preserved_historical_files",
        "reconciliation_mismatches", "reconciliation_passed")}, indent=2))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(audit())
