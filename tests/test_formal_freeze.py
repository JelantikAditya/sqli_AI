"""U07 cannot claim readiness with unresolved evidence or exhausted token budgets."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from prepare_formal_freeze import (REQUIRED_GATE_IDS, ROOT, assess_context, read_json,
                                   pilot_completion_gate_passes, ready,
                                   retrieval_index_snapshot_matches,
                                   select_completed_llm_adaptive_artifacts,
                                   validate_formal_corpus_decision)
from experiment_protocol import load_protocol
from execution_order_policy import ordered_run_slots
from run_local_experiments import validate_plan


class FormalFreezeTests(unittest.TestCase):
    def audit(self, **overrides):
        metrics = {"done": True, "done_reason": "stop", "prompt_eval_count": 3057, "eval_count": 247}
        metrics.update(overrides)
        return {"runtime_metrics": metrics, "options": {"num_ctx": 4096, "num_predict": 768}}

    def test_observed_generation_keeps_reserved_output_headroom(self):
        result = assess_context([self.audit()])
        self.assertEqual(result["status"], "passed_for_recorded_calls")
        self.assertEqual(result["minimum_reserved_context_headroom"], 271)

    def test_length_termination_does_not_pass_even_when_json_is_parseable(self):
        self.assertEqual(assess_context([self.audit(done_reason="length")])["status"], "pending")

    def test_input_must_leave_room_for_configured_output_allowance(self):
        self.assertEqual(assess_context([self.audit(prompt_eval_count=3500)])["status"], "pending")

    def test_missing_token_metrics_and_empty_audit_do_not_pass(self):
        for audits in ([], [{}], [self.audit(prompt_eval_count=None)]):
            with self.subTest(audits=audits):
                self.assertEqual(assess_context(audits)["status"], "pending")

    def test_unfinished_or_output_limit_response_does_not_pass(self):
        for audit in (self.audit(done=False), self.audit(eval_count=768)):
            self.assertEqual(assess_context([audit])["status"], "pending")

    def test_one_pending_gate_prevents_formal_readiness(self):
        gates = {key: {"status": "passed"} for key in REQUIRED_GATE_IDS}
        self.assertTrue(ready(gates))
        gates["pilot-all-techniques-and-levels-passed"]["status"] = "pending"
        self.assertFalse(ready(gates))
        self.assertFalse(ready({}))

    def test_incomplete_gate_inventory_cannot_pass(self):
        gates = {key: {"status": "passed"} for key in REQUIRED_GATE_IDS}
        del gates["researcher-corpus-decision-recorded"]
        self.assertFalse(ready(gates))

    def pilot_completion_fixture(self, **overrides):
        pilot = {"run_count": 36, "status_counts": {"completed": 33, "excluded": 3},
                 "scenario_condition_coverage": {"complete": True},
                 "all_applicable_runs_metric_eligible": True, "incomplete_runs": []}
        pilot.update(overrides)
        return pilot

    def test_pilot_completion_requires_exact_schedule_matrix_and_budget(self):
        self.assertTrue(pilot_completion_gate_passes(self.pilot_completion_fixture()))
        incomplete = self.pilot_completion_fixture(incomplete_runs=[{"unit_id": "A-S1"}])
        self.assertFalse(pilot_completion_gate_passes(incomplete))

    def test_pilot_completion_rejects_missing_coverage_invalids_and_wrong_exclusions(self):
        cases = (
            self.pilot_completion_fixture(run_count=35),
            self.pilot_completion_fixture(status_counts={"completed": 32, "invalid": 1, "excluded": 3}),
            self.pilot_completion_fixture(scenario_condition_coverage={"complete": False}),
            self.pilot_completion_fixture(all_applicable_runs_metric_eligible=False),
        )
        for pilot in cases:
            with self.subTest(pilot=pilot):
                self.assertFalse(pilot_completion_gate_passes(pilot))

    def test_retrieval_index_gate_requires_pilot_and_formal_plan_hash_pins(self):
        knowledge = {"formal_use_decision": "approved", "index_file_sha256": {"index.bin": "a" * 64}}
        plan = {"knowledge_snapshot": {"index_file_sha256": {"index.bin": "a" * 64}}}
        pilot = {"retrieval_index_snapshot_pinned": True,
                 "retrieval_index_file_sha256": {"index.bin": "a" * 64}}
        self.assertTrue(retrieval_index_snapshot_matches(pilot, plan, knowledge))
        self.assertFalse(retrieval_index_snapshot_matches({"retrieval_index_snapshot_pinned": False}, plan, knowledge))
        self.assertFalse(retrieval_index_snapshot_matches(
            {**pilot, "retrieval_index_file_sha256": {"index.bin": "b" * 64}}, plan, knowledge))
        self.assertFalse(retrieval_index_snapshot_matches(pilot, {"knowledge_snapshot": {}}, knowledge))
        self.assertFalse(retrieval_index_snapshot_matches(pilot, plan,
                                                          {**knowledge, "index_file_sha256": {"index.bin": "b" * 64}}))

    def test_integration_gate_ignores_invalid_attempt_artifacts(self):
        runs = [
            {"attempt_id": "final-a", "condition_id": "A", "status": "completed"},
            {"attempt_id": "final-b", "condition_id": "B", "status": "completed"},
            {"attempt_id": "invalid-a", "condition_id": "A", "status": "invalid"},
            {"attempt_id": "seclists-c", "condition_id": "C", "status": "completed"},
        ]
        adaptive_documents = [
            {"context": {"attempt_id": "final-a"}},
            {"context": {"attempt_id": "final-b"}},
            {"context": {"attempt_id": "invalid-a"}},
        ]

        expected, selected, nonfinal_count = select_completed_llm_adaptive_artifacts(
            adaptive_documents, runs)

        self.assertEqual(expected, {"final-a", "final-b"})
        self.assertEqual(set(selected), expected)
        self.assertEqual(nonfinal_count, 1)

    def test_formal_draft_contains_99_runs_and_separate_discovery_per_replicate(self):
        plan = read_json(ROOT / "dvwa/local_run_plan.formal-20261017.json")
        slots = list(ordered_run_slots(load_protocol(), scenario_ids=plan["scenario_ids"],
                                      condition_ids=plan["condition_ids"], replicates=plan["replicates"]))
        self.assertEqual(len(slots), 108)
        self.assertEqual(sum(s["applicable"] for s in slots), 99)
        for condition, expected in (("A", 36), ("B", 36), ("C", 27)):
            self.assertEqual(sum(s["applicable"] and s["condition_id"] == condition for s in slots), expected)
        reports = {path for per_replicate in plan["discovery_reports"].values() for path in per_replicate.values()}
        self.assertEqual(len(reports), 12)
        for per_replicate in plan["discovery_reports"].values():
            self.assertEqual(len(set(per_replicate.values())), 3)
        self.assertTrue(all(path.startswith("results/raw/formal-discovery/") for path in reports))

    def test_legacy_formal_draft_without_exact_index_hashes_is_rejected(self):
        plan = read_json(ROOT / "dvwa/local_run_plan.formal-20261017.json")
        with self.assertRaisesRegex(ValueError, "must pin the exact Chroma index file hashes"):
            validate_plan(plan, load_protocol())

    def corpus_decision_fixture(self):
        knowledge = {"corpus_sha256": "a" * 64, "source_lock_sha256": "b" * 64,
                     "knowledge_base_id": "fixture-main-index", "entry_count": 9,
                     "index_file_sha256": {"data/vectorstore/fixture/chroma.sqlite3": "c" * 64}}
        decision = {"schema_version": "1.0.0", "decision": "approved-for-formal-use",
                    "scope": "main-nine-entry-corpus-formal-use-after-u07-gates",
                    "authority": {"role": "researcher", "basis": "explicit-user-approval", "quote": "iya saya setuju"},
                    "approved_snapshot": copy.deepcopy(knowledge), "formal_execution_approval": False}
        return knowledge, decision

    def test_corpus_approval_does_not_waive_incomplete_pilot_budget(self):
        knowledge, decision = self.corpus_decision_fixture()
        self.assertTrue(validate_formal_corpus_decision(decision, knowledge))
        gates = {key: {"status": "passed"} for key in REQUIRED_GATE_IDS}
        gates["pilot-all-techniques-and-levels-passed"]["status"] = "pending"
        self.assertFalse(ready(gates))

    def test_corpus_approval_rejects_changed_content_lock_index_and_entry_count(self):
        knowledge, decision = self.corpus_decision_fixture()
        for key in knowledge:
            with self.subTest(key=key):
                changed = copy.deepcopy(knowledge)
                changed[key] = 10 if key == "entry_count" else {} if key == "index_file_sha256" else "changed"
                with self.assertRaisesRegex(ValueError, "snapshot"):
                    validate_formal_corpus_decision(decision, changed)

    def test_missing_decision_or_unrecorded_authority_cannot_approve_corpus(self):
        knowledge, decision = self.corpus_decision_fixture()
        self.assertFalse(validate_formal_corpus_decision(None, knowledge))
        self.assertFalse(validate_formal_corpus_decision({"decision": "pending"}, knowledge))
        decision["authority"]["basis"] = "assumed-by-assistant"
        with self.assertRaisesRegex(ValueError, "explicit researcher approval"):
            validate_formal_corpus_decision(decision, knowledge)


if __name__ == "__main__":
    unittest.main()
