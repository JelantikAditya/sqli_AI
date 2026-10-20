"""Audit tampering regressions using an isolated simulated session, never a model."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import audit_analysis_v5_pilot_rev2 as audit_tool
import test_analysis_v5_pilot_rev2 as simulated

pilot = audit_tool.pilot


class AuditChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        simulated.RevisionTests.setUpClass()
        cls.fixture = simulated.RevisionTests()
        cls.cases = cls.fixture.cases
        cls.labels = cls.fixture.labels
        cls.requests = cls.fixture.requests
        cls.audit_rows = cls.fixture.audit
        cls.events = []
        pilot.run_slots(cls.cases, cls.fixture.schedule, cls.requests, cls.audit_rows,
                        cls.fixture.response, cls.events.append)

    def run_fixture(self, events, mutate_summary=None):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            raw = Path(directory)
            data = "".join(json.dumps(e) + "\n" for e in events)
            (raw / "events.jsonl").write_text(data, encoding="utf-8", newline="\n")
            summary = pilot.summarize(self.cases, self.labels, self.fixture.schedule, events)
            summary.update(session_status="completed", events_sha256=pilot.digest(raw / "events.jsonl"))
            if mutate_summary:
                mutate_summary(summary)
            (raw / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with patch.object(pilot, "RAW", raw), patch.object(pilot, "verify", return_value=(
                    self.cases, self.labels, self.requests, self.audit_rows)):
                return audit_tool.audit()

    def test_complete_simulation_reproduces_and_retains_invalid_skips(self):
        _, result, rows, techniques = self.run_fixture(copy.deepcopy(self.events))
        self.assertEqual(result["parses_reproduced_from_raw_responses"], 108)
        self.assertEqual(result["skipped_invalid_slots"], 18)
        self.assertEqual(len(rows), 126)
        self.assertEqual(techniques["A"]["error-based"]["attempted"], 12)

    def test_raw_response_tamper_detected_even_with_matching_event_hash_and_summary(self):
        events = copy.deepcopy(self.events)
        response = next(e for e in events if e["event"] == "response_received")
        response["response"]["done"] = False
        # Ringkasan dan hash diperbarui, tetapi record hasil tetap tidak cocok
        # dengan respons mentah yang dimodifikasi. Audit harus mendeteksinya.
        with self.assertRaisesRegex(ValueError, "does not reproduce from raw model response"):
            self.run_fixture(events)

    def test_summary_tamper_rejected_without_changing_raw_responses(self):
        def tamper(summary):
            summary["profiles"]["A"]["raw_correct"] -= 1
        with self.assertRaisesRegex(ValueError, "summary does not reproduce"):
            self.run_fixture(copy.deepcopy(self.events), tamper)


if __name__ == "__main__":
    unittest.main()
