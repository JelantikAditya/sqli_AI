"""One-request compatibility probe for Qwen's vLLM non-thinking option."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path

import qwen_api_generation_feedback_summary_smoke as source_run
from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import COMPACT_PROMPT_VERSION, parse, prepare_compact


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v5-feedback-summary"
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v6-template-kwargs"
SCENARIO_ID = "S2"
PROBE_KIND = "boolean_pair"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def inputs() -> dict:
    source = source_run.inputs()
    plan_blob = (PREVIOUS / "plan.json").read_bytes()
    receipt = json.loads((PREVIOUS / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(plan_blob) != receipt["plan_sha256"]:
        raise ValueError("Prior plan receipt mismatch")
    results = {}
    for sid in ("S2", "S3"):
        blob = (PREVIOUS / sid / "result.json").read_bytes()
        result = json.loads(blob)
        if result["api"]["status"] != "truncated":
            raise ValueError("Expected recorded truncation for " + sid)
        results[sid] = sha(blob)
    return {**source, "pins": {**source["pins"],
                                "prior_summary_plan_sha256": sha(plan_blob),
                                "prior_summary_results_sha256": results}}


def build_entry(source: dict, settings: ChatSettings) -> dict:
    scenario = source["scenarios"][SCENARIO_ID]
    attempted = [source["candidates"][SCENARIO_ID]]
    feedback = source["feedback"][SCENARIO_ID]
    prepared = prepare_compact(scenario, attempted, candidate_count=1, feedback=feedback)
    payload = request_payload(prepared["messages"], settings)
    return {"scenario_id": SCENARIO_ID, "technique": scenario["sqli_type"],
            "attempted": attempted, "feedback": feedback, "prepared": prepared,
            "request_sha256": sha(encoded_payload(payload))}


def prepare_plan() -> None:
    source = inputs()
    settings = ChatSettings(max_tokens=1024, timeout_seconds=120,
                            chat_template_kwargs={"enable_thinking": False})
    entry = build_entry(source, settings)
    plan = {"plan_version": 1,
            "scope": "development-one-s2-qwen-vllm-template-option-compatibility-probe",
            "created_at_utc": stamp(), "prompt_version": COMPACT_PROMPT_VERSION,
            "settings": asdict(settings), "source_pins": source["pins"],
            "entry": entry}
    OUT.mkdir(parents=True, exist_ok=False)
    blob = serialize(plan)
    with (OUT / "plan.json").open("xb") as stream:
        stream.write(blob)
    with (OUT / "plan.receipt.json").open("xb") as stream:
        stream.write(serialize({"plan_sha256": sha(blob)}))
    print(json.dumps({"status": "prepared", "scenario_id": SCENARIO_ID,
                      "request_sha256": entry["request_sha256"],
                      "output_dir": str(OUT)}))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    source = inputs()
    if plan["source_pins"] != source["pins"] or plan["prompt_version"] != COMPACT_PROMPT_VERSION:
        raise ValueError("Source evidence or prompt changed")
    settings = ChatSettings(**plan["settings"])
    entry = build_entry(source, settings)
    if entry != plan["entry"]:
        raise ValueError("Prepared request changed")
    return plan, settings


def run() -> None:
    plan, settings = verified_plan()
    started, result_path = OUT / "attempt-started.json", OUT / "result.json"
    if started.exists() or result_path.exists():
        raise RuntimeError("This is a one-request plan and already has an attempt")
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("Enter a NEW HCNSEC key: ")
    client = QwenAPIClient(key, settings=settings)
    with started.open("xb") as stream:
        stream.write(serialize({"scenario_id": SCENARIO_ID, "started_at_utc": stamp(),
                                "request_sha256": plan["entry"]["request_sha256"]}))
    try:
        api = client.chat(plan["entry"]["prepared"]["messages"])
    except Exception as exc:
        api = {"status": "client-exception", "halt": True,
               "exception_type": type(exc).__name__}
    parsed = parse(plan["entry"]["prepared"], plan["entry"]["attempted"], PROBE_KIND, api)
    safe = json.loads(redact(json.dumps({"scenario_id": SCENARIO_ID, "api": api,
                                          "generation": parsed, "finished_at_utc": stamp()},
                                         ensure_ascii=False, allow_nan=False), key))
    with result_path.open("xb") as stream:
        stream.write(serialize(safe))
    print(json.dumps({"scenario_id": SCENARIO_ID,
                      "api_status": api.get("status"),
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
                      "candidate_generated": result["generation"]["candidate"] is not None,
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
