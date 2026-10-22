"""Verify repaired P3 gates, P2 wire parity and preservation without networking."""

from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "dvwa", ROOT / "development"):
    sys.path.insert(0, str(directory))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "results/raw/development/p3-repair-audit-20261022-v2")
    parser.add_argument("--baseline", type=Path,
                        default=ROOT / "results/raw/development/p3-repair-20261022-v2/preservation-before.json")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT / "results/raw/development"):
        parser.error("Audit output must stay under results/raw/development.")
    output.mkdir(parents=True, exist_ok=False)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    blocked = []

    def deny_network(*_args, **_kwargs):
        blocked.append("blocked socket connection")
        raise RuntimeError("The P3 repair audit is offline.")

    with ExitStack() as guard:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
            guard.enter_context(patch(target, side_effect=deny_network))
        import run_qwen_api_experiments as active
        import qwen_api_p2_analysis as p2
        from qwen_api_runtime import CheckpointedQwenAPI
        from run_qwen_api_p2_eval import DEFAULT_REQUESTS, load_requests
        from test_qwen_api_p3_gates import context_for

        sources = active.runtime_source_hashes()
        checks = []

        def record(name, passed, details):
            checks.append({"check": name, "passed": bool(passed), "details": details})
            write_json(output / "checks.partial.json", {"checks": checks})

        plan_path = ROOT / "development/qwen_api_p3_v2_pilot_plan.template.json"
        draft = active.run(plan_path)
        config, config_hash = active.load_config()
        plan, protocol, _, _ = active.validate_api_plan(plan_path, config, config_hash)
        slots = list(active.local_runner.ordered_run_slots(
            protocol, scenario_ids=plan["scenario_ids"], condition_ids=plan["condition_ids"], replicates=[1]))
        counts = {c: sum(s["applicable"] and s["condition_id"] == c for s in slots) for c in ("A", "B", "C")}
        record("v2_pilot_dry_run", counts == {"A": 12, "B": 12, "C": 9} and not draft["execution_started"],
               {"applicable_runs": counts, "excluded_slots": 3, "candidate_budget": 330,
                "logical_confirmations": 990, "worst_case_API_requests": draft["estimated_worst_case_api_calls"],
                "protocol_id": protocol["protocol_id"], "plan_sha256": digest(plan_path)})

        # Verify the frozen request packet, including all 18 cases, without new inference.
        requests, requests_hash = load_requests(DEFAULT_REQUESTS)
        matching = sum(p2.prepare(row["document"])["payload"] == row["prepared"]["payload"] for row in requests)
        record("frozen_P2_request_renderer", matching == 18,
               {"matching_payloads": matching, "requests_sha256": requests_hash})

        catalog = active.load_catalog()["scenarios"]
        old_run = ROOT / "results/raw/development/qwen38-api-p2-eval-20261022-run-005"
        replay_count, profile_matches = 0, 0
        with tempfile.TemporaryDirectory() as directory:
            replay_root = Path(directory).resolve()
            api = CheckpointedQwenAPI("offline-dummy-secret", replay_root, config)
            for row in requests:
                source = json.loads((old_run / "results" / (row["review_id"] + ".json")).read_text(encoding="utf-8"))
                if source["api_status"] != "ok":
                    continue
                document = row["document"]
                scenario = next(s for s in catalog if s["sqli_type"] == document["technique"] and all(
                    document["injection_point"][key] == s[key]
                    for key in ("method", "input_path", "result_path", "parameter")))
                for condition in ("A", "B"):
                    context = {**context_for(document, condition), "scenario_id": scenario["scenario_id"]}
                    class ReplayTransport:
                        def chat(self, _messages):
                            return {"status": "ok", "content": source["content"], "finish_reason": source["finish_reason"],
                                    "reported_model": source["reported_model"]}
                    api.client["analysis"] = ReplayTransport()
                    result = active.make_analysis_callback(
                        api, replay_root / "attempts" / (row["review_id"] + condition), context)(document, context)
                    checkpoint = result["audit"]["provenance"]["api_checkpoint"]
                    wire = json.loads((replay_root / checkpoint["checkpoint_directory"] / "request.json").read_text(encoding="utf-8"))
                    profile_matches += wire["payload"] == row["prepared"]["payload"]
                    replay_count += result["analysis_status"] == "completed" and result["system_claim"] == source["analysis"]["decision"]
        record("P2_response_replay_through_A_B_callbacks", replay_count == profile_matches == 34,
               {"saved_responses": 17, "conditions": ["A", "B"], "matching_callback_results": replay_count,
                "matching_checkpoint_payloads": profile_matches, "new_inferences": 0})

        suite = unittest.TestSuite()
        suite.addTests(unittest.TestLoader().discover(str(ROOT / "development"), pattern="test_qwen_api*.py"))
        selected = ("test_adaptive_s1_loop.py", "test_adaptive_candidate_policy.py", "test_confirmation_policy.py",
                    "test_dvwa_runtime_controls.py", "test_run_local_experiments.py", "test_zap_input_inventory.py",
                    "test_execution_order_policy.py", "test_response_analysis.py", "test_adaptive_runner_artifact.py",
                    "test_run_decision_policy.py")
        for pattern in selected:
            suite.addTests(unittest.TestLoader().discover(str(ROOT / "tests"), pattern=pattern))
        with (output / "tests.log").open("w", encoding="utf-8") as log:
            tests = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        test_summary = {"run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
                        "skipped": len(tests.skipped), "successful": tests.wasSuccessful()}
        record("offline_regressions_including_13_new_gate_tests", tests.wasSuccessful(), test_summary)

        changed = [name for name, old in baseline["files"].items()
                   if not (ROOT / name).is_file() or digest(ROOT / name) != old]
        expected = baseline["expected_changed_sources"]
        unexpected = sorted(set(changed) - set(expected))
        record("intentional_runtime_changes_only", set(changed) == set(expected),
               {"expected_changed_sources": expected, "changed_files": changed, "unexpected_changes": unexpected})
        archive = ROOT / baseline["legacy_source_directory"]
        bad_legacy = [name for name, old in baseline["legacy_source_sha256"].items()
                      if not (archive / name).is_file() or digest(archive / name) != old]
        record("legacy_source_archives_preserved", not bad_legacy,
               {"archived_sources": len(baseline["legacy_source_sha256"]), "mismatches": bad_legacy})
        record("historical_results_and_reference_preservation", not unexpected,
               {"baseline_files": len(baseline["files"]),
                "unchanged_files": len(baseline["files"]) - len(changed), "unexpected_changes": unexpected})
        record("network_guard", not blocked, {"blocked_attempts": len(blocked), "real_API_calls": 0, "real_DVWA_requests": 0})
        result = {"schema": "p3-repair-audit-v2", "audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "scope": "offline P3 integration repairs; no live pilot or new inference", "checks": checks,
                  "tests": test_summary, "source_sha256": sources, "source_sha256_before": baseline["legacy_source_sha256"],
                  "audit_script_sha256": digest(Path(__file__)),
                  "new_gate_tests_sha256": digest(ROOT / "development/test_qwen_api_p3_gates.py"),
                  "baseline_inventory_sha256": digest(args.baseline), "baseline_inventory": str(args.baseline.resolve().relative_to(ROOT)),
                  "legacy_source_directory": baseline["legacy_source_directory"],
                  "resolved_findings": ["P3-01", "P3-02", "P3-03"] if all(c["passed"] for c in checks) else [],
                  "offline_repairs_verified": all(c["passed"] for c in checks),
                  "live_pilot_ready": False, "formal_ready": False,
                  "pending_live_work": ["isolated generation smoke", "fresh executor controls S1-S12", "pilot-specific spending budget",
                                        "33 applicable pilot runs", "independent review", "measured duration and quota"],
                  "real_API_calls": 0, "real_DVWA_requests": 0}
        write_json(output / "audit.json", result)
        print(json.dumps({"evidence_directory": output.relative_to(ROOT).as_posix(), "tests": test_summary,
                          "resolved_findings": result["resolved_findings"], "offline_repairs_verified": result["offline_repairs_verified"],
                          "unchanged_files": len(baseline["files"]) - len(changed), "archived_sources": len(baseline["legacy_source_sha256"]),
                          "real_API_calls": 0, "real_DVWA_requests": 0}, indent=2))
        return 0 if result["offline_repairs_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
