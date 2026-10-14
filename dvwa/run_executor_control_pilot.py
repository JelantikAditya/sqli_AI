"""Exercise fixed manual SQLi controls across all DVWA forms, outside formal metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from validation_loop import ROOT, SCENARIOS_PATH, load_json


def manual_control(scenario: dict) -> dict:
    prefix = "1" if scenario["security_level"] == "medium" else "1'"
    candidate = {"candidate_id": "manual-control-" + scenario["scenario_id"].lower(),
                 "scenario_id": scenario["scenario_id"], "source": "manual",
                 "rag_mode": "not_applicable"}
    if scenario["probe_kind"] == "boolean_pair":
        candidate.update(true_payload=prefix + " AND 1=1 #",
                         false_payload=prefix + " AND 1=2 #")
    elif scenario["probe_kind"] == "single_time":
        candidate["payload"] = prefix + " AND SLEEP(2)=0 #"
    else:
        candidate["payload"] = "1)" if scenario["security_level"] == "medium" else "1'"
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    args = parser.parse_args()
    if not args.confirm_local_dvwa or not args.confirm_database_reset:
        parser.error("Confirm local DVWA and one database reset before each scenario.")
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to((ROOT / "results/raw").resolve()):
        parser.error("--output-dir must stay under results/raw/.")
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": "1.0.0", "scope": "manual-executor-controls-not-formal",
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "scenario_catalog_sha256": hashlib.sha256(SCENARIOS_PATH.read_bytes()).hexdigest(),
               "executor_sha256": hashlib.sha256((ROOT / "dvwa/validation_loop.py").read_bytes()).hexdigest(),
               "confirmations_per_candidate": 3, "conditions": [], "formal_eligible": False}
    for scenario in load_json(SCENARIOS_PATH)["scenarios"]:
        scenario_id = scenario["scenario_id"]
        directory = output_dir / scenario_id
        directory.mkdir()
        batch = directory / "manual-candidate.json"
        batch.write_text(json.dumps({"schema_version": "1.0.0",
                                     "candidates": [manual_control(scenario)]}, indent=2) + "\n",
                         encoding="utf-8")
        log = directory / "validation.jsonl"
        command = [sys.executable, "-B", str(ROOT / "dvwa/validation_loop.py"),
                   "--scenario", scenario_id, "--payload-file", str(batch), "--output", str(log),
                   "--run-id", output_dir.name + "-" + scenario_id.lower(), "--confirmations", "3",
                   "--reset-before-run", "--confirm-local-dvwa"]
        result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                                capture_output=True, check=False)
        (directory / "command.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        decisions = [r for r in records if r.get("record_type") == "decision"]
        evidence = next((r for r in records if r.get("record_type") == "candidate_evidence"), {})
        setup = next((r for r in records if r.get("record_type") == "runtime_setup"), {})
        end = next((r for r in records if r.get("record_type") == "run_end"), {})
        failure = next((r for r in records if r.get("record_type") == "runtime_failure"), {})
        valid = (result.returncode == 0 and len(decisions) == 3
                 and {r["confirmation_index"] for r in decisions} == {1, 2, 3}
                 and evidence.get("valid_confirmation_count") == 3
                 and setup.get("security_level_verified") == scenario["security_level"]
                 and setup.get("database_reset", {}).get("success_markers_verified") is True
                 and not failure)
        item = {"scenario_id": scenario_id, "security_level": scenario["security_level"],
                "probe_kind": scenario["probe_kind"], "runtime_valid": valid,
                "runtime_failure_code": failure.get("runtime_failure_code"),
                "valid_confirmation_count": evidence.get("valid_confirmation_count", 0),
                "positive_confirmation_count": evidence.get("positive_confirmation_count", 0),
                "evidence_status": evidence.get("evidence_status"),
                "database_reset_performed": bool(setup.get("database_reset")),
                "logical_probe_submissions": end.get("logical_probe_submissions"),
                "http_request_calls": end.get("http_request_calls"),
                "validation_log": log.relative_to(ROOT).as_posix(),
                "validation_sha256": hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else None,
                "timing_evidence": [r["evidence"] for r in decisions] if scenario["probe_kind"] == "single_time" else [],
                "human_validation": "pending"}
        summary["conditions"].append(item)
        summary["completed_scenarios"] = sum(r["runtime_valid"] for r in summary["conditions"])
        (output_dir / "pilot.summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"scenario_id": scenario_id, "runtime_valid": valid,
                          "positive_confirmations": item["positive_confirmation_count"],
                          "evidence_status": item["evidence_status"]}), flush=True)
        if not valid:
            raise SystemExit("Executor control pilot stopped on an invalid attempt; see persisted logs.")
    print(json.dumps({"summary_path": str(output_dir / "pilot.summary.json"),
                      "completed_scenarios": summary["completed_scenarios"], "formal_eligible": False}), flush=True)


if __name__ == "__main__":
    main()
