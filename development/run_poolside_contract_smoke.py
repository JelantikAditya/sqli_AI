"""Two-request Poolside output-contract smoke, without target execution or scoring.

Reuses the existing generation and P2 analysis renderers/parsers. This is a
new Poolside profile; it does not modify or resume a Qwen experiment.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import qwen_api_generation as generation
import qwen_api_p2_analysis as analysis
from run_qwen_api_p2_eval import DEFAULT_REQUESTS, load_requests
import run_poolside_smoke as transport


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "poolside-laguna-s-2.1-contract-smoke-v1-no-thinking"


def request_hash(payload: dict) -> str:
    # Match the exact bytes serialized by the shared Poolside transport.
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_plan() -> dict:
    rows, packet_hash = load_requests(DEFAULT_REQUESTS)
    row = rows[0]  # Fixed packet order, selected without reading reference labels.
    rebuilt = analysis.prepare(row["document"])
    if rebuilt != row["prepared"]:
        raise ValueError("Frozen P2 request no longer matches the current renderer.")
    catalog_path = ROOT / "dvwa" / "experiment_scenarios.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    scenario = next(item for item in catalog["scenarios"] if item["scenario_id"] == "S1")
    # Use only the black-box scenario coordinates, without source-code SQL hints.
    prepared_generation = generation.prepare_compact(scenario, [], candidate_count=1)
    generation_payload = {
        "model": transport.MODEL, "messages": prepared_generation["messages"],
        "temperature": 0, "max_tokens": 1024, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    prepared_analysis = copy.deepcopy(row["prepared"])
    analysis_payload = copy.deepcopy(prepared_analysis["payload"])
    analysis_payload.update(model=transport.MODEL,
                            chat_template_kwargs={"enable_thinking": False})
    prepared_analysis["payload"] = analysis_payload
    prepared_analysis["request_sha256"] = request_hash(analysis_payload)
    entries = [
        {"stage": "generation", "scenario_id": "S1", "probe_kind": scenario["probe_kind"],
         "prepared": prepared_generation, "payload": generation_payload},
        {"stage": "analysis", "review_id": row["review_id"], "document": row["document"],
         "prepared": prepared_analysis, "payload": analysis_payload},
    ]
    for entry in entries:
        entry["request_sha256"] = request_hash(entry["payload"])
    paths = [Path(__file__), Path(transport.__file__), Path(generation.__file__),
             Path(analysis.__file__), ROOT / "development/qwen_api_analysis.py", catalog_path,
             DEFAULT_REQUESTS]
    return {
        "profile_id": PROFILE, "base_url": transport.BASE_URL, "requested_model": transport.MODEL,
        "purpose": "output-contract-smoke-only; not P2 assessment or P3 execution",
        "max_requests": 2, "max_completion_tokens_total": 3072,
        "transport_timeout_seconds_per_request": 60, "automatic_retries": 0,
        "model_fallback": False, "dvwa_requests": 0, "rag_mode": "off",
        "p2_packet_sha256": packet_hash,
        "profile_change_from_qwen_p2": "Poolside model/endpoint; thinking explicitly off; 60s transport timeout",
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        "entries": entries,
    }


def api_result(result: dict) -> dict:
    wire = result.get("body")
    api = {"status": result["status"], "http_status": result["http_status"],
           "elapsed_seconds": result["elapsed_seconds"], "halt": result["status"] != "ok"}
    if api["status"] != "ok":
        return api
    if not isinstance(wire, dict):
        return {**api, "status": "invalid-response-envelope", "halt": True}
    choices = wire.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message")
    api.update(reported_model=wire.get("model"), response_id=wire.get("id"), usage=wire.get("usage"),
               finish_reason=choice.get("finish_reason"),
               content=message.get("content") if isinstance(message, dict) else None)
    if api["reported_model"] != transport.MODEL:
        api.update(status="model-metadata-mismatch", halt=True)
    elif api["finish_reason"] != "stop":
        api.update(status="unfinished-response", halt=True)
    elif not isinstance(api["content"], str) or not api["content"].strip():
        api.update(status="empty-content", halt=True)
    return api


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def run(plan: dict, key: str) -> dict:
    if not key:
        raise ValueError("No Poolside API key is configured.")
    key = transport.validate_key(key)
    destination = ROOT / "results/raw/poolside-contract-smoke" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True, exist_ok=False)
    write_new(destination / "plan.json", plan)
    opener = transport.build_opener(transport.NoRedirect())
    results = []
    for entry in plan["entries"]:
        stage = entry["stage"]
        write_new(destination / (stage + ".started.json"), {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "request_sha256": entry["request_sha256"],
        })
        response = transport.request_once(opener, key, "/chat/completions", entry["payload"])
        if response.get("request_sha256") != entry["request_sha256"]:
            raise ValueError("The sent request differs from the frozen plan.")
        api = api_result(response)
        if stage == "generation":
            parsed = generation.parse(entry["prepared"], [], entry["probe_kind"], api)
        else:
            parsed = analysis.parse(entry["document"], entry["prepared"], api)
        result = transport.redact({"stage": stage, "transport": response,
                                   "api": api, "parsed": parsed}, key)
        write_new(destination / (stage + ".result.json"), result)
        results.append({"stage": stage, "http_status": api["http_status"],
                        "api_status": api["status"], "parse_status": parsed["status"],
                        "elapsed_seconds": api["elapsed_seconds"], "usage": api.get("usage"),
                        "warnings": parsed.get("warnings", []), "error": parsed.get("error")})
        print(json.dumps(results[-1]), flush=True)
        if api.get("halt") or parsed.get("halt"):
            break
    success = len(results) == 2 and all(row["api_status"] == "ok" and row["parse_status"] in {"ok", "generated"}
                                       for row in results)
    summary = {"status": "ok" if success else "contract-smoke-incomplete-or-failed",
               "profile_id": PROFILE, "requests_sent": len(results), "results": results,
               "dvwa_requests": 0, "reference_labels_read": False, "formal_eligible": False,
               "output_dir": str(destination)}
    write_new(destination / "summary.json", summary)
    return summary


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
    summary = run(plan, key)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
