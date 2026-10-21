"""Offline checks for the one-shot P2 evaluation runner."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

from run_qwen_api_p2_eval import (
    DEFAULT_REQUESTS,
    load_or_create_manifest,
    load_requests,
    run_batch,
    exclusive_execution_lock,
    write_json_atomic,
)


class FakeFailureClient:
    def __init__(self, request_sha256):
        self.calls = 0
        self.request_sha256 = request_sha256

    def chat(self, messages):
        self.calls += 1
        return {
            "request_sha256": self.request_sha256,
            "status": "http-error",
            "http_status": 402,
            "halt": True,
        }


class QwenAPIP2EvalRunnerTests(unittest.TestCase):
    def test_frozen_packet_integrity(self):
        requests, digest = load_requests(DEFAULT_REQUESTS)
        self.assertEqual(len(requests), 18)
        self.assertEqual(len({row["review_id"] for row in requests}), 18)
        self.assertEqual(len(digest), 64)

    def test_integrity_failure_prevents_requests_from_loading(self):
        requests, _ = load_requests(DEFAULT_REQUESTS)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tampered.jsonl"
            requests[0]["prepared"]["payload"]["messages"][0]["content"] += " changed"
            path.write_text("\n".join(json.dumps(row) for row in requests), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "payload hash"):
                load_requests(path)

    def test_halted_call_is_recorded_and_never_retried(self):
        requests, digest = load_requests(DEFAULT_REQUESTS)
        client = FakeFailureClient(requests[0]["request_sha256"])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            manifest = run_batch(requests, digest, output, client, "test-secret")
            self.assertEqual(manifest["state"], "halted")
            self.assertEqual(client.calls, 1)
            with self.assertRaisesRegex(RuntimeError, "without retrying unresolved"):
                run_batch(requests, digest, output, client, "test-secret")
            self.assertEqual(client.calls, 1)
            saved = json.loads((output / "results" / f"{requests[0]['review_id']}.json").read_text())
            self.assertEqual(saved["api_status"], "http-error")
            self.assertNotIn("test-secret", json.dumps(saved))
            summary = json.loads((output / "evaluation-results.json").read_text())
            self.assertEqual(summary["state"], "halted")
            self.assertEqual(summary["api_status_counts"], {"http-error": 1})
            self.assertEqual(summary["cases"][0]["review_id"], requests[0]["review_id"])
            self.assertNotIn("test-secret", json.dumps(summary))

    def test_ambiguous_started_case_is_skipped_and_next_case_is_attempted_once(self):
        requests, digest = load_requests(DEFAULT_REQUESTS)
        client = FakeFailureClient(requests[1]["request_sha256"])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            output.mkdir()
            manifest = load_or_create_manifest(output, digest, requests)
            manifest["state"] = "ambiguous"
            write_json_atomic(output / "run-manifest.json", manifest)
            write_json_atomic(output / "request-started" / f"{requests[0]['review_id']}.json", {
                "review_id": requests[0]["review_id"],
                "request_sha256": requests[0]["request_sha256"],
                "started_at_utc": "2026-10-21T00:00:00Z",
                "policy": "single attempt; no retry",
            })

            manifest = run_batch(requests, digest, output, client, "test-secret",
                                 skip_ambiguous_and_continue=True)
            self.assertEqual(client.calls, 1)
            self.assertEqual(manifest["state"], "halted")
            unresolved = json.loads((output / "results" / f"{requests[0]['review_id']}.json").read_text())
            attempted = json.loads((output / "results" / f"{requests[1]['review_id']}.json").read_text())
            self.assertEqual(unresolved["api_status"], "ambiguous-no-response")
            self.assertFalse(unresolved["retry_performed"])
            self.assertEqual(attempted["api_status"], "http-error")
            with self.assertRaisesRegex(RuntimeError, "non-recoverable"):
                run_batch(requests, digest, output, client, "test-secret",
                          skip_ambiguous_and_continue=True)
            self.assertEqual(client.calls, 1)

    def test_halted_timeout_can_continue_without_retrying_timed_out_request(self):
        requests, digest = load_requests(DEFAULT_REQUESTS)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            output.mkdir()
            manifest = load_or_create_manifest(output, digest, requests)
            manifest["state"] = "halted"
            write_json_atomic(output / "run-manifest.json", manifest)
            write_json_atomic(output / "results" / f"{requests[0]['review_id']}.json", {
                "schema": "qwen-api-p2-case-result-v1",
                "review_id": requests[0]["review_id"],
                "request_sha256": requests[0]["request_sha256"],
                "api_status": "transport-error",
                "http_status": None,
                "request_completion_unknown": True,
                "retry_performed": False,
            })

            client = FakeFailureClient(requests[1]["request_sha256"])
            manifest = run_batch(requests, digest, output, client, "test-secret",
                                 skip_ambiguous_and_continue=True)

            self.assertEqual(client.calls, 1)
            self.assertEqual(manifest["state"], "halted")
            timed_out = json.loads((output / "results" / f"{requests[0]['review_id']}.json").read_text())
            self.assertEqual(timed_out["api_status"], "transport-error")
            self.assertTrue(timed_out["request_completion_unknown"])
            self.assertFalse(timed_out["retry_performed"])
            next_case = json.loads((output / "results" / f"{requests[1]['review_id']}.json").read_text())
            self.assertEqual(next_case["api_status"], "http-error")

    def test_second_process_cannot_acquire_active_execution_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock_path = Path(temp) / "run" / ".execution.lock"
            child_code = (
                "from pathlib import Path; import sys; "
                "sys.path.insert(0, str(Path.cwd() / 'development')); "
                "from run_qwen_api_p2_eval import exclusive_execution_lock; "
                f"p=Path({str(lock_path)!r}); "
                "\ntry:\n with exclusive_execution_lock(p): raise SystemExit(2)"
                "\nexcept RuntimeError: raise SystemExit(0)"
            )
            with exclusive_execution_lock(lock_path):
                completed = subprocess.run(
                    [sys.executable, "-c", child_code],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
