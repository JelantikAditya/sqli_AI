"""Fail-closed runner for the single-unit P4 S5-B Replicate-3 amendment.

The default dry run is offline: it validates the amendment and original audit
without reading credentials or contacting Poolside or DVWA. Formal execution
requires separate hash-bound amendment-freeze and execution receipts.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import run_poolside_laguna_p4_replicate3 as base
import run_qwen_api_experiments as engine
from poolside_completion_budget import CompletionBudgetPoolsideAPI
from qwen_api_runtime import APIRuntimeFailure
from run_poolside_generation_preflight import write_new


AMENDMENT_PATH = ROOT / "development/poolside_laguna_p4_s5b_amendment_20261023.json"
PLAN_PATH = ROOT / "development/poolside_laguna_p4_s5b_plan_20261023.json"
BUDGET_PATH = ROOT / "development/poolside_laguna_p4_s5b_budget_20261023.json"
PACKAGE_PATH = ROOT / "docs/evidence/poolside-laguna-p4-s5b-amendment-package-2026-10-23.json"
AMENDMENT_NOTE_PATH = ROOT / "docs/usulan-amendemen-terarah-p4-s5b-r3-2026-10-23.md"
READINESS_PATH = ROOT / "docs/evidence/poolside-laguna-p4-s5b-amendment-readiness-2026-10-23.json"
FREEZE_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-s5b-amendment-freeze-approval-2026-10-23.json"
EXECUTION_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-s5b-amendment-execution-approval-2026-10-23.json"
SOURCE_AUDIT_PATH = ROOT / "docs/evidence/poolside-laguna-p4-execution-audit-replicate3-2026-10-23.json"
SOURCE_RESULT_PATH = ROOT / "results/raw/formal/poolside-laguna-p4-replicate3-20261023/poolside-p4-execution-result.json"
SOURCE_LEDGER_PATH = ROOT / "results/raw/formal/poolside-laguna-p4-replicate3-20261023/ledger.jsonl"
SUPPLEMENT_OUTPUT = ROOT / "results/raw/formal/poolside-p4-s5b-r3-amend1-20261023"
PLAN_SCHEMA_PATH = ROOT / "schemas/local-run-plan.schema.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def canonical_plan_hash(plan: dict) -> str:
    payload = {key: value for key, value in plan.items() if not key.endswith("_resolved")}
    return hashlib.sha256(engine.canonical_json(payload)).hexdigest()


def _verify_source_unit(amendment: dict, audit: dict) -> dict:
    partial = audit.get("incomplete_unit", {})
    expected = {
        "scenario_id": "S5", "condition_id": "B", "replicate": 3,
        "exclusion_reason": "incomplete_candidate_budget", "expected_candidates": 10,
        "valid_candidates_executed": 9, "analysis_completed_candidates": 9,
        "system_decision": "not_evaluable", "metric_eligible": False,
        "stop_reason": "generation_exhausted", "runtime_failure_code": None,
    }
    if any(partial.get(key) != value for key, value in expected.items()):
        raise ValueError("The source audit no longer describes the exact incomplete S5-B Replicate-3 unit.")
    if amendment.get("source_attempt_id") != partial.get("attempt_id"):
        raise ValueError("Amendment source attempt does not match the original audit.")
    if not SOURCE_LEDGER_PATH.is_file() or not SOURCE_RESULT_PATH.is_file():
        raise ValueError("Original Replicate-3 raw ledger or result is missing.")
    source_hashes = audit.get("artifact_sha256", {})
    ledger_hash = sha256(SOURCE_LEDGER_PATH)
    result_hash = sha256(SOURCE_RESULT_PATH)
    if (ledger_hash != source_hashes.get("ledger")
            or result_hash != source_hashes.get("execution_result")
            or ledger_hash != amendment.get("source_ledger_sha256")
            or result_hash != amendment.get("source_execution_result_sha256")):
        raise ValueError("Original raw ledger or execution result differs from the tracked audit hashes.")
    if (audit.get("status") != "completed-with-one-incomplete-unit-excluded"
            or audit.get("scope_and_counts", {}).get("metric_eligible_units_completed") != 32
            or audit.get("scope_and_counts", {}).get("metric_eligible_units_expected") != 33
            or audit.get("authorization", {}).get("release_manifest_sha256")
            != amendment.get("source_release_sha256")):
        raise ValueError("Source audit does not match the authorized 32-of-33 Replicate-3 outcome.")
    audit_path = amendment.get("source_audit_path")
    if audit_path != relative(SOURCE_AUDIT_PATH):
        raise ValueError("Amendment points to an unexpected source audit.")
    if amendment.get("source_audit_sha256") != sha256(SOURCE_AUDIT_PATH):
        raise ValueError("Amendment does not bind the current source audit hash.")

    matching = []
    for line in SOURCE_LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if (event.get("scenario_id"), event.get("condition_id"), event.get("replicate")) == ("S5", "B", 3):
            matching.append(event)
    completions = [event for event in matching if event.get("event_type") == "attempt_completed"]
    starts = [event for event in matching if event.get("event_type") == "attempt_started"]
    if (len(starts) != 1 or len(completions) != 1
            or completions[0].get("generated_candidate_count") != 9
            or completions[0].get("budget_complete") is not False
            or completions[0].get("metric_eligible") is not False
            or completions[0].get("exclusion_reason") != "incomplete_candidate_budget"):
        raise ValueError("Original append-only ledger does not confirm one excluded 9/10 attempt.")
    if starts[0].get("attempt_id") != amendment.get("source_attempt_id"):
        raise ValueError("Original ledger attempt ID differs from the amendment binding.")
    return {"attempt_id": starts[0]["attempt_id"], "completed_candidates": 9,
            "candidate_budget": 10, "metric_eligible": False,
            "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
            "source_result_sha256": sha256(SOURCE_RESULT_PATH)}


def prepare() -> tuple[dict, dict, dict, dict, dict]:
    amendment = read_json(AMENDMENT_PATH)
    plan = read_json(PLAN_PATH)
    budget = read_json(BUDGET_PATH)
    package = read_json(PACKAGE_PATH)

    if amendment.get("schema") != "poolside-laguna-p4-targeted-amendment-v1":
        raise ValueError("Unknown targeted amendment schema.")
    if package.get("schema") != "poolside-laguna-p4-s5b-amendment-package-v1":
        raise ValueError("Unknown targeted amendment package schema.")
    if package.get("status") != "draft-awaiting-separate-freeze-and-execution-approval":
        raise ValueError("Amendment package status does not fail closed.")
    if package.get("formal_execution_authorized") is not False:
        raise ValueError("Draft amendment package must not authorize formal execution.")

    for label, path in (("amendment", AMENDMENT_PATH), ("plan", PLAN_PATH),
                        ("budget", BUDGET_PATH), ("runner", Path(__file__).resolve()),
                        ("amendment_note", AMENDMENT_NOTE_PATH),
                        ("base_protocol", base.PROTOCOL_PATH), ("base_release", base.RELEASE_PATH),
                        ("source_audit", SOURCE_AUDIT_PATH), ("source_ledger", SOURCE_LEDGER_PATH),
                        ("source_result", SOURCE_RESULT_PATH)):
        expected = package.get("artifact_sha256", {}).get(label)
        if not path.is_file() or expected != sha256(path):
            raise ValueError(f"Amendment package hash mismatch for {label}.")

    ceilings = budget.get("hard_ceilings", {})
    if (budget.get("schema") != "poolside-laguna-p4-single-unit-budget-v1"
            or budget.get("status") != "draft-not-executable"
            or budget.get("formal_execution_authorized") is not False
            or budget.get("maximum_spend_usd") != 0
            or ceilings.get("api_call_ceiling") != 40
            or ceilings.get("generation_requests_ceiling") != 30
            or ceilings.get("analysis_requests_ceiling") != 10
            or ceilings.get("completion_token_ceiling") != 51200
            or ceilings.get("generation_max_tokens") != 1024
            or ceilings.get("analysis_max_tokens") != 2048
            or ceilings.get("api_wall_time_ceiling_seconds") != 2700
            or ceilings.get("automatic_unit_replacements") != 0
            or ceilings.get("automatic_transport_retries") != 0
            or ceilings.get("model_fallback") is not False
            or budget.get("provider_model", {}).get("provider") != "direct Poolside API only"
            or budget.get("provider_model", {}).get("model") != base.transport.MODEL
            or budget.get("provider_model", {}).get("openrouter_allowed") is not False):
        raise ValueError("Supplement budget is not the approved zero-cost, one-unit ceiling.")
    if budget.get("plan_sha256") != sha256(PLAN_PATH):
        raise ValueError("Single-unit budget does not bind the amendment plan.")
    if budget.get("amendment_sha256") != sha256(AMENDMENT_PATH):
        raise ValueError("Single-unit budget does not bind the amendment policy.")

    base_inputs = base.verify_plan_inputs(require_frozen=True)
    if (amendment.get("source_release_sha256") != sha256(base.RELEASE_PATH)
            or amendment.get("source_formal_plan_sha256") != sha256(base.PLAN_PATH)
            or amendment.get("source_budget_sha256") != sha256(base.BUDGET_PATH)
            or amendment.get("source_protocol_sha256") != sha256(base.PROTOCOL_PATH)
            or amendment.get("source_protocol_candidate_sha256") != base.protocol_candidate_sha256(base_inputs["protocol"])):
        raise ValueError("Amendment source does not match the currently frozen and released P4 Replicate-3 inputs.")

    unit_source = _verify_source_unit(amendment, read_json(SOURCE_AUDIT_PATH))
    if (plan.get("schema_version") != "1.0.0"
            or plan.get("dataset") != "formal"
            or plan.get("experiment_id") != amendment.get("supplement_experiment_id")
            or plan.get("condition_ids") != ["B"]
            or plan.get("scenario_ids") != ["S5"]
            or plan.get("replicates") != [3]
            or set(plan.get("discovery_reports", {})) != {"S5"}
            or plan.get("seclists_source_root") is not None):
        raise ValueError("Supplement plan must contain only condition B, scenario S5, replicate 3.")
    if plan.get("knowledge_snapshot") != base_inputs["plan"].get("knowledge_snapshot"):
        raise ValueError("Supplement plan changed the frozen P4 RAG snapshot.")
    Draft202012Validator(read_json(PLAN_SCHEMA_PATH)).validate(plan)
    protocol = base_inputs["protocol"]
    resolved = engine.local_runner.validate_plan(plan, protocol, ROOT, verify_index=False)
    slots = engine.local_runner.planned_units(resolved, protocol, ROOT)
    if (len(slots) != 1 or slots[0].get("status") != "planned"
            or (slots[0].get("scenario_id"), slots[0].get("condition_id"), slots[0].get("replicate")) != ("S5", "B", 3)
            or engine.estimate_api_calls(resolved, protocol) != 40):
        raise ValueError("Supplement plan did not resolve to exactly one P4 S5-B Replicate-3 unit.")
    if resolved["discovery_reports_resolved"].get("S5", {}).get(3) is None:
        raise ValueError("Supplement discovery report is missing.")
    source_plan = read_json(base.PLAN_PATH)
    report_path = ROOT / source_plan["discovery_reports"]["S5"]["3"]
    if sha256(report_path) != package.get("artifact_sha256", {}).get("s5r3_discovery"):
        raise ValueError("Supplement discovery report differs from the released S5 Replicate-3 report.")
    if SUPPLEMENT_OUTPUT.exists():
        raise ValueError("Supplement output directory already exists; refusing to overwrite or replay it.")
    if not FREEZE_APPROVAL_PATH.exists() and not EXECUTION_APPROVAL_PATH.exists():
        approval_state = "pending-separate-freeze-and-execution-approval"
    elif not FREEZE_APPROVAL_PATH.exists() or not EXECUTION_APPROVAL_PATH.exists():
        approval_state = "incomplete-approval-receipts"
    else:
        approval_state = "receipts-present-validate-before-execution"
    return amendment, resolved, protocol, budget, {
        "base_inputs": base_inputs, "slots": slots, "unit_source": unit_source,
        "approval_state": approval_state,
    }


def dry_run() -> dict:
    amendment, plan, protocol, budget, checked = prepare()
    return {
        "schema": "poolside-laguna-p4-s5b-amendment-readiness-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ready-for-amendment-freeze-review",
        "amendment_id": amendment["amendment_id"],
        "package_sha256": sha256(PACKAGE_PATH),
        "amendment_sha256": sha256(AMENDMENT_PATH),
        "plan_sha256": sha256(PLAN_PATH),
        "budget_sha256": sha256(BUDGET_PATH),
        "protocol_sha256": sha256(base.PROTOCOL_PATH),
        "source_unit": {"scenario_id": "S5", "condition_id": "B", "replicate": 3,
                        "original_candidates": 9, "required_candidates": 10,
                        "original_attempt_metric_eligible": False},
        "planned_supplement_units": len(checked["slots"]),
        "planned_api_calls_ceiling": budget["hard_ceilings"]["api_call_ceiling"],
        "planned_completion_token_ceiling": budget["hard_ceilings"]["completion_token_ceiling"],
        "maximum_spend_usd": budget["maximum_spend_usd"],
        "planned_database_resets": 1,
        "output_path": relative(SUPPLEMENT_OUTPUT),
        "approval_state": checked["approval_state"],
        "formal_execution_authorized": False,
        "execution_started": False,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "credentials_read": False,
        "openrouter_used": False,
        "source_checks": checked["unit_source"],
        "gates": {
            "original-p4-frozen-inputs": "passed",
            "original-partial-unit-audited": "passed",
            "single-unit-plan-s5-b-r3": "passed",
            "frozen-method-and-snapshot-preserved": "passed",
            "zero-spend-bounded-budget": "passed",
            "separate-amendment-freeze-approval": "pending",
            "separate-formal-execution-approval": "pending",
        },
    }


def _validate_approval(path: Path, *, kind: str, package_sha: str) -> dict:
    receipt = read_json(path)
    if kind == "freeze":
        required = {
            "schema": "poolside-laguna-p4-s5b-amendment-freeze-v1",
            "decision": "approved-for-p4-s5b-amendment-freeze",
            "formal_amendment_freeze": True,
            "formal_execution_approval": False,
        }
    else:
        required = {
            "schema": "poolside-laguna-p4-s5b-amendment-execution-v1",
            "decision": "approved-for-p4-s5b-formal-execution",
            "formal_execution_approval": True,
            "maximum_spend_usd": 0,
        }
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError(f"The separate amendment {kind} receipt is missing or not approved.")
    if (receipt.get("package_sha256") != package_sha
            or receipt.get("plan_sha256") != sha256(PLAN_PATH)
            or receipt.get("budget_sha256") != sha256(BUDGET_PATH)
            or receipt.get("amendment_sha256") != sha256(AMENDMENT_PATH)
            or receipt.get("protocol_sha256") != sha256(base.PROTOCOL_PATH)):
        raise ValueError(f"Amendment {kind} receipt is not bound to this exact package.")
    if kind == "execution" and receipt.get("freeze_approval_sha256") != sha256(FREEZE_APPROVAL_PATH):
        raise ValueError("Execution receipt does not bind the approved amendment-freeze receipt.")
    if kind == "execution":
        scope = receipt.get("unit_scope", {})
        ceilings = read_json(BUDGET_PATH)["hard_ceilings"]
        if (scope != {"condition_id": "B", "scenario_id": "S5", "replicate": 3,
                      "database_resets": 1}
                or receipt.get("api_call_ceiling") != ceilings["api_call_ceiling"]
                or receipt.get("completion_token_ceiling") != ceilings["completion_token_ceiling"]
                or receipt.get("output_path") != relative(SUPPLEMENT_OUTPUT)):
            raise ValueError("Execution receipt scope or ceilings differ from this one-unit amendment.")
    authority = receipt.get("authority", {})
    if (authority.get("role") != "researcher"
            or authority.get("basis") != "explicit-user-approval"
            or not authority.get("approved_at_local")
            or not authority.get("quote")):
        raise ValueError(f"Amendment {kind} receipt lacks explicit researcher authority.")
    if kind == "execution" and (receipt.get("confirm_local_dvwa") is not True
                                  or receipt.get("confirm_database_reset") is not True
                                  or receipt.get("confirm_zero_spend") is not True):
        raise ValueError("Execution approval must explicitly authorize local DVWA, one reset, and USD 0.")
    return receipt


def execute(*, confirm_local_dvwa: bool, confirm_database_reset: bool,
            confirm_zero_spend: bool) -> dict:
    amendment, plan, protocol, budget, checked = prepare()
    package = read_json(PACKAGE_PATH)
    package_hash = sha256(PACKAGE_PATH)
    _validate_approval(FREEZE_APPROVAL_PATH, kind="freeze", package_sha=package_hash)
    execution_approval = _validate_approval(EXECUTION_APPROVAL_PATH, kind="execution",
                                            package_sha=package_hash)
    if not (confirm_local_dvwa and confirm_database_reset and confirm_zero_spend):
        raise ValueError("Execution requires explicit local-DVWA, one-reset, and zero-spend command flags.")
    if execution_approval.get("maximum_spend_usd") != 0:
        raise ValueError("This amendment only permits free-only execution.")

    engine.local_runner.require_local_target(protocol["target_origin"])
    api_key = base.transport.load_key()
    if not api_key:
        raise ValueError("No direct Poolside API key is configured in the local environment.")
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    clean_plan = {key: value for key, value in plan.items() if not key.endswith("_resolved")}
    plan_hash = canonical_plan_hash(clean_plan)
    protocol_hash = sha256(base.PROTOCOL_PATH)
    authorization = {
        "scope": "poolside-p4-s5b-targeted-amendment-execution",
        "amendment_package_sha256": package_hash,
        "execution_approval_path": relative(EXECUTION_APPROVAL_PATH),
        "execution_approval_sha256": sha256(EXECUTION_APPROVAL_PATH),
        "maximum_spend_usd": 0,
        "formal_execution_approval": True,
    }
    ledger = engine.local_runner.ExperimentLedger.create(
        SUPPLEMENT_OUTPUT, plan, protocol, plan_hash, protocol_hash, ROOT,
        formal_execution_authorization=authorization)
    write_new(SUPPLEMENT_OUTPUT / "poolside-p4-amendment-runtime.snapshot.json", {
        "amendment_id": amendment["amendment_id"], "package_sha256": package_hash,
        "plan_sha256": sha256(PLAN_PATH), "budget_sha256": sha256(BUDGET_PATH),
        "protocol_sha256": protocol_hash, "source_release_sha256": sha256(base.RELEASE_PATH),
        "execution_approval_sha256": authorization["execution_approval_sha256"],
        "runtime_source_sha256": checked["base_inputs"]["runtime_hashes"],
        "api_base_url": base.transport.BASE_URL, "model": base.transport.MODEL,
        "api_call_ceiling": budget["hard_ceilings"]["api_call_ceiling"],
        "completion_token_ceiling": budget["hard_ceilings"]["completion_token_ceiling"],
        "maximum_spend_usd": 0, "openrouter_used": False,
    })
    for source_name in checked["base_inputs"]["runtime_hashes"]:
        source = ROOT / source_name
        target = SUPPLEMENT_OUTPUT / "source" / source_name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(source.read_bytes())

    api = CompletionBudgetPoolsideAPI(
        api_key, SUPPLEMENT_OUTPUT,
        max_calls=budget["hard_ceilings"]["api_call_ceiling"],
        max_seconds=budget["hard_ceilings"]["api_wall_time_ceiling_seconds"],
        max_completion_tokens=budget["hard_ceilings"]["completion_token_ceiling"],
    )
    config = {"limits": {"max_total_api_calls": budget["hard_ceilings"]["api_call_ceiling"],
                         "max_retrieved_chars_per_chunk": 1800}}

    def execute_one(unit, attempt, active_plan, active_protocol, data_dir, root):
        api.require_time()
        print(json.dumps({"event": "unit-start", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "replicate": unit["replicate"],
                          "api_calls": api.used_calls}, ensure_ascii=False), flush=True)
        return base._execute_one(unit, attempt, active_plan, active_protocol,
                                 data_dir, api, config)

    with base.p4_callbacks(), engine.local_runner.experiment_lock(SUPPLEMENT_OUTPUT):
        result = engine.local_runner.execute_ledger(
            ledger, plan, protocol, SUPPLEMENT_OUTPUT, execute=True,
            retry_invalid=False, recovered=0, root=ROOT, execute_one=execute_one)
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result_file in SUPPLEMENT_OUTPUT.glob("attempts/**/api-calls/*/result.json"):
        record = read_json(result_file).get("result", {})
        current = record.get("usage") or {}
        for key in usage:
            if type(current.get(key)) is int:
                usage[key] += current[key]
    summary = {
        **result, "amendment_id": amendment["amendment_id"],
        "source_attempt_id": amendment["source_attempt_id"],
        "protocol_id": protocol["protocol_id"], "model": base.transport.MODEL,
        "api_calls_used": api.used_calls, "api_call_ceiling": budget["hard_ceilings"]["api_call_ceiling"],
        "completion_tokens_used": api.completion_tokens_reserved,
        "completion_token_ceiling": budget["hard_ceilings"]["completion_token_ceiling"],
        "usage_totals": usage, "execution_started": True,
        "openrouter_used": False, "maximum_spend_usd": 0,
    }
    result_path = SUPPLEMENT_OUTPUT / "poolside-p4-s5b-amendment-result.json"
    if not result_path.exists():
        write_new(result_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true",
                       help="Validate the one-unit amendment without credentials or network access")
    modes.add_argument("--execute", action="store_true",
                       help="Run the single unit only after separate hash-bound approvals exist")
    parser.add_argument("--output", type=Path, help="Write dry-run evidence inside this project")
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    parser.add_argument("--confirm-zero-spend", action="store_true")
    args = parser.parse_args()
    execution_attempted = bool(args.execute)
    try:
        if args.execute:
            if args.output:
                parser.error("--output is only for the dry run.")
            result = execute(confirm_local_dvwa=args.confirm_local_dvwa,
                             confirm_database_reset=args.confirm_database_reset,
                             confirm_zero_spend=args.confirm_zero_spend)
        else:
            result = dry_run()
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        print(rendered, end="")
        if args.output:
            output = args.output if args.output.is_absolute() else ROOT / args.output
            if not output.resolve().is_relative_to(ROOT.resolve()):
                parser.error("--output must remain inside the P4 workspace.")
            if output.exists():
                parser.error("Refusing to overwrite existing amendment readiness evidence.")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(rendered)
        return 0 if args.execute or result.get("status") == "ready-for-amendment-freeze-review" else 2
    except (OSError, ValueError, KeyError, TypeError, APIRuntimeFailure) as failure:
        side_effects = ({"execution_attempted": True,
                         "api_requests_sent": "inspect amendment checkpoints",
                         "dvwa_requests_sent": "inspect amendment ledger and validation logs"}
                        if execution_attempted else
                        {"execution_attempted": False, "api_requests_sent": 0,
                         "dvwa_requests_sent": 0, "credentials_read": False})
        print(json.dumps({"status": "blocked", "error_type": type(failure).__name__,
                          "message": str(failure), **side_effects,
                          "openrouter_used": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
