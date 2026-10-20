"""One-shot compact /no_think Qwen preflight for local DVWA S1-S3; no execution."""

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
from qwen_api_generation import COMPACT_PROMPT_VERSION, parse, prepare_compact


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "dvwa/experiment_scenarios.json"
PRIOR = {
    "v1": ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020",
    "v2": ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v2",
}
OUT = ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v3"
IDS = ("S1", "S2", "S3")
KINDS = {"error-based": "single_error", "boolean-based blind": "boolean_pair",
         "time-based blind": "single_time"}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(serialize(value))


def scenarios():
    blob = CATALOG.read_bytes()
    catalog = json.loads(blob)
    rows = {row["scenario_id"]: row for row in catalog["scenarios"]}
    if not all(sid in rows for sid in IDS):
        raise ValueError("Missing S1-S3 scenarios")
    return rows, sha(blob)


def prior_pins() -> dict:
    pins = {}
    for version, base in PRIOR.items():
        plan_blob = (base / "plan.json").read_bytes()
        receipt = json.loads((base / "plan.receipt.json").read_text(encoding="utf-8"))
        if sha(plan_blob) != receipt["plan_sha256"]:
            raise ValueError("Prior plan receipt mismatch: " + version)
        plan = json.loads(plan_blob)
        result_hashes = {}
        for entry in plan["entries"]:
            sid = entry["scenario_id"]
            result_hashes[sid] = sha((base / sid / "result.json").read_bytes())
        pins[version] = {"plan_sha256": sha(plan_blob), "results_sha256": result_hashes}
    return pins


def prepare_plan() -> None:
    catalog, catalog_hash = scenarios()
    settings = ChatSettings(max_tokens=1024, timeout_seconds=120)
    entries = []
    for sid in IDS:
        prepared = prepare_compact(catalog[sid], [], candidate_count=1)
        payload = request_payload(prepared["messages"], settings)
        entries.append({"scenario_id": sid, "technique": catalog[sid]["sqli_type"],
                        "prepared": prepared, "request_sha256": sha(encoded_payload(payload))})
    plan = {"plan_version": 1, "scope": "development-compact-generation-preflight-no-dvwa-execution",
            "created_at_utc": stamp(), "prompt_version": COMPACT_PROMPT_VERSION,
            "catalog_sha256": catalog_hash, "settings": asdict(settings), "entries": entries,
            "prior_batches": prior_pins()}
    write_new(OUT / "plan.json", plan)
    write_new(OUT / "plan.receipt.json", {"plan_sha256": sha(serialize(plan))})
    print(json.dumps({"status": "prepared", "planned": len(entries), "output_dir": str(OUT)}))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    _, catalog_hash = scenarios()
    if plan["catalog_sha256"] != catalog_hash or plan["prompt_version"] != COMPACT_PROMPT_VERSION:
        raise ValueError("Catalog or prompt version changed")
    if plan["prior_batches"] != prior_pins():
        raise ValueError("Prior preflight artifacts changed")
    settings = ChatSettings(**plan["settings"])
    for entry in plan["entries"]:
        payload = request_payload(entry["prepared"]["messages"], settings)
        if sha(encoded_payload(payload)) != entry["request_sha256"]:
            raise ValueError("Request hash mismatch: " + entry["scenario_id"])
    return plan, settings


def run() -> None:
    plan, settings = verified_plan()
    unfinished = [entry["scenario_id"] for entry in plan["entries"]
                  if (OUT / entry["scenario_id"] / "attempt-started.json").exists()
                  and not (OUT / entry["scenario_id"] / "result.json").exists()]
    if unfinished:
        raise RuntimeError("Unfinished attempt requires audit: " + ", ".join(unfinished))
    pending = [entry for entry in plan["entries"]
               if not (OUT / entry["scenario_id"] / "attempt-started.json").exists()]
    if not pending:
        print(json.dumps({"status": "nothing-pending"}))
        return
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("HCNSEC_API_KEY: ")
    client = QwenAPIClient(key, settings=settings)
    for entry in pending:
        sid = entry["scenario_id"]
        path = OUT / sid
        write_new(path / "attempt-started.json", {"scenario_id": sid, "started_at_utc": stamp(),
                                                   "request_sha256": entry["request_sha256"]})
        try:
            api = client.chat(entry["prepared"]["messages"])
        except Exception as exc:
            api = {"status": "client-exception", "halt": True,
                   "exception_type": type(exc).__name__}
        if api.get("request_sha256") not in (None, entry["request_sha256"]):
            api = {"status": "request-hash-mismatch", "halt": True}
        parsed = parse(entry["prepared"], [], KINDS[entry["technique"]], api)
        safe = json.loads(redact(json.dumps({"scenario_id": sid, "api": api,
                                              "generation": parsed, "finished_at_utc": stamp()},
                                             ensure_ascii=False, allow_nan=False), key))
        write_new(path / "result.json", safe)
        print(json.dumps({"scenario_id": sid, "api_status": api.get("status"),
                          "generation_status": parsed["status"],
                          "candidate": parsed["candidate"],
                          "elapsed_seconds": api.get("elapsed_seconds")}, ensure_ascii=False), flush=True)
        if api.get("halt") or parsed.get("halt"):
            break


def report() -> None:
    plan, _ = verified_plan()
    rows = []
    for entry in plan["entries"]:
        result_path = OUT / entry["scenario_id"] / "result.json"
        if not result_path.exists():
            rows.append({"scenario_id": entry["scenario_id"], "api_status": "pending"})
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rows.append({"scenario_id": entry["scenario_id"], "technique": entry["technique"],
                     "api_status": result["api"]["status"],
                     "generation_status": result["generation"]["status"],
                     "candidate": result["generation"]["candidate"],
                     "elapsed_seconds": result["api"].get("elapsed_seconds")})
    print(json.dumps({"scope": plan["scope"], "prompt_version": plan["prompt_version"],
                      "rows": rows}, ensure_ascii=False, indent=2))


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
