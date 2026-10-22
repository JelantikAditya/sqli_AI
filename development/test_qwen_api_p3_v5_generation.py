"""Offline tests for P3 v5 same-slot duplicate retry memory."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import qwen_api_p3_v5_generation as generation_retry


class FakeAPI:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.messages = []

    def chat(self, stage, messages, attempt_directory):
        self.messages.append(messages)
        payload = next(self.payloads)
        return ({"status": "ok", "content": json.dumps({"candidates": [{"payload": payload}]})},
                {"request_sha256": f"request-{len(self.messages)}", "stage": stage})


class DuplicateRetryMemoryTests(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "scenario_id": "S1",
            "probe_kind": "single_error",
            "sqli_type": "error-based",
            "method": "GET",
            "input_path": "/vulnerabilities/sqli/",
            "result_path": "/vulnerabilities/sqli/",
            "parameter": "id",
        }

    def test_duplicate_suggestion_is_prompted_and_excluded_on_retry(self):
        api = FakeAPI(["2'", "2'", "2')"])
        callback = generation_retry.make_generation_callback(
            api, ROOT / "results/raw/test", self.scenario, None,
            {"http_status": 200}, {"limits": {"max_retrieved_chars_per_chunk": 1000}})
        attempted = ["1'"]

        candidate, first = callback(None, attempted, 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(first["status"], "no_valid_distinct_candidate")
        self.assertEqual(first["same_slot_rejected_count_after_request"], 1)

        candidate, second = callback(None, attempted, 1, "no_valid_distinct_candidate")
        self.assertIsNone(candidate)
        self.assertEqual(second["status"], "no_valid_distinct_candidate")
        self.assertEqual(second["same_slot_rejected_count_before_request"], 1)
        self.assertEqual(second["suggestions"][0]["status"], "duplicate_structure")
        self.assertIn("2'", api.messages[1][1]["content"])

        candidate, third = callback(None, attempted, 2, "no_valid_distinct_candidate")
        self.assertEqual(candidate, "2')")
        self.assertEqual(third["status"], "generated")
        self.assertEqual(third["same_slot_rejected_count_before_request"], 1)

    def test_retry_cache_is_isolated_by_candidate_slot(self):
        api = FakeAPI(["2'", "2')", "3'", "3'"])
        callback = generation_retry.make_generation_callback(
            api, ROOT / "results/raw/test", self.scenario, None,
            {"http_status": 200}, {"limits": {"max_retrieved_chars_per_chunk": 1000}})
        _, first_slot = callback(None, ["1'"], 0, None)
        self.assertEqual(first_slot["same_slot_rejected_count_after_request"], 1)

        # A successful candidate advances the caller's attempted list, so the
        # next slot starts with an empty retry-exclusion cache.
        candidate, second_slot = callback(None, ["1'"], 1, "no_valid_distinct_candidate")
        self.assertEqual(candidate, "2')")
        candidate, third_slot = callback(None, ["1'", "2')"], 0, None)
        self.assertIsNone(candidate)
        self.assertEqual(third_slot["same_slot_rejected_count_before_request"], 0)

        # The first rejection in a new slot is remembered for its own retry.
        candidate, fourth_slot = callback(None, ["1'", "2')"], 1, "no_valid_distinct_candidate")
        self.assertIsNone(candidate)
        self.assertEqual(fourth_slot["same_slot_rejected_count_before_request"], 1)


if __name__ == "__main__":
    unittest.main()
