"""Verify P4's local DVWA session, level, reset, benign baseline, and timing capture."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from validation_loop import DvwaClient, SetupFormParser, form_data, load_json, load_local_env_file, require_local_target


OUTPUT = ROOT / "docs/evidence/poolside-laguna-p4-dvwa-preflight-2026-10-23.json"
PROTOCOL_PATH = ROOT / "development/poolside_laguna_p4_protocol_20261023.json"
PLAN_PATH = ROOT / "development/poolside_laguna_p4_formal_plan_20261023.json"
SCENARIO_PATH = ROOT / "dvwa/experiment_scenarios.json"
ORIGIN = "http://127.0.0.1:4280"
LEVELS = ("low", "medium", "high", "impossible")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_candidate_digest(protocol: dict) -> str:
    candidate = copy.deepcopy(protocol)
    candidate["status"] = "draft"
    candidate.pop("freeze_candidate_sha256", None)
    payload = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_preflight() -> dict:
    protocol = load_json(PROTOCOL_PATH)
    plan = load_json(PLAN_PATH)
    catalog = load_json(SCENARIO_PATH)
    origin = protocol.get("target_origin")
    require_local_target(origin)
    if origin != ORIGIN:
        raise ValueError("P4 preflight is pinned to the local DVWA host origin only.")
    local_values = load_local_env_file()
    username = os.environ.get("DVWA_USERNAME") or local_values.get("DVWA_USERNAME") or "admin"
    password = os.environ.get("DVWA_PASSWORD") or local_values.get("DVWA_PASSWORD") or "password"
    timeout = int(plan.get("request_timeout_seconds", 15))
    client = DvwaClient(origin, timeout)
    started = datetime.now(timezone.utc)

    reset = client.reset_database()
    levels = {}
    baseline_latencies = []
    for level in LEVELS:
        client.login_and_set_level(username, password, level)
        level_check = client.verify_session_level(level)
        scenarios = [item for item in catalog["scenarios"] if item["security_level"] == level]
        input_checks = []
        for scenario in scenarios:
            response = client.get_form(scenario["input_path"])
            form_parser = SetupFormParser()
            form_parser.feed(response["body"])
            has_expected_field = any(scenario["parameter"] in item["controls"] for item in form_parser.forms)
            login_form_present = bool(re.search(r"<input[^>]+name=['\"]password['\"]", response["body"], re.I))
            authenticated = response["status"] == 200 and not login_form_present
            input_checks.append({
                "scenario_id": scenario["scenario_id"],
                "input_path": scenario["input_path"],
                "method": scenario["method"],
                "status": response["status"],
                "authenticated": authenticated,
                "expected_parameter_present": has_expected_field,
                "response_sha256": response["body_sha256"],
            })

        timing_scenario = next(item for item in scenarios if item["sqli_type"] == "time-based blind")
        timing_path = timing_scenario["result_path"]
        samples = []
        for _ in range(5):
            form = client.get_form(timing_scenario["input_path"])
            parser = SetupFormParser()
            parser.feed(form["body"])
            matching_forms = [item for item in parser.forms
                              if timing_scenario["parameter"] in item["controls"]
                              and item["method"] == timing_scenario["method"]]
            if form["status"] != 200 or len(matching_forms) != 1:
                raise RuntimeError(f"Time scenario form was unavailable for benign baseline at {level}.")
            values = {timing_scenario["parameter"]: "1", "Submit": "Submit"}
            token_control = matching_forms[0]["controls"].get("user_token")
            if token_control and token_control.get("value"):
                values["user_token"] = token_control["value"]
            started_request = time.perf_counter()
            submitted = client.request(timing_scenario["method"], timing_scenario["input_path"], values)
            response = submitted
            if timing_scenario["input_path"] != timing_path:
                response = client.get_form(timing_path)
            response["elapsed_ms"] = round((time.perf_counter() - started_request) * 1000, 2)
            authenticated = (response["status"] == 200
                             and not re.search(r"<input[^>]+name=['\"]password['\"]", response["body"], re.I))
            if not authenticated:
                raise RuntimeError(f"Benign baseline failed for {level}.")
            if "first name:" not in response["body"].lower() and "user id exists" not in response["body"].lower():
                raise RuntimeError(f"Benign ID=1 baseline did not return a known DVWA record at {level}.")
            samples.append(response["elapsed_ms"])
            baseline_latencies.append(response["elapsed_ms"])

        level_passed = (level_check["security_level"] == level
                        and len(input_checks) == 3
                        and all(item["authenticated"] and item["expected_parameter_present"] for item in input_checks)
                        and len(samples) == 5)
        levels[level] = {
            "passed": level_passed,
            "security_page_verified": level_check["security_level"],
            "security_page_sha256": level_check["response_sha256"],
            "input_checks": input_checks,
            "benign_baseline": {
                "scenario_id": timing_scenario["scenario_id"],
                "request_count": len(samples),
                "parameter_value": "1",
                "sql_injection_payloads_sent": 0,
                "latency_ms": samples,
                "median_latency_ms": statistics.median(samples),
                "maximum_latency_ms": max(samples),
                "response_control": "HTTP 200, authenticated marker, and known sample-record marker",
            },
        }

    status = "passed" if all(item["passed"] for item in levels.values()) and reset["success_markers_verified"] else "failed"
    baseline_max = max(baseline_latencies)
    return {
        "schema": "poolside-laguna-p4-dvwa-preflight-v1",
        "experiment_id": "poolside-laguna-p4-20261023",
        "created_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "scope": "local DVWA readiness only; not a formal experiment run",
        "target_origin": origin,
        "target_host_is_loopback": True,
        "protocol_sha256": digest(PROTOCOL_PATH),
        "protocol_candidate_sha256": protocol_candidate_digest(protocol),
        "formal_runner_plan_sha256": digest(PLAN_PATH),
        "database_reset": reset,
        "database_reset_count": 1,
        "levels": levels,
        "timing_instrumentation": {
            "method": "time.perf_counter around local HTTP request",
            "sample_count": len(baseline_latencies),
            "median_latency_ms": statistics.median(baseline_latencies),
            "maximum_latency_ms": baseline_max,
            "time_signal_threshold_ms": protocol["validation"]["time_signal_threshold_ms"],
            "maximum_benign_sample_below_threshold": baseline_max < protocol["validation"]["time_signal_threshold_ms"],
            "scope_note": "Confirms local timing capture and benign baseline only; it does not test SQLi time-delay detection.",
        },
        "http_request_count": client.http_request_calls,
        "logical_probe_submissions": 0,
        "sql_injection_payloads_sent": 0,
        "api_requests_sent": 0,
        "dvwa_credentials_read": True,
        "api_credentials_read": False,
        "credential_values_recorded": False,
        "openrouter_used": False,
        "execution_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Run the authorized local DVWA preflight and one DB reset.")
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run to execute the local DVWA preflight.")
    try:
        result = run_preflight()
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        if OUTPUT.exists():
            raise FileExistsError(f"Refusing to overwrite P4 preflight evidence: {OUTPUT}")
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    except Exception as failure:
        print(json.dumps({"status": "failed", "error_type": type(failure).__name__,
                          "error": str(failure)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
