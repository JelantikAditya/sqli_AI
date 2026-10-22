"""Offline regression checks for the versioned Poolside generation retries."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import poolside_laguna_generation_v2 as generation_v2


class FakeAPI:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def chat(self, stage, messages, attempt_directory):
        self.messages.append(messages)
        return ({"status": "ok", "content": next(self.responses)},
                {"request_sha256": f"request-{len(self.messages)}", "stage": stage})


class PoolsideGenerationV2Tests(unittest.TestCase):
    def setUp(self):
        self.error_scenario = {
            "scenario_id": "S1", "probe_kind": "single_error", "sqli_type": "error-based",
            "method": "GET", "input_path": "/vulnerabilities/sqli/",
            "result_path": "/vulnerabilities/sqli/", "parameter": "id",
        }
        self.config = {"limits": {"max_retrieved_chars_per_chunk": 1000}}

    def callback(self, api, scenario=None):
        return generation_v2.make_generation_callback(
            api, ROOT / "results/raw/offline-generation-test",
            scenario or self.error_scenario, None, {"http_status": 200}, self.config)

    @staticmethod
    def reply(value):
        return json.dumps({"candidates": [value]}, separators=(",", ":"))

    def test_malformed_json_gets_typed_feedback_and_a_distinct_retry_prompt(self):
        malformed = '{"candidates":[{"payload":"1`)}"]}'
        api = FakeAPI([malformed, self.reply({"payload": '2"'})])
        generate = self.callback(api)
        candidate, first = generate(None, ["1'"], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(first["status"], "invalid_candidate_format")
        candidate, second = generate(None, ["1'"], 1, "invalid_candidate_format")
        self.assertEqual(candidate, '2"')
        self.assertEqual(second["status"], "generated")

        first_task = json.loads(api.messages[0][1]["content"])
        retry_task = json.loads(api.messages[1][1]["content"])
        self.assertEqual(first_task["generation_attempt"], 0)
        self.assertEqual(retry_task["generation_attempt"], 1)
        self.assertEqual(retry_task["validation_feedback"][0]["diagnostic"]["code"], "invalid_json")
        self.assertNotEqual(api.messages[0][1]["content"], api.messages[1][1]["content"])
        self.assertEqual(first["validation_diagnostic"]["line"], 1)

    def test_duplicate_uses_bounded_fallback_and_parser_still_excludes_structure(self):
        api = FakeAPI([self.reply({"payload": "2'"}), self.reply({"payload": '2")'})])
        generate = self.callback(api)
        candidate, first = generate(None, ["1'", "2'"], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(first["status"], "no_valid_distinct_candidate")
        candidate, second = generate(None, ["1'", "2'"], 1, "no_valid_distinct_candidate")
        self.assertEqual(candidate, '2")')
        retry_task = json.loads(api.messages[1][1]["content"])
        self.assertEqual(retry_task["variation_family"]["phase"], "fallback-1")
        self.assertEqual(second["same_slot_duplicate_exclusion_count"], 1)

    def test_numeric_boolean_variants_are_still_duplicates_after_normalization(self):
        scenario = {**self.error_scenario, "scenario_id": "S2", "probe_kind": "boolean_pair",
                    "sqli_type": "boolean-based blind"}
        attempted = [{"true_payload": "1 AND 1=1", "false_payload": "1 AND 1=2"}]
        api = FakeAPI([self.reply({"true_payload": "5 AND 5=5", "false_payload": "5 AND 5=6"})])
        _, audit = self.callback(api, scenario)(None, attempted, 0, None)
        self.assertEqual(audit["status"], "no_valid_distinct_candidate")
        self.assertEqual(audit["suggestions"][0]["status"], "duplicate_structure")

    def test_invalid_two_sleep_suggestion_is_not_sent_to_structural_key_cache(self):
        scenario = {**self.error_scenario, "scenario_id": "S3", "probe_kind": "single_time",
                    "sqli_type": "time-based blind"}
        invalid = "1' AND IF(1=1,SLEEP(2),SLEEP(0))-- -"
        valid = "1' AND IF(1=1,SLEEP(2),0)-- -"
        api = FakeAPI([self.reply({"payload": invalid}), self.reply({"payload": valid})])
        generate = self.callback(api, scenario)
        candidate, first = generate(None, [], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(first["status"], "no_valid_distinct_candidate")
        self.assertEqual(first["suggestions"][0]["status"], "invalid_policy")
        candidate, second = generate(None, [], 1, "no_valid_distinct_candidate")
        self.assertEqual(candidate["payload"], valid)
        self.assertEqual(second["status"], "generated")
        self.assertEqual(second["same_slot_duplicate_exclusion_count"], 0)

    def test_primary_and_fallback_family_are_deterministic_across_ab(self):
        for probe_kind, scenario_ids in (("single_error", ("S1", "S4")),
                                         ("boolean_pair", ("S2", "S5")),
                                         ("single_time", ("S3", "S6"))):
            for slot in (1, 6, 10):
                if slot > len(generation_v2.PRIMARY_FAMILIES[probe_kind]):
                    continue
                a = generation_v2._request_family(probe_kind, slot, 0)
                b = generation_v2._request_family(probe_kind, slot, 0)
                self.assertEqual(a, b)
            self.assertEqual(len(generation_v2.PRIMARY_FAMILIES[probe_kind]), 10)
            self.assertEqual(len(generation_v2.FALLBACK_FAMILIES[probe_kind]), 2)


if __name__ == "__main__":
    unittest.main()
