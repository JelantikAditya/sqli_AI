"""Read-only status/audit of the Poolside P3 cohort; never contacts services."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "results/raw/pilot/poolside-s21-p3-r1-20261022"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        # A live writer may not have finished its current file yet.
        return None


def summarize(directory: Path) -> dict:
    checkpoint = read_json(directory / "checkpoint.json") or {}
    started = list(directory.glob("attempts/**/api-calls/*/request-started.json"))
    statuses, stages, http = Counter(), Counter(), Counter()
    usage = Counter()
    latencies = []
    errors = []
    for path in directory.glob("attempts/**/api-calls/*/result.json"):
        saved = read_json(path)
        if saved is None:
            continue
        result = saved["result"]
        status = result.get("status", "unknown")
        statuses[status] += 1
        http[str(result.get("http_status"))] += 1
        request = read_json(path.with_name("request.json")) or {}
        stages[request.get("stage", "unknown")] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[key] += (result.get("usage") or {}).get(key, 0)
        if result.get("elapsed_seconds") is not None:
            latencies.append(result["elapsed_seconds"])
        if status != "ok":
            errors.append({"checkpoint": path.relative_to(directory).as_posix(),
                           "status": status, "http_status": result.get("http_status")})
    running = [{"scenario": row["unit"]["scenario_id"], "condition": row["unit"]["condition_id"]}
               for row in checkpoint.get("runs", {}).values() if row["status"] == "running"]
    units = []
    for path in directory.glob("attempts/*/*/qwen-api-adaptive-result.json"):
        result = read_json(path)
        if result is None:
            continue
        summary = result.get("run_summary") or {}
        units.append({"scenario": result["context"]["scenario_id"],
                      "condition": result["context"]["condition_id"],
                      "candidate_count": summary.get("candidate_count"),
                      "budget_complete": summary.get("budget_complete"),
                      "stop_reason": result.get("stop_reason"),
                      "runtime_failure_code": result.get("runtime_failure_code")})
    return {"experiment_id": checkpoint.get("experiment_id"), "updated_at_utc": checkpoint.get("updated_at_utc"),
            "status_counts": checkpoint.get("status_counts"), "running": running,
            "api_requests_started": len(started), "api_results_saved": sum(statuses.values()),
            "api_statuses": dict(statuses), "http_statuses": dict(http), "api_stages": dict(stages),
            "api_elapsed_seconds": round(sum(latencies), 3), "token_usage_available": dict(usage),
            "service_errors": errors, "llm_units_with_artifacts": units,
            "cohort_result": read_json(directory / "poolside-execution-result.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
