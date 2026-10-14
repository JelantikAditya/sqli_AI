"""Known-result abstention fixtures for T01, not measured experiment data."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from analyze_response import normalize_analysis, summarize_run
from experiment_protocol import load_protocol
from rag_pipeline import load_catalog
from run_decision_evaluator import summarize_fpr_replicate


class RunDecisionPolicyTests(unittest.TestCase):
    def summary(self, scenario_id, claim, *, condition="A", replicate=1, runtime_invalid=False):
        scenario = next(s for s in load_catalog()["scenarios"] if s["scenario_id"] == scenario_id)
        roles = {"error-based": ("baseline", "candidate"),
                 "boolean-based blind": ("baseline", "true_condition", "false_condition"),
                 "time-based blind": ("baseline", "candidate", "no_delay_control")}[scenario["sqli_type"]]
        observations = []
        for trial in (1, 2, 3):
            for role in roles:
                observations.append({"observation_id": f"obs-{len(observations)+1:03d}", "trial": trial,
                    "role": role, "http_status": 200, "elapsed_ms": 10, "response_sha256": "a" * 64,
                    "diagnostics": [], "content_markers": []})
        evidence = {"schema_version": "1.0.0", "technique": scenario["sqli_type"],
            "injection_point": {k: scenario[k] for k in ("method", "input_path", "result_path", "parameter")},
            "runtime_status": "invalid" if runtime_invalid else "valid",
            "baseline_valid": not runtime_invalid, "time_threshold_ms": 1500, "observations": observations}
        reasons = {"error-based": ("new_database_diagnostic", "no_new_database_diagnostic"),
                   "boolean-based blind": ("boolean_difference", "no_boolean_difference"),
                   "time-based blind": ("matched_delay", "no_matched_delay")}[scenario["sqli_type"]]
        output = None if runtime_invalid else {"decision": claim,
            "reason_code": reasons[0] if claim == "positive" else reasons[1] if claim == "negative" else "insufficient_evidence",
            "reason": "Synthetic fixture.", "evidence_refs": [o["observation_id"] for o in observations],
            "feedback_action": "revise_candidate"}
        context = {"experiment_id": "fixture", "run_id": f"run-{scenario_id}", "attempt_id": "attempt-1",
            "candidate_id": "c1", "scenario_id": scenario_id, "replicate": replicate,
            "condition_id": condition, "source": "LLM", "rag_mode": "off" if condition == "A" else "on"}
        return summarize_run([normalize_analysis(evidence, output, context)], 1)

    def accounting(self, summaries, **kwargs):
        return summarize_fpr_replicate(summaries, experiment_id="fixture", condition_id="A",
                                      replicate=1, candidate_budget=1, **kwargs)

    def test_abstention_withholds_primary_even_when_decided_only_fpr_is_defined(self):
        result = self.accounting([self.summary("S10", "positive"), self.summary("S11", "negative"),
                                  self.summary("S12", "inconclusive")])
        self.assertEqual((result["FP"], result["TN"], result["inconclusive_units"]), (1, 1, 1))
        self.assertAlmostEqual(result["decision_coverage"], 2/3)
        self.assertEqual(result["diagnostic_decided_only_fpr"], 0.5)
        self.assertIsNone(result["primary_fpr"])
        self.assertFalse(result["primary_summary_eligible"])
        self.assertEqual(result["status"], "inconclusive")

    def test_all_binary_valid_units_produce_known_fpr(self):
        result = self.accounting([self.summary("S10", "positive"), self.summary("S11", "negative"),
                                  self.summary("S12", "negative")])
        self.assertEqual((result["FP"], result["TN"]), (1, 2))
        self.assertAlmostEqual(result["primary_fpr"], 1/3)
        self.assertEqual(result["decision_coverage"], 1)
        self.assertTrue(result["primary_summary_eligible"])

    def test_all_inconclusive_does_not_report_zero_fpr(self):
        result = self.accounting([self.summary(s, "inconclusive") for s in ("S10", "S11", "S12")])
        self.assertEqual((result["FP"], result["TN"]), (0, 0))
        self.assertEqual(result["inconclusive_units"], 3)
        self.assertEqual(result["decision_coverage"], 0)
        self.assertIsNone(result["primary_fpr"])
        self.assertIsNone(result["diagnostic_decided_only_fpr"])

    def test_runtime_invalid_and_missing_units_remain_in_planned_coverage(self):
        invalid = self.summary("S12", "negative", runtime_invalid=True)
        result = self.accounting([self.summary("S10", "negative"), invalid])
        self.assertEqual(result["planned_negative_units"], 3)
        self.assertEqual(result["TN"], 1)
        self.assertEqual(result["not_evaluable_units"], 1)
        self.assertEqual(result["missing_scenario_ids"], ["S11"])
        self.assertAlmostEqual(result["decision_coverage"], 1/3)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["primary_fpr"])

    def test_empty_observed_group_is_incomplete_rather_than_zero(self):
        result = self.accounting([])
        self.assertEqual(result["missing_scenario_ids"], ["S10", "S11", "S12"])
        self.assertIsNone(result["primary_fpr"])
        self.assertIsNone(result["diagnostic_decided_only_fpr"])

    def test_expected_technique_subset_is_explicit(self):
        result = self.accounting([self.summary("S10", "negative")], scenario_ids=("S10",))
        self.assertEqual(result["planned_negative_units"], 1)
        self.assertEqual(result["primary_fpr"], 0)

    def test_accounting_rejects_duplicates_cross_conditions_replicates_and_wrong_budget(self):
        unit = self.summary("S10", "negative")
        cases = [[unit, copy.deepcopy(unit)], [self.summary("S10", "negative", condition="B")],
                 [self.summary("S10", "negative", replicate=2)], [self.summary("S1", "negative")]]
        for summaries in cases:
            with self.subTest(summaries=[s["context"] for s in summaries]), self.assertRaises(ValueError):
                self.accounting(summaries)
        with self.assertRaises(ValueError):
            summarize_fpr_replicate([unit], experiment_id="fixture", condition_id="A", replicate=1, candidate_budget=10)
        with self.assertRaises(ValueError):
            self.accounting([], scenario_ids=("S10", "S10"))

    def test_protocol_rejects_imputing_negatives_retry_and_incomplete_primary_fpr(self):
        for field, value in (("negative", "no-positive-even-if-inconclusive"),
                             ("inconclusive_retry", "until-binary")):
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
                protocol = load_protocol()
                protocol["run_decision"][field] = value
                path = Path(temporary) / "protocol.json"
                path.write_text(json.dumps(protocol), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Preserve inconclusive"):
                    load_protocol(path)
        for field in ("fpr_requires_all_planned_negative_decisions", "fpr_report_decision_coverage"):
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
                protocol = load_protocol()
                protocol["metrics"][field] = False
                path = Path(temporary) / "protocol.json"
                path.write_text(json.dumps(protocol), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Preserve inconclusive"):
                    load_protocol(path)


if __name__ == "__main__":
    unittest.main()
