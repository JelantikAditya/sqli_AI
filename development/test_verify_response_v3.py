"""Offline contracts for independent evidence checks and conservative combination."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hybrid_validation_v3 as validation
import verify_response_v3 as gate


class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, labels = validation.new_cases()
        cls.labels = {r["case_id"]: r for r in labels}

    def raw_record(self, index=0, claim="positive"):
        case = self.cases[index]
        roles = gate.ROLES[case["input"]["technique"]]
        label = self.labels[case["case_id"]]
        refs = {trial: [o["observation_id"] for o in case["input"]["observations"]
                        if o["trial"] == trial and o["role"] in roles] for trial in map(int, label["expected_trials"])}
        output = {"decision": claim,
                  "reason_code": gate.REASONS[case["input"]["technique"]].get(claim, "insufficient_evidence"),
                  "reason": "Offline model fixture; may deliberately disagree with measurements.",
                  "evidence_refs": [ref for group in refs.values() for ref in group],
                  "feedback_action": "none" if claim == "positive" else "revise_candidate",
                  "trial_assessments": [{"trial": trial, "outcome": label["expected_trials"][str(trial)],
                                         "evidence_refs": group} for trial, group in refs.items()]}
        return validation.model.frozen.normalize_analysis(case["input"], output, case["context"],
                                                          {"raw_model_content": json.dumps(output)})

    def test_verifier_matches_hand_declared_fixture_decisions_and_trials(self):
        for case in self.cases:
            label = self.labels[case["case_id"]]
            result = gate.verify(case["input"])
            self.assertEqual(result["decision"], label["expected_claim"] or "not_evaluable")
            if label["expected_claim"] is not None:
                self.assertEqual({str(t["trial"]): t["outcome"] for t in result["trial_assessments"]}, label["expected_trials"])

    def test_binary_agreement_truth_table(self):
        expected = {0: {"positive": "positive", "negative": "inconclusive", "inconclusive": "inconclusive"},
                    1: {"positive": "inconclusive", "negative": "negative", "inconclusive": "inconclusive"},
                    2: {"positive": "inconclusive", "negative": "inconclusive", "inconclusive": "inconclusive"}}
        for index, claims in expected.items():
            for raw, combined in claims.items():
                self.assertEqual(gate.combine(self.raw_record(index, raw))["combined"]["decision"], combined)

    def test_raw_record_is_preserved_even_when_claim_is_blocked(self):
        record = self.raw_record(1, "positive")
        before = copy.deepcopy(record)
        result = gate.combine(record)
        self.assertEqual(record, before)
        self.assertEqual(result["llm_record"], before)
        self.assertEqual(result["llm_record_sha256"], gate.digest(before))
        self.assertEqual(result["combined"]["decision"], "inconclusive")
        self.assertEqual(result["llm_record"]["system_claim"], "positive")

    def test_raw_reason_code_is_preserved_separately(self):
        record = self.raw_record()
        record["model_output"]["reason_code"] = "insufficient_evidence"
        result = gate.combine(record)
        self.assertEqual(result["llm_record"]["model_output"]["reason_code"], "insufficient_evidence")
        self.assertEqual(result["combined"]["reason_code"], "new_database_diagnostic")
        self.assertFalse(result["combined"]["model_explanation_verified"])

    def test_decimal_boundary_is_not_rounded_below_threshold(self):
        case = self.cases[15]
        self.assertLess(2048.2 - 548.2, 1500)
        result = gate.verify(case["input"])
        self.assertEqual(result["decision"], "positive")
        self.assertEqual([r["candidate_minus_control_ms"] for r in result["trial_assessments"]], ["1500.0"] * 3)
        self.assertEqual(gate.verify(self.cases[16]["input"])["decision"], "negative")

    def test_matched_markers_and_valid_404_are_required(self):
        self.assertEqual(gate.verify(self.cases[10]["input"])["decision"], "positive")
        self.assertEqual(gate.verify(self.cases[17]["input"])["decision"], "negative")
        self.assertEqual(gate.verify(self.cases[19]["input"])["decision"], "negative")

    def test_missing_control_abstains_instead_of_becoming_negative(self):
        document = copy.deepcopy(self.cases[10]["input"])
        document["observations"] = [o for o in document["observations"] if not (o["trial"] == 1 and o["role"] == "no_delay_control")]
        result = gate.verify(document)
        self.assertEqual(result["decision"], "inconclusive")
        self.assertEqual(result["status"], "incomplete")

    def test_duplicate_observation_and_role_are_rejected(self):
        document = copy.deepcopy(self.cases[0]["input"])
        document["observations"][1]["observation_id"] = document["observations"][0]["observation_id"]
        self.assertEqual(gate.verify(document)["status"], "input_invalid")
        document = copy.deepcopy(self.cases[0]["input"])
        document["observations"][1]["role"] = "baseline"
        self.assertEqual(gate.verify(document)["status"], "input_invalid")

    def test_null_and_extra_trials_do_not_establish_a_binary_decision(self):
        document = copy.deepcopy(self.cases[0]["input"])
        document["observations"][1]["elapsed_ms"] = None
        self.assertEqual(gate.verify(document)["decision"], "inconclusive")
        document = copy.deepcopy(self.cases[0]["input"])
        for observation in copy.deepcopy(document["observations"][:2]):
            observation["trial"] = 4
            observation["observation_id"] = f"obs-{len(document['observations']) + 1:03d}"
            document["observations"].append(observation)
        self.assertEqual(gate.verify(document)["decision"], "inconclusive")

    def test_runtime_invalid_remains_not_evaluable(self):
        case = self.cases[-1]
        record = validation.model.frozen.normalize_analysis(case["input"], None, case["context"])
        self.assertEqual(gate.combine(record)["combined"]["decision"], "not_evaluable")

    def test_model_failure_cannot_be_rescued_by_positive_rules(self):
        case = self.cases[0]
        record = validation.model.frozen.normalize_analysis(case["input"], None, case["context"])
        result = gate.combine(record)
        self.assertEqual(result["verification"]["decision"], "positive")
        self.assertEqual(result["combined"]["decision"], "inconclusive")

    def test_unknown_refs_and_mismatched_input_hash_abstain(self):
        record = self.raw_record()
        record["model_output"]["evidence_refs"].append("obs-999")
        self.assertEqual(gate.combine(record)["combined"]["decision"], "inconclusive")
        record = self.raw_record()
        record["audit"]["input_sha256"] = "0" * 64
        self.assertFalse(gate.combine(record)["combined"]["model_usable"])

    def test_non_finite_and_target_label_inputs_are_rejected(self):
        document = copy.deepcopy(self.cases[0]["input"])
        document["time_threshold_ms"] = float("nan")
        self.assertEqual(gate.verify(document)["status"], "input_invalid")
        document = copy.deepcopy(self.cases[0]["input"])
        document["expected_claim"] = "positive"
        self.assertEqual(gate.verify(document)["status"], "input_invalid")

    def test_verification_does_not_depend_on_evaluator_context(self):
        record = self.raw_record()
        before = gate.combine(record)["verification"]
        record["context"].update(scenario_id="S12", condition_id="B", rag_mode="on")
        self.assertEqual(gate.combine(record)["verification"], before)

    def test_metrics_report_abstention_cost_on_negative_fixture(self):
        record = self.raw_record(1, "positive")
        row = {"expected_claim": "negative", "hybrid": gate.combine(record)}
        raw = validation.metrics([row], "raw_qwen_v2")
        combined = validation.metrics([row], "combined")
        self.assertEqual(raw["false_positive_on_negative_fixtures"], 1)
        self.assertEqual(combined["false_positive_on_negative_fixtures"], 0)
        self.assertEqual(combined["abstention_on_negative_fixtures"], 1)
        self.assertEqual(combined["negative_fixture_binary_coverage_count"], 0)

    def test_prepare_freezes_exact_requests_without_model_calls(self):
        if not (Path(__file__).resolve().parents[1] / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json").is_file():
            self.skipTest("Requires the ignored private formal-review source inventory.")
        temporary_root = validation.ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root, prefix="hybrid-v3-test-") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(temporary_root.resolve()))
            output = Path(directory) / "prepared"
            with patch.object(validation.model.v1, "post_ollama", side_effect=AssertionError("Unexpected inference")):
                validation.prepare(output)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["planned_model_calls"], 20)
            self.assertEqual(manifest["opened_regression_records"], 27)
            self.assertTrue(all(validation.pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()))


if __name__ == "__main__":
    unittest.main()
