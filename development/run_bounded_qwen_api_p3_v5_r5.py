"""Prepare or launch a fresh bounded P3 v5 cohort with duplicate-aware retries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import run_qwen_api_experiments as active
from qwen_api_credentials import get_api_key
from qwen_api_runtime import APIRuntimeFailure
from qwen_api_runtime_p3_timeout180 import Timeout180CheckpointedQwenAPI
import qwen_api_p3_v5_generation as retry_generation


ROOT = active.ROOT
PROTOCOL_ID = "qwen38-api-sqli-v5-pilot"
EXPERIMENT_ID = "qwen38-api-r5-20261022"
PROFILE_PATH = ROOT / "development/qwen_api_p3_v5_retry_profile_r5.json"
BASE_CONFIG_PATH = ROOT / "development/qwen_api_runtime_config.json"
ORIGINAL_API_PROTOCOL = active.api_protocol


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(active.canonical_json(value)).hexdigest()


def runtime_source_hashes() -> dict[str, str]:
    hashes = active.runtime_source_hashes(ROOT)
    for name in (
        "development/qwen_api_runtime_p3_timeout180.py",
        "development/qwen_api_p3_timeout180_profile.json",
        "development/qwen_api_p3_v5_generation.py",
        "development/run_bounded_qwen_api_p3_v5_r5.py",
        "development/qwen_api_p3_v5_retry_profile_r5.json",
    ):
        hashes[name] = digest(ROOT / name)
    return dict(sorted(hashes.items()))


def configure_protocol(profile: dict, profile_sha256: str) -> None:
    active.API_PROTOCOL_ID = PROTOCOL_ID
    active.make_generation_callback = retry_generation.make_generation_callback

    retry_helper_sha256 = digest(ROOT / "development/qwen_api_p3_v5_generation.py")

    def api_protocol_v5(base_protocol: dict, config: dict, config_hash: str) -> dict:
        protocol = ORIGINAL_API_PROTOCOL(base_protocol, config, config_hash)
        protocol["protocol_id"] = PROTOCOL_ID
        protocol["methodology"]["api_timeout_profile_id"] = profile["analysis_profile_id"]
        protocol["methodology"]["api_timeout_profile_sha256"] = profile["analysis_profile_sha256"]
        protocol["methodology"]["api_transport_timeouts_seconds"] = profile["transport_timeouts_seconds"]
        protocol["methodology"]["generation_retry_policy_id"] = retry_generation.RETRY_POLICY_ID
        protocol["methodology"]["generation_retry_policy_sha256"] = retry_helper_sha256
        protocol["methodology"]["generation_retry_profile_id"] = profile["profile_id"]
        protocol["methodology"]["generation_retry_profile_sha256"] = profile_sha256
        return protocol

    active.api_protocol = api_protocol_v5


def prepare(plan_path: Path, budget_path: Path) -> tuple:
    plan_path, budget_path = Path(plan_path).resolve(), Path(budget_path).resolve()
    if not plan_path.is_relative_to(ROOT) or not budget_path.is_relative_to(ROOT):
        raise ValueError("Plan and budget must remain inside this workspace.")
    if digest(BASE_CONFIG_PATH) != "5a098538060d5f9bb6522e23dd0add037295a9e0eaed34e0a978880317068016":
        raise ValueError("The frozen base runtime configuration changed after timeout-profile preparation.")

    budget = read_json(budget_path)
    if (budget.get("schema") != "qwen-p3-pilot-budget-v1"
            or budget.get("experiment_id") != EXPERIMENT_ID
            or type(budget.get("max_api_calls")) is not int or not 1 <= budget["max_api_calls"] <= 960
            or type(budget.get("max_wall_seconds")) is not int or not 90 <= budget["max_wall_seconds"] <= 21600
            or budget.get("automatic_transport_retries") != 0
            or budget.get("automatic_replacement_attempts") != 0
            or budget.get("analysis_timeout_seconds") != 180
            or budget.get("retry_policy_id") != retry_generation.RETRY_POLICY_ID):
        raise ValueError("Invalid duplicate-aware bounded P3 v5 budget.")

    profile = read_json(PROFILE_PATH)
    profile_sha256 = digest(PROFILE_PATH)
    config, base_config_hash = active.load_config()
    if (profile.get("protocol_id") != PROTOCOL_ID
            or profile.get("base_runtime_config_sha256") != base_config_hash
            or profile.get("analysis_profile_path") != "development/qwen_api_p3_timeout180_profile.json"
            or profile.get("analysis_profile_sha256") != digest(ROOT / "development/qwen_api_p3_timeout180_profile.json")
            or profile.get("retry_policy_id") != retry_generation.RETRY_POLICY_ID
            or profile.get("transport_timeouts_seconds") != {"generation": config["timeout_seconds"], "analysis": 180}
            or budget.get("retry_profile_sha256") != profile_sha256
            or budget.get("timeout_profile_sha256") != profile["analysis_profile_sha256"]
            or budget.get("base_runtime_config_sha256") != base_config_hash):
        raise ValueError("Retry profile or frozen P2-compatible base configuration changed.")

    config = copy.deepcopy(config)
    config["limits"]["max_total_api_calls"] = budget["max_api_calls"]
    effective_config_identity = {
        "schema": "qwen-p3-effective-config-v1",
        "base_runtime_config_sha256": base_config_hash,
        "bounded_base_config": config,
        "retry_profile_sha256": profile_sha256,
        "retry_policy_id": retry_generation.RETRY_POLICY_ID,
        "retry_policy_source_sha256": digest(ROOT / "development/qwen_api_p3_v5_generation.py"),
        "protocol_id": PROTOCOL_ID,
    }
    config_hash = canonical_digest(effective_config_identity)
    configure_protocol(profile, profile_sha256)
    plan, protocol, plan_hash, protocol_hash = active.validate_api_plan(plan_path, config, config_hash)
    if plan["experiment_id"] != EXPERIMENT_ID:
        raise ValueError("Plan experiment ID differs from this launcher's fresh cohort ID.")
    if digest(plan_path) != budget.get("plan_sha256"):
        raise ValueError("Pilot plan changed after its budget was frozen.")
    estimate = active.estimate_api_calls(plan, protocol)
    if estimate > budget["max_api_calls"]:
        raise ValueError("Pilot worst-case API request count exceeds the explicit ceiling.")

    sources = runtime_source_hashes()
    if sources != budget.get("runtime_source_sha256"):
        raise ValueError("P3 v5 sources changed after the duplicate-aware retry budget was frozen.")
    snapshot = active.runtime_snapshot(config_hash, ROOT)
    snapshot.update(
        protocol_id=PROTOCOL_ID,
        source_sha256=sources,
        retry_profile_id=profile["profile_id"],
        retry_profile_sha256=profile_sha256,
        retry_policy_id=retry_generation.RETRY_POLICY_ID,
        retry_policy_source_sha256=digest(ROOT / "development/qwen_api_p3_v5_generation.py"),
        api_timeout_profile_id=profile["analysis_profile_id"],
        api_timeout_profile_sha256=profile["analysis_profile_sha256"],
        api_transport_timeouts_seconds=profile["transport_timeouts_seconds"],
        effective_runtime_config_identity_sha256=config_hash,
    )
    snapshot.update(budget_sha256=digest(budget_path), bounded_launcher_sha256=digest(Path(__file__).resolve()))

    output_directory = ROOT / "results/raw/pilot" / EXPERIMENT_ID
    if output_directory.exists():
        raise ValueError("This launcher only prepares a fresh experiment ID and never resumes or overwrites.")
    return budget, profile, config, plan, protocol, plan_hash, protocol_hash, snapshot, estimate


class DeadlineQwenAPI(Timeout180CheckpointedQwenAPI):
    def __init__(self, key, directory, config, *, analysis_timeout_seconds, max_seconds, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + max_seconds
        super().__init__(key, directory, config, analysis_timeout_seconds=analysis_timeout_seconds)

    def require_time(self, stage=None):
        reserve = self.settings[stage].timeout_seconds if stage is not None else 0
        if self.clock() + reserve >= self.deadline:
            raise APIRuntimeFailure("pilot_time_budget_exceeded", {"used_calls": self.used_calls})

    def chat(self, stage, messages, attempt_directory):
        self.require_time(stage)
        return super().chat(stage, messages, attempt_directory)


def run(plan_path: Path, budget_path: Path, *, execute=False, confirm_local_dvwa=False,
        confirm_database_reset=False, confirm_api_spending=False) -> dict:
    budget, profile, config, plan, protocol, plan_hash, protocol_hash, snapshot, estimate = prepare(
        plan_path, budget_path)
    directory = ROOT / "results/raw/pilot" / EXPERIMENT_ID
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "protocol_id": PROTOCOL_ID,
        "retry_profile_id": profile["profile_id"],
        "retry_policy_id": retry_generation.RETRY_POLICY_ID,
        "api_transport_timeouts_seconds": profile["transport_timeouts_seconds"],
        "worst_case_api_calls": estimate,
        "api_call_ceiling": budget["max_api_calls"],
        "max_wall_seconds": budget["max_wall_seconds"],
        "execution_started": False,
        "planned_slots": len(active.local_runner.planned_units(plan, protocol)),
    }
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

    ledger = active.local_runner.ExperimentLedger.create(
        directory, plan, protocol, plan_hash, protocol_hash, ROOT)
    active.check_or_write_runtime_snapshot(directory, snapshot, ledger)
    active.local_runner.safe_write_json(directory / "explicit-budget.snapshot.json", budget)
    active.local_runner.safe_write_json(directory / "bounded-config.snapshot.json", config)
    active.local_runner.safe_write_json(directory / "generation-retry-profile.snapshot.json", profile)
    api = DeadlineQwenAPI(
        key, directory, config,
        analysis_timeout_seconds=profile["transport_timeouts_seconds"]["analysis"],
        max_seconds=budget["max_wall_seconds"])

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
    result.update(
        protocol_id=PROTOCOL_ID,
        retry_profile_id=profile["profile_id"],
        retry_policy_id=retry_generation.RETRY_POLICY_ID,
        api_transport_timeouts_seconds=profile["transport_timeouts_seconds"],
        api_calls_used=api.used_calls,
        api_call_ceiling=api.max_total_calls,
        execution_started=True,
        max_wall_seconds=budget["max_wall_seconds"],
    )
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
    output = run(
        args.plan, args.budget, execute=args.execute,
        confirm_local_dvwa=args.confirm_local_dvwa,
        confirm_database_reset=args.confirm_database_reset,
        confirm_api_spending=args.confirm_api_spending)
    print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
