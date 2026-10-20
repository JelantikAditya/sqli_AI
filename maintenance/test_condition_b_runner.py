"""Offline regression checks for the B recovery amendment; never calls DVWA or Ollama."""

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
sys.path.insert(0, str(ROOT / "tests"))

import run_local_experiments as runner
import test_run_local_experiments as fixture_module


class ConditionBRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "results/raw")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = fixture_module.LocalExperimentOrchestratorTests()
        self.snapshot = self.fixture.write_formal_knowledge_snapshot(self.root)
        self.index = self.root / "data/vectorstore/formal-candidate/index.bin"
        self.expected_bytes = self.index.read_bytes()
        self.amendment = {
            "applies_to_replicates": [3], "amendment_sha256": "a" * 64,
            "index_payload_resolved": {name: (self.root / name).read_bytes()
                                       for name in self.snapshot["index_file_sha256"]},
        }
        self.plan = {"knowledge_snapshot": self.snapshot,
                     "condition_b_runner_amendment_resolved": self.amendment}
        self.directory = self.root / "results/raw/formal/test"
        self.unit = {"unit_id": "test-b-s1-r3", "condition_id": "B", "replicate": 3}

    def prepare(self, attempt_id="attempt-1-offline"):
        return runner.prepare_condition_b_index(self.unit, {"attempt_id": attempt_id},
                                               self.plan, self.directory, self.root)

    def test_drift_is_backed_up_restored_verified_and_clean_index_is_not_copied(self):
        self.index.write_bytes(b"runtime-drift")
        result = self.prepare()
        receipt = runner.read_json(self.root / result["receipt_path"])
        self.assertEqual(result["status"], "restored-and-verified")
        self.assertEqual(self.index.read_bytes(), self.expected_bytes)
        self.assertEqual((self.root / receipt["preserved_active_backup"] / "index.bin").read_bytes(),
                         b"runtime-drift")
        self.assertEqual(receipt["index_file_sha256"], self.snapshot["index_file_sha256"])
        self.assertFalse(receipt["database_reset_performed"])
        self.assertEqual(receipt["probe_submissions"], 0)
        next_result = self.prepare("attempt-2-offline")
        self.assertEqual(next_result["status"], "verified-unchanged")
        self.assertIsNone(runner.read_json(self.root / next_result["receipt_path"])["preserved_active_backup"])

    def test_a_and_c_skip_every_index_operation(self):
        for condition in ("A", "C"):
            unit = {**self.unit, "condition_id": condition}
            self.assertIsNone(runner.prepare_condition_b_index(
                unit, {}, {"condition_b_runner_amendment_resolved": {}}, self.directory, self.root))
        self.assertFalse(self.directory.exists())

    def test_preserved_replicates_cannot_use_new_recovery_path(self):
        self.unit["replicate"] = 2
        with self.assertRaisesRegex(ValueError, "restricted to R3"):
            self.prepare()

    def test_unexpected_files_and_metadata_drift_require_manual_review(self):
        extra = self.index.parent / "unexpected.wal"
        extra.write_bytes(b"unknown-writer")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            self.prepare()
        extra.unlink()
        manifest = self.root / self.snapshot["manifest_path"]
        manifest.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest_path"):
            self.prepare()

    def test_bad_recovery_source_cannot_reach_executor(self):
        self.index.write_bytes(b"drift")
        name = next(name for name in self.amendment["index_payload_resolved"] if name.endswith("index.bin"))
        self.amendment["index_payload_resolved"][name] = b"unapproved-bytes"
        with self.assertRaisesRegex(ValueError, "Recovery source bytes"):
            self.prepare()
        self.assertEqual(self.index.read_bytes(), b"drift")

    def make_ledger(self):
        plan_path, value, _ = self.fixture.write_plan(self.root, conditions=["B"], scenarios=["S1", "S2"],
                                                     replicates=[3])
        value["knowledge_snapshot"] = self.snapshot
        value["discovery_reports"] = {scenario: {"3": "results/zap/s1-r1.json"}
                                      for scenario in ("S1", "S2")}
        protocol = runner.load_protocol()
        plan = runner.validate_plan(value, protocol, self.root)
        plan["condition_b_runner_amendment_resolved"] = self.amendment
        ledger = runner.ExperimentLedger.create(self.directory, plan, protocol, "a" * 64, "b" * 64, self.root)
        return plan, protocol, ledger

    def test_adjacent_b_runs_wait_for_recovery_before_executor(self):
        plan, protocol, ledger = self.make_ledger()
        calls = []

        def execute(unit, attempt, *args):
            self.assertEqual(self.index.read_bytes(), self.expected_bytes)
            calls.append(unit["scenario_id"])
            # Simulate Chroma persisting runtime bytes after retrieval.
            self.index.write_bytes(b"runtime-drift")
            return {"budget_complete": True}

        result = runner.execute_ledger(ledger, plan, protocol, self.directory, execute=True,
                                       retry_invalid=False, recovered=0, root=self.root,
                                       execute_one=execute)
        self.assertEqual(calls, ["S1", "S2"])
        self.assertEqual(result["status_counts"]["completed"], 2)
        self.assertEqual(result["status_counts"]["invalid"], 0)
        completed = [event for event in ledger.events if event["event_type"] == "attempt_completed"]
        self.assertEqual([event["condition_b_index_preflight"]["status"] for event in completed],
                         ["verified-unchanged", "restored-and-verified"])

    def test_recovery_failure_records_invalid_and_stops_before_executor(self):
        plan, protocol, ledger = self.make_ledger()
        (self.index.parent / "unexpected.wal").write_bytes(b"concurrent-writer")
        execute = Mock(side_effect=AssertionError("executor must not run"))
        result = runner.execute_ledger(ledger, plan, protocol, self.directory, execute=True,
                                       retry_invalid=False, recovered=0, root=self.root,
                                       execute_one=execute)
        execute.assert_not_called()
        self.assertEqual(result["status_counts"]["invalid"], 1)
        event = ledger.events[-1]
        self.assertFalse(event["database_reset_performed"])
        self.assertEqual(event["valid_candidates_executed"], 0)


class ConditionBAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "results/raw")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture = fixture_module.LocalExperimentOrchestratorTests()
        snapshot = fixture.write_formal_knowledge_snapshot(self.root)
        self.plan_path, value, _ = fixture.write_plan(self.root, conditions=["B"], replicates=[1, 2, 3], dataset="formal")
        value["knowledge_snapshot"] = snapshot
        value["discovery_reports"] = {"S1": {str(i): "results/zap/s1-r1.json" for i in (1, 2, 3)}}
        self.plan_path.write_text(json.dumps(value), encoding="utf-8")
        self.protocol = runner.load_protocol()
        self.plan = runner.validate_plan(value, self.protocol, self.root)
        self.code = self.root / "dvwa/run_local_experiments.py"
        self.code.parent.mkdir(parents=True)
        self.code.write_bytes(b"original-runner")
        before = runner.sha256_file(self.code)
        protocol_path = self.root / "dvwa/local_experiment_protocol.json"
        protocol_path.write_text(json.dumps(self.protocol), encoding="utf-8")
        release = self.root / self.protocol["formal_freeze_release"]["release_manifest_path"]
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_text("{}", encoding="utf-8")
        self.directory = self.root / "results/raw/formal" / value["experiment_id"]
        self.plan_hash = hashlib.sha256(runner.json_bytes({key: value for key, value in self.plan.items()
                                                         if not key.endswith("_resolved")})).hexdigest()
        self.protocol_hash = runner.sha256_file(protocol_path)
        self.ledger = runner.ExperimentLedger.create(self.directory, self.plan, self.protocol,
                                                    self.plan_hash, self.protocol_hash, self.root)
        for state in list(self.ledger.statuses().values()):
            unit = state["unit"]
            if unit["replicate"] < 3:
                self.ledger.append("attempt_started", **unit, attempt_id=f"r{unit['replicate']}")
                self.ledger.append("attempt_completed", unit_id=unit["unit_id"], attempt_id=f"r{unit['replicate']}")
        self.preserved = self.directory / "r1-evidence.json"
        self.preserved.write_text('{"evidence":"original"}', encoding="utf-8")
        inventory_path = self.directory / "preserved.json"
        inventory_path.write_text(json.dumps({"files": {
            self.preserved.relative_to(self.root).as_posix(): runner.sha256_file(self.preserved)}}), encoding="utf-8")
        archive_path = self.directory / "index.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name in snapshot["index_file_sha256"]:
                archive.write(self.root / name, name)
        self.code.write_bytes(b"patched-runner")
        prefix = self.ledger.path.read_bytes()
        self.receipt = {
            "schema_version": "1.0.0", "scope": "condition-b-index-recovery-r3",
            "decision": "approved-for-condition-b-runner-amendment", "runner_amendment_approval": True,
            "formal_execution_approval": False, "condition_ids": ["B"], "applies_to_replicates": [3],
            "preserve_replicates": [1, 2], "experiment_id": value["experiment_id"],
            "authority": {"role": "researcher", "basis": "explicit-user-approval", "quote": "fixture approval"},
            "formal_plan_path": self.plan_path.relative_to(self.root).as_posix(),
            "formal_plan_sha256": runner.sha256_file(self.plan_path),
            "protocol_sha256": runner.sha256_file(protocol_path),
            "release_manifest_path": release.relative_to(self.root).as_posix(),
            "release_manifest_sha256": runner.sha256_file(release),
            "runner_before_sha256": before, "runner_after_sha256": runner.sha256_file(self.code),
            "plan_snapshot_sha256": runner.sha256_file(self.directory / "plan.snapshot.json"),
            "index_archive_path": archive_path.relative_to(self.root).as_posix(),
            "index_archive_sha256": runner.sha256_file(archive_path),
            "preserved_history": {"ledger_prefix_bytes": len(prefix),
                                  "ledger_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
                                  "ledger_event_count": len(self.ledger.events),
                                  "inventory_path": inventory_path.relative_to(self.root).as_posix(),
                                  "inventory_sha256": runner.sha256_file(inventory_path)},
        }
        self.path = self.directory / "amendment.json"

    def validate(self):
        self.path.write_text(json.dumps(self.receipt), encoding="utf-8")
        return runner.validate_condition_b_runner_amendment(self.path, self.plan_path, self.plan,
                                                            self.protocol, self.root)

    def test_validation_preserves_snapshot_and_ledger_and_accepts_r3_suffix(self):
        before = {path: runner.sha256_file(path) for path in
                  (self.ledger.path, self.directory / "plan.snapshot.json", self.preserved)}
        result = self.validate()
        self.assertTrue(result["index_payload_resolved"])
        self.assertEqual(before, {path: runner.sha256_file(path) for path in before})
        self.ledger.append("formal_execution_authorized",
                           condition_b_runner_amendment=runner.condition_b_amendment_record(result))
        self.ledger.append("attempt_started", unit_id="t05-test-b-s1-r3", attempt_id="r3")
        self.validate()

    def test_replayed_r1_and_tampered_old_evidence_are_rejected(self):
        self.preserved.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            self.validate()
        self.preserved.write_text('{"evidence":"original"}', encoding="utf-8")
        self.ledger.append("attempt_started", unit_id="t05-test-b-s1-r1", attempt_id="replay")
        with self.assertRaisesRegex(ValueError, "new attempt"):
            self.validate()

    def test_unapproved_receipt_and_wrong_runner_hash_cannot_bypass_freeze(self):
        self.receipt["runner_amendment_approval"] = False
        with self.assertRaisesRegex(ValueError, "explicit B-only"):
            self.validate()
        self.receipt["runner_amendment_approval"] = True
        self.receipt["runner_after_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "active plan, protocol, release, or runner"):
            self.validate()

    def test_modified_ledger_prefix_is_rejected(self):
        self.ledger.path.write_bytes(self.ledger.path.read_bytes().replace(b"r1", b"xx", 1))
        with self.assertRaisesRegex(ValueError, "ledger prefix changed"):
            self.validate()

    def test_r3_attempt_requires_recorded_amendment_first(self):
        self.ledger.append("attempt_started", unit_id="t05-test-b-s1-r3", attempt_id="r3")
        with self.assertRaisesRegex(ValueError, "precedes its recorded runner amendment"):
            self.validate()

    def test_pilot_protocol_still_blocks_formal_execution(self):
        with self.assertRaisesRegex(ValueError, "protocol is frozen"):
            runner.validate_plan(self.plan, {**self.protocol, "status": "pilot"}, self.root)

    def test_resume_allows_only_approved_runner_difference_and_keeps_history(self):
        amendment = self.validate()
        before = self.ledger.path.read_bytes()
        snapshot_before = (self.directory / "plan.snapshot.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "code or schema hashes differ"):
            runner.ExperimentLedger.resume(self.directory, self.plan, self.plan_hash,
                                            self.protocol_hash, self.root)
        resumed = runner.ExperimentLedger.resume(self.directory, self.plan, self.plan_hash,
                                                 self.protocol_hash, self.root, runner_amendment=amendment)
        self.assertEqual(resumed.statuses()["t05-test-b-s1-r1"]["status"], "completed")
        self.assertEqual(resumed.statuses()["t05-test-b-s1-r2"]["status"], "completed")
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual((self.directory / "plan.snapshot.json").read_bytes(), snapshot_before)
        (self.root / "dvwa/local_experiment_protocol.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "code or schema hashes differ"):
            runner.ExperimentLedger.resume(self.directory, self.plan, self.plan_hash,
                                            self.protocol_hash, self.root, runner_amendment=amendment)


if __name__ == "__main__":
    unittest.main()
