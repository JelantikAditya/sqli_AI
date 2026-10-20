"""One-shot compact feedback experiment for S2/S3 after DVWA pilot evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys

import qwen_api_generation_feedback_smoke as source_run
from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import COMPACT_PROMPT_VERSION, parse, prepare_compact


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v5-feedback-summary"
FAILED_BATCH = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v4-feedback-canonical"
IDS = ("S2", "S3")
KINDS = {"boolean-based blind": "boolean_pair", "time-based blind": "single_time"}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_feedback(sid: str, feedback: dict) -> dict:
    """Reduce trial records to predeclared observations without changing labels."""
    trials = feedback["previous_observations"]
    if len(trials) != 3:
        raise ValueError("Expected three executor confirmations for " + sid)
    if sid == "S2":
        equal_markers = all(row["true_condition"]["content_markers"] ==
                            row["false_condition"]["content_markers"] for row in trials)
        statuses = {row[role]["http_status"] for row in trials
                    for role in ("true_condition", "false_condition")}
        marker_sets = [set(row[role]["content_markers"]) for row in trials
                       for role in ("true_condition", "false_condition")]
        shared_markers = sorted(set.intersection(*marker_sets))
        return {"confirmations": 3, "http_statuses": sorted(statuses),
                "true_false_content_markers_equal_all_trials": equal_markers,
                "shared_content_markers": shared_markers}
    if sid == "S3":
        deltas = [row["delta_ms"] for row in trials]
        equal_markers = all(row["single"]["content_markers"] ==
                            row["no_delay_control"]["content_markers"] for row in trials)
        statuses = {row[role]["http_status"] for row in trials
                    for role in ("single", "no_delay_control")}
        marker_sets = [set(row[role]["content_markers"]) for row in trials
                       for role in ("single", "no_delay_control")]
        shared_markers = sorted(set.intersection(*marker_sets))
        return {"confirmations": 3, "http_statuses": sorted(statuses),
                "single_control_content_markers_equal_all_trials": equal_markers,
                "shared_content_markers": shared_markers,
                "timing_delta_ms": deltas}
    raise ValueError("Unsupported scenario: " + sid)


def inputs() -> dict:
    source = source_run.inputs()
    feedback = {sid: compact_feedback(sid, source["feedback"][sid]) for sid in IDS}
    failed_plan_blob = (FAILED_BATCH / "plan.json").read_bytes()
    failed_plan = json.loads(failed_plan_blob)
    receipt = json.loads((FAILED_BATCH / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(failed_plan_blob) != receipt["plan_sha256"]:
        raise ValueError("Prior feedback plan receipt mismatch")
    failed_results = {}
    for sid in IDS:
        blob = (FAILED_BATCH / sid / "result.json").read_bytes()
        row = json.loads(blob)
        if row["api"]["status"] not in {"transport-error", "truncated"}:
            raise ValueError("Expected failed diagnostic attempt for " + sid)
        failed_results[sid] = sha(blob)
    return {**source, "feedback": feedback,
            "pins": {**source["pins"],
                     "prior_feedback_plan_sha256": sha(failed_plan_blob),
                     "prior_feedback_results_sha256": failed_results}}


def prepare_plan() -> None:
    source = inputs()
    settings = ChatSettings(max_tokens=1024, timeout_seconds=120)
    entries = []
    for sid in IDS:
        attempted = [source["candidates"][sid]]
        prepared = prepare_compact(source["scenarios"][sid], attempted,
                                   candidate_count=1, feedback=source["feedback"][sid])
        request = request_payload(prepared["messages"], settings)
        entries.append({"scenario_id": sid,
                        "technique": source["scenarios"][sid]["sqli_type"],
                        "attempted": attempted, "feedback": source["feedback"][sid],
                        "prepared": prepared,
                        "request_sha256": sha(encoded_payload(request))})
    plan = {"plan_version": 1,
            "scope": "development-one-regeneration-using-compact-typed-executor-feedback",
            "created_at_utc": stamp(), "prompt_version": COMPACT_PROMPT_VERSION,
            "settings": asdict(settings), "source_pins": source["pins"],
            "entries": entries}
    OUT.mkdir(parents=True, exist_ok=False)
    blob = serialize(plan)
    with (OUT / "plan.json").open("xb") as stream:
        stream.write(blob)
    with (OUT / "plan.receipt.json").open("xb") as stream:
        stream.write(serialize({"plan_sha256": sha(blob)}))
    print(json.dumps({"status": "prepared", "planned": len(entries),
                      "output_dir": str(OUT)}))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    source = inputs()
    if plan["source_pins"] != source["pins"] or plan["prompt_version"] != COMPACT_PROMPT_VERSION:
        raise ValueError("Prompt or source evidence changed")
    settings = ChatSettings(**plan["settings"])
    for entry in plan["entries"]:
        sid = entry["scenario_id"]
        expected_attempted = [source["candidates"][sid]]
        if entry["attempted"] != expected_attempted or entry["feedback"] != source["feedback"][sid]:
            raise ValueError("Feedback input changed: " + sid)
        prepared = prepare_compact(source["scenarios"][sid], expected_attempted,
                                   candidate_count=1, feedback=entry["feedback"])
        if prepared != entry["prepared"]:
            raise ValueError("Prepared prompt changed: " + sid)
        request = request_payload(prepared["messages"], settings)
        if sha(encoded_payload(request)) != entry["request_sha256"]:
            raise ValueError("Request hash mismatch: " + sid)
    return plan, settings


def run() -> None:
    plan, settings = verified_plan()
    pending = []
    for entry in plan["entries"]:
        folder = OUT / entry["scenario_id"]
        started, result = folder / "attempt-started.json", folder / "result.json"
        if started.exists() and not result.exists():
            raise RuntimeError("Unfinished attempt requires audit: " + entry["scenario_id"])
        if not started.exists():
            pending.append(entry)
    if not pending:
        print(json.dumps({"status": "nothing-pending"}))
        return
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("HCNSEC_API_KEY: ")
    client = QwenAPIClient(key, settings=settings)
    for entry in pending:
        sid = entry["scenario_id"]
        folder = OUT / sid
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "attempt-started.json").open("xb") as stream:
            stream.write(serialize({"scenario_id": sid, "started_at_utc": stamp(),
                                    "request_sha256": entry["request_sha256"]}))
        try:
            api = client.chat(entry["prepared"]["messages"])
        except Exception as exc:
            api = {"status": "client-exception", "halt": True,
                   "exception_type": type(exc).__name__}
        if api.get("request_sha256") not in (None, entry["request_sha256"]):
            api = {"status": "request-hash-mismatch", "halt": True}
        parsed = parse(entry["prepared"], entry["attempted"], KINDS[entry["technique"]], api)
        safe = json.loads(redact(json.dumps({"scenario_id": sid, "api": api,
                                              "generation": parsed,
                                              "finished_at_utc": stamp()},
                                             ensure_ascii=False, allow_nan=False), key))
        with (folder / "result.json").open("xb") as stream:
            stream.write(serialize(safe))
        print(json.dumps({"scenario_id": sid, "api_status": api.get("status"),
                          "generation_status": parsed["status"],
                          "candidate": parsed["candidate"],
                          "elapsed_seconds": api.get("elapsed_seconds")},
                         ensure_ascii=False), flush=True)
        if api.get("halt") or parsed.get("halt"):
            break


def report() -> None:
    plan, _ = verified_plan()
    rows = []
    for entry in plan["entries"]:
        result_path = OUT / entry["scenario_id"] / "result.json"
        if not result_path.exists():
            rows.append({"scenario_id": entry["scenario_id"], "status": "pending"})
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rows.append({"scenario_id": entry["scenario_id"],
                     "api_status": result["api"]["status"],
                     "generation_status": result["generation"]["status"],
                     "candidate": result["generation"]["candidate"]})
    print(json.dumps({"scope": plan["scope"], "rows": rows},
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
