"""Replay saved Q3 model replies through v5 without API or DVWA access."""

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

import poolside_laguna_generation_v5 as generation
import qwen_api_generation as parser
import run_poolside_contract_smoke as contract
import run_qwen_api_experiments as engine


SOURCE = ROOT / "results/raw/pilot/poolside-s21-p3-q3-20261023"
EXPECTED_UNITS = 24


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): _digest(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


class SavedResponseAPI:
    """Supply a saved response and capture the newly rendered v5 request."""

    def __init__(self, responses: list[dict]):
        self.responses = iter(responses)
        self.messages: list[list[dict]] = []
        self.last_response: dict | None = None

    def chat(self, stage: str, messages: list[dict], attempt_directory: Path):
        if stage != "generation":
            raise AssertionError("The replay must not call the analysis API.")
        self.messages.append(messages)
        self.last_response = next(self.responses)
        checkpoint = {"stage": stage,
                      "request_sha256": self.last_response.get("request_sha256"),
                      "checkpoint_directory": "offline-replay"}
        return self.last_response, checkpoint


def _duplicate_signatures(response: dict, audit: dict, probe_kind: str) -> list[str]:
    duplicate_indices = {
        item.get("index") for item in audit.get("suggestions", [])
        if item.get("status") == "duplicate_structure"
    }
    if not duplicate_indices:
        return []
    try:
        candidates = json.loads(response.get("content", "")).get("candidates", [])
    except (AttributeError, TypeError, ValueError):
        return []
    signatures = []
    for index, candidate in enumerate(candidates, 1):
        if index in duplicate_indices:
            signature = generation.structure_signature(candidate, probe_kind)
            if signature not in signatures:
                signatures.append(signature)
    return signatures


def replay(directory: Path = SOURCE) -> dict:
    before = _inventory(directory)
    if not before:
        raise ValueError("The pinned Q3 run is missing or empty.")
    assessment = _read(directory / "qualification-assessment.json")
    ledger = [_read_line for _read_line in
              (json.loads(line) for line in (directory / "ledger.jsonl").read_text(
                  encoding="utf-8").splitlines() if line.strip())]
    scenarios = {item["scenario_id"]: item
                 for item in engine.local_runner.load_catalog()["scenarios"]}
    unit_summaries = []
    parser_status_counts: Counter[str] = Counter()
    parser_mismatches = []
    request_hash_mismatches = 0
    family_id_collisions = 0
    retry_signature_coverage_checks = 0
    retry_signature_coverage_failures = 0
    generation_calls = 0

    for event in ledger:
        if event.get("event_type") != "attempt_completed":
            continue
        attempt_directory = Path(event["runner_batch_path"]).parent
        result_path = attempt_directory / "qwen-api-adaptive-result.json"
        result = _read(result_path)
        context = result["context"]
        scenario_id = context["scenario_id"]
        scenario = scenarios[scenario_id]
        probe_kind = scenario["probe_kind"]
        saved_audit = _read(attempt_directory / "adaptive-generation-audit.json")
        saved_events = saved_audit["events"]
        canonical = json.dumps(saved_events, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != saved_audit["events_sha256"]:
            raise ValueError("A Q3 generation-event hash does not match its saved event body.")

        responses = []
        response_by_sequence = {}
        for saved in saved_events:
            if saved.get("kind") != "generation":
                continue
            old = saved["data"]["audit"]
            checkpoint_directory = old["checkpoint"]["checkpoint_directory"]
            call_directory = directory / checkpoint_directory
            request_record = _read(call_directory / "request.json")
            response_record = _read(call_directory / "result.json")
            response = response_record["result"]
            request_hash = contract.request_hash(request_record["payload"])
            if (request_hash != request_record.get("request_sha256")
                    or request_hash != old.get("request_sha256")
                    or request_hash != response.get("request_sha256")):
                request_hash_mismatches += 1
            responses.append(response)
            response_by_sequence[saved["sequence"]] = response

        fake_api = SavedResponseAPI(responses)
        callback = generation.make_generation_callback(
            fake_api, Path("offline-replay"), scenario, None,
            {"http_status": 200}, {"limits": {"max_retrieved_chars_per_chunk": 1800}})
        accepted = []
        requested_family_ids: set[str] = set()
        duplicate_signatures_by_slot: dict[int, list[str]] = {}
        last_status_by_slot: dict[int, str | None] = {}
        local_statuses: Counter[str] = Counter()
        scheduled_family_ids = []

        for saved in saved_events:
            if saved.get("kind") != "generation":
                continue
            saved_data = saved["data"]
            slot = saved_data["slot"]
            retry_index = saved_data["retry"]
            if slot != len(accepted) + 1:
                parser_mismatches.append({"unit": context["run_id"], "kind": "slot-order"})
                continue
            response = response_by_sequence[saved["sequence"]]
            rejection_code = last_status_by_slot.get(slot) if retry_index else None
            candidate, replay_audit = callback(
                None, accepted, retry_index, rejection_code)
            local_statuses[replay_audit["status"]] += 1
            parser_status_counts[replay_audit["status"]] += 1
            generation_calls += 1
            if replay_audit["status"] != saved_data["status"]:
                parser_mismatches.append({
                    "unit": context["run_id"], "slot": slot,
                    "retry": retry_index, "kind": "parser-status",
                    "saved": saved_data["status"], "replayed": replay_audit["status"],
                })
            family_id = replay_audit["family_id"]
            family_id_collisions += int(family_id in requested_family_ids)
            requested_family_ids.add(family_id)
            scheduled_family_ids.append(family_id)

            task = json.loads(fake_api.messages[-1][1]["content"])
            contract_data = task.get("variation_contract")
            if not isinstance(contract_data, dict):
                retry_signature_coverage_failures += 1
            else:
                forbidden = set(contract_data.get("avoid_structural_signatures", []))
                expected = {generation.structure_signature(item, probe_kind)
                            for item in accepted}
                expected.update(duplicate_signatures_by_slot.get(slot, []))
                if expected:
                    retry_signature_coverage_checks += 1
                    if not expected.issubset(forbidden):
                        retry_signature_coverage_failures += 1

            if candidate is not None:
                accepted.append(candidate)
                duplicate_signatures_by_slot.pop(slot, None)
                last_status_by_slot.pop(slot, None)
            else:
                duplicate_signatures_by_slot.setdefault(slot, [])
                for signature in _duplicate_signatures(response, replay_audit, probe_kind):
                    if signature not in duplicate_signatures_by_slot[slot]:
                        duplicate_signatures_by_slot[slot].append(signature)
                last_status_by_slot[slot] = replay_audit["status"]

        saved_candidate_count = result["run_summary"]["candidate_count"]
        if len(accepted) != saved_candidate_count:
            parser_mismatches.append({"unit": context["run_id"], "kind": "accepted-count",
                                      "saved": saved_candidate_count, "replayed": len(accepted)})
        unit_summaries.append({
            "unit": f"{context['condition_id']}/{scenario_id}",
            "saved_candidates": saved_candidate_count,
            "replayed_candidates": len(accepted),
            "budget_complete": result["run_summary"]["budget_complete"],
            "generation_calls_replayed": sum(local_statuses.values()),
            "family_ids_unique": len(scheduled_family_ids) == len(set(scheduled_family_ids)),
            "parser_status_counts": dict(local_statuses),
        })

    after = _inventory(directory)
    if (before != after or parser_mismatches or request_hash_mismatches
            or family_id_collisions or len(unit_summaries) != EXPECTED_UNITS
            or retry_signature_coverage_failures):
        raise ValueError("Q3 v5 replay, request integrity, prompt-feedback, or preservation check failed.")

    recorded_units = {item["unit"]: item for item in assessment["unit_results"]}
    for unit in unit_summaries:
        recorded = recorded_units.get(unit["unit"])
        if recorded is None or unit["saved_candidates"] != recorded["generated_candidate_count"]:
            raise ValueError("Replayed Q3 unit counts differ from the saved qualification assessment.")

    inventory_digest = hashlib.sha256(json.dumps(
        before, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "poolside-laguna-q3-v5-offline-replay-v1",
        "source_experiment_id": assessment["experiment_id"],
        "replay_profile": generation.PROMPT_VERSION,
        "retry_policy_id": generation.RETRY_POLICY_ID,
        "source_unit_count": len(unit_summaries),
        "source_generation_calls_replayed": generation_calls,
        "saved_candidate_count": sum(item["saved_candidates"] for item in unit_summaries),
        "replayed_candidate_count": sum(item["replayed_candidates"] for item in unit_summaries),
        "saved_generation_status_counts": dict(parser_status_counts),
        "parser_status_mismatches": parser_mismatches,
        "saved_request_hash_mismatches": request_hash_mismatches,
        "replayed_family_id_collisions": family_id_collisions,
        "unit_family_ids_unique": all(item["family_ids_unique"] for item in unit_summaries),
        "retry_signature_coverage_checks": retry_signature_coverage_checks,
        "retry_signature_coverage_failures": retry_signature_coverage_failures,
        "source_files_preserved": len(before),
        "source_inventory_sha256": inventory_digest,
        "source_files_unchanged": before == after,
        "api_requests_sent": 0,
        "dvwa_requests_sent": 0,
        "interpretation": (
            "Saved Q3 replies replay with the existing parser and preserve the original assessment. "
            "The v5 request now carries normalized signatures for accepted and rejected structures. "
            "Since replies were generated before the v5 prompt existed, this replay validates feedback "
            "rendering and regression behavior, not v5 model performance or qualification success."
        ),
        "units": unit_summaries,
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
