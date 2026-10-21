"""Offline checks for P2 reviewer-agreement metrics."""

from __future__ import annotations

import unittest

from development.assess_qwen_api_p2_results import calculate_metrics


class QwenAPIP2AssessmentTests(unittest.TestCase):
    def test_unresolved_cases_are_excluded_from_agreement_but_count_toward_coverage(self):
        cases = [
            {"technique": "boolean-based blind", "reference_decision": "positive",
             "model_decision": "positive", "scored": True, "agreement": True},
            {"technique": "boolean-based blind", "reference_decision": "negative",
             "model_decision": "negative", "scored": True, "agreement": True},
            {"technique": "time-based blind", "reference_decision": "inconclusive",
             "model_decision": None, "scored": False, "agreement": None},
        ]

        metrics = calculate_metrics(cases)

        self.assertEqual(metrics["case_count"], 3)
        self.assertEqual(metrics["scored_count"], 2)
        self.assertEqual(metrics["unresolved_count"], 1)
        self.assertEqual(metrics["coverage"], 0.666667)
        self.assertEqual(metrics["exact_agreement_count"], 2)
        self.assertEqual(metrics["exact_agreement_on_scored"], 1.0)
        self.assertEqual(metrics["by_technique"]["time-based blind"]["scored_count"], 0)
        self.assertIsNone(metrics["by_technique"]["time-based blind"]["exact_agreement_on_scored"])


if __name__ == "__main__":
    unittest.main()
