"""Regression checks for scoring boundaries with simulated outputs, never Qwen results."""

import copy
import json
import unittest

from test_prerequisites import require_local_snapshots
from unittest.mock import patch

from tokenizers import Tokenizer

import analysis_v5_pilot_rev2 as pilot
import test_analysis_v5_pilot as original_tests


class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_snapshots("knowledge/analysis-v5/sources.lock.json", extra_paths=("results/raw/development/analysis-v5-pilot-20261020/tokenizer.json",))
        cls.cases, cls.labels = pilot.dataset.build_cases()
        cls.requests = pilot.prepare_requests(cls.cases)
        cls.tokenizer = Tokenizer.from_file(str(pilot.context.RAW / "tokenizer.json"))
        cls.audit = pilot.audit_requests(cls.cases, cls.requests, cls.tokenizer)
        cls.schedule = pilot.dataset.schedule(cls.cases)
        cls.request_map = {(r["case_id"], r["profile"]): r["request"] for r in cls.requests}
        cls.count_map = {(r["case_id"], r["profile"]): r["prompt_tokens"] for r in cls.audit}
        cls.doc_map = {c["case_id"]: c["input"] for c in cls.cases}

    response = original_tests.PilotTests.response

    def parse(self, response, cid="pilot-001", profile="A"):
        return pilot.parse_output(self.doc_map[cid], self.request_map[(cid, profile)], response,
                                  self.count_map[(cid, profile)])

    def mutate(self, response, callback):
        result = copy.deepcopy(response)
        content = json.loads(result["message"]["content"])
        callback(content)
        result["message"]["content"] = json.dumps(content)
        return result

    def test_completion_boundaries_distinguish_budget_from_length_and_json(self):
        response = self.response(self.request_map[("pilot-001", "A")])
        variants = [
            ({"done": False}, "generation-not-finished"),
            ({"done_reason": "length", "eval_count": 768}, "generation-length-limit"),
            ({"done_reason": "length", "eval_count": 400}, "generation-length-limit"),
            ({"done_reason": "stop", "eval_count": 768}, "output-budget-rejection"),
            ({"done_reason": "stop", "eval_count": 769}, "output-budget-rejection"),
            ({"done_reason": "unknown"}, "unexpected-completion-reason"),
            ({"eval_count": None}, "invalid-generation-token-count"),
            ({"eval_count": True}, "invalid-generation-token-count"),
            ({"eval_count": 0}, "invalid-generation-token-count"),
        ]
        for update, error in variants:
            with self.subTest(update=update):
                result = self.parse({**response, **update})
                self.assertEqual(result["error"], error)
                self.assertEqual(result["status"], "analysis_error")
        # JSON ini lengkap dan valid, tetapi kebijakan anggaran tetap menolaknya.
        json.loads(response["message"]["content"])
        self.assertEqual(self.parse({**response, "eval_count": 767})["status"], "ok")
        self.assertEqual(self.parse({**response, "prompt_eval_count": -1, "eval_count": 768})["error"],
                         "prompt-count-mismatch")

    def test_each_content_error_keeps_case_and_trial_denominators_without_retry(self):
        events, calls = [], []
        slots = [s for s in self.schedule if s["case_id"] == "pilot-001"]

        def client(request):
            calls.append(request)
            response = self.response(request, malformed=len(calls) == 3)
            if len(calls) == 1:
                response["eval_count"] = 768
            elif len(calls) == 2:
                response.update(done_reason="length", eval_count=768)
            return response

        pilot.run_slots(self.cases, slots, self.requests, self.audit, client, events.append)
        summary = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual(len(calls), 3)
        self.assertEqual([e["error"] for e in events if e["event"] == "finished"],
                         ["output-budget-rejection", "generation-length-limit", "invalid-json-or-schema"])
        for row in summary["profiles"].values():
            self.assertEqual((row["attempted_eligible"], row["trial_denominator"]), (1, 3))
            self.assertEqual((row["raw_correct"], row["trial_correct"], row["analysis_errors"]), (0, 0, 1))

    def test_unknown_ids_are_errors_at_both_citation_levels(self):
        response = self.response(self.request_map[("pilot-001", "A")])
        for top_level in (True, False):
            with self.subTest(top_level=top_level):
                def change(output):
                    refs = output["evidence_refs"] if top_level else output["trial_assessments"][0]["evidence_refs"]
                    refs[0] = "obs-099"
                self.assertEqual(self.parse(self.mutate(response, change))["error"], "unknown-observation-reference")

    def test_missing_required_field_is_schema_error_not_semantic_warning(self):
        response = self.response(self.request_map[("pilot-001", "A")])
        changed = self.mutate(response, lambda output: output.pop("trial_assessments"))
        self.assertEqual(self.parse(changed)["error"], "invalid-json-or-schema")

    def test_known_but_unsupported_citations_are_warnings_and_keep_raw_verdict(self):
        response = self.response(self.request_map[("pilot-001", "A")], decision="negative")

        def change(output):
            output["trial_assessments"][0]["evidence_refs"] = ["obs-003", "obs-004"]
            output["trial_assessments"][0]["outcome"] = "negative"

        parsed = self.parse(self.mutate(response, change))
        self.assertEqual((parsed["status"], parsed["decision"]), ("ok", "negative"))
        self.assertIn("missing-or-incorrect-trial-citations", parsed["warnings"])
        self.assertIn("unrelated-trial-citations", parsed["warnings"])
        self.assertIn("trial-outcome-evidence-mismatch", parsed["warnings"])

        # Baseline benign ada pada kasus boolean, tetapi bukan bagian pembandingnya.
        response = self.response(self.request_map[("pilot-013", "A")])
        response = self.mutate(response, lambda output: output["evidence_refs"].append("obs-001"))
        parsed = self.parse(response, cid="pilot-013")
        self.assertEqual(parsed["status"], "ok")
        self.assertIn("unrelated-top-level-citations", parsed["warnings"])

    def test_missing_duplicate_and_wrong_trials_score_zero_without_shrinking_denominator(self):
        events = []
        for slot in [s for s in self.schedule if s["case_id"] == "pilot-001"]:
            response = self.response(self.request_map[(slot["case_id"], slot["profile"])])
            def change(output):
                trials = output["trial_assessments"]
                if slot["profile"] == "A":
                    output["trial_assessments"] = trials[:2]
                elif slot["profile"] == "B2":
                    output["trial_assessments"] = [trials[0], trials[0], trials[2]]
                else:
                    trials[0]["outcome"] = "negative"
            parsed = self.parse(self.mutate(response, change), profile=slot["profile"])
            self.assertEqual(parsed["status"], "ok")
            events.extend([{**slot, "event": "attempt_started"}, {**slot, "event": "finished", **parsed}])
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)
        for profile, correct in (("A", 2), ("B2", 1), ("B3", 2)):
            self.assertEqual(result["profiles"][profile]["trial_correct"], correct)
            self.assertEqual(result["profiles"][profile]["trial_denominator"], 3)
            self.assertEqual(result["profiles"][profile]["raw_correct"], 1)

    def test_reason_reference_accuracy_is_separate_from_internal_consistency(self):
        events = []
        for slot in [s for s in self.schedule if s["case_id"] == "pilot-001"]:
            request = self.request_map[(slot["case_id"], slot["profile"])]
            response = self.response(request, decision="negative" if slot["profile"] == "A" else "positive")
            if slot["profile"] == "B3":
                response = self.mutate(response, lambda output: output.update(reason_code="no_new_database_diagnostic"))
            parsed = self.parse(response, profile=slot["profile"])
            events.extend([{**slot, "event": "attempt_started"}, {**slot, "event": "finished", **parsed}])
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)["profiles"]
        self.assertEqual((result["A"]["reason_code_accuracy"], result["A"]["reason_code_consistency"]), (0, 1))
        self.assertEqual((result["B2"]["reason_code_accuracy"], result["B2"]["reason_code_consistency"]), (1, 1))
        self.assertEqual((result["B3"]["raw_correct"], result["B3"]["reason_code_consistency"]), (1, 0))

    def test_paired_transitions_include_case_ids_and_reconcile_delta(self):
        events = []
        verdicts = {
            "pilot-001": {"A": "negative", "B3": "positive"},
            "pilot-002": {"A": "positive", "B3": "negative"},
            "pilot-003": {"A": "negative", "B3": "positive"},
            "pilot-004": {"A": "positive", "B3": "positive"},
            "pilot-005": {"A": "positive", "B3": "positive"},
        }
        for slot in self.schedule:
            if slot["case_id"] not in verdicts:
                continue
            verdict = verdicts[slot["case_id"]].get(slot["profile"], "positive")
            response = self.response(self.request_map[(slot["case_id"], slot["profile"])], decision=verdict)
            parsed = self.parse(response, cid=slot["case_id"], profile=slot["profile"])
            events.extend([{**slot, "event": "attempt_started"}, {**slot, "event": "finished", **parsed}])
        primary = pilot.summarize(self.cases, self.labels, self.schedule, events)["primary"]
        transitions = primary["paired_correctness_transitions"]
        self.assertEqual(transitions["wrong_to_correct"], {"count": 2, "case_ids": ["pilot-001", "pilot-003"]})
        self.assertEqual(transitions["correct_to_wrong"]["case_ids"], ["pilot-002"])
        self.assertEqual(transitions["both_correct"]["case_ids"], ["pilot-004"])
        self.assertEqual(transitions["both_wrong"]["case_ids"], ["pilot-005"])
        self.assertAlmostEqual(primary["paired_accuracy_difference_percentage_points"], 20)
        self.assertEqual(primary["conclusion"], "incomplete")

    def test_interrupted_pair_is_error_and_unpaired_cases_are_explicit(self):
        slots = {s["profile"]: s for s in self.schedule if s["case_id"] == "pilot-001"}
        a, b = slots["A"], slots["B3"]
        parsed = self.parse(self.response(self.request_map[("pilot-001", "B3")]), profile="B3")
        events = [{**a, "event": "attempt_started"}, {**b, "event": "attempt_started"},
                  {**b, "event": "finished", **parsed}]
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual(result["profiles"]["A"]["analysis_errors"], 1)
        self.assertEqual(result["primary"]["paired_correctness_transitions"]["wrong_to_correct"]["case_ids"], ["pilot-001"])
        self.assertEqual(result["primary"]["unfinished_pair_case_ids"], ["pilot-001"])
        self.assertEqual(len(result["primary"]["unpaired_eligible_case_ids"]), 35)
        self.assertFalse(result["primary"]["complete"])

    def test_complete_simulation_remains_108_calls_18_skips_and_102_trials(self):
        events, calls = [], []
        def client(request):
            calls.append(request)
            return self.response(request)
        with patch.object(pilot.context, "api", side_effect=AssertionError("Offline tests must not call services")):
            status = pilot.run_slots(self.cases, self.schedule, self.requests, self.audit, client, events.append)
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual((status, len(calls), result["skipped_invalid_slots"]), ("completed", 108, 18))
        self.assertTrue(result["primary"]["complete"])
        self.assertEqual(result["primary"]["paired_correctness_transitions"]["both_correct"]["count"], 36)
        for row in result["profiles"].values():
            self.assertEqual(row["trial_denominator"], 102)
            self.assertEqual((row["reason_code_accuracy"], row["reason_code_consistency"]), (1, 1))

    def test_protocol_keeps_review_pending_and_records_limited_gate_scope(self):
        protocol = pilot.protocol()
        self.assertEqual(protocol["researcher_review"], "pending")
        self.assertEqual(protocol["researcher_adoption"], "not-recorded")
        self.assertEqual(len(protocol["coverage_limits"]), 6)
        self.assertIn("not proof of incomplete JSON", protocol["output_completion"]["output-budget-rejection"])

    def test_all_retained_labels_match_actual_frozen_rules(self):
        audit = pilot.audit_frozen_contract(self.cases, self.labels)
        self.assertEqual((audit["cases_checked"], audit["eligible_cases_checked"],
                          audit["eligible_trial_assessments_checked"]), (42, 36, 102))
        changed = copy.deepcopy(self.labels)
        changed["cases"][0]["trial_assessments"][0]["outcome"] = "negative"
        with self.assertRaisesRegex(ValueError, "frozen executor signals"):
            pilot.audit_frozen_contract(self.cases, changed)


if __name__ == "__main__":
    unittest.main()
