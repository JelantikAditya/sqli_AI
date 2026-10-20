"""Summarize explicit-method ZAP API SQLi scan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from rag_pipeline import ROOT, load_catalog


RULES = {
    "40018": "SQL Injection",
    "40019": "SQL Injection MySQL Time Based",
}


def safe_path(value: str) -> str:
    return urlsplit(value).path or "/"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(report_path: Path, har_path: Path, evidence_path: Path,
              level: str, plan_path: Path | None = None) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    har = json.loads(har_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    catalog = load_catalog()
    expected_parameters = {
        (item["input_path"], item["method"].upper()): item["parameter"].lower()
        for item in catalog["scenarios"] if item["security_level"] == level
    }

    alerts = Counter()
    alert_coordinates = set()
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            rule_id = str(alert.get("pluginid", ""))
            if rule_id not in RULES:
                continue
            for instance in alert.get("instances", []):
                method = str(instance.get("method", "")).upper()
                path = safe_path(str(instance.get("uri", "")))
                parameter = str(instance.get("param", "")).lower()
                alerts[rule_id] += 1
                if expected_parameters.get((path, method)) == parameter:
                    alert_coordinates.add((path, method, parameter))

    scan_requests = Counter()
    scan_parameter_requests = Counter()
    input_observations = Counter()
    tagged_observations = Counter()
    tagged_rules = defaultdict(set)
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        headers = {
            str(header.get("name", "")).lower(): str(header.get("value", ""))
            for header in request.get("headers", [])
        }
        path = safe_path(str(request.get("url", "")))
        method = str(request.get("method", "UNKNOWN")).upper()
        expected_parameter = expected_parameters.get((path, method))
        query_params = request.get("queryString", [])
        post_params = request.get("postData", {}).get("params", [])
        cookie_params = request.get("cookies", [])
        parameter_names = {
            str(param.get("name", "")).lower()
            for param in [*query_params, *post_params, *cookie_params]
        }
        if expected_parameter and expected_parameter in parameter_names:
            input_observations[(path, method)] += 1

        rule_id = headers.get("x-zap-scan-id")
        if rule_id not in RULES:
            continue
        scan_requests[rule_id] += 1
        if expected_parameter and expected_parameter in parameter_names:
            coordinate = (path, method, expected_parameter)
            tagged_observations[coordinate] += 1
            tagged_rules[coordinate].add(rule_id)
        scan_parameter_requests[rule_id] += sum(
            1 for param in [*query_params, *post_params, *cookie_params]
            if str(param.get("name", "")).lower() == "id"
        )

    expected_coordinates = {
        (path, method, parameter)
        for (path, method), parameter in expected_parameters.items()
    }
    observed_coordinates = set(alert_coordinates) | set(tagged_observations)
    covered = sorted(observed_coordinates & expected_coordinates)
    scan_stats = evidence.get("zap_rule_request_stats_by_rule", {})
    scan_records = evidence.get("active_scans", [])
    return {
        "schema_version": "1.0.0",
        "scope": "local-dvwa-sqli-active-explicit-api",
        "runner": evidence.get("runner"),
        "security_level": level,
        "target_origin": "http://dvwa",
        "active_scan_rules": RULES,
        "scan_method_and_input_explicit": all(
            (item.get("method") == "POST" and item.get("seed_post_data") == "id=1&Submit=Submit")
            or (item.get("method") == "GET" and item.get("seed_url_query") == "id=1&Submit=Submit")
            for item in scan_records
        ),
        "api_scans_completed": bool(scan_records) and all(
            int(item.get("final_status_percent", -1)) >= 100 for item in scan_records
        ),
        "automation_setup_completed": bool(evidence.get("automation_plan_finished"))
        and not evidence.get("automation_plan_errors"),
        "expected_injection_coordinates": [
            {"path": path, "method": method, "parameter": expected_parameters[(path, method)]}
            for path, method in sorted(expected_parameters)
        ],
        "har_scan_id_tagged_requests_by_rule": dict(sorted(scan_requests.items())),
        "zap_rule_request_stats_by_rule": scan_stats,
        "requests_with_id_parameter_by_rule": dict(sorted(scan_parameter_requests.items())),
        "scanner_tagged_input_coordinates": [
            {"path": path, "method": method, "parameter": parameter,
             "rule_ids": sorted(tagged_rules[(path, method, parameter)]),
             "request_count": tagged_observations[(path, method, parameter)]}
            for path, method, parameter in covered
            if (path, method, parameter) in tagged_observations
        ],
        "har_input_coordinate_observations_any_job": [
            {"path": path, "method": method, "parameter_present": True,
             "request_count": count}
            for (path, method), count in sorted(input_observations.items())
        ],
        "observed_injection_coordinates": [
            {"path": path, "method": method} for path, method, _ in covered
        ],
        "coordinate_coverage": {
            "observed": len(covered),
            "expected": len(expected_coordinates),
            "complete": len(covered) == len(expected_coordinates),
        },
        "active_sqli_alert_instances_by_rule": dict(sorted(alerts.items())),
        "interpretation": (
            "Alert absence is interpretable only when authentication, level, active-rule execution, "
            "and scanner-tagged input-coordinate coverage are verified."
        ),
        "artifact_sha256": {
            "report": sha256_file(report_path),
            "har_local_only": sha256_file(har_path),
            "api_evidence": sha256_file(evidence_path),
            **({"plan": sha256_file(plan_path)} if plan_path else {}),
        },
        "artifact_names": {
            "report": report_path.name,
            "har_local_only": har_path.name,
            "api_evidence": evidence_path.name,
            **({"plan": plan_path.name} if plan_path else {}),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("har", type=Path)
    parser.add_argument("api_evidence", type=Path)
    parser.add_argument("--security-level", choices=("low", "medium", "high", "impossible"), required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "results/raw").resolve()):
        raise ValueError("Summary output must be stored under results/raw.")
    result = summarize(args.report, args.har, args.api_evidence,
                       args.security_level, args.plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write("\n")
    print(json.dumps({
        "output": str(output),
        "coordinate_coverage": result["coordinate_coverage"],
        "tagged_requests": result["har_scan_id_tagged_requests_by_rule"],
        "rule_request_stats": result["zap_rule_request_stats_by_rule"],
        "alerts": result["active_sqli_alert_instances_by_rule"],
    }))


if __name__ == "__main__":
    main()
