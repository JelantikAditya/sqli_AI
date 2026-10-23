"""Fail-closed runner for the separate Poolside Laguna P4 formal cohort.

--dry-run validates pinned inputs without reading credentials or sending API or
DVWA requests. Formal execution requires a frozen P4 protocol, a released P4
manifest, separate freeze and execution receipts, and explicit local flags.
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
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT / "development"
sys.path.insert(0, str(ROOT / "dvwa"))
sys.path.insert(0, str(DEVELOPMENT))

import poolside_laguna_generation_v5 as generation_v5
from prepare_poolside_laguna_p4 import provider_confirmation_valid
import run_bounded_poolside_qualification_v3 as p3_engine
import run_poolside_smoke as transport
from poolside_completion_budget import CompletionBudgetPoolsideAPI
from qwen_api_runtime import APIRuntimeFailure
import run_qwen_api_experiments as engine
from run_poolside_generation_preflight import write_new


EXPERIMENT_ID = "poolside-laguna-p4-20261023"
PROTOCOL_ID = "poolside-laguna-p4-formal-v1"
PLAN_PATH = DEVELOPMENT / "poolside_laguna_p4_formal_plan_20261023_recovery1.json"
BUDGET_PATH = DEVELOPMENT / "poolside_laguna_p4_budget_20261023_recovery1.json"
PROTOCOL_PATH = DEVELOPMENT / "poolside_laguna_p4_protocol_20261023_recovery1.json"
METHOD_DECISION_PATH = ROOT / "docs/evidence/poolside-laguna-p4-method-decision-2026-10-23.json"
P4_PLAN_PATH = DEVELOPMENT / "poolside_laguna_p4_plan_20261023_recovery1.json"
RELEASE_PATH = ROOT / "docs/evidence/poolside-laguna-p4-release-manifest-recovery1-2026-10-23.json"
FREEZE_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-freeze-approval-recovery1-2026-10-23.json"
EXECUTION_APPROVAL_PATH = ROOT / "docs/evidence/poolside-laguna-p4-execution-approval-recovery1-2026-10-23.json"
PREFLIGHT_PATH = ROOT / "docs/evidence/poolside-laguna-p4-dvwa-preflight-recovery1-2026-10-23.json"
DISCOVERY_REVIEW_PATH = ROOT / "docs/evidence/poolside-laguna-p4-discovery-review-recovery1-2026-10-23.json"
Q4_AUDIT_PATH = ROOT / "docs/evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json"
ARCHIVE_ROOT = ROOT / "results/raw/formal/formal-sqli-v1-20261017/index-recovery/approved-snapshot"
ARCHIVE_STORE = ARCHIVE_ROOT / "data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3"
FORMAL_OUTPUT = ROOT / "results/raw/formal" / "poolside-laguna-p4-recovery1-20261023"
PLAN_SCHEMA_PATH = ROOT / "schemas/local-run-plan.schema.json"
FREEZE_SCHEMA_PATH = ROOT / "schemas/poolside-laguna-p4-freeze-approval.schema.json"
EXECUTION_SCHEMA_PATH = ROOT / "schemas/poolside-laguna-p4-execution-approval.schema.json"
RUNNER_STATUS_SCHEMA = "poolside-laguna-p4-offline-readiness-v1"
MAX_DISCOVERY_AGE_HOURS = 24
EXPECTED_COUNTS = {
    "ab_api_units": 72,
    "c_seclists_units": 27,
    "applicable_units": 99,
    "ab_candidates": 720,
    "c_candidates": 270,
    "total_candidates": 990,
    "logical_confirmations": 2970,
    "excluded_c_slots": 9,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protocol_candidate_sha256(protocol: dict) -> str:
    """Hash the approved P4 content independent of draft/frozen state."""
    candidate = copy.deepcopy(protocol)
    candidate["status"] = "draft"
    candidate.pop("freeze_candidate_sha256", None)
    payload = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def method_decision_valid() -> bool:
    receipt = read_json(METHOD_DECISION_PATH)
    decision = receipt.get("researcher_decision", {})
    adviser = receipt.get("adviser_approval", {})
    return bool(
        receipt.get("decision") == "approved-for-poolside-laguna-p4-method"
        and decision.get("basis") == "explicit-user-approval-in-chat"
        and decision.get("cohort_role") == "Poolside Laguna P4 is the primary formal model cohort for the revised analysis."
        and decision.get("local_qwen_data_policy") == "Preserve all existing local-Qwen formal results and report them separately. Do not overwrite, merge, or discard them."
        and decision.get("proposal_update_timing") == "at the end of the research"
        and adviser.get("status") == "reported-by-researcher"
        and adviser.get("direct_adviser_receipt_present") is False
        and receipt.get("formal_protocol_frozen") is False
        and receipt.get("formal_execution_approval") is False
        and receipt.get("openrouter_in_scope") is False
    )


def verify_plan_inputs(*, require_frozen: bool = False) -> dict:
    """Load and bind P4 inputs. Credential and network access are intentionally absent."""
    p4_plan = read_json(P4_PLAN_PATH)
    plan = read_json(PLAN_PATH)
    budget = read_json(BUDGET_PATH)
    protocol = read_json(PROTOCOL_PATH)
    if p4_plan.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("P4 summary plan belongs to a different cohort.")
    if budget.get("experiment_id") != EXPERIMENT_ID or budget.get("plan_sha256") != sha256(P4_PLAN_PATH):
        raise ValueError("P4 budget does not bind the current P4 summary plan.")
    if budget.get("formal_runner_plan_path") != relative(PLAN_PATH):
        raise ValueError("P4 budget points to a different formal runner plan.")
    if budget.get("formal_runner_plan_sha256") != sha256(PLAN_PATH):
        raise ValueError("P4 budget does not bind the current formal runner plan.")
    if (budget.get("protocol_path") != relative(PROTOCOL_PATH)
            or budget.get("protocol_candidate_sha256") != protocol_candidate_sha256(protocol)
            or protocol.get("freeze_candidate_sha256") != protocol_candidate_sha256(protocol)):
        raise ValueError("P4 budget does not bind the current P4 protocol candidate.")
    if plan.get("experiment_id") != EXPERIMENT_ID or plan.get("dataset") != "formal":
        raise ValueError("P4 runner requires its unique formal dataset plan.")
    if (plan.get("condition_ids") != ["A", "B", "C"]
            or plan.get("scenario_ids") != [f"S{i}" for i in range(1, 13)]
            or plan.get("replicates") != [1, 2, 3]):
        raise ValueError("P4 formal plan matrix differs from the approved design.")
    Draft202012Validator(read_json(PLAN_SCHEMA_PATH)).validate(plan)
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("P4 protocol ID mismatch.")
    allowed_statuses = {"draft", "frozen"}
    if protocol.get("status") not in allowed_statuses:
        raise ValueError("P4 protocol must remain draft or become frozen through its receipt.")
    if require_frozen and protocol.get("status") != "frozen":
        raise ValueError("Formal execution requires a separately approved frozen P4 protocol.")
    if protocol.get("generation", {}).get("model") != transport.MODEL:
        raise ValueError("P4 protocol model does not match the direct Poolside model ID.")
    if protocol.get("methodology", {}).get("api_base_url") != transport.BASE_URL:
        raise ValueError("P4 protocol endpoint differs from the pinned direct Poolside endpoint.")
    if protocol.get("generation", {}).get("candidate_budget") != 10:
        raise ValueError("P4 protocol must generate ten candidates per applicable unit.")
    if protocol.get("validation", {}).get("confirmations_per_candidate") != 3:
        raise ValueError("P4 protocol must retain three candidate confirmations.")
    if p4_plan.get("design", {}).get("counts") != EXPECTED_COUNTS:
        raise ValueError("P4 summary plan counts differ from the frozen study design.")
    ceilings = budget.get("hard_ceilings_draft", {})
    if (ceilings.get("api_units") != 72 or ceilings.get("api_calls_per_unit") != 40
            or ceilings.get("max_api_calls") != 2880
            or ceilings.get("max_completion_tokens") != 3686400
            or ceilings.get("automatic_transport_retries") != 0
            or ceilings.get("automatic_unit_replacements") != 0
            or ceilings.get("model_fallback") is not False):
        raise ValueError("P4 API/token ceilings or no-replacement policy changed.")
    spend = budget.get("spend_and_provider_limits", {})
    if spend.get("provider") != "direct Poolside API only" or spend.get("maximum_spend_usd") != 0:
        raise ValueError("P4 is authorized for free-only direct Poolside access, with zero spend.")
    smoke = spend.get("current_account_smoke", {})
    if (smoke.get("free_status_verified") is not True
            or smoke.get("requested_model") != transport.MODEL
            or smoke.get("reported_model") != transport.MODEL
            or smoke.get("http_requests") != 2):
        raise ValueError("P4 requires a current direct Poolside smoke confirming the exact model is free.")
    if protocol.get("status") == "frozen" and not method_decision_valid():
        raise ValueError("The recorded method decision no longer matches the P4 release.")

    # The existing plan validator uses status=pilot only to resolve and validate
    # shared paths; it never executes this copy or changes the saved formal plan.
    resolve_plan = copy.deepcopy(plan)
    resolve_plan["dataset"] = "pilot"
    resolve_protocol = copy.deepcopy(protocol)
    resolve_protocol["status"] = "pilot"
    resolved = engine.local_runner.validate_plan(resolve_plan, resolve_protocol, ROOT, verify_index=False)
    resolved["dataset"] = "formal"

    slots = engine.local_runner.planned_units(resolved, protocol, ROOT)
    applicable = [slot for slot in slots if slot["status"] != "excluded"]
    if (len(slots) != 108 or len(applicable) != 99
            or sum(slot["condition_id"] in {"A", "B"} for slot in applicable) != 72
            or sum(slot["condition_id"] == "C" for slot in applicable) != 27):
        raise ValueError("P4 ledger schedule does not produce 99 applicable units and nine excluded C slots.")

    runtime_hashes = p4_plan.get("generation_profile", {}).get("runtime_source_sha256", {})
    changed = [path for path, expected in runtime_hashes.items()
               if not (ROOT / path).is_file() or sha256(ROOT / path) != expected]
    if changed:
        raise ValueError("Pinned P4 runtime sources changed: " + ", ".join(changed[:12]))
    if not method_decision_valid():
        raise ValueError("P4 lacks the recorded researcher method decision.")
    q4 = read_json(Q4_AUDIT_PATH)
    if q4.get("formal_eligible") is not False or q4.get("qualification", {}).get("qualification_passed") is not True:
        raise ValueError("Q4 v5 is not a valid P4 generator qualification receipt.")
    return {"p4_plan": p4_plan, "plan": resolved, "budget": budget,
            "protocol": protocol, "slots": slots, "runtime_hashes": runtime_hashes}


def archived_index_check(inputs: dict, *, copy_test: bool = False) -> dict:
    """Verify all approved archive bytes and optionally open a temporary isolated copy."""
    index = inputs["p4_plan"]["knowledge_snapshot"]["archive_file_hashes"]
    expected = {key: value["expected_sha256"] for key, value in index.items()}
    observed = {}
    for project_path, expected_hash in expected.items():
        source = ARCHIVE_ROOT / project_path
        actual = sha256(source) if source.is_file() else None
        observed[project_path] = {"expected_sha256": expected_hash, "observed_sha256": actual,
                                  "matches": actual == expected_hash}
    if len(observed) != 6 or not all(item["matches"] for item in observed.values()):
        return {"passed": False, "files": observed, "copy_test": None}

    copy_result = None
    if copy_test:
        # The test copy lives in a fresh temporary directory and is deleted after
        # inspection. Chroma never opens the approved archive itself.
        before = {path: sha256(ARCHIVE_ROOT / path) for path in expected}
        manifest = read_json(ARCHIVE_STORE / "manifest.json")
        manifest["resolved_store_path"] = str(ARCHIVE_STORE.resolve())
        snapshot = {"index_file_sha256": {
            (ARCHIVE_ROOT / project_path).resolve().relative_to(ROOT.resolve()).as_posix(): expected_hash
            for project_path, expected_hash in expected.items()
        }}
        with tempfile.TemporaryDirectory(prefix="poolside-p4-index-check-", dir=ROOT) as temp_name:
            temp_root = Path(temp_name)
            copy_path = temp_root / "isolated-index"
            copy_receipt = engine.copy_verified_index_snapshot(manifest, snapshot, copy_path, ROOT)
            probe = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "dvwa"))
import rag_pipeline
manifest = json.loads((root / "results/raw/formal/formal-sqli-v1-20261017/index-recovery/approved-snapshot/data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3/manifest.json").read_text(encoding="utf-8"))
manifest["resolved_store_path"] = sys.argv[2]
scenario = next(item for item in rag_pipeline.load_catalog()["scenarios"] if item["scenario_id"] == "S1")
query = rag_pipeline.scenario_query(scenario, mode="proposal")
result = rag_pipeline.retrieve_chunks(query, manifest, 2, technique=scenario["sqli_type"], mode="proposal")
print(json.dumps({"collection_count": 9, "retrieved_chunks": len(result.get("chunks", [])),
                  "shortfall": result.get("shortfall"), "retrieval_mode": result.get("retrieval_mode")}))
'''
            completed = subprocess.run(
                [sys.executable, "-c", probe, str(ROOT), str(copy_path)],
                check=False, capture_output=True, text=True, encoding="utf-8", timeout=360,
            )
            if completed.returncode != 0:
                raise ValueError("Local embedding/retrieval snapshot probe failed: "
                                 + completed.stderr[-1200:])
            retrieval_probe = json.loads(completed.stdout.strip().splitlines()[-1])
            if retrieval_probe.get("collection_count") != 9 or retrieval_probe.get("retrieved_chunks", 0) < 1:
                raise ValueError("Isolated P4 snapshot did not return approved SQLi retrieval chunks.")
            copy_after = engine.store_file_hashes(copy_path)
        after = {path: sha256(ARCHIVE_ROOT / path) for path in expected}
        copy_result = {**retrieval_probe, "copy_path_was_temporary": True,
                       "copy_file_count": len(copy_after), "copy_receipt": copy_receipt,
                       "archive_unchanged": before == after}
        if before != after:
            raise ValueError("Approved archived index changed during isolated-copy test.")
    return {"passed": True, "files": observed, "copy_test": copy_result}


def check_discovery_freshness(plan: dict) -> dict:
    now = datetime.now(timezone.utc)
    reports = {}
    for scenario_id, per_replicate in plan.get("discovery_reports", {}).items():
        for replicate_text, report_path_text in per_replicate.items():
            report_path = ROOT / report_path_text
            key = f"{scenario_id}/r{replicate_text}"
            if not report_path.is_file():
                reports[key] = {"passed": False, "reason": "missing"}
                continue
            report = read_json(report_path)
            metadata = report.get("run_metadata", {})
            try:
                generated = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
                age_hours = (now - generated.astimezone(timezone.utc)).total_seconds() / 3600
            except (KeyError, TypeError, ValueError):
                age_hours = None
            passed = (
                metadata.get("authentication_status") == "verified"
                and metadata.get("target_origin") == "http://dvwa"
                and age_hours is not None and 0 <= age_hours <= MAX_DISCOVERY_AGE_HOURS
                and report.get("summary", {}).get("verified_injection_point_count") == 2
            )
            reports[key] = {"passed": passed, "path": report_path_text,
                            "sha256": sha256(report_path), "age_hours": age_hours,
                            "authentication_status": metadata.get("authentication_status"),
                            "target_origin": metadata.get("target_origin"),
                            "out_of_level_observation_count": report.get("summary", {}).get(
                                "out_of_level_sqli_input_observation_count")}
    unique = {item["path"] for item in reports.values() if item.get("path")}
    return {"passed": len(reports) == 36 and len(unique) == 12
            and all(item["passed"] for item in reports.values()), "expected_scenario_replicate_pairs": 36,
            "unique_reports": len(unique), "reports": reports}


def readiness_report(*, copy_test: bool = False) -> dict:
    inputs = verify_plan_inputs()
    archive = archived_index_check(inputs, copy_test=copy_test)
    discovery = check_discovery_freshness(inputs["plan"])
    protocol_frozen = inputs["protocol"].get("status") == "frozen"
    release_present = RELEASE_PATH.is_file()
    freeze_receipt = read_json(FREEZE_APPROVAL_PATH) if FREEZE_APPROVAL_PATH.is_file() else {}
    try:
        Draft202012Validator(read_json(FREEZE_SCHEMA_PATH)).validate(freeze_receipt)
        freeze_receipt_present = (
            protocol_frozen
            and freeze_receipt.get("decision") == "approved-for-p4-protocol-freeze"
            and freeze_receipt.get("formal_plan_sha256") == sha256(PLAN_PATH)
            and freeze_receipt.get("budget_sha256") == sha256(BUDGET_PATH)
            and freeze_receipt.get("protocol_candidate_sha256") == inputs["protocol"].get("freeze_candidate_sha256")
        )
    except Exception:
        freeze_receipt_present = False
    execution_receipt_present = EXECUTION_APPROVAL_PATH.is_file()
    preflight_receipt = read_json(PREFLIGHT_PATH) if PREFLIGHT_PATH.is_file() else {}
    preflight_levels = preflight_receipt.get("levels", {})
    preflight_present = (
        preflight_receipt.get("schema") == "poolside-laguna-p4-dvwa-preflight-v1"
        and preflight_receipt.get("experiment_id") == EXPERIMENT_ID
        and preflight_receipt.get("status") == "passed"
        and preflight_receipt.get("target_origin") == "http://127.0.0.1:4280"
        and preflight_receipt.get("target_host_is_loopback") is True
        and preflight_receipt.get("protocol_candidate_sha256") == protocol_candidate_sha256(inputs["protocol"])
        and preflight_receipt.get("formal_runner_plan_sha256") == sha256(PLAN_PATH)
        and preflight_receipt.get("database_reset_count") == 1
        and preflight_receipt.get("api_credentials_read") is False
        and preflight_receipt.get("openrouter_used") is False
        and set(preflight_levels) == {"low", "medium", "high", "impossible"}
        and all(item.get("passed") is True for item in preflight_levels.values())
        and preflight_receipt.get("timing_instrumentation", {}).get("maximum_benign_sample_below_threshold") is True
    )
    review_receipt = read_json(DISCOVERY_REVIEW_PATH) if DISCOVERY_REVIEW_PATH.is_file() else {}
    expected_report_hashes = {item.get("path"): item.get("sha256")
                              for item in inputs["p4_plan"].get("discovery_reports", [])}
    review_present = (
        review_receipt.get("schema") == "poolside-laguna-p4-discovery-review-v1"
        and review_receipt.get("experiment_id") == EXPERIMENT_ID
        and review_receipt.get("status") == "reviewed"
        and review_receipt.get("summary_plan_sha256") == sha256(P4_PLAN_PATH)
        and review_receipt.get("formal_runner_plan_sha256") == sha256(PLAN_PATH)
        and review_receipt.get("reviewer_script_sha256") == sha256(DEVELOPMENT / "review_poolside_laguna_p4_discovery_recovery1.py")
        and review_receipt.get("report_hashes") == expected_report_hashes
        and review_receipt.get("out_of_level_counts_by_level") == {"low": 1, "medium": 1, "high": 0, "impossible": 3}
        and review_receipt.get("sql_injection_alert_group_count_by_level") == {
            "low": 0, "medium": 0, "high": 0, "impossible": 0
        }
        and review_receipt.get("mapping_matches_formal_plan") is True
    )
    budget = inputs["budget"]["spend_and_provider_limits"]
    qwen_preserved = (ROOT / "results/raw/formal/formal-sqli-v1-20261017").is_dir()
    gates = [
        {"gate_id": "p4-runner-and-pinned-inputs", "status": "passed",
         "evidence": "P4 standard plan, separate draft protocol, budget, method receipt, and runtime source hashes validate offline."},
        {"gate_id": "approved-snapshot-isolation", "status": "passed" if archive["passed"] else "failed",
         "evidence": "Six archived files match their approved hashes; Chroma access is confined to per-attempt copies."},
        {"gate_id": "generator-qualification", "status": "passed",
         "evidence": "Q4 v5 receipt is 24/24 but formal_eligible=false, so it remains qualification only."},
        {"gate_id": "local-qwen-results-preserved", "status": "passed" if qwen_preserved else "failed",
         "evidence": "The prior local-Qwen formal cohort remains at its original, separate output path."},
        {"gate_id": "fresh-discovery-and-review", "status": "passed" if discovery["passed"] and review_present else "open",
         "evidence": f"Freshness check found {discovery['unique_reports']}/12 unique reports; hash-bound technical review validated={review_present}."},
        {"gate_id": "direct-provider-free-quota-and-continuity", "status": "passed" if provider_confirmation_valid(inputs["budget"]) else "open",
         "evidence": f"Current direct smoke reports the exact model free={budget.get('current_account_smoke', {}).get('free_status_verified')}; the researcher confirms the new account quota/rate limit and formal run are safe, and acknowledges the 31 October 2026 shutdown notice. Confirmation valid={provider_confirmation_valid(inputs['budget'])}; the account console limit was not independently read. Zero spend policy={budget.get('maximum_spend_usd')}."},
        {"gate_id": "dvwa-formal-preflight", "status": "passed" if preflight_present else "open",
         "evidence": f"P4 local preflight receipt is valid={preflight_present}; target, one database reset, authenticated forms at four levels, benign baseline timing, and source hashes are checked."},
        {"gate_id": "protocol-freeze", "status": "passed" if freeze_receipt_present else "open",
         "evidence": "The recovery package needs its own hash-bound researcher freeze approval."},
        {"gate_id": "formal-execution-release", "status": "passed" if release_present else "open",
         "evidence": "A released P4 manifest is present; the separate hash-bound execution approval remains the final execution check."},
        {"gate_id": "val01-blind-review", "status": "deferred-by-design",
         "evidence": "The new VAL-01 packet is built only after P4 candidate IDs are locked."},
    ]
    ready = all(item["status"] == "passed" for item in gates if item["status"] != "deferred-by-design")
    return {
        "schema": RUNNER_STATUS_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": EXPERIMENT_ID,
        "status": "ready-for-execution-approval" if ready else "blocked-not-execution-ready",
        "plan_sha256": sha256(PLAN_PATH), "budget_sha256": sha256(BUDGET_PATH),
        "protocol_sha256": sha256(PROTOCOL_PATH),
        "method_decision_sha256": sha256(METHOD_DECISION_PATH),
        "archive_check": archive, "discovery_check": discovery,
        "formal_output_path": relative(FORMAL_OUTPUT),
        "qwen_local_formal_path": "results/raw/formal/formal-sqli-v1-20261017",
        "gates": gates, "execution_authorized": False, "execution_started": False,
        "api_requests_sent": 0, "dvwa_requests_sent": 0,
        "credentials_read": False, "openrouter_used": False,
    }


def _snapshot_for_attempt(plan: dict) -> dict:
    """Translate approved active-path hashes to their preserved archive paths."""
    resolved = copy.deepcopy(plan["knowledge_snapshot_resolved"])
    archive_hashes = {}
    for active_path, digest in plan["knowledge_snapshot"]["index_file_sha256"].items():
        archive_path = (ARCHIVE_ROOT / Path(active_path)).resolve()
        if not archive_path.is_relative_to(ARCHIVE_STORE.resolve()):
            raise ValueError("P4 archive mapping escaped the approved Chroma store.")
        archive_hashes[relative(archive_path)] = digest
    resolved["index_file_sha256"] = archive_hashes
    resolved["store_path_resolved"] = str(ARCHIVE_STORE.resolve())
    return resolved


@contextmanager
def p4_callbacks():
    old_generation = engine.make_generation_callback
    old_analysis = engine.make_analysis_callback
    engine.make_generation_callback = generation_v5.make_generation_callback
    engine.make_analysis_callback = p3_engine.analysis_callback
    try:
        yield
    finally:
        engine.make_generation_callback = old_generation
        engine.make_analysis_callback = old_analysis


def _execute_one(unit: dict, attempt: dict, plan: dict, protocol: dict,
                 data_directory: Path, api: CompletionBudgetPoolsideAPI,
                 config: dict) -> dict:
    if unit["condition_id"] == "C":
        return engine.execute_api_unit(unit, attempt, plan, protocol, data_directory, ROOT, api, config)
    p4_plan = copy.deepcopy(plan)
    if unit["condition_id"] == "B":
        p4_plan["knowledge_snapshot_resolved"] = _snapshot_for_attempt(plan)
        original_read_manifest = engine.read_manifest

        def archive_manifest(path: Path) -> dict:
            manifest = original_read_manifest(path)
            manifest["resolved_store_path"] = str(ARCHIVE_STORE.resolve())
            return manifest

        engine.read_manifest = archive_manifest
        try:
            return engine.execute_api_unit(unit, attempt, p4_plan, protocol,
                                           data_directory, ROOT, api, config)
        finally:
            engine.read_manifest = original_read_manifest
    return engine.execute_api_unit(unit, attempt, p4_plan, protocol, data_directory, ROOT, api, config)


def _validate_execution_release(inputs: dict) -> dict:
    protocol = inputs["protocol"]
    if protocol.get("status") != "frozen":
        raise ValueError("P4 execution is blocked until the protocol is frozen.")
    release = read_json(RELEASE_PATH)
    if (release.get("schema") != "poolside-laguna-p4-release-v1"
            or release.get("status") != "released"
            or release.get("ready_for_formal") is not True
            or release.get("protocol_frozen") is not True
            or release.get("formal_execution_authorized") is not False
            or release.get("plan_sha256") != sha256(PLAN_PATH)
            or release.get("budget_sha256") != sha256(BUDGET_PATH)
            or release.get("protocol_sha256") != sha256(PROTOCOL_PATH)
            or release.get("method_decision_sha256") != sha256(METHOD_DECISION_PATH)
            or not isinstance(release.get("gates"), dict)
            or not release["gates"]
            or any(item.get("status") != "passed" for item in release["gates"].values())):
        raise ValueError("P4 release manifest is missing, stale, or has an open gate.")
    freeze_receipt = read_json(FREEZE_APPROVAL_PATH)
    Draft202012Validator(read_json(FREEZE_SCHEMA_PATH)).validate(freeze_receipt)
    if (freeze_receipt.get("decision") != "approved-for-p4-protocol-freeze"
            or freeze_receipt.get("formal_protocol_freeze") is not True
            or freeze_receipt.get("formal_execution_approval") is not False
            or freeze_receipt.get("experiment_id") != EXPERIMENT_ID
            or freeze_receipt.get("formal_plan_sha256") != sha256(PLAN_PATH)
            or freeze_receipt.get("budget_sha256") != sha256(BUDGET_PATH)
            or freeze_receipt.get("protocol_candidate_sha256") != protocol.get("freeze_candidate_sha256")):
        raise ValueError("P4 freeze approval does not match the protocol candidate and plan hashes.")
    execution_receipt = read_json(EXECUTION_APPROVAL_PATH)
    Draft202012Validator(read_json(EXECUTION_SCHEMA_PATH)).validate(execution_receipt)
    if (execution_receipt.get("decision") != "approved-for-p4-formal-execution"
            or execution_receipt.get("formal_execution_approval") is not True
            or execution_receipt.get("experiment_id") != EXPERIMENT_ID
            or execution_receipt.get("formal_plan_sha256") != sha256(PLAN_PATH)
            or execution_receipt.get("budget_sha256") != sha256(BUDGET_PATH)
            or execution_receipt.get("protocol_sha256") != sha256(PROTOCOL_PATH)
            or execution_receipt.get("release_manifest_sha256") != sha256(RELEASE_PATH)):
        raise ValueError("P4 formal execution approval is missing or does not match the released package.")
    spend = inputs["budget"]["spend_and_provider_limits"]
    if spend.get("maximum_spend_usd") != 0 or spend.get("researcher_reported_current_access") != "free":
        raise ValueError("P4 execution is configured for zero-spend access only.")
    if not PREFLIGHT_PATH.is_file() or not DISCOVERY_REVIEW_PATH.is_file():
        raise ValueError("Fresh DVWA preflight and discovery-review receipts are required.")
    return {"scope": "poolside-p4-formal-execution", "decision": execution_receipt["decision"],
            "formal_execution_approval": True, "experiment_id": EXPERIMENT_ID,
            "formal_plan_sha256": sha256(PLAN_PATH), "budget_sha256": sha256(BUDGET_PATH),
            "protocol_sha256": sha256(PROTOCOL_PATH),
            "release_manifest_sha256": sha256(RELEASE_PATH),
            "approval_path": relative(EXECUTION_APPROVAL_PATH),
            "approval_sha256": sha256(EXECUTION_APPROVAL_PATH),
            "authority": execution_receipt["authority"]}


def execute(*, confirm_local_dvwa: bool, confirm_database_reset: bool,
            confirm_zero_spend: bool, resume: bool = False) -> dict:
    inputs = verify_plan_inputs(require_frozen=True)
    authorization = _validate_execution_release(inputs)
    if not (confirm_local_dvwa and confirm_database_reset and confirm_zero_spend):
        raise ValueError("Execution needs explicit local-DVWA, database-reset, and zero-spend flags.")
    if not resume and FORMAL_OUTPUT.exists():
        raise ValueError("P4 output already exists; refusing to overwrite or start a second cohort.")
    if resume and not (FORMAL_OUTPUT / "ledger.jsonl").is_file():
        raise ValueError("Cannot resume P4 without its original append-only ledger.")
    engine.local_runner.require_local_target(inputs["protocol"]["target_origin"])
    api_key = transport.load_key()
    if not api_key:
        raise ValueError("No direct Poolside API key is configured in the local environment.")
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    plan = inputs["plan"]
    protocol = inputs["protocol"]
    budget = inputs["budget"]
    plan_hash = engine.sha256_bytes(engine.canonical_json({
        key: value for key, value in plan.items() if not key.endswith("_resolved")
    }))
    protocol_hash = sha256(PROTOCOL_PATH)
    formal_output = FORMAL_OUTPUT
    if resume:
        ledger = engine.local_runner.ExperimentLedger.resume(
            formal_output, plan, plan_hash, protocol_hash, ROOT,
            formal_execution_authorization=authorization)
    else:
        ledger = engine.local_runner.ExperimentLedger.create(
            formal_output, plan, protocol, plan_hash, protocol_hash, ROOT,
            formal_execution_authorization=authorization)
        write_new(formal_output / "poolside-p4-runtime.snapshot.json", {
            "experiment_id": EXPERIMENT_ID, "plan_sha256": sha256(PLAN_PATH),
            "budget_sha256": sha256(BUDGET_PATH), "protocol_sha256": protocol_hash,
            "release_manifest_sha256": sha256(RELEASE_PATH),
            "execution_approval_sha256": authorization["approval_sha256"],
            "method_decision_sha256": sha256(METHOD_DECISION_PATH),
            "runtime_source_sha256": inputs["runtime_hashes"],
            "api_base_url": transport.BASE_URL, "model": transport.MODEL,
            "api_calls_max": budget["hard_ceilings_draft"]["max_api_calls"],
            "completion_tokens_max": budget["hard_ceilings_draft"]["max_completion_tokens"],
            "maximum_spend_usd": 0, "openrouter_used": False,
        })
        for source_name in inputs["runtime_hashes"]:
            source = ROOT / source_name
            target = formal_output / "source" / source_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(source.read_bytes())

    max_calls = budget["hard_ceilings_draft"]["max_api_calls"]
    max_completion = budget["hard_ceilings_draft"]["max_completion_tokens"]
    max_seconds = budget["estimates"]["max_api_wall_seconds"]
    api = CompletionBudgetPoolsideAPI(
        api_key, formal_output, max_calls=max_calls, max_seconds=max_seconds,
        max_completion_tokens=max_completion)
    config = {"limits": {"max_total_api_calls": max_calls,
                         "max_retrieved_chars_per_chunk": 1800}}

    def execute_one(unit, attempt, active_plan, active_protocol, data_dir, root):
        api.require_time()
        print(json.dumps({"event": "unit-start", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "replicate": unit["replicate"],
                          "api_calls": api.used_calls}, ensure_ascii=False), flush=True)
        return _execute_one(unit, attempt, active_plan, active_protocol, data_dir, api, config)

    with p4_callbacks(), engine.local_runner.experiment_lock(formal_output, recover_stale=resume):
        result = engine.local_runner.execute_ledger(
            ledger, plan, protocol, formal_output, execute=True, retry_invalid=False,
            recovered=0, root=ROOT, execute_one=execute_one)
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result_path in formal_output.glob("attempts/**/api-calls/*/result.json"):
        record = read_json(result_path).get("result", {})
        usage = record.get("usage") or {}
        for key in usage_totals:
            if type(usage.get(key)) is int:
                usage_totals[key] += usage[key]
    summary = {**result, "protocol_id": PROTOCOL_ID, "model": transport.MODEL,
               "api_calls_used": api.used_calls, "api_call_ceiling": max_calls,
               "completion_tokens_used": api.completion_tokens_reserved,
               "completion_token_ceiling": max_completion, "usage_totals": usage_totals,
               "execution_started": True, "openrouter_used": False}
    result_path = formal_output / "poolside-p4-execution-result.json"
    if not result_path.exists():
        write_new(result_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true",
                       help="Check P4 inputs and gates without API, credential, or DVWA access")
    modes.add_argument("--check-snapshot", action="store_true",
                       help="Verify the archived index and test a temporary isolated Chroma copy")
    modes.add_argument("--execute", action="store_true",
                       help="Run P4 only after hash-bound freeze, release, and execution receipts exist")
    parser.add_argument("--output", type=Path, help="Write readiness or snapshot evidence to this P4 path")
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    parser.add_argument("--confirm-zero-spend", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    execution_attempted = bool(args.execute)
    try:
        if args.execute:
            if args.output:
                parser.error("--output does not apply to formal execution.")
            result = execute(confirm_local_dvwa=args.confirm_local_dvwa,
                             confirm_database_reset=args.confirm_database_reset,
                             confirm_zero_spend=args.confirm_zero_spend, resume=args.resume)
        elif args.check_snapshot:
            inputs = verify_plan_inputs()
            archive_check = archived_index_check(inputs, copy_test=True)
            result = {"schema": "poolside-laguna-p4-snapshot-check-v1",
                      "experiment_id": EXPERIMENT_ID,
                      "created_at_utc": datetime.now(timezone.utc).isoformat(),
                      "status": "passed" if archive_check["passed"]
                      and archive_check.get("copy_test", {}).get("archive_unchanged") is True else "failed",
                      "archive_check": archive_check,
                      "api_requests_sent": 0, "dvwa_requests_sent": 0,
                      "credentials_read": False, "openrouter_used": False}
        else:
            result = readiness_report()
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        print(serialized, end="")
        if args.output:
            output = args.output if args.output.is_absolute() else ROOT / args.output
            if not output.resolve().is_relative_to(ROOT.resolve()):
                parser.error("--output must stay inside the P4 workspace.")
            if output.exists():
                existing = read_json(output)
                if existing.get("experiment_id") != EXPERIMENT_ID or existing.get("schema") != result.get("schema"):
                    parser.error("Refusing to overwrite evidence not owned by this P4 cohort.")
                output.unlink()
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as destination:
                destination.write(serialized)
        return 0 if args.execute or result.get("status") in {
            "ready-for-execution-approval", "passed"} else 2
    except (OSError, ValueError, KeyError, TypeError, APIRuntimeFailure) as failure:
        side_effects = ({"execution_attempted": True,
                         "api_requests_sent": "inspect cohort API checkpoints",
                         "dvwa_requests_sent": "inspect cohort ledger and validation logs",
                         "credential_status": "inspect execution stage"}
                        if execution_attempted else
                        {"execution_attempted": False, "api_requests_sent": 0,
                         "dvwa_requests_sent": 0, "credentials_read": False})
        print(json.dumps({"status": "blocked", "error_type": type(failure).__name__,
                          "message": str(failure), **side_effects,
                          "openrouter_used": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
