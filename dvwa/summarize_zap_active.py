"""Summarize scoped ZAP SQLi active-scan evidence without exporting payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from rag_pipeline import ROOT, load_catalog


RULES = {"40018": "SQL Injection", "40019": "SQL Injection MySQL Time Based"}


def safe_path(value: str) -> str:
    return urlsplit(value).path or "/"


def summarize(report_path: Path, har_path: Path, log_path: Path, level: str,
              plan_path: Path | None = None) -> dict:
    report_bytes = report_path.read_bytes()
    har_bytes = har_path.read_bytes()
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    log_bytes = log_path.read_bytes()
    plan_bytes = plan_path.read_bytes() if plan_path else None
    report = json.loads(report_bytes)
    har = json.loads(har_bytes)
    catalog = load_catalog()
    expected = {
        (item["input_path"], item["method"].upper())
        for item in catalog["scenarios"]
        if item["security_level"] == level
    }
    expected_parameters = {
        (item["input_path"], item["method"].upper()): item["parameter"].lower()
        for item in catalog["scenarios"] if item["security_level"] == level
    }

    alerts = Counter()
    alert_coordinates = set()
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            plugin_id = str(alert.get("pluginid", ""))
            if plugin_id not in RULES:
                continue
            for instance in alert.get("instances", []):
                method = instance.get("method")
                method = method.upper() if isinstance(method, str) else None
                path = safe_path(instance.get("uri", ""))
                alerts[plugin_id] += 1
                parameter = str(instance.get("param", "")).lower()
                if expected_parameters.get((path, method)) == parameter:
                    alert_coordinates.add((path, method, parameter))

    scan_requests = Counter()
    scan_parameter_requests = Counter()
    input_coordinate_observations = Counter()
    tagged_input_coordinate_observations = Counter()
    tagged_input_coordinate_rules = defaultdict(set)
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        header_values = {
            str(header.get("name", "")).lower(): str(header.get("value", ""))
            for header in request.get("headers", [])
        }
        url = request.get("url", "")
        path = safe_path(url)
        method = str(request.get("method", "UNKNOWN")).upper()
        input_parameter = expected_parameters.get((path, method))
        parameter_names = {
            str(param.get("name", "")).lower()
            for param in request.get("queryString", [])
        }
        parameter_names.update(
            str(param.get("name", "")).lower()
            for param in request.get("postData", {}).get("params", [])
        )
        parameter_names.update(
            str(cookie.get("name", "")).lower()
            for cookie in request.get("cookies", [])
        )
        if input_parameter:
            if input_parameter in parameter_names:
                input_coordinate_observations[(path, method)] += 1
        rule_id = header_values.get("x-zap-scan-id")
        if rule_id not in RULES:
            continue
        scan_requests[rule_id] += 1
        if input_parameter and input_parameter in parameter_names:
            coordinate = (path, method, input_parameter)
            tagged_input_coordinate_observations[coordinate] += 1
            tagged_input_coordinate_rules[coordinate].add(rule_id)
        scan_parameter_requests[rule_id] += sum(
            1 for param in request.get("queryString", []) if param.get("name", "").lower() == "id"
        )
        post_data = request.get("postData", {})
        scan_parameter_requests[rule_id] += sum(
            1 for param in post_data.get("params", []) if param.get("name", "").lower() == "id"
        )
        scan_parameter_requests[rule_id] += sum(
            1 for cookie in request.get("cookies", []) if cookie.get("name", "").lower() == "id"
        )

    expected_coordinates = {
        (path, method, parameter) for (path, method), parameter in expected_parameters.items()
    }
    observed_coordinates = set(alert_coordinates) | set(tagged_input_coordinate_observations)
    covered = sorted(observed_coordinates.intersection(expected_coordinates))
    rule_request_stats = {}
    for rule_id in RULES:
        name = "Generic SQL injection rule sent requests" if rule_id == "40018" else "MySQL timing SQL injection rule sent requests"
        import re
        match = re.search(
            rf"{re.escape(name)} \[(\d+) >= 1\]",
            log_text,
        )
        rule_request_stats[rule_id] = int(match.group(1)) if match else None
    return {
        "schema_version": "1.0.0",
        "scope": "local-dvwa-sqli-active-baseline",
        "security_level": level,
        "target_origin": "http://dvwa",
        "active_scan_rules": RULES,
        "authentication_and_level_assertions": "automation-plan-required-tests; runner must exit zero",
        "expected_injection_coordinates": [
            {"path": path, "method": method, "parameter": expected_parameters[(path, method)]}
            for path, method in sorted(expected)
        ],
        "har_scan_id_tagged_requests_by_rule": dict(sorted(scan_requests.items())),
        "zap_rule_request_stats_by_rule": rule_request_stats,
        "requests_with_id_parameter_by_rule": dict(sorted(scan_parameter_requests.items())),
        "scanner_tagged_input_coordinates": [
            {"path": path, "method": method, "parameter": parameter,
             "rule_ids": sorted(tagged_input_coordinate_rules[(path, method, parameter)]),
             "request_count": tagged_input_coordinate_observations[(path, method, parameter)]}
            for path, method, parameter in sorted(
                set(tagged_input_coordinate_observations).intersection(expected_coordinates))
        ],
        # This includes seed/spider traffic. Keep it separate from scanner-tagged
        # coverage so untagged requests cannot prove active-scan attribution.
        "har_input_coordinate_observations_any_job": [
            {"path": path, "method": method, "parameter_present": True,
             "request_count": count}
            for (path, method), count in sorted(input_coordinate_observations.items())
        ],
        "observed_injection_coordinates": [
            {"path": path, "method": method} for path, method, _parameter in covered
        ],
        "coordinate_coverage": {
            "observed": len(covered),
            "expected": len(expected),
            "complete": len(covered) == len(expected),
        },
        "active_sqli_alert_instances_by_rule": dict(sorted(alerts.items())),
        "interpretation": "Alert presence is a scanner observation. Absence is interpretable only when authentication, level, active-rule execution, and injection-coordinate coverage are verified.",
        "artifact_sha256": {
            "report": hashlib.sha256(report_bytes).hexdigest(),
            "har_local_only": hashlib.sha256(har_bytes).hexdigest(),
            "log": hashlib.sha256(log_bytes).hexdigest(),
            **({"plan": hashlib.sha256(plan_bytes).hexdigest()} if plan_bytes is not None else {}),
        },
        "artifact_names": {"report": report_path.name, "har_local_only": har_path.name,
                           "log": log_path.name,
                           **({"plan": plan_path.name} if plan_path is not None else {})},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("har", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--security-level", choices=("low", "medium", "high", "impossible"), required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "results/raw").resolve()):
        raise ValueError("Summary output must be stored under results/raw.")
    result = summarize(args.report, args.har, args.log, args.security_level, args.plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write("\n")
    print(json.dumps({"output": str(output), "coordinate_coverage": result["coordinate_coverage"],
                      "rule_request_stats": result["zap_rule_request_stats_by_rule"],
                      "alerts": result["active_sqli_alert_instances_by_rule"]}))


if __name__ == "__main__":
    main()
