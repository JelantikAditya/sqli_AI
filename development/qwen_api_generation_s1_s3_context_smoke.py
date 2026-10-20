"""One-request-per-scenario Qwen prompt test for local DVWA Low S1 and S3.

This checks generation, schema parsing, and local payload policy only. It does
not send generated values to DVWA and never retries an API request.
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
import re
import sys

from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_generation import (COMPACT_S1_CONTEXT_PROMPT_VERSION,
                                 COMPACT_S3_CONTEXT_PROMPT_VERSION, parse,
                                 prepare_compact_s1_low_context,
                                 prepare_compact_s3_low_context)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from run_local_experiments import candidate_policy_violation  # noqa: E402
from validation_loop import matched_no_delay_payload  # noqa: E402


CATALOG = ROOT / "dvwa/experiment_scenarios.json"
OUT = ROOT / "results/raw/development/qwen38-api-generation-s1-s3-context-20261020-v1"
PREVIOUS = {
    "s1_generic": ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v3/S1/result.json",
    "s3_generic": ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v3/S3/result.json",
    "s2_context": ROOT / "results/raw/development/qwen38-api-generation-smoke-20261020-v7-s2-context/result.json",
}
PROMPTS = {
    "S1": (COMPACT_S1_CONTEXT_PROMPT_VERSION, prepare_compact_s1_low_context),
    "S3": (COMPACT_S3_CONTEXT_PROMPT_VERSION, prepare_compact_s3_low_context),
}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(serialize(value))


def source_inputs() -> tuple[dict, str, dict]:
    catalog_blob = CATALOG.read_bytes()
    catalog = json.loads(catalog_blob)
    scenarios = {row["scenario_id"]: row for row in catalog["scenarios"]}
    if not {"S1", "S3"}.issubset(scenarios):
        raise ValueError("The scenario catalog must contain S1 and S3")
    prior_pins = {}
    for name, path in PREVIOUS.items():
        if not path.is_file():
            raise ValueError(f"Required prior development result is missing: {name}")
        prior_pins[name] = sha(path.read_bytes())
    return scenarios, sha(catalog_blob), prior_pins


def make_entries(scenarios: dict, settings: ChatSettings) -> list[dict]:
    entries = []
    for sid in ("S1", "S3"):
        prompt_version, prepare_prompt = PROMPTS[sid]
        prepared = prepare_prompt(scenarios[sid])
        payload = request_payload(prepared["messages"], settings)
        entries.append({
            "scenario_id": sid,
            "technique": scenarios[sid]["sqli_type"],
            "prompt_version": prompt_version,
            "prepared": prepared,
            "request_sha256": sha(encoded_payload(payload)),
        })
    return entries


def prepare_plan() -> None:
    if OUT.exists():
        raise FileExistsError(f"One-shot output already exists; refusing to overwrite: {OUT}")
    scenarios, catalog_hash, prior_pins = source_inputs()
    settings = ChatSettings(max_tokens=512, timeout_seconds=60,
                            chat_template_kwargs={"enable_thinking": False})
    entries = make_entries(scenarios, settings)
    plan = {
        "plan_version": 1,
        "scope": "development-prompt-test-only-no-dvwa-execution-one-request-per-scenario",
        "created_at_utc": stamp(),
        "prompt_versions": {sid: PROMPTS[sid][0] for sid in ("S1", "S3")},
        "catalog_sha256": catalog_hash,
        "prior_result_sha256": prior_pins,
        "settings": asdict(settings),
        "max_requests_per_scenario": 1,
        "entries": entries,
    }
    OUT.mkdir(parents=True, exist_ok=False)
    blob = serialize(plan)
    with (OUT / "plan.json").open("xb") as stream:
        stream.write(blob)
    write_new(OUT / "plan.receipt.json", {"plan_sha256": sha(blob)})
    print(json.dumps({"status": "prepared", "scenarios": ["S1", "S3"],
                      "max_requests_per_scenario": 1, "output_dir": str(OUT)}))


def verified_plan() -> tuple[dict, ChatSettings]:
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if sha(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    scenarios, catalog_hash, prior_pins = source_inputs()
    if (plan["catalog_sha256"] != catalog_hash
            or plan["prior_result_sha256"] != prior_pins
            or plan["prompt_versions"] != {sid: PROMPTS[sid][0] for sid in ("S1", "S3")}
            or plan["max_requests_per_scenario"] != 1):
        raise ValueError("Scenario catalog, prompt version, or request cap changed")
    settings = ChatSettings(**plan["settings"])
    if plan["entries"] != make_entries(scenarios, settings):
        raise ValueError("Prepared prompts or request hashes changed")
    return plan, settings


def candidate_policy(prepared: dict, scenario: dict, parsed: dict) -> dict:
    candidate = parsed.get("candidate")
    if parsed.get("status") != "generated" or candidate is None:
        return {"status": "not_evaluated", "reason": "no_generated_candidate"}
    violation = candidate_policy_violation(candidate, scenario)
    if violation:
        return {"status": "rejected", "reason": violation}
    if scenario["scenario_id"] == "S1":
        return {"status": "passed", "checks": ["schema", "bounded_s1_diagnostic_policy"]}

    value = candidate.get("payload", "")
    sleeps = re.findall(r"\bsleep\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)", value, re.I)
    if (not value.startswith("1'") or len(sleeps) != 1 or float(sleeps[0]) != 2
            or "#" not in value):
        return {"status": "rejected", "reason": "s3_prompt_shape_not_satisfied"}
    try:
        control = matched_no_delay_payload(value)
    except ValueError:
        return {"status": "rejected", "reason": "s3_matched_control_not_constructible"}
    return {"status": "passed", "checks": ["schema", "bounded_time_policy",
                                                  "quoted_id_context", "single_sleep_2",
                                                  "matched_control_constructible"],
            "matched_control": control}


def run() -> None:
    plan, settings = verified_plan()
    for entry in plan["entries"]:
        scenario_dir = OUT / entry["scenario_id"]
        started_path = scenario_dir / "attempt-started.json"
        result_path = scenario_dir / "result.json"
        if started_path.exists() or result_path.exists():
            raise RuntimeError(f"One-request limit already consumed for {entry['scenario_id']}")

    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("HCNSEC_API_KEY: ")
    client = QwenAPIClient(key, settings=settings)
    scenarios, _, _ = source_inputs()
    for entry in plan["entries"]:
        sid = entry["scenario_id"]
        scenario_dir = OUT / sid
        scenario_dir.mkdir(parents=True, exist_ok=False)
        write_new(scenario_dir / "attempt-started.json", {
            "scenario_id": sid, "started_at_utc": stamp(),
            "request_sha256": entry["request_sha256"], "request_number": 1,
        })
        try:
            api = client.chat(entry["prepared"]["messages"])
        except Exception as exc:
            api = {"status": "client-exception", "halt": True,
                   "exception_type": type(exc).__name__}
        if api.get("request_sha256") not in (None, entry["request_sha256"]):
            api = {"status": "request-hash-mismatch", "halt": True}
        parsed = parse(entry["prepared"], [], scenarios[sid]["probe_kind"], api)
        policy = candidate_policy(entry["prepared"], scenarios[sid], parsed)
        safe = json.loads(redact(json.dumps({
            "scenario_id": sid, "api": api, "generation": parsed,
            "candidate_policy": policy, "finished_at_utc": stamp(),
        }, ensure_ascii=False, allow_nan=False), key))
        write_new(scenario_dir / "result.json", safe)
        print(json.dumps({"scenario_id": sid, "api_status": api.get("status"),
                          "generation_status": parsed["status"],
                          "candidate": parsed.get("candidate"),
                          "candidate_policy": policy["status"],
                          "elapsed_seconds": api.get("elapsed_seconds"),
                          "usage": api.get("usage"),
                          "finish_reason": api.get("finish_reason")}, ensure_ascii=False),
              flush=True)
        if api.get("halt") or parsed.get("halt"):
            print(json.dumps({"status": "stopped_after_halt", "remaining_scenarios": [
                row["scenario_id"] for row in plan["entries"]
                if row["scenario_id"] != sid and not (OUT / row["scenario_id"] / "result.json").exists()
            ]}))
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
                     "prompt_version": entry["prompt_version"],
                     "api_status": result["api"]["status"],
                     "generation_status": result["generation"]["status"],
                     "candidate": result["generation"].get("candidate"),
                     "candidate_policy": result["candidate_policy"],
                     "elapsed_seconds": result["api"].get("elapsed_seconds"),
                     "usage": result["api"].get("usage")})
    print(json.dumps({"scope": plan["scope"], "rows": rows}, ensure_ascii=False, indent=2))


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
