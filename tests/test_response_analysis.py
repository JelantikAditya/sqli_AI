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
                             audit_trial_assessments, comparison_observation_ids,
                             input_from_s1_smoke, load_catalog, normalize_analysis, rule_signal,
                             summarize_run, validate_input)


class ResponseAnalysisTests(unittest.TestCase):
    def observation(self, index, role, diagnostics=(), markers=(), elapsed=10, trial=1):
        return {"observation_id": f"obs-{index:03d}", "trial": trial, "role": role,
                "http_status": 200, "elapsed_ms": elapsed, "response_sha256": "a" * 64,
                "diagnostics": list(diagnostics), "content_markers": list(markers)}

    def expand_trials(self, doc):
        templates = copy.deepcopy(doc["observations"])
        doc["observations"] = []
        for trial in (1, 2, 3):
            for observation in templates:
                doc["observations"].append({**observation, "trial": trial,
                                            "observation_id": f"obs-{len(doc['observations']) + 1:03d}"})
        return doc

    def evidence(self, success=True, positive_count=None):
        doc = self.expand_trials({"schema_version": "1.0.0", "technique": "error-based",
                "injection_point": {"method": "GET", "input_path": "/vulnerabilities/sqli/",
                                    "result_path": "/vulnerabilities/sqli/", "parameter": "id"},
                "runtime_status": "valid", "baseline_valid": True, "time_threshold_ms": 1500,
                "observations": [self.observation(1, "baseline", markers=["benign_record"]),
                                 self.observation(2, "candidate", ["mysql_syntax_error"] if success else [])]})
        if positive_count is not None:
            for observation in doc["observations"]:
                if observation["role"] == "candidate":
                    observation["diagnostics"] = ["mysql_syntax_error"] if observation["trial"] <= positive_count else []
        return doc

    def context(self, candidate="c1", replicate=1):
        return {"experiment_id": "fixture", "run_id": "r1", "attempt_id": "attempt1",
                "candidate_id": candidate, "scenario_id": "S1", "replicate": replicate,
                "condition_id": "A", "source": "LLM", "rag_mode": "off"}

    def output(self, decision="positive", refs=None):
        return {"decision": decision, "reason_code": "new_database_diagnostic" if decision == "positive" else "no_new_database_diagnostic",
                "reason": "Comparison of supplied observations.",
                "evidence_refs": [f"obs-{i:03d}" for i in range(1, 7)] if refs is None else refs,
                "feedback_action": "none" if decision == "positive" else "revise_candidate"}

    def trial_output(self, doc, decision, positive_trials=(), *, top_refs=None, assessment_refs=None):
        roles = {"error-based": ("baseline", "candidate"),
                 "boolean-based blind": ("true_condition", "false_condition"),
                 "time-based blind": ("candidate", "no_delay_control")}[doc["technique"]]
        by_trial = {}
        for observation in doc["observations"]:
            by_trial.setdefault(observation["trial"], {})[observation["role"]] = observation["observation_id"]
        comparisons = {trial: [by_trial[trial][role] for role in roles]
                       for trial in sorted(by_trial) if all(role in by_trial[trial] for role in roles)}
        assessments = [{"trial": trial,
                        "outcome": "positive" if trial in positive_trials else "negative",
                        "evidence_refs": (assessment_refs or {}).get(trial, comparisons[trial])}
                       for trial in comparisons]
        refs = top_refs if top_refs is not None else [ref for values in comparisons.values() for ref in values]
        reason_codes = {
            "error-based": {"positive": "new_database_diagnostic", "negative": "no_new_database_diagnostic"},
            "boolean-based blind": {"positive": "boolean_difference", "negative": "no_boolean_difference"},
            "time-based blind": {"positive": "matched_delay", "negative": "no_matched_delay"},
        }[doc["technique"]]
        reason_codes["inconclusive"] = "insufficient_evidence"
        return {"decision": decision, "reason_code": reason_codes[decision],
                "reason": "Per-trial comparison of supplied observations.",
                "evidence_refs": refs,
                "feedback_action": "none" if decision == "positive" else "revise_candidate",
                "trial_assessments": assessments}

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
        self.assertEqual(rule_signal(doc), "INCOMPLETE_CONFIRMATIONS")
        for secret in ("secret", "private-cookie", "private-query", "ground_truth", "rag_mode"):
            self.assertNotIn(secret, json.dumps(doc))

    def test_positive_claim_is_preserved_without_rule_support_and_becomes_fp(self):
        record = normalize_analysis(self.evidence(False), self.output(), self.context())
        self.assertFalse(record["claim_supported"])
        self.assertIn("model_claim_evidence_mismatch", record["analysis_warnings"])
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

    def test_negative_claim_against_three_positive_diagnostics_is_flagged_and_preserved(self):
        record = normalize_analysis(self.evidence(True), self.output("negative"), self.context())
        self.assertEqual(record["system_claim"], "negative")
        self.assertTrue(record["confirmed_success"])
        self.assertIn("model_claim_evidence_mismatch", record["analysis_warnings"])

    def test_mixed_evidence_requires_inconclusive_claim_warning_for_confident_model_verdict(self):
        record = normalize_analysis(self.evidence(True, positive_count=2), self.output("negative"), self.context())
        self.assertEqual(record["evidence_status"], "MIXED_EVIDENCE")
        self.assertIn("model_claim_evidence_mismatch", record["analysis_warnings"])

    def test_citations_must_include_supporting_comparison(self):
        record = normalize_analysis(self.evidence(), self.output(refs=["obs-001"]), self.context())
        self.assertFalse(record["claim_supported"])
        record = normalize_analysis(self.evidence(), self.output(), self.context())
        self.assertTrue(record["claim_supported"])

    def test_per_trial_contract_covers_zero_one_two_three_and_missing_confirmations(self):
        cases = ((0, "negative", ("negative", "negative", "negative")),
                 (1, "inconclusive", ("positive", "negative", "negative")),
                 (2, "inconclusive", ("positive", "positive", "negative")),
                 (3, "positive", ("positive", "positive", "positive")))
        for count, decision, outcomes in cases:
            with self.subTest(positive_count=count):
                doc = self.evidence(positive_count=count)
                output = self.trial_output(doc, decision, range(1, count + 1))
                self.assertEqual(audit_trial_assessments(doc, output), [])
                record = normalize_analysis(doc, output, self.context())
                self.assertEqual(record["system_claim"], decision)
                self.assertNotIn("model_claim_evidence_mismatch", record["analysis_warnings"])
                self.assertEqual(tuple(item["outcome"] for item in output["trial_assessments"]), outcomes)

        incomplete = self.evidence(positive_count=2)
        incomplete["observations"] = [o for o in incomplete["observations"] if o["trial"] <= 2]
        output = self.trial_output(incomplete, "positive", (1, 2))
        record = normalize_analysis(incomplete, output, self.context())
        self.assertIn("model_claim_evidence_mismatch", record["analysis_warnings"])
        self.assertIn("model_claim_trial_assessment_mismatch", record["analysis_warnings"])
        self.assertFalse(record["claim_supported"])
        self.assertEqual(record["system_claim"], "positive")

    def test_per_trial_contract_audits_pair_references_and_preserves_claim(self):
        doc = self.evidence()
        full_pairs = comparison_observation_ids(doc)
        candidates_only = [o["observation_id"] for o in doc["observations"] if o["role"] == "candidate"]
        output = self.trial_output(doc, "positive", (1, 2, 3), top_refs=candidates_only)
        record = normalize_analysis(doc, output, self.context())
        self.assertTrue(record["claim_supported"] is False)
        self.assertIn("evidence_refs_incomplete", record["analysis_warnings"])
        self.assertEqual(record["system_claim"], "positive")

        incomplete_trial_refs = {trial: [next(iter(ids - {next(o["observation_id"] for o in doc["observations"]
                                                           if o["trial"] == trial and o["role"] == "baseline")}))]
                                 for trial, ids in full_pairs.items()}
        output = self.trial_output(doc, "positive", (1, 2, 3), assessment_refs=incomplete_trial_refs)
        record = normalize_analysis(doc, output, self.context())
        self.assertIn("trial_assessment_evidence_refs_incomplete", record["analysis_warnings"])
        self.assertNotIn("evidence_refs_incomplete", record["analysis_warnings"])

        output["trial_assessments"][0]["outcome"] = "negative"
        record = normalize_analysis(doc, output, self.context())
        self.assertIn("trial_assessment_evidence_mismatch", record["analysis_warnings"])

    def test_new_model_contract_requires_trial_assessments_and_prompts_for_comparison_ids(self):
        doc = self.evidence()
        output = self.trial_output(doc, "positive", (1, 2, 3))
        requests = []
        response = {"model": "qwen2.5:7b", "message": {"content": json.dumps(output)}, "done": True}
        with patch("analyze_response.post_ollama", side_effect=lambda endpoint, payload, timeout: (requests.append(payload) or response)):
            record = analyze_with_qwen(doc, self.context())
        self.assertEqual(record["analysis_status"], "completed")
        self.assertTrue(record["claim_supported"])
        self.assertEqual(record["audit"]["provenance"]["prompt_version"], "sqli-response-analysis-v8-count-trials")
        self.assertIn("trial_assessments", requests[0]["format"]["required"])
        self.assertIn("both sides of each pair", requests[0]["messages"][0]["content"])

        legacy_response = {"model": "qwen2.5:7b", "message": {"content": json.dumps(self.output())}, "done": True}
        with patch("analyze_response.post_ollama", return_value=legacy_response):
            rejected = analyze_with_qwen(doc, self.context())
        self.assertEqual(rejected["analysis_status"], "analysis_error")
        self.assertIsNone(rejected["system_claim"])
        self.assertEqual(rejected["audit"]["provenance"]["analysis_error"], "invalid-model-json-or-schema")

    def test_trial_contract_uses_the_correct_comparison_pair_for_each_technique(self):
        scenarios = load_catalog()["scenarios"]
        roles = {"error-based": ("baseline", "candidate"),
                 "boolean-based blind": ("baseline", "true_condition", "false_condition"),
                 "time-based blind": ("baseline", "candidate", "no_delay_control")}
        scenario_ids = {"error-based": "S1", "boolean-based blind": "S2", "time-based blind": "S3"}
        for technique, scenario_id in scenario_ids.items():
            with self.subTest(technique=technique):
                scenario = next(item for item in scenarios if item["scenario_id"] == scenario_id)
                doc = {"schema_version": "1.0.0", "technique": technique,
                       "injection_point": {key: scenario[key] for key in
                                           ("method", "input_path", "result_path", "parameter")},
                       "runtime_status": "valid", "baseline_valid": True,
                       "time_threshold_ms": 1500, "observations": []}
                for trial in (1, 2, 3):
                    for role in roles[technique]:
                        index = len(doc["observations"]) + 1
                        kwargs = {}
                        if technique == "error-based" and role == "baseline":
                            kwargs["markers"] = ["benign_record"]
                        elif technique == "error-based" and role == "candidate":
                            kwargs["diagnostics"] = ["mysql_syntax_error"]
                        elif technique == "boolean-based blind":
                            kwargs["markers"] = {"baseline": ["benign_record"],
                                                 "true_condition": ["user_id_exists"],
                                                 "false_condition": ["user_id_missing"]}[role]
                        elif technique == "time-based blind":
                            kwargs["markers"] = ["benign_record"] if role == "baseline" else ["user_id_exists"]
                            kwargs["elapsed"] = 2000 if role == "candidate" else 10
                        doc["observations"].append(self.observation(index, role, trial=trial, **kwargs))
                validate_input(doc)
                output = self.trial_output(doc, "positive", (1, 2, 3))
                context = {**self.context(), "scenario_id": scenario_id}
                record = normalize_analysis(doc, output, context)
                self.assertTrue(record["claim_supported"])
                self.assertEqual(record["analysis_warnings"], [])

    def test_hallucinated_reference_is_quarantined_without_erasing_claim(self):
        record = normalize_analysis(self.evidence(), self.output(refs=["obs-999"]), self.context())
        self.assertEqual(record["system_claim"], "positive")
        self.assertEqual(record["analysis_status"], "invalid_evidence_reference")
        summary = summarize_run([record], 1)
        self.assertEqual(summary["run_status"], "incomplete")
        self.assertIsNone(confusion_class(summary, "negative"))

        doc = self.evidence()
        output = self.trial_output(doc, "positive", (1, 2, 3))
        output["trial_assessments"][0]["evidence_refs"].append("obs-999")
        nested_record = normalize_analysis(doc, output, self.context())
        self.assertEqual(nested_record["system_claim"], "positive")
        self.assertEqual(nested_record["analysis_status"], "invalid_evidence_reference")
        self.assertEqual(nested_record["unknown_evidence_refs"], ["obs-999"])

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
        for field in ("evidence", "system_claim", "qwen_claim", "evidence_status"):
            changed = copy.deepcopy(record)
            if field == "evidence":
                changed[field]["observations"][1]["diagnostics"] = []
            elif field == "system_claim":
                changed[field] = "negative"
            elif field == "qwen_claim":
                changed[field] = "NOT_VULNERABLE"
            else:
                changed[field] = "CONSISTENT_NEGATIVE"
            with self.assertRaises(ValueError):
                summarize_run([changed], 1)

    def test_time_uses_matched_control_not_benign_baseline(self):
        doc = self.evidence()
        doc["technique"] = "time-based blind"
        doc["observations"] = [self.observation(1, "baseline", elapsed=1),
                               self.observation(2, "candidate", markers=["user_id_exists"], elapsed=2200),
                               self.observation(3, "no_delay_control", markers=["user_id_exists"], elapsed=2100)]
        validate_input(doc)
        self.expand_trials(doc)
        self.assertEqual(rule_signal(doc), "CONSISTENT_NEGATIVE")
        for observation in doc["observations"]:
            if observation["role"] == "no_delay_control":
                observation["elapsed_ms"] = 50
        self.assertEqual(rule_signal(doc), "CONSISTENT_POSITIVE")
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
        self.expand_trials(doc)
        output = self.output(refs=[o["observation_id"] for o in doc["observations"]])
        output["reason_code"] = "boolean_difference"
        context = {**self.context(), "scenario_id": "S2"}
        summary = summarize_run([normalize_analysis(doc, output, context)], 1)
        self.assertEqual(summary["valid_executed_count"], 1)

    def test_mixed_keeps_denominator_and_positive_claim_on_negative_target_is_fp(self):
        records = [normalize_analysis(self.evidence(positive_count=count), self.output(),
                                      self.context(f"c{count}")) for count in (1, 2)]
        for count, record in zip((1, 2), records):
            self.assertEqual(record["evidence_status"], "MIXED_EVIDENCE")
            self.assertEqual(record["positive_confirmation_count"], count)
            self.assertEqual(record["valid_confirmation_count"], 3)
            self.assertEqual(record["qwen_claim"], "VULNERABLE")
            self.assertFalse(record["confirmed_success"])
            self.assertFalse(record["claim_supported"])
        summary = summarize_run(records, 2)
        self.assertEqual(summary["valid_executed_count"], 2)
        self.assertEqual(summary["confirmed_success_count"], 0)
        self.assertEqual(summary["mixed_evidence_count"], 2)
        self.assertEqual(confusion_class(summary, "negative"), "FP")
        self.assertEqual(confusion_class(summary, "positive"), "TP")
        self.assertIsNone(summary["psr"])

    def test_confirmation_policy_covers_all_techniques_and_positive_counts(self):
        for technique in ("error-based", "boolean-based blind", "time-based blind"):
            for positive_count in range(4):
                with self.subTest(technique=technique, positive_count=positive_count):
                    doc = self.evidence(positive_count=positive_count)
                    doc["technique"] = technique
                    if technique != "error-based":
                        doc["injection_point"]["input_path"] = "/vulnerabilities/sqli_blind/"
                        doc["injection_point"]["result_path"] = "/vulnerabilities/sqli_blind/"
                        doc["observations"] = []
                        for trial in (1, 2, 3):
                            roles = ("baseline", "true_condition", "false_condition") if technique == "boolean-based blind" else ("baseline", "candidate", "no_delay_control")
                            for role in roles:
                                markers = (["user_id_exists"] if role in {"true_condition", "candidate", "no_delay_control"} else
                                           ["user_id_missing"] if role == "false_condition" and trial <= positive_count else [])
                                elapsed = 1510 if role == "candidate" and trial <= positive_count else 10
                                doc["observations"].append(self.observation(
                                    len(doc["observations"]) + 1, role, markers=markers,
                                    elapsed=elapsed, trial=trial))
                    expected = ("CONSISTENT_POSITIVE" if positive_count == 3 else
                                "CONSISTENT_NEGATIVE" if positive_count == 0 else "MIXED_EVIDENCE")
                    self.assertEqual(rule_signal(doc), expected)

    def test_partial_extra_or_nonstandard_trial_ids_cannot_establish_success(self):
        for trials in ((1,), (1, 2), (1, 2, 3, 4), (2, 3, 4)):
            with self.subTest(trials=trials):
                doc = self.evidence()
                templates = doc["observations"][:2]
                doc["observations"] = []
                for trial in trials:
                    for observation in templates:
                        doc["observations"].append({**observation, "trial": trial,
                            "observation_id": f"obs-{len(doc['observations']) + 1:03d}"})
                record = normalize_analysis(doc, self.output(refs=[o["observation_id"] for o in doc["observations"]]), self.context())
                self.assertEqual(record["evidence_status"], "INCOMPLETE_CONFIRMATIONS")
                self.assertIsNone(record["confirmed_success"])
                self.assertEqual(summarize_run([record], 1)["run_status"], "incomplete")

    def test_wrong_scenario_coordinates_cannot_enter_ledger(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            normalize_analysis(self.evidence(), self.output(), {**self.context(), "scenario_id": "S4"})

    def test_final_run_decisions_cover_negative_abstention_and_positive_precedence(self):
        cases = [(("negative", "negative"), "negative"),
                 (("inconclusive", "negative"), "inconclusive"),
                 (("inconclusive", "inconclusive"), "inconclusive"),
                 (("positive", "inconclusive"), "positive"),
                 (("negative", "positive"), "positive")]
        for claims, expected in cases:
            with self.subTest(claims=claims):
                records = [normalize_analysis(self.evidence(False), self.output(claim), self.context(f"c{i}"))
                           for i, claim in enumerate(claims)]
                summary = summarize_run(records, 2)
                self.assertEqual(summary["system_decision"], expected)
                self.assertEqual(summary["execution_status"], "complete")
                self.assertTrue(summary["psr_evidence_eligible"])
                self.assertEqual(summary["binary_decision_eligible"], expected != "inconclusive")
                if expected == "inconclusive":
                    self.assertEqual(summary["decision_exclusion_reason"], "inconclusive")
                    self.assertIsNone(confusion_class(summary, "negative"))
                    self.assertIsNone(confusion_class(summary, "positive"))
                else:
                    self.assertIsNone(summary["decision_exclusion_reason"])

    def test_mixed_inconclusive_keeps_psr_evidence_without_becoming_tn_or_fn(self):
        for count in (1, 2):
            with self.subTest(positive_count=count):
                record = normalize_analysis(self.evidence(positive_count=count), self.output("inconclusive"), self.context())
                summary = summarize_run([record], 1)
                self.assertEqual(summary["valid_executed_count"], 1)
                self.assertEqual(summary["confirmed_success_count"], 0)
                self.assertEqual(summary["mixed_evidence_count"], 1)
                self.assertTrue(summary["psr_evidence_eligible"])
                self.assertFalse(summary["binary_decision_eligible"])
                self.assertIsNone(confusion_class(summary, "negative"))
                self.assertIsNone(confusion_class(summary, "positive"))
                self.assertIsNone(summary["psr"])

    def test_model_uncertainty_does_not_override_three_positive_evidence_trials(self):
        record = normalize_analysis(self.evidence(True), self.output("inconclusive"), self.context())
        summary = summarize_run([record], 1)
        self.assertEqual(summary["confirmed_success_count"], 1)
        self.assertEqual(summary["system_decision"], "inconclusive")
        self.assertTrue(summary["psr_evidence_eligible"])
        self.assertFalse(summary["binary_decision_eligible"])

    def test_runtime_budget_and_analysis_failure_have_distinct_exclusion_reasons(self):
        valid = normalize_analysis(self.evidence(True), self.output(), self.context())
        self.assertEqual(summarize_run([valid], 2)["decision_exclusion_reason"], "incomplete_budget")
        doc = self.evidence()
        doc["runtime_status"] = "invalid"
        doc["baseline_valid"] = False
        invalid = normalize_analysis(doc, None, self.context("c2"))
        summary = summarize_run([valid, invalid], 2)
        self.assertEqual(summary["execution_status"], "invalid")
        self.assertEqual(summary["decision_exclusion_reason"], "runtime_invalid")
        self.assertEqual(summary["system_positive_count"], 1)
        self.assertFalse(summary["binary_decision_eligible"])
        self.assertFalse(summary["psr_evidence_eligible"])
        failed_analysis = normalize_analysis(self.evidence(True), None, self.context())
        summary = summarize_run([failed_analysis], 1)
        self.assertEqual(summary["execution_status"], "complete")
        self.assertEqual(summary["decision_exclusion_reason"], "analysis_incomplete")
        self.assertTrue(summary["psr_evidence_eligible"])
        self.assertFalse(summary["binary_decision_eligible"])

    def test_edited_abstention_cannot_become_a_negative_decision_or_eligible_binary_unit(self):
        record = normalize_analysis(self.evidence(False), self.output("inconclusive"), self.context())
        summary = summarize_run([record], 1)
        for field, value in (("system_decision", "negative"), ("run_status", "complete"),
                             ("binary_decision_eligible", True), ("decision_exclusion_reason", None),
                             ("psr_evidence_eligible", False)):
            with self.subTest(field=field):
                changed = {**summary, field: value}
                with self.assertRaisesRegex(ValueError, "summary semantics"):
                    confusion_class(changed, "negative")

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

    def test_duplicate_model_evidence_references_are_audited_and_canonicalized(self):
        doc = self.evidence()
        output = {"decision": "positive", "reason_code": "new_database_diagnostic",
                  "reason": "The candidate has the diagnostic in all confirmations.",
                  "evidence_refs": ["obs-002", "obs-002", "obs-004", "obs-006"],
                  "trial_assessments": [
                      {"trial": trial, "outcome": "positive",
                       "evidence_refs": [f"obs-{trial * 2:03d}", f"obs-{trial * 2:03d}", f"obs-{trial * 2 - 1:03d}"]}
                      for trial in (1, 2, 3)],
                  "feedback_action": "none"}
        response = {"model": "qwen2.5:7b", "message": {"content": json.dumps(output)},
                    "done": True}
        with patch("analyze_response.post_ollama", return_value=response):
            record = analyze_with_qwen(doc, self.context())
        self.assertEqual(record["analysis_status"], "completed")
        self.assertEqual(record["model_output"]["evidence_refs"], ["obs-002", "obs-004", "obs-006"])
        self.assertIn("duplicate_evidence_refs_removed", record["analysis_warnings"])
        provenance = record["audit"]["provenance"]
        self.assertEqual(provenance["duplicate_evidence_reference_count"], 4)
        self.assertIn('"obs-002", "obs-002"', provenance["raw_model_content"])
        self.assertEqual(summarize_run([record], 10)["analysis_completed_count"], 1)


if __name__ == "__main__":
    unittest.main()
