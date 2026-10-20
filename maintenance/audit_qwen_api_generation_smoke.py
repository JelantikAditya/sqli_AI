"""Audit both checkpointed Qwen API generation preflights without network calls."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
from qwen_api_client import ChatSettings, encoded_payload, request_payload
from qwen_api_generation import PROMPT_VERSION, parse


RAW = ROOT / "results/raw/development"
BATCHES = ("qwen38-api-generation-smoke-20261020",
           "qwen38-api-generation-smoke-20261020-v2")
OUT = ROOT / "results/processed/qwen38-api-generation-smoke-20261020"
CATALOG = ROOT / "dvwa/experiment_scenarios.json"
KINDS = {"error-based": "single_error", "boolean-based blind": "boolean_pair",
         "time-based blind": "single_time"}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def audit() -> dict:
    catalog_hash = sha(CATALOG.read_bytes())
    file_hashes = {}
    rows = []
    for batch_name in BATCHES:
        base = RAW / batch_name
        plan_path = base / "plan.json"
        plan_blob = plan_path.read_bytes()
        receipt_path = base / "plan.receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt["plan_sha256"] != sha(plan_blob):
            raise ValueError("Plan receipt mismatch: " + batch_name)
        plan = json.loads(plan_blob)
        if plan["catalog_sha256"] != catalog_hash or plan["prompt_version"] != PROMPT_VERSION:
            raise ValueError("Source mismatch: " + batch_name)
        if batch_name == BATCHES[1]:
            previous = RAW / BATCHES[0]
            if plan["prior_plan_sha256"] != sha((previous / "plan.json").read_bytes()):
                raise ValueError("Prior plan mismatch")
            for sid, expected in plan["prior_results_sha256"].items():
                if expected != sha((previous / sid / "result.json").read_bytes()):
                    raise ValueError("Prior result mismatch: " + sid)
        settings = ChatSettings(**plan["settings"])
        for path in (plan_path, receipt_path):
            file_hashes[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
        for entry in plan["entries"]:
            sid = entry["scenario_id"]
            request_hash = sha(encoded_payload(request_payload(entry["prepared"]["messages"], settings)))
            if request_hash != entry["request_sha256"]:
                raise ValueError("Request mismatch: " + batch_name + "/" + sid)
            attempt_path = base / sid / "attempt-started.json"
            result_path = base / sid / "result.json"
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if attempt["scenario_id"] != sid or attempt["request_sha256"] != request_hash:
                raise ValueError("Attempt mismatch: " + batch_name + "/" + sid)
            if result["scenario_id"] != sid or result["api"].get("request_sha256") not in (None, request_hash):
                raise ValueError("Result mismatch: " + batch_name + "/" + sid)
            replay = parse(entry["prepared"], [], KINDS[entry["technique"]], result["api"])
            if replay != result["generation"]:
                raise ValueError("Parser replay mismatch: " + batch_name + "/" + sid)
            for path in (attempt_path, result_path):
                file_hashes[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
            usage = result["api"].get("usage") or {}
            rows.append({"batch": batch_name, "scenario_id": sid,
                         "max_tokens": settings.max_tokens,
                         "timeout_seconds": settings.timeout_seconds,
                         "api_status": result["api"]["status"],
                         "generation_status": replay["status"],
                         "candidate": replay["candidate"],
                         "finish_reason": result["api"].get("finish_reason"),
                         "reported_model": result["api"].get("reported_model"),
                         "completion_tokens": usage.get("completion_tokens"),
                         "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                         "elapsed_seconds": result["api"].get("elapsed_seconds")})
    if len(rows) != 5:
        raise ValueError("Expected exactly five preflight attempts")
    return {"scope": "development-generation-preflight-no-dvwa-execution",
            "formal_FPR_PSR": False, "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "model_calls_during_audit": 0, "dvwa_requests_during_audit": 0,
            "attempts_replayed": len(rows),
            "api_status": dict(Counter(row["api_status"] for row in rows)),
            "generation_status": dict(Counter(row["generation_status"] for row in rows)),
            "rows": rows, "raw_file_sha256": dict(sorted(file_hashes.items()))}


def main() -> None:
    receipt = audit()
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / "audit.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "offline-replay-passed", "attempts": receipt["attempts_replayed"],
                      "api_status": receipt["api_status"],
                      "output": str(OUT / "audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
