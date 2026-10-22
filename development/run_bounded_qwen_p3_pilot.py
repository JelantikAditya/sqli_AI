"""Launch the existing P3 pilot with an explicit call ceiling and deadline gate."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

import run_qwen_api_experiments as active
from qwen_api_credentials import get_api_key
from qwen_api_runtime import APIRuntimeFailure, CheckpointedQwenAPI

ROOT = active.ROOT


class DeadlineQwenAPI(CheckpointedQwenAPI):
    def __init__(self, key, directory, config, *, max_seconds, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + max_seconds
        super().__init__(key, directory, config)

    def require_time(self, stage=None):
        # Preserve the frozen request timeout; do not start a request that cannot fit.
        reserve = self.settings[stage].timeout_seconds if stage is not None else 0
        if self.clock() + reserve >= self.deadline:
            raise APIRuntimeFailure("pilot_time_budget_exceeded", {"used_calls": self.used_calls})

    def chat(self, stage, messages, attempt_directory):
        self.require_time(stage)
        return super().chat(stage, messages, attempt_directory)


def prepare(plan_path, budget_path):
    plan_path, budget_path = Path(plan_path).resolve(), Path(budget_path).resolve()
    if not plan_path.is_relative_to(ROOT) or not budget_path.is_relative_to(ROOT):
        raise ValueError("Plan and budget must remain inside this workspace.")
    budget = active.local_runner.read_json(budget_path)
    if (budget.get("schema") != "qwen-p3-pilot-budget-v1"
            or type(budget.get("max_api_calls")) is not int or not 1 <= budget["max_api_calls"] <= 960
            or type(budget.get("max_wall_seconds")) is not int or not 90 <= budget["max_wall_seconds"] <= 21600
            or budget.get("automatic_transport_retries") != 0
            or budget.get("automatic_replacement_attempts") != 0):
        raise ValueError("Invalid bounded P3 pilot budget.")
    config, _ = active.load_config()
    config = copy.deepcopy(config)
    config["limits"]["max_total_api_calls"] = budget["max_api_calls"]
    config_hash = active.sha256_bytes(active.canonical_json(config))
    plan, protocol, plan_hash, protocol_hash = active.validate_api_plan(plan_path, config, config_hash)
    if plan["experiment_id"] != budget["experiment_id"]:
        raise ValueError("Budget is bound to a different experiment.")
    estimate = active.estimate_api_calls(plan, protocol)
    if estimate > budget["max_api_calls"]:
        raise ValueError("The pilot worst-case budget exceeds the explicit API ceiling.")
    if active.local_runner.sha256_file(plan_path) != budget["plan_sha256"]:
        raise ValueError("Pilot plan changed after its budget was frozen.")
    snapshot = active.runtime_snapshot(config_hash)
    if snapshot["source_sha256"] != budget["runtime_source_sha256"]:
        raise ValueError("Pilot sources changed after its budget was frozen.")
    snapshot.update(budget_sha256=active.local_runner.sha256_file(budget_path),
                    bounded_launcher_sha256=active.local_runner.sha256_file(Path(__file__)))
    return budget, config, plan, protocol, plan_hash, protocol_hash, snapshot, estimate


def run(plan_path, budget_path, *, execute=False, confirm_local_dvwa=False,
        confirm_database_reset=False, confirm_api_spending=False):
    budget, config, plan, protocol, ph, prh, snapshot, estimate = prepare(plan_path, budget_path)
    directory = ROOT / "results/raw/pilot" / plan["experiment_id"]
    summary = {"experiment_id": plan["experiment_id"], "protocol_id": active.API_PROTOCOL_ID,
               "worst_case_api_calls": estimate, "api_call_ceiling": budget["max_api_calls"],
               "max_wall_seconds": budget["max_wall_seconds"], "execution_started": False,
               "planned_slots": len(active.local_runner.planned_units(plan, protocol))}
    if not execute:
        return summary
    if not (confirm_local_dvwa and confirm_database_reset and confirm_api_spending):
        raise ValueError("Explicit local DVWA, database reset and API spending flags are required.")
    if directory.exists():
        raise ValueError("This bounded launcher never overwrites or resumes an existing experiment.")
    active.check_pilot_receipt(plan)
    active.require_local_target(protocol["target_origin"])
    key = get_api_key(prompt=False)
    if not key:
        raise ValueError("No API credential is configured; no request sent.")
    ledger = active.local_runner.ExperimentLedger.create(directory, plan, protocol, ph, prh, ROOT)
    active.check_or_write_runtime_snapshot(directory, snapshot, ledger)
    active.local_runner.safe_write_json(directory / "explicit-budget.snapshot.json", budget)
    active.local_runner.safe_write_json(directory / "bounded-config.snapshot.json", config)
    api = DeadlineQwenAPI(key, directory, config, max_seconds=budget["max_wall_seconds"])

    def execute_one(unit, attempt, current_plan, current_protocol, data_dir, root):
        try:
            api.require_time()
        except APIRuntimeFailure as failure:
            raise active.local_runner.ExecutionFailure(failure.code, failure.details) from failure
        print(json.dumps({"event": "unit-start", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "api_calls": api.used_calls}), flush=True)
        details = active.execute_api_unit(unit, attempt, current_plan, current_protocol, data_dir, root, api, config)
        print(json.dumps({"event": "unit-execution-returned", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "api_calls": api.used_calls}), flush=True)
        return details

    with active.local_runner.experiment_lock(directory):
        reserve = active.remaining_call_reserve(ledger, protocol, False)
        if reserve > api.max_total_calls:
            raise ValueError("Remaining run reserve exceeds the explicit pilot budget.")
        result = active.local_runner.execute_ledger(
            ledger, plan, protocol, directory, execute=True, retry_invalid=False, recovered=0,
            root=ROOT, execute_one=execute_one)
    result.update(protocol_id=active.API_PROTOCOL_ID, api_calls_used=api.used_calls,
                  api_call_ceiling=api.max_total_calls, execution_started=True,
                  max_wall_seconds=budget["max_wall_seconds"])
    active.local_runner.safe_write_json(directory / "bounded-execution-result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    parser.add_argument("--confirm-api-spending", action="store_true")
    args = parser.parse_args()
    result = run(args.plan, args.budget, execute=args.execute, confirm_local_dvwa=args.confirm_local_dvwa,
                 confirm_database_reset=args.confirm_database_reset, confirm_api_spending=args.confirm_api_spending)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
