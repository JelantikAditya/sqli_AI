"""Validate or execute a fresh Poolside Laguna v5 generation qualification."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import run_bounded_poolside_qualification_v3 as previous_runner
from poolside_completion_budget import (CompletionBudgetPoolsideAPI,
                                        MAX_COMPLETION_TOKENS)
import poolside_laguna_generation_v5 as generation_v5


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "poolside-s21-p3-q4-v5-20261023"
PROTOCOL_ID = "poolside-laguna-s21-sqli-v5-qualification-structure-feedback"
PLAN_PATH = ROOT / "development/poolside_laguna_qualification_plan_20261023_q4_v5.json"
BUDGET_PATH = ROOT / "development/poolside_laguna_qualification_budget_20261023_q4_v5.json"
_PREVIOUS_PREPARE = previous_runner.prepare


def _scoped_runner_overrides(stack: ExitStack) -> None:
    stack.enter_context(patch.object(previous_runner, "EXPERIMENT_ID", EXPERIMENT_ID))
    stack.enter_context(patch.object(previous_runner, "PROTOCOL_ID", PROTOCOL_ID))
    stack.enter_context(patch.object(previous_runner, "PLAN_PATH", PLAN_PATH))
    stack.enter_context(patch.object(previous_runner, "BUDGET_PATH", BUDGET_PATH))
    stack.enter_context(patch.object(previous_runner, "retry_generation", generation_v5))
    stack.enter_context(patch.object(previous_runner, "CheckpointedPoolsideAPI",
                                     CompletionBudgetPoolsideAPI))


def prepare(plan_path: Path = PLAN_PATH, budget_path: Path = BUDGET_PATH) -> tuple:
    with ExitStack() as stack:
        _scoped_runner_overrides(stack)
        prepared = _PREVIOUS_PREPARE(plan_path, budget_path)

    budget = prepared[2]
    expected_completion_ceiling = 720 * 1024 + 240 * 2048
    if (budget.get("max_completion_tokens") != MAX_COMPLETION_TOKENS
            or expected_completion_ceiling != MAX_COMPLETION_TOKENS):
        raise ValueError("The v5 completion-token budget differs from its frozen request profile.")
    if (budget.get("family_bank_size_per_probe") != generation_v5.MAX_FAMILIES_PER_PROBE
            or budget.get("unique_family_scheduling_within_unit") is not True):
        raise ValueError("The v5 budget does not pin the inherited family schedule.")

    replay_path = ROOT / budget.get("q3_v5_offline_replay_path", "")
    if (not replay_path.is_file()
            or previous_runner.digest(replay_path) != budget.get("q3_v5_offline_replay_sha256")):
        raise ValueError("The v5 budget does not match its verified offline replay evidence.")
    replay = previous_runner.engine.local_runner.read_json(replay_path)
    if (replay.get("replay_profile") != generation_v5.PROMPT_VERSION
            or replay.get("source_files_unchanged") is not True
            or replay.get("api_requests_sent") != 0
            or replay.get("dvwa_requests_sent") != 0
            or replay.get("parser_status_mismatches")
            or replay.get("saved_request_hash_mismatches") != 0
            or replay.get("retry_signature_coverage_failures") != 0):
        raise ValueError("The pinned v5 offline replay did not pass its integrity checks.")
    return prepared


def run(*, execute=False, confirm_local_dvwa=False, confirm_database_reset=False,
        confirm_api_spending=False, plan_path: Path = PLAN_PATH,
        budget_path: Path = BUDGET_PATH) -> dict:
    with ExitStack() as stack:
        _scoped_runner_overrides(stack)
        stack.enter_context(patch.object(previous_runner, "prepare",
                                         lambda: prepare(plan_path, budget_path)))
        result = previous_runner.run(
            execute=execute,
            confirm_local_dvwa=confirm_local_dvwa,
            confirm_database_reset=confirm_database_reset,
            confirm_api_spending=confirm_api_spending,
        )
    result["max_completion_tokens"] = MAX_COMPLETION_TOKENS
    return result


def main() -> int:
    import argparse
    import json

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--execute", action="store_true")
    cli.add_argument("--confirm-local-dvwa", action="store_true")
    cli.add_argument("--confirm-database-reset", action="store_true")
    cli.add_argument("--confirm-api-spending", action="store_true")
    args = cli.parse_args()
    result = run(
        execute=args.execute,
        confirm_local_dvwa=args.confirm_local_dvwa,
        confirm_database_reset=args.confirm_database_reset,
        confirm_api_spending=args.confirm_api_spending,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
