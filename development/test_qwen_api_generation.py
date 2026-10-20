"""Offline generator checks for slot metadata and structural deduplication."""

import json
import unittest

from qwen_api_generation import (COMPACT_PROMPT_VERSION, COMPACT_S1_CONTEXT_PROMPT_VERSION,
                                 COMPACT_S2_CONTEXT_PROMPT_VERSION,
                                 COMPACT_S3_CONTEXT_PROMPT_VERSION, generate_one, parse,
                                 prepare, prepare_compact, prepare_compact_s1_low_context,
                                 prepare_compact_s2_low_context, prepare_compact_s3_low_context,
                                 structural_key)


S1 = {"scenario_id": "S1", "probe_kind": "single_error", "sqli_type": "error-based",
      "method": "GET", "input_path": "/vulnerabilities/sqli/",
      "result_path": "/vulnerabilities/sqli/", "parameter": "id"}
S2_LOW = {"scenario_id": "S2", "security_level": "low", "probe_kind": "boolean_pair",
          "sqli_type": "boolean-based blind", "method": "GET",
          "input_path": "/vulnerabilities/sqli_blind/",
          "result_path": "/vulnerabilities/sqli_blind/", "parameter": "id"}
S1_LOW = {**S1, "security_level": "low"}
S3_LOW = {"scenario_id": "S3", "security_level": "low", "probe_kind": "single_time",
          "sqli_type": "time-based blind", "method": "GET",
          "input_path": "/vulnerabilities/sqli_blind/",
          "result_path": "/vulnerabilities/sqli_blind/", "parameter": "id"}


