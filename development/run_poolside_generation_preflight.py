"""Six bounded generation requests: three SQLi techniques, with and without RAG.

--prepare queries only local embedding/retrieval services on a copied index.
--run consumes that frozen plan. Generated candidates never reach DVWA here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
import run_qwen_api_experiments as builder
import qwen_api_generation as generation
import run_poolside_contract_smoke as contract
import run_poolside_smoke as transport
from validation_loop import matched_no_delay_payload


PROFILE = "poolside-laguna-s-2.1-blackbox-generation-v1"
ORDER = (("S1", "A"), ("S1", "B"), ("S2", "B"), ("S2", "A"), ("S3", "A"), ("S3", "B"))
SNAPSHOT_PLAN = ROOT / "development/qwen_api_p3_v5_r5_plan.template.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def make_entry(scenario: dict, condition: str, retrieval: dict | None) -> dict:
    if condition not in {"A", "B"} or (condition == "A" and retrieval is not None):
        raise ValueError("RAG-off must not consume a retrieval record.")
    chunks = builder.safe_retrieval(retrieval, {"limits": {"max_retrieved_chars_per_chunk": 1800}})
    if condition == "B" and len(chunks) != 2:
        raise ValueError("RAG-on requires exactly two retrieved chunks.")
    # Empty baseline is explicit: no new target measurement is fabricated.
    prepared, messages = builder.generation_messages(scenario, [], chunks, {}, None, 0, None)
    payload = {"model": transport.MODEL, "messages": messages, "temperature": 0,
               "max_tokens": 1024, "stream": False,
               "chat_template_kwargs": {"enable_thinking": False}}
    return {"scenario_id": scenario["scenario_id"], "condition_id": condition,
            "probe_kind": scenario["probe_kind"], "technique": scenario["sqli_type"],
            "prepared": prepared, "payload": payload,
            "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in chunks],
            "request_sha256": contract.request_hash(payload)}


def prepare(destination: Path) -> dict:
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / "results/raw/poolside-generation-preflight"):
        raise ValueError("Output must stay in the Poolside generation preflight directory.")
    destination.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads(SNAPSHOT_PLAN.read_text(encoding="utf-8"))["knowledge_snapshot"]
    for field in ("manifest", "corpus", "source_lock", "review_decision"):
        if digest(ROOT / snapshot[field + "_path"]) != snapshot[field + "_sha256"]:
            raise ValueError("Approved knowledge snapshot changed: " + field)
    manifest = builder.read_manifest(ROOT / snapshot["manifest_path"])
    protocol_path = ROOT / "dvwa/local_experiment_protocol.json"
    catalog_path = ROOT / "dvwa/experiment_scenarios.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["generation"]["top_k"] != 2:
        raise ValueError("The proposal retrieval top-k changed.")
    scenarios = {row["scenario_id"]: row for row in builder.load_catalog()["scenarios"]}
    # A entries are rendered before any vector-store copy or query is opened.
    entries = {(sid, "A"): make_entry(scenarios[sid], "A", None) for sid in ("S1", "S2", "S3")}
    index_copy = builder.copy_verified_index_snapshot(manifest, snapshot, destination / "index-copy", ROOT)
    retrieval_manifest = {**manifest, "resolved_store_path": str(destination / "index-copy")}
    retrievals = {}
    for sid in ("S1", "S2", "S3"):
        scenario = scenarios[sid]
        query = builder.scenario_query(scenario, mode="focused")
        retrieved = builder.retrieve_chunks(query, retrieval_manifest, 2,
                                             technique=scenario["sqli_type"], mode="proposal")
        retrievals[sid] = retrieved
        entries[(sid, "B")] = make_entry(scenario, "B", retrieved)
    source_index_after = builder.store_file_hashes(Path(manifest["resolved_store_path"]))
    if source_index_after != index_copy["snapshot_file_sha256"]:
        raise ValueError("The source Chroma index changed during retrieval.")
    paths = [Path(__file__), Path(builder.__file__), Path(generation.__file__),
             Path(contract.__file__), Path(transport.__file__),
             ROOT / "dvwa/adaptive_candidate_policy.py", ROOT / "dvwa/adaptive_s1_loop.py",
             ROOT / "dvwa/validation_loop.py", ROOT / "dvwa/rag_pipeline.py",
             ROOT / "dvwa/retrieve_structured_knowledge.py", ROOT / "dvwa/knowledge_corpus.py",
             ROOT / "dvwa/generate_candidate_batch.py", catalog_path, protocol_path, SNAPSHOT_PLAN,
             *(ROOT / snapshot[field + "_path"] for field in ("manifest", "corpus", "source_lock", "review_decision"))]
    plan = {"profile_id": PROFILE, "base_url": transport.BASE_URL, "requested_model": transport.MODEL,
            "scope": "development-generation-preflight; no target execution or formal metrics",
            "baseline_policy": "not measured in this preflight; empty object supplied equally to A/B",
            "max_requests": 6, "max_completion_tokens_total": 6144, "timeout_seconds": 60,
            "automatic_retries": 0, "model_fallback": False, "dvwa_requests": 0,
            "generation_prompt_version": builder.PROMPT_VERSION, "candidate_slot": 1,
            "max_chars_per_retrieved_chunk": 1800, "retrieval_top_k": 2,
            "retrieval_by_scenario": retrievals, "index_copy": index_copy,
            "source_index_unchanged_after_retrieval": True,
            "source_sha256": {path.relative_to(ROOT).as_posix(): digest(path) for path in paths},
            "entries": [entries[key] for key in ORDER]}
    write_new(destination / "plan.json", plan)
    write_new(destination / "plan.receipt.json", {"plan_sha256": digest(destination / "plan.json")})
    for relative in plan["source_sha256"]:
        path = ROOT / relative
        if path.suffix == ".py":
            target = destination / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(path.read_bytes())
    return {"status": "prepared", "max_requests": 6, "plan_path": str(destination / "plan.json"),
            "source_index_unchanged": True, "local_embedding_requests": 3}


def validate_output(entry: dict, api: dict) -> dict:
    parsed = generation.parse(entry["prepared"], [], entry["probe_kind"], api)
    if parsed["status"] == "generated":
        try:
            builder.validate_candidate_policy(parsed["candidate"], entry["probe_kind"], entry["scenario_id"])
        except (ValueError, KeyError):
            return {**parsed, "status": "invalid_candidate_policy"}
        if entry["probe_kind"] == "single_time":
            parsed["matched_no_delay_control"] = matched_no_delay_payload(parsed["candidate"]["payload"])
    return parsed


def run(plan_path: Path, key: str, opener=None) -> dict:
    receipt = json.loads(plan_path.with_name("plan.receipt.json").read_text(encoding="utf-8"))
    if digest(plan_path) != receipt["plan_sha256"]:
        raise ValueError("Frozen plan hash changed.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["profile_id"] != PROFILE or len(plan["entries"]) != 6 or plan["max_requests"] != 6:
        raise ValueError("Unsupported preflight plan.")
    if any(digest(ROOT / path) != expected for path, expected in plan["source_sha256"].items()):
        raise ValueError("A frozen source/input changed before execution.")
    destination = plan_path.parent
    # Reserve the run before any request so a second process cannot resend it.
    write_new(destination / "execution-started.json", {"started_at_utc": datetime.now(timezone.utc).isoformat()})
    key = transport.validate_key(key)
    opener = opener if opener is not None else transport.build_opener(transport.NoRedirect())
    rows = []
    for entry in plan["entries"]:
        if contract.request_hash(entry["payload"]) != entry["request_sha256"]:
            raise ValueError("Prepared request hash changed.")
        call_id = entry["scenario_id"] + "-" + entry["condition_id"]
        write_new(destination / (call_id + ".started.json"), {"request_sha256": entry["request_sha256"]})
        response = transport.request_once(opener, key, "/chat/completions", entry["payload"])
        if response.get("request_sha256") != entry["request_sha256"]:
            raise ValueError("Sent request differs from the frozen plan.")
        api = {**contract.api_result(response), "request_sha256": response["request_sha256"]}
        parsed = validate_output(entry, api)
        write_new(destination / (call_id + ".result.json"), transport.redact({"transport": response, "api": api,
                                                                            "parsed": parsed}, key))
        row = {"scenario_id": entry["scenario_id"], "condition_id": entry["condition_id"],
               "api_status": api["status"], "http_status": api["http_status"], "parse_status": parsed["status"],
               "candidate": parsed.get("candidate"), "retrieved_chunk_ids": entry["retrieved_chunk_ids"],
               "elapsed_seconds": api["elapsed_seconds"], "usage": api.get("usage")}
        rows.append(row)
        print(json.dumps(row), flush=True)
        if api.get("halt"):
            break
    success = len(rows) == 6 and all(row["parse_status"] == "generated" for row in rows)
    summary = {"status": "ok" if success else "incomplete-or-failed", "profile_id": PROFILE,
               "requests_sent": len(rows), "valid_candidates": sum(row["parse_status"] == "generated" for row in rows),
               "total_tokens": sum((row.get("usage") or {}).get("total_tokens", 0) for row in rows),
               "api_elapsed_seconds": round(sum(row["elapsed_seconds"] for row in rows), 3),
               "automatic_retries": 0, "dvwa_requests": 0, "formal_eligible": False,
               "rows": rows, "output_dir": str(destination)}
    write_new(destination / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if args.prepare:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        print(json.dumps(prepare(ROOT / "results/raw/poolside-generation-preflight" / stamp), indent=2))
        return 0
    if args.plan is None:
        parser.error("--run requires --plan pointing to a frozen plan.json")
    key = transport.load_key()
    if not key:
        print(json.dumps({"status": "missing-api-key", "requests_sent": 0}))
        return 2
    summary = run(args.plan.resolve(), key)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
