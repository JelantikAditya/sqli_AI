import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from adaptive_candidate_policy import candidate_key, candidate_probe_payload, candidate_values, observation_document
from adaptive_s1_loop import (PROBE_SLOT_PROFILES, assigned_slot_nonce, candidate_uses_slot_nonce,
                              generate_one, generation_messages, run_loop)
from analyze_response import normalize_analysis
from rag_pipeline import load_catalog
from unittest.mock import patch


class AdaptiveCandidatePolicyTests(unittest.TestCase):
    def test_boolean_pair_is_one_candidate_and_distinctness_is_checked(self):
        candidate = {"true_payload": "1' AND 1=1#", "false_payload": "1' AND 1=2#"}
        values = candidate_values(candidate, "boolean_pair")
        self.assertEqual(len(values), 2)
        self.assertNotEqual(candidate_key(candidate, "boolean_pair"),
                            candidate_key({"true_payload": "1' AND 1=2#", "false_payload": "1' AND 1=1#"}, "boolean_pair"))
        with self.assertRaisesRegex(ValueError, "must differ"):
            candidate_values({"true_payload": "1=1", "false_payload": "1=1"}, "boolean_pair")

    def test_time_candidate_has_bounded_matched_control_and_read_only_guard(self):
        self.assertEqual(candidate_values({"payload": "1' AND SLEEP(2)#"}, "single_time"),
                         ("1' AND SLEEP(2)#",))
        for payload in ("1' AND SLEEP(3)#", "1'; DROP TABLE users"):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                candidate_values({"payload": payload}, "single_time")
        with self.assertRaisesRegex(ValueError, "only for time"):
            candidate_values({"payload": "1' AND SLEEP(1)#"}, "single_error")

    def test_executor_roles_translate_to_analysis_roles_and_exact_payloads(self):
        scenario = load_catalog()["scenarios"][2]
        candidate = {"payload": "1' AND SLEEP(1)#"}
        self.assertEqual(candidate_probe_payload(candidate, "control"), "1' AND SLEEP(0)#")
        captured = [{"trial": 1, "role": "control", "indicators": [], "response": {
            "status": 200, "elapsed_ms": 12, "body_sha256": "a" * 64,
            "body": "User ID exists"}}]
        doc = observation_document(scenario, captured, 3, 1500)
        self.assertEqual(doc["technique"], "time-based blind")
        self.assertEqual(doc["observations"][0]["role"], "no_delay_control")
        self.assertEqual(doc["observations"][0]["content_markers"], ["user_id_exists"])

    def test_adaptive_loop_treats_boolean_pair_as_one_candidate_and_three_trials(self):
        context = {"experiment_id": "fixture", "run_id": "r1", "attempt_id": "a1",
                   "candidate_id": "__run__", "scenario_id": "S2",
                   "replicate": 1, "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        candidates = iter(({"true_payload": "1' AND 1=1#", "false_payload": "1' AND 1=2#"},
                           {"true_payload": "1' AND 2=2#", "false_payload": "1' AND 2=3#"}))
        observed = []

        def observe(candidate, confirmations):
            observed.append((candidate, confirmations))
            rows = []
            for trial in range(1, confirmations + 1):
                for role, markers in (("baseline", ["user_id_exists"]),
                                      ("true_condition", ["user_id_exists"]),
                                      ("false_condition", ["user_id_missing"])):
                    rows.append({"observation_id": f"obs-{len(rows)+1:03d}", "trial": trial, "role": role,
                                 "http_status": 200, "elapsed_ms": 12, "response_sha256": "a"*64,
                                 "diagnostics": [], "content_markers": markers})
            return {"schema_version": "1.0.0", "technique": "boolean-based blind",
                    "injection_point": {"method": "GET", "input_path": "/vulnerabilities/sqli_blind/",
                                        "result_path": "/vulnerabilities/sqli_blind/", "parameter": "id"},
                    "runtime_status": "valid", "baseline_valid": True,
                    "time_threshold_ms": 1500, "observations": rows}

        def analyze(evidence, candidate_context):
            return normalize_analysis(evidence, {"decision": "positive", "reason_code": "boolean_difference",
                "reason": "The paired markers are consistent.",
                "evidence_refs": [item["observation_id"] for item in evidence["observations"]],
                "feedback_action": "none"}, candidate_context)

        result = run_loop(context, lambda previous, attempted: (next(candidates), {"status": "generated"}),
                          observe, analyze, budget=2, slot_limit=2, probe_kind="boolean_pair")
        self.assertEqual([count for _, count in observed], [3, 3])
        self.assertEqual(len(result["candidate_records"]), 2)
        self.assertTrue(all(record["evidence_status"] == "CONSISTENT_POSITIVE"
                            for record in result["candidate_records"]))

    def test_generator_uses_scenario_specific_output_schema(self):
        scenario = load_catalog()["scenarios"][1]
        response = {"model": "qwen2.5:7b", "message": {"content":
                    '{"candidates":[{"true_payload":"1\' AND 101=101#","false_payload":"1\' AND 101=102#"}]}'}}
        with patch("adaptive_s1_loop.post_ollama", return_value=response) as call:
            candidate, audit = generate_one(scenario, None, [], seed=42)
        self.assertEqual(candidate["true_payload"], "1' AND 101=101#")
        self.assertEqual(candidate["false_payload"], "1' AND 101=102#")
        self.assertEqual(audit["status"], "generated")
        request = call.call_args.args[1]
        self.assertIn("true_payload", request["format"]["properties"]["candidates"]["items"]["required"])

    def test_adaptive_prompt_allows_timing_only_for_time_scenarios(self):
        scenarios = load_catalog()["scenarios"]
        boolean_prompt = "\n".join(part["content"] for part in generation_messages(scenarios[1], None, []))
        timing_prompt = "\n".join(part["content"] for part in generation_messages(scenarios[2], None, []))
        self.assertIn("Do not use timing functions or add a delay", boolean_prompt)
        self.assertNotIn("Use exactly one literal SLEEP", boolean_prompt)
        self.assertIn("Use exactly one literal SLEEP(2)", timing_prompt)
        self.assertNotIn("SLEEP(1)", timing_prompt)

    def test_slot_nonce_is_stable_for_retries_and_advances_after_acceptance(self):
        scenarios = load_catalog()["scenarios"]
        scenario = scenarios[1]
        first = generation_messages(scenario, None, [], retry_index=0)[1]["content"]
        retry = generation_messages(scenario, None, [], retry_index=1,
                                    rejection_code="slot_nonce_mismatch")[1]["content"]
        second = generation_messages(scenario, None, ["accepted-candidate"])[1]["content"]
        self.assertEqual(assigned_slot_nonce(0), 101)
        self.assertEqual(assigned_slot_nonce(1), 102)
        self.assertIn("assigned slot integer is 101", first)
        self.assertIn("assigned slot integer is 101", retry)
        self.assertIn("assigned slot integer is 102", second)

    def test_generation_rejects_candidate_without_assigned_slot_nonce(self):
        scenario = load_catalog()["scenarios"][1]
        response = {"model": "qwen2.5:7b", "message": {"content":
                    '{"candidates":[{"true_payload":"1\' AND 1=1#",'
                    '"false_payload":"1\' AND 1=2#"}]}'} }
        with patch("adaptive_s1_loop.post_ollama", return_value=response):
            candidate, audit = generate_one(scenario, None, [], seed=42)
        self.assertIsNone(candidate)
        self.assertEqual(audit["status"], "invalid_candidate")
        self.assertEqual(audit["rejection_code"], "slot_nonce_mismatch")

    def test_generation_accepts_slot_nonce_in_each_boolean_value(self):
        scenario = load_catalog()["scenarios"][1]
        response = {"model": "qwen2.5:7b", "message": {"content":
                    '{"candidates":[{"true_payload":"1\' AND 101=101#",'
                    '"false_payload":"1\' AND 101=102#"}]}'} }
        with patch("adaptive_s1_loop.post_ollama", return_value=response):
            candidate, audit = generate_one(scenario, None, [], seed=42)
        self.assertEqual(candidate["true_payload"], "1' AND 101=101#")
        self.assertEqual(candidate["false_payload"], "1' AND 101=102#")
        self.assertEqual(audit["assigned_slot_nonce"], 101)

    def test_s1_slot_nonce_must_be_the_initial_numeric_id(self):
        scenario = load_catalog()["scenarios"][0]
        self.assertTrue(candidate_uses_slot_nonce({"payload": "101'"}, scenario, 101))
        self.assertFalse(candidate_uses_slot_nonce({"payload": "1' AND 101=101#"}, scenario, 101))

    def test_non_s1_slots_receive_probe_kind_specific_diversity_guidance(self):
        scenarios = load_catalog()["scenarios"]
        for scenario in scenarios[1:]:
            with self.subTest(scenario=scenario["scenario_id"]):
                prompts = []
                for slot in range(len(PROBE_SLOT_PROFILES[scenario["probe_kind"]])):
                    messages = generation_messages(
                        scenario, None, [f"candidate-{i}" for i in range(slot)])
                    prompts.append(messages[1]["content"].split(
                        "Slot diversity requirement: ", 1)[1])
                self.assertEqual(len(set(prompts)), len(PROBE_SLOT_PROFILES[scenario["probe_kind"]]))
                self.assertTrue(all(prompt.strip() for prompt in prompts))
                if scenario["probe_kind"] == "single_time":
                    self.assertTrue(all("SLEEP(2)" in prompt for prompt in prompts))
                    self.assertTrue(all("SLEEP(1)" not in prompt for prompt in prompts))
                else:
                    self.assertTrue(all("SLEEP" not in prompt for prompt in prompts))

    def test_non_s1_retries_preserve_slot_family_and_request_unused_values(self):
        scenarios = load_catalog()["scenarios"]
        for scenario in scenarios[1:]:
            with self.subTest(scenario=scenario["scenario_id"]):
                first = generation_messages(scenario, None, ["attempted"], retry_index=0)[1]["content"]
                retry = generation_messages(scenario, None, ["attempted"], retry_index=1,
                                            rejection_code="duplicate_candidate")[1]["content"]
                self.assertEqual(
                    first.split("Slot diversity requirement: ", 1)[1],
                    retry.split("Slot diversity requirement: ", 1)[1])
                self.assertIn("unused", retry)
                self.assertNotEqual(first, retry)


if __name__ == "__main__":
    unittest.main()
