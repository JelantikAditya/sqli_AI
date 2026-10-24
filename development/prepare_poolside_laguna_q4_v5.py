"""Freeze a fresh v5 qualification plan and budget, then validate a dry-run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import poolside_laguna_generation_v5 as generation
import run_bounded_poolside_qualification_v5 as runner
from poolside_completion_budget import MAX_COMPLETION_TOKENS


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLAN = ROOT / "development/poolside_laguna_qualification_plan_20261023_q3.json"
SOURCE_BUDGET = ROOT / "development/poolside_laguna_qualification_budget_20261023_q3.json"
Q3_REPLAY = ROOT / "docs/evidence/poolside-laguna-q3-v5-offline-replay-2026-10-23.json"
PLAN_PATH = runner.PLAN_PATH
BUDGET_PATH = runner.BUDGET_PATH
EVIDENCE_PATH = ROOT / "docs/evidence/poolside-laguna-q4-v5-dry-run-2026-10-23.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, document: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _validate_q3_replay(source_budget: dict) -> dict:
    if not Q3_REPLAY.is_file():
        raise ValueError("The saved Q3 v5 offline replay evidence is missing.")
    replay = _read(Q3_REPLAY)
    if (replay.get("source_experiment_id") != source_budget["experiment_id"]
            or replay.get("replay_profile") != generation.PROMPT_VERSION
            or replay.get("source_unit_count") != 24
            or replay.get("source_generation_calls_replayed") != 274
            or replay.get("saved_candidate_count") != replay.get("replayed_candidate_count")
            or replay.get("parser_status_mismatches")
            or replay.get("saved_request_hash_mismatches") != 0
            or replay.get("replayed_family_id_collisions") != 0
            or replay.get("retry_signature_coverage_failures") != 0
            or replay.get("source_files_unchanged") is not True
            or replay.get("api_requests_sent") != 0
            or replay.get("dvwa_requests_sent") != 0):
        raise ValueError("The saved Q3 v5 replay did not pass its frozen integrity checks.")
    return replay


def prepare() -> dict:
    if PLAN_PATH.exists() or BUDGET_PATH.exists() or EVIDENCE_PATH.exists():
        raise ValueError("A v5 plan, budget, or evidence file already exists; refusing to overwrite it.")
    if not SOURCE_PLAN.is_file() or not SOURCE_BUDGET.is_file():
        raise ValueError("The pinned Q3 plan or budget is missing.")

    source_plan = _read(SOURCE_PLAN)
    source_budget = _read(SOURCE_BUDGET)
    if source_plan.get("experiment_id") != source_budget.get("experiment_id"):
        raise ValueError("The source Q3 plan and budget do not match.")
    if source_budget.get("status") != "prepared-not-executed":
        raise ValueError("The source Q3 budget is not a frozen preparation artifact.")
    for relative, expected in source_budget.get("runtime_source_sha256", {}).items():
        path = ROOT / relative
        if not path.is_file() or _digest(path) != expected:
            raise ValueError("An inherited Q3 runtime source pin no longer matches: " + relative)

    replay = _validate_q3_replay(source_budget)
    plan = dict(source_plan)
    plan["experiment_id"] = runner.EXPERIMENT_ID
    plan_bytes = (json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")

    budget = dict(source_budget)
    pinned_sources = dict(source_budget["runtime_source_sha256"])
    for relative in (
        "development/poolside_laguna_generation_v5.py",
        "development/run_bounded_poolside_qualification_v5.py",
    ):
        pinned_sources[relative] = _digest(ROOT / relative)

    budget.update(
        experiment_id=runner.EXPERIMENT_ID,
        status="prepared-not-executed",
        scope="Fresh P3 generation qualification using the v5 structure-feedback profile; not formal data.",
        plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        max_api_calls=960,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        max_wall_seconds=21600,
        generation_requests_per_candidate_slot=3,
        candidate_budget_per_unit=10,
        confirmations_per_candidate=3,
        automatic_transport_retries=0,
        automatic_replacement_attempts=0,
        generation_retry_policy_id=generation.RETRY_POLICY_ID,
        generation_prompt_version=generation.PROMPT_VERSION,
        retrieval_context_policy_id=generation.RETRIEVAL_CONTEXT_POLICY_ID,
        family_bank_size_per_probe=generation.MAX_FAMILIES_PER_PROBE,
        unique_family_scheduling_within_unit=True,
        q3_v5_offline_replay_path=Q3_REPLAY.relative_to(ROOT).as_posix(),
        q3_v5_offline_replay_sha256=_digest(Q3_REPLAY),
        q3_predecessor_experiment_id=source_budget["experiment_id"],
        q3_v5_offline_replay_candidate_count=replay["replayed_candidate_count"],
        runtime_source_sha256=pinned_sources,
        formal_eligible=False,
    )
    budget["qualification_gate"].update(
        all_24_ab_units_complete_10_candidates=True,
        unique_family_id_per_generation_request=True,
        reference_family_key_not_already_accepted=True,
        partial_cohort_is_not_formal_or_eligible=True,
        v5_structure_feedback_prompt_pinned=True,
        v5_offline_replay_integrity_passed=True,
    )

    budget_bytes = (json.dumps(budget, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="poolside-q4-v5-") as temporary:
        temp_root = Path(temporary)
        temp_plan, temp_budget = temp_root / "plan.json", temp_root / "budget.json"
        temp_plan.write_bytes(plan_bytes)
        temp_budget.write_bytes(budget_bytes)
        dry_run = runner.run(execute=False, plan_path=temp_plan, budget_path=temp_budget)

    if (dry_run.get("execution_started") is not False
            or dry_run.get("applicable_units") != 24
            or dry_run.get("candidate_budget") != 240
            or dry_run.get("logical_confirmations") != 720
            or dry_run.get("worst_case_api_calls") != 960
            or dry_run.get("max_completion_tokens") != MAX_COMPLETION_TOKENS
            or dry_run.get("generation_prompt_version") != generation.PROMPT_VERSION
            or dry_run.get("generation_retry_policy_id") != generation.RETRY_POLICY_ID):
        raise ValueError("The v5 dry-run differs from its frozen qualification budget.")

    _write_new(PLAN_PATH, plan)
    _write_new(BUDGET_PATH, budget)
    # Re-read the published inputs through the runner's standard dry-run entry point.
    frozen_dry_run = runner.run(execute=False)
    if frozen_dry_run != dry_run:
        raise ValueError("The published v5 plan/budget do not reproduce the validated dry-run.")

    evidence = {
        "schema": "poolside-laguna-q4-v5-dry-run-v1",
        "experiment_id": runner.EXPERIMENT_ID,
        "protocol_id": runner.PROTOCOL_ID,
        "status": "prepared-not-executed",
        "generation_prompt_version": generation.PROMPT_VERSION,
        "generation_retry_policy_id": generation.RETRY_POLICY_ID,
        "plan_path": PLAN_PATH.relative_to(ROOT).as_posix(),
        "plan_sha256": _digest(PLAN_PATH),
        "budget_path": BUDGET_PATH.relative_to(ROOT).as_posix(),
        "budget_sha256": _digest(BUDGET_PATH),
        "runtime_source_count": len(pinned_sources),
        "runtime_source_sha256": pinned_sources,
        "predecessor_experiment_id": source_budget["experiment_id"],
        "offline_replay_path": Q3_REPLAY.relative_to(ROOT).as_posix(),
        "offline_replay_sha256": _digest(Q3_REPLAY),
        "offline_replay_integrity_passed": True,
        "dry_run": frozen_dry_run,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "execution_started": False,
        "formal_eligible": False,
    }
    _write_new(EVIDENCE_PATH, evidence)
    return evidence


def main() -> int:
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
