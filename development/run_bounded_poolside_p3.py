"""Validate or execute a fresh Poolside P3 pilot using the existing DVWA engine.

Default is offline validation. Execution requires explicit local-target,
database-reset and API-use flags. Existing Qwen sources and runs are preserved.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator

import run_qwen_api_experiments as engine
import qwen_api_p2_analysis as analysis
import qwen_api_p3_v5_generation as retry_generation
from qwen_api_runtime import APIRuntimeFailure
from poolside_p3_runtime import CheckpointedPoolsideAPI
import run_poolside_smoke as transport
import run_poolside_contract_smoke as contract
from run_poolside_generation_preflight import write_new
from run_qwen_api_p2_eval import DEFAULT_REQUESTS, load_requests


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "poolside-laguna-s21-sqli-v1-pilot"
EXPERIMENT_ID = "poolside-s21-p3-r1-20261022"
PLAN_PATH = ROOT / "development/poolside_p3_plan.template.json"
BUDGET_PATH = ROOT / "development/poolside_p3_budget_20261022.json"
P2_PROFILE = "poolside-laguna-s-2.1-p2-evidence-v1-no-thinking"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analysis_callback(api, attempt_directory: Path, context: dict):
    def analyze(document: dict, candidate_context: dict) -> dict:
        engine.analyze_response.validate_input(document)
        engine.analyze_response.validate_case(document, candidate_context)
        if document["runtime_status"] != "valid" or not document["baseline_valid"]:
            return engine.analyze_response.normalize_analysis(document, None, candidate_context, {
                "prompt_version": analysis.PROMPT_VERSION, "analysis_gate_version": "poolside-p3-v1",
                "analysis_skipped": "runtime_or_baseline_invalid", "api_call_performed": False})
        prepared = analysis.prepare(document)
        messages = prepared["payload"]["messages"]
        expected_hash = contract.request_hash(CheckpointedPoolsideAPI.payload("analysis", messages))
        result, checkpoint = api.chat("analysis", messages, attempt_directory)
        if checkpoint["request_sha256"] != expected_hash:
            raise APIRuntimeFailure("api_analysis_profile_mismatch", checkpoint)
        parsed = analysis.parse(document, prepared, result)
        provenance = {"prompt_version": analysis.PROMPT_VERSION, "analysis_gate_version": "poolside-p3-v1",
                      "analysis_profile_id": P2_PROFILE, "analysis_document_sha256": prepared["document_sha256"],
                      "analysis_schema_sha256": prepared["schema_sha256"], "api_model": result.get("reported_model"),
                      "api_request_sha256": expected_hash, "api_response_id": result.get("response_id"),
                      "api_finish_reason": result.get("finish_reason"), "api_usage": result.get("usage"),
                      "api_checkpoint": checkpoint, "analysis_parser_status": parsed["status"],
                      "analysis_parser_error": parsed.get("error"), "model_summary_warnings": parsed.get("warnings", []),
                      "model_confirmation_summary": (parsed.get("model_output") or {}).get("confirmation_summary")}
        output = parsed.get("model_output") if parsed["status"] == "ok" else None
        if output is None:
            provenance.update(rejected_model_output=parsed.get("model_output"), rejected_raw_response=result.get("content"))
        else:
            output = {key: value for key, value in output.items() if key != "confirmation_summary"}
        return engine.analyze_response.normalize_analysis(document, output, candidate_context, provenance)
    return analyze


@contextmanager
def poolside_callbacks():
    # The existing engine exposes these serial callback hooks. Restore both on exit.
    old_generation, old_analysis = engine.make_generation_callback, engine.make_analysis_callback
    engine.make_generation_callback = retry_generation.make_generation_callback
    engine.make_analysis_callback = analysis_callback
    try:
        yield
    finally:
        engine.make_generation_callback, engine.make_analysis_callback = old_generation, old_analysis


def prepare(plan_path: Path = PLAN_PATH, budget_path: Path = BUDGET_PATH) -> tuple:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    Draft202012Validator(engine.local_runner.read_json(engine.PLAN_SCHEMA_PATH)).validate(plan)
    if plan["experiment_id"] != EXPERIMENT_ID or plan["dataset"] != "pilot":
        raise ValueError("Only this fresh Poolside pilot ID is supported.")
    if budget["experiment_id"] != EXPERIMENT_ID or digest(plan_path) != budget["plan_sha256"]:
        raise ValueError("Budget belongs to a different plan.")
    if (budget["max_api_calls"] != 960 or budget["max_wall_seconds"] != 21600
            or budget["automatic_transport_retries"] != 0 or budget["automatic_replacement_attempts"] != 0):
        raise ValueError("Unsupported pilot budget.")
    for path, expected in budget["runtime_source_sha256"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("Frozen runtime source changed: " + path)
    p2 = ROOT / budget["p2_run_dir"]
    p2_plan = engine.local_runner.read_json(p2 / "plan.json")
    assessment = engine.local_runner.read_json(p2 / "evaluation-assessment.json")
    if (p2_plan["profile_id"] != P2_PROFILE or assessment["metrics"]["scored_count"] != 18
            or assessment["metrics"]["exact_agreement_count"] != 18):
        raise ValueError("The pinned Poolside P2 evidence is incomplete.")
    if p2_plan["timeout_seconds"] != 60 or p2_plan["max_tokens"] != 2048 or p2_plan["thinking"] is not False:
        raise ValueError("Pilot profile differs from validated Poolside P2.")
    p2_rows = {row["review_id"]: row for row in p2_plan["entries"]}
    for row in load_requests(DEFAULT_REQUESTS)[0]:
        prepared = analysis.prepare(row["document"])
        payload = CheckpointedPoolsideAPI.payload("analysis", prepared["payload"]["messages"])
        if payload != p2_rows[row["review_id"]]["prepared"]["payload"]:
            raise ValueError("Pilot analysis payload differs from the validated P2 packet.")
    protocol = copy.deepcopy(engine.local_runner.load_protocol())
    protocol.update(protocol_id=PROTOCOL_ID, status="pilot")
    protocol["methodology"].update(model_transport="poolside-hosted-chat-api",
                                  llm_pipeline_framework="custom-serial-checkpointed-api-adapter",
                                  api_random_seed="not-sent; replicate-seed-is-metadata-only",
                                  api_analysis_profile=P2_PROFILE,
                                  api_transport_timeouts_seconds={"generation": 60, "analysis": 60},
                                  generation_retry_policy_id=retry_generation.RETRY_POLICY_ID)
    protocol["generation"].update(model=transport.MODEL, num_predict=1024)
    validated = engine.local_runner.validate_plan(plan, protocol, ROOT, verify_index=True)
    estimate = engine.estimate_api_calls(validated, protocol)
    if estimate != 960:
        raise ValueError("Pilot scope or request estimate changed.")
    config = {"limits": {"max_total_api_calls": 960, "max_retrieved_chars_per_chunk": 1800}}
    plan_hash = engine.sha256_bytes(engine.canonical_json({key: value for key, value in validated.items()
                                                          if not key.endswith("_resolved")}))
    protocol_hash = engine.sha256_bytes(engine.canonical_json(protocol))
    directory = ROOT / "results/raw/pilot" / EXPERIMENT_ID
    if directory.exists():
        raise ValueError("A Poolside pilot with this ID already exists; resume and overwrite are refused.")
    return validated, protocol, budget, config, plan_hash, protocol_hash, directory


def run(*, execute=False, confirm_local_dvwa=False, confirm_database_reset=False, confirm_api_spending=False) -> dict:
    plan, protocol, budget, config, plan_hash, protocol_hash, directory = prepare()
    slots = engine.local_runner.planned_units(plan, protocol, ROOT)
    applicable = [slot for slot in slots if slot["status"] != "excluded"]
    candidates = len(applicable) * protocol["generation"]["candidate_budget"]
    summary = {"experiment_id": EXPERIMENT_ID, "protocol_id": PROTOCOL_ID, "model": transport.MODEL,
               "planned_slots": len(slots), "applicable_units": len(applicable),
               "llm_units": sum(slot["condition_id"] in {"A", "B"} for slot in applicable),
               "candidate_budget": candidates,
               "logical_confirmations": candidates * protocol["validation"]["confirmations_per_candidate"],
               "worst_case_api_calls": 960, "max_wall_seconds": 21600,
               "analysis_payloads_matching_p2": 18, "execution_started": False}
    if not execute:
        return summary
    if not (confirm_local_dvwa and confirm_database_reset and confirm_api_spending):
        raise ValueError("Execution needs explicit local-DVWA, database-reset, and API-use flags.")
    engine.check_pilot_receipt(plan)
    engine.require_local_target(protocol["target_origin"])
    key = transport.load_key()
    if not key:
        raise ValueError("No Poolside key is configured.")
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    ledger = engine.local_runner.ExperimentLedger.create(directory, plan, protocol, plan_hash, protocol_hash, ROOT)
    write_new(directory / "poolside-runtime.snapshot.json", budget)
    for relative in budget["runtime_source_sha256"]:
        target = directory / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write((ROOT / relative).read_bytes())
    api = CheckpointedPoolsideAPI(key, directory, max_calls=960, max_seconds=21600)
    def execute_one(unit, attempt, current_plan, current_protocol, data_dir, root):
        api.require_time()
        print(json.dumps({"event": "unit-start", "scenario": unit["scenario_id"],
                          "condition": unit["condition_id"], "api_calls": api.used_calls}), flush=True)
        return engine.execute_api_unit(unit, attempt, current_plan, current_protocol, data_dir, root, api, config)
    with poolside_callbacks(), engine.local_runner.experiment_lock(directory):
        result = engine.local_runner.execute_ledger(ledger, plan, protocol, directory, execute=True,
                    retry_invalid=False, recovered=0, root=ROOT, execute_one=execute_one)
    result.update(protocol_id=PROTOCOL_ID, api_calls_used=api.used_calls, execution_started=True)
    write_new(directory / "poolside-execution-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    parser.add_argument("--confirm-database-reset", action="store_true")
    parser.add_argument("--confirm-api-spending", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(execute=args.execute, confirm_local_dvwa=args.confirm_local_dvwa,
                         confirm_database_reset=args.confirm_database_reset,
                         confirm_api_spending=args.confirm_api_spending), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
