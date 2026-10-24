"""Replay Q2 generation replies through the v4 scheduler, without network calls."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
sys.path.insert(0, str(ROOT / "dvwa"))

import qwen_api_generation as parser
import run_poolside_contract_smoke as contract
import run_qwen_api_experiments as engine
import poolside_laguna_generation_v4 as generation


SOURCE = ROOT / "results/raw/pilot/poolside-s21-p3-q2-20261022"
EXPECTED_UNITS = 24


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): _digest(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def replay(directory: Path = SOURCE) -> dict:
    before = _inventory(directory)
    if not before:
        raise ValueError("The pinned Q2 checkpoint is missing or empty.")
    units = []
    mismatches = []
    response_hash_mismatches = 0
    family_id_collisions = 0
    family_key_collisions = 0
    family_selections = 0
    fallback_selections = 0
    parser_status_counts: Counter[str] = Counter()

    for result_path in sorted(directory.glob("attempts/*/*/qwen-api-adaptive-result.json")):
        attempt_directory = result_path.parent
        result = _read(result_path)
        context = result["context"]
        scenario_id = context["scenario_id"]
        scenario = next(item for item in engine.local_runner.load_catalog()["scenarios"]
                        if item["scenario_id"] == scenario_id)
        probe_kind = scenario["probe_kind"]
        audit_record = _read(attempt_directory / "adaptive-generation-audit.json")
        events = audit_record["events"]
        canonical_events = json.dumps(events, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"), allow_nan=False).encode()
        if hashlib.sha256(canonical_events).hexdigest() != audit_record["events_sha256"]:
            raise ValueError("A saved Q2 generation-event hash does not match its event body.")

        accepted = []
        rejected_by_slot: dict[int, list] = {}
        requested_family_ids: set[str] = set()
        unit_statuses = Counter()

        for event in events:
            if event.get("kind") != "generation":
                continue
            saved = event["data"]
            old_audit = saved["audit"]
            slot = saved["slot"]
            if slot != len(accepted) + 1:
                mismatches.append({"unit": context["run_id"], "kind": "slot-order"})
                continue
            rejected = rejected_by_slot.setdefault(slot, [])
            occupied_family_ids = set(requested_family_ids)
            family = generation.select_family(probe_kind, slot, [*accepted, *rejected],
                                              requested_family_ids)
            occupied = {parser.structural_key(
                {"payload": value} if isinstance(value, str) else value, probe_kind)
                for value in accepted}
            family_id_collisions += int(family.family_id in occupied_family_ids)
            family_key_collisions += int(family.structural_key in occupied)
            family_selections += 1
            if family.family_id != generation.FAMILIES[probe_kind][slot - 1].family_id:
                fallback_selections += 1
            requested_family_ids.add(family.family_id)

            checkpoint = old_audit["checkpoint"]["checkpoint_directory"]
            call_directory = directory / checkpoint
            request = _read(call_directory / "request.json")
            response_record = _read(call_directory / "result.json")
            response = response_record["result"]
            request_hash = contract.request_hash(request["payload"])
            if (request_hash != request.get("request_sha256")
                    or request_hash != old_audit.get("request_sha256")
                    or request_hash != response.get("request_sha256")):
                response_hash_mismatches += 1

            prepared = {
                "prompt_version": generation.PROMPT_VERSION,
                "slot_id": slot,
                "family_index": len(requested_family_ids),
                "schema": parser.output_schema(probe_kind, 1),
            }
            parsed = parser.parse(prepared, [*accepted, *rejected], probe_kind, response)
            status = parsed["status"]
            candidate = parsed.get("candidate")
            if candidate is not None:
                try:
                    engine.validate_candidate_policy(candidate, probe_kind, scenario_id)
                except (KeyError, ValueError):
                    status = "invalid_candidate_policy"

            parser_status_counts[status] += 1
            unit_statuses[status] += 1
            if status != saved["status"]:
                mismatches.append({"unit": context["run_id"], "kind": "parser-status"})

            if status == "generated" and candidate is not None:
                accepted.append(candidate["payload"] if scenario_id == "S1" else candidate)
                rejected_by_slot.pop(slot, None)
            elif status == "no_valid_distinct_candidate":
                generation._remember_duplicate(parsed, response, rejected)
            elif status == "invalid_candidate_policy" and candidate is not None \
                    and candidate not in rejected:
                rejected.append(candidate)

        summary = result["run_summary"]
        if len(accepted) != summary["candidate_count"]:
            mismatches.append({"unit": context["run_id"], "kind": "accepted-count"})
        units.append({
            "unit": f"{context['condition_id']}/{scenario_id}",
            "replayed_candidates": len(accepted),
            "saved_candidates": summary["candidate_count"],
            "saved_budget_complete": summary["budget_complete"],
            "generation_calls_replayed": sum(unit_statuses.values()),
            "v4_family_ids_unique": len(requested_family_ids) == sum(unit_statuses.values()),
            "parser_status_counts": dict(unit_statuses),
        })

    after = _inventory(directory)
    assessment = _read(directory / "qualification-assessment.json")
    if (before != after or mismatches or response_hash_mismatches or family_id_collisions
            or family_key_collisions
            or len(units) != EXPECTED_UNITS):
        raise ValueError("Q2 replay, request integrity, family schedule, or preservation check failed.")
    for unit in units:
        recorded = next(item for item in assessment["unit_results"] if item["unit"] == unit["unit"])
        if unit["replayed_candidates"] != recorded["generated_candidate_count"]:
            raise ValueError("Q2 unit count differs between its saved assessment and replay.")

    return {
        "schema": "poolside-laguna-q2-v4-offline-replay-v1",
        "source_experiment_id": assessment["experiment_id"],
        "replay_profile": generation.PROMPT_VERSION,
        "generation_retry_policy_id": generation.RETRY_POLICY_ID,
        "source_unit_count": len(units),
        "source_candidate_count": sum(item["replayed_candidates"] for item in units),
        "source_generation_calls_replayed": family_selections,
        "v4_family_selections": family_selections,
        "v4_fallback_selections": fallback_selections,
        "v4_family_id_collisions": family_id_collisions,
        "v4_reference_key_collisions_with_accepted_candidates": family_key_collisions,
        "unique_family_ids_within_each_unit": all(item["v4_family_ids_unique"] for item in units),
        "saved_response_hash_mismatches": response_hash_mismatches,
        "parser_replay_mismatches": mismatches,
        "parser_status_counts": dict(parser_status_counts),
        "source_files_preserved": len(before),
        "source_inventory_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "source_files_unchanged": before == after,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "interpretation": (
            "The replay checks saved Q2 response parsing and confirms that v4 never assigns an already-requested "
            "family or a reference key matching an accepted candidate. The saved responses were generated under "
            "the older prompt, so this replay does not predict v4 model performance or qualification success."
        ),
        "units": units,
    }


def main() -> int:
    import argparse

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, default=SOURCE)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    with patch("socket.socket.connect", side_effect=AssertionError("Replay must remain offline")):
        result = replay(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "units"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
