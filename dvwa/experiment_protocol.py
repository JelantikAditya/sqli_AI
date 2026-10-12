"""Validate local pilot protocol and emit an audit snapshot, without executing probes."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rag_pipeline import ROOT, load_catalog
from validation_loop import require_local_target

DEFAULT_PROTOCOL = Path(__file__).with_name("local_experiment_protocol.json")


def load_protocol(path=DEFAULT_PROTOCOL):
    protocol = json.loads(path.read_text(encoding="utf-8"))
    catalog = load_catalog()
    require_local_target(protocol["target_origin"])
    if protocol["schema_version"] != "1.0.0" or protocol["environment"] != "local-laptop" or protocol["method"] != "DAST-black-box":
        raise ValueError("Unsupported experiment environment or protocol.")
    if protocol["status"] not in {"pilot", "frozen"}:
        raise ValueError("Protocol status must be pilot or frozen.")
    expected = [("A", "LLM", "off", list(range(1, 13))), ("B", "LLM", "on", list(range(1, 13))), ("C", "SecLists", "not_applicable", list(range(1, 10)))]
    actual = [(c["condition_id"], c["source"], c["rag_mode"], c["scenario_ids"]) for c in protocol["conditions"]]
    if actual != [(cid, source, rag, [f"S{i}" for i in ids]) for cid, source, rag, ids in expected]:
        raise ValueError("Conditions must match the A/B ablation and C positive-only PSR design.")
    seeds = protocol["replicate_seeds"]
    if len(seeds) != 3 or len(set(seeds)) != 3 or any(type(s) is not int for s in seeds):
        raise ValueError("Use three distinct integer replicate seeds.")
    gen, validation = protocol["generation"], protocol["validation"]
    if type(gen["candidate_budget"]) is not int or not 1 <= gen["candidate_budget"] <= catalog["protocol"]["max_candidates_per_run"]:
        raise ValueError("Candidate budget exceeds catalog limits.")
    if gen["stop_on_success"] or not gen["exclude_labels_from_prompt"] or gen["num_ctx"] < 2048:
        raise ValueError("Evaluation requires full budget, hidden labels, and adequate context.")
    for key in ("num_ctx", "num_predict", "top_k", "max_generation_retries_per_slot"):
        if type(gen[key]) is not int or gen[key] < 1:
            raise ValueError(f"generation.{key} must be a positive integer.")
    if gen["top_k"] > 10 or not isinstance(gen["model"], str) or not gen["model"].strip():
        raise ValueError("Use a named model and top-k between 1 and 10.")
    if type(gen["temperature"]) not in {int, float} or not math.isfinite(gen["temperature"]) or gen["temperature"] < 0:
        raise ValueError("Temperature must be finite and non-negative.")
    for key in ("request_timeout_seconds", "time_signal_threshold_ms"):
        if type(validation[key]) not in {int, float} or not math.isfinite(validation[key]) or validation[key] <= 0:
            raise ValueError(f"validation.{key} must be finite and positive.")
    if validation["execution"] != "serial" or validation["invalid_session_is_attack_failure"]:
        raise ValueError("Serial probes and infrastructure-error separation are required.")
    if validation["confirmations_per_candidate"] != 3 or validation["timing_control"] != "matched-no-delay":
        raise ValueError("Use three confirmations and a matched timing control.")
    if protocol["metrics"]["fpr_unit"] != "scenario-condition-replicate" or protocol["metrics"]["psr_unit"] != "logical-candidate":
        raise ValueError("Metric units do not match the protocol.")
    if not protocol["metrics"]["retain_system_prediction_before_review"] or protocol["metrics"]["zero_denominator"] != "undefined":
        raise ValueError("Do not filter system predictions or replace undefined metrics with zero.")
    metrics = protocol["metrics"]
    # Preserve independent run outcomes instead of voting across replications.
    if (metrics.get("aggregation") != "per-run-arithmetic-mean"
            or type(metrics.get("stddev_ddof")) is not int or metrics["stddev_ddof"] != 1
            or metrics.get("cross_run_success_vote") != "none"
            or metrics.get("primary_summary_requires_complete_replicates") is not True):
        raise ValueError("Use per-run means, sample standard deviations, no cross-run voting, and complete replicates.")
    if protocol["status"] == "frozen" and (protocol["review"]["corpus_researcher_review"] == "pending" or protocol["review"]["independent_validator"] == "pending"):
        raise ValueError("A frozen protocol requires recorded corpus and validator decisions.")
    return protocol


def experiment_matrix(protocol):
    return [{"condition_id": c["condition_id"], "source": c["source"], "rag_mode": c["rag_mode"],
             "scenario_id": sid, "replicate": r, "seed": seed}
            for c in protocol["conditions"] for sid in c["scenario_ids"]
            for r, seed in enumerate(protocol["replicate_seeds"], start=1)]


def snapshot(protocol, path):
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    scripts = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
               for folder in ("dvwa", "schemas", "knowledge") for p in sorted((ROOT / folder).glob("*"))
               if p.suffix in {".py", ".json", ".yaml"} and ".local." not in p.name}
    packages = {}
    for name in ("chromadb", "jsonschema", "pypdf", "langchain"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "pilot-config-snapshot-not-formal-runtime-freeze",
            "protocol_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "protocol": protocol,
            "git_revision": revision, "python": platform.python_version(), "packages": packages,
            "file_sha256": scripts, "matrix": experiment_matrix(protocol),
            "unresolved_formal_gate": protocol["formal_gate"], "formal_evaluation_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    result = {"protocol_id": protocol["protocol_id"], "status": protocol["status"], "run_count": len(experiment_matrix(protocol))}
    if args.write_manifest:
        directory = ROOT / "results/raw"
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / ("protocol-manifest-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        output.write_text(json.dumps(snapshot(protocol, args.protocol), indent=2) + "\n", encoding="utf-8")
        result["manifest"] = str(output)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
