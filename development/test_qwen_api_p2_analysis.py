"""Offline tests for the P2 Qwen API prompt adapter. No API calls are made."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))

import analysis_v5_pilot_cases as dataset
import analyze_response_v2 as contract
from qwen_api_p2_analysis import default_settings, parse, prepare


class QwenAPIP2AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows, _ = dataset.build_cases()
        cls.documents = {row["case_id"]: row["input"] for row in rows}

    def test_uses_explicit_v2_rules_and_no_rag_projection(self):
        document = self.documents["pilot-031"]
        prepared = prepare(document, default_settings())
        self.assertEqual(prepared["base_contract_version"], contract.PROMPT_VERSION)
        self.assertEqual(prepared["payload"]["model"], "Qwen3.8-27B")
        self.assertEqual(prepared["payload"]["max_tokens"], 2048)
        self.assertIn("identical valid exists/missing markers", prepared["payload"]["messages"][0]["content"])
        user_view = json.loads(prepared["payload"]["messages"][1]["content"])
        self.assertEqual(user_view["time_threshold_ms"], 1500)
        self.assertNotIn("reference_context", user_view)
        self.assertNotIn("pilot-031", prepared["payload"]["messages"][1]["content"])
        self.assertNotIn("ground_truth", prepared["payload"]["messages"][1]["content"])

    def test_missing_trial_is_represented_without_fabrication(self):
        document = copy.deepcopy(self.documents["pilot-031"])
        document["observations"] = [row for row in document["observations"] if row["trial"] != 2]
        prepared = prepare(document)
        view = json.loads(prepared["payload"]["messages"][1]["content"])
        self.assertEqual([row["trial"] for row in view["comparisons"]], [1, 3])
        self.assertEqual(view["required_trials"], [1, 2, 3])

    def test_runtime_invalid_and_baseline_invalid_are_blocked(self):
        document = copy.deepcopy(self.documents["pilot-001"])
        document.update(runtime_status="invalid", runtime_failure_code="network_error", observations=[])
        with self.assertRaises(ValueError):
            prepare(document)

        document = copy.deepcopy(self.documents["pilot-001"])
        document["baseline_valid"] = False
        with self.assertRaises(ValueError):
            prepare(document)

    def test_parser_preserves_model_verdict_without_executor_override(self):
        document = self.documents["pilot-031"]
        prepared = prepare(document)
        ids_by_trial = {}
        for row in document["observations"]:
            ids_by_trial.setdefault(row["trial"], []).append(row["observation_id"])
        assessments = [{"trial": trial, "outcome": "positive", "evidence_refs": ids_by_trial[trial]}
                       for trial in (1, 2, 3)]
        output = {
            "trial_assessments": assessments,
            "confirmation_summary": {"observed_trials": [1, 2, 3],
                                     "positive_trial_count": 3, "negative_trial_count": 0},
            "decision": "positive", "reason_code": "matched_delay",
            "reason": "Klaim model untuk fixture tes.",
            "evidence_refs": [row for trial in (1, 2, 3) for row in ids_by_trial[trial]],
            "feedback_action": "none",
        }
        result = parse(document, prepared, {"status": "ok", "content": json.dumps(output)})
        self.assertEqual(result["decision"], "positive")
        self.assertFalse(result.get("claim_override", False))


if __name__ == "__main__":
    unittest.main()
