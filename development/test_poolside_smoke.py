"""Offline transport and credential isolation checks for the Poolside smoke."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_poolside_smoke as smoke


class Response(io.BytesIO):
    status = 200

    def __init__(self, body):
        super().__init__(json.dumps(body).encode())


class Opener:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Response(reply)


def model_list():
    return {"data": [{"id": smoke.MODEL}]}


def completion(**changes):
    body = {"model": smoke.MODEL, "usage": {"total_tokens": 20},
            "choices": [{"finish_reason": "stop", "message": {"content": "API_OK"}}]}
    body.update(changes)
    return body


class PoolsideSmokeTests(unittest.TestCase):
    def test_success_uses_exact_host_and_two_requests(self):
        opener = Opener(model_list(), completion())
        result = smoke.run_smoke("test-secret", opener)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([request.full_url for request in opener.requests],
                         [smoke.BASE_URL + "/models", smoke.BASE_URL + "/chat/completions"])
        payload = json.loads(opener.requests[1].data)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertNotIn("test-secret", json.dumps(result))

    def test_auth_failure_stops_before_chat_and_redacts_error(self):
        error = HTTPError(smoke.BASE_URL + "/models", 401, "Unauthorized", {},
                          io.BytesIO(b'{"error":"test-secret"}'))
        opener = Opener(error)
        result = smoke.run_smoke("test-secret", opener)
        self.assertEqual(result["status"], "model-list-request-failed")
        self.assertEqual(len(opener.requests), 1)
        self.assertNotIn("test-secret", json.dumps(result))

    def test_unavailable_model_does_not_substitute_or_send_chat(self):
        opener = Opener({"data": [{"id": "some-other-model"}]})
        self.assertEqual(smoke.run_smoke("test-secret", opener)["status"], "model-not-listed")
        self.assertEqual(len(opener.requests), 1)

    def test_wrong_model_and_truncated_response_fail(self):
        cases = [(completion(model="some-other-model"), "model-metadata-mismatch"),
                 (completion(choices=[{"finish_reason": "length", "message": {"content": "API_OK"}}]),
                  "unfinished-response")]
        for body, expected in cases:
            with self.subTest(expected=expected):
                opener = Opener(model_list(), body)
                self.assertEqual(smoke.run_smoke("test-secret", opener)["status"], expected)
                self.assertEqual(len(opener.requests), 2)

    def test_success_body_echoing_key_is_redacted(self):
        body = completion(extra="test-secret")
        result = smoke.run_smoke("test-secret", Opener(model_list(), body))
        self.assertNotIn("test-secret", json.dumps(result))
        self.assertEqual(result["requests"][1]["body"]["extra"], "[REDACTED]")

    def test_redirect_handler_does_not_follow_location(self):
        self.assertIsNone(smoke.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))

    def test_missing_key_does_not_open_network(self):
        opener = Opener()
        self.assertEqual(smoke.run_smoke("", opener)["status"], "missing-api-key")
        self.assertEqual(opener.requests, [])

    def test_dry_run_neither_reads_credentials_nor_opens_network(self):
        with patch.object(sys, "argv", ["run_poolside_smoke.py", "--dry-run"]), \
                patch.object(smoke, "load_key", side_effect=AssertionError("Key read")), \
                patch.object(smoke, "build_opener", side_effect=AssertionError("Network")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(smoke.main(), 0)
        self.assertFalse(json.loads(output.getvalue())["execution_started"])

    def test_saved_key_and_environment_are_isolated_from_qwen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.poolside.local"
            with patch.object(smoke.getpass, "getpass", return_value="test-poolside-key"):
                smoke.save_key(path)
            with patch.dict(os.environ, {smoke.ENV_NAME: "", "HCNSEC_API_KEY": "test-qwen-key"}):
                self.assertEqual(smoke.load_key(path), "test-poolside-key")
            with patch.dict(os.environ, {smoke.ENV_NAME: "test-environment-key"}):
                self.assertEqual(smoke.load_key(path), "test-environment-key")

    def test_save_aborts_if_hidden_input_is_unavailable(self):
        def insecure_prompt(*args):
            import warnings
            warnings.warn("No hidden input", smoke.getpass.GetPassWarning)
            return "test-secret"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.poolside.local"
            with patch.object(smoke.getpass, "getpass", side_effect=insecure_prompt):
                with self.assertRaises(smoke.getpass.GetPassWarning):
                    smoke.save_key(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
