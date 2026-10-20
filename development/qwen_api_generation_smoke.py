"""Checkpointed Qwen API generator preflight for local DVWA S1-S3.

This preflight requests payloads but does not execute them against DVWA.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path

from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import PROMPT_VERSION, parse, prepare


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "dvwa/experiment_scenarios.json"
PREVIOUS_OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020"
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v2"
IDS = ("S2", "S3")


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def serialize(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(serialize(value))


def catalog_scenarios():
    blob = CATALOG.read_bytes()
    catalog = json.loads(blob)
    scenarios = {row["scenario_id"]: row for row in catalog["scenarios"]}
    if not all(cid in scenarios for cid in IDS):
        raise ValueError("Missing S1-S3 scenario")
    return scenarios, sha(blob)


def prepare_plan():
    scenarios, catalog_hash = catalog_scenarios()
    settings = ChatSettings(max_tokens=4096, timeout_seconds=150)
    prior_plan_blob = (PREVIOUS_OUT / "plan.json").read_bytes()
    prior_receipt = json.loads((PREVIOUS_OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(prior_plan_blob) != prior_receipt["plan_sha256"]:
        raise ValueError("Prior plan receipt mismatch")
    prior_results = {}
    for cid in ("S1", "S2", "S3"):
        result = PREVIOUS_OUT / cid / "result.json"
        if not result.exists():
            raise ValueError("Prior result missing: " + cid)
        prior_results[cid] = sha(result.read_bytes())
    entries = []
    for cid in IDS:
        prepared = prepare(scenarios[cid], [], candidate_count=1)
        payload = request_payload(prepared["messages"], settings)
        entries.append({"scenario_id": cid, "technique": scenarios[cid]["sqli_type"],
                        "prepared": prepared, "request_sha256": sha(encoded_payload(payload))})
    plan = {"plan_version": 1, "scope": "development-generation-preflight-no-dvwa-execution",
            "created_at_utc": stamp(), "prompt_version": PROMPT_VERSION,
            "catalog_sha256": catalog_hash, "settings": asdict(settings), "entries": entries,
            "prior_plan_sha256": sha(prior_plan_blob), "prior_results_sha256": prior_results}
    write_new(OUT / "plan.json", plan)
    write_new(OUT / "plan.receipt.json", {"plan_sha256": sha(serialize(plan))})
    print(json.dumps({"status": "prepared", "planned": len(entries), "output_dir": str(OUT)}))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    _, catalog_hash = catalog_scenarios()
    if plan["catalog_sha256"] != catalog_hash or plan["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Catalog or prompt version changed")
    if sha((PREVIOUS_OUT / "plan.json").read_bytes()) != plan["prior_plan_sha256"]:
        raise ValueError("Prior plan changed")
    for cid, expected in plan["prior_results_sha256"].items():
        if sha((PREVIOUS_OUT / cid / "result.json").read_bytes()) != expected:
            raise ValueError("Prior result changed: " + cid)
    settings = ChatSettings(**plan["settings"])
    for entry in plan["entries"]:
        payload = request_payload(entry["prepared"]["messages"], settings)
        if sha(encoded_payload(payload)) != entry["request_sha256"]:
            raise ValueError("Request hash mismatch")
    return plan, settings


def run():
    plan, settings = verified_plan()
    unfinished = [row["scenario_id"] for row in plan["entries"]
                  if (OUT / row["scenario_id"] / "attempt-started.json").exists() and
                  not (OUT / row["scenario_id"] / "result.json").exists()]
    if unfinished:
        raise RuntimeError("Unfinished attempt requires audit: " + ", ".join(unfinished))
    pending = [row for row in plan["entries"]
               if not (OUT / row["scenario_id"] / "attempt-started.json").exists()]
    if not pending:
        print(json.dumps({"status": "nothing-pending"}))
        return
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("HCNSEC_API_KEY: ")
    client = QwenAPIClient(key, settings=settings)
    for entry in pending:
        cid = entry["scenario_id"]
        path = OUT / cid
        write_new(path / "attempt-started.json", {"scenario_id": cid,
                  "started_at_utc": stamp(), "request_sha256": entry["request_sha256"]})
        try:
            api = client.chat(entry["prepared"]["messages"])
        except Exception as exc:
            api = {"status": "client-exception", "halt": True,
                   "exception_type": type(exc).__name__}
        if api.get("request_sha256") not in (None, entry["request_sha256"]):
            api = {"status": "request-hash-mismatch", "halt": True}
        parsed = parse(entry["prepared"], [], {
            "error-based": "single_error", "boolean-based blind": "boolean_pair",
            "time-based blind": "single_time"}[entry["technique"]], api)
        safe = json.loads(redact(json.dumps({"scenario_id": cid, "api": api,
                                              "generation": parsed, "finished_at_utc": stamp()},
                                             ensure_ascii=False, allow_nan=False), key))
        write_new(path / "result.json", safe)
        print(json.dumps({"scenario_id": cid, "api_status": api["status"],
                          "generation_status": parsed["status"],
                          "candidate": parsed["candidate"],
                          "elapsed_seconds": api.get("elapsed_seconds")}, ensure_ascii=False), flush=True)
        if api.get("halt") or parsed.get("halt"):
            break


def report():
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


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    action.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_plan()
    elif args.run:
        run()
    else:
        report()


if __name__ == "__main__":
    main()
