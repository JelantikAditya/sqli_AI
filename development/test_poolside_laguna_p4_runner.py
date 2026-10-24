"""Offline safety and binding tests for the P4 formal runner."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_poolside_laguna_p4 as historical_p4
import run_poolside_laguna_p4_replicate3 as p4
import run_poolside_smoke as transport
from poolside_p3_runtime import CheckpointedPoolsideAPI


class PoolsideLagunaP4RunnerTests(unittest.TestCase):
    def test_frozen_inputs_validate_without_authorizing_execution(self):
        inputs = p4.verify_plan_inputs()
        self.assertEqual(inputs["plan"]["dataset"], "formal")
        self.assertEqual(inputs["protocol"]["status"], "frozen")
        self.assertEqual(len(inputs["slots"]), 36)
        self.assertEqual(sum(item["status"] != "excluded" for item in inputs["slots"]), 33)

    def test_superseded_initial_plan_fails_closed_on_its_pinned_source_hash(self):
        with self.assertRaisesRegex(
                ValueError,
                "Pinned P4 runtime sources changed: dvwa/run_local_experiments.py"):
            historical_p4.verify_plan_inputs()

    def test_execution_refuses_draft_protocol_before_local_or_remote_calls(self):
        inputs = p4.verify_plan_inputs()
        inputs["protocol"]["status"] = "draft"
        with patch.object(transport, "load_key", side_effect=AssertionError("key must stay unread")), \
                patch.object(transport, "request_once", side_effect=AssertionError("API must stay idle")), \
                patch.object(p4.engine.local_runner, "require_local_target",
                             side_effect=AssertionError("DVWA must not be contacted")):
            with self.assertRaisesRegex(ValueError, "protocol is frozen"):
                p4._validate_execution_release(inputs)

    def test_isolated_snapshot_mapping_uses_approved_archive_paths(self):
        inputs = p4.verify_plan_inputs()
        snapshot = p4._snapshot_for_attempt(inputs["plan"])
        self.assertEqual(snapshot["store_path_resolved"], str(p4.ARCHIVE_STORE.resolve()))
        self.assertEqual(len(snapshot["index_file_sha256"]), 6)
        self.assertTrue(all((p4.ROOT / Path(path)).resolve().is_relative_to(p4.ARCHIVE_ROOT.resolve())
                            for path in snapshot["index_file_sha256"]))

    def test_protocol_candidate_digest_survives_draft_to_frozen_status_change(self):
        protocol = p4.read_json(p4.PROTOCOL_PATH)
        candidate_digest = p4.protocol_candidate_sha256(protocol)
        frozen = dict(protocol)
        frozen["status"] = "frozen"
        frozen["freeze_candidate_sha256"] = candidate_digest
        self.assertEqual(candidate_digest, p4.protocol_candidate_sha256(frozen))

    def test_blocked_dry_run_does_not_read_key_or_call_poolside_or_dvwa(self):
        with patch.object(transport, "load_key", side_effect=AssertionError("key must stay unread")), \
                patch.object(transport, "request_once", side_effect=AssertionError("API must stay idle")), \
                patch.object(p4.engine.local_runner, "require_local_target",
                             side_effect=AssertionError("DVWA must stay idle")):
            readiness = p4.readiness_report()
        self.assertEqual(readiness["status"], "blocked-not-execution-ready")
        self.assertFalse(readiness["execution_authorized"])
        self.assertEqual(readiness["api_requests_sent"], 0)
        self.assertEqual(readiness["dvwa_requests_sent"], 0)
        self.assertFalse(readiness["credentials_read"])
        gates = {item["gate_id"]: item["status"] for item in readiness["gates"]}
        self.assertEqual(gates["fresh-discovery-and-review"], "open")

    def test_freeze_and_provider_gates_do_not_authorize_execution(self):
        readiness = p4.readiness_report()
        gates = {item["gate_id"]: item["status"] for item in readiness["gates"]}
        self.assertEqual(gates["direct-provider-free-quota-and-continuity"], "passed")
        self.assertEqual(gates["protocol-freeze"], "passed")
        self.assertEqual(gates["formal-execution-release"], "passed")
        self.assertFalse(readiness["execution_authorized"])
        self.assertFalse(readiness["execution_started"])

    def test_direct_payload_is_pinned_to_poolside_laguna(self):
        payload = CheckpointedPoolsideAPI.payload("generation", [{"role": "user", "content": "safe test"}])
        self.assertEqual(payload["model"], "poolside/laguna-s-2.1")
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], False)


if __name__ == "__main__":
    unittest.main()
