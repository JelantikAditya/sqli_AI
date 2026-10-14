"""Offline artifact aggregation distinguishes generation exhaustion from runtime failure."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from adaptive_s1_loop import run_loop
from analyze_response import normalize_analysis
from experiment_protocol import load_protocol
from rag_pipeline import load_catalog
from run_local_experiments import ExecutionFailure, execute_adaptive_s1_unit, sha256_file


class AdaptiveArtifactTests(unittest.TestCase):
    def aggregate(self, status):
        scenario = load_catalog()["scenarios"][0]
        context = {"experiment_id": "test-adaptive", "run_id": "run1", "attempt_id": "attempt1",
                   "scenario_id": "S1", "replicate": 1, "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        def observe(payload, confirmations):
            observations = []
            for trial in (1, 2, 3):
                for role in ("baseline", "candidate"):
                    observations.append({"observation_id": f"obs-{len(observations)+1:03d}",
                                         "trial": trial, "role": role, "http_status": 200, "elapsed_ms": 5,
                                         "response_sha256": "a" * 64, "diagnostics": [],
                                         "content_markers": ["benign_record"] if role == "baseline" else []})
            return {"schema_version": "1.0.0", "technique": "error-based", "runtime_status": "valid",
                    "baseline_valid": True, "time_threshold_ms": 1500, "observations": observations,
                    "injection_point": {key: scenario[key] for key in ("method", "input_path", "result_path", "parameter")}}
        def analyze(evidence, ctx):
            return normalize_analysis(evidence, {"decision": "negative", "reason_code": "no_new_database_diagnostic",
                                      "reason": "No diagnostic observed.", "evidence_refs": ["obs-001", "obs-002"],
                                      "feedback_action": "revise_candidate"}, ctx)
        generated = "1'" if status == "generated" else None
        artifact = run_loop(context, lambda previous, attempted: (generated, {"status": status}),
                            observe, analyze, budget=10, slot_limit=10)
        artifact["runtime"] = {"http_request_attempt_count": 23, "database_reset": {"success_markers_verified": True},
                               "retrieval": None}
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            directory = Path(temporary)
            report = directory / "report.json"
            report.write_text('{}', encoding="utf-8")
            path = directory / "adaptive.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            unit = {"scenario_id": "S1", "condition_id": "A", "replicate": 1, "seed": 42,
                    "source": "LLM", "rag_mode": "off", "discovery_report": str(report),
                    "discovery_sha256": sha256_file(report)}
            with patch("run_local_experiments.run_command") as command:
                details = execute_adaptive_s1_unit(unit, context, {"experiment_id": "test-adaptive"},
                                                   load_protocol(), directory, ROOT, adaptive_result_path=path)
                command.assert_not_called()
            records = ([json.loads(line) for line in (directory / "validation.jsonl").read_text().splitlines()]
                       if (directory / "validation.jsonl").exists() else [])
            return details, records

    def test_duplicate_exhaustion_retains_valid_evidence_and_excludes_incomplete_run(self):
        details, records = self.aggregate("generated")
        self.assertFalse(details["metric_eligible"])
        self.assertFalse(details["budget_complete"])
        self.assertEqual(details["valid_candidates_executed"], 1)
        self.assertEqual(details["candidate_generation_failed_count"], 9)
        self.assertEqual(details["decision_records"], 3)
        self.assertEqual(details["payload_records"], 6)
        self.assertEqual(details["system_decision"], "not_evaluable")
        self.assertEqual(records[-1]["attempt_status"], "incomplete")

    def test_zero_schema_valid_candidates_are_excluded_without_probe_data(self):
        details, records = self.aggregate("invalid_candidate")
        self.assertFalse(details["metric_eligible"])
        self.assertEqual(details["valid_candidates_executed"], 0)
        self.assertEqual(details["candidate_generation_failed_count"], 10)
        self.assertEqual(records, [])

    def test_local_model_service_failure_still_requires_runtime_recovery(self):
        with self.assertRaisesRegex(ExecutionFailure, "local_model_service_unavailable"):
            self.aggregate("model_service_error")


if __name__ == "__main__":
    unittest.main()
