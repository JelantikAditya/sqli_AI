"""Local-only control checks for DVWA runtime and reset handling."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from rag_pipeline import load_catalog
from validation_loop import (DvwaClient, LocalRuntimeFailure, execute_candidate,
                             sql_error_markers)


SETUP_FORM = '''<form method="post" action="#">
<input type="hidden" name="user_token" value="csrf-local">
<input type="submit" name="create_db" value="Create / Reset Database">
</form>'''


class DvwaRuntimeControlTests(unittest.TestCase):
    def setUp(self):
        self.client = DvwaClient("http://127.0.0.1:4280", 2)

    def test_database_reset_posts_only_local_csrf_form_and_verifies_success(self):
        calls = []

        def fake_request(method, path, values=None):
            calls.append((method, path, values))
            if method == "GET":
                return {"status": 200, "body": SETUP_FORM, "elapsed_ms": 1,
                        "body_sha256": "a" * 64}
            return {"status": 200,
                    "body": "Database has been created. Setup successful!",
                    "elapsed_ms": 1, "body_sha256": "b" * 64}

        with patch.object(self.client, "request", side_effect=fake_request):
            receipt = self.client.reset_database()
            self.assertTrue(receipt["success_markers_verified"])
            self.assertTrue(self.client.database_reset_done)
            with self.assertRaisesRegex(LocalRuntimeFailure, "database_reset_failed"):
                self.client.reset_database()

        self.assertEqual(calls[0], ("GET", "/setup.php", None))
        self.assertEqual(calls[1], ("POST", "/setup.php",
                                    {"create_db": "Create / Reset Database", "user_token": "csrf-local"}))

    def test_database_reset_rejects_unexpected_form_action_without_posting(self):
        calls = []

        def fake_request(method, path, values=None):
            calls.append((method, path, values))
            return {"status": 200,
                    "body": SETUP_FORM.replace('action="#"', 'action="http://example.com/setup.php"'),
                    "elapsed_ms": 1, "body_sha256": "a" * 64}

        with patch.object(self.client, "request", side_effect=fake_request):
            with self.assertRaisesRegex(LocalRuntimeFailure, "setup_form_invalid"):
                self.client.reset_database()
        self.assertEqual(len(calls), 1)

    def test_database_reset_requires_both_explicit_success_markers(self):
        def fake_request(method, path, values=None):
            body = SETUP_FORM if method == "GET" else "Setup successful!"
            return {"status": 200, "body": body, "elapsed_ms": 1, "body_sha256": "a" * 64}

        with patch.object(self.client, "request", side_effect=fake_request):
            with self.assertRaisesRegex(LocalRuntimeFailure, "database_reset_failed"):
                self.client.reset_database()

    def test_session_verification_checks_login_and_exact_security_level(self):
        html = ('<a href="/logout.php">Logout</a><select name="security">'
                '<option value="low" selected>Low</option></select>')
        with patch.object(self.client, "get_form", return_value={
                "status": 200, "body": html, "body_sha256": "c" * 64}):
            self.assertEqual(self.client.verify_session_level("low")["security_level"], "low")
        with patch.object(self.client, "get_form", return_value={
                "status": 200, "body": '<form><input name="password"></form>', "body_sha256": "d" * 64}):
            with self.assertRaisesRegex(LocalRuntimeFailure, "session_invalid"):
                self.client.verify_session_level("low")

    def test_invalid_benign_baseline_stops_before_candidate_and_is_not_fn(self):
        scenario = load_catalog()["scenarios"][0]

        class BaselineClient:
            def __init__(self):
                self.values = []

            def verify_session_level(self, level):
                self.asserted_level = level

            def submit_probe(self, scenario, value):
                self.values.append(value)
                return {"status": 200, "body": "mysqli_sql_exception", "elapsed_ms": 2,
                        "body_sha256": "e" * 64}

        client = BaselineClient()
        candidate = {"candidate_id": "c1", "payload": "1'", "source": "manual",
                     "rag_mode": "not_applicable"}
        with self.assertRaisesRegex(LocalRuntimeFailure, "baseline_invalid"):
            execute_candidate(client, io.StringIO(), "r1", scenario, candidate, 1, 1500)
        self.assertEqual(client.values, ["1"])

    def test_time_candidate_uses_matched_no_delay_control(self):
        scenario = load_catalog()["scenarios"][2]

        class TimingClient:
            def __init__(self):
                self.responses = iter((
                    {"status": 200, "body": "User ID exists in the database.", "elapsed_ms": 25,
                     "body_sha256": "a" * 64},
                    {"status": 200, "body": "User ID exists in the database.", "elapsed_ms": 2025,
                     "body_sha256": "b" * 64},
                    {"status": 200, "body": "User ID exists in the database.", "elapsed_ms": 30,
                     "body_sha256": "c" * 64},
                ))

            def verify_session_level(self, level):
                self.asserted_level = level

            def submit_probe(self, scenario, value):
                return next(self.responses)

        output = io.StringIO()
        candidate = {"candidate_id": "time-c1", "payload": "bounded-delay-candidate",
                     "source": "manual", "rag_mode": "not_applicable"}
        detected = execute_candidate(TimingClient(), output, "r-time", scenario,
                                     candidate, 3, 1500, 2, "attempt-retry")
        self.assertTrue(detected)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r["payload_role"] for r in records if r["record_type"] == "payload"],
                         ["baseline", "single", "no_delay_control"])
        decision = next(r for r in records if r["record_type"] == "decision")
        self.assertEqual(decision["replicate"], 3)
        self.assertEqual(decision["confirmation_index"], 2)
        self.assertEqual(decision["attempt_id"], "attempt-retry")
        self.assertEqual(decision["evidence"]["matched_control_time_ms"], 30)
        self.assertEqual(decision["evidence"]["time_delta_ms"], 1995)
        self.assertTrue(decision["system_signal"])

    def test_exception_class_name_alone_is_not_database_diagnostic(self):
        self.assertEqual(sql_error_markers("mysqli_sql_exception database failure"), [])


if __name__ == "__main__":
    unittest.main()
