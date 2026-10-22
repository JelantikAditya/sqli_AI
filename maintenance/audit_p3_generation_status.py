"""Replay the halted pilot's generation checkpoints and verify its offline fix."""

from contextlib import ExitStack
import argparse
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "dvwa", ROOT / "development"):
    sys.path.insert(0, str(folder))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "results/raw/development/p3-generation-status-repair-audit-20261022")
    output = parser.parse_args().output_dir.resolve()
    if not output.is_relative_to(ROOT / "results/raw/development"):
        parser.error("Audit output must remain under results/raw/development.")
    output.mkdir(parents=True, exist_ok=False)
    blocked = []
    def deny(*_args, **_kwargs):
        blocked.append("socket attempt")
        raise RuntimeError("Generation status repair audit is offline")
    with ExitStack() as guard:
        for name in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
            guard.enter_context(patch(name, side_effect=deny))
        import run_qwen_api_experiments as active
        import run_bounded_qwen_p3_pilot as bounded
        from qwen_api_client import ChatSettings, request_payload
        config, _ = active.load_config()
        stage_settings = ChatSettings(max_tokens=config["token_limits"]["generation"],
                                      timeout_seconds=config["timeout_seconds"], chat_template_kwargs={"enable_thinking": False})
        pilot = ROOT / "results/raw/pilot/qwen38-api-p3-v2-pilot-20261022"
        scenario = next(s for s in active.load_catalog()["scenarios"] if s["scenario_id"] == "S1")
        replay = []
        for request_file in sorted(pilot.glob("attempts/**/api-calls/*-generation-*/request.json")):
            wire = json.loads(request_file.read_text(encoding="utf-8"))
            response = json.loads((request_file.parent / "result.json").read_text(encoding="utf-8"))["result"]
            task = json.loads(wire["payload"]["messages"][1]["content"])
            feedback = task["previous_measured_feedback"]
            previous = None if feedback is None else {"analysis": {"evidence": feedback}}
            class ReplayAPI:
                calls = 0
                def chat(self, stage, messages, directory):
                    assert stage == "generation"
                    assert request_payload(messages, stage_settings) == wire["payload"]
                    self.calls += 1
                    return response, {"request_sha256": wire["request_sha256"]}
            fake = ReplayAPI()
            candidate, audit = active.make_generation_callback(
                fake, output, scenario, None, task["benign_baseline_measurement"], config)(
                    previous, task["previously_attempted_values"], 0, task["rejection_code"])
            assert fake.calls == 1 and isinstance(audit["status"], str)
            replay.append({"call_id": wire["call_id"], "status": audit["status"],
                           "candidate_present": candidate is not None, "exact_wire_payload_reproduced": True})
        assert len(replay) == 9
        assert sum(r["candidate_present"] for r in replay) == 8
        assert replay[-1]["status"] == "no_valid_distinct_candidate"
        suite = unittest.TestSuite()
        suite.addTests(unittest.TestLoader().discover(str(ROOT / "development"), pattern="test_qwen_api*.py"))
        for pattern in ("test_adaptive_s1_loop.py", "test_adaptive_candidate_policy.py", "test_confirmation_policy.py",
                        "test_dvwa_runtime_controls.py", "test_run_local_experiments.py", "test_zap_input_inventory.py",
                        "test_execution_order_policy.py", "test_response_analysis.py", "test_adaptive_runner_artifact.py",
                        "test_run_decision_policy.py"):
            suite.addTests(unittest.TestLoader().discover(str(ROOT / "tests"), pattern=pattern))
        with (output / "tests.log").open("w", encoding="utf-8") as log:
            tests = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        test_result = {"run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
                       "skipped": len(tests.skipped), "successful": tests.wasSuccessful()}
        before_path = ROOT / "results/raw/development/p3-generation-status-repair-20261022/preservation-before.json"
        before = json.loads(before_path.read_text(encoding="utf-8"))
        altered = [name for name, old in before["files"].items() if digest(ROOT / name) != old]
        archived = ROOT / "results/raw/development/p3-generation-status-repair-20261022/source-before"
        bad_archive = [name for name, old in before["runtime_source_before"].items() if digest(archived / name) != old]
        changed_source = [name for name, old in before["runtime_source_before"].items() if digest(ROOT / name) != old]
        assert changed_source == ["development/run_qwen_api_experiments.py"]
        recovery = bounded.run(ROOT / "development/qwen_api_p3_v3_pilot_plan.template.json",
                               ROOT / "development/qwen_api_p3_v3_budget_20261022.json")
        result = {"schema": "p3-generation-status-repair-audit-v1", "audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "root_cause": "A rejected generation returned rejection_code without audit.status; adaptive_s1_loop requires audit.status.",
                  "protocol_id": active.API_PROTOCOL_ID, "tests": test_result, "saved_generation_replays": replay,
                  "actual_duplicate_rejection_reproduced_without_crash": replay[-1]["status"] == "no_valid_distinct_candidate",
                  "preserved_attempt_and_smoke_files": len(before["files"]), "changed_historical_artifacts": altered,
                  "archived_runtime_sources": len(before["runtime_source_before"]), "legacy_archive_mismatches": bad_archive,
                  "intentional_runtime_source_changes": changed_source, "runtime_source_sha256": active.runtime_source_hashes(),
                  "new_generation_tests_sha256": digest(ROOT / "development/test_qwen_api_p3_generation_status.py"),
                  "analysis_gate_tests_sha256": digest(ROOT / "development/test_qwen_api_p3_gates.py"),
                  "audit_script_sha256": digest(Path(__file__)), "test_log_sha256": digest(output / "tests.log"),
                  "recovery_plan_dry_run": recovery, "automatic_replacement_started": False,
                  "real_API_calls": 0, "real_DVWA_requests": 0, "blocked_connection_attempts": len(blocked)}
        ok = tests.wasSuccessful() and not altered and not bad_archive and not blocked
        result["offline_fix_verified"] = ok
        (output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"offline_fix_verified": ok, "tests": test_result, "generation_checkpoint_replays": len(replay),
                          "preserved_historical_artifacts": len(before["files"]), "changed_historical_artifacts": altered,
                          "runtime_version": active.API_PROTOCOL_ID, "new_API_calls": 0, "automatic_replacement_started": False}, indent=2))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
