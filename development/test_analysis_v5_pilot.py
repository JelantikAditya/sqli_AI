"""Critical pilot checks with a simulated client only; these are not Qwen results."""

import copy
from collections import Counter
import json
import unittest

from test_prerequisites import require_local_snapshots

from tokenizers import Tokenizer

import analysis_v5_pilot as pilot


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_snapshots("knowledge/analysis-v5/sources.lock.json", extra_paths=("results/raw/development/analysis-v5-pilot-20261020/tokenizer.json",))
        cls.cases, cls.labels = pilot.dataset.build_cases()
        cls.requests = pilot.prepare_requests(cls.cases)
        cls.tokenizer = Tokenizer.from_file(str(pilot.context.RAW / "tokenizer.json"))
        cls.audit = pilot.audit_requests(cls.cases, cls.requests, cls.tokenizer)
        cls.schedule = pilot.dataset.schedule(cls.cases)

    def response(self, request, *, decision=None, malformed=False):
        doc = next(c["input"] for c in self.cases if pilot.rag.base.v1.paired_view(c["input"]) ==
                   json.loads(request["messages"][1]["content"])["measured_evidence"])
        truth = pilot.dataset.reference(doc)
        assessments = truth["trial_assessments"]
        verdict = truth["decision"] if decision is None else decision
        pos, neg = pilot.rag.base.REASON_CODES[doc["technique"]]
        output = {"trial_assessments": assessments,
            "confirmation_summary": {"observed_trials": [t["trial"] for t in assessments],
                "positive_trial_count": sum(t["outcome"] == "positive" for t in assessments),
                "negative_trial_count": sum(t["outcome"] == "negative" for t in assessments)},
            "decision": verdict, "reason_code": {"positive": pos, "negative": neg, "inconclusive": "insufficient_evidence"}[verdict],
            "reason": "Synthetic test response, never a Qwen observation.",
            "evidence_refs": [r for t in assessments for r in t["evidence_refs"]],
            "feedback_action": "none" if verdict == "positive" else "revise_candidate"}
        n = len(self.tokenizer.encode(pilot.context.serialized_chat(request), add_special_tokens=False).ids)
        return {"done": True, "done_reason": "stop", "prompt_eval_count": n, "eval_count": 200,
                "message": {"content": "{bad" if malformed else json.dumps(output)}}

    def test_case_composition_and_exact_trial_labels(self):
        counts = Counter((r["technique"], r["decision"]) for r in self.labels["cases"])
        self.assertEqual(len(self.cases), 42)
        for technique in pilot.rag.TECHNIQUES:
            for decision in pilot.CLASSES:
                self.assertEqual(counts[(technique, decision)], 4)
            self.assertEqual(counts[(technique, None)], 2)
        # Independent Decimal labels also agree with the frozen executable contract on this package.
        for case in self.cases:
            doc = case["input"]
            frozen = pilot.rag.base.frozen.trial_rule_signals(doc)
            expected = pilot.dataset.expected_trials(doc)
            if pilot.dataset.eligible(doc):
                self.assertEqual(frozen, {r["trial"]: r["outcome"] == "positive" for r in expected})
        boundary = next(r for r in self.labels["cases"] if "1499.8" in r["rationale"])
        self.assertEqual(boundary["decision"], "negative")

    def test_schedule_balanced_overall_and_in_each_eligible_technique(self):
        balance = pilot.audit_schedule(self.cases, self.schedule)
        self.assertEqual(balance["all"]["A"], {"1": 14, "2": 14, "3": 14})
        self.assertEqual(balance["eligible"]["B3"], {"1": 12, "2": 12, "3": 12})
        for technique in pilot.rag.TECHNIQUES:
            ids = {c["case_id"] for c in self.cases if c["input"]["technique"] == technique and pilot.dataset.eligible(c["input"])}
            counts = Counter((r["profile"], r["position_within_case"]) for r in self.schedule if r["case_id"] in ids)
            self.assertEqual(set(counts.values()), {4})

    def test_actual_requests_only_reference_changes_no_label_leakage(self):
        self.assertEqual(len(self.audit), 126)
        self.assertGreater(min(r["reserved_headroom"] for r in self.audit), 0)
        for case in self.cases:
            group = [r for r in self.audit if r["case_id"] == case["case_id"]]
            self.assertEqual(len({r["common_request_sha256_without_reference_context"] for r in group}), 1)
        for row in self.requests:
            text = json.dumps(row["request"]["messages"])
            for forbidden in ("pilot-", "rationale", "researcher_review", "trial_assessments\": ["):
                self.assertNotIn(forbidden, text)
            self.assertNotIn("stop", row["request"]["options"])
        bad = copy.deepcopy(self.requests)
        bad[1]["request"]["messages"][0]["content"] += " Changed contract."
        bad[1]["request_sha256"] = pilot.rag.sha(bad[1]["request"])
        with self.assertRaisesRegex(ValueError, "outside reference_context"):
            pilot.audit_requests(self.cases, bad, self.tokenizer)

    def test_invalid_inputs_make_zero_calls(self):
        ids = {c["case_id"] for c in self.cases if not pilot.dataset.eligible(c["input"])}
        schedule = [r for r in self.schedule if r["case_id"] in ids]
        events = []
        def forbidden(request):
            self.fail("Invalid input reached the model client.")
        status = pilot.run_slots(self.cases, schedule, self.requests, self.audit, forbidden, events.append)
        self.assertEqual(status, "completed")
        self.assertEqual(len(events), 18)
        self.assertTrue(all(e["status"] == "input_invalid" and not e["attempted"] for e in events))

    def test_any_overbudget_request_aborts_before_first_call(self):
        audit = copy.deepcopy(self.audit)
        audit[-1]["prompt_tokens"] = pilot.OPTIONS["num_ctx"]
        with self.assertRaisesRegex(ValueError, "before any call"):
            pilot.run_slots(self.cases, self.schedule, self.requests, audit,
                            lambda req: self.fail("Budget guard ran too late"), lambda event: None)

    def test_malformed_json_and_exhausted_output_are_errors_without_retry(self):
        calls, events = [], []
        def client(request):
            calls.append(request)
            response = self.response(request, malformed=len(calls) == 1)
            if len(calls) == 2:
                response.update(done_reason="length", eval_count=768)
            return response
        schedule = [r for r in self.schedule if r["case_id"] == "pilot-001"]
        pilot.run_slots(self.cases, schedule, self.requests, self.audit, client, events.append)
        results = [e for e in events if e["event"] == "finished"]
        self.assertEqual(len(calls), 3)
        self.assertEqual([r["status"] for r in results], ["analysis_error", "analysis_error", "ok"])
        score = pilot.summarize(self.cases, self.labels, self.schedule, events)
        for row in score["profiles"].values():
            self.assertEqual(row["attempted_eligible"], 1)
            self.assertEqual(row["trial_denominator"], 3)
        self.assertEqual(score["primary"]["conclusion"], "incomplete")

    def test_transport_error_stays_in_denominator_and_halts(self):
        calls, events = [], []
        def client(request):
            calls.append(request)
            raise TimeoutError("Simulated timeout")
        status = pilot.run_slots(self.cases, self.schedule, self.requests, self.audit, client, events.append)
        self.assertEqual(status, "halted-transport-error")
        self.assertEqual(len(calls), 1)
        score = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual(sum(r["analysis_errors"] for r in score["profiles"].values()), 1)
        self.assertEqual(sum(r["attempted_eligible"] for r in score["profiles"].values()), 1)
        self.assertFalse(score["primary"]["complete"])

    def test_negative_claim_and_abstention_are_separate_on_positive_reference(self):
        slots = [r for r in self.schedule if r["case_id"] == "pilot-001"]
        events = []
        reqs = {(r["case_id"], r["profile"]): r["request"] for r in self.requests}
        counts = {(r["case_id"], r["profile"]): r["prompt_tokens"] for r in self.audit}
        for slot in slots:
            verdict = {"A": "negative", "B2": "inconclusive", "B3": "positive"}[slot["profile"]]
            req = reqs[(slot["case_id"], slot["profile"])]
            parsed = pilot.parse_output(self.cases[0]["input"], req, self.response(req, decision=verdict), counts[(slot["case_id"], slot["profile"])])
            events.extend([{**slot, "event": "attempt_started"}, {**slot, "event": "finished", **parsed}])
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual(result["profiles"]["A"]["reference_output_matrix"]["positive"]["negative"], 1)
        self.assertEqual(result["profiles"]["B2"]["reference_output_matrix"]["positive"]["inconclusive"], 1)
        self.assertEqual(result["profiles"]["B3"]["raw_correct"], 1)
        self.assertEqual(result["profiles"]["B2"]["binary_coverage"], 0)

    def test_raw_decision_preserved_despite_semantic_contradiction(self):
        req = self.requests[0]["request"]
        response = self.response(req, decision="negative")
        parsed = pilot.parse_output(self.cases[0]["input"], req, response, self.audit[0]["prompt_tokens"])
        self.assertEqual(parsed["decision"], "negative")
        self.assertEqual(parsed["status"], "ok")
        self.assertIn("model_summary_decision_mismatch", parsed["warnings"])

    def test_context_mismatch_halts_and_unknown_reference_is_analysis_error(self):
        req = self.requests[0]["request"]
        response = self.response(req)
        response["prompt_eval_count"] -= 1
        parsed = pilot.parse_output(self.cases[0]["input"], req, response, self.audit[0]["prompt_tokens"])
        self.assertTrue(parsed["halt"])
        self.assertEqual(parsed["error"], "prompt-count-mismatch")
        response = self.response(req)
        content = json.loads(response["message"]["content"])
        content["evidence_refs"].append("obs-099")
        response["message"]["content"] = json.dumps(content)
        parsed = pilot.parse_output(self.cases[0]["input"], req, response, self.audit[0]["prompt_tokens"])
        self.assertEqual(parsed["error"], "unknown-observation-reference")

    def test_interrupted_attempt_counted_as_error_and_duplicate_attempt_rejected(self):
        slot = next(r for r in self.schedule if r["case_id"] == "pilot-001")
        start = {**slot, "event": "attempt_started"}
        summary = pilot.summarize(self.cases, self.labels, self.schedule, [start])
        row = summary["profiles"][slot["profile"]]
        self.assertEqual(row["attempted_eligible"], 1)
        self.assertEqual(row["analysis_errors"], 1)
        self.assertEqual(row["unfinished_attempts"], 1)
        self.assertEqual(row["raw_accuracy"], 0)
        with self.assertRaisesRegex(ValueError, "Duplicate attempt"):
            pilot.summarize(self.cases, self.labels, self.schedule, [start, start])

    def test_complete_simulated_session_has_108_calls_and_18_skips(self):
        calls, events = [], []
        def client(request):
            calls.append(request)
            return self.response(request)
        status = pilot.run_slots(self.cases, self.schedule, self.requests, self.audit, client, events.append)
        self.assertEqual(status, "completed")
        self.assertEqual(len(calls), 108)
        result = pilot.summarize(self.cases, self.labels, self.schedule, events)
        self.assertEqual(result["skipped_invalid_slots"], 18)
        self.assertEqual(result["input_gate_violations"], [])
        self.assertTrue(result["primary"]["complete"])
        self.assertEqual(result["primary"]["conclusion"], "no-raw-accuracy-improvement")
        self.assertEqual(result["profiles"]["A"]["trial_denominator"], 102)


if __name__ == "__main__":
    unittest.main()
