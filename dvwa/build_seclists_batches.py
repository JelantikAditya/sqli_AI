"""Build audited SecLists batches from the frozen T04 selection plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prepare_candidate_batch import ROOT, SCENARIOS_PATH, validate_batch


PLAN_PATH = ROOT / "docs" / "evidence" / "seclists-selection-plan-2026-10-12.json"
TRANSFORM_RULE_ID = "seclists-mariadb-id-fragment-v1"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def placeholder_values(scenario_id: str, ordinal: int) -> dict[str, str]:
    """Use a fixed ordinal mapping, not values selected from response outcomes."""
    marker = f"T04{scenario_id}{ordinal:02d}"
    return {
        "RANDNUM": str(10 + ordinal),
        "RANDNUM1": str(20 + ordinal),
        "RANDNUM2": str(30 + ordinal),
        "RANDNUM3": str(40 + ordinal),
        "RANDNUM4": str(50 + ordinal),
        "RANDNUM5": str(60 + ordinal),
        "RANDSTR": marker,
        "ORIGVALUE": "1",
        "SLEEPTIME": "2",
        "DELIMITER_START": marker + "A",
        "DELIMITER_STOP": marker + "Z",
    }


def build_batch(plan: dict, plan_sha256: str, scenario: dict, source_root: Path) -> tuple[dict, Path]:
    scenario_id = scenario["scenario_id"]
    technique = plan["scenario_mapping"].get(scenario_id)
    if technique is None:
        raise ValueError(f"No SecLists technique mapping for {scenario_id}.")

    source_info = plan["files"][technique]
    relative_source = Path(source_info["path"])
    source_list = (source_root / relative_source).resolve()
    if not source_list.is_relative_to(source_root.resolve()):
        raise ValueError("SecLists source path must remain under --source-root.")
    if not source_list.is_file():
        raise FileNotFoundError(f"Missing pinned SecLists file: {source_list}")
    actual_hash = hashlib.sha256(source_list.read_bytes()).hexdigest()
    if actual_hash.lower() != source_info["sha256"].lower():
        raise ValueError(f"Hash mismatch for pinned SecLists file: {relative_source.as_posix()}")

    wrapper = "numeric_id" if scenario["security_level"] == "medium" else "quoted_id"
    provenance = {
        "repository": plan["repository"],
        "revision": plan["revision"],
        "list_path": source_info["path"],
        "list_sha256": source_info["sha256"],
        "selection_rule_id": plan["selection_rule_id"],
        "selection_manifest_sha256": plan_sha256,
    }
    candidates = []
    for ordinal, line_number in enumerate(source_info["selected_source_lines"], start=1):
        transform = {
            "rule_id": TRANSFORM_RULE_ID,
            "wrapper": wrapper,
            "placeholder_values": placeholder_values(scenario_id, ordinal),
        }
        candidate = {
            "candidate_id": f"seclists-{scenario_id.lower()}-{ordinal:03d}",
            "source_transform": transform,
        }
        if scenario["probe_kind"] == "boolean_pair":
            candidate["source_line_numbers"] = [line_number, line_number]
        else:
            candidate["source_line_number"] = line_number
        candidates.append(candidate)

    batch = {
        "schema_version": "1.0.0",
        "scenario_id": scenario_id,
        "source": "SecLists",
        "rag_mode": "not_applicable",
        "provenance": provenance,
        "candidates": candidates,
    }
    return validate_batch(batch, source_list), source_list


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", required=True, type=Path,
        help="Local root containing the exact pinned SecLists directory tree.",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        help="Destination under results/raw/ (defaults to a timestamped folder).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = read_json(PLAN_PATH)
    plan_bytes = PLAN_PATH.read_bytes()
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    catalog = read_json(SCENARIOS_PATH)
    scenarios = {item["scenario_id"]: item for item in catalog["scenarios"]}
    source_root = args.source_root.resolve()
    output_root = ROOT / "results" / "raw"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (args.output_dir or output_root / f"seclists-t04-{timestamp}").resolve()
    if not output_dir.is_relative_to(output_root.resolve()):
        raise SystemExit("Output directory must stay inside results/raw/.")
    output_dir.mkdir(parents=True, exist_ok=False)

    for scenario_id in plan["scenario_mapping"]:
        prepared, source_list = build_batch(plan, plan_sha256, scenarios[scenario_id], source_root)
        destination = output_dir / f"{scenario_id}.json"
        with destination.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(prepared, target, ensure_ascii=False, indent=2)
            target.write("\n")
        print(json.dumps({
            "scenario_id": scenario_id,
            "candidate_count": len(prepared["candidates"]),
            "source_path": source_list.relative_to(source_root).as_posix(),
            "output_path": str(destination),
            "plan_sha256": plan_sha256,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
