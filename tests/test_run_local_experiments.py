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
    adaptive_manifest_args,
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

    def write_knowledge_snapshot(self, root):
        directory = root / "results" / "raw" / "candidate-knowledge"
        directory.mkdir(parents=True)
        corpus_path = directory / "corpus.json"
        corpus_path.write_text(json.dumps({"curation": {"researcher_review": "reviewed"}}), encoding="utf-8")
        corpus_sha = sha256_file(corpus_path)
        store = root / "data" / "vectorstore" / "candidate"
        store.mkdir(parents=True)
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0.0", "knowledge_base_id": "candidate-test",
            "corpus_kind": "structured-sqli-knowledge-v1", "purpose": "proposal-rag",
            "corpus_path": corpus_path.relative_to(root).as_posix(),
            "corpus_sha256": corpus_sha,
            "store_path": store.relative_to(root).as_posix(),
        }), encoding="utf-8")
        decision_path = directory / "review.json"
        decision_path.write_text(json.dumps({
            "decision": "approved-for-generation-only-preflight",
            "scope": "seeded-local-generation-diagnostic-only",
            "formal_experiment_approval": False,
            "candidate_corpus_sha256": corpus_sha,
        }), encoding="utf-8")
        return {
            "manifest_path": manifest_path.relative_to(root).as_posix(),
            "manifest_sha256": sha256_file(manifest_path),
            "corpus_path": corpus_path.relative_to(root).as_posix(),
            "corpus_sha256": corpus_sha,
            "review_decision_path": decision_path.relative_to(root).as_posix(),
            "review_decision_sha256": sha256_file(decision_path),
        }

    def write_formal_knowledge_snapshot(self, root):
        directory = root / "results" / "raw" / "formal-knowledge"
        directory.mkdir(parents=True)
        corpus_path = directory / "corpus.json"
        corpus_path.write_text(json.dumps({"curation": {"researcher_review": "pending"}}), encoding="utf-8")
        source_lock_path = directory / "sources.lock.json"
        source_lock_path.write_text(json.dumps({"revision": "fixture"}), encoding="utf-8")
        store = root / "data" / "vectorstore" / "formal-candidate"
        store.mkdir(parents=True)
        (store / "index.bin").write_bytes(b"fixed-index-bytes")
        corpus_sha = sha256_file(corpus_path)
        source_lock_sha = sha256_file(source_lock_path)
        manifest_path = store / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0.0", "knowledge_base_id": "formal-candidate",
            "corpus_kind": "structured-sqli-knowledge-v1", "purpose": "proposal-rag",
            "corpus_path": corpus_path.relative_to(root).as_posix(),
            "corpus_sha256": corpus_sha, "source_lock_sha256": source_lock_sha,
            "store_path": store.relative_to(root).as_posix(), "entry_count": 9,
        }), encoding="utf-8")
        index_hashes = {path.relative_to(root).as_posix(): sha256_file(path)
                        for path in store.rglob("*") if path.is_file()}
        decision_path = directory / "formal-decision.json"
        decision_path.write_text(json.dumps({
            "schema_version": "1.0.0", "decision": "approved-for-formal-use",
            "scope": "main-nine-entry-corpus-formal-use-after-u07-gates",
            "authority": {"role": "researcher", "basis": "explicit-user-approval"},
            "approved_snapshot": {"corpus_sha256": corpus_sha, "source_lock_sha256": source_lock_sha,
                                  "knowledge_base_id": "formal-candidate", "entry_count": 9,
                                  "index_file_sha256": index_hashes},
            "formal_execution_approval": False,
        }), encoding="utf-8")
        return {
            "manifest_path": manifest_path.relative_to(root).as_posix(),
            "manifest_sha256": sha256_file(manifest_path),
            "corpus_path": corpus_path.relative_to(root).as_posix(),
            "corpus_sha256": corpus_sha,
            "review_decision_path": decision_path.relative_to(root).as_posix(),
            "review_decision_sha256": sha256_file(decision_path),
            "source_lock_path": source_lock_path.relative_to(root).as_posix(),
            "source_lock_sha256": source_lock_sha,
            "index_file_sha256": index_hashes,
        }

    def write_pilot_knowledge_snapshot(self, root):
        snapshot = self.write_formal_knowledge_snapshot(root)
        formal_decision = json.loads((root / snapshot["review_decision_path"]).read_text(encoding="utf-8"))
        pilot_decision = {
            **formal_decision,
            "decision": "approved-for-pilot-use",
            "scope": "local-pilot-corpus-use-only",
            "candidate_corpus_sha256": snapshot["corpus_sha256"],
            "researcher_review_status": "reviewed",
            "formal_experiment_approval": False,
            "authority": {**formal_decision["authority"], "quote": "Approve this fixture for pilot use."},
        }
        decision_path = root / "results/raw/formal-knowledge/pilot-decision.json"
        decision_path.write_text(json.dumps(pilot_decision), encoding="utf-8")
        return {**snapshot, "review_decision_path": decision_path.relative_to(root).as_posix(),
                "review_decision_sha256": sha256_file(decision_path)}

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
            protocol = load_protocol()
            protocol["status"] = "pilot"
            with self.assertRaisesRegex(ValueError, "protocol is frozen"):
                validate_plan(plan, protocol, root)

    def test_knowledge_snapshot_is_hash_pinned_and_only_passed_to_condition_b(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B"], scenarios=["S3"])
            plan_value["discovery_reports"] = {"S3": {"1": "results/zap/s1-r1.json"}}
            plan_value["knowledge_snapshot"] = self.write_knowledge_snapshot(root)
            plan = validate_plan(plan_value, load_protocol(), root)
            self.assertEqual(plan["knowledge_snapshot_resolved"]["knowledge_base_id"], "candidate-test")
            self.assertEqual(adaptive_manifest_args(plan, {"condition_id": "A"}, root), [])
            self.assertEqual(adaptive_manifest_args(plan, {"condition_id": "B"}, root)[0], "--manifest")

    def test_knowledge_snapshot_hash_drift_blocks_plan_validation(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B"], scenarios=["S3"])
            plan_value["discovery_reports"] = {"S3": {"1": "results/zap/s1-r1.json"}}
            plan_value["knowledge_snapshot"] = self.write_knowledge_snapshot(root)
            corpus_path = root / plan_value["knowledge_snapshot"]["corpus_path"]
            corpus_path.write_text('{"curation":{"researcher_review":"reviewed"},"changed":true}',
                                   encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "corpus_path is missing or its hash changed"):
                validate_plan(plan_value, load_protocol(), root)

    def test_formal_receipt_pins_source_lock_and_every_chroma_file(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B"], scenarios=["S3"])
            plan_value["discovery_reports"] = {"S3": {"1": "results/zap/s1-r1.json"}}
            plan_value["knowledge_snapshot"] = self.write_formal_knowledge_snapshot(root)
            plan = validate_plan(plan_value, load_protocol(), root)
            self.assertEqual(plan["knowledge_snapshot_resolved"]["knowledge_base_id"], "formal-candidate")
            self.assertEqual(adaptive_manifest_args(plan, {"condition_id": "B"}, root)[0], "--manifest")

    def test_formal_receipt_rejects_chroma_file_hash_drift(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B"], scenarios=["S3"])
            plan_value["discovery_reports"] = {"S3": {"1": "results/zap/s1-r1.json"}}
            plan_value["knowledge_snapshot"] = self.write_formal_knowledge_snapshot(root)
            plan = validate_plan(plan_value, load_protocol(), root)
            index_key = next(path for path in plan_value["knowledge_snapshot"]["index_file_sha256"]
                             if path.endswith("index.bin"))
            index_path = root / index_key
            index_path.write_bytes(b"changed-index-bytes")
            with self.assertRaisesRegex(ValueError, "index_file_sha256 differs"):
                adaptive_manifest_args(plan, {"condition_id": "B"}, root)

    def test_pilot_receipt_reviews_pinned_snapshot_without_changing_formal_assets(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root)
            snapshot = self.write_pilot_knowledge_snapshot(root)
            plan_value["knowledge_snapshot"] = snapshot
            before = {path: sha256_file(path) for path in root.rglob("*") if path.is_file()}
            validate_plan(plan_value, load_protocol(), root)
            self.assertEqual(before, {path: sha256_file(path) for path in root.rglob("*") if path.is_file()})
            corpus = json.loads((root / snapshot["corpus_path"]).read_text(encoding="utf-8"))
            self.assertEqual(corpus["curation"]["researcher_review"], "pending")

    def test_pilot_receipt_rejects_missing_review_or_mismatched_index_attestation(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root)
            snapshot = self.write_pilot_knowledge_snapshot(root)
            plan_value["knowledge_snapshot"] = snapshot
            decision_path = root / snapshot["review_decision_path"]
            baseline = json.loads(decision_path.read_text(encoding="utf-8"))
            wrong_snapshot = json.loads(json.dumps(baseline["approved_snapshot"]))
            index_key = next(iter(wrong_snapshot["index_file_sha256"]))
            wrong_snapshot["index_file_sha256"][index_key] = "0" * 64
            for field, value in (("researcher_review_status", "pending"),
                                 ("authority", {**baseline["authority"], "quote": " "}),
                                 ("approved_snapshot", wrong_snapshot)):
                with self.subTest(field=field):
                    decision_path.write_text(json.dumps({**baseline, field: value}), encoding="utf-8")
                    # Even a newly pinned receipt must still attest the exact approved assets.
                    snapshot["review_decision_sha256"] = sha256_file(decision_path)
                    with self.assertRaisesRegex(ValueError, "must attest researcher review"):
                        validate_plan(plan_value, load_protocol(), root)

    def test_formal_plan_with_rag_requires_exact_index_hashes(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            _, plan_value, _ = self.write_plan(root, conditions=["A", "B"], dataset="formal")
            protocol = load_protocol()
            protocol["status"] = "frozen"
            with self.assertRaisesRegex(ValueError, "must pin the exact Chroma index file hashes"):
                validate_plan(plan_value, protocol, root)

    def test_non_pilot_corpus_approvals_block_pilot_execution(self):
        for fixture in (self.write_knowledge_snapshot, self.write_formal_knowledge_snapshot):
            with self.subTest(fixture=fixture.__name__), tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
                root = Path(temporary)
                plan_path, plan_value, _ = self.write_plan(root, conditions=["A", "B"], scenarios=["S3"])
                plan_value["discovery_reports"] = {"S3": {"1": "results/zap/s1-r1.json"}}
                plan_value["knowledge_snapshot"] = fixture(root)
                plan_path.write_text(json.dumps(plan_value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "decision=approved-for-pilot-use"):
                    execute_plan(plan_path, execute=True, confirm_local_dvwa=True,
                                 confirm_database_reset=True, root=root)
                self.assertFalse((root / "results/raw/pilot/t05-test").exists())

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

    def test_one_replicate_per_session_pauses_and_resumes_at_boundary(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            plan_path, plan_value, _ = self.write_plan(
                root, conditions=["A"], scenarios=["S1"], replicates=[1, 2])
            second_report = root / "results" / "zap" / "s1-r2.json"
            second_report.write_text('{"schema_version":"1.0.0","inputs":[]}', encoding="utf-8")
            plan_value["discovery_reports"]["S1"]["2"] = "results/zap/s1-r2.json"
            plan_path.write_text(json.dumps(plan_value), encoding="utf-8")
            calls = []

            def fake_executor(unit, attempt, plan, protocol, directory, fake_root):
                calls.append((unit["replicate"], attempt["attempt_id"]))
                return {"metric_eligible": True, "candidate_budget": 10,
                        "valid_candidates_executed": 10, "database_reset_performed": True}

            first_session = execute_plan(
                plan_path, execute=True, one_replicate_per_session=True, root=root,
                confirm_local_dvwa=True, confirm_database_reset=True,
                execute_one=fake_executor)

            self.assertEqual([replicate for replicate, _ in calls], [1])
            self.assertEqual(first_session["replicate_session"], {
                "status": "paused_at_replicate_boundary",
                "finished_replicate": 1,
                "next_replicate": 2,
            })

            second_session = execute_plan(
                plan_path, resume=True, execute=True, one_replicate_per_session=True, root=root,
                confirm_local_dvwa=True, confirm_database_reset=True,
                execute_one=fake_executor)

            self.assertEqual([replicate for replicate, _ in calls], [1, 2])
            self.assertEqual(second_session["status_counts"]["completed"], 2)
            self.assertEqual(second_session["replicate_session"]["status"], "plan_complete")
            events = [json.loads(line) for line in Path(first_session["ledger_path"]).read_text().splitlines()]
            pauses = [event for event in events if event["event_type"] == "execution_paused"]
            self.assertEqual(len(pauses), 1)
            self.assertEqual(pauses[0]["replicate"], 1)
            self.assertEqual(pauses[0]["next_replicate"], 2)

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
