"""Check that smoke evidence excludes secrets and rejects a broken benign baseline."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from smoke_s1_pair import EvidenceClient, InputForms


class S1SmokeEvidenceTests(unittest.TestCase):
    def response(self, body, status=200):
        return {"status": status, "body": body, "elapsed_ms": 4.0, "body_sha256": "fixture"}

    def test_evidence_retains_fixed_diagnostics_without_adjacent_secrets(self):
        client = EvidenceClient("http://127.0.0.1:4280", 15)
        client.condition = "off"
        baseline = self.response("First name: private-user")
        candidate = self.response(
            "secret-token mysqli_sql_exception: You have an error in your SQL syntax; private-query"
        )
        with patch("validation_loop.DvwaClient.submit_probe", side_effect=[baseline, candidate]):
            client.submit_probe({}, "1")
            client.submit_probe({}, "1")
        self.assertEqual([r["role"] for r in client.receipts], ["baseline", "candidate"])
        self.assertEqual(client.receipts[1]["sql_error_excerpts"], [
            "You have an error in your SQL syntax", "mysqli_sql_exception",
        ])
        for secret in ("secret-token", "private-query", "private-user"):
            self.assertNotIn(secret, str(client.receipts))

    def test_missing_benign_record_stops_before_candidate(self):
        client = EvidenceClient("http://127.0.0.1:4280", 15)
        client.condition = "off"
        with patch("validation_loop.DvwaClient.submit_probe", return_value=self.response("Login")):
            with self.assertRaisesRegex(RuntimeError, "benign baseline"):
                client.submit_probe({}, "1")
        self.assertEqual(client.receipts, [])

    def test_form_inventory_keeps_field_names_without_values(self):
        forms = InputForms()
        forms.feed('<form method="GET" action="#"><input name="id" value="private-value">'
                   '<input name="user_token" value="secret-token"></form>')
        self.assertEqual(forms.forms[0]["fields"], ["id", "user_token"])
        self.assertNotIn("private-value", str(forms.forms))
        self.assertNotIn("secret-token", str(forms.forms))


if __name__ == "__main__":
    unittest.main()
