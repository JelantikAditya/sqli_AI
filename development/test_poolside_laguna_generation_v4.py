from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import poolside_laguna_generation_v4 as generation
import run_qwen_api_experiments as active
from poolside_completion_budget import CompletionBudgetPoolsideAPI
from qwen_api_runtime import APIRuntimeFailure


class FakeAPI:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def chat(self, stage, messages, attempt_directory):
        self.messages.append(messages)
        return ({"status": "ok", "content": next(self.responses)},
                {"request_sha256": f"request-{len(self.messages)}", "stage": stage})


class FamilySchedulerTests(unittest.TestCase):
    def test_each_probe_has_40_unique_safe_family_references(self):
        scenario_ids = {"single_error": "S1", "boolean_pair": "S2", "single_time": "S3"}
        for probe_kind, scenario_id in scenario_ids.items():
            bank = generation.FAMILIES[probe_kind]
            self.assertEqual(len(bank), generation.MAX_FAMILIES_PER_PROBE)
            self.assertEqual(len({item.structural_key for item in bank}), len(bank))
            for family in bank:
                candidate = generation._candidate(probe_kind, family.reference_values)
                active.validate_candidate_policy(candidate, probe_kind, scenario_id)

    def test_fallback_uses_an_unrequested_family_and_unoccupied_key(self):
        probe_kind = "single_error"
        accepted = [generation.FAMILIES[probe_kind][0].reference_values[0]]
        requested = {generation.FAMILIES[probe_kind][0].family_id}

        selected = generation.select_family(probe_kind, 1, accepted, requested)

        self.assertNotIn(selected.family_id, requested)
        self.assertNotIn(selected.structural_key, {
            generation.parser.structural_key({"payload": value}, probe_kind)
            for value in accepted
        })

    def test_all_scheduled_families_remain_distinct_for_worst_case_unit(self):
        for probe_kind, bank in generation.FAMILIES.items():
            requested = set()
            accepted = []
            for slot in range(1, 11):
                for _ in range(generation.MAX_RETRIES_PER_SLOT + 1):
                    selected = generation.select_family(probe_kind, slot, accepted, requested)
                    self.assertNotIn(selected.family_id, requested)
                    self.assertNotIn(selected.structural_key, {
                        generation.parser.structural_key(generation._candidate(
                            probe_kind, (value,) if isinstance(value, str)
                            else tuple(generation.parser.candidate_values(value, probe_kind))), probe_kind)
                        for value in accepted
                    })
                    requested.add(selected.family_id)
                accepted.append(generation._candidate(probe_kind, bank[slot - 1].reference_values))
            self.assertEqual(len(requested), 30)

    def test_invalid_json_retry_changes_family_and_never_sends_reference_value(self):
        scenario = {
            "scenario_id": "S1", "probe_kind": "single_error", "sqli_type": "error-based",
            "method": "GET", "input_path": "/vulnerabilities/sqli/",
            "result_path": "/vulnerabilities/sqli/", "parameter": "id",
        }
        candidate_json = json.dumps({"candidates": [{"payload": "2\""}]})
        api = FakeAPI(['{"candidates":[', candidate_json])
        callback = generation.make_generation_callback(
            api, ROOT / "unused", scenario, None, {"http_status": 200},
            {"limits": {"max_retrieved_chars_per_chunk": 1800}},
        )

        candidate, first = callback(None, [], 0, None)
        self.assertIsNone(candidate)
        candidate, second = callback(None, [], 1, first["status"])

        self.assertEqual(candidate, "2\"")
        self.assertNotEqual(first["family_id"], second["family_id"])
        self.assertEqual(first["status"], "invalid_candidate_format")
        self.assertEqual(second["status"], "generated")
        self.assertNotEqual(first["family_structural_key"], second["family_structural_key"])
        prompt = json.dumps(api.messages, ensure_ascii=False)
        self.assertNotIn("reference_values", prompt)
        self.assertNotIn('"payload":"1\'"', prompt)

    def test_q2_retrieval_projection_is_retained_without_mutating_source(self):
        source = {"chunks": [{"chunk_id": "q2", "text": json.dumps({
            "title": "Boolean logic", "detection_method": "Matched pair",
            "payload_examples": [{"value": "sample"}],
        })}]}
        projected, removed = generation.strip_payload_examples(source)
        self.assertEqual(removed, 1)
        self.assertIn("payload_examples", json.loads(source["chunks"][0]["text"]))
        self.assertNotIn("payload_examples", json.loads(projected["chunks"][0]["text"]))


class CompletionBudgetTests(unittest.TestCase):
    def test_existing_unsent_and_completed_checkpoints_restore_conservative_tokens(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "attempts" / "unit" / "attempt-1"
            started = root / "api-calls" / "call-1"
            started.mkdir(parents=True)
            (started / "request-started.json").write_text("{}", encoding="utf-8")
            (started / "request.json").write_text(json.dumps({"stage": "generation", "payload": {"max_tokens": 1024}}), encoding="utf-8")
            complete = root / "api-calls" / "call-2"
            complete.mkdir(parents=True)
            (complete / "request-started.json").write_text("{}", encoding="utf-8")
            (complete / "request.json").write_text(json.dumps({"stage": "analysis", "payload": {"max_tokens": 2048}}), encoding="utf-8")
            (complete / "result.json").write_text(json.dumps({"result": {"usage": {"completion_tokens": 17}}}), encoding="utf-8")

            api = CompletionBudgetPoolsideAPI("offline-test", Path(directory), max_calls=3,
                                              max_seconds=300, opener=object(), clock=lambda: 0)

        self.assertEqual(api.completion_tokens_reserved, 1024 + 17)

    def test_request_reservation_is_rejected_before_any_api_call(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            api = CompletionBudgetPoolsideAPI("offline-test", Path(directory), max_calls=3,
                                              max_seconds=300, opener=object(), clock=lambda: 0,
                                              max_completion_tokens=100)
            with self.assertRaises(APIRuntimeFailure):
                api.chat("analysis", [{"role": "user", "content": "fixture"}],
                         Path(directory) / "attempts" / "unit" / "attempt-1")
            self.assertEqual(list((Path(directory) / "attempts").rglob("request-started.json"))
                             if (Path(directory) / "attempts").exists() else [], [])


if __name__ == "__main__":
    unittest.main()
