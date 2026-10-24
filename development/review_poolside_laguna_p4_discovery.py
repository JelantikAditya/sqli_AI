"""Bind a technical review of the fresh P4 passive-discovery report set."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from parse_zap_report import EXPECTED_INPUTS_BY_LEVEL, SQLI_INPUT_PATHS


EXPERIMENT_ID = "poolside-laguna-p4-20261023"
SUMMARY_PLAN = ROOT / "development/poolside_laguna_p4_plan_20261023.json"
FORMAL_PLAN = ROOT / "development/poolside_laguna_p4_formal_plan_20261023.json"
REVIEW_PATH = ROOT / "docs/evidence/poolside-laguna-p4-discovery-review-2026-10-23.json"
DISCOVERY_ROOT = ROOT / "results/raw/formal-discovery/poolside-laguna-p4-20261023"
LEVELS = ("low", "medium", "high", "impossible")
EXPECTED_OUT_OF_LEVEL = {"low": 1, "medium": 1, "high": 0, "impossible": 3}
EXPECTED_OBSERVATION_NAMES = {
    "Cookie Poisoning", "Cookie No HttpOnly Flag", "Cookie without SameSite Attribute"
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {path}.")
    return value


def mapped_out_of_level_observations(report: dict, level: str) -> list[dict]:
    result = []
    expected = EXPECTED_INPUTS_BY_LEVEL[level]
    for observation in report.get("observations", []):
        instance = observation.get("instance") or {}
        uri = instance.get("uri") or ""
        path = uri.split("?", 1)[0].removeprefix("http://dvwa")
        method = instance.get("method") or "UNKNOWN"
        parameter = instance.get("parameter") or ""
        if path in SQLI_INPUT_PATHS and parameter.lower() == "id" and (path, method) not in expected:
            result.append({"path": path, "method": method, "parameter": "id",
                           "alert_name": observation.get("alert", {}).get("name")})
    return result


def review() -> dict:
    summary_plan = read_json(SUMMARY_PLAN)
    formal_plan = read_json(FORMAL_PLAN)
    if summary_plan.get("experiment_id") != EXPERIMENT_ID or formal_plan.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("P4 discovery review refuses plans for another cohort.")

    reports = summary_plan.get("discovery_reports", [])
    if len(reports) != 12:
        raise ValueError("P4 discovery review requires exactly twelve mapped reports.")
    report_hashes = {}
    report_findings = []
    out_of_level_counts = {level: [] for level in LEVELS}
    sql_alert_counts = {level: [] for level in LEVELS}
    all_passed = True

    for item in reports:
        path = ROOT / item["path"]
        report = read_json(path)
        replicate = item["replicate"]
        level = item["level"]
        receipt_path = path.parent / "capture-receipt.json"
        capture = read_json(receipt_path)
        metadata = report.get("run_metadata", {})
        summary = report.get("summary", {})
        out_of_level = mapped_out_of_level_observations(report, level)
        points = report.get("candidate_injection_points", [])
        fresh = None
        try:
            generated = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
            fresh = 0 <= (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() <= 24 * 3600
        except (KeyError, TypeError, ValueError):
            fresh = False
        report_passed = (
            item.get("p4_use") == "fresh P4 discovery"
            and sha256(path) == item.get("sha256")
            and capture.get("status") == "passed"
            and capture.get("replicate") == replicate
            and capture.get("security_level") == level
            and metadata.get("authentication_status") == "verified"
            and metadata.get("target_origin") == "http://dvwa"
            and metadata.get("security_level") == level
            and metadata.get("scan_mode") == "passive"
            and fresh
            and summary.get("verified_injection_point_count") == 2
            and len(points) == 2
            and all(point.get("verification_status") == "verified" for point in points)
            and summary.get("sql_injection_alert_group_count") == 0
            and len(out_of_level) == EXPECTED_OUT_OF_LEVEL[level]
            and all(item.get("path") == "/vulnerabilities/sqli_blind/cookie-input.php"
                    and item.get("method") == "POST"
                    and item.get("alert_name") in EXPECTED_OBSERVATION_NAMES for item in out_of_level)
        )
        all_passed = all_passed and report_passed
        out_of_level_counts[level].append(len(out_of_level))
        sql_alert_counts[level].append(summary.get("sql_injection_alert_group_count"))
        report_hashes[item["path"]] = item["sha256"]
        report_findings.append({
            "replicate": replicate,
            "level": level,
            "path": item["path"],
            "sha256": item["sha256"],
            "authentication_status": metadata.get("authentication_status"),
            "scan_mode": metadata.get("scan_mode"),
            "verified_injection_points": len(points),
            "sql_injection_alert_group_count": summary.get("sql_injection_alert_group_count"),
            "out_of_level_observation_count": len(out_of_level),
            "out_of_level_observations": out_of_level,
            "passed": report_passed,
        })

    normalized_counts = {level: values[0] if len(set(values)) == 1 else None
                         for level, values in out_of_level_counts.items()}
    normalized_sql_alert_counts = {level: values[0] if len(set(values)) == 1 else None
                                   for level, values in sql_alert_counts.items()}
    expected_formal_mapping = formal_plan.get("discovery_reports", {})
    # Check scenario ranges explicitly, keeping the expected mapping human-readable.
    mapping_matches = True
    for item in reports:
        first, last = (int(value.removeprefix("S")) for value in item["scenario_ids"].split("-"))
        for number in range(first, last + 1):
            scenario = f"S{number}"
            if expected_formal_mapping.get(scenario, {}).get(str(item["replicate"])) != item["path"]:
                mapping_matches = False
    all_passed = all_passed and normalized_counts == EXPECTED_OUT_OF_LEVEL
    all_passed = all_passed and normalized_sql_alert_counts == {level: 0 for level in LEVELS} and mapping_matches

    return {
        "schema": "poolside-laguna-p4-discovery-review-v1",
        "experiment_id": EXPERIMENT_ID,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "reviewed" if all_passed else "review-required",
        "reviewer_role": "Codex technical review",
        "review_basis": [
            "P4 normalized ZAP report and capture hashes",
            "DVWA scenario catalog and expected level/method coordinates",
            "Pinned passive ZAP discovery template and normalization contract",
        ],
        "summary_plan_sha256": sha256(SUMMARY_PLAN),
        "formal_runner_plan_sha256": sha256(FORMAL_PLAN),
        "reviewer_script_sha256": sha256(Path(__file__).resolve()),
        "source_sha256": {
            "dvwa/parse_zap_report.py": sha256(ROOT / "dvwa/parse_zap_report.py"),
            "dvwa/experiment_scenarios.json": sha256(ROOT / "dvwa/experiment_scenarios.json"),
            "dvwa/zap-auth.template.yaml": sha256(ROOT / "dvwa/zap-auth.template.yaml"),
        },
        "report_hashes": report_hashes,
        "report_count": len(report_findings),
        "reports": report_findings,
        "verified_injection_points_per_report": 2,
        "out_of_level_counts_by_level": normalized_counts,
        "sql_injection_alert_group_count_by_level": normalized_sql_alert_counts,
        "classification": "passive-discovery-coordinate-observations-only",
        "out_of_level_interpretation": (
            "The repeated out-of-level observations come from the POST cookie-input helper route. "
            "The passive discovery plan seeds that helper at every security level; its input coordinate "
            "is expected only at High. Cookie-related passive alerts at Low, Medium, and Impossible "
            "therefore describe helper-route observations, not SQL injection detections or additional "
            "formal scenarios. The parser and report show zero SQL injection alert groups."
        ),
        "metric_policy": "Do not score ZAP discovery alerts or out-of-level observations as FPR or PSR outcomes.",
        "review_limit": "Technical review only. It does not freeze the P4 protocol or approve formal execution.",
        "mapping_matches_formal_plan": mapping_matches,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "openrouter_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="Refresh this receipt only if it belongs to the same P4 report hashes.")
    args = parser.parse_args()
    result = review()
    if REVIEW_PATH.exists():
        existing = read_json(REVIEW_PATH)
        if (not args.refresh or existing.get("schema") != result["schema"]
                or existing.get("experiment_id") != EXPERIMENT_ID
                or existing.get("report_hashes") != result["report_hashes"]):
            raise FileExistsError(f"Refusing to overwrite P4 discovery review: {REVIEW_PATH}")
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.refresh and REVIEW_PATH.exists():
        descriptor, temporary_name = tempfile.mkstemp(prefix=REVIEW_PATH.name + ".", dir=REVIEW_PATH.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, REVIEW_PATH)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        REVIEW_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "report_count": result["report_count"],
                      "out_of_level_counts_by_level": result["out_of_level_counts_by_level"],
                      "sql_injection_alert_group_count_by_level": result["sql_injection_alert_group_count_by_level"],
                      "review_path": REVIEW_PATH.relative_to(ROOT).as_posix()}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "reviewed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
