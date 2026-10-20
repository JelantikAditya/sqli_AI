"""Checkpointed, development-only SQLi evidence diagnosis with Qwen API.

Usage: --prepare, then --run --max-requests 3 for one case per technique,
then --report. A later --run may process the remaining cases without retries.
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
from collections import Counter

import analysis_v5_pilot_cases as cases
from qwen_api_analysis import PROMPT_VERSION, parse, payload_bytes, prepare
from qwen_api_client import ChatSettings, QwenAPIClient, redact


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "results/processed/analysis-v5-pilot-20261020-r2"
PREVIOUS_OUT = ROOT / "results/raw/development/qwen38-api-analysis-diagnosis-20261020-v2"
OUT = ROOT / "results/raw/development/qwen38-api-analysis-diagnosis-20261020-v3"
PINNED_INPUTS = ("inputs.lock.json", "prepared-requests.lock.json", "labels.ai.lock.json")
CALIBRATION = ("pilot-001", "pilot-013", "pilot-025")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


def load_pinned():
    manifest = json.loads((LOCK / "manifest.lock.json").read_text(encoding="utf-8"))
    hashes = {}
    for filename in PINNED_INPUTS:
        path = LOCK / filename
        blob = path.read_bytes()
        hashes[filename] = digest(blob)
        if hashes[filename] != manifest["artifact_sha256"][path.relative_to(ROOT).as_posix()]:
            raise ValueError("Pinned input hash mismatch: " + filename)
    inputs = json.loads((LOCK / PINNED_INPUTS[0]).read_text(encoding="utf-8"))
    requests = json.loads((LOCK / PINNED_INPUTS[1]).read_text(encoding="utf-8"))
    labels = json.loads((LOCK / PINNED_INPUTS[2]).read_text(encoding="utf-8"))
    return inputs, requests, labels, hashes


def make_plan():
    inputs, requests, _, hashes = load_pinned()
    settings = ChatSettings(max_tokens=2048)
    previous_plan = (PREVIOUS_OUT / "plan.json").read_bytes()
    previous_receipt = json.loads((PREVIOUS_OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if digest(previous_plan) != previous_receipt["plan_sha256"]:
        raise ValueError("Previous plan receipt mismatch")
    prior_results = {}
    for row in json.loads(previous_plan)["entries"]:
        cid = row["case_id"]
        attempt = PREVIOUS_OUT / cid / "attempt-started.json"
        result = PREVIOUS_OUT / cid / "result.json"
        if attempt.exists():
            if not result.exists():
                raise ValueError("Previous attempt is unfinished: " + cid)
            prior_results[cid] = digest(result.read_bytes())
    if len(prior_results) != 9:
        raise ValueError("Expected exactly nine prior calibration/development attempts")
    reqs = {(row["case_id"], row["profile"]): row for row in requests}
    if len(inputs) != 42 or len(reqs) != 126 or len(CALIBRATION) != 3:
        raise ValueError("Unexpected frozen pilot inventory")
    order = list(CALIBRATION) + sorted(row["case_id"] for row in inputs
                                       if row["case_id"] not in CALIBRATION)
    docs = {row["case_id"]: row["input"] for row in inputs}
    if set(order) != set(docs) or len(order) != len(docs):
        raise ValueError("Calibration IDs or case IDs mismatch")
    entries = []
    for case_id in order:
        doc = docs[case_id]
        eligible = cases.eligible(doc)
        gate = "prior_attempted" if case_id in prior_results else (
            "eligible" if eligible else "input_invalid")
        entry = {"case_id": case_id, "technique": doc["technique"], "gate": gate}
        if gate == "eligible":
            adapted = prepare(doc, reqs[(case_id, "A")], settings)
            entry.update(prepared=adapted, request_sha256=digest(payload_bytes(adapted)))
        entries.append(entry)
    if Counter(row["gate"] for row in entries) != {
            "eligible": 27, "input_invalid": 6, "prior_attempted": 9}:
        raise ValueError("Expected 27 new, nine prior, and six invalid cases")
    if {row["technique"] for row in entries[:3]} != {
            "error-based", "boolean-based blind", "time-based blind"}:
        raise ValueError("Calibration must cover all three techniques")
    return {"plan_version": 1, "scope": "synthetic-development-only",
            "prompt_version": PROMPT_VERSION, "created_at_utc": now(),
            "settings": asdict(settings), "source_sha256": hashes, "entries": entries,
            "previous_plan_sha256": digest(previous_plan),
            "previous_results_sha256": prior_results}


def prepare_plan():
    plan = make_plan()
    write_new(OUT / "plan.json", plan)
    write_new(OUT / "plan.receipt.json", {"plan_sha256": digest(json_bytes(plan))})
    print(json.dumps({"status": "prepared", "eligible_new": 27, "prior_attempted": 9, "invalid": 6,
                      "output_dir": str(OUT)}, ensure_ascii=False))


def verified_plan():
    blob = (OUT / "plan.json").read_bytes()
    receipt = json.loads((OUT / "plan.receipt.json").read_text(encoding="utf-8"))
    if digest(blob) != receipt["plan_sha256"]:
        raise ValueError("Plan receipt mismatch")
    plan = json.loads(blob)
    _, _, _, hashes = load_pinned()
    if plan["source_sha256"] != hashes or plan["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Pinned source or prompt version changed")
    if digest((PREVIOUS_OUT / "plan.json").read_bytes()) != plan["previous_plan_sha256"]:
        raise ValueError("Previous plan changed")
    for cid, expected_hash in plan["previous_results_sha256"].items():
        if digest((PREVIOUS_OUT / cid / "result.json").read_bytes()) != expected_hash:
            raise ValueError("Previous attempt changed: " + cid)
    if len(plan["entries"]) != 42:
        raise ValueError("Plan inventory changed")
    settings = ChatSettings(**plan["settings"])
    for entry in plan["entries"]:
        if entry["gate"] == "eligible" and digest(payload_bytes(entry["prepared"])) != entry["request_sha256"]:
            raise ValueError("Prepared API request hash changed")
    return plan, settings


def run(max_requests: int):
    plan, settings = verified_plan()
    if max_requests < 1 or max_requests > 27:
        raise ValueError("max_requests must be 1..27")
    docs = {row["case_id"]: row["input"] for row in load_pinned()[0]}
    pending = [row for row in plan["entries"] if row["gate"] == "eligible" and
               not (OUT / row["case_id"] / "attempt-started.json").exists()]
    if not pending:
        print(json.dumps({"status": "nothing-pending"}))
        return
    # An unfinished attempt is ambiguous. Never repeat it automatically.
    unfinished = [row["case_id"] for row in plan["entries"] if row["gate"] == "eligible" and
                  (OUT / row["case_id"] / "attempt-started.json").exists() and
                  not (OUT / row["case_id"] / "result.json").exists()]
    if unfinished:
        raise RuntimeError("Unfinished attempt requires manual audit: " + ", ".join(unfinished))
    key = os.environ.get("HCNSEC_API_KEY") or getpass.getpass("HCNSEC_API_KEY: ")
    client = QwenAPIClient(key, settings=settings)
    sent = 0
    for entry in pending:
        if sent >= max_requests:
            break
        case_id = entry["case_id"]
        directory = OUT / case_id
        # This checkpoint is created before the network operation. If the
        # process dies, a later invocation refuses to resend the same case.
        write_new(directory / "attempt-started.json", {"case_id": case_id,
                  "started_at_utc": now(), "request_sha256": entry["request_sha256"]})
        try:
            actual = client.chat(entry["prepared"]["payload"]["messages"])
        except Exception as exc:
            actual = {"status": "client-exception", "halt": True,
                      "exception_type": type(exc).__name__}
        if actual.get("request_sha256") not in (None, entry["request_sha256"]):
            actual = {"status": "request-hash-mismatch", "halt": True}
        parsed = parse(docs[case_id], entry["prepared"]["schema"], actual)
        # Redact even an unexpected upstream echo before persisting the reply.
        safe = json.loads(redact(json.dumps({"case_id": case_id, "api": actual,
                                              "analysis": parsed, "finished_at_utc": now()},
                                             ensure_ascii=False, allow_nan=False), key))
        write_new(directory / "result.json", safe)
        sent += 1
        print(json.dumps({"case_id": case_id, "api_status": actual["status"],
                          "analysis_status": parsed["status"], "decision": parsed["decision"],
                          "elapsed_seconds": actual.get("elapsed_seconds")}, ensure_ascii=False), flush=True)
        if actual.get("halt") or parsed.get("halt"):
            print(json.dumps({"status": "halted", "case_id": case_id}), flush=True)
            break
    print(json.dumps({"status": "batch-finished", "requests_sent": sent}), flush=True)


def report():
    plan, _ = verified_plan()
    _, _, labels, _ = load_pinned()
    truth = {row["case_id"]: row for row in labels["cases"]}
    counts = Counter()
    by_budget = {1024: Counter(), 2048: Counter()}
    by_technique = {name: Counter() for name in
                    ("error-based", "boolean-based blind", "time-based blind")}
    rows = []
    for entry in plan["entries"]:
        if entry["gate"] == "input_invalid":
            continue
        cid = entry["case_id"]
        path = (PREVIOUS_OUT if entry["gate"] == "prior_attempted" else OUT) / cid / "result.json"
        if not path.exists():
            counts["pending"] += 1
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        analysis = result["analysis"]
        actual = analysis["decision"] if analysis["status"] == "ok" else "analysis_error"
        expected = truth[cid]["decision"]
        correct = actual == expected
        budget = 1024 if entry["gate"] == "prior_attempted" else 2048
        counts["attempted"] += 1
        counts["correct"] += correct
        counts["analysis_error"] += actual == "analysis_error"
        counts["negative_false_positive"] += expected == "negative" and actual == "positive"
        by_budget[budget]["attempted"] += 1
        by_budget[budget]["correct"] += correct
        by_budget[budget]["analysis_error"] += actual == "analysis_error"
        counts["trial_reference_total"] += len(truth[cid]["trial_assessments"])
        for reference in truth[cid]["trial_assessments"]:
            matches = [row for row in analysis["trial_assessments"] if row["trial"] == reference["trial"]]
            counts["trial_correct"] += len(matches) == 1 and matches[0]["outcome"] == reference["outcome"]
        by_technique[entry["technique"]]["attempted"] += 1
        by_technique[entry["technique"]]["correct"] += correct
        rows.append({"case_id": cid, "technique": entry["technique"],
                     "expected": expected, "actual": actual,
                     "error": analysis["error"], "warnings": analysis["warnings"]})
    summary = {"scope": "synthetic-development-only", "formal_FPR_PSR": False,
               "prior_attempts_max_tokens": 1024, "new_attempts_max_tokens": 2048,
               "comparable_single_output_budget": False,
               "counts": dict(counts), "by_technique": {k: dict(v) for k, v in by_technique.items()},
               "by_output_budget": {str(k): dict(v) for k, v in by_budget.items()},
               "rows": rows, "reported_at_utc": now()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    action.add_argument("--report", action="store_true")
    parser.add_argument("--max-requests", type=int, default=3)
    args = parser.parse_args()
    if args.prepare:
        prepare_plan()
    elif args.run:
        run(args.max_requests)
    else:
        report()


if __name__ == "__main__":
    main()
