"""Offline checks for the development contract and preservation of model failures."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

import analyze_response_v1 as v1
import analyze_response_v2 as v2
import response_analysis_validation_v2 as validation


class DevelopmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.labels = validation.new_cases()

    def output(self, case):
        document = case["input"]
        signals = v1.frozen.trial_rule_signals(document)
        refs = v1.frozen.comparison_observation_ids(document)
        assessments = [{"trial": trial, "outcome": "positive" if signal else "negative",
                        "evidence_refs": sorted(refs[trial])} for trial, signal in signals.items()]
        positives = sum(signals.values())
        claim = {0: "negative", 3: "positive"}.get(positives, "inconclusive") if set(signals) == {1, 2, 3} else "inconclusive"
        codes = dict(zip(("positive", "negative"), v2.REASON_CODES[document["technique"]]))
        return {"trial_assessments": assessments,
                "confirmation_summary": {"observed_trials": sorted(signals), "positive_trial_count": positives,
                                         "negative_trial_count": len(signals) - positives},
                "decision": claim, "reason_code": codes.get(claim, "insufficient_evidence"),
                "reason": "Offline fixture for parser/audit validation.",
                "evidence_refs": sorted(set().union(*refs.values())),
                "feedback_action": "none" if claim == "positive" else "revise_candidate"}

    def parse(self, case, output):
        raw = json.dumps(output)
        response = {"model": v2.MODEL, "done": True, "done_reason": "stop", "message": {"content": raw}}
        return v2.parse_response(case["input"], case["context"], v2.prepared_request(case["input"]), response), raw

    def test_measured_inputs_and_inference_options_are_identical(self):
        for case in self.cases:
            old, new = (module.prepared_request(case["input"]) for module in (v1, v2))
            self.assertEqual(old["request"]["messages"][1], new["request"]["messages"][1])
            self.assertEqual(old["request"]["options"], new["request"]["options"])
            validation.audit_request(case, new)
            self.assertNotIn("confirmation_summary", json.loads(new["request"]["messages"][1]["content"]))

    def test_literal_codes_match_all_techniques(self):
        for case in self.cases:
            prompt = v2.build_messages(case["input"])[0]["content"]
            for code in v2.REASON_CODES[case["input"]["technique"]]:
                self.assertIn(code, prompt)
            self.assertIn("anything other than exactly [1,2,3]", prompt)

    def test_correct_outputs_preserve_raw_verdict_and_tally(self):
        for case in self.cases[:-1]:
            output = self.output(case)
            Draft202012Validator(v2.output_schema(case["input"])).validate(output)
            record, raw = self.parse(case, output)
            self.assertEqual(record["system_claim"], output["decision"])
            self.assertEqual(record["analysis_warnings"], [])
            self.assertEqual(record["audit"]["provenance"]["raw_model_content"], raw)
            self.assertEqual(record["audit"]["provenance"]["development_contract_warnings"], [])
            self.assertEqual(record["audit"]["provenance"]["model_confirmation_summary"], output["confirmation_summary"])

    def test_inconsistent_reason_code_remains_a_model_failure(self):
        case = self.cases[0]
        output = self.output(case)
        output["reason_code"] = "insufficient_evidence"
        record, _ = self.parse(case, output)
        self.assertEqual(record["system_claim"], "positive")
        self.assertEqual(record["model_output"]["reason_code"], "insufficient_evidence")
        self.assertIn("decision_reason_code_mismatch", record["analysis_warnings"])

    def test_mixed_positive_claim_is_preserved_and_flagged(self):
        case = self.cases[2]
        output = self.output(case)
        output.update(decision="positive", reason_code="new_database_diagnostic")
        record, _ = self.parse(case, output)
        self.assertEqual(record["system_claim"], "positive")
        self.assertIn("model_claim_trial_assessment_mismatch", record["analysis_warnings"])
        self.assertIn("model_summary_decision_mismatch", record["audit"]["provenance"]["development_contract_warnings"])

    def test_incomplete_positive_claim_is_not_silently_fixed(self):
        case = self.cases[3]
        output = self.output(case)
        output.update(decision="positive", reason_code="new_database_diagnostic")
        record, _ = self.parse(case, output)
        self.assertEqual(record["system_claim"], "positive")
        self.assertIn("model_claim_evidence_mismatch", record["analysis_warnings"])

    def test_invented_tally_is_preserved_and_flagged(self):
        case = self.cases[0]
        output = self.output(case)
        output["confirmation_summary"]["positive_trial_count"] = 2
        record, _ = self.parse(case, output)
        self.assertEqual(record["audit"]["provenance"]["model_confirmation_summary"]["positive_trial_count"], 2)
        self.assertIn("model_confirmation_summary_mismatch", record["audit"]["provenance"]["development_contract_warnings"])

    def test_missing_summary_fails_schema_without_inventing_a_verdict(self):
        case = self.cases[0]
        output = self.output(case)
        del output["confirmation_summary"]
        record, raw = self.parse(case, output)
        self.assertEqual(record["analysis_status"], "analysis_error")
        self.assertIsNone(record["system_claim"])
        self.assertEqual(record["audit"]["provenance"]["raw_model_content"], raw)

    def test_runtime_invalid_never_calls_model(self):
        case = self.cases[-1]
        with patch.object(v1, "post_ollama", side_effect=AssertionError("Unexpected model call")) as call:
            record = v2.analyze_with_qwen(case["input"], case["context"])
        call.assert_not_called()
        self.assertEqual(record["analysis_status"], "runtime_invalid")

    def test_changed_prepared_request_is_rejected_before_call(self):
        case = self.cases[0]
        prepared = v2.prepared_request(case["input"])
        prepared["request"]["options"]["seed"] = 99
        with patch.object(v1, "post_ollama") as call:
            with self.assertRaisesRegex(ValueError, "changed after freeze"):
                v2.analyze_with_qwen(case["input"], case["context"], prepared=prepared)
        call.assert_not_called()

    def test_boundary_and_control_fixtures_match_predeclared_labels(self):
        labels = {row["case_id"]: row for row in self.labels}
        for case in self.cases:
            if labels[case["case_id"]]["expected_claim"] is not None:
                self.assertEqual(self.output(case)["decision"], labels[case["case_id"]]["expected_claim"])
        threshold_case = self.cases[12]
        self.assertEqual([c["candidate_minus_control_ms"] for c in v1.paired_view(threshold_case["input"])["comparisons"]], [1500.0] * 3)

    def test_freeze_contains_every_planned_request_and_no_inference(self):
        if not (Path(__file__).resolve().parents[1] / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json").is_file():
            self.skipTest("Requires the ignored private formal-review source inventory.")
        temporary_root = validation.ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root, prefix="v2-contract-test-") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(temporary_root.resolve()))
            output = Path(directory) / "frozen"
            with patch.object(v1, "post_ollama", side_effect=AssertionError("Unexpected model call")):
                validation.prepare(output)
            manifest = json.loads((output / "manifest.json").read_text())
            schedule = json.loads((output / "prepared-requests.json").read_text())
            self.assertEqual(len(schedule), 44)
            self.assertEqual(manifest["planned_model_calls"], 41)
            self.assertTrue(all(validation.pilot.digest(output / name) == digest
                                for name, digest in manifest["artifact_sha256"].items()))


if __name__ == "__main__":
    unittest.main()
