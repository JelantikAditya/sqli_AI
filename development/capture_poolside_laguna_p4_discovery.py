"""Run one bounded passive ZAP discovery and capture its raw P4 evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "results/raw/formal-discovery/poolside-laguna-p4-20261023"
POWERSHELL_SCRIPT = ROOT / "dvwa/run_zap_discovery.ps1"
LEVELS = ("low", "medium", "high", "impossible")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture(replicate: int, level: str) -> dict:
    if replicate not in (1, 2, 3) or level not in LEVELS:
        raise ValueError("P4 discovery requires replicate 1-3 and one of the four DVWA levels.")
    destination = OUTPUT_ROOT / f"replicate-{replicate}" / level
    if destination.exists():
        raise FileExistsError(f"Refusing to replace existing P4 discovery evidence: {destination}")

    started = datetime.now(timezone.utc)
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(POWERSHELL_SCRIPT), "-SecurityLevel", level]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=2400)
    combined_output = completed.stdout + "\n" + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(f"ZAP discovery failed for replicate {replicate}, {level}; inspect local output.\n"
                           + combined_output[-3000:])

    normalized_match = re.search(r"Normalized report written:\s*(.+)", combined_output)
    report_match = re.search(r"ZAP report:\s*(.+)", combined_output)
    har_match = re.search(r"ZAP HAR \(local only\):\s*(.+)", combined_output)
    plan_match = re.search(r"ZAP plan:\s*(.+)", combined_output)
    if not all((normalized_match, report_match, har_match, plan_match)):
        raise RuntimeError("ZAP completed but its raw evidence paths could not be parsed.")

    source_paths = {
        "normalized_report": Path(normalized_match.group(1).strip()).resolve(),
        "raw_report": Path(report_match.group(1).strip()).resolve(),
        "har": Path(har_match.group(1).strip()).resolve(),
        "plan": Path(plan_match.group(1).strip()).resolve(),
    }
    source_paths["log"] = source_paths["raw_report"].with_suffix(".log")
    if any(not path.is_file() for path in source_paths.values()):
        missing = [key for key, path in source_paths.items() if not path.is_file()]
        raise FileNotFoundError(f"Completed ZAP output is missing expected evidence files: {missing}")

    destination.mkdir(parents=True, exist_ok=False)
    filenames = {
        "normalized_report": "zap-discovery.normalized.json",
        "raw_report": "zap-discovery.json",
        "har": "zap-discovery.har",
        "plan": "zap-discovery.yaml",
        "log": "zap-discovery.log",
    }
    captured = {}
    for kind, source in source_paths.items():
        target = destination / filenames[kind]
        shutil.copy2(source, target)
        captured[kind] = {"path": target.relative_to(ROOT).as_posix(), "sha256": sha256(target),
                          "source_path": source.relative_to(ROOT).as_posix(), "source_sha256": sha256(source)}
        if captured[kind]["sha256"] != captured[kind]["source_sha256"]:
            raise RuntimeError(f"Evidence copy hash mismatch for {kind}.")

    normalized = json.loads((destination / filenames["normalized_report"]).read_text(encoding="utf-8"))
    metadata = normalized.get("run_metadata", {})
    expected_origin = "http://dvwa"
    expected_counts = normalized.get("summary", {}).get("verified_injection_point_count") == 2
    passed = (metadata.get("authentication_status") == "verified"
              and metadata.get("target_origin") == expected_origin
              and metadata.get("security_level") == level
              and metadata.get("scan_mode") == "passive"
              and expected_counts)
    receipt = {
        "schema": "poolside-laguna-p4-discovery-capture-v1",
        "experiment_id": "poolside-laguna-p4-20261023",
        "replicate": replicate,
        "security_level": level,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": completed.returncode,
        "status": "passed" if passed else "review-required",
        "target_origin": metadata.get("target_origin"),
        "authentication_status": metadata.get("authentication_status"),
        "reported_security_level": metadata.get("security_level"),
        "scan_mode": metadata.get("scan_mode"),
        "verified_injection_point_count": normalized.get("summary", {}).get("verified_injection_point_count"),
        "out_of_level_sqli_input_observation_count": normalized.get("summary", {}).get(
            "out_of_level_sqli_input_observation_count"),
        "artifacts": captured,
        "api_requests_sent": 0,
        "openrouter_used": False,
    }
    receipt_path = destination / "capture-receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not passed:
        raise RuntimeError(f"P4 discovery requires review; receipt: {receipt_path.relative_to(ROOT)}")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--level", required=True, choices=LEVELS)
    parser.add_argument("--run", action="store_true", help="Run the passive ZAP discovery against local DVWA.")
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run to execute the local discovery scan.")
    try:
        print(json.dumps(capture(args.replicate, args.level), ensure_ascii=False, indent=2))
        return 0
    except Exception as failure:
        print(json.dumps({"status": "failed", "error_type": type(failure).__name__,
                          "error": str(failure)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
