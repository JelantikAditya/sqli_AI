"""Verify model isolation, evidence links and metric units in the analysis contract."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from analyze_response import (analyze_with_qwen, build_messages, confusion_class,
                             input_from_s1_smoke, normalize_analysis, rule_signal,
                             summarize_run, validate_input)


class ResponseAnalysisTests(unittest.TestCase):
    def observation(self, index, role, diagnostics=(), markers=(), elapsed=10):
        return {"observation_id": f"obs-{index:03d}", "trial": 1, "role": role,
                "http_status": 200, "elapsed_ms": elapsed, "response_sha256": "a" * 64,
                "diagnostics": list(diagnostics), "content_markers": list(markers)}

    def evidence(self, success=True):
        return {"schema_version": "1.0.0", "technique": "error-based",
                "injection_point": {"method": "GET", "input_path": "/vulnerabilities/sqli/",
                                    "result_path": "/vulnerabilities/sqli/", "parameter": "id"},
                "runtime_status": "valid", "baseline_valid": True, "time_threshold_ms": 1500,
                "observations": [self.observation(1, "baseline", markers=["benign_record"]),
                                 self.observation(2, "candidate", ["mysql_syntax_error"] if success else [])]}

    def context(self, candidate="c1", replicate=1):
        return {"experiment_id": "fixture", "run_id": "r1", "attempt_id": "attempt1",
                "candidate_id": candidate, "scenario_id": "S1", "replicate": replicate,
                "condition_id": "A", "source": "LLM", "rag_mode": "off"}

    def output(self, decision="positive", refs=None):
        return {"decision": decision, "reason_code": "new_database_diagnostic" if decision == "positive" else "no_new_database_diagnostic",
                "reason": "Comparison of supplied observations.",
                "evidence_refs": ["obs-001", "obs-002"] if refs is None else refs,
                "feedback_action": "none" if decision == "positive" else "revise_candidate"}

    def test_prompt_and_input_reject_evaluator_labels_and_raw_page_fields(self):
        doc = self.evidence()
        for field in ("ground_truth", "scenario_id", "security_level", "condition_id", "rag_mode", "raw_body", "cookie"):
            changed = {**doc, field: "private-value"}
            with self.assertRaises(ValidationError):
                build_messages(changed)
        self.assertNotIn("private-value", json.dumps(build_messages(doc)))

    def test_adapter_discards_secrets_and_exception_name_without_diagnostic(self):
        receipt = {"http_status": 200, "response_time_ms": 5, "response_sha256": "a" * 64,
                   "benign_record_visible": True, "sql_error_excerpts": [], "rag_mode": "off"}
        smoke = {"authentication_verified": True, "security_level_verified": "low",
                 "observed_form": {"method": "GET", "path": "/vulnerabilities/sqli/", "parameter": "id", "user_token": "secret"},
                 "ground_truth": "negative", "response_receipts": [
                     {**receipt, "role": "baseline", "cookie": "private-cookie"},
                     {**receipt, "role": "candidate", "sql_error_excerpts": ["mysqli_sql_exception private-query"]}]}
        doc = input_from_s1_smoke(smoke, "off")
        self.assertFalse(rule_signal(doc))
        for secret in ("secret", "private-cookie", "private-query", "ground_truth", "rag_mode"):
            self.assertNotIn(secret, json.dumps(doc))

    def test_positive_claim_is_preserved_without_rule_support_and_becomes_fp(self):
        record = normalize_analysis(self.evidence(False), self.output(), self.context())
        self.assertFalse(record["claim_supported"])
        self.assertEqual(record["system_claim"], "positive")
        summary = summarize_run([record], 1)
        self.assertEqual(confusion_class(summary, "negative"), "FP")
        self.assertIsNone(summary["psr"])

    def test_reason_code_mismatch_is_flagged_without_filtering_positive_claim(self):
        output = self.output()
        output["reason_code"] = "insufficient_evidence"
        record = normalize_analysis(self.evidence(), output, self.context())
        self.assertEqual(record["analysis_warnings"], ["decision_reason_code_mismatch"])
        self.assertEqual(confusion_class(summarize_run([record], 1), "negative"), "FP")

    def test_citations_must_include_supporting_comparison(self):
        record = normalize_analysis(self.evidence(), self.output(refs=["obs-001"]), self.context())
        self.assertFalse(record["claim_supported"])
        record = normalize_analysis(self.evidence(), self.output(), self.context())
        self.assertTrue(record["claim_supported"])

    def test_hallucinated_reference_is_quarantined_without_erasing_claim(self):
        record = normalize_analysis(self.evidence(), self.output(refs=["obs-999"]), self.context())
        self.assertEqual(record["system_claim"], "positive")
        self.assertEqual(record["analysis_status"], "invalid_evidence_reference")
        summary = summarize_run([record], 1)
        self.assertEqual(summary["run_status"], "incomplete")
        self.assertIsNone(confusion_class(summary, "negative"))

    def test_invalid_runtime_skips_inference_and_never_becomes_negative(self):
        doc = self.evidence()
        doc["runtime_status"] = "invalid"
        doc["baseline_valid"] = False
        with patch("analyze_response.post_ollama") as model:
            record = analyze_with_qwen(doc, self.context())
        model.assert_not_called()
        self.assertEqual(record["analysis_status"], "runtime_invalid")
        self.assertIsNone(record["system_claim"])
        self.assertEqual(summarize_run([record], 1)["system_decision"], "not_evaluable")

    def test_incomplete_budget_inconclusive_and_duplicate_candidates_are_distinct(self):
        record = normalize_analysis(self.evidence(False), self.output("negative"), self.context())
        self.assertEqual(summarize_run([record], 10)["run_status"], "incomplete")
        uncertain = normalize_analysis(self.evidence(False), self.output("inconclusive"), self.context())
        self.assertEqual(summarize_run([uncertain], 1)["run_status"], "inconclusive")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summarize_run([record, record], 2)

    def test_no_cross_run_voting_and_mixed_replicates_are_rejected(self):
        record = normalize_analysis(self.evidence(), self.output(), self.context())
        negative = normalize_analysis(self.evidence(False), self.output("negative"), self.context("c2"))
        self.assertEqual(summarize_run([record, negative], 2)["system_decision"], "positive")
        other_run = normalize_analysis(self.evidence(False), self.output("negative"), self.context("c2", 2))
        with self.assertRaisesRegex(ValueError, "Do not mix"):
            summarize_run([record, other_run], 2)

    def test_changed_observations_or_claims_cannot_silently_change_metrics(self):
        record = normalize_analysis(self.evidence(), self.output(), self.context())
        for field in ("evidence", "system_claim"):
            changed = copy.deepcopy(record)
            if field == "evidence":
                changed[field]["observations"][1]["diagnostics"] = []
            else:
                changed[field] = "negative"
            with self.assertRaises(ValueError):
                summarize_run([changed], 1)

    def test_time_uses_matched_control_not_benign_baseline(self):
        doc = self.evidence()
        doc["technique"] = "time-based blind"
        doc["observations"] = [self.observation(1, "baseline", elapsed=1),
                               self.observation(2, "candidate", elapsed=2200),
                               self.observation(3, "no_delay_control", elapsed=2100)]
        validate_input(doc)
        self.assertFalse(rule_signal(doc))
        doc["observations"][2]["elapsed_ms"] = 50
        self.assertTrue(rule_signal(doc))
        doc["observations"][2]["trial"] = 2
        with self.assertRaisesRegex(ValueError, "Each trial"):
            validate_input(doc)

    def test_boolean_pair_is_one_candidate(self):
        doc = self.evidence()
        doc["technique"] = "boolean-based blind"
        doc["injection_point"]["input_path"] = "/vulnerabilities/sqli_blind/"
        doc["injection_point"]["result_path"] = "/vulnerabilities/sqli_blind/"
        doc["observations"] = [self.observation(1, "baseline"),
                               self.observation(2, "true_condition", markers=["user_id_exists"]),
                               self.observation(3, "false_condition", markers=["user_id_missing"])]
        output = self.output(refs=["obs-002", "obs-003"])
        output["reason_code"] = "boolean_difference"
        context = {**self.context(), "scenario_id": "S2"}
        summary = summarize_run([normalize_analysis(doc, output, context)], 1)
        self.assertEqual(summary["valid_executed_count"], 1)

    def test_wrong_scenario_coordinates_cannot_enter_ledger(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            normalize_analysis(self.evidence(), self.output(), {**self.context(), "scenario_id": "S4"})

    def test_model_failure_preserves_analysis_error_and_ablation_prompt_is_identical(self):
        doc = self.evidence()
        other = {**self.context(), "condition_id": "B", "rag_mode": "on"}
        requests = []
        def fake(endpoint, payload, timeout):
            requests.append(payload)
            return {"model": "qwen2.5:7b", "message": {"content": "not-json"}}
        with patch("analyze_response.post_ollama", side_effect=fake):
            a = analyze_with_qwen(doc, self.context())
            b = analyze_with_qwen(doc, other)
        self.assertEqual(a["analysis_status"], "analysis_error")
        self.assertEqual(a["audit"]["provenance"]["raw_model_content"], "not-json")
        self.assertEqual(requests[0], requests[1])
        with patch("analyze_response.post_ollama", side_effect=RuntimeError("unavailable")):
            self.assertEqual(analyze_with_qwen(doc, self.context())["analysis_status"], "analysis_error")
        with patch("analyze_response.post_ollama", return_value={"message": None}):
            self.assertEqual(analyze_with_qwen(doc, self.context())["analysis_status"], "analysis_error")


if __name__ == "__main__":
    unittest.main()
