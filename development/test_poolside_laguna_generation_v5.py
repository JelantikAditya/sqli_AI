from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
sys.path.insert(0, str(ROOT / "maintenance"))

import poolside_laguna_generation_v4 as v4
import poolside_laguna_generation_v5 as generation
from replay_poolside_laguna_q3_v5 import replay as replay_q3


class FakeAPI:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def chat(self, stage, messages, attempt_directory):
        self.messages.append(messages)
        return ({"status": "ok", "content": next(self.responses),
                 "finish_reason": "stop", "usage": {"completion_tokens": 16}},
                {"request_sha256": f"request-{len(self.messages)}", "stage": stage})


class StructureFeedbackTests(unittest.TestCase):
    def test_signature_normalizes_case_whitespace_and_numeric_literals(self):
        first = "1' AND SLEEP(2)-- -"
        second = "9'  and sleep(1)-- -"

        self.assertEqual(generation.structure_signature(first, "single_time"),
                         generation.structure_signature(second, "single_time"))
        self.assertNotEqual(generation.structure_signature(first, "single_time"),
                            generation.structure_signature("1' OR SLEEP(2)-- -", "single_time"))

    def test_boolean_signature_preserves_true_false_pair_structure(self):
        first = {"true_payload": "0' OR '1'='1-- -",
                 "false_payload": "0' OR '1'='2-- -"}
        numeric_variant = {"true_payload": "4' OR '7'='7-- -",
                           "false_payload": "4' OR '7'='8-- -"}
        alternate = {"true_payload": "0' AND '1'='1-- -",
                     "false_payload": "0' AND '1'='2-- -"}

        self.assertEqual(generation.structure_signature(first, "boolean_pair"),
                         generation.structure_signature(numeric_variant, "boolean_pair"))
        self.assertNotEqual(generation.structure_signature(first, "boolean_pair"),
                            generation.structure_signature(alternate, "boolean_pair"))

    def test_retry_prompt_lists_accepted_and_rejected_patterns_without_reference_values(self):
        scenario = {
            "scenario_id": "S3", "probe_kind": "single_time", "sqli_type": "time-based blind",
            "method": "GET", "input_path": "/vulnerabilities/sqli_blind/",
            "result_path": "/vulnerabilities/sqli_blind/", "parameter": "id",
        }
        duplicate = {"candidates": [{"payload": "1' AND SLEEP(2)-- -"}]}
        unique = {"candidates": [{"payload": "1' OR SLEEP(2)-- -"}]}
        api = FakeAPI([json.dumps(duplicate), json.dumps(duplicate), json.dumps(unique)])
        callback = generation.make_generation_callback(
            api, ROOT / "unused", scenario, None, {"http_status": 200},
            {"limits": {"max_retrieved_chars_per_chunk": 1800}},
        )

        first, first_audit = callback(None, [], 0, None)
        self.assertIsNotNone(first)
        repeated, repeated_audit = callback(None, [first], 0, None)
        self.assertIsNone(repeated)
        self.assertEqual(repeated_audit["status"], "no_valid_distinct_candidate")
        recovered, retry_audit = callback(None, [first], 1, repeated_audit["status"])

        self.assertEqual(recovered, {"payload": "1' OR SLEEP(2)-- -"})
        self.assertNotEqual(first_audit["family_id"], repeated_audit["family_id"])
        self.assertNotEqual(repeated_audit["family_id"], retry_audit["family_id"])
        task = json.loads(api.messages[-1][1]["content"])
        contract = task["variation_contract"]
        signature = generation.structure_signature(first, "single_time")
        self.assertEqual(contract["avoid_structural_signatures"], [signature])
        self.assertIn("requested_family_pattern", contract)
        self.assertIn("numeric literals", contract["novelty_rule"])
        # The model receives a normalized abstract shape, not private family payload values.
        prompt = json.dumps(api.messages, ensure_ascii=False)
        self.assertNotIn(v4.FAMILIES["single_time"][1].reference_values[0], prompt)


class Q3ReplayTests(unittest.TestCase):
    def test_saved_q3_responses_replay_offline_with_v5_prompt_feedback(self):
        with patch("socket.socket.connect",
                   side_effect=AssertionError("Q3 replay must not open a network connection")):
            result = replay_q3()

        self.assertEqual(result["source_unit_count"], 24)
        self.assertEqual(result["source_generation_calls_replayed"], 274)
        self.assertEqual(result["saved_candidate_count"], 221)
        self.assertEqual(result["replayed_candidate_count"], 221)
        self.assertEqual(result["saved_generation_status_counts"], {
            "generated": 221,
            "invalid_candidate_format": 6,
            "no_valid_distinct_candidate": 47,
        })
        self.assertEqual(result["parser_status_mismatches"], [])
        self.assertEqual(result["saved_request_hash_mismatches"], 0)
        self.assertEqual(result["replayed_family_id_collisions"], 0)
        self.assertEqual(result["retry_signature_coverage_failures"], 0)
        self.assertTrue(result["source_files_unchanged"])
        self.assertEqual(result["api_requests_sent"], 0)
        self.assertEqual(result["dvwa_requests_sent"], 0)
        incomplete = {unit["unit"] for unit in result["units"] if not unit["budget_complete"]}
        self.assertEqual(incomplete, {"A/S3", "A/S12", "B/S3", "B/S8"})


if __name__ == "__main__":
    unittest.main()
