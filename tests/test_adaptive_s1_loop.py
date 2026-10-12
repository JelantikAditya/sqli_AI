"""Control-flow checks for the bounded S1 feedback pilot."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from adaptive_s1_loop import (feedback_view, generation_messages, run_loop,
                              validate_payload)
from analyze_response import normalize_analysis
from rag_pipeline import load_catalog


class AdaptiveS1LoopTests(unittest.TestCase):
    def setUp(self):
        self.context = {"experiment_id": "pilot", "run_id": "run1", "attempt_id": "attempt1",
                        "candidate_id": "__run__", "scenario_id": "S1", "replicate": 1,
                        "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        self.scenario = load_catalog()["scenarios"][0]

    def evidence(self, payload, diagnostic=False):
        observations = []
        for trial in range(1, 4):
            observations.append(
                {"observation_id": f"obs-{len(observations) + 1:03d}", "trial": trial,
                 "role": "baseline", "http_status": 200, "elapsed_ms": 5,
                 "response_sha256": "a" * 64, "diagnostics": [],
                 "content_markers": ["benign_record"]})
            observations.append(
                {"observation_id": f"obs-{len(observations) + 1:03d}", "trial": trial,
                 "role": "candidate", "http_status": 200, "elapsed_ms": 5,
                 "response_sha256": "b" * 64,
                 "diagnostics": ["mysql_syntax_error"] if diagnostic else [],
                 "content_markers": []})
        return {"schema_version": "1.0.0", "technique": "error-based",
                "injection_point": {k: self.scenario[k] for k in
                                     ("method", "input_path", "result_path", "parameter")},
                "runtime_status": "valid", "baseline_valid": True, "time_threshold_ms": 1500,
                "observations": observations}

    def analyze(self, evidence, context, decision, feedback_action):
        reason_code = {"positive": "new_database_diagnostic",
                       "negative": "no_new_database_diagnostic",
                       "inconclusive": "insufficient_evidence"}[decision]
        output = {"decision": decision, "reason_code": reason_code,
                  "reason": "Matches the supplied observations.",
                  "evidence_refs": [o["observation_id"] for o in evidence["observations"][:2]],
                  "feedback_action": feedback_action}
        return normalize_analysis(evidence, output, context)

    def test_failed_candidate_evidence_drives_unique_next_candidate(self):
        generated_with = []
        observations = []
        candidates = iter(["1' OR '1'='1", "1'"])

        def generate(previous, attempted):
            generated_with.append(feedback_view(previous) if previous else None)
            return next(candidates), {"status": "generated"}

        def observe(payload, confirmations):
            observations.append((payload, confirmations))
            return self.evidence(payload, diagnostic=payload == "1'")

        def analyze(evidence, context):
            payload = observations[-1][0]
            return self.analyze(evidence, context,
                                "positive" if payload == "1'" else "negative",
                                "none" if payload == "1'" else "revise_candidate")

        result = run_loop(self.context, generate, observe, analyze, slot_limit=2)
        self.assertEqual([entry[0] for entry in observations], ["1' OR '1'='1", "1'"])
        self.assertEqual([entry[1] for entry in observations], [3, 3])
        self.assertEqual(generated_with[1]["decision"], "negative")
        self.assertEqual(generated_with[1]["feedback_action"], "revise_candidate")
        self.assertEqual(result["stop_reason"], "pilot_slot_limit")
        self.assertFalse(result["formal_eligible"])
        self.assertEqual(result["run_summary"]["run_status"], "incomplete")
        self.assertEqual(result["run_summary"]["system_decision"], "not_evaluable")

    def test_inconclusive_feedback_collects_one_extra_round_for_same_candidate(self):
        calls = {"observe": 0, "analyze": 0}

        def observe(payload, confirmations):
            calls["observe"] += 1
            return self.evidence(payload, diagnostic=True)

        def analyze(evidence, context):
            calls["analyze"] += 1
            if calls["analyze"] == 1:
                return self.analyze(evidence, context, "inconclusive", "collect_more_evidence")
            return self.analyze(evidence, context, "positive", "none")

        result = run_loop(self.context,
                          lambda previous, attempted: ("1'", {"status": "generated"}),
                          observe, analyze, slot_limit=1)
        record = result["candidate_records"][0]
        self.assertEqual(calls, {"observe": 2, "analyze": 2})
        self.assertEqual(len(record["evidence"]["observations"]), 12)
        self.assertEqual(record["system_claim"], "positive")
        revisions = [e["data"]["revision"] for e in result["events"]
                     if e["kind"] == "candidate_analysis"]
        self.assertEqual(revisions, [1, 2])

    def test_duplicate_generation_retries_are_bounded_and_not_executed(self):
        observations = []

        def generate(previous, attempted):
            return "1'", {"status": "generated"}

        def observe(payload, confirmations):
            observations.append(payload)
            return self.evidence(payload)

        result = run_loop(self.context, generate, observe,
                          lambda evidence, context: self.analyze(evidence, context, "negative", "revise_candidate"),
                          slot_limit=2, generation_retries=2)
        self.assertEqual(observations, ["1'"])
        self.assertEqual(result["stop_reason"], "generation_exhausted")
        self.assertEqual(len(result["candidate_records"]), 1)
        duplicates = [e for e in result["events"]
                      if e["kind"] == "generation" and e["data"]["status"] == "duplicate"]
        self.assertEqual(len(duplicates), 3)

    def test_feedback_prompt_excludes_free_text_labels_and_attempted_values(self):
        evidence = self.evidence("1'", diagnostic=False)
        record = self.analyze(evidence, {**self.context, "candidate_id": "candidate-001"},
                              "negative", "revise_candidate")
        view = feedback_view({"payload": "1'", "analysis": record})
        messages = generation_messages(self.scenario, {"payload": "1'", "analysis": record}, ["1'"])
        prompt = "\n".join(item["content"] for item in messages)
        self.assertEqual(view["decision"], "negative")
        self.assertNotIn("ground_truth", prompt)
        self.assertNotIn("security_level", prompt)
        self.assertNotIn("condition_id", prompt)
        self.assertIn("Attempted parameter values", prompt)
        self.assertIn("no_new_database_diagnostic", prompt)
        self.assertIn("diagnostics", prompt)

    def test_candidate_guard_rejects_mutation_and_delay_keywords(self):
        self.assertEqual(validate_payload("1'"), "1'")
        for value in ("1; DROP TABLE users", "1' OR SLEEP(2)", "1\n2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_payload(value)


if __name__ == "__main__":
    unittest.main()