class GeneratorTests(unittest.TestCase):
    def test_slot_id_stays_in_metadata_and_no_numeric_nonce_is_required(self):
        prepared = prepare(S1, [], candidate_count=1)
        self.assertEqual(prepared["slot_id"], 1)
        combined = " ".join(message["content"] for message in prepared["messages"])
        self.assertNotIn("assigned slot integer", combined)
        self.assertNotIn("101", combined)
        self.assertIn("Candidate slot ID is metadata", combined)

    def test_literal_changes_do_not_create_new_structure(self):
        self.assertEqual(structural_key({"payload": "1'"}, "single_error"),
                         structural_key({"payload": "101'"}, "single_error"))
        self.assertNotEqual(structural_key({"payload": "1'"}, "single_error"),
                            structural_key({"payload": '1"'}, "single_error"))

    def test_parser_rejects_number_only_duplicate(self):
        prepared = prepare(S1, ["1'"], candidate_count=1)
        api = {"status": "ok", "content": json.dumps({"candidates": [{"payload": "101'"}]})}
        result = parse(prepared, ["1'"], "single_error", api)
        self.assertEqual(result["status"], "no_valid_distinct_candidate")
        self.assertEqual(result["audit"]["suggestions"][0]["status"], "duplicate_structure")

    def test_duplicate_json_key_is_rejected(self):
        prepared = prepare(S1, [], candidate_count=1)
        api = {"status": "ok", "content": '{"candidates":[{"payload":"1\u0027","payload":"1\\\""}]}' }
        self.assertEqual(parse(prepared, [], "single_error", api)["status"],
                         "invalid_candidate_format")

    def test_serial_wrapper_selects_distinct_candidate(self):
        class FakeClient:
            def chat(self, messages):
                self.messages = messages
                return {"status": "ok", "content": json.dumps({"candidates": [{"payload": '1"'}]}),
                        "request_sha256": "f" * 64, "reported_model": "self-dploy/Qwen3.8-27B"}

        client = FakeClient()
        result = generate_one(client, S1, ["1'"], candidate_count=1)
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["candidate"], {"payload": '1"'})
        self.assertEqual(len(client.messages), 2)
        self.assertEqual(result["api_result"]["reported_model"], "self-dploy/Qwen3.8-27B")
        self.assertEqual(result["prepared"]["slot_id"], 2)

    def test_compact_prompt_uses_qwen_no_think_and_bounded_task_rules(self):
        prepared = prepare_compact({**S1, "probe_kind": "single_error"}, [], candidate_count=1)
        system, user = prepared["messages"]
        self.assertEqual(prepared["prompt_version"], COMPACT_PROMPT_VERSION)
        self.assertIn("/no_think", system["content"])
        self.assertIn("/no_think", user["content"])
        self.assertIn("exactly 1 candidate", user["content"])
        self.assertIn("SQL syntax diagnostic", user["content"])
        self.assertNotIn("101", system["content"] + user["content"])

    def test_compact_boolean_and_time_prompts_preserve_probe_contracts(self):
        boolean = prepare_compact({**S1, "probe_kind": "boolean_pair",
                                   "sqli_type": "boolean-based blind"}, [], candidate_count=1)
        timing = prepare_compact({**S1, "probe_kind": "single_time",
                                  "sqli_type": "time-based blind"}, [], candidate_count=1)
        self.assertIn("change only the truth condition", boolean["messages"][1]["content"])
        self.assertIn("0 < x <= 2", timing["messages"][1]["content"])
        self.assertIn("changing x to 0", timing["messages"][1]["content"])

    def test_context_prompt_pins_verified_s2_quote_and_absent_id(self):
        prepared = prepare_compact_s2_low_context(
            S2_LOW, [{"true_payload": "1 OR 1=1", "false_payload": "1 OR 1=2"}],
            feedback={"signals": [False, False, False]})
        self.assertEqual(prepared["prompt_version"], COMPACT_S2_CONTEXT_PROMPT_VERSION)
        prompt = "\n".join(message["content"] for message in prepared["messages"])
        self.assertIn("WHERE user_id = '$id'", prompt)
        self.assertIn("ID 1 exists and ID 0 is absent", prompt)
        self.assertIn("0' OR '1'='1", prompt)
        self.assertIn("0' OR '1'='2", prompt)
        self.assertNotIn("existing benign numeric ID literal", prompt)

    def test_context_prompt_rejects_other_scenarios_or_levels(self):
        for scenario in (S1, {**S2_LOW, "scenario_id": "S8", "security_level": "high"},
                         {**S2_LOW, "security_level": "medium"}):
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                prepare_compact_s2_low_context(scenario, [])

    def test_specialized_s1_prompt_pins_low_quoted_error_context(self):
        prepared = prepare_compact_s1_low_context(S1_LOW)
        system, user = prepared["messages"]
        self.assertEqual(prepared["prompt_version"], COMPACT_S1_CONTEXT_PROMPT_VERSION)
        self.assertEqual(prepared["candidate_count"], 1)
        self.assertIn("WHERE user_id = '$id';", user["content"])
        self.assertIn("syntax diagnostic", user["content"])
        self.assertIn("syntax-only", user["content"])
        self.assertNotIn("SLEEP", user["content"])
        self.assertIn("/no_think", system["content"] + user["content"])

    def test_specialized_s3_prompt_pins_quoted_id_and_bounded_control(self):
        prepared = prepare_compact_s3_low_context(S3_LOW)
        user = prepared["messages"][1]["content"]
        self.assertEqual(prepared["prompt_version"], COMPACT_S3_CONTEXT_PROMPT_VERSION)
        self.assertEqual(prepared["candidate_count"], 1)
        self.assertIn("ID 1 exists", user)
        self.assertIn("SLEEP(2)", user)
        self.assertIn("replacing only the literal 2 inside SLEEP(2) with 0", user)
        self.assertIn("MySQL # line comment", user)
        self.assertNotIn("SLEEP(3)", user)

    def test_specialized_context_prompts_reject_wrong_scenario_or_level(self):
        for prepare_context, scenario in (
                (prepare_compact_s1_low_context, {**S1_LOW, "security_level": "medium"}),
                (prepare_compact_s1_low_context, S2_LOW),
                (prepare_compact_s3_low_context, {**S3_LOW, "scenario_id": "S9",
                                                  "security_level": "high"}),
                (prepare_compact_s3_low_context, {**S3_LOW, "probe_kind": "boolean_pair"})):
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                prepare_context(scenario)


if __name__ == "__main__":
    unittest.main()
