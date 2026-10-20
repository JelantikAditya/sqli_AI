"""Offline contract tests. These tests never call the HCNSEC endpoint."""

import json
from io import BytesIO
from pathlib import Path
import unittest
from urllib.error import HTTPError

import analysis_v5_pilot_cases as cases
import qwen_api_diagnosis as diagnosis
from qwen_api_analysis import parse, prepare
from qwen_api_client import ChatSettings, QwenAPIClient, redact


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "results/processed/analysis-v5-pilot-20261020-r2"
TEST_KEY = "sk-" + "TESTTOKEN12345678901234567890"


class QwenAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inputs = json.loads((LOCK / "inputs.lock.json").read_text(encoding="utf-8"))
        requests = json.loads((LOCK / "prepared-requests.lock.json").read_text(encoding="utf-8"))
        cls.document = next(row["input"] for row in inputs if row["case_id"] == "pilot-001")
        cls.locked = next(row for row in requests if row["case_id"] == "pilot-001" and row["profile"] == "A")

    def setUp(self):
        self.prepared = prepare(self.document, self.locked, ChatSettings())
        assessments = cases.expected_trials(self.document)
        refs = sorted({ref for row in assessments for ref in row["evidence_refs"]})
        self.output = {"trial_assessments": assessments,
                       "confirmation_summary": {"observed_trials": [1, 2, 3],
                                                "positive_trial_count": 3, "negative_trial_count": 0},
                       "decision": "positive", "reason_code": "new_database_diagnostic",
                       "reason": "Diagnostic baru terukur pada tiga trial.",
                       "evidence_refs": refs, "feedback_action": "none"}

    def result(self):
        return {"status": "ok", "content": json.dumps(self.output), "halt": False}

    def test_adaptation_keeps_locked_evidence_and_schema(self):
        self.assertEqual(self.prepared["schema"], self.locked["request"]["format"])
        self.assertEqual(self.prepared["payload"]["messages"][1], self.locked["request"]["messages"][1])
        self.assertNotIn("trial_assessments", self.prepared["payload"]["messages"][1]["content"])
        self.assertEqual(self.prepared["payload"]["model"], "Qwen3.8-27B")

    def test_accepts_complete_evidence_without_changing_claim(self):
        row = parse(self.document, self.prepared["schema"], self.result())
        self.assertEqual((row["status"], row["decision"]), ("ok", "positive"))

    def test_rejects_fabricated_trial_even_when_json_valid(self):
        self.output["trial_assessments"][1]["trial"] = 4
        row = parse(self.document, self.prepared["schema"], self.result())
        self.assertEqual(row["error"], "trial-set-mismatch")

    def test_rejects_unknown_observation(self):
        self.output["trial_assessments"][0]["evidence_refs"][0] = "obs-999"
        row = parse(self.document, self.prepared["schema"], self.result())
        self.assertEqual(row["error"], "unknown-observation-reference")

    def test_rejects_duplicate_json_key(self):
        result = self.result()
        result["content"] = result["content"].replace('"decision": "positive",',
                                                       '"decision": "negative", "decision": "positive",')
        self.assertEqual(parse(self.document, self.prepared["schema"], result)["error"],
                         "invalid-json-or-schema")

    def test_tally_mismatch_warns_and_preserves_model_verdict(self):
        self.output["confirmation_summary"]["positive_trial_count"] = 2
        row = parse(self.document, self.prepared["schema"], self.result())
        self.assertEqual(row["decision"], "positive")
        self.assertIn("model_confirmation_summary_mismatch", row["warnings"])

    def test_upstream_truncation_is_error(self):
        row = parse(self.document, self.prepared["schema"], {"status": "truncated", "halt": False})
        self.assertEqual(row["error"], "api-truncated")

    def test_invalid_input_is_blocked_before_transport(self):
        invalid = dict(self.document, runtime_status="invalid")
        with self.assertRaises(ValueError):
            prepare(invalid, self.locked, ChatSettings())

    def test_key_redaction_and_payload_guard(self):
        key = TEST_KEY
        self.assertEqual(redact("Bearer " + key, key), "Bearer [REDACTED]")
        client = QwenAPIClient(key)
        with self.assertRaises(ValueError):
            client.chat([{"role": "user", "content": key}])

    def test_second_plan_never_resends_recorded_attempts(self):
        if not (diagnosis.OUT / "plan.json").exists():
            self.skipTest("Local diagnosis checkpoints are intentionally gitignored")
        plan, settings = diagnosis.verified_plan()
        self.assertEqual(settings.max_tokens, 2048)
        self.assertEqual(sum(row["gate"] == "prior_attempted" for row in plan["entries"]), 9)
        self.assertEqual(sum(row["gate"] == "eligible" for row in plan["entries"]), 27)
        self.assertEqual(sum(row["gate"] == "input_invalid" for row in plan["entries"]), 6)
        self.assertFalse(set(plan["previous_results_sha256"]) &
                         {row["case_id"] for row in plan["entries"] if row["gate"] == "eligible"})

    def test_transport_marks_length_stop_as_truncation(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return json.dumps({"model": "self-dploy/Qwen3.8-27B", "id": "test",
                                   "choices": [{"message": {"content": "{}"},
                                                "finish_reason": "length"}]}).encode()

        class Opener:
            def open(self, *_args, **_kwargs):
                return Response()

        result = QwenAPIClient(TEST_KEY, opener=Opener()).chat(
            [{"role": "user", "content": "ping"}])
        self.assertEqual(result["status"], "truncated")

    def test_transport_halts_on_redirect_without_following_it(self):
        class Opener:
            def open(self, request, **_kwargs):
                raise HTTPError(request.full_url, 302, "redirect", None, BytesIO(b"moved"))

        result = QwenAPIClient(TEST_KEY, opener=Opener()).chat(
            [{"role": "user", "content": "ping"}])
        self.assertTrue(result["halt"])
        self.assertEqual(result["http_status"], 302)


if __name__ == "__main__":
    unittest.main()
