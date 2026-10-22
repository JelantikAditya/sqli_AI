"""Verify A/B isolation, candidate controls, and single-attempt execution offline."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_poolside_generation_preflight as runner
from test_poolside_smoke import Opener


SCENARIOS = {row["scenario_id"]: row for row in runner.builder.load_catalog()["scenarios"]}
RETRIEVAL = {"chunks": [{"chunk_id": "test-1", "text": "Generic SQLi technique knowledge."},
                         {"chunk_id": "test-2", "text": "Generic validation knowledge."}]}


def prepared_plan(directory):
    rows = [runner.make_entry(SCENARIOS[sid], condition, RETRIEVAL if condition == "B" else None)
            for sid, condition in runner.ORDER]
    plan = {"profile_id": runner.PROFILE, "max_requests": 6, "source_sha256": {}, "entries": rows}
    path = Path(directory) / "plan.json"
    runner.write_new(path, plan)
    runner.write_new(path.with_name("plan.receipt.json"), {"plan_sha256": runner.digest(path)})
    return path, rows


class GenerationPreflightTests(unittest.TestCase):
    def test_ab_differ_only_in_retrieved_context_and_do_not_leak_labels(self):
        for sid in ("S1", "S2", "S3"):
            a = runner.make_entry(SCENARIOS[sid], "A", None)
            b = runner.make_entry(SCENARIOS[sid], "B", RETRIEVAL)
            av = json.loads(a["payload"]["messages"][1]["content"])
            bv = json.loads(b["payload"]["messages"][1]["content"])
            self.assertEqual(av.pop("retrieved_reference_chunks"), [])
            self.assertEqual(len(bv.pop("retrieved_reference_chunks")), 2)
            self.assertEqual(av, bv)
            self.assertNotIn("ground_truth", av)
            self.assertNotIn("security_level", av)
            self.assertEqual(av["benign_baseline_measurement"], {})

    def test_a_refuses_retrieval_and_b_refuses_missing_chunks(self):
        with self.assertRaises(ValueError):
            runner.make_entry(SCENARIOS["S1"], "A", RETRIEVAL)
        with self.assertRaises(ValueError):
            runner.make_entry(SCENARIOS["S1"], "B", None)

    def test_timing_control_changes_only_literal_delay(self):
        entry = runner.make_entry(SCENARIOS["S3"], "A", None)
        result = runner.validate_output(entry, {"status": "ok", "content": json.dumps({
            "candidates": [{"payload": "1 AND SLEEP(2)"}]})})
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["matched_no_delay_control"], "1 AND SLEEP(0)")
        rejected = runner.validate_output(entry, {"status": "ok", "content": json.dumps({
            "candidates": [{"payload": "1 AND SLEEP(3)"}]})})
        self.assertNotEqual(rejected["status"], "generated")

    def test_provider_failure_is_not_retried_or_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = prepared_plan(directory)
            error = HTTPError(runner.transport.BASE_URL, 500, "Failure", {}, io.BytesIO(b'provider error'))
            opener = Opener(error)
            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.run(path, "test-key", opener)
                self.assertEqual(result["requests_sent"], 1)
                with self.assertRaises(FileExistsError):
                    runner.run(path, "test-key", opener)
            self.assertEqual(len(opener.requests), 1)

    def test_changed_plan_blocks_before_any_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = prepared_plan(directory)
            path.write_text(path.read_text() + "\n")
            opener = Opener()
            with self.assertRaises(ValueError):
                runner.run(path, "test-key", opener)
            self.assertEqual(opener.requests, [])


if __name__ == "__main__":
    unittest.main()
