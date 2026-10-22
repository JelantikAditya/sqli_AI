"""Offline integration regressions for P3 gates and the exact P2 wire profile."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
sys.path.insert(0, str(ROOT / "development"))

import adaptive_s1_loop
import analysis_v5_pilot_cases as fixtures
import analyze_response
import qwen_api_p2_analysis as p2
import run_qwen_api_experiments as runner
from qwen_api_client import encoded_payload, request_payload
from qwen_api_runtime import APIRuntimeFailure, CheckpointedQwenAPI


def context_for(document, condition="A"):
    scenario = {"error-based": "S1", "boolean-based blind": "S2",
                "time-based blind": "S3"}[document["technique"]]
    return {"experiment_id": "p3-gate-tests", "run_id": "run-1", "attempt_id": "attempt-1",
            "candidate_id": "candidate-001", "scenario_id": scenario, "replicate": 1,
            "condition_id": condition, "source": "LLM", "rag_mode": "off" if condition == "A" else "on"}


def positive_output(document):
    roles = {"error-based": {"baseline", "candidate"},
             "boolean-based blind": {"true_condition", "false_condition"},
             "time-based blind": {"candidate", "no_delay_control"}}[document["technique"]]
    trials = sorted({row["trial"] for row in document["observations"]})
    assessments = [{"trial": trial, "outcome": "positive", "evidence_refs": [
        row["observation_id"] for row in document["observations"]
        if row["trial"] == trial and row["role"] in roles]} for trial in trials]
    code = {"error-based": "new_database_diagnostic", "boolean-based blind": "boolean_difference",
            "time-based blind": "matched_delay"}[document["technique"]]
    return {"trial_assessments": assessments,
            "confirmation_summary": {"observed_trials": trials, "positive_trial_count": len(trials),
                                     "negative_trial_count": 0},
            "decision": "positive", "reason_code": code,
            "reason": "Offline model claim; its semantic accuracy must remain measurable.",
            "evidence_refs": [ref for trial in assessments for ref in trial["evidence_refs"]],
            "feedback_action": "none"}


class FakeAPI:
    def __init__(self, output):
        self.content = output if isinstance(output, str) else json.dumps(output)
        self.calls = 0
        self.messages = None

    def chat(self, stage, messages, directory):
        assert stage == "analysis"
        self.calls += 1
        self.messages = messages
        payload = request_payload(messages, p2.default_settings())
        return {"status": "ok", "content": self.content, "finish_reason": "stop",
                "reported_model": "self-dploy/Qwen3.8-27B", "elapsed_seconds": 999999}, {
                    "request_sha256": hashlib.sha256(encoded_payload(payload)).hexdigest()}


class P3AnalysisGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows, _ = fixtures.build_cases()
        cls.documents = {row["case_id"]: row["input"] for row in rows}

    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("Offline P3 test attempted networking"))
            guard.start()
            self.addCleanup(guard.stop)

    def analyze(self, document, output, condition="A"):
        api = FakeAPI(output)
        ctx = context_for(document, condition)
        result = runner.make_analysis_callback(api, Path("unused-offline-directory"), ctx)(document, ctx)
        return api, result

    def test_all_six_invalid_inputs_stop_before_rendering_or_api(self):
        for name, document in self.documents.items():
            if fixtures.eligible(document):
                continue
            with self.subTest(case=name), patch.object(p2, "prepare", side_effect=AssertionError("Rendered invalid input")):
                api, result = self.analyze(document, {})
                self.assertEqual(api.calls, 0)
                self.assertEqual(result["analysis_status"], "runtime_invalid")
                self.assertIsNone(result["system_claim"])
                self.assertIsNone(result["model_output"])
                self.assertFalse(result["audit"]["provenance"]["api_call_performed"])
                summary = analyze_response.summarize_run([result], 1)
                self.assertFalse(summary["binary_decision_eligible"])

    def test_invalid_coordinates_stop_before_api(self):
        document = copy.deepcopy(self.documents["pilot-001"])
        api = FakeAPI({})
        ctx = context_for(document)
        ctx["scenario_id"] = "S4"  # Medium requires POST, whereas this evidence is GET.
        with self.assertRaises(ValueError):
            runner.make_analysis_callback(api, Path("unused"), ctx)(document, ctx)
        self.assertEqual(api.calls, 0)

    def test_transport_failure_propagates_without_manufacturing_a_model_claim(self):
        document = self.documents["pilot-001"]
        api = FakeAPI({})
        api.chat = lambda *_args: (_ for _ in ()).throw(APIRuntimeFailure("api_http_error"))
        ctx = context_for(document)
        with self.assertRaises(APIRuntimeFailure) as raised:
            runner.make_analysis_callback(api, Path("unused"), ctx)(document, ctx)
        self.assertEqual(raised.exception.code, "api_http_error")

    def test_structural_rejections_are_not_valid_binary_claims(self):
        for case in ("pilot-001", "pilot-013", "pilot-025"):
            document = self.documents[case]
            for mutation, expected_error in (
                    ("fabricated_trial", "trial-set-mismatch"),
                    ("cross_trial", "missing-trial-evidence"),
                    ("unknown_reference", "unknown-observation-reference"),
                    ("missing_top_reference", "missing-top-level-evidence")):
                with self.subTest(case=case, mutation=mutation):
                    output = positive_output(document)
                    if mutation == "fabricated_trial":
                        output["trial_assessments"][1]["trial"] = 4
                    elif mutation == "cross_trial":
                        output["trial_assessments"][0]["evidence_refs"] = output["trial_assessments"][1]["evidence_refs"]
                    elif mutation == "unknown_reference":
                        output["evidence_refs"].append("obs-999")
                    else:
                        output["evidence_refs"] = output["evidence_refs"][1:]
                    api, result = self.analyze(document, output)
                    self.assertEqual(api.calls, 1)
                    self.assertEqual(result["analysis_status"], "analysis_error")
                    self.assertIsNone(result["system_claim"])
                    self.assertIsNone(result["model_output"])
                    provenance = result["audit"]["provenance"]
                    self.assertEqual(provenance["analysis_parser_error"], expected_error)
                    self.assertEqual(provenance["rejected_model_output"], output)
                    self.assertEqual(json.loads(provenance["rejected_raw_response"]), output)
                    summary = analyze_response.summarize_run([result], 1)
                    self.assertEqual(summary["analysis_completed_count"], 0)
                    self.assertEqual(summary["system_positive_count"], 0)
                    self.assertFalse(summary["binary_decision_eligible"])

    def test_invalid_json_preserves_raw_response_without_valid_claim(self):
        api, result = self.analyze(self.documents["pilot-001"], "not JSON")
        self.assertEqual(api.calls, 1)
        self.assertEqual(result["analysis_status"], "analysis_error")
        self.assertEqual(result["audit"]["provenance"]["rejected_raw_response"], "not JSON")
        self.assertIsNone(result["system_claim"])

    def test_semantically_wrong_positive_is_preserved_for_evaluation(self):
        document = self.documents["pilot-005"]  # HTTP 500 without any SQL diagnostic.
        _, result = self.analyze(document, positive_output(document))
        self.assertEqual(result["analysis_status"], "completed")
        self.assertEqual(result["system_claim"], "positive")
        self.assertFalse(result["confirmed_success"])
        self.assertIn("model_claim_evidence_mismatch", result["analysis_warnings"])

    def test_semantic_tally_warning_does_not_override_model_verdict(self):
        document = self.documents["pilot-001"]
        output = positive_output(document)
        output["confirmation_summary"]["positive_trial_count"] = 0
        output["confirmation_summary"]["negative_trial_count"] = 3
        _, result = self.analyze(document, output)
        self.assertEqual(result["analysis_status"], "completed")
        self.assertEqual(result["system_claim"], "positive")
        self.assertIn("model_confirmation_summary_mismatch", result["audit"]["provenance"]["model_summary_warnings"])

    def test_all_36_eligible_cases_use_exact_p2_messages_on_a_and_b(self):
        count = 0
        for name, document in self.documents.items():
            if not fixtures.eligible(document):
                continue
            for condition in ("A", "B"):
                with self.subTest(case=name, condition=condition):
                    api, result = self.analyze(document, positive_output(document))
                    self.assertEqual(api.messages, p2.prepare(document)["payload"]["messages"])
                    self.assertEqual(result["evidence"], document)
            count += 1
        self.assertEqual(count, 36)

    def test_parser_rejection_stops_adaptive_loop_without_followup_generation(self):
        document = self.documents["pilot-001"]
        output = positive_output(document)
        output["trial_assessments"][1]["trial"] = 4
        api = FakeAPI(output)
        ctx = context_for(document)
        result = adaptive_s1_loop.run_loop(
            ctx, lambda previous, attempted: ("1'", {"status": "generated"}),
            lambda candidate, confirmations: copy.deepcopy(document),
            runner.make_analysis_callback(api, Path("unused"), ctx),
            budget=2, slot_limit=2, confirmations=3, database_reset_performed=True)
        self.assertEqual(result["stop_reason"], "analysis_error")
        self.assertEqual(len(result["candidate_records"]), 1)
        self.assertEqual(api.calls, 1)
        self.assertFalse(result["run_summary"]["binary_decision_eligible"])

    def test_actual_checkpoint_wire_payload_matches_p2_and_generation_keeps_its_profile(self):
        config, _ = runner.load_config()
        document = self.documents["pilot-001"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            api = CheckpointedQwenAPI("offline-dummy-secret", root, config)
            transport = FakeAPI(positive_output(document))
            transport.chat = lambda messages: {"status": "ok", "content": transport.content,
                                                "reported_model": "self-dploy/Qwen3.8-27B", "finish_reason": "stop"}
            api.client["analysis"] = transport
            ctx = context_for(document)
            result = runner.make_analysis_callback(api, root / "attempts/unit/attempt-1", ctx)(document, ctx)
            request_file, = root.rglob("request.json")
            checkpoint = json.loads(request_file.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["payload"], p2.prepare(document)["payload"])
            self.assertEqual(api.settings["analysis"], p2.default_settings())
            self.assertIsNone(api.settings["analysis"].chat_template_kwargs)
            self.assertEqual(api.settings["generation"].chat_template_kwargs, {"enable_thinking": False})
            self.assertEqual(result["analysis_status"], "completed")

    def test_analysis_profile_drift_is_rejected_before_transport(self):
        config, _ = runner.load_config()
        with tempfile.TemporaryDirectory() as directory:
            for field, value in (("analysis", 1024), ("timeout_seconds", 60), ("temperature", 0.5)):
                with self.subTest(field=field):
                    changed = copy.deepcopy(config)
                    if field == "analysis":
                        changed["token_limits"][field] = value
                    else:
                        changed[field] = value
                    with self.assertRaisesRegex(ValueError, "frozen P2 profile"):
                        CheckpointedQwenAPI("offline-dummy-secret", Path(directory), changed)

    def test_checkpoint_hash_mismatch_halts_instead_of_accepting_other_profile(self):
        document = self.documents["pilot-001"]
        api = FakeAPI(positive_output(document))
        chat = api.chat
        def altered(*args):
            response, checkpoint = chat(*args)
            return response, {**checkpoint, "request_sha256": "0" * 64}
        api.chat = altered
        ctx = context_for(document)
        with self.assertRaises(APIRuntimeFailure) as raised:
            runner.make_analysis_callback(api, Path("unused"), ctx)(document, ctx)
        self.assertEqual(raised.exception.code, "api_analysis_profile_mismatch")

    def test_new_protocol_snapshot_refuses_old_attempt_resume(self):
        config, digest = runner.load_config()
        new_snapshot = runner.runtime_snapshot(digest)
        self.assertEqual(new_snapshot["protocol_id"], runner.API_PROTOCOL_ID)
        self.assertIn("development/qwen_api_p2_analysis.py", new_snapshot["source_sha256"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            old_snapshot = {**new_snapshot, "protocol_id": "qwen38-api-sqli-v1-pilot"}
            runner.api_snapshot_path(path).write_text(json.dumps(old_snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Resume is refused"):
                runner.check_or_write_runtime_snapshot(path, new_snapshot, type("Ledger", (), {"events": []})())


if __name__ == "__main__":
    unittest.main()
