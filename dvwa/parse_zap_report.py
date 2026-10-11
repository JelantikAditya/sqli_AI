"""Normalize a ZAP traditional JSON report for the DVWA SQLi experiment.

Legacy reports preserve alert metadata. A matching ZAP HAR adds safe request/form
coordinates and session-correlated verification. Neither path classifies SQLi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "1.0.0"
SCENARIO_CATALOG_PATH = Path(__file__).with_name("experiment_scenarios.json")


def load_scenario_catalog() -> dict:
    """Load the shared experiment catalog used by the validator and parser."""
    with SCENARIO_CATALOG_PATH.open("r", encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def scenario_lookup(catalog: dict) -> tuple[set[str], dict[str, dict[tuple[str, str], tuple[str, ...]]]]:
    """Derive candidate paths and level/method mappings from the catalog."""
    paths: set[str] = set()
    expected: dict[str, dict[tuple[str, str], list[str]]] = {}
    for scenario in catalog.get("scenarios", []):
        path = scenario["input_path"]
        paths.add(path)
        level_map = expected.setdefault(scenario["security_level"], {})
        coordinate = (path, scenario["method"].upper())
        level_map.setdefault(coordinate, []).append(scenario["scenario_id"])
    return paths, {
        level: {coordinate: tuple(ids) for coordinate, ids in level_map.items()}
        for level, level_map in expected.items()
    }


SQLI_INPUT_PATHS, EXPECTED_INPUTS_BY_LEVEL = scenario_lookup(load_scenario_catalog())


def safe_uri(raw_uri: object) -> str | None:
    """Drop query strings and fragments so tokens and payloads are not copied."""
    if not isinstance(raw_uri, str) or not raw_uri:
        return None

    parts = urlsplit(raw_uri)
    if parts.scheme and parts.netloc:
        host = parts.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parts.port}" if parts.port is not None else ""
        netloc = host + port
        return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", "", ""))

    # ZAP can emit a relative URI in some report variants.
    return urlunsplit(("", "", parts.path or raw_uri.split("?", 1)[0], "", ""))


def safe_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def observation_id(alert: dict, instance: dict | None) -> str:
    coordinates = {
        "plugin_id": alert.get("pluginid"),
        "name": alert.get("alert") or alert.get("name"),
        "uri": safe_uri(instance.get("uri")) if instance else None,
        "method": instance.get("method") if instance else None,
        "parameter": instance.get("param") if instance else None,
    }
    digest = hashlib.sha256(
        json.dumps(coordinates, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"zapobs-{digest}"


def normalize_report(
    report: dict,
    source_report: str,
    security_level: str,
    scan_mode: str,
    authentication_status: str,
    inventory: dict | None = None,
) -> dict:
    sites = report.get("site") or []
    observations: list[dict] = []
    candidates: dict[tuple[str, str, str], dict] = {}
    alert_group_count = 0
    alert_instance_count = 0
    sql_injection_alert_group_count = 0
    out_of_level_sqli_input_observation_count = 0
    alert_uris: set[str] = set()

    for site in sites:
        for alert in site.get("alerts") or []:
            alert_group_count += 1
            alert_name = alert.get("alert") or alert.get("name")
            if isinstance(alert_name, str) and "sql injection" in alert_name.lower():
                sql_injection_alert_group_count += 1

            instances = alert.get("instances") or []
            if not instances:
                instances = [None]

            for instance in instances:
                alert_instance_count += instance is not None
                uri = safe_uri(instance.get("uri")) if instance else None
                if uri:
                    alert_uris.add(uri)

                identifier = observation_id(alert, instance)
                method = instance.get("method") if instance else None
                method = method.upper() if isinstance(method, str) and method else None
                parameter = instance.get("param") if instance else None
                parameter = parameter.strip() if isinstance(parameter, str) else None
                observation = {
                    "observation_id": identifier,
                    "alert": {
                        "plugin_id": (
                            str(alert.get("pluginid"))
                            if alert.get("pluginid") is not None
                            else None
                        ),
                        "name": alert_name if isinstance(alert_name, str) else None,
                        "risk_code": safe_int(alert.get("riskcode")),
                        "confidence_code": safe_int(alert.get("confidence")),
                    },
                    "instance": (
                        {
                            "uri": uri,
                            "method": method,
                            "parameter": parameter or None,
                        }
                        if instance is not None
                        else None
                    ),
                }
                observations.append(observation)

                if not instance or not uri or not parameter:
                    continue
                parsed_uri = urlsplit(uri)
                path = parsed_uri.path or "/"
                if path not in SQLI_INPUT_PATHS or parameter.lower() != "id":
                    continue

                key = (path, method or "UNKNOWN", parameter)
                scenario_ids = EXPECTED_INPUTS_BY_LEVEL.get(security_level, {}).get(
                    (path, method or "UNKNOWN"),
                    (),
                )
                if not scenario_ids:
                    if security_level != "unknown":
                        out_of_level_sqli_input_observation_count += 1
                    continue
                candidates.setdefault(
                    key,
                    {
                        "path": path,
                        "method": method or "UNKNOWN",
                        "parameter": parameter,
                        "source_observation_id": identifier,
                        "scenario_ids": list(scenario_ids),
                        "verification_status": "unverified",
                    },
                )

    generated_at = report.get("created") or report.get("@generated")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "run_metadata": {
            "run_id": Path(source_report).stem,
            "source_report": Path(source_report).name,
            "generated_at": str(generated_at) if generated_at is not None else None,
            "scanner_name": report.get("@programName"),
            "scanner_version": report.get("@version"),
            "target_origin": (sites[0].get("@name") if sites else None),
            "security_level": security_level,
            "scan_mode": scan_mode,
            "authentication_status": authentication_status,
        },
        "summary": {
            "alert_group_count": alert_group_count,
            "alert_instance_count": alert_instance_count,
            "distinct_alert_uri_count": len(alert_uris),
            "candidate_injection_point_count": len(candidates),
            "sql_injection_alert_group_count": sql_injection_alert_group_count,
            "out_of_level_sqli_input_observation_count": (
                out_of_level_sqli_input_observation_count
            ),
        },
        "observations": observations,
        "candidate_injection_points": list(candidates.values()),
        "interpretation": {
            "sql_injection_detection": "not_assessed",
            "note": (
                "ZAP alert instances are passive/discovery observations. They do not "
                "establish SQL injection, ground truth, or full crawl coverage. "
                "Candidate input coordinates remain unverified until checked against "
                "the black-box scenario protocol."
            ),
        },
    }
    if inventory is not None:
        if inventory["security_level"] != security_level:
            raise ValueError("HAR inventory level differs from report level.")
        normalized["schema_version"] = "1.1.0"
        normalized["discovery_inventory"] = inventory
        normalized["run_metadata"]["authentication_status"] = inventory["authentication_status"]
        # Verified request/form evidence replaces matching alert-only coordinates.
        for point in inventory["candidate_injection_points"]:
            candidates[(point["path"], point["method"], point["parameter"])] = point
        normalized["candidate_injection_points"] = list(candidates.values())
        normalized["summary"]["candidate_injection_point_count"] = len(candidates)
        normalized["summary"]["verified_injection_point_count"] = len(inventory["candidate_injection_points"])
        normalized["interpretation"]["note"] = (
            "HAR coordinates are verified only with authenticated response and security-page "
            "evidence in the same session. Coverage describes scenario input coordinates, "
            "not vulnerability detection or complete application coverage."
        )
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="ZAP traditional JSON report")
    parser.add_argument("--har-report", type=Path, help="HAR from the same ZAP run (same file stem)")
    parser.add_argument("--require-complete-inputs", action="store_true", help="Fail unless HAR covers all scenario inputs at this level")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path (default: <report-name>.normalized.json)",
    )
    parser.add_argument(
        "--security-level",
        choices=("low", "medium", "high", "impossible", "unknown"),
        default="unknown",
        help="Level independently verified for this scanner session",
    )
    parser.add_argument(
        "--scan-mode",
        choices=("passive", "active", "unknown"),
        default="unknown",
        help="Scan mode from the run plan/log, not inferred from alerts",
    )
    parser.add_argument(
        "--authentication-status",
        choices=("verified", "unverified", "unknown"),
        default="unknown",
        help="Authentication status from independent run evidence",
    )
    return parser.parse_args()


def validate_normalized_report(report):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    schema = json.loads((schema_dir / "zap-normalized-run.schema.json").read_text(encoding="utf-8"))
    inventory_schema = json.loads((schema_dir / "zap-input-inventory.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resource("zap-input-inventory.schema.json", Resource.from_contents(inventory_schema))
    Draft202012Validator(schema, registry=registry).validate(report)


def main() -> None:
    args = parse_args()
    with args.report.open("r", encoding="utf-8") as source:
        report = json.load(source)

    if not isinstance(report, dict):
        raise SystemExit("Expected a ZAP report JSON object at the document root.")

    inventory = None
    if args.har_report:
        if args.har_report.stem != args.report.stem:
            raise SystemExit("The HAR and alert report must have the same run stem.")
        from export_zap_inputs import read_inventory
        inventory = read_inventory(args.har_report, args.security_level)
    elif args.require_complete_inputs:
        raise SystemExit("--require-complete-inputs requires --har-report.")
    normalized = normalize_report(
        report=report,
        source_report=args.report.name,
        security_level=args.security_level,
        scan_mode=args.scan_mode,
        authentication_status=args.authentication_status,
        inventory=inventory,
    )
    validate_normalized_report(normalized)
    output_path = args.output or args.report.with_name(
        f"{args.report.stem}.normalized.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(normalized, destination, ensure_ascii=False, indent=2)
        destination.write("\n")

    print(f"Normalized report written: {output_path}")
    print(json.dumps(normalized["summary"], ensure_ascii=False))
    if args.require_complete_inputs and (inventory["missing_scenario_ids"] or inventory["authentication_status"] != "verified"):
        raise SystemExit("Discovery input coverage or session verification is incomplete; see the normalized report.")


if __name__ == "__main__":
    main()
