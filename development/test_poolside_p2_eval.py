"""Offline checks of the new provider packet and P2 failure isolation."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_poolside_p2_eval as runner
from test_poolside_smoke import Opener


class PoolsideP2Tests(unittest.TestCase):
    def test_new_profile_keeps_every_original_message_and_evidence_document(self):
        plan = runner.build_plan()
        originals, _ = runner.load_requests(runner.DEFAULT_REQUESTS)
        self.assertEqual(len(plan["entries"]), 18)
        for row, original in zip(plan["entries"], originals):
            self.assertEqual(row["document"], original["document"])
            self.assertEqual(row["prepared"]["payload"]["messages"], original["prepared"]["payload"]["messages"])

    def test_provider_error_stops_without_retry_or_next_case(self):
        plan = runner.build_plan()
        plan["source_sha256"] = {}
        error = HTTPError(runner.transport.BASE_URL, 503, "Unavailable", {}, io.BytesIO(b'test-secret'))
        opener = Opener(error)
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "ROOT", Path(directory)), \
                contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(plan, "test-secret", opener)
            self.assertEqual(result["state"], "halted")
            self.assertEqual(len(opener.requests), 1)
            saved = Path(result["output_dir"]) / "evaluation-results.json"
            self.assertNotIn("test-secret", saved.read_text())

    def test_schema_rejection_is_unscored_and_does_not_become_a_verdict(self):
        plan = runner.build_plan()
        plan["source_sha256"] = {}
        wire = {"model": runner.transport.MODEL,
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        opener = Opener(*[wire for _ in range(18)])
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "ROOT", Path(directory)), \
                contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(plan, "test-secret", opener)
            saved = json.loads((Path(result["output_dir"]) / "evaluation-results.json").read_text())
            self.assertEqual(len(opener.requests), 18)
            self.assertTrue(all(row["analysis_status"] == "rejected" for row in saved["cases"]))
            self.assertTrue(all(row["analysis"]["decision"] is None for row in saved["cases"]))


if __name__ == "__main__":
    unittest.main()
