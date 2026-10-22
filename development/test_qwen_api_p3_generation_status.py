"""Regressions for rejected generator results reaching the adaptive loop."""

import copy
import json
from pathlib import Path
import unittest

import run_qwen_api_experiments as active
import adaptive_s1_loop
import analyze_response
import test_qwen_api_p3_gates as gate_tests
from test_qwen_api_p3_gates import context_for, positive_output


class GenerationAPI:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = 0

    def chat(self, stage, messages, directory):
        assert stage == "generation"
        self.calls += 1
        return {"status": "ok", "finish_reason": "stop", "content": next(self.contents)}, {
            "request_sha256": "a" * 64}


class P3GenerationStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gate_tests.P3AnalysisGateTests.setUpClass()
        cls.document = gate_tests.P3AnalysisGateTests.documents["pilot-001"]
        cls.scenario = next(s for s in active.load_catalog()["scenarios"] if s["scenario_id"] == "S1")
        cls.config, _ = active.load_config()
        cls.baseline = {"http_status": 200, "elapsed_ms": 4, "diagnostics": [],
                        "content_markers": ["benign_record"], "technique": "error-based"}

    def callback(self, api):
        return active.make_generation_callback(api, Path("unused-offline"), self.scenario,
                                               None, self.baseline, self.config)

    def test_policy_rejected_candidate_always_carries_status(self):
        response = json.dumps({"candidates": [{"payload": "1' UNION SELECT 1"}]})
        api = GenerationAPI([response])
        candidate, audit = self.callback(api)(None, [], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(audit["status"], "no_valid_distinct_candidate")
        self.assertEqual(audit["rejection_code"], "no_valid_distinct_candidate")

    def test_malformed_json_always_carries_status(self):
        candidate, audit = self.callback(GenerationAPI(["not JSON"]))(None, [], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(audit["status"], "invalid_candidate_format")

    def test_duplicate_candidate_always_carries_status(self):
        response = json.dumps({"candidates": [{"payload": "101'"}]})
        candidate, audit = self.callback(GenerationAPI([response]))(None, ["1'"], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(audit["status"], "no_valid_distinct_candidate")
        self.assertEqual(audit["suggestions"][0]["status"], "duplicate_structure")

    def test_rejection_exhausts_bounded_retries_without_observation_or_exception(self):
        api = GenerationAPI(["bad JSON"] * 3)
        generate = self.callback(api)
        def forbidden(*_args):
            self.fail("Rejected generation must not execute a candidate or call analysis")
        result = adaptive_s1_loop.run_loop(
            context_for(self.document), generate, forbidden, forbidden, budget=10,
            slot_limit=10, confirmations=3, generation_retries=2,
            database_reset_performed=True, generate_with_retry=generate)
        self.assertEqual(api.calls, 3)
        self.assertEqual(result["stop_reason"], "generation_exhausted")
        self.assertEqual(result["candidate_records"], [])

    def test_rejection_after_valid_candidate_returns_incomplete_run_instead_of_crashing(self):
        good = json.dumps({"candidates": [{"payload": "1'"}]})
        api = GenerationAPI([good, "bad JSON", "bad JSON", "bad JSON"])
        generate = self.callback(api)
        def analyze(document, ctx):
            output = positive_output(document)
            output.pop("confirmation_summary")
            return analyze_response.normalize_analysis(document, output, ctx)
        result = adaptive_s1_loop.run_loop(
            context_for(self.document), generate, lambda *_args: copy.deepcopy(self.document), analyze,
            budget=2, slot_limit=2, confirmations=3, generation_retries=2,
            database_reset_performed=True, generate_with_retry=generate)
        self.assertEqual(api.calls, 4)
        self.assertEqual(result["stop_reason"], "generation_exhausted")
        self.assertEqual(len(result["candidate_records"]), 1)
        self.assertEqual(result["run_summary"]["system_decision"], "not_evaluable")
        self.assertFalse(result["run_summary"]["binary_decision_eligible"])


if __name__ == "__main__":
    unittest.main()
