"""Reproduce P3 readiness checks with fake APIs and networking disabled.

Writes new audit evidence only. It does not repair or execute the pilot runner,
load API credentials, query Chroma/Ollama, or contact DVWA.
"""

from __future__ import annotations

import argparse
import ast
import copy
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dvwa"))
sys.path.insert(0, str(ROOT / "development"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def preserve_paths(source_hashes: dict, plan: dict) -> dict:
    paths = set(source_hashes)
    inventory = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json"
    if inventory.is_file():
        paths.update(json.loads(inventory.read_text(encoding="utf-8")))
    for directory in (ROOT / "results/raw/development").glob("qwen38-api-p2-*"):
        if directory.is_dir():
            paths.update(path.relative_to(ROOT).as_posix()
                         for path in directory.rglob("*") if path.is_file())
    paths.update(plan["knowledge_snapshot"]["index_file_sha256"])
    paths.update(("knowledge/sqli-entries.json", "knowledge/sources.lock.json"))
    return {name: digest(ROOT / name) for name in sorted(paths) if (ROOT / name).is_file()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path,
                        default=ROOT / "development/qwen_api_p3_pilot_plan.template.json")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "results/raw/development/p3-offline-audit-20261021")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT / "results/raw/development"):
        parser.error("Audit output must stay under results/raw/development.")
    output.mkdir(parents=True, exist_ok=False)
    blocked_network = []

    def deny_network(*_args, **_kwargs):
        blocked_network.append("socket connection blocked")
        raise RuntimeError("This audit is offline; network connections are forbidden.")

    with ExitStack() as guard:
        # Guard project imports and checks, including accidental loopback calls.
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
            guard.enter_context(patch(target, side_effect=deny_network))

        import run_qwen_api_experiments as active
        import qwen_api_generation as generator
        import qwen_api_p2_analysis as p2
        import analysis_v5_pilot_cases as cases
        import analyze_response_v2 as contract
        import adaptive_s1_loop as loop
        import run_local_experiments as local
        from qwen_api_client import ChatSettings, request_payload
        from qwen_api_runtime import APIRuntimeFailure, CheckpointedQwenAPI
        from validation_loop import matched_no_delay_payload

        config, config_hash = active.load_config()
        plan_path = args.plan.resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        sources = active.runtime_source_hashes()
        before = preserve_paths(sources, plan)
        write_json(output / "preservation-before.json", {"files": before, "source_sha256": sources})
        checks = []

        def record(name, passed, details, *, finding=None):
            checks.append({"check": name, "passed": bool(passed), "details": details,
                           **({"finding": finding} if finding else {})})
            write_json(output / "checks.partial.json", checks)

        draft = active.run(plan_path)
        protocol = active.api_protocol(local.load_protocol(), config, config_hash)
        slots = list(local.ordered_run_slots(protocol, scenario_ids=plan["scenario_ids"],
                                            condition_ids=plan["condition_ids"], replicates=[1]))
        applicable = [slot for slot in slots if slot["applicable"]]
        counts = {condition: sum(slot["condition_id"] == condition for slot in applicable)
                  for condition in ("A", "B", "C")}
        record("pilot_matrix_and_dry_run", counts == {"A": 12, "B": 12, "C": 9}
               and not draft["execution_started"],
               {"applicable_runs": counts, "planned_slots": len(slots),
                "excluded_C_Impossible_slots": len(slots) - len(applicable),
                "candidate_budget": 330, "logical_confirmations": 990,
                "worst_case_API_requests": draft["estimated_worst_case_api_calls"],
                "configured_API_ceiling": draft["api_call_ceiling"],
                "plan_sha256": digest(plan_path)})

        catalog = {item["scenario_id"]: item for item in active.load_catalog()["scenarios"]}
        coordinates = []
        for scenario in catalog.values():
            report = ROOT / plan["discovery_reports"][scenario["scenario_id"]]["1"]
            point = active.injection_point_context(scenario, report, require_verified=True)
            coordinates.append({"scenario": scenario["scenario_id"], "method": point["method"],
                                "path": point["path"], "parameter": point["parameter"],
                                "report_sha256": digest(report)})
        record("historical_verified_discovery_S1_S12", len(coordinates) == 12, coordinates)

        paired, no_nonce = 0, True
        for scenario in catalog.values():
            for slot in range(10):
                attempted = [f"offline-previous-{i}" for i in range(slot)]
                baseline = {"http_status": 200, "elapsed_ms": 10, "diagnostics": [],
                            "content_markers": ["benign_record"], "technique": scenario["sqli_type"]}
                _, a = active.generation_messages(scenario, attempted, [], baseline, None, 0, None)
                _, b = active.generation_messages(scenario, attempted,
                                                  [{"chunk_id": "offline-reference", "text": "Technique reference."}],
                                                  baseline, None, 0, None)
                av, bv = json.loads(a[1]["content"]), json.loads(b[1]["content"])
                av.pop("retrieved_reference_chunks")
                bv.pop("retrieved_reference_chunks")
                assert av == bv and a[0] == b[0]
                assert not ({"ground_truth", "security_level", "scenario_id"} & set(av))
                text = " ".join(row["content"] for row in a)
                no_nonce &= not any(token in text for token in ("assigned slot integer", "assigned slot ID", "101"))
                paired += 1
        record("A_B_prompt_isolation_and_slot_identity", no_nonce,
               {"paired_generation_requests_checked": paired,
                "only_treatment_difference": "retrieved_reference_chunks",
                "ground_truth_level_scenario_fields_in_model_task": False,
                "numeric_slot_nonce_required": not no_nonce})
        record("structural_deduplication", generator.structural_key({"payload": "1'"}, "single_error")
               == generator.structural_key({"payload": "101'"}, "single_error"),
               {"numeric_only_variants_collapse": True})
        delayed = "1' AND SLEEP(2)#"
        control = matched_no_delay_payload(delayed)
        record("matched_time_control", control == "1' AND SLEEP(0)#",
               {"only_sleep_argument_changes": True, "threshold_ms": protocol["validation"]["time_signal_threshold_ms"]})

        locked = json.loads((ROOT / "results/processed/analysis-v5-pilot-20261020-r2/inputs.lock.json")
                            .read_text(encoding="utf-8"))
        document = next(row["input"] for row in locked if row["case_id"] == "pilot-001")
        trials = cases.expected_trials(document)
        refs = sorted({ref for trial in trials for ref in trial["evidence_refs"]})
        model_output = {"trial_assessments": trials,
                        "confirmation_summary": {"observed_trials": [1, 2, 3],
                                                 "positive_trial_count": 3, "negative_trial_count": 0},
                        "decision": "positive", "reason_code": "new_database_diagnostic",
                        "reason": "Offline fake response for integration audit.",
                        "evidence_refs": refs, "feedback_action": "none"}
        context = {"experiment_id": "p3-offline", "run_id": "r1", "attempt_id": "attempt1",
                   "candidate_id": "candidate-001", "scenario_id": "S1", "replicate": 1,
                   "condition_id": "A", "source": "LLM", "rag_mode": "off"}

        class FakeAPI:
            def __init__(self, answer):
                self.answer, self.calls, self.messages = answer, 0, None

            def chat(self, stage, messages, directory):
                self.calls += 1
                self.messages = messages
                return {"status": "ok", "content": json.dumps(self.answer),
                        "reported_model": "self-dploy/Qwen3.8-27B", "finish_reason": "stop",
                        "elapsed_seconds": 999999}, {"request_sha256": "a" * 64}

        good = FakeAPI(model_output)
        valid = active.make_analysis_callback(good, output, context)(document, context)
        record("valid_analysis_control", valid["analysis_status"] == "completed", {"fake_API_calls": good.calls})

        invalid_rows = []
        for field, value in (("runtime_status", "invalid"), ("baseline_valid", False)):
            invalid = copy.deepcopy(document)
            invalid[field] = value
            fake = FakeAPI(model_output)
            try:
                active.make_analysis_callback(fake, output, context)(invalid, context)
                outcome = "returned"
            except Exception as error:
                outcome = type(error).__name__
            invalid_rows.append({"invalid_field": field, "fake_API_calls": fake.calls, "outcome": outcome})
        record("invalid_evidence_gate_before_API", all(row["fake_API_calls"] == 0 for row in invalid_rows),
               invalid_rows, finding="P3-01")

        rejected_rows = []
        for mutation in ("fabricated_trial", "cross_trial_references"):
            answer = copy.deepcopy(model_output)
            if mutation == "fabricated_trial":
                answer["trial_assessments"][1]["trial"] = 4
            else:
                answer["trial_assessments"][0]["evidence_refs"] = answer["trial_assessments"][1]["evidence_refs"]
            fake = FakeAPI(answer)
            result = active.make_analysis_callback(fake, output, context)(document, context)
            rejected_rows.append({"mutation": mutation, "analysis_status": result["analysis_status"],
                                  "parser_error": result["audit"]["provenance"]["analysis_parser_error"],
                                  "system_claim": result["system_claim"]})
        record("parser_rejection_propagation", all(row["analysis_status"] != "completed" for row in rejected_rows),
               rejected_rows, finding="P3-02")

        active_payload = request_payload(good.messages, ChatSettings(max_tokens=2048, timeout_seconds=90,
                                         chat_template_kwargs={"enable_thinking": False}))
        p2_payload = p2.prepare(document)["payload"]
        record("P2_to_pilot_analysis_request_equivalence", active_payload == p2_payload,
               {"messages_equal": active_payload["messages"] == p2_payload["messages"],
                "P2_template_kwargs": p2_payload.get("chat_template_kwargs"),
                "pilot_template_kwargs": active_payload.get("chat_template_kwargs"),
                "same_base_contract": True, "alignment_or_separate_validation_required": True}, finding="P3-03")

        trace = []

        def generate(previous, attempted):
            trace.append("generation")
            return ("1'" if not attempted else '1"'), {"status": "generated"}

        def observe(candidate, confirmations):
            trace.append("HTTP_observation")
            return copy.deepcopy(document)

        def analyze(evidence, candidate_context):
            trace.append("analysis")
            return active.make_analysis_callback(FakeAPI(model_output), output, context)(evidence, candidate_context)

        serial = loop.run_loop(context, generate, observe, analyze, budget=2, slot_limit=2, confirmations=3,
                               database_reset_performed=True)
        record("serial_orchestration_and_time_separation", trace == ["generation", "HTTP_observation", "analysis"] * 2
               and serial["candidate_records"][0]["evidence"] == document,
               {"stage_trace": trace, "fake_API_elapsed_seconds": 999999,
                "HTTP_evidence_unchanged": serial["candidate_records"][0]["evidence"] == document})

        with tempfile.TemporaryDirectory() as temporary:
            # Windows TEMP may use an 8.3 alias; match the runtime's resolved root.
            temp = Path(temporary).resolve()
            bounded = copy.deepcopy(config)
            bounded["limits"]["max_total_api_calls"] = 1
            api = CheckpointedQwenAPI("offline-dummy-secret", temp, bounded)

            class FakeTransport:
                calls = 0

                def chat(self, messages):
                    self.calls += 1
                    return {"status": "http-error", "http_status": 503, "halt": False,
                            "error_detail": "offline overload; offline-dummy-secret"}

            transport = FakeTransport()
            api.client["generation"] = transport
            attempt = temp / "attempts/unit/attempt1"
            codes = []
            for _ in range(2):
                try:
                    api.chat("generation", [{"role": "user", "content": "Offline test"}], attempt)
                except APIRuntimeFailure as error:
                    codes.append(error.code)
            resumed = CheckpointedQwenAPI("offline-dummy-secret", temp, bounded)
            secret_absent = all("offline-dummy-secret" not in file.read_text(encoding="utf-8")
                                for file in temp.rglob("*.json"))
            record("checkpoint_call_ceiling_and_redaction", transport.calls == 1 and resumed.used_calls == 1
                   and secret_absent and codes == ["api_http_error", "api_call_ceiling_reached"],
                   {"fake_transport_calls": transport.calls, "started_calls_after_reinit": resumed.used_calls,
                    "failure_codes": codes, "dummy_key_redacted": secret_absent})
            active.check_or_write_runtime_snapshot(temp, {"version": "original"}, type("Ledger", (), {"events": []})())
            try:
                active.check_or_write_runtime_snapshot(temp, {"version": "changed"}, type("Ledger", (), {"events": []})())
                refused = False
            except ValueError:
                refused = True
            record("resume_refuses_changed_source_snapshot", refused, {"changed_snapshot_refused": refused})

        handlers = [node for node in ast.walk(ast.parse(inspect.getsource(local.execute_ledger)))
                    if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name)
                    and node.type.id == "Exception"]
        error_halts = any(
            any(isinstance(node, ast.Break) for node in ast.walk(handler))
            and any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == "attempt_invalid"
                    for node in ast.walk(handler))
            for handler in handlers)
        record("batch_error_halt_static_inspection", error_halts,
               {"method": "source inspection plus fake transport error propagation",
                "behavior": "API failure raises ExecutionFailure; execute_ledger records invalid attempt and breaks."})

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
        record("existing_offline_regression_suite", tests.wasSuccessful(), test_summary)

        changed = [name for name, previous in before.items()
                   if not (ROOT / name).is_file() or digest(ROOT / name) != previous]
        record("preservation", not changed, {"files_checked": len(before), "changed_files": changed})
        record("network_guard", not blocked_network, {"blocked_connection_attempts": len(blocked_network),
                                                       "real_API_calls": 0, "real_DVWA_requests": 0})
        result = {"schema": "p3-offline-audit-v1", "audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "scope": "offline audit, no runtime repairs or live pilot",
                  "plan": plan_path.relative_to(ROOT).as_posix(), "source_sha256": sources,
                  "audit_script_sha256": digest(Path(__file__)), "checks": checks,
                  "tests": test_summary, "findings": [row["finding"] for row in checks if not row["passed"] and "finding" in row],
                  "live_pilot_ready": False, "formal_ready": False,
                  "pending_live_work": ["fresh executor controls S1-S12", "isolated generation smoke",
                                        "33 applicable pilot runs", "independent review", "measured duration and quota"],
                  "real_API_calls": 0, "real_DVWA_requests": 0,
                  "preserved_file_count": len(before), "changed_preserved_files": changed}
        write_json(output / "audit.json", result)
        print(json.dumps({"evidence_directory": output.relative_to(ROOT).as_posix(), "checks": len(checks),
                          "findings": result["findings"], "tests": test_summary,
                          "preserved_file_count": len(before), "changed_files": changed,
                          "real_API_calls": 0, "real_DVWA_requests": 0}, indent=2))
        return 0 if tests.wasSuccessful() and not changed and not blocked_network else 1


if __name__ == "__main__":
    raise SystemExit(main())
