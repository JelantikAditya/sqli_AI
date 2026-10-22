"""Replay saved Poolside P3 generation, without API, target, or credential access."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
import qwen_api_generation as parser
import run_qwen_api_experiments as engine
import run_poolside_contract_smoke as contract
from jsonschema import Draft202012Validator


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def classify(content, schema, parsed):
    try:
        output = json.loads(content, object_pairs_hook=parser._unique_keys)
    except json.JSONDecodeError as error:
        return {"category": "json_syntax", "line": error.lineno, "column": error.colno}
    except (TypeError, ValueError):
        return {"category": "json_type_or_duplicate_key"}
    if list(Draft202012Validator(schema).iter_errors(output)):
        return {"category": "schema_violation"}
    statuses = Counter(row["status"] for row in parsed["audit"].get("suggestions", []))
    if parsed["status"] == "generated":
        return {"category": "accepted"}
    return {"category": "candidate_rejection", "suggestions": dict(statuses)}


def audit(directory):
    before = inventory(directory)
    calls, units, mismatches = [], [], []
    for result_path in sorted(directory.glob("attempts/*/*/qwen-api-adaptive-result.json")):
        result = read(result_path)
        context = result["context"]
        scenario = next(s for s in engine.local_runner.load_catalog()["scenarios"]
                        if s["scenario_id"] == context["scenario_id"])
        probe = scenario["probe_kind"]
        schema = parser.output_schema(probe, 1)
        accepted, rejected_by_slot = [], {}
        accepted_calls = []
        events = read(result_path.parent / "adaptive-generation-audit.json")["events"]
        unit_calls = []
        for event in events:
            if event["kind"] != "generation":
                continue
            saved = event["data"]
            a = saved["audit"]
            slot = saved["slot"]
            rejected = rejected_by_slot.setdefault(slot, [])
            call = directory / a["checkpoint"]["checkpoint_directory"]
            request, response = read(call / "request.json"), read(call / "result.json")["result"]
            prepared = {"prompt_version": a["prompt_version"], "slot_id": slot,
                        "family_index": a["family_index"], "schema": schema}
            parsed = parser.parse(prepared, [*accepted, *rejected], probe, response)
            status = parsed["status"]
            if parsed["candidate"] is not None:
                try:
                    engine.validate_candidate_policy(parsed["candidate"], probe, context["scenario_id"])
                except (KeyError, ValueError):
                    status = "invalid_candidate_policy"
            if status != saved["status"]:
                mismatches.append({"call_id": call.name, "saved": saved["status"], "replayed": status})
            reason = classify(response.get("content"), schema, parsed)
            row = {"scenario": context["scenario_id"], "condition": context["condition_id"],
                   "slot": slot, "retry": saved["retry"], "status": status,
                   "reason": reason, "family": a["variation_family"], "call_id": call.name,
                   "request_sha256": request["request_sha256"],
                   "request_hash_valid": contract.request_hash(request["payload"]) == request["request_sha256"] == response["request_sha256"],
                   "http_status": response["http_status"], "finish_reason": response.get("finish_reason"),
                   "response_sha256": digest(call / "result.json"),
                   "content": response.get("content"), "duplicate_of_accepted_slots": []}
            try:
                output = json.loads(response["content"])
                for candidate in output.get("candidates", []):
                    try:
                        key = parser.structural_key(candidate, probe)
                    except (KeyError, TypeError, ValueError):
                        continue
                    row["duplicate_of_accepted_slots"].extend(i + 1 for i, value in enumerate(accepted)
                        if parser.structural_key({"payload": value} if isinstance(value, str) else value, probe) == key)
                if parsed["status"] == "no_valid_distinct_candidate":
                    indices = {s["index"] for s in parsed["audit"].get("suggestions", [])
                               if s["status"] == "duplicate_structure"}
                    for index, candidate in enumerate(output.get("candidates", []), 1):
                        if index in indices and candidate not in rejected and len(rejected) < 3:
                            rejected.append(candidate)
            except (KeyError, TypeError, ValueError):
                pass
            if status == "generated":
                candidate = parsed["candidate"]
                accepted.append(candidate["payload"] if context["scenario_id"] == "S1" else candidate)
                accepted_calls.append(row["call_id"])
                rejected_by_slot.pop(slot, None)
            calls.append(row)
            unit_calls.append(row)
        summary = result["run_summary"]
        if len(accepted) != summary["candidate_count"]:
            mismatches.append({"unit": context["run_id"], "replayed_candidate_count": len(accepted)})
        final_slot = unit_calls[-1]["slot"]
        terminal = [c for c in unit_calls if c["slot"] == final_slot]
        units.append({"scenario": context["scenario_id"], "condition": context["condition_id"],
                      "candidate_count": len(accepted), "budget_complete": summary["budget_complete"],
                      "generation_calls": len(unit_calls), "status_counts": dict(Counter(c["status"] for c in unit_calls)),
                      "terminal_slot": final_slot,
                      "terminal_reasons": [c["reason"] for c in terminal],
                      "terminal_duplicate_slots": [c["duplicate_of_accepted_slots"] for c in terminal],
                      "terminal_unique_request_hashes": len({c["request_sha256"] for c in terminal}),
                      "terminal_unique_response_contents": len({c["content"] for c in terminal})})
    after = inventory(directory)
    partial = [u for u in units if not u["budget_complete"]]
    summary = {"schema": "poolside-generation-replay-audit-v1", "experiment_id": directory.name,
               "api_requests_sent": 0, "dvwa_requests_sent": 0,
               "llm_units": len(units), "complete_units": len(units) - len(partial),
               "partial_units": partial, "generation_calls_replayed": len(calls),
               "status_counts": dict(Counter(c["status"] for c in calls)),
               "rejection_categories": dict(Counter(c["reason"]["category"] for c in calls if c["status"] != "generated")),
               "request_hash_mismatches": sum(not c["request_hash_valid"] for c in calls),
               "replay_mismatches": mismatches, "preserved_files": len(before),
               "input_inventory_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
               "inputs_unchanged": before == after,
               "interpretation": "Replay verifies historical rejection and preservation; it does not predict a new prompt's generation success."}
    if mismatches or before != after or any(not c["request_hash_valid"] for c in calls):
        raise ValueError("Replay or preservation validation failed.")
    return summary, {"summary": summary, "calls": calls, "input_inventory": before}


def write_new(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--directory", type=Path, default=ROOT / "results/raw/pilot/poolside-s21-p3-r1-20261022")
    cli.add_argument("--summary", type=Path, required=True)
    cli.add_argument("--private-details", type=Path, required=True)
    args = cli.parse_args()
    with patch("socket.socket.connect", side_effect=AssertionError("Audit must remain offline")):
        summary, details = audit(args.directory)
    write_new(args.summary, summary)
    write_new(args.private_details, details)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
