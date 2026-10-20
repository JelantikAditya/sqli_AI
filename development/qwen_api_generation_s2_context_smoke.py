"""One-request Qwen probe with verified stock DVWA Low S2 SQL context."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path

import qwen_api_generation_reasoning_control_smoke as prior_run
from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import (COMPACT_S2_CONTEXT_PROMPT_VERSION,
                                 parse, prepare_compact_s2_low_context)


ROOT = Path(__file__).resolve().parents[1]
PRIOR = prior_run.OUT
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v7-s2-context"
SCENARIO_ID = "S2"
TARGET_SOURCE_SHA256 = "28e34b5f7f4dd2ae1a38b1fae4c1bf67aaf3b98791c4a6c7560e322d1079f73a"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def evidence_inputs() -> dict:
    source = prior_run.inputs()
    prior_plan, _ = prior_run.verified_plan()
    old_result_path = PRIOR / "result.json"
    old_result = json.loads(old_result_path.read_text(encoding="utf-8"))
    if old_result["api"]["status"] != "ok" or old_result["generation"]["status"] != "generated":
        raise ValueError("The prior S2 response is not a parsed candidate")

    ineffective_path = PRIOR / "dvwa-validation.jsonl"
    control_path = PRIOR / "context-control-id0-validation.jsonl"
    ineffective_records = read_jsonl(ineffective_path)
    control_records = read_jsonl(control_path)
    ineffective_evidence = next(row for row in ineffective_records
                                if row.get("record_type") == "candidate_evidence")
    control_evidence = next(row for row in control_records
                            if row.get("record_type") == "candidate_evidence")
    if (ineffective_evidence["evidence_status"] != "CONSISTENT_NEGATIVE"
            or ineffective_evidence["valid_confirmation_count"] != 3
            or control_evidence["evidence_status"] != "CONSISTENT_POSITIVE"
            or control_evidence["valid_confirmation_count"] != 3):
        raise ValueError("Prior S2 DVWA evidence does not match the pinned pilot outcomes")

    ineffective_payloads = [row for row in ineffective_records if row.get("record_type") == "payload"]
    control_payloads = [row for row in control_records if row.get("record_type") == "payload"]
    if len(ineffective_payloads) != 9 or len(control_payloads) != 9:
        raise ValueError("Expected three complete baseline/true/false confirmation sets")
    prior_candidate = old_result["generation"]["candidate"]
    context_candidate = {"true_payload": "0' OR '1'='1", "false_payload": "0' OR '1'='2"}
    feedback = {
        "previous_qwen_candidate": prior_candidate,
        "previous_qwen_evidence": {
            "evidence_status": ineffective_evidence["evidence_status"],
            "confirmation_signals": ineffective_evidence["confirmation_signals"],
            "true_and_false_both_returned": "user_id_exists",
        },
        "verified_local_context_control": {
            **context_candidate,
            "evidence_status": control_evidence["evidence_status"],
            "confirmation_signals": control_evidence["confirmation_signals"],
            "true_returned": "user_id_exists",
            "false_returned": "user_id_missing",
        },
        "target_sql_context": "SELECT first_name, last_name FROM users WHERE user_id = '$id';",
        "target_source_sha256": TARGET_SOURCE_SHA256,
    }
    pins = {"v6_plan_sha256": sha((PRIOR / "plan.json").read_bytes()),
            "v6_result_sha256": sha(old_result_path.read_bytes()),
            "v6_dvwa_validation_sha256": sha(ineffective_path.read_bytes()),
            "context_control_payload_sha256": sha((PRIOR / "s2-context-control-id0.json").read_bytes()),
            "context_control_validation_sha256": sha(control_path.read_bytes()),
            "dvwa_low_source_sha256": TARGET_SOURCE_SHA256}
    return {**source, "pins": {**source["pins"], **pins}, "feedback": feedback,
            "attempted": [prior_candidate], "prior_plan": prior_plan}


def build_entry(source: dict, settings: ChatSettings) -> dict:
    scenario = source["scenarios"][SCENARIO_ID]
    attempted = source["attempted"]
    prepared = prepare_compact_s2_low_context(scenario, attempted,
                                              feedback=source["feedback"])
    payload = request_payload(prepared["messages"], settings)
    return {"scenario_id": SCENARIO_ID, "technique": scenario["sqli_type"],
            "attempted": attempted, "feedback": source["feedback"], "prepared": prepared,
            "request_sha256": sha(encoded_payload(payload))}


def prepare_plan() -> None:
    source = evidence_inputs()
    settings = ChatSettings(max_tokens=512, timeout_seconds=60,
                            chat_template_kwargs={"enable_thinking": False})
    entry = build_entry(source, settings)
    plan = {"plan_version": 1,
            "scope": "development-one-s2-qwen-vllm-template-option-with-verified-dvwa-context",
            "created_at_utc": stamp(), "prompt_version": COMPACT_S2_CONTEXT_PROMPT_VERSION,
            "settings": asdict(settings), "source_pins": source["pins"], "entry": entry}
    OUT.mkdir(parents=True, exist_ok=False)
    blob = serialize(plan)
    with (OUT / "plan.json").open("xb") as stream:
        stream.write(blob)
    with (OUT / "plan.receipt.json").open("xb") as stream:
        stream.write(serialize({"plan_sha256": sha(blob)}))
    print(json.dumps({"status": "prepared", "scenario_id": SCENARIO_ID,
                      "prompt_version": COMPACT_S2_CONTEXT_PROMPT_VERSION,
                      "request_sha256": entry["request_sha256"], "output_dir": str(OUT)}))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    source = evidence_inputs()
    if (plan["source_pins"] != source["pins"]
            or plan["prompt_version"] != COMPACT_S2_CONTEXT_PROMPT_VERSION):
        raise ValueError("Prompt or evidence changed")
    settings = ChatSettings(**plan["settings"])
    if build_entry(source, settings) != plan["entry"]:
        raise ValueError("Prepared request changed")
    return plan, settings


def run() -> None:
    plan, settings = verified_plan()
    started, result_path = OUT / "attempt-started.json", OUT / "result.json"
    if started.exists() or result_path.exists():
        raise RuntimeError("This is a one-request plan and already has an attempt")
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("Enter the provided HCNSEC key: ")
    client = QwenAPIClient(key, settings=settings)
    with started.open("xb") as stream:
        stream.write(serialize({"scenario_id": SCENARIO_ID, "started_at_utc": stamp(),
                                "request_sha256": plan["entry"]["request_sha256"]}))
    try:
        api = client.chat(plan["entry"]["prepared"]["messages"])
    except Exception as exc:
        api = {"status": "client-exception", "halt": True,
               "exception_type": type(exc).__name__}
    parsed = parse(plan["entry"]["prepared"], plan["entry"]["attempted"], "boolean_pair", api)
    safe = json.loads(redact(json.dumps({"scenario_id": SCENARIO_ID, "api": api,
                                          "generation": parsed, "finished_at_utc": stamp()},
                                         ensure_ascii=False, allow_nan=False), key))
    with result_path.open("xb") as stream:
        stream.write(serialize(safe))
    print(json.dumps({"scenario_id": SCENARIO_ID, "api_status": api.get("status"),
                      "generation_status": parsed["status"],
                      "candidate_generated": parsed["candidate"] is not None,
                      "elapsed_seconds": api.get("elapsed_seconds"),
                      "usage": api.get("usage"),
                      "finish_reason": api.get("finish_reason")}, ensure_ascii=False))


def report() -> None:
    plan, _ = verified_plan()
    result_path = OUT / "result.json"
    if not result_path.exists():
        print(json.dumps({"scope": plan["scope"], "status": "pending",
                          "scenario_id": SCENARIO_ID}, ensure_ascii=False))
        return
    result = json.loads(result_path.read_text(encoding="utf-8"))
    print(json.dumps({"scope": plan["scope"], "scenario_id": SCENARIO_ID,
                      "api_status": result["api"]["status"],
                      "generation_status": result["generation"]["status"],
                      "candidate": result["generation"]["candidate"],
                      "finish_reason": result["api"].get("finish_reason"),
                      "usage": result["api"].get("usage")},
                     ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_plan()
    elif args.run:
        run()
    else:
        report()


if __name__ == "__main__":
    main()
