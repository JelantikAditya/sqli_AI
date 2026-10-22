"""Offline checks for the P3 call ceiling and frozen-profile deadline gate."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_bounded_qwen_p3_pilot as bounded
from qwen_api_runtime import APIRuntimeFailure, CheckpointedQwenAPI


class P3BudgetTests(unittest.TestCase):
    def test_deadline_rejects_request_before_transport_without_changing_timeout(self):
        config, _ = bounded.active.load_config()
        with tempfile.TemporaryDirectory() as directory:
            clock = [0]
            api = bounded.DeadlineQwenAPI("offline-dummy-secret", Path(directory), config,
                                        max_seconds=100, clock=lambda: clock[0])
            clock[0] = 11
            with patch.object(CheckpointedQwenAPI, "chat") as transport:
                with self.assertRaises(APIRuntimeFailure) as raised:
                    api.chat("analysis", [{"role": "user", "content": "offline"}], Path(directory))
            self.assertEqual(raised.exception.code, "pilot_time_budget_exceeded")
            transport.assert_not_called()
            self.assertEqual(api.settings["analysis"].timeout_seconds, 90)
            self.assertEqual(api.used_calls, 0)

    def test_deadline_allows_call_with_sufficient_time(self):
        config, _ = bounded.active.load_config()
        with tempfile.TemporaryDirectory() as directory:
            api = bounded.DeadlineQwenAPI("offline-dummy-secret", Path(directory), config,
                                        max_seconds=100, clock=lambda: 0)
            with patch.object(CheckpointedQwenAPI, "chat", return_value=({}, {})) as transport:
                self.assertEqual(api.chat("generation", [], Path(directory)), ({}, {}))
                transport.assert_called_once()

    def test_bound_call_ceiling_is_enforced_before_transport(self):
        config, _ = bounded.active.load_config()
        config = copy.deepcopy(config)
        config["limits"]["max_total_api_calls"] = 1
        with tempfile.TemporaryDirectory() as directory:
            api = bounded.DeadlineQwenAPI("offline-dummy-secret", Path(directory), config,
                                        max_seconds=100, clock=lambda: 0)
            api.used_calls = 1
            with patch.object(api.client["generation"], "chat") as transport:
                with self.assertRaises(APIRuntimeFailure) as raised:
                    api.chat("generation", [{"role": "user", "content": "offline"}], Path(directory))
                transport.assert_not_called()
            self.assertEqual(raised.exception.code, "api_call_ceiling_reached")


if __name__ == "__main__":
    unittest.main()
