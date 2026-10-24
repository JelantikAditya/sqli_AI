"""Fail-closed runner for the P4 A/S12/R2 amended sensitivity unit.

The offline dry-run validates pinned sources without reading credentials or
contacting Poolside or DVWA. Execution is disabled until methodological,
amendment-freeze, and formal-execution receipts bind the exact package.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import run_poolside_laguna_p4_recovery1 as base
from experiment_dataset import load_runs


AMENDMENT_PATH = ROOT / "development/poolside_laguna_p4_a_s12_r2_amendment_20261023.json"
PLAN_PATH = ROOT / "development/poolside_laguna_p4_a_s12_r2_plan_20261023.json"
BUDGET_PATH = ROOT / "development/poolside_laguna_p4_a_s12_r2_budget_20261023.json"
PACKAGE_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-amendment-package-2026-10-23.json"
NOTE_PATH = ROOT / "docs/usulan-amendemen-fpr-p4-a-s12-r2-2026-10-23.md"
READINESS_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-amendment-readiness-2026-10-23.json"
METHOD_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-method-approval-2026-10-23.json"
FREEZE_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-freeze-approval-2026-10-23.json"
EXECUTION_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-a-s12-r2-execution-approval-2026-10-23.json"
PLAN_SCHEMA_PATH = ROOT / "schemas/local-run-plan.schema.json"
SOURCE_RUN_DIR = ROOT / "results/raw/formal/poolside-laguna-p4-recovery1-20261023"
SOURCE_LEDGER_PATH = SOURCE_RUN_DIR / "ledger.jsonl"
SOURCE_METRICS_PATH = ROOT / "results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01/metrics-P4-VAL01.json"
SOURCE_DIAGNOSTIC_PATH = ROOT / "docs/evidence/poolside-p4-a-r2-s12-fpr-abstention-diagnostic-2026-10-23.json"
SOURCE_SMOKE_PATH = ROOT / "results/raw/poolside-smoke/20261023T113310424083Z.json"
SUPPLEMENT_OUTPUT = ROOT / "results/raw/formal/poolside-p4-a-s12-r2-amend1-20261023"
SOURCE_UNIT_ID = "poolside-laguna-p4-20261023-a-s12-r2"
SUPPLEMENT_EXPERIMENT_ID = "poolside-p4-a-s12-r2-amend1"
AMENDMENT_ID = "p4-a-s12-r2-amend1"
EXPECTED = {
    "condition_id": "A",
    "scenario_id": "S12",
    "replicate": 2,
    "candidate_id": "candidate-004",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8-sig") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def relative(path: Path) -> str:
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_artifacts() -> dict[str, Path]:
    source_events = [json.loads(line) for line in SOURCE_LEDGER_PATH.read_text(
        encoding="utf-8").splitlines()]
    completion = next(event for event in reversed(source_events)
                      if event.get("unit_id") == SOURCE_UNIT_ID
                      and event.get("event_type") == "attempt_completed")
    adaptive_path = Path(completion["adaptive_result_path"]).resolve()
    require(adaptive_path.is_relative_to(SOURCE_RUN_DIR.resolve()),
            "Original adaptive result path escaped the source run directory.")
    discovery_path = ROOT / "results/raw/formal-discovery/poolside-laguna-p4-20261023/replicate-2/impossible/zap-discovery.normalized.json"
    return {
        "amendment": AMENDMENT_PATH,
        "plan": PLAN_PATH,
        "budget": BUDGET_PATH,
        "runner": Path(__file__).resolve(),
        "amendment_note": NOTE_PATH,
        "base_formal_plan": base.PLAN_PATH,
        "base_budget": base.BUDGET_PATH,
        "base_protocol": base.PROTOCOL_PATH,
        "base_release": base.RELEASE_PATH,
        "source_ledger": SOURCE_LEDGER_PATH,
        "source_execution_result": SOURCE_RUN_DIR / "poolside-p4-execution-result.json",
        "source_adaptive_result": adaptive_path,
        "source_metrics": SOURCE_METRICS_PATH,
        "source_diagnostic": SOURCE_DIAGNOSTIC_PATH,
        "source_discovery": discovery_path,
        "latest_key_smoke": SOURCE_SMOKE_PATH,
    }


def verify_original_blocker(diagnostic: dict) -> dict:
    require(SOURCE_LEDGER_PATH.is_file() and SOURCE_METRICS_PATH.is_file()
            and SOURCE_DIAGNOSTIC_PATH.is_file(),
            "The original FPR source evidence is incomplete.")
    events = [json.loads(line) for line in SOURCE_LEDGER_PATH.read_text(
        encoding="utf-8").splitlines()]
    completion = next(event for event in reversed(events)
                      if event.get("unit_id") == SOURCE_UNIT_ID
                      and event.get("event_type") == "attempt_completed")
    require(completion.get("generated_candidate_count") == 10
            and completion.get("budget_complete") is True
            and completion.get("metric_eligible") is True
            and completion.get("system_decision") == "inconclusive",
            "Original A/S12/R2 is not the reviewed complete-but-inconclusive unit.")
    adaptive_path = Path(completion["adaptive_result_path"]).resolve()
    require(adaptive_path.is_relative_to(SOURCE_RUN_DIR.resolve())
            and sha256(adaptive_path) == completion.get("adaptive_result_sha256"),
            "Original adaptive result failed path or ledger hash verification.")
    require(sha256(SOURCE_LEDGER_PATH) == diagnostic["source_integrity"]["execution_ledger_sha256"]
            and sha256(adaptive_path) == diagnostic["source_integrity"]["adaptive_result_sha256"]
            and sha256(SOURCE_METRICS_PATH) == diagnostic["source_integrity"]["val01_metrics_sha256"],
            "Original source evidence no longer matches the published diagnostic hashes.")

    adaptive = read_json(adaptive_path)
    matching = [record for record in adaptive.get("candidate_records", [])
                if record.get("context", {}).get("candidate_id") == EXPECTED["candidate_id"]]
    require(len(matching) == 1, "Expected one candidate-004 record in the original S12/R2 unit.")
    record = matching[0]
    require(all(record["context"].get(key) == value for key, value in EXPECTED.items())
            and record.get("system_claim") == "inconclusive"
            and record.get("evidence_status") == "CONSISTENT_NEGATIVE"
            and {"trial_assessment_evidence_mismatch", "model_claim_evidence_mismatch"}
            <= set(record.get("analysis_warnings", [])),
            "The original candidate no longer matches the approved mismatch signature.")

    loaded = load_runs(SOURCE_RUN_DIR)
    original_run = next((run for run in loaded if run.get("unit_id") == SOURCE_UNIT_ID), None)
    require(original_run is not None and original_run.get("status") == "completed"
            and original_run.get("metric_eligible") is True
            and original_run.get("analysis_summary", {}).get("system_decision") == "inconclusive",
            "The dataset adapter does not confirm the original complete abstention.")

    metrics = read_json(SOURCE_METRICS_PATH)
    withheld = metrics.get("fpr", {}).get("withheld_replicate_detail", {})
    row = next((item for item in metrics.get("fpr", {}).get("condition_replicates", [])
                if item.get("condition_id") == "A" and item.get("replicate") == 2), None)
    require(withheld.get("scenario_id") == "S12" and withheld.get("run_decision") == "inconclusive"
            and not metrics["fpr"]["eligible"] and row is not None
            and row.get("eligible") is False and row.get("fpr") is None,
            "The current frozen VAL-01 metrics no longer show the expected withheld A/R2 FPR.")
    return {
        "source_unit_id": SOURCE_UNIT_ID,
        "original_attempt_id": completion.get("attempt_id"),
        "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
        "source_adaptive_result_sha256": sha256(adaptive_path),
        "original_candidate_count": completion["generated_candidate_count"],
        "original_run_complete": True,
        "original_run_metric_eligible": True,
        "original_system_decision": "inconclusive",
        "original_fpr_a_r2": None,
        "original_fpr_a_eligible": False,
        "original_artifacts_preserved": True,
        "post_result_sensitivity_only": True,
    }


def verify_discovery(plan: dict, base_inputs: dict) -> dict:
    source_plan = base_inputs["plan"]
    expected_path = source_plan["discovery_reports"]["S12"]["2"]
    supplied_path = plan["discovery_reports"]["S12"]["2"]
    require(supplied_path == expected_path,
            "Supplement plan must reuse the exact released S12/R2 discovery report.")
    report_path = ROOT / supplied_path
    report = read_json(report_path)
    metadata = report.get("run_metadata", {})
    generated_text = metadata.get("generated_at")
    require(isinstance(generated_text, str), "S12/R2 discovery report has no generation timestamp.")
    generated = datetime.fromisoformat(generated_text.replace("Z", "+00:00")).astimezone(timezone.utc)
    age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
    require(metadata.get("authentication_status") == "verified"
            and metadata.get("target_origin") == "http://dvwa"
            and report.get("summary", {}).get("verified_injection_point_count") == 2
            and 0 <= age_hours <= base.MAX_DISCOVERY_AGE_HOURS,
            "S12/R2 discovery is not authenticated, complete, or fresh enough for a formal attempt.")
    return {"path": supplied_path, "sha256": sha256(report_path),
            "age_hours": round(age_hours, 4), "authenticated": True,
            "verified_injection_point_count": 2}


def prepare() -> tuple[dict, dict, dict, dict]:
    amendment = read_json(AMENDMENT_PATH)
    plan = read_json(PLAN_PATH)
    budget = read_json(BUDGET_PATH)
    package = read_json(PACKAGE_PATH)
    require(amendment.get("schema") == "poolside-laguna-p4-fpr-targeted-amendment-draft-v1"
            and amendment.get("amendment_id") == AMENDMENT_ID
            and amendment.get("status") == "draft-needs-methodological-approval-not-executable",
            "Unknown or unexpectedly promoted amendment state.")
    require(package.get("schema") == "poolside-laguna-p4-a-s12-r2-amendment-package-v1"
            and package.get("status") == "draft-awaiting-methodological-approval-and-separate-approvals"
            and package.get("formal_execution_authorized") is False,
            "Amendment package status must remain fail-closed.")
    require(package.get("sensitivity_only") is True
            and package.get("frozen_primary_result_changes") is False,
            "Package must preserve the frozen primary result and label the supplement sensitivity-only.")

    artifacts = source_artifacts()
    expected_artifacts = package.get("artifact_sha256", {})
    require(set(expected_artifacts) == set(artifacts),
            "Package artifact hash list does not match the runner's source inventory.")
    for label, path in artifacts.items():
        expected = expected_artifacts.get(label)
        require(path.is_file() and expected == sha256(path),
                f"Package hash mismatch for {label}.")

    base_inputs = base.verify_plan_inputs(require_frozen=True)
    require(sha256(base.RELEASE_PATH) == amendment["source"]["frozen_release_sha256"]
            and sha256(base.PLAN_PATH) == amendment["source"]["frozen_formal_plan_sha256"]
            and sha256(base.BUDGET_PATH) == amendment["source"]["frozen_budget_sha256"]
            and sha256(base.PROTOCOL_PATH) == amendment["source"]["frozen_protocol_sha256"]
            and base.protocol_candidate_sha256(base_inputs["protocol"])
            == amendment["source"]["frozen_protocol_candidate_sha256"],
            "Supplement no longer binds the frozen Recovery1 P4 source release.")

    require(plan.get("schema_version") == "1.0.0"
            and plan.get("experiment_id") == SUPPLEMENT_EXPERIMENT_ID
            and plan.get("dataset") == "formal"
            and plan.get("condition_ids") == ["A"]
            and plan.get("scenario_ids") == ["S12"]
            and plan.get("replicates") == [2]
            and plan.get("seclists_source_root") is None,
            "Supplement plan must contain only A/S12/R2.")
    Draft202012Validator(read_json(PLAN_SCHEMA_PATH)).validate(plan)
    discovered = verify_discovery(plan, base_inputs)
    protocol = base_inputs["protocol"]
    resolved = base.engine.local_runner.validate_plan(plan, protocol, ROOT, verify_index=False)
    slots = base.engine.local_runner.planned_units(resolved, protocol, ROOT)
    require(len(slots) == 1 and slots[0].get("status") == "planned"
            and (slots[0].get("condition_id"), slots[0].get("scenario_id"),
                 slots[0].get("replicate")) == ("A", "S12", 2)
            and base.engine.estimate_api_calls(resolved, protocol) == 40,
            "Resolved plan did not produce exactly one A/S12/R2 unit with 40 maximum API calls.")

    require(budget.get("schema") == "poolside-laguna-p4-targeted-sensitivity-budget-v1"
            and budget.get("status") == "draft-not-frozen-not-executable"
            and budget.get("amendment_sha256") == sha256(AMENDMENT_PATH)
            and budget.get("plan_sha256") == sha256(PLAN_PATH)
            and budget.get("source_release_sha256") == sha256(base.RELEASE_PATH)
            and budget.get("source_formal_plan_sha256") == sha256(base.PLAN_PATH)
            and budget.get("source_protocol_sha256") == sha256(base.PROTOCOL_PATH)
            and budget.get("source_protocol_candidate_sha256")
            == base.protocol_candidate_sha256(protocol),
            "Supplement budget does not bind the amendment, plan, and frozen source inputs.")
    ceilings = budget.get("hard_ceilings", {})
    require(budget.get("scope", {}).get("condition_ids") == ["A"]
            and budget["scope"].get("scenario_ids") == ["S12"]
            and budget["scope"].get("replicates") == [2]
            and budget["scope"].get("applicable_units") == 1
            and budget["scope"].get("candidate_budget") == 10
            and ceilings.get("api_call_ceiling") == 40
            and ceilings.get("generation_requests_ceiling") == 30
            and ceilings.get("analysis_requests_ceiling") == 10
            and ceilings.get("completion_token_ceiling") == 51200
            and ceilings.get("api_wall_time_ceiling_seconds") == 2700
            and ceilings.get("automatic_transport_retries") == 0
            and ceilings.get("automatic_unit_replacements") == 0
            and ceilings.get("model_fallback") is False
            and budget.get("spend", {}).get("maximum_spend_usd") == 0
            and budget.get("provider_model", {}).get("provider") == "direct Poolside API only"
            and budget["provider_model"].get("model") == base.transport.MODEL
            and budget["provider_model"].get("openrouter_allowed") is False,
            "Budget does not enforce the one-unit direct-provider USD 0 ceilings.")
    require(sha256(SOURCE_SMOKE_PATH) == budget["provider_model"]["latest_key_smoke_sha256"],
            "Latest replacement-key smoke no longer matches the budget receipt.")
    smoke = read_json(SOURCE_SMOKE_PATH)
    require(smoke.get("status") == "ok"
            and smoke.get("reported_model") == base.transport.MODEL
            and smoke.get("requested_model") == base.transport.MODEL
            and smoke.get("base_url") == base.transport.BASE_URL
            and smoke.get("automatic_retries") == 0
            and smoke.get("model_fallback") is False,
            "Latest replacement-key smoke is not a successful direct Poolside smoke.")

    diagnostic = read_json(SOURCE_DIAGNOSTIC_PATH)
    source_summary = verify_original_blocker(diagnostic)
    require(diagnostic.get("source_integrity", {}).get("execution_ledger_sha256")
            == amendment["source"]["source_execution_ledger_sha256"]
            and diagnostic.get("source_integrity", {}).get("adaptive_result_sha256")
            == amendment["source"]["source_adaptive_result_sha256"]
            and diagnostic.get("source_integrity", {}).get("val01_metrics_sha256")
            == amendment["source"]["current_val01_metrics_sha256"],
            "Amendment source binding differs from the published blocker diagnostic.")
    require(not SUPPLEMENT_OUTPUT.exists(),
            "Supplement output already exists; refusing to overwrite or repeat the unit.")

    method_present = METHOD_APPROVAL_PATH.is_file()
    freeze_present = FREEZE_APPROVAL_PATH.is_file()
    execution_present = EXECUTION_APPROVAL_PATH.is_file()
    return amendment, resolved, protocol, {
        "budget": budget,
        "package": package,
        "base_inputs": base_inputs,
        "slots": slots,
        "source_summary": source_summary,
        "discovery": discovered,
        "method_approval_present": method_present,
        "freeze_approval_present": freeze_present,
        "execution_approval_present": execution_present,
    }


def dry_run() -> dict:
    amendment, plan, protocol, checked = prepare()
    budget = checked["budget"]
    return {
        "schema": "poolside-laguna-p4-a-s12-r2-amendment-readiness-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ready-for-methodological-review",
        "amendment_id": amendment["amendment_id"],
        "package_sha256": sha256(PACKAGE_PATH),
        "amendment_sha256": sha256(AMENDMENT_PATH),
        "plan_sha256": sha256(PLAN_PATH),
        "budget_sha256": sha256(BUDGET_PATH),
        "source_protocol_sha256": sha256(base.PROTOCOL_PATH),
        "source_release_sha256": sha256(base.RELEASE_PATH),
        "source_unit": checked["source_summary"],
        "planned_unit": {"condition_id": "A", "scenario_id": "S12", "replicate": 2,
                         "candidate_budget": 10},
        "discovery": checked["discovery"],
        "provider": budget["provider_model"],
        "api_call_ceiling": budget["hard_ceilings"]["api_call_ceiling"],
        "completion_token_ceiling": budget["hard_ceilings"]["completion_token_ceiling"],
        "maximum_spend_usd": budget["spend"]["maximum_spend_usd"],
        "planned_database_resets": 1,
        "output_path": relative(SUPPLEMENT_OUTPUT),
        "sensitivity_only": True,
        "frozen_primary_result_changes": False,
        "approval_state": {
            "methodological": "present-needs-validated-receipt" if checked["method_approval_present"] else "pending",
            "amendment_freeze": "present-needs-validation" if checked["freeze_approval_present"] else "pending",
            "formal_execution": "present-needs-validation" if checked["execution_approval_present"] else "pending",
        },
        "execution_authorized": False,
        "execution_started": False,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "credentials_read": False,
        "database_resets": 0,
        "openrouter_used": False,
        "gates": {
            "original-complete-abstention-hash-verified": "passed",
            "frozen-p4-source-release-and-runtime": "passed",
            "one-unit-a-s12-r2-plan": "passed",
            "fresh-authenticated-s12-r2-discovery": "passed",
            "zero-spend-bounded-budget": "passed",
            "current-key-direct-provider-smoke": "passed",
            "post-result-methodological-approval": "pending",
            "separate-amendment-freeze-approval": "pending",
            "separate-formal-execution-approval": "pending",
        },
    }


def validate_approval(path: Path, *, kind: str, package_hash: str) -> dict:
    receipt = read_json(path)
    common = {
        "package_sha256": package_hash,
        "amendment_sha256": sha256(AMENDMENT_PATH),
        "plan_sha256": sha256(PLAN_PATH),
        "budget_sha256": sha256(BUDGET_PATH),
        "source_protocol_sha256": sha256(base.PROTOCOL_PATH),
        "sensitivity_only": True,
        "frozen_primary_result_changes": False,
    }
    if any(receipt.get(key) != value for key, value in common.items()):
        raise ValueError(f"{kind} receipt does not bind the exact sensitivity package.")
    if kind == "method":
        if (receipt.get("schema") != "poolside-laguna-p4-a-s12-r2-method-approval-v1"
                or receipt.get("decision") != "approved-for-amended-sensitivity-analysis"
                or receipt.get("original_complete_run_excluded_only_from_sensitivity") is not True):
            raise ValueError("Explicit researcher and adviser approval of the post-result sensitivity treatment is missing.")
        if (receipt.get("researcher", {}).get("decision") != "approved"
                or receipt.get("adviser", {}).get("decision") != "approved"):
            raise ValueError("Both researcher and adviser methodological approval are required.")
    elif kind == "freeze":
        if (receipt.get("schema") != "poolside-laguna-p4-a-s12-r2-freeze-approval-v1"
                or receipt.get("decision") != "approved-for-p4-a-s12-r2-amendment-freeze"
                or receipt.get("formal_amendment_freeze") is not True
                or receipt.get("formal_execution_approval") is not False
                or receipt.get("method_approval_sha256") != sha256(METHOD_APPROVAL_PATH)):
            raise ValueError("Separate hash-bound amendment-freeze approval is missing or invalid.")
    else:
        if (receipt.get("schema") != "poolside-laguna-p4-a-s12-r2-execution-approval-v1"
                or receipt.get("decision") != "approved-for-p4-a-s12-r2-formal-execution"
                or receipt.get("formal_execution_approval") is not True
                or receipt.get("maximum_spend_usd") != 0
                or receipt.get("method_approval_sha256") != sha256(METHOD_APPROVAL_PATH)
                or receipt.get("freeze_approval_sha256") != sha256(FREEZE_APPROVAL_PATH)):
            raise ValueError("Separate hash-bound formal-execution approval is missing or invalid.")
        scope = receipt.get("unit_scope", {})
        if scope != {"condition_id": "A", "scenario_id": "S12", "replicate": 2,
                     "database_resets": 1, "candidate_budget": 10}:
            raise ValueError("Execution approval scope differs from the one-unit A/S12/R2 plan.")
        ceilings = read_json(BUDGET_PATH)["hard_ceilings"]
        if (receipt.get("api_call_ceiling") != ceilings["api_call_ceiling"]
                or receipt.get("completion_token_ceiling") != ceilings["completion_token_ceiling"]
                or receipt.get("output_path") != relative(SUPPLEMENT_OUTPUT)):
            raise ValueError("Execution approval ceilings or output path differ from the budget.")
        if any(receipt.get(key) is not True for key in
               ("confirm_local_dvwa", "confirm_database_reset", "confirm_zero_spend")):
            raise ValueError("Execution receipt must explicitly authorize loopback DVWA, one reset, and USD 0.")
    authority = receipt.get("authority", {})
    if (authority.get("role") != "researcher"
            or authority.get("basis") != "explicit-user-approval"
            or not authority.get("approved_at_local")
            or not authority.get("quote")):
        raise ValueError(f"{kind} receipt lacks explicit researcher authority.")
    return receipt


def execute(*, confirm_local_dvwa: bool, confirm_database_reset: bool,
            confirm_zero_spend: bool) -> dict:
    amendment, plan, protocol, checked = prepare()
    package_hash = sha256(PACKAGE_PATH)
    validate_approval(METHOD_APPROVAL_PATH, kind="method", package_hash=package_hash)
    validate_approval(FREEZE_APPROVAL_PATH, kind="freeze", package_hash=package_hash)
    validate_approval(EXECUTION_APPROVAL_PATH, kind="execution", package_hash=package_hash)
    if not (confirm_local_dvwa and confirm_database_reset and confirm_zero_spend):
        raise ValueError("Execution requires explicit loopback-DVWA, one-reset, and USD 0 flags.")
    api_key = base.transport.load_key()
    if not api_key:
        raise ValueError("No direct Poolside API key is configured in the local environment.")
    base.engine.local_runner.require_local_target(protocol["target_origin"])
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    clean_plan = {key: value for key, value in plan.items() if not key.endswith("_resolved")}
    plan_hash = hashlib.sha256(base.engine.canonical_json(clean_plan)).hexdigest()
    protocol_hash = sha256(base.PROTOCOL_PATH)
    authorization = {
        "scope": "poolside-p4-a-s12-r2-amended-sensitivity-execution",
        "amendment_id": amendment["amendment_id"],
        "amendment_package_sha256": package_hash,
        "method_approval_sha256": sha256(METHOD_APPROVAL_PATH),
        "freeze_approval_sha256": sha256(FREEZE_APPROVAL_PATH),
        "execution_approval_path": relative(EXECUTION_APPROVAL_PATH),
        "execution_approval_sha256": sha256(EXECUTION_APPROVAL_PATH),
        "maximum_spend_usd": 0,
        "formal_execution_approval": True,
        "sensitivity_only": True,
        "frozen_primary_result_changes": False,
    }
    ledger = base.engine.local_runner.ExperimentLedger.create(
        SUPPLEMENT_OUTPUT, plan, protocol, plan_hash, protocol_hash, ROOT,
        formal_execution_authorization=authorization)
    base.write_new(SUPPLEMENT_OUTPUT / "poolside-p4-a-s12-r2-amendment-runtime.snapshot.json", {
        "amendment_id": amendment["amendment_id"], "package_sha256": package_hash,
        "amendment_sha256": sha256(AMENDMENT_PATH), "plan_sha256": sha256(PLAN_PATH),
        "budget_sha256": sha256(BUDGET_PATH), "source_release_sha256": sha256(base.RELEASE_PATH),
        "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
        "source_adaptive_result_sha256": checked["source_summary"]["source_adaptive_result_sha256"],
        "source_diagnostic_sha256": sha256(SOURCE_DIAGNOSTIC_PATH),
        "execution_approval_sha256": authorization["execution_approval_sha256"],
        "runtime_source_sha256": checked["base_inputs"]["runtime_hashes"],
        "api_base_url": base.transport.BASE_URL, "model": base.transport.MODEL,
        "api_call_ceiling": checked["budget"]["hard_ceilings"]["api_call_ceiling"],
        "completion_token_ceiling": checked["budget"]["hard_ceilings"]["completion_token_ceiling"],
        "maximum_spend_usd": 0, "openrouter_used": False,
        "sensitivity_only": True, "frozen_primary_result_changes": False,
    })
    for source_name in checked["base_inputs"]["runtime_hashes"]:
        source = ROOT / source_name
        target = SUPPLEMENT_OUTPUT / "source" / source_name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(source.read_bytes())

    ceiling = checked["budget"]["hard_ceilings"]
    api = base.CompletionBudgetPoolsideAPI(
        api_key, SUPPLEMENT_OUTPUT, max_calls=ceiling["api_call_ceiling"],
        max_seconds=ceiling["api_wall_time_ceiling_seconds"],
        max_completion_tokens=ceiling["completion_token_ceiling"],
    )
    config = {"limits": {"max_total_api_calls": ceiling["api_call_ceiling"],
                         "max_retrieved_chars_per_chunk": 1800}}

    def execute_one(unit, attempt, active_plan, active_protocol, data_dir, root):
        api.require_time()
        print(json.dumps({"event": "unit-start", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "replicate": unit["replicate"],
                          "api_calls": api.used_calls}, ensure_ascii=False), flush=True)
        return base._execute_one(unit, attempt, active_plan, active_protocol,
                                 data_dir, api, config)

    with base.p4_callbacks(), base.engine.local_runner.experiment_lock(SUPPLEMENT_OUTPUT):
        result = base.engine.local_runner.execute_ledger(
            ledger, plan, protocol, SUPPLEMENT_OUTPUT, execute=True,
            retry_invalid=False, recovered=0, root=ROOT, execute_one=execute_one)
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result_path in SUPPLEMENT_OUTPUT.glob("attempts/**/api-calls/*/result.json"):
        current = read_json(result_path).get("result", {}).get("usage") or {}
        for key in usage:
            if type(current.get(key)) is int:
                usage[key] += current[key]
    summary = {
        **result, "amendment_id": amendment["amendment_id"],
        "source_unit_id": SOURCE_UNIT_ID,
        "source_system_decision": "inconclusive",
        "protocol_id": protocol["protocol_id"], "model": base.transport.MODEL,
        "api_calls_used": api.used_calls, "api_call_ceiling": ceiling["api_call_ceiling"],
        "completion_tokens_used": api.completion_tokens_reserved,
        "completion_token_ceiling": ceiling["completion_token_ceiling"],
        "usage_totals": usage, "execution_started": True,
        "openrouter_used": False, "maximum_spend_usd": 0,
        "sensitivity_only": True, "frozen_primary_result_changes": False,
    }
    result_path = SUPPLEMENT_OUTPUT / "poolside-p4-a-s12-r2-amendment-result.json"
    if not result_path.exists():
        base.write_new(result_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true",
                       help="Validate the amendment offline without credentials, API, or DVWA access")
    modes.add_argument("--execute", action="store_true",
                       help="Run only after separate method, freeze, and execution approvals exist")
    parser.add_argument("--output", type=Path, help="Write dry-run evidence inside this project")
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    parser.add_argument("--confirm-zero-spend", action="store_true")
    args = parser.parse_args()
    try:
        if args.execute:
            if args.output:
                parser.error("--output is only available for dry-run evidence.")
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
        if args.execute:
            return 0
        return 0 if result.get("status") == "ready-for-methodological-review" else 2
    except (OSError, ValueError, KeyError, TypeError) as failure:
        print(json.dumps({
            "status": "blocked",
            "error_type": type(failure).__name__,
            "message": str(failure),
            "execution_attempted": bool(args.execute),
            "api_requests_sent": 0 if not args.execute else "inspect supplemental ledger",
            "dvwa_requests_sent": 0 if not args.execute else "inspect supplemental validation logs",
            "credentials_read": False if not args.execute else "inspect execution stage",
            "database_resets": 0 if not args.execute else "inspect supplemental ledger",
            "openrouter_used": False,
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
