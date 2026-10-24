"""Offline P3 adapter checks: P2 parity, gates, checkpointing, and call limits."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_bounded_poolside_p3 as runner
from poolside_p3_runtime import CheckpointedPoolsideAPI
from qwen_api_runtime import APIRuntimeFailure
import analysis_v5_pilot_cases as fixtures
from test_qwen_api_p3_gates import context_for, positive_output
from test_poolside_smoke import Opener


class FakeAPI:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def chat(self, stage, messages, directory):
        self.calls += 1
        payload = CheckpointedPoolsideAPI.payload(stage, messages)
        return {"status": "ok", "content": json.dumps(self.output)}, {
            "request_sha256": runner.contract.request_hash(payload)}


class PoolsideP3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {row["case_id"]: row["input"] for row in fixtures.build_cases()[0]}

    def setUp(self):
        guard = patch("socket.socket.connect", side_effect=AssertionError("Unexpected network"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_invalid_evidence_never_calls_the_api(self):
        tested = 0
        for document in self.documents.values():
            if fixtures.eligible(document):
                continue
            api = FakeAPI({})
            ctx = context_for(document)
            result = runner.analysis_callback(api, Path("unused"), ctx)(document, ctx)
            self.assertEqual(api.calls, 0)
            self.assertEqual(result["analysis_status"], "runtime_invalid")
            tested += 1
        self.assertEqual(tested, 6)

    def test_rejected_fabricated_trial_never_becomes_valid_claim(self):
        document = self.documents["pilot-001"]
        output = positive_output(document)
        output["trial_assessments"][0]["trial"] = 99
        api = FakeAPI(output)
        ctx = context_for(document)
        result = runner.analysis_callback(api, Path("unused"), ctx)(document, ctx)
        self.assertEqual(result["analysis_status"], "analysis_error")
        self.assertIsNone(result["system_claim"])
        self.assertEqual(api.calls, 1)

    def test_semantically_wrong_valid_claim_is_preserved(self):
        document = self.documents["pilot-001"]
        api = FakeAPI(positive_output(document))
        ctx = context_for(document)
        result = runner.analysis_callback(api, Path("unused"), ctx)(document, ctx)
        self.assertEqual(result["system_claim"], "positive")
        self.assertEqual(result["analysis_status"], "completed")

    def test_analysis_payloads_match_all_18_validated_poolside_requests(self):
        p2 = runner.ROOT / "results/raw/poolside-p2/20261022T094120890211Z/plan.json"
        for row in json.loads(p2.read_text())["entries"]:
            payload = CheckpointedPoolsideAPI.payload("analysis", row["prepared"]["payload"]["messages"])
            self.assertEqual(payload, row["prepared"]["payload"])

    def test_checkpoint_is_written_before_request_and_call_ceiling_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = root / "attempts/test-unit/attempt-1"
            wire = {"model": runner.transport.MODEL, "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            class CheckingOpener(Opener):
                def open(self, request, timeout):
                    assert len(list(root.glob("attempts/**/request-started.json"))) == 1
                    return super().open(request, timeout)
            opener = CheckingOpener(wire)
            api = CheckpointedPoolsideAPI("test-secret", root, max_calls=1, max_seconds=120, opener=opener, clock=lambda: 0)
            api.chat("generation", [{"role": "user", "content": "test"}], attempt)
            with self.assertRaises(APIRuntimeFailure):
                api.chat("generation", [{"role": "user", "content": "test"}], attempt)
            self.assertEqual(len(opener.requests), 1)
            self.assertNotIn("test-secret", "".join(p.read_text() for p in root.rglob("*.json")))

    def test_deadline_blocks_before_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = Opener()
            api = CheckpointedPoolsideAPI("test-secret", Path(directory), max_calls=1, max_seconds=59,
                                         opener=opener, clock=lambda: 0)
            with self.assertRaises(APIRuntimeFailure):
                api.chat("analysis", [], Path(directory) / "attempts/test/attempt-1")
            self.assertEqual(opener.requests, [])

    def test_runtime_rejects_key_in_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = Opener()
            api = CheckpointedPoolsideAPI("test-secret", Path(directory), max_calls=1, max_seconds=120,
                                         opener=opener, clock=lambda: 0)
            with self.assertRaises(ValueError):
                api.chat("analysis", [{"role": "user", "content": "test-secret"}],
                         Path(directory) / "attempts/test/attempt-1")
            self.assertEqual(opener.requests, [])

    def test_offline_plan_check_does_not_load_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            experiment_id = "poolside-p3-offline-test"
            plan = json.loads(runner.PLAN_PATH.read_text(encoding="utf-8"))
            budget = json.loads(runner.BUDGET_PATH.read_text(encoding="utf-8"))
            plan["experiment_id"] = experiment_id
            budget["experiment_id"] = experiment_id
            plan_path = temp / "plan.json"
            budget_path = temp / "budget.json"
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            budget["plan_sha256"] = runner.digest(plan_path)
            # This temporary fixture models a newly bound plan. Keep the
            # committed historical budget and its source pins untouched.
            budget["runtime_source_sha256"] = {
                path: runner.digest(runner.ROOT / path)
                for path in budget["runtime_source_sha256"]
            }
            budget_path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
            prepare = runner.prepare
            with patch.object(runner, "EXPERIMENT_ID", experiment_id), \
                    patch.object(runner, "prepare", side_effect=lambda: prepare(plan_path, budget_path)), \
                    patch.object(runner.transport, "load_key", side_effect=AssertionError("Credential read")):
                result = runner.run()
        self.assertEqual(result["applicable_units"], 33)
        self.assertEqual(result["worst_case_api_calls"], 960)
        self.assertFalse(result["execution_started"])

    def test_committed_historical_budget_refuses_changed_runtime_source(self):
        with self.assertRaisesRegex(ValueError, "Frozen runtime source changed: dvwa/run_local_experiments.py"):
            runner.prepare()

    def test_execution_flags_are_required_before_creating_ledger_or_loading_key(self):
        with patch.object(runner.transport, "load_key", side_effect=AssertionError("Credential read")), \
                patch.object(runner.engine.local_runner.ExperimentLedger, "create", side_effect=AssertionError("Ledger created")):
            with self.assertRaises(ValueError):
                runner.run(execute=True)

    def test_callback_bindings_are_restored_after_failure(self):
        old_generation = runner.engine.make_generation_callback
        old_analysis = runner.engine.make_analysis_callback
        with self.assertRaises(RuntimeError):
            with runner.poolside_callbacks():
                self.assertIs(runner.engine.make_analysis_callback, runner.analysis_callback)
                raise RuntimeError("fixture failure")
        self.assertIs(runner.engine.make_generation_callback, old_generation)
        self.assertIs(runner.engine.make_analysis_callback, old_analysis)


if __name__ == "__main__":
    unittest.main()
