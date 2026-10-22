"""Offline checks for the P3-only 180-second transport timeout profile."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_qwen_api_experiments as active
from qwen_api_client import QwenAPIClient, request_payload
from qwen_api_p2_analysis import default_settings as p2_analysis_settings
from qwen_api_runtime import APIRuntimeFailure
from run_bounded_qwen_p3_timeout180 import DeadlineQwenAPI


class P3Timeout180Tests(unittest.TestCase):
    def make_api(self, max_seconds=600):
        config, _ = active.load_config()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / "experiment"
        with patch.object(QwenAPIClient, "chat", side_effect=AssertionError("network call blocked")):
            api = DeadlineQwenAPI(
                "offline-test-key", directory, config,
                analysis_timeout_seconds=180, max_seconds=max_seconds, clock=lambda: 0)
        return api, directory

    def test_analysis_timeout_is_extended_without_changing_generation_or_p2(self):
        api, _ = self.make_api()
        self.assertEqual(p2_analysis_settings().timeout_seconds, 90)
        self.assertEqual(api.settings["generation"].timeout_seconds, 90)
        self.assertEqual(api.settings["analysis"].timeout_seconds, 180)

        messages = [{"role": "user", "content": "fixture"}]
        extended = api.settings["analysis"]
        original = p2_analysis_settings()
        self.assertEqual(request_payload(messages, extended), request_payload(messages, original))

    def test_deadline_gate_reserves_180_seconds_before_analysis(self):
        api, directory = self.make_api(max_seconds=179)
        with self.assertRaises(APIRuntimeFailure) as raised:
            api.chat("analysis", [{"role": "user", "content": "offline"}], directory)
        self.assertEqual(raised.exception.code, "pilot_time_budget_exceeded")
        self.assertEqual(api.used_calls, 0)
        self.assertFalse(directory.exists())

    def test_deadline_gate_allows_analysis_when_more_than_180_seconds_remain(self):
        api, _ = self.make_api(max_seconds=181)
        api.require_time("analysis")


if __name__ == "__main__":
    unittest.main()
