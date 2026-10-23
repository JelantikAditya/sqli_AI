"""Prepare a fail-closed Poolside Laguna P4 plan and run an offline dry-run.

This utility never reads credentials, makes HTTP requests, or contacts DVWA.
The dry-run reports readiness only; it cannot authorize formal execution.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "poolside-laguna-p4-20261023"
PLAN_PATH = ROOT / "development/poolside_laguna_p4_plan_20261023.json"
BUDGET_PATH = ROOT / "development/poolside_laguna_p4_budget_20261023.json"
FORMAL_PLAN_PATH = ROOT / "development/poolside_laguna_p4_formal_plan_20261023.json"
PROTOCOL_PATH = ROOT / "development/poolside_laguna_p4_protocol_20261023.json"
Q4_AUDIT_PATH = ROOT / "docs/evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json"
Q4_BUDGET_PATH = ROOT / "development/poolside_laguna_qualification_budget_20261023_q4_v5.json"
METHOD_DECISION_PATH = ROOT / "docs/evidence/poolside-laguna-p4-method-decision-2026-10-23.json"
POOLSIDE_SMOKE_ROOT = ROOT / "results/raw/poolside-smoke"
APPROVED_PLAN_PATH = ROOT / "dvwa/local_run_plan.formal-20261017-approved-index.json"
CORPUS_DECISION_PATH = ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json"
ACTIVE_PROTOCOL_PATH = ROOT / "dvwa/local_experiment_protocol.json"
ARCHIVE_ROOT = ROOT / "results/raw/formal/formal-sqli-v1-20261017/index-recovery/approved-snapshot"
ACTIVE_STORE_ROOT = ROOT / "data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3"
DISCOVERY_ROOT = ROOT / "results/raw/formal-discovery/formal-sqli-v1-20261017"
P4_DISCOVERY_ROOT = ROOT / "results/raw/formal-discovery/poolside-laguna-p4-20261023"
SNAPSHOT_CHECK_PATH = ROOT / "docs/evidence/poolside-laguna-p4-snapshot-check-2026-10-23.json"
RUNNER_READINESS_PATH = ROOT / "docs/evidence/poolside-laguna-p4-runner-readiness-2026-10-23.json"
P4_PREFLIGHT_PATH = ROOT / "docs/evidence/poolside-laguna-p4-dvwa-preflight-2026-10-23.json"
DISCOVERY_REVIEW_PATH = ROOT / "docs/evidence/poolside-laguna-p4-discovery-review-2026-10-23.json"
PROVIDER_CONFIRMATION_PATH = ROOT / "docs/evidence/poolside-laguna-p4-provider-confirmation-2026-10-23.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protocol_candidate_sha256(protocol: dict) -> str:
    """Hash protocol content while ignoring its draft/frozen lifecycle marker."""
    candidate = copy.deepcopy(protocol)
    candidate["status"] = "draft"
    candidate.pop("freeze_candidate_sha256", None)
    payload = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def provider_confirmation_valid(budget: dict) -> bool:
    """Validate the researcher's account assurance against current pinned evidence."""
    try:
        receipt = read_json(PROVIDER_CONFIRMATION_PATH)
        limits = budget.get("spend_and_provider_limits", {})
        smoke = limits.get("current_account_smoke", {})
        smoke_path = (ROOT / receipt["smoke_report_path"]).resolve()
        return (
            smoke_path.is_relative_to(ROOT.resolve())
            and receipt.get("schema") == "poolside-laguna-p4-provider-confirmation-v1"
            and receipt.get("experiment_id") == EXPERIMENT_ID
            and receipt.get("status") == "researcher-confirmed"
            and receipt.get("account", {}).get("new_poolside_account_reported") is True
            and receipt.get("account", {}).get("new_api_key_configured") is True
            and receipt.get("account", {}).get("key_value_recorded") is False
            and receipt.get("provider_readiness", {}).get("free_access_currently_verified_by_smoke") is True
            and receipt.get("provider_readiness", {}).get("account_quota_and_rate_limit_sufficient_for_formal_run") is True
            and receipt.get("provider_readiness", {}).get("formal_laguna_api_run_confirmed_safe_by_researcher") is True
            and receipt.get("provider_readiness", {}).get("poolside_shutdown_notice_acknowledged") is True
            and receipt.get("formal_runner_plan_sha256") == sha256(FORMAL_PLAN_PATH)
            and receipt.get("protocol_candidate_sha256") == protocol_candidate_sha256(read_json(PROTOCOL_PATH))
            and receipt.get("smoke_report_sha256") == smoke.get("report_sha256")
            and smoke_path == (ROOT / smoke.get("report_path", "")).resolve()
            and sha256(smoke_path) == receipt.get("smoke_report_sha256")
            and smoke.get("free_status_verified") is True
            and limits.get("researcher_confirmation_receipt_path") == relative(PROVIDER_CONFIRMATION_PATH)
            and limits.get("researcher_confirmation_receipt_sha256") == sha256(PROVIDER_CONFIRMATION_PATH)
            and receipt.get("protocol_freeze_approved") is False
            and receipt.get("formal_execution_approved") is False
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as source:
        return json.load(source)


def write_json_new(path: Path, value: dict) -> None:
    """Create a new artifact without silently replacing an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(payload)


def write_json_replace(path: Path, value: dict) -> None:
    """Atomically refresh only the two P4 draft artifacts after identity checks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def build_plan() -> dict:
    approved_plan = read_json(APPROVED_PLAN_PATH)
    decision = read_json(CORPUS_DECISION_PATH)
    protocol = read_json(ACTIVE_PROTOCOL_PATH)
    q4_audit = read_json(Q4_AUDIT_PATH)
    q4_budget = read_json(Q4_BUDGET_PATH)
    method_decision = read_json(METHOD_DECISION_PATH)
    q4_run_root = ROOT / "results/raw/pilot/poolside-s21-p3-q4-v5-20261023"
    q4_result_paths = sorted(q4_run_root.glob("attempts/*/attempt-*/api-calls/*/result.json"))
    if not q4_result_paths:
        raise ValueError("Q4 generation response evidence is missing.")
    q4_sample_response_path = q4_result_paths[0]
    q4_reported_models = {}
    q4_result_statuses = {}
    for result_path in q4_result_paths:
        result = read_json(result_path).get("result", {})
        model = result.get("reported_model") or "missing"
        status = result.get("status") or "missing"
        q4_reported_models[model] = q4_reported_models.get(model, 0) + 1
        q4_result_statuses[status] = q4_result_statuses.get(status, 0) + 1

    discovery_reports = []
    expected_levels = {"low": "S1-S3", "medium": "S4-S6",
                       "high": "S7-S9", "impossible": "S10-S12"}
    p4_discovery_complete = all(
        (P4_DISCOVERY_ROOT / f"replicate-{replicate}" / level / "zap-discovery.normalized.json").is_file()
        for replicate in (1, 2, 3) for level in expected_levels
    )
    today = datetime.now(timezone.utc).date()
    for replicate in (1, 2, 3):
        for level, scenarios in expected_levels.items():
            p4_path = P4_DISCOVERY_ROOT / f"replicate-{replicate}" / f"{level}" / "zap-discovery.normalized.json"
            path = p4_path if p4_discovery_complete else (
                DISCOVERY_ROOT / f"replicate-{replicate}" / f"zap-discovery-{level}.normalized.json"
            )
            report = read_json(path)
            metadata = report.get("run_metadata", {})
            discovery_reports.append({
                "replicate": replicate,
                "level": level,
                "scenario_ids": scenarios,
                "path": relative(path),
                "sha256": sha256(path),
                "generated_at": metadata.get("generated_at"),
                "age_days_at_preparation": (today - datetime.fromisoformat(
                    metadata["generated_at"].replace("Z", "+00:00")).date()).days,
                "target_origin_in_report": metadata.get("target_origin"),
                "authentication_status": metadata.get("authentication_status"),
                "verified_injection_point_count": report.get("summary", {}).get(
                    "verified_injection_point_count"),
                "out_of_level_sqli_input_observation_count": report.get("summary", {}).get(
                    "out_of_level_sqli_input_observation_count"),
                "p4_use": "fresh P4 discovery" if p4_discovery_complete else "reference-only; refresh and bind to current target before execution",
            })

    approved_hashes = approved_plan["knowledge_snapshot"]["index_file_sha256"]
    archive_hashes = {}
    active_comparison = {}
    for original_path, expected_hash in approved_hashes.items():
        archive_file = ARCHIVE_ROOT / original_path
        active_file = ROOT / original_path
        archive_observed = sha256(archive_file) if archive_file.is_file() else None
        active_observed = sha256(active_file) if active_file.is_file() else None
        archive_hashes[original_path] = {
            "expected_sha256": expected_hash,
            "archive_sha256": archive_observed,
            "matches_approved": archive_observed == expected_hash,
            "archive_path": relative(archive_file),
        }
        active_comparison[original_path] = {
            "expected_sha256": expected_hash,
            "active_sha256": active_observed,
            "matches_approved": active_observed == expected_hash,
        }

    runtime_paths = [
        "development/poolside_laguna_generation_v5.py",
        "development/run_bounded_poolside_qualification_v5.py",
        "development/run_bounded_poolside_qualification_v3.py",
        "development/run_poolside_laguna_p4.py",
        "development/capture_poolside_laguna_p4_discovery.py",
        "development/preflight_poolside_laguna_p4_dvwa.py",
        "development/review_poolside_laguna_p4_discovery.py",
        "development/poolside_completion_budget.py",
        "development/prepare_poolside_laguna_p4.py",
        "development/poolside_p3_runtime.py",
        "development/run_poolside_contract_smoke.py",
        "development/run_poolside_generation_preflight.py",
        "development/run_poolside_smoke.py",
        "development/qwen_api_p2_analysis.py",
        "development/run_qwen_api_experiments.py",
        "dvwa/run_local_experiments.py",
        "dvwa/local_experiment_protocol.json",
        "dvwa/experiment_scenarios.json",
        "dvwa/compose.yaml",
        "dvwa/zap-auth.template.yaml",
        "dvwa/rag_pipeline.py",
        "dvwa/retrieve_structured_knowledge.py",
        "dvwa/analyze_response.py",
        "dvwa/validation_loop.py",
        "dvwa/confirmation_policy.py",
        "dvwa/execution_order_policy.py",
        "requirements-formal-2026-10-17.lock.txt",
        "schemas/local-run-plan.schema.json",
        "schemas/formal-execution-approval.schema.json",
    ]
    runtime_hashes = {path: sha256(ROOT / path) for path in runtime_paths}

    q4_usage = q4_audit["api_responses"]["usage_total"]
    plan = {
        "schema": "poolside-laguna-formal-plan-draft-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "draft-blocked-not-frozen",
        "dataset": "separate-formal-cohort-primary-model-in-revised-analysis",
        "user_direction": {
            "provider": "direct Poolside API",
            "model": "poolside/laguna-s-2.1",
            "openrouter": "deferred; not part of this plan",
        },
        "provider": {
            "base_url": "https://inference.poolside.ai/v1",
            "requested_model": "poolside/laguna-s-2.1",
            "reported_model_evidence": {
                "response_file_count": len(q4_result_paths),
                "reported_model_counts": q4_reported_models,
                "result_status_counts": q4_result_statuses,
                "path": relative(q4_sample_response_path),
                "sha256": sha256(q4_sample_response_path),
            },
            "credential_source": "local environment or .env.poolside.local; never read by this preparation utility",
            "model_fallback": False,
            "transport_retries": 0,
        },
        "method_amendment": {
            "path": "docs/usulan-amendemen-metode-poolside-laguna-p4-2026-10-23.md",
            "sha256": sha256(ROOT / "docs/usulan-amendemen-metode-poolside-laguna-p4-2026-10-23.md"),
            "status": "researcher-decision-recorded; adviser-approval-reported-by-researcher",
            "decision_receipt_path": relative(METHOD_DECISION_PATH),
            "decision_receipt_sha256": sha256(METHOD_DECISION_PATH),
            "cohort_role": method_decision["researcher_decision"]["cohort_role"],
            "local_qwen_data_policy": method_decision["researcher_decision"]["local_qwen_data_policy"],
            "proposal_update_timing": method_decision["researcher_decision"]["proposal_update_timing"],
            "proposal_update_reason": method_decision["researcher_decision"]["proposal_update_reason"],
            "protocol_freeze_or_execution_approval": False,
        },
        "method_decision": {
            "decision_id": method_decision["decision_id"],
            "decision": method_decision["decision"],
            "cohort_role": method_decision["researcher_decision"]["cohort_role"],
            "cohort_relationship": method_decision["researcher_decision"]["cohort_relationship"],
            "local_qwen_data_policy": method_decision["researcher_decision"]["local_qwen_data_policy"],
            "adviser_approval_status": method_decision["adviser_approval"]["status"],
            "direct_adviser_receipt_present": method_decision["adviser_approval"]["direct_adviser_receipt_present"],
            "proposal_update_timing": method_decision["researcher_decision"]["proposal_update_timing"],
            "proposal_update_reason": method_decision["researcher_decision"]["proposal_update_reason"],
            "protocol_frozen": method_decision["formal_protocol_frozen"],
            "formal_execution_approval": method_decision["formal_execution_approval"],
        },
        "design": {
            "target": protocol["target_origin"],
            "method": "DAST black-box SQL injection on local DVWA",
            "techniques": ["error-based", "boolean-based blind", "time-based blind"],
            "security_levels": ["low", "medium", "high", "impossible"],
            "conditions": {
                "A": {"source": "Poolside Laguna API", "rag_mode": "off", "scenario_ids": [f"S{i}" for i in range(1, 13)]},
                "B": {"source": "Poolside Laguna API", "rag_mode": "on", "scenario_ids": [f"S{i}" for i in range(1, 13)]},
                "C": {"source": "SecLists", "rag_mode": "not_applicable", "scenario_ids": [f"S{i}" for i in range(1, 10)]},
            },
            "replicates": [1, 2, 3],
            "candidate_budget_per_applicable_unit": 10,
            "confirmations_per_candidate": 3,
            "counts": {
                "ab_api_units": 72,
                "c_seclists_units": 27,
                "applicable_units": 99,
                "ab_candidates": 720,
                "c_candidates": 270,
                "total_candidates": 990,
                "logical_confirmations": 2970,
                "excluded_c_slots": 9,
            },
            "primary_metrics": {"fpr": "condition A versus B, per applicable run", "psr": "conditions B and C, candidate-level"},
        },
        "generation_profile": {
            "generation_prompt_version": "poolside-laguna-sqli-generation-v5-explicit-structure-feedback",
            "generation_retry_policy_id": "poolside-unit-wide-unseen-family-structure-feedback-v5",
            "api_call_retry_policy_id": "poolside-family-fallback-and-format-feedback-v2",
            "retrieval_context_policy_id": "structured-chunks-remove-payload-examples-v1",
            "analysis_prompt_version": "qwen38-api-p2-explicit-evidence-v1",
            "temperature": 0,
            "thinking": False,
            "generation_max_tokens": 1024,
            "analysis_max_tokens": 2048,
            "replicate_seed": "not sent by direct Poolside adapter; report hosted nondeterminism",
            "runtime_source_sha256": runtime_hashes,
        },
        "discovery_reports": discovery_reports,
        "discovery_requirements": {
            "expected_report_count": 12,
            "refresh_policy": "fresh for each replicate and security level",
            "existing_reports_are_execution_eligible": False,
            "report_target_origin_mapping_required": True,
            "manual_review_required_for_out_of_level_observations": True,
        },
        "knowledge_snapshot": {
            "corpus_sha256": approved_plan["knowledge_snapshot"]["corpus_sha256"],
            "source_lock_sha256": approved_plan["knowledge_snapshot"]["source_lock_sha256"],
            "review_decision_path": relative(CORPUS_DECISION_PATH),
            "review_decision_sha256": sha256(CORPUS_DECISION_PATH),
            "review_decision": decision.get("decision"),
            "formal_execution_approval_in_receipt": decision.get("formal_execution_approval"),
            "approved_archive_root": relative(ARCHIVE_ROOT),
            "archive_file_hashes": archive_hashes,
            "active_store_comparison": active_comparison,
            "active_store_may_be_overwritten": False,
            "required_p4_execution_mode": "isolated verified snapshot or runner with an explicit read-only store path",
        },
        "protocol_reference": {
            "legacy_protocol_path": relative(ACTIVE_PROTOCOL_PATH),
            "legacy_protocol_sha256": sha256(ACTIVE_PROTOCOL_PATH),
            "legacy_protocol_model": protocol.get("generation", {}).get("model"),
            "legacy_protocol_status": protocol.get("status"),
            "reused_as_p4_approval": False,
        },
        "execution_authorized": False,
        "execution_approval_receipt": None,
        "runner_status": "P4 fail-closed runner implemented; execution remains closed pending protocol freeze, release, and hash-bound execution approval",
        "preparation_side_effects": {"api_requests": 0, "dvwa_requests": 0, "credentials_read": False, "openrouter_used": False},
    }
    return plan


def build_formal_runner_plan() -> dict:
    """Create a separate standard-ledger plan without editing the frozen Qwen plan."""
    plan = read_json(APPROVED_PLAN_PATH)
    plan["experiment_id"] = EXPERIMENT_ID
    plan["dataset"] = "formal"
    summary_reports = build_plan().get("discovery_reports", [])
    for item in summary_reports:
        first, last = (int(value.removeprefix("S")) for value in item["scenario_ids"].split("-"))
        for number in range(first, last + 1):
            scenario_id = f"S{number}"
            plan["discovery_reports"].setdefault(scenario_id, {})[str(item["replicate"])] = item["path"]
    return plan


def build_protocol() -> dict:
    """Create an unfrozen P4 protocol candidate derived without editing local Qwen."""
    protocol = read_json(ACTIVE_PROTOCOL_PATH)
    protocol["protocol_id"] = "poolside-laguna-p4-formal-v1"
    protocol["status"] = "draft"
    protocol.pop("formal_freeze_release", None)
    protocol["generation"].update(model="poolside/laguna-s-2.1", num_predict=1024)
    protocol["methodology"].update(
        decision_id="poolside-laguna-p4-revised-formal-v1",
        execution_topology="local-dvwa-and-direct-poolside-hosted-inference",
        llm_pipeline_framework="custom-serial-checkpointed-api-adapter",
        model_transport="poolside-direct-openai-compatible-chat-api",
        api_base_url="https://inference.poolside.ai/v1",
        api_model_id="poolside/laguna-s-2.1",
        api_generation_prompt_version="poolside-laguna-sqli-generation-v5-explicit-structure-feedback",
        api_generation_retry_policy_id="poolside-unit-wide-unseen-family-structure-feedback-v5",
        api_analysis_prompt_version="qwen38-api-p2-explicit-evidence-v1",
        api_max_tokens={"generation": 1024, "analysis": 2048},
        api_temperature=0,
        api_thinking=False,
        api_transport_retries=0,
        api_model_fallback=False,
        formal_cohort_role="primary-model-cohort-in-revised-analysis",
        prior_local_qwen_formal_results="preserve-and-report-as-separate-cohort",
        retrieval_store="approved-2026-10-17-archive-with-per-attempt-verified-copy",
        retrieval_context_policy_id="structured-chunks-remove-payload-examples-v1",
        formal_release_system="poolside-laguna-p4-hash-bound-release-v1",
    )
    protocol.pop("freeze_candidate_sha256", None)
    protocol["freeze_candidate_sha256"] = protocol_candidate_sha256(protocol)
    return protocol


def build_budget(plan: dict, plan_hash: str) -> dict:
    q4_audit = read_json(Q4_AUDIT_PATH)
    q4_budget = read_json(Q4_BUDGET_PATH)
    smoke_paths = sorted(POOLSIDE_SMOKE_ROOT.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    current_smoke = None
    if smoke_paths:
        smoke_path = smoke_paths[0]
        smoke = read_json(smoke_path)
        model_entry = next((item for request in smoke.get("requests", [])
                            for item in ((request.get("body") or {}).get("data") or [])
                            if isinstance(item, dict) and item.get("id") == "poolside/laguna-s-2.1"), None)
        pricing = model_entry.get("pricing", {}) if isinstance(model_entry, dict) else {}
        zero_price = bool(pricing) and all(str(value) == "0" for value in pricing.values())
        current_smoke = {
            "report_path": relative(smoke_path),
            "report_sha256": sha256(smoke_path),
            "started_at_utc": smoke.get("started_at_utc"),
            "status": smoke.get("status"),
            "requested_model": smoke.get("requested_model"),
            "reported_model": smoke.get("reported_model"),
            "model_listed": smoke.get("model_listed"),
            "model_catalog_is_free": model_entry.get("is_free") if isinstance(model_entry, dict) else None,
            "model_catalog_zero_pricing": zero_price,
            "pricing": pricing,
            "context_length": model_entry.get("context_length") if isinstance(model_entry, dict) else None,
            "http_requests": len(smoke.get("requests", [])),
            "chat_usage": smoke.get("usage"),
            "free_status_verified": bool(
                smoke.get("status") == "ok"
                and smoke.get("requested_model") == "poolside/laguna-s-2.1"
                and smoke.get("reported_model") == "poolside/laguna-s-2.1"
                and smoke.get("model_listed") is True
                and isinstance(model_entry, dict) and model_entry.get("is_free") is True
                and zero_price
            ),
            "scope_note": "Current model catalog and 1 chat request only; does not verify full-run quota, rate limit, or future continuity.",
        }
    usage = q4_audit["api_responses"]["usage_total"]
    q4_units = q4_audit["qualification"]["expected_ab_units"]
    p4_units = plan["design"]["counts"]["ab_api_units"]
    multiplier = p4_units // q4_units
    gen_requests_per_unit = q4_budget["generation_requests_per_candidate_slot"] * q4_budget["candidate_budget_per_unit"]
    analysis_requests_per_unit = q4_budget["candidate_budget_per_unit"]
    max_calls_per_unit = gen_requests_per_unit + analysis_requests_per_unit
    max_completion_per_unit = (
        gen_requests_per_unit * q4_budget["generation_max_tokens"]
        + analysis_requests_per_unit * q4_budget["analysis_max_tokens"]
    )
    return {
        "schema": "poolside-laguna-formal-budget-draft-v1",
        "experiment_id": plan["experiment_id"],
        "status": "draft-not-approved-not-executable",
        "plan_path": relative(PLAN_PATH),
        "plan_sha256": plan_hash,
        "formal_runner_plan_path": relative(FORMAL_PLAN_PATH),
        "formal_runner_plan_sha256": sha256(FORMAL_PLAN_PATH),
        "protocol_path": relative(PROTOCOL_PATH),
        "protocol_candidate_sha256": protocol_candidate_sha256(read_json(PROTOCOL_PATH)),
        "scope": "72 direct API units in A/B; condition C uses local SecLists and is excluded from API-call budget",
        "calibration_source": {
            "experiment_id": q4_audit["experiment_id"],
            "audit_path": relative(Q4_AUDIT_PATH),
            "audit_sha256": sha256(Q4_AUDIT_PATH),
            "api_calls": q4_audit["qualification"]["api_calls_used"],
            "api_call_ceiling": q4_audit["qualification"]["api_call_ceiling"],
            "ab_units": q4_units,
            "actual_prompt_tokens": usage["prompt_tokens"],
            "actual_completion_tokens": usage["completion_tokens"],
        },
        "estimates": {
            "linear_expected_api_calls": round(q4_audit["qualification"]["api_calls_used"] / q4_units * p4_units),
            "expected_prompt_tokens_from_q4_x3": usage["prompt_tokens"] * multiplier,
            "expected_completion_tokens_from_q4_x3": usage["completion_tokens"] * multiplier,
            "expected_total_tokens_from_q4_x3": usage["total_tokens"] * multiplier,
            "api_wall_time_ceiling_seconds_from_q4_x3": q4_budget["max_wall_seconds"] * multiplier,
            "max_api_wall_seconds": q4_budget["max_wall_seconds"] * multiplier,
            "status": "projection only; full P4 duration includes DVWA validation and must be re-estimated",
        },
        "hard_ceilings_draft": {
            "api_units": p4_units,
            "api_calls_per_unit": max_calls_per_unit,
            "max_api_calls": p4_units * max_calls_per_unit,
            "generation_max_tokens": q4_budget["generation_max_tokens"],
            "analysis_max_tokens": q4_budget["analysis_max_tokens"],
            "max_completion_tokens": p4_units * max_completion_per_unit,
            "automatic_transport_retries": 0,
            "automatic_unit_replacements": 0,
            "model_fallback": False,
        },
        "spend_and_provider_limits": {
            "provider": "direct Poolside API only",
            "maximum_spend_usd": 0,
            "spend_policy": "free-only; stop if any charge or non-free status is reported",
            "researcher_reported_current_access": "free",
            "official_free_access_evidence": {
                "url": "https://poolside.ai/models",
                "statement": "Free to use for a limited time",
                "captured_date": datetime.now(timezone.utc).date().isoformat(),
            },
            "current_account_smoke": current_smoke,
            "account_spending_limit_usd": 0,
            "account_spending_limit_verified": False,
            "request_quota_verified": False,
            "rate_limit_verified": False,
            "continuity_through_full_run_verified": False,
            "researcher_confirmation_receipt_path": relative(PROVIDER_CONFIRMATION_PATH) if PROVIDER_CONFIRMATION_PATH.is_file() else None,
            "researcher_confirmation_receipt_sha256": sha256(PROVIDER_CONFIRMATION_PATH) if PROVIDER_CONFIRMATION_PATH.is_file() else None,
            "researcher_confirmation_valid": provider_confirmation_valid({"spend_and_provider_limits": {"current_account_smoke": current_smoke,
                "researcher_confirmation_receipt_path": relative(PROVIDER_CONFIRMATION_PATH) if PROVIDER_CONFIRMATION_PATH.is_file() else None,
                "researcher_confirmation_receipt_sha256": sha256(PROVIDER_CONFIRMATION_PATH) if PROVIDER_CONFIRMATION_PATH.is_file() else None}}),
            "execution_gate": "researcher confirmed the new account and formal run are safe; keep direct Poolside access free-only and complete the cohort while inference is available",
        },
        "abort_conditions": [
            "reported model differs from poolside/laguna-s-2.1",
            "HTTP response, finish reason, or response schema is invalid",
            "API request or completion-token ceiling is reached",
            "provider rate limit or account quota is reached",
            "request would exceed the approved spend limit",
            "DVWA origin, authentication, security level, baseline, or database reset fails",
            "runtime, prompt, corpus, index, SecLists, plan, or budget hash changes",
            "provider availability cannot cover the complete cohort and recovery window",
        ],
        "execution_authorized": False,
    }


def prepare_drafts(*, refresh: bool = False) -> None:
    if refresh and PROTOCOL_PATH.is_file() and read_json(PROTOCOL_PATH).get("status") == "frozen":
        raise ValueError("Refusing to refresh P4 drafts after the protocol has been frozen.")
    plan = build_plan()
    formal_plan = build_formal_runner_plan()
    protocol = build_protocol()
    if refresh:
        for path, expected_schema in ((PLAN_PATH, "poolside-laguna-formal-plan-draft-v1"),
                                      (BUDGET_PATH, "poolside-laguna-formal-budget-draft-v1"),
                                      (FORMAL_PLAN_PATH, None), (PROTOCOL_PATH, None)):
            if path.exists():
                existing = read_json(path)
                if (existing.get("experiment_id", EXPERIMENT_ID) != EXPERIMENT_ID
                        or (expected_schema and existing.get("schema") != expected_schema)
                        or (path == PROTOCOL_PATH
                            and existing.get("protocol_id") != protocol["protocol_id"])):
                    raise ValueError(f"Refusing to refresh an artifact not owned by this P4 draft: {relative(path)}")
        write_json_replace(PLAN_PATH, plan)
        write_json_replace(FORMAL_PLAN_PATH, formal_plan)
        write_json_replace(PROTOCOL_PATH, protocol)
    else:
        write_json_new(PLAN_PATH, plan)
        write_json_new(FORMAL_PLAN_PATH, formal_plan)
        write_json_new(PROTOCOL_PATH, protocol)
    budget = build_budget(plan, sha256(PLAN_PATH))
    if refresh:
        write_json_replace(BUDGET_PATH, budget)
    else:
        write_json_new(BUDGET_PATH, budget)


def gate(gate_id: str, status: str, evidence: str, next_action: str) -> dict:
    return {"gate_id": gate_id, "status": status, "evidence": evidence, "next_action": next_action}


def discovery_review_valid(path: Path, reports: list[dict]) -> bool:
    if not path.is_file():
        return False
    receipt = read_json(path)
    expected_hashes = {item.get("path"): item.get("sha256") for item in reports}
    return (
        receipt.get("schema") == "poolside-laguna-p4-discovery-review-v1"
        and receipt.get("experiment_id") == EXPERIMENT_ID
        and receipt.get("status") == "reviewed"
        and receipt.get("summary_plan_sha256") == sha256(PLAN_PATH)
        and receipt.get("formal_runner_plan_sha256") == sha256(FORMAL_PLAN_PATH)
        and receipt.get("reviewer_script_sha256") == sha256(ROOT / "development/review_poolside_laguna_p4_discovery.py")
        and receipt.get("report_hashes") == expected_hashes
        and receipt.get("out_of_level_counts_by_level") == {"low": 1, "medium": 1, "high": 0, "impossible": 3}
        and receipt.get("sql_injection_alert_group_count_by_level") == {
            "low": 0, "medium": 0, "high": 0, "impossible": 0
        }
        and receipt.get("verified_injection_points_per_report") == 2
        and receipt.get("classification") == "passive-discovery-coordinate-observations-only"
    )


def fresh_discovery_report_valid(item: dict, now: datetime) -> bool:
    path = ROOT / item.get("path", "")
    if not path.is_file() or sha256(path) != item.get("sha256"):
        return False
    report = read_json(path)
    metadata = report.get("run_metadata", {})
    try:
        generated = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
        age_hours = (now - generated.astimezone(timezone.utc)).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return False
    return (
        item.get("p4_use") == "fresh P4 discovery"
        and metadata.get("authentication_status") == "verified"
        and metadata.get("target_origin") == "http://dvwa"
        and metadata.get("security_level") == item.get("level")
        and metadata.get("scan_mode") == "passive"
        and 0 <= age_hours <= 24
        and item.get("authentication_status") == "verified"
        and item.get("verified_injection_point_count") == 2
        and report.get("summary", {}).get("verified_injection_point_count") == 2
    )


def inspect_target_binding(protocol: dict, reports: list[dict]) -> dict:
    """Verify the ZAP service alias and host origin map to the current DVWA container."""
    compose_path = ROOT / "dvwa/compose.yaml"
    zap_template_path = ROOT / "dvwa/zap-auth.template.yaml"
    compose = compose_path.read_text(encoding="utf-8")
    zap_template = zap_template_path.read_text(encoding="utf-8")
    origins = sorted({item.get("target_origin_in_report") for item in reports})
    result = {
        "compose_sha256": sha256(compose_path),
        "zap_template_sha256": sha256(zap_template_path),
        "report_origins": origins,
        "runner_origin": protocol.get("target_origin"),
        "compose_has_dvwa_host_binding": "127.0.0.1:4280:80" in compose,
        "zap_uses_compose_service_alias": "http://dvwa/" in zap_template,
        "docker_inspect_succeeded": False,
        "same_container_binding_verified": False,
    }
    try:
        completed = subprocess.run(
            ["docker", "inspect", "dvwa-dvwa-1"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        container = json.loads(completed.stdout)[0]
        config = container.get("Config") or {}
        network_settings = container.get("NetworkSettings") or {}
        labels = config.get("Labels") or {}
        networks = network_settings.get("Networks") or {}
        aliases = {alias for network in networks.values() for alias in network.get("Aliases", [])}
        ports = (network_settings.get("Ports") or {}).get("80/tcp", [])
        host_binding = any(item.get("HostIp") == "127.0.0.1" and item.get("HostPort") == "4280"
                           for item in (ports or []))
        expected_image = "ghcr.io/digininja/dvwa@sha256:ed35515e9111801e6e386a6fbb11165508cc7f72e0cb8da4dbb3df70182986c6"
        result.update({
            "docker_inspect_succeeded": True,
            "container_id": container.get("Id"),
            "container_image": config.get("Image"),
            "compose_project": labels.get("com.docker.compose.project"),
            "compose_service": labels.get("com.docker.compose.service"),
            "service_alias_present": "dvwa" in aliases,
            "host_binding_present": host_binding,
            "image_digest_matches_compose": config.get("Image") == expected_image,
        })
        result["same_container_binding_verified"] = (
            origins == ["http://dvwa"]
            and protocol.get("target_origin") == "http://127.0.0.1:4280"
            and result["compose_has_dvwa_host_binding"]
            and result["zap_uses_compose_service_alias"]
            and result["compose_project"] == "dvwa"
            and result["compose_service"] == "dvwa"
            and result["service_alias_present"]
            and result["host_binding_present"]
            and result["image_digest_matches_compose"]
        )
    except (OSError, subprocess.SubprocessError, IndexError, KeyError, json.JSONDecodeError) as failure:
        result["docker_inspect_error_type"] = type(failure).__name__
    return result


def run_dry_run() -> dict:
    plan = read_json(PLAN_PATH)
    budget = read_json(BUDGET_PATH)
    q4_audit = read_json(Q4_AUDIT_PATH)
    method_decision = read_json(METHOD_DECISION_PATH)
    q4_qualification_passed = (
        q4_audit.get("formal_eligible") is False
        and q4_audit.get("qualification", {}).get("qualification_passed") is True
        and q4_audit.get("qualification", {}).get("completed_ab_units") == 24
        and q4_audit.get("qualification", {}).get("units_by_candidate_count") == {"10": 24}
    )
    q4_model_evidence = plan.get("provider", {}).get("reported_model_evidence", {})
    q4_model_match = (
        q4_model_evidence.get("response_file_count") == q4_audit.get("api_responses", {}).get("result_files")
        and q4_model_evidence.get("reported_model_counts") == {"poolside/laguna-s-2.1": 506}
        and q4_model_evidence.get("result_status_counts") == {"ok": 506}
    )
    expected_plan_hash = budget.get("plan_sha256")
    plan_hash_matches = expected_plan_hash == sha256(PLAN_PATH)
    researcher_decision = method_decision.get("researcher_decision", {})
    adviser_approval = method_decision.get("adviser_approval", {})
    method_decision_valid = (
        method_decision.get("schema") == "poolside-laguna-p4-method-decision-v1"
        and method_decision.get("decision_id") == "poolside-laguna-p4-method-decision-20261023"
        and method_decision.get("decision") == "approved-for-poolside-laguna-p4-method"
        and researcher_decision.get("basis") == "explicit-user-approval-in-chat"
        and researcher_decision.get("cohort_role") == "Poolside Laguna P4 is the primary formal model cohort for the revised analysis."
        and researcher_decision.get("cohort_relationship") == "P4 is a separate formal cohort from the prior local-Qwen formal experiment."
        and researcher_decision.get("local_qwen_data_policy") == "Preserve all existing local-Qwen formal results and report them separately. Do not overwrite, merge, or discard them."
        and researcher_decision.get("proposal_update_timing") == "at the end of the research"
        and researcher_decision.get("proposal_update_reason") == "The researcher wants to focus first on conducting the research so the results can be written."
        and researcher_decision.get("quote") == "saya sudah membaca file draf amandemen, saya akan mengganti proposal saya diakhir saja, kenapa? karena saya ingin fokus dulu terhadap penelitian ini agar bisa ditulis hasilnya, jadi pembimbing saya sudah menyetujui, saya setuju dengan laguna sebagai cohort formal tambahan, setuju juga laguna menggantikan model formal utama, yang terpenting hasil pengujian formal menggunakan qwen lokal tetap disimpan"
        and adviser_approval.get("status") == "reported-by-researcher"
        and adviser_approval.get("direct_adviser_receipt_present") is False
        and adviser_approval.get("quote") == "pembimbing saya sudah menyetujui"
        and method_decision.get("execution_authorized") is False
        and method_decision.get("formal_protocol_frozen") is False
        and method_decision.get("formal_execution_approval") is False
        and method_decision.get("openrouter_in_scope") is False
        and plan.get("method_amendment", {}).get("decision_receipt_sha256") == sha256(METHOD_DECISION_PATH)
    )
    counts = plan.get("design", {}).get("counts", {})
    count_check = counts == {
        "ab_api_units": 72,
        "c_seclists_units": 27,
        "applicable_units": 99,
        "ab_candidates": 720,
        "c_candidates": 270,
        "total_candidates": 990,
        "logical_confirmations": 2970,
        "excluded_c_slots": 9,
    }

    reports = plan.get("discovery_reports", [])
    discovery_integrity = len(reports) == 12
    discovery_integrity = discovery_integrity and len({item.get("path") for item in reports}) == 12
    now = datetime.now(timezone.utc)
    discovery_integrity = discovery_integrity and all(fresh_discovery_report_valid(item, now) for item in reports)

    archive_files = plan.get("knowledge_snapshot", {}).get("archive_file_hashes", {})
    archive_intact = len(archive_files) == 6 and all(
        item.get("matches_approved") is True for item in archive_files.values()
    )
    active_compare = plan.get("knowledge_snapshot", {}).get("active_store_comparison", {})
    active_matches = len(active_compare) == 6 and all(
        item.get("matches_approved") is True for item in active_compare.values()
    )
    current_active_compare = {}
    for relative_path, expected in archive_files.items():
        active_path = ROOT / relative_path
        observed = sha256(active_path) if active_path.is_file() else None
        current_active_compare[relative_path] = {
            "approved_sha256": expected["expected_sha256"],
            "active_sha256": observed,
            "matches_approved": observed == expected["expected_sha256"],
        }
    active_mismatches = [path for path, item in current_active_compare.items()
                         if not item["matches_approved"]]

    snapshot_check = read_json(SNAPSHOT_CHECK_PATH) if SNAPSHOT_CHECK_PATH.is_file() else {}
    snapshot_copy = snapshot_check.get("archive_check", {}).get("copy_test", {})
    snapshot_isolated_passed = (
        snapshot_check.get("schema") == "poolside-laguna-p4-snapshot-check-v1"
        and snapshot_check.get("experiment_id") == EXPERIMENT_ID
        and snapshot_check.get("status") == "passed"
        and snapshot_check.get("archive_check", {}).get("passed") is True
        and snapshot_copy.get("archive_unchanged") is True
        and snapshot_copy.get("retrieved_chunks", 0) >= 1
        and snapshot_copy.get("copy_path_was_temporary") is True
        and snapshot_check.get("api_requests_sent") == 0
        and snapshot_check.get("dvwa_requests_sent") == 0
        and snapshot_check.get("credentials_read") is False
        and snapshot_check.get("openrouter_used") is False
    )

    runner_readiness = read_json(RUNNER_READINESS_PATH) if RUNNER_READINESS_PATH.is_file() else {}
    runner_gates = {item.get("gate_id"): item.get("status") for item in runner_readiness.get("gates", [])}
    runner_implementation_passed = (
        runner_readiness.get("schema") == "poolside-laguna-p4-offline-readiness-v1"
        and runner_readiness.get("experiment_id") == EXPERIMENT_ID
        and runner_gates.get("p4-runner-and-pinned-inputs") == "passed"
        and runner_gates.get("approved-snapshot-isolation") == "passed"
        and runner_gates.get("generator-qualification") == "passed"
        and runner_readiness.get("api_requests_sent") == 0
        and runner_readiness.get("dvwa_requests_sent") == 0
        and runner_readiness.get("credentials_read") is False
        and runner_readiness.get("openrouter_used") is False
    )

    preflight = read_json(P4_PREFLIGHT_PATH) if P4_PREFLIGHT_PATH.is_file() else {}
    preflight_levels = preflight.get("levels", {})
    preflight_passed = (
        preflight.get("schema") == "poolside-laguna-p4-dvwa-preflight-v1"
        and preflight.get("experiment_id") == EXPERIMENT_ID
        and preflight.get("status") == "passed"
        and preflight.get("target_origin") == "http://127.0.0.1:4280"
        and preflight.get("protocol_candidate_sha256") == protocol_candidate_sha256(read_json(PROTOCOL_PATH))
        and preflight.get("formal_runner_plan_sha256") == sha256(FORMAL_PLAN_PATH)
        and preflight.get("database_reset_count") == 1
        and preflight.get("api_credentials_read") is False
        and preflight.get("openrouter_used") is False
        and set(preflight_levels) == {"low", "medium", "high", "impossible"}
        and all(item.get("passed") is True for item in preflight_levels.values())
        and preflight.get("timing_instrumentation", {}).get("maximum_benign_sample_below_threshold") is True
    )
    discovery_review_passed = discovery_review_valid(DISCOVERY_REVIEW_PATH, reports)

    engine_source = (ROOT / "development/run_qwen_api_experiments.py").read_text(encoding="utf-8")
    formal_api_block = "The Qwen API adapter only supports dataset=pilot. Formal execution is blocked." in engine_source
    protocol = read_json(ACTIVE_PROTOCOL_PATH)
    target_origins = sorted({item.get("target_origin_in_report") for item in reports})
    target_binding = inspect_target_binding(protocol, reports)
    target_mapping_matches = target_binding.get("same_container_binding_verified") is True

    gates = [
        gate("design-and-counts", "passed" if count_check else "failed", "P4 matrix has 99 applicable units, 990 candidates, and 2,970 logical confirmations.", "Maintain these counts when freezing the protocol."),
        gate("q4-generator-qualification", "passed" if q4_qualification_passed else "failed", "Q4 v5 reached 24/24 A/B units with ten valid candidates; the Q4 receipt says formal_eligible=false.", "Treat Q4 as a generator qualification gate only."),
        gate("q4-direct-model-evidence", "passed" if q4_model_match else "failed", "All Q4 response receipts are checked for direct Poolside model ID and successful status.", "Repeat the reported-model check on every P4 API response."),
        gate("discovery-archive-integrity", "passed" if discovery_integrity else "failed", "All 12 fresh P4 passive ZAP reports are pinned by hash, authenticated, level-bound, less than 24 hours old, and each verifies two injection points.", "Keep the discovery report mapping fixed to this plan and refresh if any report expires or the target changes."),
        gate("discovery-target-binding", "passed" if target_mapping_matches else "open", f"Current compose configuration and Docker inspection map ZAP origin {target_origins} and runner origin {protocol.get('target_origin')} to the pinned DVWA service.", "Use one canonical origin for the 12 fresh P4 discovery scans and retain this container-binding evidence."),
        gate("approved-corpus-archive", "passed" if archive_intact else "failed", "The preserved six-file archive is checked against the 17 October approved formal snapshot.", "Use an isolated read-only snapshot path in the P4 runner; do not overwrite the active index."),
        gate("active-index-isolation", "passed" if snapshot_isolated_passed else "open", f"{len(active_mismatches)} of 6 active index files differ from the approved snapshot; P4 retrieval uses a temporary copy. Isolated retrieval evidence passed={snapshot_isolated_passed}.", "Continue to use the verified archived snapshot through per-attempt copies; never mutate the active index."),
        gate("method-amendment-decision", "passed" if method_decision_valid else "open", "Researcher decision is recorded: Laguna P4 is the primary formal model cohort for the revised analysis; existing local-Qwen formal results remain preserved and separately reported. Adviser approval is reported by the researcher, with no direct adviser receipt attached. The research proposal text will be updated at the end; this decision does not freeze the P4 protocol or authorize execution.", "Keep the Laguna and local-Qwen datasets separate; update the proposal at the end of the research, then obtain separate protocol-freeze and execution-approval receipts before any formal run."),
        gate("formal-poolside-runner", "passed" if runner_implementation_passed and formal_api_block else "open", f"Dedicated fail-closed P4 runner and pinned separate inputs validate offline; implementation evidence passed={runner_implementation_passed}.", "Keep API and DVWA execution disabled until P4 freeze and execution receipts bind the final hashes."),
        gate("provider-account-budget", "passed" if provider_confirmation_valid(budget) else "open", f"The researcher confirms the new account has sufficient quota/rate limit for the formal run; latest direct smoke reports exact model free with zero listed pricing. P4 enforces maximum_spend_usd=0. Confirmation valid={provider_confirmation_valid(budget)}; quota is researcher-confirmed, not independently read from the account console.", "Keep the run within the provider availability window and stop if a request is limited or any charge/non-free status appears."),
        gate("provider-continuity", "passed" if provider_confirmation_valid(budget) else "open", "The researcher confirms the direct Laguna API formal run is safe and acknowledges Poolside's 31 October 2026 inference shutdown notice. An interrupted cohort remains invalid; no provider switch is allowed.", "Run only while direct Poolside inference is available. Do not route through OpenRouter."),
        gate("dvwa-preflight", "passed" if preflight_passed else "open", f"P4 local receipt passed={preflight_passed}; it verifies one database reset, session and input coordinates at all four levels, benign timing baseline, and current protocol/plan hashes.", "Repeat the preflight if protocol, formal plan, DVWA image, or runtime changes."),
        gate("discovery-out-of-level-review", "passed" if discovery_review_passed else "open", "The review receipt binds all twelve fresh reports and assesses the out-of-level input observations against the pinned passive-discovery template.", "Review out-of-level observations against the scan plan; do not treat passive alerts as SQLi detections or FPR/PSR labels."),
        gate("val01-blind-review", "deferred-by-design", "A fresh blind packet cannot be built until P4 candidate IDs are locked.", "After the cohort, create a new randomized VAL-01 packet and mapping; never reuse pilot annotations."),
        gate("formal-execution-approval", "open", "No execution receipt is bound to a P4 protocol, plan, budget, and release manifest.", "Create the P4 release manifest after every prior gate passes, then obtain explicit approval bound to its hashes."),
    ]
    ready = all(item["status"] == "passed" for item in gates)
    return {
        "schema": "poolside-laguna-p4-offline-dry-run-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": plan.get("experiment_id"),
        "status": "ready" if ready else "blocked-not-execution-ready",
        "plan_sha256": sha256(PLAN_PATH),
        "budget_sha256": sha256(BUDGET_PATH),
        "plan_hash_matches_budget": plan_hash_matches,
        "design_count_check_passed": count_check,
        "q4_qualification_gate_passed": q4_qualification_passed,
        "q4_direct_model_evidence_passed": q4_model_match,
        "discovery_inventory_integrity_passed": discovery_integrity,
        "discovery_review_passed": discovery_review_passed,
        "approved_archive_integrity_passed": archive_intact,
        "isolated_snapshot_retrieval_passed": snapshot_isolated_passed,
        "isolated_snapshot_evidence_path": relative(SNAPSHOT_CHECK_PATH) if SNAPSHOT_CHECK_PATH.is_file() else None,
        "formal_runner_readiness_passed": runner_implementation_passed,
        "formal_runner_readiness_evidence_path": relative(RUNNER_READINESS_PATH) if RUNNER_READINESS_PATH.is_file() else None,
        "dvwa_preflight_passed": preflight_passed,
        "dvwa_preflight_evidence_path": relative(P4_PREFLIGHT_PATH) if P4_PREFLIGHT_PATH.is_file() else None,
        "method_decision_recorded": method_decision_valid,
        "method_decision_receipt_path": relative(METHOD_DECISION_PATH),
        "method_decision_receipt_sha256": sha256(METHOD_DECISION_PATH),
        "active_index_matches_approved_snapshot": active_matches,
        "active_index_mismatches": active_mismatches,
        "active_index_comparison": current_active_compare,
        "formal_api_pilot_only_guard_found": formal_api_block,
        "discovery_target_origins": target_origins,
        "frozen_protocol_target_origin": protocol.get("target_origin"),
        "target_binding_evidence": target_binding,
        "gates": gates,
        "execution_authorized": False,
        "execution_started": False,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "credentials_read": False,
        "openrouter_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-drafts", action="store_true",
                       help="Create new P4 plan and budget draft files without overwriting existing files")
    modes.add_argument("--refresh-drafts", action="store_true",
                       help="Refresh P4 drafts and create missing runner-plan/protocol drafts after identity checks")
    modes.add_argument("--dry-run", action="store_true",
                       help="Validate P4 preparation offline; sends no API or DVWA requests")
    parser.add_argument("--output", type=Path,
                        help="Optional JSON evidence path; only this P4 dry-run's own prior evidence may be refreshed")
    args = parser.parse_args()

    try:
        if args.prepare_drafts or args.refresh_drafts:
            if args.output:
                parser.error("--output is only valid with --dry-run.")
            prepare_drafts(refresh=args.refresh_drafts)
            print(json.dumps({"status": "drafts-refreshed" if args.refresh_drafts else "drafts-created", "plan": relative(PLAN_PATH),
                              "budget": relative(BUDGET_PATH), "execution_started": False}, indent=2))
            return 0
        result = run_dry_run()
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        print(serialized, end="")
        if args.output:
            output = args.output if args.output.is_absolute() else ROOT / args.output
            if output.exists():
                existing = read_json(output)
                if (existing.get("schema") != "poolside-laguna-p4-offline-dry-run-v1"
                        or existing.get("experiment_id") != EXPERIMENT_ID):
                    raise ValueError(f"Refusing to replace evidence not owned by this P4 dry-run: {relative(output)}")
                write_json_replace(output, result)
            else:
                write_json_new(output, result)
        return 0 if result["status"] == "ready" else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as failure:
        print(json.dumps({"status": "dry-run-error", "error_type": type(failure).__name__,
                          "error": str(failure), "execution_started": False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
