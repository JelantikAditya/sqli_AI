"""Freeze the offline Q3 plan and budget, then validate the bounded dry run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import poolside_laguna_generation_v4 as generation
import run_bounded_poolside_qualification_v4 as runner
from poolside_completion_budget import MAX_COMPLETION_TOKENS


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLAN = ROOT / "development/poolside_laguna_qualification_plan_20261022_v2.json"
SOURCE_BUDGET = ROOT / "development/poolside_laguna_qualification_budget_20261022_v2.json"
PLAN_PATH = runner.PLAN_PATH
BUDGET_PATH = runner.BUDGET_PATH
REPLAY_PATH = ROOT / "docs/evidence/poolside-laguna-q3-q2-offline-replay-2026-10-23.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, document: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def prepare() -> dict:
    if PLAN_PATH.exists() or BUDGET_PATH.exists():
        raise ValueError("Q3 plan or budget already exists; refusing to overwrite the frozen cohort.")
    if not REPLAY_PATH.is_file():
        raise ValueError("The pinned offline Q2 replay evidence is missing.")
    replay = _read(REPLAY_PATH)
    if (replay.get("source_unit_count") != 24
            or replay.get("source_candidate_count") != 235
            or replay.get("v4_family_id_collisions") != 0
            or replay.get("v4_reference_key_collisions_with_accepted_candidates") != 0
            or replay.get("parser_replay_mismatches")
            or replay.get("saved_response_hash_mismatches") != 0
            or replay.get("source_files_unchanged") is not True
            or replay.get("api_requests_sent") != 0
            or replay.get("dvwa_requests_sent") != 0):
        raise ValueError("The Q2 offline replay did not pass its frozen integrity checks.")
    plan = _read(SOURCE_PLAN)
    budget = _read(SOURCE_BUDGET)
    if plan["experiment_id"] != budget["experiment_id"]:
        raise ValueError("The source Q2 plan and budget do not match.")

    plan["experiment_id"] = runner.EXPERIMENT_ID
    plan_bytes = (json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")

    pinned_sources = dict(budget["runtime_source_sha256"])
    for relative, expected in pinned_sources.items():
        path = ROOT / relative
        if not path.is_file() or _digest(path) != expected:
            raise ValueError("An inherited Q2 runtime source pin no longer matches: " + relative)
    added_sources = (
        "development/poolside_laguna_generation_v4.py",
        "development/poolside_completion_budget.py",
        "development/run_bounded_poolside_qualification_v4.py",
    )
    for relative in added_sources:
        pinned_sources[relative] = _digest(ROOT / relative)

    budget.update(
        schema="poolside-generation-qualification-budget-v2",
        experiment_id=runner.EXPERIMENT_ID,
        status="prepared-not-executed",
        scope="Fresh P3 generation qualification only; not formal data.",
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
        q2_offline_replay_path=REPLAY_PATH.relative_to(ROOT).as_posix(),
        q2_offline_replay_sha256=_digest(REPLAY_PATH),
        account_spending_limit_usd=None,
        account_spending_limit_verified=False,
        account_budget_evidence_path=None,
        runtime_source_sha256=pinned_sources,
        formal_eligible=False,
    )
    budget["qualification_gate"].update(
        all_24_ab_units_complete_10_candidates=True,
        unique_family_id_per_generation_request=True,
        reference_family_key_not_already_accepted=True,
        partial_cohort_is_not_formal_or_eligible=True,
    )

    # Validate temporary plan/budget before publishing immutable cohort inputs.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="poolside-q3-plan-") as temporary:
        temp_root = Path(temporary)
        temp_plan, temp_budget = temp_root / "plan.json", temp_root / "budget.json"
        temp_plan.write_bytes(plan_bytes)
        budget_bytes = (json.dumps(budget, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        temp_budget.write_bytes(budget_bytes)
        dry_run = runner.run(execute=False, plan_path=temp_plan, budget_path=temp_budget)

    if dry_run["execution_started"] or dry_run["applicable_units"] != 24:
        raise ValueError("Q3 offline preparation did not produce the expected 24-unit qualification.")
    if (dry_run["worst_case_api_calls"] != 960
            or dry_run["candidate_budget"] != 240
            or dry_run["logical_confirmations"] != 720
            or dry_run["max_completion_tokens"] != MAX_COMPLETION_TOKENS):
        raise ValueError("Q3 dry-run budget differs from its frozen plan.")

    _write_new(PLAN_PATH, plan)
    _write_new(BUDGET_PATH, budget)
    return {"plan": str(PLAN_PATH.relative_to(ROOT)),
            "budget": str(BUDGET_PATH.relative_to(ROOT)),
            "plan_sha256": hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
            "budget_sha256": _digest(BUDGET_PATH),
            "runtime_source_count": len(pinned_sources),
            "dry_run": dry_run}


def main() -> int:
    result = prepare()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
