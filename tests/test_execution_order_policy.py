"""Verify fixed scheduling, ledger order and recovery without live target requests."""

import copy
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from experiment_protocol import experiment_matrix, load_protocol
from run_local_experiments import (execute_plan, planned_units, validate_plan)


class ExecutionOrderPolicyTests(unittest.TestCase):
    def write_plan(self, root, *, scenarios, conditions, replicates):
        reports = {}
        for scenario in scenarios:
            reports[scenario] = {}
            for replicate in replicates:
                report = root / "results/zap" / f"{scenario}-r{replicate}.json"
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text('{"schema_version":"1.0.0","inputs":[]}', encoding="utf-8")
                reports[scenario][str(replicate)] = str(report.relative_to(root)).replace("\\", "/")
        seclists = root / "results/raw/seclists"
        seclists.mkdir(parents=True, exist_ok=True)
        plan = {"schema_version": "1.0.0", "experiment_id": "order-test", "dataset": "pilot",
                "scenario_ids": scenarios, "condition_ids": conditions, "replicates": replicates,
                "discovery_reports": reports, "seclists_source_root": "results/raw/seclists"}
        path = root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path, plan

    def coordinates(self, rows):
        return [(r["replicate"], r["scenario_id"], r["condition_id"]) for r in rows]

    def test_full_matrix_counts_blocks_seeds_and_ab_precedence(self):
        matrix = experiment_matrix(load_protocol())
        self.assertEqual(len(matrix), 99)
        self.assertEqual(Counter(r["condition_id"] for r in matrix), {"A": 36, "B": 36, "C": 27})
        self.assertEqual([r["replicate"] for r in matrix], [1]*33 + [2]*33 + [3]*33)
        self.assertEqual([r["seed"] for r in matrix], [42]*33 + [43]*33 + [44]*33)
        self.assertEqual([r["planned_execution_index"] for r in matrix], list(range(1, 100)))
        self.assertEqual(len(set(self.coordinates(matrix))), 99)
        before = Counter()
        for replicate in (1, 2, 3):
            for scenario in (f"S{i}" for i in range(1, 13)):
                group = [r["condition_id"] for r in matrix if r["replicate"] == replicate and r["scenario_id"] == scenario]
                before["A-first" if group.index("A") < group.index("B") else "B-first"] += 1
        self.assertEqual(before, {"A-first": 18, "B-first": 18})

    def test_every_positive_scenario_balances_all_three_condition_positions(self):
        matrix = experiment_matrix(load_protocol())
        for scenario in (f"S{i}" for i in range(1, 10)):
            for condition in ("A", "B", "C"):
                with self.subTest(scenario=scenario, condition=condition):
                    positions = [r["nominal_condition_position"] for r in matrix
                                 if r["scenario_id"] == scenario and r["condition_id"] == condition]
                    self.assertEqual(sorted(positions), [1, 2, 3])
        expected = {"S1": ["ABC", "BCA", "CAB"], "S2": ["CBA", "ACB", "BAC"],
                    "S10": ["BA", "AB", "BA"], "S11": ["AB", "BA", "AB"]}
        for scenario, orders in expected.items():
            actual = ["".join(r["condition_id"] for r in matrix if r["scenario_id"] == scenario and r["replicate"] == replicate)
                      for replicate in (1, 2, 3)]
            self.assertEqual(actual, orders)

    def test_subset_selector_order_cannot_override_the_canonical_schedule(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            root = Path(temporary)
            _, plan = self.write_plan(root, scenarios=["S12", "S2", "S1"], conditions=["B", "A"], replicates=[3, 1])
            protocol = load_protocol()
            units = planned_units(validate_plan(plan, protocol, root), protocol, root)
            filtered = [r for r in experiment_matrix(protocol) if r["scenario_id"] in plan["scenario_ids"]
                        and r["condition_id"] in plan["condition_ids"] and r["replicate"] in plan["replicates"]]
            self.assertEqual(self.coordinates(units), self.coordinates(filtered))
            self.assertEqual([r["planned_execution_index"] for r in units], list(range(1, 13)))

    def test_full_plan_retains_nine_exclusions_and_matches_matrix_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            root = Path(temporary)
            _, plan = self.write_plan(root, scenarios=[f"S{i}" for i in range(12, 0, -1)],
                                      conditions=["C", "A", "B"], replicates=[3, 2, 1])
            protocol = load_protocol()
            units = planned_units(validate_plan(plan, protocol, root), protocol, root)
            self.assertEqual(len(units), 108)
            self.assertEqual([r["planned_slot_index"] for r in units], list(range(1, 109)))
            excluded = [r for r in units if r["status"] == "excluded"]
            self.assertEqual(len(excluded), 9)
            self.assertTrue(all(r["condition_id"] == "C" and r["planned_execution_index"] is None for r in excluded))
            self.assertEqual(self.coordinates([r for r in units if r["status"] == "planned"]), self.coordinates(experiment_matrix(protocol)))

    def test_mock_execution_and_noop_resume_follow_the_saved_rotated_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            root = Path(temporary)
            path, plan = self.write_plan(root, scenarios=["S10", "S2", "S1"],
                                        conditions=["C", "B", "A"], replicates=[3, 1, 2])
            expected = [r for r in planned_units(validate_plan(plan, load_protocol(), root), load_protocol(), root)
                        if r["status"] == "planned"]
            calls = []
            def fake(unit, attempt, plan, protocol, directory, fake_root):
                calls.append((unit["replicate"], unit["scenario_id"], unit["condition_id"]))
                return {"metric_eligible": True, "candidate_budget": 10, "valid_candidates_executed": 10,
                        "database_reset_performed": True}
            result = execute_plan(path, execute=True, confirm_local_dvwa=True, confirm_database_reset=True,
                                  root=root, execute_one=fake)
            self.assertEqual(calls, self.coordinates(expected))
            self.assertEqual(result["status_counts"]["completed"], 24)
            ledger_path = root / "results/raw/pilot/order-test/ledger.jsonl"
            before = ledger_path.read_bytes()
            resumed = execute_plan(path, resume=True, execute=True, confirm_local_dvwa=True,
                                   confirm_database_reset=True, root=root, execute_one=fake)
            self.assertEqual(len(calls), 24)
            self.assertEqual(ledger_path.read_bytes(), before)
            self.assertEqual(resumed["status_counts"]["completed"], 24)
            schema = json.loads((ROOT / "schemas/experiment-ledger-event.schema.json").read_text())
            validator = Draft202012Validator(schema)
            for line in before.decode().splitlines():
                validator.validate(json.loads(line))

    def test_partial_resume_skips_completed_and_continues_same_next_unit(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            root = Path(temporary)
            path, plan = self.write_plan(root, scenarios=["S2"], conditions=["A", "B", "C"], replicates=[2])
            calls = []
            def interrupted(unit, attempt, plan, protocol, directory, fake_root):
                calls.append(unit["condition_id"])
                if unit["condition_id"] == "C":
                    raise KeyboardInterrupt()
                return {"metric_eligible": True}
            with self.assertRaises(KeyboardInterrupt):
                execute_plan(path, execute=True, confirm_local_dvwa=True, confirm_database_reset=True,
                             root=root, execute_one=interrupted)
            self.assertEqual(calls, ["A", "C"])
            resumed = []
            def recovered(unit, attempt, plan, protocol, directory, fake_root):
                resumed.append((unit["condition_id"], attempt["attempt_number"]))
                return {"metric_eligible": True, "database_reset_performed": True}
            result = execute_plan(path, resume=True, retry_invalid=True, execute=True,
                                  confirm_local_dvwa=True, confirm_database_reset=True, root=root, execute_one=recovered)
            self.assertEqual(resumed, [("C", 2), ("B", 1)])
            self.assertEqual(result["status_counts"]["completed"], 3)

    def test_resume_rejects_changed_planned_order_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            root = Path(temporary)
            path, _ = self.write_plan(root, scenarios=["S1"], conditions=["A", "B"], replicates=[1])
            execute_plan(path, root=root)
            ledger_path = root / "results/raw/pilot/order-test/ledger.jsonl"
            events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
            events[1]["planned_slot_index"] = 99
            ledger_path.write_text("".join(json.dumps(e)+"\n" for e in events), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "planned order differs"):
                execute_plan(path, resume=True, root=root)

    def test_protocol_rejects_posthoc_condition_scenario_and_resume_order_changes(self):
        changes = ("conditions", "scenarios", "subset", "resume")
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
                protocol = copy.deepcopy(load_protocol())
                if change == "conditions":
                    protocol["execution_order"]["odd_scenario_orders"]["1"] = ["B", "A", "C"]
                elif change == "scenarios":
                    protocol["execution_order"]["scenario_order"].reverse()
                else:
                    protocol["execution_order"]["subset_order" if change == "subset" else "resume_order"] = "shuffle"
                path = Path(temporary) / "protocol.json"
                path.write_text(json.dumps(protocol), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "mirrored condition rotation"):
                    load_protocol(path)


if __name__ == "__main__":
    unittest.main()
