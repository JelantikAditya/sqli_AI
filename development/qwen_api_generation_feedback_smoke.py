"""Regenerate S2/S3 once using typed executor evidence from the development pilot."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path

from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import COMPACT_PROMPT_VERSION, parse, prepare_compact


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v3"
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v4-feedback-canonical"
CATALOG = ROOT / "dvwa/experiment_scenarios.json"
IDS = ("S2", "S3")
KINDS = {"boolean-based blind": "boolean_pair", "time-based blind": "single_time"}
SOURCE_PATHS = {
    "generation_plan": BASE / "plan.json",
    "generation_manifest": BASE / "dvwa-input/manifest.json",
    "context_probe": BASE / "dvwa-input/context-probe-S2.json",
    "validation_S2": BASE / "dvwa-input/validation-S2.jsonl",
    "validation_S3": BASE / "dvwa-input/validation-S3.jsonl",
}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def json_sha(value) -> str:
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode())


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode()


def scenarios():
    blob = CATALOG.read_bytes()
    rows = {row["scenario_id"]: row for row in json.loads(blob)["scenarios"]}
    if not all(sid in rows for sid in IDS):
        raise ValueError("Missing S2/S3 scenario")
    return rows, sha(blob)


def inputs():
    plan_blob = SOURCE_PATHS["generation_plan"].read_bytes()
    plan = json.loads(plan_blob)
    results = {}
    candidates = {}
    for sid in IDS:
        blob = (BASE / sid / "result.json").read_bytes()
        row = json.loads(blob)
        if row["api"]["status"] != "ok" or row["generation"]["status"] != "generated":
            raise ValueError("Prior API candidate is not usable: " + sid)
        candidates[sid] = row["generation"]["candidate"]
        results[sid] = sha(blob)
    parsed = {}
    for sid in IDS:
        rows = [json.loads(line) for line in SOURCE_PATHS["validation_" + sid].read_text(encoding="utf-8").splitlines() if line]
        payloads = [row for row in rows if row.get("record_type") == "payload"]
        if len(payloads) != 9:
            raise ValueError("Expected nine executor observations for " + sid)
        parsed[sid] = payloads
    context_blob = SOURCE_PATHS["context_probe"].read_bytes()
    context = json.loads(context_blob)
    if context["confirmation_count"] != 3:
        raise ValueError("Context probe is incomplete")
    feedback = {}
    for sid in IDS:
        payloads = parsed[sid]
        trials = defaultdict(dict)
        for row in payloads:
            role = row["payload_role"]
            trials[row["confirmation_index"]][role] = {
                "http_status": row["http_status"],
                "elapsed_ms": row["response_time_ms"],
                "diagnostics": row["response_indicators"],
                "content_markers": row["content_markers"],
            }
        if sid == "S2":
            summary = {"previous_observations": [
                {"trial": trial, **roles} for trial, roles in sorted(trials.items())],
                "same_endpoint_quote_boundary_probe": [
                    {"trial": row["trial"], "http_status": row["candidate_status"],
                     "diagnostics": row["new_sql_diagnostics"],
                     "content_signature": row["candidate_signature"]}
                    for row in context["results"]]}
        else:
            deltas = []
            for trial, roles in sorted(trials.items()):
                single = roles["single"]
                control = roles["no_delay_control"]
                deltas.append({"trial": trial,
                               "single": single,
                               "no_delay_control": control,
                               "delta_ms": round(single["elapsed_ms"] - control["elapsed_ms"], 2)})
            summary = {"previous_observations": deltas,
                       "same_endpoint_quote_boundary_probe": [
                           {"trial": row["trial"], "http_status": row["candidate_status"],
                            "diagnostics": row["new_sql_diagnostics"],
                            "content_signature": row["candidate_signature"]}
                           for row in context["results"]]}
        feedback[sid] = summary
    pins = {"catalog_sha256": sha(CATALOG.read_bytes()),
            "previous_plan_sha256": sha(plan_blob),
            "previous_results_sha256": results,
            "evidence_sha256": {name: sha(path.read_bytes()) for name, path in SOURCE_PATHS.items()}}
    return {"scenarios": scenarios()[0], "candidates": candidates,
            "feedback": feedback, "pins": pins}


def prepare_plan() -> None:
    source = inputs()
    settings = ChatSettings(max_tokens=1024, timeout_seconds=120)
    entries = []
    for sid in IDS:
        prepared = prepare_compact(source["scenarios"][sid], [source["candidates"][sid]],
                                   candidate_count=1, feedback=source["feedback"][sid])
        payload = request_payload(prepared["messages"], settings)
        entries.append({"scenario_id": sid, "technique": source["scenarios"][sid]["sqli_type"],
                        "attempted": [source["candidates"][sid]], "feedback": source["feedback"][sid],
                        "prepared": prepared, "request_sha256": sha(encoded_payload(payload))})
    plan = {"plan_version": 1, "scope": "development-one-regeneration-using-typed-executor-feedback",
            "created_at_utc": stamp(), "prompt_version": COMPACT_PROMPT_VERSION,
            "settings": asdict(settings), "source_pins": source["pins"], "entries": entries}
    OUT.mkdir(parents=True, exist_ok=False)
    blob = serialize(plan)
    with (OUT / "plan.json").open("xb") as stream:
        stream.write(blob)
    with (OUT / "plan.receipt.json").open("xb") as stream:
        stream.write(serialize({"plan_sha256": sha(blob)}))
    print(json.dumps({"status": "prepared", "planned": len(entries), "output_dir": str(OUT)}))


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
        if entry["attempted"] != [source["candidates"][sid]] or entry["feedback"] != source["feedback"][sid]:
            raise ValueError("Feedback input changed: " + sid)
        prepared = prepare_compact(source["scenarios"][sid], entry["attempted"],
                                   candidate_count=1, feedback=entry["feedback"])
        if prepared != entry["prepared"]:
            raise ValueError("Prepared prompt changed: " + sid)
        payload = request_payload(prepared["messages"], settings)
        if sha(encoded_payload(payload)) != entry["request_sha256"]:
            raise ValueError("Request hash mismatch: " + sid)
    return plan, settings


def run() -> None:
    plan, settings = verified_plan()
    pending = []
    for entry in plan["entries"]:
        path = OUT / entry["scenario_id"]
        started, result = path / "attempt-started.json", path / "result.json"
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
        path = OUT / sid
        path.mkdir(parents=True, exist_ok=True)
        with (path / "attempt-started.json").open("xb") as stream:
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
                                              "generation": parsed, "finished_at_utc": stamp()},
                                             ensure_ascii=False, allow_nan=False), key))
        with (path / "result.json").open("xb") as stream:
            stream.write(serialize(safe))
        print(json.dumps({"scenario_id": sid, "api_status": api.get("status"),
                          "generation_status": parsed["status"], "candidate": parsed["candidate"],
                          "elapsed_seconds": api.get("elapsed_seconds")}, ensure_ascii=False), flush=True)
        if api.get("halt") or parsed.get("halt"):
            break


def report() -> None:
    plan, _ = verified_plan()
    rows = []
    for entry in plan["entries"]:
        path = OUT / entry["scenario_id"] / "result.json"
        if not path.exists():
            rows.append({"scenario_id": entry["scenario_id"], "status": "pending"})
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"scenario_id": entry["scenario_id"],
                     "api_status": result["api"]["status"],
                     "generation_status": result["generation"]["status"],
                     "candidate": result["generation"]["candidate"]})
    print(json.dumps({"scope": plan["scope"], "rows": rows}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--run", action="store_true")
    group.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_plan()
    elif args.run:
        run()
    else:
        report()


if __name__ == "__main__":
    main()
