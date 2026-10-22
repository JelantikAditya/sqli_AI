"""Evaluate the frozen 18-case evidence packet with a separate Poolside profile.

The inference runner does not read annotations. Each invocation creates a new
run, with one attempt per case and no retries, target traffic, or fallback.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import qwen_api_p2_analysis as analysis
from run_qwen_api_p2_eval import DEFAULT_REQUESTS, load_requests
import run_poolside_contract_smoke as contract
import run_poolside_smoke as transport


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "poolside-laguna-s-2.1-p2-evidence-v1-no-thinking"


def build_plan() -> dict:
    original_rows, original_digest = load_requests(DEFAULT_REQUESTS)
    rows = []
    for original in original_rows:
        if analysis.prepare(original["document"]) != original["prepared"]:
            raise ValueError("Frozen P2 request differs from the current renderer.")
        row = copy.deepcopy(original)
        row["prepared"]["payload"].update(model=transport.MODEL,
                                         chat_template_kwargs={"enable_thinking": False})
        digest = contract.request_hash(row["prepared"]["payload"])
        row["request_sha256"] = row["prepared"]["request_sha256"] = digest
        rows.append(row)
    sources = [Path(__file__), Path(transport.__file__), Path(contract.__file__),
               Path(analysis.__file__), ROOT / "development/qwen_api_analysis.py",
               ROOT / "development/run_qwen_api_p2_eval.py", DEFAULT_REQUESTS]
    return {
        "profile_id": PROFILE, "purpose": "development evidence analysis; not formal FPR/PSR",
        "base_url": transport.BASE_URL, "requested_model": transport.MODEL,
        "origin_requests_sha256": original_digest, "max_requests": 18,
        "max_completion_tokens_total": 18 * 2048, "temperature": 0,
        "max_tokens": 2048, "timeout_seconds": 60, "thinking": False,
        "automatic_retries": 0, "model_fallback": False, "dvwa_requests": 0,
        "prompt_version": analysis.PROMPT_VERSION, "rag_mode": "off", "claim_override": False,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sources},
        "entries": rows,
    }


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def run(plan: dict, key: str, opener=None) -> dict:
    key = transport.validate_key(key)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "results/raw/poolside-p2" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    write_new(destination / "plan.json", plan)
    # Retain actual sources beside the hashes so later edits cannot erase this profile.
    for relative in plan["source_sha256"]:
        if Path(relative).parts[0] == "development":
            target = destination / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write((ROOT / relative).read_bytes())
    opener = opener if opener is not None else transport.build_opener(transport.NoRedirect())
    records = []
    for row in plan["entries"]:
        rid = row["review_id"]
        write_new(destination / "request-started" / (rid + ".json"), {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "request_sha256": row["request_sha256"], "policy": "one attempt; no retry",
        })
        response = transport.request_once(opener, key, "/chat/completions", row["prepared"]["payload"])
        if response.get("request_sha256") != row["request_sha256"]:
            raise ValueError("Sent request differs from the frozen plan.")
        api = contract.api_result(response)
        parsed = analysis.parse(row["document"], row["prepared"], api)
        record = transport.redact({
            "review_id": rid, "technique": row["document"]["technique"],
            "api_status": api["status"], "analysis_status": "parsed" if parsed["status"] == "ok" else "rejected",
            "analysis": parsed, "requested_model": transport.MODEL,
            "reported_model": api.get("reported_model"), "http_status": api["http_status"],
            "elapsed_seconds": api["elapsed_seconds"], "usage": api.get("usage"),
            "request_sha256": row["request_sha256"], "transport": response,
            "request_completion_unknown": api["status"] == "transport-error" and api["http_status"] is None,
            "retry_performed": False,
        }, key)
        write_new(destination / "results" / (rid + ".json"), record)
        records.append(record)
        print(json.dumps({"case": len(records), "review_id": rid,
                          "api_status": api["status"], "parse_status": parsed["status"],
                          "decision": parsed.get("decision"), "warnings": parsed.get("warnings"),
                          "elapsed_seconds": api["elapsed_seconds"]}), flush=True)
        if api.get("halt"):
            break
    full = len(records) == 18
    state = "completed" if full and all(record["api_status"] == "ok" for record in records) else "halted"
    totals = {name: sum((row.get("usage") or {}).get(name, 0) for row in records)
              for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
    manifest = {key: value for key, value in plan.items() if key not in {"entries", "source_sha256"}}
    manifest.update(state=state, run_id="poolside-p2-" + stamp,
                    requests_sha256=plan["origin_requests_sha256"],
                    payload_origin_note="requests_sha256 identifies original evidence packet; actual Poolside payload hashes are in plan entries",
                    requests_sent=len(records), reference_labels_read=False,
                    actual_usage=totals, api_elapsed_seconds=round(sum(row["elapsed_seconds"] for row in records), 3))
    write_new(destination / "run-manifest.json", manifest)
    write_new(destination / "evaluation-results.json", {
        "schema": "poolside-p2-results-v1", "profile_id": PROFILE,
        "requests_sha256": plan["origin_requests_sha256"], "saved_result_count": len(records),
        "cases": [{key: value for key, value in row.items() if key != "transport"} for row in records],
    })
    return {"state": state, "requests_sent": len(records), "actual_usage": totals,
            "api_elapsed_seconds": manifest["api_elapsed_seconds"], "output_dir": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if args.dry_run:
        print(json.dumps({key: value for key, value in plan.items()
                          if key not in {"entries", "source_sha256"}}, indent=2))
        return 0
    key = transport.load_key()
    if not key:
        print(json.dumps({"status": "missing-api-key", "requests_sent": 0}))
        return 2
    result = run(plan, key)
    print(json.dumps(result, indent=2))
    return 0 if result["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
