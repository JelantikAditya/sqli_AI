"""Reparse and score the local Qwen API SQLi development diagnosis offline.

The raw provider responses are intentionally gitignored. This audit writes a
processed receipt with hashes but never calls the model or DVWA.
"""

from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
import qwen_api_diagnosis as diagnosis
from qwen_api_analysis import parse

OUT = ROOT / "results/processed/qwen38-api-diagnosis-20261020"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def audit():
    plan, _ = diagnosis.verified_plan()
    prior_plan_blob = (diagnosis.PREVIOUS_OUT / "plan.json").read_bytes()
    prior_plan = json.loads(prior_plan_blob)
    prior_entries = {row["case_id"]: row for row in prior_plan["entries"]}
    docs = {row["case_id"]: row["input"] for row in diagnosis.load_pinned()[0]}
    fingerprints = {}
    api_status = Counter()
    analysis_status = Counter()
    finish_reasons = Counter()
    models = Counter()
    usage = Counter()
    elapsed = 0.0
    attempted = 0
    for entry in plan["entries"]:
        if entry["gate"] == "input_invalid":
            for base in (diagnosis.PREVIOUS_OUT, diagnosis.OUT):
                if (base / entry["case_id"] / "attempt-started.json").exists():
                    raise ValueError("Invalid input reached API: " + entry["case_id"])
            continue
        cid = entry["case_id"]
        if entry["gate"] == "prior_attempted":
            base, prepared_entry = diagnosis.PREVIOUS_OUT, prior_entries[cid]
        else:
            base, prepared_entry = diagnosis.OUT, entry
        attempt_path = base / cid / "attempt-started.json"
        result_path = base / cid / "result.json"
        if not attempt_path.exists() or not result_path.exists():
            raise ValueError("Incomplete case: " + cid)
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        result_blob = result_path.read_bytes()
        result = json.loads(result_blob)
        if attempt["case_id"] != cid or attempt["request_sha256"] != prepared_entry["request_sha256"]:
            raise ValueError("Attempt receipt mismatch: " + cid)
        if result["case_id"] != cid:
            raise ValueError("Result case mismatch: " + cid)
        api = result["api"]
        if api.get("request_sha256") not in (None, prepared_entry["request_sha256"]):
            raise ValueError("Provider request hash mismatch: " + cid)
        replay = parse(docs[cid], prepared_entry["prepared"]["schema"], api)
        if replay != result["analysis"]:
            raise ValueError("Parser replay mismatch: " + cid)
        fingerprints[attempt_path.relative_to(ROOT).as_posix()] = sha(attempt_path.read_bytes())
        fingerprints[result_path.relative_to(ROOT).as_posix()] = sha(result_blob)
        attempted += 1
        api_status[api["status"]] += 1
        analysis_status[replay["status"]] += 1
        finish_reasons[str(api.get("finish_reason"))] += 1
        models[str(api.get("reported_model"))] += 1
        elapsed += api.get("elapsed_seconds", 0) or 0
        for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
            usage[field] += (api.get("usage") or {}).get(field, 0) or 0
    if attempted != 36:
        raise ValueError("All 36 eligible cases must have one attempt")
    with redirect_stdout(io.StringIO()):
        summary = diagnosis.report()
    if summary["counts"].get("pending", 0) or summary["counts"]["attempted"] != 36:
        raise ValueError("Scored case count mismatch")
    return {"scope": "synthetic-development-only", "formal_FPR_PSR": False,
            "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "model_calls_during_audit": 0, "dvwa_requests_during_audit": 0,
            "eligible_attempts_replayed": attempted, "invalid_inputs_skipped": 6,
            "plan_sha256": sha((diagnosis.OUT / "plan.json").read_bytes()),
            "previous_plan_sha256": sha(prior_plan_blob),
            "api_status": dict(api_status), "analysis_status": dict(analysis_status),
            "finish_reasons": dict(finish_reasons), "reported_models": dict(models),
            "usage_sum": dict(usage), "elapsed_seconds_sum": round(elapsed, 3),
            "score": summary, "raw_file_sha256": dict(sorted(fingerprints.items()))}


def main():
    receipt = audit()
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / "audit.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "offline-replay-passed",
                      "eligible_attempts": receipt["eligible_attempts_replayed"],
                      "api_status": receipt["api_status"],
                      "analysis_status": receipt["analysis_status"],
                      "output": str(OUT / "audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
