"""Offline end-to-end confirmation policy checks; no live DVWA/model calls."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from confirmation_policy import classify_confirmations
from experiment_protocol import load_protocol
from run_local_experiments import ExecutionFailure, candidate_evidence_stats, validate_probe_evidence
from rag_pipeline import load_catalog
from validation_loop import LocalRuntimeFailure, main


class ConfirmationPolicyTests(unittest.TestCase):
    def run_executor(self, directory, scenario_id, signals, condition="A", fail_trial=None):
        source, rag_mode = {"A": ("LLM", "off"), "B": ("LLM", "on"),
                            "C": ("SecLists", "not_applicable")}[condition]
        candidate = {"candidate_id": "c1", "scenario_id": scenario_id,
                     "source": source, "rag_mode": rag_mode}
        if scenario_id == "S2":
            candidate.update(true_payload="true-probe", false_payload="false-probe")
        elif scenario_id == "S3":
            candidate["payload"] = "1 AND SLEEP(2)=0 #"
        else:
            candidate["payload"] = "candidate-probe"
        batch = directory / "batch.json"
        batch.write_text(json.dumps({"schema_version": "1.0.0", "candidates": [candidate]}), encoding="utf-8")
        log = directory / "validation.jsonl"

        class FakeClient:
            def __init__(self):
                self.http_request_calls = 0
                self.logical_probe_submissions = 0
                self.trial = 0

            def login_and_set_level(self, username, password, level):
                pass

            def verify_session_level(self, level):
                self.trial += 1
                if self.trial == fail_trial:
                    raise LocalRuntimeFailure("session_invalid")

            def submit_probe(self, scenario, value):
                self.logical_probe_submissions += 1
                self.http_request_calls += 1
                positive = signals[self.trial - 1]
                body = "First name: sample" if scenario_id == "S1" else "User ID exists in the database."
                elapsed = 10
                if scenario_id == "S1" and value != "1" and positive:
                    body = "You have an error in your SQL syntax"
                elif scenario_id == "S2" and value == "false-probe" and positive:
                    body = "User ID is missing from the database."
                elif scenario_id == "S3" and value == candidate["payload"] and positive:
                    elapsed = 1510
                return {"status": 200, "body": body, "elapsed_ms": elapsed,
                        "body_sha256": "a" * 64}

        client = FakeClient()
        argv = ["validation_loop.py", "--scenario", scenario_id, "--payload-file", str(batch),
                "--output", str(log), "--run-id", "run1", "--attempt-id", "attempt1",
                "--experiment-id", "test-policy", "--condition-id", condition, "--confirm-local-dvwa"]
        with patch("sys.argv", argv), patch("validation_loop.DvwaClient", return_value=client), \
                patch("validation_loop.load_local_env_file", return_value={}), \
                patch("validation_loop.time.sleep"), redirect_stdout(io.StringIO()):
            main()
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        return records, client

    def test_executor_three_confirmations_per_candidate_across_techniques_and_conditions(self):
        validator = Draft202012Validator(json.loads((ROOT / "schemas/candidate-evidence.schema.json").read_text()))
        for scenario_id in ("S1", "S2", "S3"):
            for condition in ("A", "B", "C"):
                for count in range(4):
                    with self.subTest(scenario=scenario_id, condition=condition, count=count):
                        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
                            records, client = self.run_executor(Path(temporary), scenario_id,
                                [i < count for i in range(3)], condition)
                        summaries = [r for r in records if r["record_type"] == "candidate_evidence"]
                        self.assertEqual(len(summaries), 1)
                        summary = summaries[0]
                        validator.validate(summary)
                        self.assertEqual(summary["valid_confirmation_count"], 3)
                        self.assertEqual(summary["positive_confirmation_count"], count)
                        self.assertEqual(summary["confirmed_success"], count == 3)
                        self.assertIsNone(summary["qwen_claim"])
                        self.assertEqual(client.trial, 3)
                        self.assertEqual(client.logical_probe_submissions, 6 if scenario_id == "S1" else 9)
                        unit = {"condition_id": condition, "scenario_id": scenario_id, "replicate": 1,
                                "source": summary["payload_source"], "rag_mode": summary["rag_mode"]}
                        stats = candidate_evidence_stats(records, unit,
                            {"run_id": "run1", "attempt_id": "attempt1"}, {"c1"})
                        self.assertEqual(stats["confirmed_success_count"], int(count == 3))
                        self.assertEqual(stats["mixed_evidence_count"], int(count in (1, 2)))

    def test_runtime_failure_invalidates_candidate_despite_earlier_positive_confirmation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            records, client = self.run_executor(Path(temporary), "S1", [True, True, True], fail_trial=2)
        summary = next(r for r in records if r["record_type"] == "candidate_evidence")
        self.assertEqual(summary["evidence_status"], "RUNTIME_INVALID")
        self.assertEqual(summary["valid_confirmation_count"], 1)
        self.assertIsNone(summary["confirmed_success"])
        self.assertEqual(client.trial, 2)
        failure = next(r for r in records if r["record_type"] == "runtime_failure")
        self.assertFalse(failure["attack_failure"])
        self.assertFalse(any(r["record_type"] == "run_end" for r in records))

    def test_probe_ledger_rejects_missing_baseline_duplicate_or_wrong_attempt(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            records, _ = self.run_executor(Path(temporary), "S1", [False, False, False])
        scenario = load_catalog()["scenarios"][0]
        unit = {"scenario_id": "S1", "condition_id": "A", "source": "LLM", "rag_mode": "off", "replicate": 1}
        attempt = {"run_id": "run1", "attempt_id": "attempt1"}
        validate_probe_evidence(records, scenario, unit, attempt, {"c1"}, "test-policy")
        baseline = next(r for r in records if r.get("payload_role") == "baseline")
        missing = [r for r in records if r is not baseline]
        duplicate = records + [baseline]
        tampered = copy.deepcopy(records)
        next(r for r in tampered if r.get("record_type") == "payload")["attempt_id"] = "another-attempt"
        for changed, code in ((missing, "probe_evidence_incomplete"),
                              (duplicate, "duplicate_probe_evidence"),
                              (tampered, "probe_evidence_context_mismatch")):
            with self.subTest(code=code), self.assertRaisesRegex(ExecutionFailure, code):
                validate_probe_evidence(changed, scenario, unit, attempt, {"c1"}, "test-policy")

    def test_runner_rejects_tampered_success_and_missing_candidate_summary(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            records, _ = self.run_executor(Path(temporary), "S1", [True, True, False])
        unit = {"condition_id": "A", "scenario_id": "S1", "replicate": 1, "source": "LLM", "rag_mode": "off"}
        attempt = {"run_id": "run1", "attempt_id": "attempt1"}
        changed = copy.deepcopy(records)
        summary = next(r for r in changed if r["record_type"] == "candidate_evidence")
        summary["confirmed_success"] = True
        with self.assertRaisesRegex(ExecutionFailure, "semantics_mismatch"):
            candidate_evidence_stats(changed, unit, attempt, {"c1"})
        with self.assertRaisesRegex(ExecutionFailure, "count_mismatch"):
            candidate_evidence_stats([r for r in records if r["record_type"] != "candidate_evidence"], unit, attempt, {"c1"})
        changed = copy.deepcopy(records)
        next(r for r in changed if r["record_type"] == "decision")["attempt_id"] = "other-attempt"
        with self.assertRaisesRegex(ExecutionFailure, "context_mismatch"):
            candidate_evidence_stats(changed, unit, attempt, {"c1"})

    def test_protocol_rejects_threshold_changes_and_extra_rounds(self):
        changes = {"success_requires_positive_confirmations": 2,
                   "additional_confirmation_rounds": 1,
                   "mixed_evidence_policy": "exclude-from-denominator"}
        for field, value in changes.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
                protocol = load_protocol()
                protocol["validation"][field] = value
                path = Path(temporary) / "protocol.json"
                path.write_text(json.dumps(protocol), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Require 3/3"):
                    load_protocol(path)

    def test_partial_extra_and_duplicate_like_trial_numbers_are_not_success(self):
        for results in ({1: True}, {1: True, 2: True},
                        {1: True, 2: True, 3: True, 4: True}, {2: True, 3: True, 4: True}):
            self.assertEqual(classify_confirmations(results)["evidence_status"], "INCOMPLETE_CONFIRMATIONS")
            self.assertIsNone(classify_confirmations(results)["confirmed_success"])


if __name__ == "__main__":
    unittest.main()
