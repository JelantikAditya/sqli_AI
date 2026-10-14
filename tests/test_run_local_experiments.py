import sys
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
TEST_TEMP_ROOT = ROOT / "results" / "raw"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from experiment_protocol import load_protocol
from run_local_experiments import (
    ExperimentLedger,
    candidate_policy_violation,
    experiment_lock,
    execute_plan,
    json_bytes,
    planned_units,
    prepare_run_batch,
    sha256_file,
    validate_plan,
)


class LocalExperimentOrchestratorTests(unittest.TestCase):
    def write_plan(self, root, *, conditions=None, scenarios=None, replicates=None, dataset="pilot"):
        report = root / "results" / "zap" / "s1-r1.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"schema_version":"1.0.0","inputs":[]}', encoding="utf-8")
        plan = {
            "schema_version": "1.0.0",
            "experiment_id": "t05-test",
            "dataset": dataset,
            "condition_ids": conditions or ["A", "B"],
            "scenario_ids": scenarios or ["S1"],
            "replicates": replicates or [1],
            "discovery_reports": {"S1": {"1": "results/zap/s1-r1.json"}},
            "seclists_source_root": None,
        }
        path = root / "local-run-plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path, plan, report

    def test_ab_pair_has_same_seed_and_discovery_hash(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, report = self.write_plan(root)
            protocol = load_protocol()
            plan = validate_plan(plan_value, protocol, root)
            units = planned_units(plan, protocol, root)
            self.assertEqual(len(units), 2)
            self.assertEqual(units[0]["seed"], units[1]["seed"])
            self.assertEqual(units[0]["seed"], 42)
            self.assertEqual(units[0]["discovery_sha256"], sha256_file(report))
            self.assertEqual(units[0]["discovery_sha256"], units[1]["discovery_sha256"])
            self.assertEqual(units[0]["discovery_report"], units[1]["discovery_report"])

    def test_condition_c_marks_impossible_rows_excluded(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B", "C"], scenarios=["S10"])
            plan_value["seclists_source_root"] = "results/raw/seclists"
            plan = validate_plan(plan_value, load_protocol(), root)
            units = planned_units(plan, load_protocol(), root)
            self.assertEqual([unit["condition_id"] for unit in units], ["C", "B", "A"])
            excluded = next(unit for unit in units if unit["condition_id"] == "C")
            self.assertEqual(excluded["status"], "excluded")
            self.assertIsNone(excluded["planned_execution_index"])
            self.assertEqual(excluded["exclusion_reason"], "condition_does_not_include_scenario")

    def test_formal_dataset_is_blocked_while_protocol_is_pilot(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan, _ = self.write_plan(root, dataset="formal")
            with self.assertRaisesRegex(ValueError, "protocol is frozen"):
                validate_plan(plan, load_protocol(), root)

    def test_live_lock_blocks_a_second_orchestrator(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            directory = Path(temporary)
            with experiment_lock(directory):
                with self.assertRaisesRegex(RuntimeError, "Another orchestrator"):
                    with experiment_lock(directory):
                        pass

    def test_candidate_policy_blocks_mutation_and_caps_timing_delay(self):
        error_scenario = {"sqli_type": "error-based"}
        time_scenario = {"sqli_type": "time-based blind"}
        self.assertEqual(candidate_policy_violation({"payload": "1; DROP TABLE users"}, error_scenario),
                         "stacked_statement_separator")
        self.assertEqual(candidate_policy_violation({"payload": "1' OR SLEEP(1)"}, error_scenario),
                         "delay_outside_time_based_scenario")
        self.assertEqual(candidate_policy_violation({"payload": "1' AND SLEEP(3)"}, time_scenario),
                         "delay_exceeds_two_second_cap")
        self.assertEqual(candidate_policy_violation({"payload": "SLEEP(2)+SLEEP(2)"}, time_scenario),
                         "combined_delay_exceeds_two_second_cap")
        self.assertIsNone(candidate_policy_violation({"payload": "1' AND SLEEP(2)"}, time_scenario))

    def test_candidate_batch_deduplicates_and_assigns_unique_run_ids(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            directory = Path(temporary)
            batch_path = directory / "batch.json"
            payload = "1' AND 1=1 #"
            base = {"scenario_id": "S1", "source": "LLM", "rag_mode": "off",
                    "provenance": {"comparison_id": "pair", "model": "qwen2.5:7b",
                                   "prompt_version": "test", "temperature": 0, "seed": 42,
                                   "knowledge_base_id": None, "retrieved_chunk_ids": [],
                                   "retrieval_top_k": None}}
            batch = {"schema_version": "1.0.0", "candidates": [
                {**base, "candidate_id": "source-a", "payload": payload},
                {**base, "candidate_id": "source-b", "payload": payload},
                {**base, "candidate_id": "source-c", "payload": "1' AND 1=2 #"},
            ]}
            batch_path.write_text(json.dumps(batch), encoding="utf-8")
            unit = {"condition_id": "A"}
            normalized = directory / "runner-input.json"
            mapping = directory / "candidate-id-map.json"
            result = prepare_run_batch(batch_path, unit,
                                      {"scenario_id": "S1", "probe_kind": "single_error",
                                       "sqli_type": "error-based"},
                                      10, "run-a1b2", normalized, mapping)
            self.assertEqual(result["generated_candidate_count"], 3)
            self.assertEqual(result["unique_candidate_count"], 2)
            self.assertEqual(result["duplicate_candidate_count"], 1)
            normalized_ids = [item["candidate_id"] for item in json.loads(normalized.read_text())["candidates"]]
            self.assertEqual(normalized_ids, ["run-a1b2-c001", "run-a1b2-c002"])
            self.assertEqual(len(set(normalized_ids)), 2)

    def test_resume_marks_unknown_attempt_invalid_then_retries_fresh(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            plan_path, plan_value, _ = self.write_plan(root, conditions=["A"], scenarios=["S1"])
            first = execute_plan(plan_path, root=root)
            self.assertEqual(first["status_counts"]["planned"], 1)
            plan = validate_plan(plan_value, load_protocol(), root)
            plan_hash = hashlib.sha256(json_bytes({key: value for key, value in plan.items()
                                                   if not key.endswith("_resolved")})).hexdigest()
            protocol_hash = sha256_file(ROOT / "dvwa" / "local_experiment_protocol.json")
            data_directory = root / "results" / "raw" / "pilot" / "t05-test"
            ledger = ExperimentLedger.resume(data_directory, plan, plan_hash, protocol_hash, root)
            unit_id, state = next(iter(ledger.statuses().items()))
            ledger.append("attempt_started", **state["unit"],
                          run_id="run-interrupted", attempt_id="attempt-old", attempt_number=1,
                          reset_required=True, fresh_login_required=True, state_reused=False)

            calls = []

            def fake_executor(unit, attempt, plan, protocol, directory, fake_root):
                calls.append((unit["unit_id"], attempt["attempt_id"]))
                return {"metric_eligible": True, "candidate_budget": 10,
                        "valid_candidates_executed": 10, "database_reset_performed": True}

            blocked = execute_plan(plan_path, resume=True, execute=True, root=root,
                                   confirm_local_dvwa=True, confirm_database_reset=True,
                                   execute_one=fake_executor)
            self.assertIn(unit_id, blocked["blocked_by_invalid_runs"])
            self.assertEqual(calls, [])

            completed = execute_plan(plan_path, resume=True, retry_invalid=True, execute=True, root=root,
                                     confirm_local_dvwa=True, confirm_database_reset=True,
                                     execute_one=fake_executor)
            self.assertEqual(completed["status_counts"]["completed"], 1)
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][1], "attempt-old")
            events = [json.loads(line) for line in (data_directory / "ledger.jsonl").read_text().splitlines()]
            retry = next(event for event in events if event["event_type"] == "attempt_retried")
            self.assertFalse(retry["state_reused"])
            self.assertTrue(retry["reset_required"])

    def test_resume_rejects_code_or_schema_hash_drift(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            plan_path, plan_value, _ = self.write_plan(root, conditions=["A"], scenarios=["S1"])
            execute_plan(plan_path, root=root)
            plan = validate_plan(plan_value, load_protocol(), root)
            plan_hash = hashlib.sha256(json_bytes({key: value for key, value in plan.items()
                                                   if not key.endswith("_resolved")})).hexdigest()
            protocol_hash = sha256_file(ROOT / "dvwa" / "local_experiment_protocol.json")
            directory = root / "results" / "raw" / "pilot" / "t05-test"
            snapshot_path = directory / "plan.snapshot.json"
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["artifact_sha256"]["dvwa/run_local_experiments.py"] = "0" * 64
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "code or schema hashes differ"):
                ExperimentLedger.resume(directory, plan, plan_hash, protocol_hash, root)


    def test_unexpected_executor_error_closes_attempt_instead_of_leaving_it_running(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            path, _, _ = self.write_plan(root)
            def broken(*args):
                raise KeyError("candidate_id")
            result = execute_plan(path, execute=True, root=root, confirm_local_dvwa=True,
                                  confirm_database_reset=True, execute_one=broken)
            self.assertEqual(result["status_counts"]["invalid"], 1)
            self.assertEqual(result["status_counts"]["running"], 0)
            self.assertEqual(result["status_counts"]["planned"], 1)
            events = [json.loads(line) for line in Path(result["ledger_path"]).read_text().splitlines()]
            failure = events[-1]
            self.assertEqual(failure["failure_details"]["exception_type"], "KeyError")

    def test_generation_exclusion_continues_next_condition_without_retry(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            path, _, _ = self.write_plan(root)
            calls = []
            def executor(unit, *args):
                calls.append(unit["condition_id"])
                return {"metric_eligible": unit["condition_id"] != "A",
                        "budget_complete": unit["condition_id"] != "A",
                        "exclusion_reason": "incomplete_candidate_budget" if unit["condition_id"] == "A" else None}
            result = execute_plan(path, execute=True, root=root, confirm_local_dvwa=True,
                                  confirm_database_reset=True, execute_one=executor)
            self.assertEqual(calls, ["A", "B"])
            self.assertEqual(result["status_counts"]["excluded"], 1)
            self.assertEqual(result["status_counts"]["completed"], 1)
            self.assertEqual(result["status_counts"]["invalid"], 0)
            events = [json.loads(line) for line in Path(result["ledger_path"]).read_text().splitlines()]
            self.assertEqual(sum(event["event_type"] == "attempt_started" for event in events), 2)
            self.assertFalse(any(event["event_type"] == "attempt_retried" for event in events))


if __name__ == "__main__":
    unittest.main()
