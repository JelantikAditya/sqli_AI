"""Replay the bounded Qwen S2 context pilot without API or DVWA access."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
import qwen_api_generation_s2_context_smoke as smoke
from qwen_api_generation import parse


OUT = ROOT / "results/processed/qwen38-api-generation-s2-context-20261020"


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def audit() -> dict:
    plan, settings = smoke.verified_plan()
    base = smoke.OUT
    result_path = base / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    entry = plan["entry"]
    request_hash = entry["request_sha256"]
    if result["api"].get("request_sha256") != request_hash:
        raise ValueError("API result request hash does not match the frozen plan")
    replay = parse(entry["prepared"], entry["attempted"], "boolean_pair", result["api"])
    if replay != result["generation"] or replay["status"] != "generated":
        raise ValueError("Generation parser replay failed")
    if replay["candidate"] != {"true_payload": "0' OR '1'='1",
                               "false_payload": "0' OR '1'='2"}:
        raise ValueError("Generated candidate does not match the independently verified context pair")

    validation_path = base / "dvwa-validation.jsonl"
    rows = read_jsonl(validation_path)
    payloads = [row for row in rows if row.get("record_type") == "payload"]
    decisions = [row for row in rows if row.get("record_type") == "decision"]
    evidence = [row for row in rows if row.get("record_type") == "candidate_evidence"]
    run_end = [row for row in rows if row.get("record_type") == "run_end"]
    if (len(payloads) != 9 or len(decisions) != 3 or len(evidence) != 1 or len(run_end) != 1
            or run_end[0]["attempt_status"] != "complete"
            or run_end[0]["database_reset_performed"]):
        raise ValueError("DVWA pilot is incomplete or outside the declared no-reset scope")
    if (evidence[0]["evidence_status"] != "CONSISTENT_POSITIVE"
            or evidence[0]["confirmation_signals"] != [True, True, True]
            or any(not row["system_signal"] for row in decisions)):
        raise ValueError("Expected three positive boolean-pair confirmations")
    for trial in range(1, 4):
        pair = {row["payload_role"]: row for row in payloads
                if row["confirmation_index"] == trial}
        if (set(pair) != {"baseline", "true_condition", "false_condition"}
                or "user_id_exists" not in pair["true_condition"]["content_markers"]
                or "user_id_missing" not in pair["false_condition"]["content_markers"]):
            raise ValueError("True/false response markers failed at confirmation " + str(trial))

    files = [base / "plan.json", base / "plan.receipt.json", base / "attempt-started.json",
             result_path, validation_path]
    return {
        "scope": "development-only-qwen-api-generation-and-local-dvwa-s2-context-pilot",
        "formal_FPR_PSR": False,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_calls_during_audit": 0,
        "dvwa_requests_during_audit": 0,
        "candidate": replay["candidate"],
        "reported_model": result["api"].get("reported_model"),
        "api_status": result["api"]["status"],
        "generation_status": replay["status"],
        "finish_reason": result["api"].get("finish_reason"),
        "completion_tokens": (result["api"].get("usage") or {}).get("completion_tokens"),
        "reasoning_tokens": ((result["api"].get("usage") or {}).get("completion_tokens_details") or {}).get(
            "reasoning_tokens"),
        "timeout_seconds": settings.timeout_seconds,
        "max_tokens": settings.max_tokens,
        "dvwa_confirmations": len(decisions),
        "dvwa_evidence_status": evidence[0]["evidence_status"],
        "positive_confirmations": Counter(evidence[0]["confirmation_signals"])[True],
        "database_reset_performed": run_end[0]["database_reset_performed"],
        "raw_file_sha256": {path.relative_to(ROOT).as_posix(): sha(path.read_bytes())
                            for path in files},
    }


def main() -> None:
    receipt = audit()
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / "audit.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "offline-replay-passed",
                      "dvwa_confirmations": receipt["dvwa_confirmations"],
                      "dvwa_evidence_status": receipt["dvwa_evidence_status"],
                      "output": str(OUT / "audit.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
