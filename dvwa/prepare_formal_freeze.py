"""Prepare a traceable U07 readiness package without running experiments or freezing a protocol."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from experiment_dataset import load_runs
from experiment_protocol import load_protocol
from execution_order_policy import ordered_run_slots
from knowledge_corpus import prepare_documents, validate_corpus
from retrieve_structured_knowledge import retrieval_policy
from run_local_experiments import validate_knowledge_snapshot, validate_plan

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "results/raw/pilot/u07-v17-integrated-20261017"
ZAP = ROOT / "results/raw/u06-zap-api-explicit-20261016"
REVIEW = ROOT / "results/raw/u06-v15-integrated-review-sample-20261016"
REVIEW_AUDIT = ROOT / "results/raw/pilot/u06-v15-integrated-20261016/review-audit.json"
CORPUS_DECISION = ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json"
APPROVED_INDEX_ARCHIVE = ROOT / "results/raw/u07-formal-readiness-20261017/source-index-evidence.zip"
REQUIRED_GATE_IDS = {
    "pilot-all-techniques-and-levels-passed", "researcher-corpus-decision-recorded",
    "runtime-manifest-frozen", "seclists-version-and-selection-frozen", "validator-protocol-ready",
    "local-methodology-recorded", "local-langchain-integration-verified",
    "context-and-runtime-preflight", "active-zap-coordinate-coverage", "retrieval-index-snapshot-pinned",
    "offline-contract-checks",
}
DOCKER_IMAGES = {
    "dvwa": "ghcr.io/digininja/dvwa@sha256:ed35515e9111801e6e386a6fbb11165508cc7f72e0cb8da4dbb3df70182986c6",
    "database": "mariadb@sha256:7f22313fc130a377a44999965bcb0a08dd5b21e8502824c1b864f792f9bc66ab",
    "zap": "ghcr.io/zaproxy/zaproxy@sha256:781a2bdaea47324e7bab583e2263f21d257b0aee61ed51521a5be45f5f5081ef",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


class CorpusSnapshotMismatch(ValueError):
    """The recorded researcher approval no longer matches active corpus/index bytes."""

    def __init__(self, mismatches):
        super().__init__("Formal corpus decision snapshot mismatch.")
        self.mismatches = mismatches


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def resolve_pilot_path(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    pilot_root = (ROOT / "results/raw/pilot").resolve()
    if not path.is_relative_to(pilot_root) or not path.is_dir():
        raise ValueError("Pilot evidence must be an existing directory under results/raw/pilot/.")
    return path


def command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=45,
                            encoding="utf-8", errors="replace")
    return {"exit_code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def request_json(path):
    # Metadata endpoints only. This helper never invokes inference or sends SQLi probes.
    with urllib.request.urlopen("http://127.0.0.1:11434" + path, timeout=10) as response:
        return json.load(response)


def capture_runtime(pilot_path=PILOT):
    pilot_path = resolve_pilot_path(pilot_path)
    packages = sorted(({"name": d.metadata["Name"], "version": d.version}
                       for d in importlib.metadata.distributions()), key=lambda d: d["name"].lower())
    startup = command([sys.executable, "-c", "import sys; print(sys.version); print(sys.prefix)"])
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": {"version": platform.python_version(), "executable": sys.executable,
                         "platform": platform.platform(), "startup": startup},
              "packages": packages, "pip_check": command([sys.executable, "-m", "pip", "check"]),
              "docker_version": command(["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"]),
              "lab_containers": command(["docker", "ps", "--filter", "name=dvwa-", "--format",
                                          "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]),
              "docker_images": {}, "ollama_version": request_json("/api/version"),
              "models": [m for m in request_json("/api/tags")["models"]
                         if m["name"] in {"qwen2.5:7b", "nomic-embed-text:latest"}],
              "disk": dict(zip(("total", "used", "free"), shutil.disk_usage(ROOT)))}
    for name, reference in DOCKER_IMAGES.items():
        result["docker_images"][name] = {"reference": reference, "inspection": command([
            "docker", "image", "inspect", reference, "--format", "{{.Id}} {{json .RepoDigests}}"])}
    result["zap_bundled_addons"] = command([
        "docker", "run", "--rm", "--pull=never", "--network", "none", "--entrypoint", "sh",
        DOCKER_IMAGES["zap"], "-c", "ls /zap/zap-*.jar /zap/plugin/*.zap"])
    for name, query in {
        "os": "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,TotalVisibleMemorySize | ConvertTo-Json -Compress",
        "cpu": "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress",
        "gpu": "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion | ConvertTo-Json -Compress",
    }.items():
        result[name] = command(["powershell.exe", "-NoProfile", "-Command", query])
    result["nvidia"] = command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    with urllib.request.urlopen("http://127.0.0.1:4280/login.php", timeout=10) as response:
        body = response.read()
        result["dvwa_reachability"] = {"http_status": response.status,
                                        "response_sha256": hashlib.sha256(body).hexdigest(),
                                        "login_page_marker_present": b"Login :: Damn Vulnerable Web Application" in body}
    result["pilot_server_log"] = {"coverage_verified": False}
    ledger_path = pilot_path / "ledger.jsonl"
    ledger_events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    first_call = next(e for e in ledger_events if e["event_type"] == "attempt_started")
    last_call = next(e for e in reversed(ledger_events) if e["event_type"] == "attempt_completed")
    jakarta = timezone(timedelta(hours=7))
    local_start = datetime.fromisoformat(first_call["recorded_at_utc"]).astimezone(jakarta)
    local_end = datetime.fromisoformat(last_call["recorded_at_utc"]).astimezone(jakarta)
    boundaries = []
    for label, stamp in (("start", local_start), ("end", local_end)):
        boundaries.append({"label": label, "local": stamp.isoformat(),
                           "markers": (stamp.strftime("%Y-%m-%dT%H:"),
                                       stamp.strftime("%Y/%m/%d - %H:"))})
    for path in (Path.home() / "AppData/Local/Ollama").glob("server*.log"):
        log = path.read_text(encoding="utf-8", errors="replace")
        if all(any(marker in log for marker in boundary["markers"]) for boundary in boundaries):
            counts = collections.Counter(re.findall(r"truncated\s*=\s*(\d+)", log))
            result["pilot_server_log"] = {"path": str(path), "sha256": digest(path),
                "coverage_verified": True, "coverage": "Contains both recorded pilot boundary hours; log may also cover other calls.",
                "expected_boundaries": boundaries,
                "release_truncation_counts": dict(counts),
                "positive_truncation_count": sum(n for flag, n in counts.items() if int(flag) > 0),
                "explicit_input_truncation_warnings": len(re.findall("truncating input prompt", log, re.I))}
            break
    if not result["pilot_server_log"]["coverage_verified"]:
        result["pilot_server_log"]["expected_boundaries"] = boundaries
        result["pilot_server_log"]["coverage"] = "No Ollama server log verified both selected pilot boundary hours."
    return result


def assess_context(audits):
    """Fail closed when a recorded call is unfinished, unaccounted, or exceeds its token budget."""
    rows, issues = [], []
    for audit in audits:
        metrics, options = audit.get("runtime_metrics", {}), audit.get("options", {})
        keys = (metrics.get("prompt_eval_count"), metrics.get("eval_count"),
                options.get("num_ctx"), options.get("num_predict"))
        if any(type(value) is not int or value < 1 for value in keys):
            issues.append("missing_or_invalid_token_accounting")
            continue
        prompt, output, context, prediction_limit = keys
        rows.append((prompt, output, context, prediction_limit))
        if metrics.get("done") is not True or metrics.get("done_reason") != "stop":
            issues.append("response_not_cleanly_stopped")
        # Reserve the configured output allowance, rather than only the output observed.
        if prompt + prediction_limit > context or output >= prediction_limit:
            issues.append("context_or_output_budget_exhaustion")
    return {"status": "passed_for_recorded_calls" if rows and not issues else "pending",
            "calls": len(audits), "accounted_calls": len(rows),
            "maximum_prompt_tokens": max((r[0] for r in rows), default=None),
            "maximum_output_tokens": max((r[1] for r in rows), default=None),
            "minimum_reserved_context_headroom": min((r[2] - r[0] - r[3] for r in rows), default=None),
            "issues": dict(collections.Counter(issues)),
            "scope": "Observed pilot calls; token counts alone do not prove future prompts cannot truncate."}


def select_completed_llm_adaptive_artifacts(adaptive_documents, runs):
    """Select only the final completed A/B attempt artifacts for integration gates."""
    final_attempt_ids = {
        run["attempt_id"] for run in runs
        if run["status"] == "completed" and run["condition_id"] in {"A", "B"}
        and run.get("attempt_id")
    }
    final_documents = {}
    nonfinal_count = 0
    for document in adaptive_documents:
        attempt_id = document.get("context", {}).get("attempt_id")
        if attempt_id not in final_attempt_ids:
            # Invalid/retried attempts remain archived, but do not represent a
            # metric-eligible A/B condition-run in the integration gate.
            nonfinal_count += 1
            continue
        if attempt_id in final_documents:
            raise ValueError("Multiple adaptive artifacts found for a completed LLM attempt: " + attempt_id)
        final_documents[attempt_id] = document
    return final_attempt_ids, final_documents, nonfinal_count


def pilot_audit(pilot_path=PILOT):
    pilot_path = resolve_pilot_path(pilot_path)
    runs = load_runs(pilot_path)  # Existing loader validates sequence, artifact hashes, evidence, and analysis summaries.
    pilot_plan = read_json(pilot_path / "plan.snapshot.json")["plan"]
    knowledge_snapshot = pilot_plan.get("knowledge_snapshot")
    incomplete = [{"unit_id": r["unit_id"], "candidate_count": len(r["candidates"]),
                   "candidate_budget": r["candidate_budget"]} for r in runs
                  if r.get("candidate_budget") and len(r["candidates"]) != r["candidate_budget"]]
    generation, analysis, orchestration, retrieval_checks = [], [], [], []
    for path in (pilot_path / "attempts").glob("*/*/adaptive-generation-audit.json"):
        document = read_json(path)
        # Runner audit hashes use compact JSON; original adaptive artifacts use
        # the analysis module's serialization and are checked by load_runs above.
        canonical = json.dumps(document["events"], ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()
        if hashlib.sha256(canonical).hexdigest() != document["events_sha256"]:
            raise ValueError("Generation audit event hash mismatch.")
        generation.extend(e["data"]["audit"] for e in document["events"] if e["kind"] == "generation")

    adaptive_documents = [read_json(path) for path in
                          (pilot_path / "attempts").glob("*/*/adaptive/*.json")]
    for document in adaptive_documents:
        analysis.extend(c["audit"]["provenance"] for c in document["candidate_records"])
    final_llm_attempt_ids, final_adaptive, nonfinal_adaptive_artifacts = (
        select_completed_llm_adaptive_artifacts(adaptive_documents, runs))

    for document in final_adaptive.values():
        runtime = document["runtime"]
        orchestration.append(runtime["orchestration"])
        retrieval = runtime["retrieval"]
        condition = document["context"]["condition_id"]
        retrieval_checks.append(retrieval is None if condition == "A" else
                                retrieval is not None and retrieval["top_k_requested"] == 2)
    expected_completed = {(f"S{i}", condition) for i in range(1, 13) for condition in ("A", "B")}
    expected_completed |= {(f"S{i}", "C") for i in range(1, 10)}
    expected_excluded = {(f"S{i}", "C") for i in range(10, 13)}
    completed_pairs = {(r["scenario_id"], r["condition_id"]) for r in runs if r["status"] == "completed"}
    excluded_pairs = {(r["scenario_id"], r["condition_id"]) for r in runs if r["status"] == "excluded"}
    outcome_counts = {}
    for condition in ("A", "B", "C"):
        condition_runs = [r for r in runs if r["condition_id"] == condition and r["status"] == "completed"]
        candidate_total = sum(len(r["candidates"]) for r in condition_runs)
        successes = sum(bool(c["confirmed_success"]) for r in condition_runs for c in r["candidates"])
        outcome_counts[condition] = {"runs": len(condition_runs), "candidate_total": candidate_total,
                                     "confirmed_successes": successes,
                                     "confirmed_negatives": candidate_total - successes}
    coverage = {"complete": completed_pairs == expected_completed and excluded_pairs == expected_excluded,
                "expected_completed_pairs": len(expected_completed),
                "observed_completed_pairs": len(completed_pairs),
                "missing_completed_pairs": sorted(expected_completed - completed_pairs),
                "unexpected_completed_pairs": sorted(completed_pairs - expected_completed),
                "expected_excluded_pairs": sorted(expected_excluded),
                "observed_excluded_pairs": sorted(excluded_pairs)}
    status_counts = dict(collections.Counter(r["status"] for r in runs))
    return {"path": relative(pilot_path), "ledger_sha256": digest(pilot_path / "ledger.jsonl"),
            "plan_snapshot_sha256": digest(pilot_path / "plan.snapshot.json"), "loader_verified": True,
            "run_count": len(runs), "status_counts": status_counts,
            "scenario_condition_coverage": coverage,
            "all_applicable_runs_metric_eligible": all(r["metric_eligible"] for r in runs if r["status"] == "completed"),
            "retrieval_index_snapshot_pinned": bool(knowledge_snapshot and knowledge_snapshot.get("index_file_sha256")),
            "retrieval_index_file_sha256": (knowledge_snapshot.get("index_file_sha256")
                                             if isinstance(knowledge_snapshot, dict) else None),
            "candidate_outcomes_by_condition": outcome_counts,
            "candidate_count": sum(len(r["candidates"]) for r in runs), "incomplete_runs": incomplete,
            "generation_context": assess_context(generation), "analysis_context": assess_context(analysis),
            "generation_prompt_versions": sorted({a["prompt_version"] for a in generation}),
            "analysis_prompt_versions": sorted({a["prompt_version"] for a in analysis}),
            "suggestions_per_call_counts": dict(collections.Counter(a["candidate_suggestions_requested"] for a in generation)),
            "llm_runs": len(orchestration),
            "nonfinal_adaptive_artifacts_excluded_from_integration_gate": nonfinal_adaptive_artifacts,
            "langchain_serial_verified": len(final_llm_attempt_ids) == 24 and len(orchestration) == 24
            and all(o.get("framework") == "langchain-core" and o.get("version") == "1.6.10"
                    and o.get("max_concurrency") == 1 and o.get("external_tracing") is False for o in orchestration),
            "rag_isolation_verified": len(final_llm_attempt_ids) == 24
            and len(retrieval_checks) == 24 and all(retrieval_checks)}


def pilot_completion_gate_passes(pilot):
    return (pilot.get("run_count") == 36
            and pilot.get("status_counts") == {"completed": 33, "excluded": 3}
            and pilot.get("scenario_condition_coverage", {}).get("complete") is True
            and pilot.get("all_applicable_runs_metric_eligible") is True
            and not pilot.get("incomplete_runs"))


def retrieval_index_snapshot_matches(pilot, formal_plan, knowledge):
    snapshot = formal_plan.get("knowledge_snapshot")
    pilot_snapshot = pilot.get("retrieval_index_file_sha256")
    return (pilot.get("retrieval_index_snapshot_pinned") is True
            and isinstance(snapshot, dict)
            and isinstance(pilot_snapshot, dict)
            and pilot_snapshot == snapshot.get("index_file_sha256")
            and snapshot.get("index_file_sha256") == knowledge.get("index_file_sha256")
            and knowledge.get("formal_use_decision") == "approved")


def validate_formal_corpus_decision(decision, knowledge):
    """Bind an explicit researcher decision to the exact corpus and index snapshot."""
    if not decision or decision.get("decision") != "approved-for-formal-use":
        return False
    authority = decision.get("authority", {})
    if (decision.get("schema_version") != "1.0.0"
            or decision.get("scope") != "main-nine-entry-corpus-formal-use-after-u07-gates"
            or authority.get("role") != "researcher"
            or authority.get("basis") != "explicit-user-approval"
            or not authority.get("quote")
            or decision.get("formal_execution_approval") is not False):
        raise ValueError("Formal corpus decision must record explicit researcher approval with the agreed scope.")
    expected = {key: knowledge[key] for key in (
        "corpus_sha256", "source_lock_sha256", "knowledge_base_id", "entry_count", "index_file_sha256")}
    if decision.get("approved_snapshot") != expected:
        approved = decision.get("approved_snapshot", {})
        mismatches = {key: {"approved": approved.get(key), "current": expected[key]}
                      for key in expected if approved.get(key) != expected[key]}
        raise CorpusSnapshotMismatch(mismatches)
    return True


def knowledge_audit():
    corpus, lock = validate_corpus()
    pointer = read_json(ROOT / "knowledge/active-index.local.json")
    manifest_path = ROOT / pointer["manifest_path"]
    manifest = read_json(manifest_path)
    store = ROOT / manifest["store_path"]
    if (manifest["corpus_sha256"] != digest(ROOT / manifest["corpus_path"])
            or manifest["source_lock_sha256"] != digest(ROOT / "knowledge/sources.lock.json")
            or pointer["knowledge_base_id"] != manifest["knowledge_base_id"]):
        raise ValueError("Active index does not match the source corpus and lock.")
    expected = {item["id"]: item for item in prepare_documents(corpus, lock)}
    # SQLite read-only mode avoids modifying the persistent Chroma index or emitting telemetry.
    with sqlite3.connect((store / "chroma.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT e.embedding_id, m.string_value FROM embeddings e "
                                  "JOIN embedding_metadata m ON e.id=m.id WHERE m.key='chroma:document'").fetchall()
        if len(rows) != len(expected) or dict(rows) != {key: item["text"] for key, item in expected.items()}:
            raise ValueError("Chroma documents differ from the validated corpus.")
        metadata = {key: {} for key in expected}
        rows = connection.execute("SELECT e.embedding_id, m.key, m.string_value, m.int_value, "
                                  "m.float_value, m.bool_value FROM embeddings e "
                                  "JOIN embedding_metadata m ON e.id=m.id WHERE m.key!='chroma:document'").fetchall()
        for key, field, *values in rows:
            metadata[key][field] = next(value for value in values if value is not None)
        if metadata != {key: item["metadata"] for key, item in expected.items()}:
            raise ValueError("Chroma metadata differs from the validated corpus.")
    policy, policy_hash = retrieval_policy()
    result = {"knowledge_base_id": pointer["knowledge_base_id"], "entry_count": len(expected),
            "corpus_sha256": manifest["corpus_sha256"], "source_lock_sha256": manifest["source_lock_sha256"],
            "index_file_sha256": {relative(p): digest(p) for p in sorted(store.rglob("*")) if p.is_file()},
            "retrieval_policy": policy, "retrieval_policy_sha256": policy_hash,
            "top_k": 2, "embedding_model": manifest["embedding_model"], "content_integrity_verified": True,
            "review_evidence": "docs/evidence/review-peneliti-2026-10-12.md",
            "review_evidence_sha256": digest(ROOT / "docs/evidence/review-peneliti-2026-10-12.md"),
            "recorded_review_scope": "pilot-only; see docs/corpus-review-2026-10-11.md",
            "formal_use_decision": "pending", "embedded_review_metadata": corpus["curation"]["researcher_review"]}
    if CORPUS_DECISION.is_file():
        decision = read_json(CORPUS_DECISION)
        try:
            approved = validate_formal_corpus_decision(decision, result)
        except CorpusSnapshotMismatch as error:
            result.update(formal_use_decision="snapshot-mismatch",
                          formal_decision_mismatch=error.mismatches,
                          formal_decision_path=relative(CORPUS_DECISION),
                          formal_decision_sha256=digest(CORPUS_DECISION))
        else:
            result.update(formal_use_decision="approved" if approved else "pending",
                          formal_decision_path=relative(CORPUS_DECISION),
                          formal_decision_sha256=digest(CORPUS_DECISION))
    return result


def seclists_audit():
    path = ROOT / "docs/evidence/seclists-selection-plan-2026-10-12.json"
    selection = read_json(path)
    base = ROOT / "results/raw/seclists" / selection["revision"]
    files = []
    for item in selection["files"].values():
        source = base / item["path"]
        if digest(source) != item["sha256"]:
            raise ValueError("Locked SecLists source hash changed.")
        files.append({"path": relative(source), "sha256": digest(source),
                      "selected_source_lines": item["selected_source_lines"]})
    return {"revision": selection["revision"], "selection_rule_id": selection["selection_rule_id"],
            "selection_plan_sha256": digest(path), "files": files, "integrity_verified": True}


def zap_audit():
    result = {}
    for level in ("low", "medium", "high", "impossible"):
        matches = sorted(ZAP.glob(f"*{level}*summary*.json"))
        # The Medium v2 summary corrected attribution in the earlier report.
        path = next((p for p in matches if p.name.endswith("summary-v2.json")), matches[0])
        document = read_json(path)
        for name, filename in document["artifact_names"].items():
            artifact = ZAP / filename if name == "api_evidence" else ROOT / "results/zap" / filename
            if digest(artifact) != document["artifact_sha256"][name]:
                raise ValueError("ZAP evidence hash mismatch: " + filename)
        result[level] = {"summary": relative(path), "summary_sha256": digest(path),
                         "coordinate_coverage": document["coordinate_coverage"],
                         "completed": document["api_scans_completed"] and document["automation_setup_completed"]}
    return result


def ready(gates):
    return REQUIRED_GATE_IDS.issubset(gates) and all(gate["status"] == "passed" for gate in gates.values())


def source_files():
    files = [p for folder in ("dvwa", "schemas", "knowledge", "tests") for p in (ROOT / folder).glob("*")
             if p.is_file() and p.suffix in {".py", ".json", ".yaml", ".ps1", ".md"} and ".local." not in p.name]
    files.extend(ROOT.glob("requirements*.txt"))
    return sorted(set(files))


def prepare(plan_path, runtime_path, output, pilot_path=PILOT):
    pilot_path = resolve_pilot_path(pilot_path)
    output = output.resolve()
    if not output.is_relative_to((ROOT / "results/raw").resolve()):
        raise ValueError("Readiness artifacts must stay under results/raw/.")
    output.mkdir(parents=True, exist_ok=True)
    protocol = load_protocol()
    plan = read_json(plan_path)
    Draft202012Validator(read_json(ROOT / "schemas/local-run-plan.schema.json")).validate(plan)
    if plan["dataset"] != "formal":
        raise ValueError("U07 requires a formal draft plan.")
    if not isinstance(plan.get("knowledge_snapshot"), dict):
        raise ValueError("U07 formal draft must pin the approved Chroma index snapshot.")
    formal_knowledge_snapshot = validate_knowledge_snapshot(plan["knowledge_snapshot"])
    slots = list(ordered_run_slots(protocol, scenario_ids=plan["scenario_ids"],
                                  condition_ids=plan["condition_ids"], replicates=plan["replicates"]))
    applicable = [s for s in slots if s["applicable"]]
    counts = dict(collections.Counter(s["condition_id"] for s in applicable))
    if counts != {"A": 36, "B": 36, "C": 27} or len(applicable) != 99:
        raise ValueError("Formal plan must contain exactly A36/B36/C27.")
    discovery_paths = [plan["discovery_reports"][f"S{i}"][str(r)] for i in range(1, 13) for r in (1, 2, 3)]
    unique_discovery = sorted(set(discovery_paths))
    if len(unique_discovery) != 12 or any(not p.startswith("results/raw/formal-discovery/") for p in unique_discovery):
        raise ValueError("Reserve 12 fresh discovery reports: four levels for each replicate.")
    # Ask the real admission guard; never make a temporary frozen copy to bypass it.
    try:
        validate_plan(plan, protocol)
        admission = "accepted"
    except ValueError as error:
        admission = str(error)
    pilot, knowledge, seclists, zap = (pilot_audit(pilot_path), knowledge_audit(),
                                        seclists_audit(), zap_audit())
    runtime = read_json(runtime_path)
    imported = read_json(REVIEW / "annotations.imported.json")
    audit = read_json(REVIEW_AUDIT)
    annotations = imported["annotations"]
    validator_ready = imported["validator_id"] == "VAL-01" and len(annotations) == 4
    tests_path = output / "tests.log"
    test_summary = (re.search(r"Ran (\d+) tests in ([\d.]+)s\s+OK\s*$",
                              tests_path.read_text(encoding="utf-8", errors="replace"))
                    if tests_path.is_file() else None)
    tests = {"passed": test_summary is not None, "log": relative(tests_path),
             "log_sha256": digest(tests_path) if tests_path.is_file() else None,
             "tests_run": int(test_summary.group(1)) if test_summary else None,
             "command": ".venv/Scripts/python.exe -m unittest discover -s tests -v"}
    context_ok = all(pilot[k]["status"] == "passed_for_recorded_calls"
                     for k in ("generation_context", "analysis_context"))
    server_log = runtime.get("pilot_server_log", {})
    if server_log.get("coverage_verified"):
        log_snapshot = output / "ollama-pilot-server.local.log"
        if not log_snapshot.is_file() or digest(log_snapshot) != server_log["sha256"]:
            shutil.copyfile(server_log["path"], log_snapshot)
        if digest(log_snapshot) != server_log["sha256"]:
            raise ValueError("Ollama pilot server log changed since runtime capture.")
        server_log["snapshot_path"] = relative(log_snapshot)
    context_ok = (context_ok and server_log.get("coverage_verified") is True
                  and server_log.get("positive_truncation_count") == 0
                  and server_log.get("explicit_input_truncation_warnings") == 0)
    runtime_ok = (runtime["pip_check"]["exit_code"] == 0
                  and runtime["python"]["startup"]["exit_code"] == 0
                  and not runtime["python"]["startup"]["stderr"]
                  and runtime["docker_version"]["exit_code"] == 0
                  and runtime["lab_containers"]["exit_code"] == 0
                  and all(i["inspection"]["exit_code"] == 0 for i in runtime["docker_images"].values())
                  and runtime["zap_bundled_addons"]["exit_code"] == 0
                  and "dvwa-tunnel-1" not in runtime["lab_containers"]["stdout"]
                  and "dvwa-gateway-1" not in runtime["lab_containers"]["stdout"]
                  and {m["name"] for m in runtime["models"]} == {"qwen2.5:7b", "nomic-embed-text:latest"}
                  and runtime["dvwa_reachability"]["http_status"] == 200
                  and runtime["dvwa_reachability"]["login_page_marker_present"])
    gates = {
        "pilot-all-techniques-and-levels-passed": {"status": "passed" if pilot_completion_gate_passes(pilot) else "pending",
            "evidence": pilot["path"], "reason": ("36 scheduled slots checked: 33 applicable completed, three planned C/Impossible exclusions, exact A/B and C scenario coverage, all runs metric eligible, no budget mismatches."
                if pilot_completion_gate_passes(pilot) else
                "Pilot must have the exact 36-slot matrix, 33 applicable completed runs, three planned exclusions, metric eligibility and no candidate-budget mismatches.")},
        "researcher-corpus-decision-recorded": {
            "status": "passed" if knowledge["formal_use_decision"] == "approved" else "pending",
            "evidence": knowledge.get("formal_decision_path", knowledge["review_evidence"]),
            "reason": ("Explicit researcher approval matches the current nine-entry corpus and index; other U07 gates remain applicable."
                       if knowledge["formal_use_decision"] == "approved" else
                       "The approval receipt exists, but current Chroma index file hashes differ from its approved snapshot. Restore the verified approved index or record a new researcher decision before formal use.")},
        "runtime-manifest-frozen": {"status": "pending", "evidence": relative(output / "manifest.json"),
            "reason": "Candidate runtime and source snapshot captured; release depends on the other formal gates."},
        "seclists-version-and-selection-frozen": {"status": "passed", "evidence": "docs/evidence/seclists-selection-plan-2026-10-12.json",
            "reason": "Pinned revision, original source files, line selections and transformations verified."},
        "validator-protocol-ready": {"status": "passed" if validator_ready else "pending",
            "evidence": relative(REVIEW / "annotations.imported.json"),
            "reason": "VAL-01 qualifications recorded; four blind pilot annotations imported. Formal annotations follow F01."},
        "local-methodology-recorded": {"status": "passed", "evidence": "docs/metodologi-lokal-2026-10-14.md",
            "reason": "Local serial pipeline, retrieval for generation only, and fixed evaluation policies recorded."},
        "local-langchain-integration-verified": {"status": "passed" if pilot["langchain_serial_verified"] and pilot["rag_isolation_verified"] else "pending",
            "evidence": pilot["path"], "reason": "24 A/B attempts cover S1-S12; serial LangChain and RAG isolation verified separately from generation budget."},
        "retrieval-index-snapshot-pinned": {"status": "passed" if retrieval_index_snapshot_matches(pilot, plan, knowledge) else "pending",
            "evidence": relative(plan_path), "reason": ("Pilot and formal plan pin the exact approved index file hashes."
                if retrieval_index_snapshot_matches(pilot, plan, knowledge) else
                "The formal draft pins the approved index bytes, but the selected pilot does not pin that same snapshot. Complete a matching pinned pilot before formal use.")},
        "context-and-runtime-preflight": {"status": "passed" if runtime_ok and context_ok else "pending",
            "evidence": relative(runtime_path), "reason": (
                "Local metadata, clean interpreter, dependency consistency, closed-lab state and observed pilot token budgets checked."
                if runtime_ok and context_ok else
                "The local lab is closed and runtime metadata is archived, but no Ollama server log covering both pilot boundary hours was found; retain that log with no truncation warnings before formal use."
                if runtime_ok else
                "Runtime preflight is pending; inspect the captured container, dependency, model, Docker, and DVWA metadata before formal use.")},
        "active-zap-coordinate-coverage": {"status": "passed" if all(z["completed"] and z["coordinate_coverage"]["complete"] for z in zap.values()) else "pending",
            "evidence": relative(ZAP), "reason": "Scanner-tagged coordinates and raw artifact hashes checked for four levels."},
        "offline-contract-checks": {"status": "passed" if tests["passed"] else "pending",
            "evidence": tests["log"], "reason": "Complete offline suite, including U07 admission and token-budget regression checks."},
    }
    lock = output / "requirements-formal-2026-10-17.lock.txt"
    lock.write_text("# U07 installed-version candidate snapshot; freeze is pending.\n# Python "
                    + runtime["python"]["version"] + "; this is a version lock, without wheel hashes.\n"
                    + "".join(f"{p['name']}=={p['version']}\n" for p in runtime["packages"]), encoding="utf-8")
    hashes = {relative(p): digest(p) for p in source_files()}
    tree_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    base_revision = command(["git", "rev-parse", "HEAD"])["stdout"]
    previous_hashes = read_json(pilot_path / "plan.snapshot.json")["artifact_sha256"]
    pilot_source_differences = {name: {"pilot_sha256": expected, "current_sha256": digest(ROOT / name)}
                                for name, expected in previous_hashes.items() if digest(ROOT / name) != expected}
    write_json(output / "source-file-sha256.json", hashes)
    archive = output / "source-index-evidence.zip"
    archive_paths = set(source_files())
    archive_paths.update(ROOT / path for path in knowledge["index_file_sha256"])
    archive_paths.add(ROOT / "knowledge/active-index.local.json")
    if APPROVED_INDEX_ARCHIVE.is_file():
        archive_paths.add(APPROVED_INDEX_ARCHIVE)
    archive_paths.update(p for p in pilot_path.rglob("*") if p.is_file())
    archive_paths.update(p for p in REVIEW.rglob("*") if p.is_file())
    archive_paths.update(ROOT / f["path"] for f in seclists["files"])
    archive_paths.update(p for p in (ROOT / "data/raw/knowledge-sources").rglob("*") if p.is_file())
    archive_paths.update(p for p in (ROOT / "docs").rglob("*") if p.is_file())
    archive_paths.update(p for p in ZAP.glob("*.json"))
    for item in zap.values():
        summary = read_json(ROOT / item["summary"])
        archive_paths.update(ZAP / filename if kind == "api_evidence" else ROOT / "results/zap" / filename
                             for kind, filename in summary["artifact_names"].items())
    archive_paths.update((runtime_path, lock, REVIEW_AUDIT))
    if server_log.get("snapshot_path"):
        archive_paths.add(ROOT / server_log["snapshot_path"])
    archive_paths.add(output / "source-file-sha256.json")
    archive_paths.update(ROOT / name for name in ("README.md", ".gitignore", ".gitattributes"))
    if tests_path.is_file():
        archive_paths.add(tests_path)
    # This archive is private local evidence. It includes the validator's private mapping.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as backup:
        for p in sorted(archive_paths):
            backup.write(p, relative(p))
    with zipfile.ZipFile(archive) as backup:
        if backup.testzip() is not None:
            raise ValueError("Readiness snapshot archive failed CRC validation.")
        for name, expected in {**hashes, **knowledge["index_file_sha256"]}.items():
            if hashlib.sha256(backup.read(name)).hexdigest() != expected:
                raise ValueError("Archived source/index differs from the captured file hash: " + name)
    backup_directory = ROOT / "results/raw/backups" / f"{plan['experiment_id']}-{output.name}"
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / "u07-source-index-evidence.zip"
    shutil.copyfile(archive, backup_path)
    if digest(archive) != digest(backup_path):
        raise ValueError("Local backup copy hash mismatch.")
    with (output / "formal-schedule.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["planned_slot_index", "planned_execution_index", "replicate", "seed", "scenario_id", "condition_id", "applicable", "candidate_slots"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for slot in slots:
            writer.writerow({key: slot.get(key) for key in fields[:3] + ["scenario_id", "condition_id", "applicable"]}
                            | {"seed": protocol["replicate_seeds"][slot["replicate"] - 1],
                               "candidate_slots": protocol["generation"]["candidate_budget"] if slot["applicable"] else 0})
    manifest = {"schema_version": "1.0.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "U07-formal-readiness-candidate", "ready_for_formal": ready(gates), "protocol_frozen": False,
        "formal_evaluation_executed": False, "base_git_revision": base_revision,
        "working_tree_status": command(["git", "status", "--porcelain=v1"])["stdout"],
        "source_tree_sha256": tree_hash, "source_hashes": relative(output / "source-file-sha256.json"),
        "differences_from_pilot_snapshot": pilot_source_differences,
        "source_archive": {"path": relative(archive), "sha256": digest(archive),
                           "crc_verified": True, "backup_copy": relative(backup_path),
                           "backup_copy_sha256": digest(backup_path),
                           "same_disk_snapshot": True, "sharing": "private-local-only"},
        "protocol": {"path": "dvwa/local_experiment_protocol.json", "sha256": digest(ROOT / "dvwa/local_experiment_protocol.json"),
                     "status": protocol["status"], "generation": protocol["generation"], "active_markers_unchanged": True},
        "formal_plan": {"path": relative(plan_path), "sha256": digest(plan_path), "schema_valid": True,
                        "applicable_runs": 99, "by_condition": counts, "not_applicable_slots": len(slots) - 99,
                        "candidate_slots": len(applicable) * protocol["generation"]["candidate_budget"],
                        "runner_admission": admission, "fresh_discovery_paths": unique_discovery,
                        "fresh_discovery_present": sum((ROOT / p).is_file() for p in unique_discovery),
                        "discovery_refresh_stage": "F01 preparation, four fresh levels per replicate; never reuse pilot reports"},
        "runtime": runtime, "pilot": pilot, "knowledge": knowledge, "seclists": seclists, "zap": zap,
        "formal_knowledge_snapshot": {"validated": True,
            "review_decision_sha256": plan["knowledge_snapshot"]["review_decision_sha256"],
            "source_lock_sha256": plan["knowledge_snapshot"]["source_lock_sha256"],
            "index_file_sha256": formal_knowledge_snapshot["index_file_sha256"]},
        "offline_checks": tests,
        "validator": {"validator_id": imported["validator_id"], "pilot_annotations": len(annotations),
                      "annotations_sha256": digest(REVIEW / "annotations.imported.json"),
                      "review_audit_path": relative(REVIEW_AUDIT),
                      "review_audit_sha256": digest(REVIEW_AUDIT),
                      "psr_eligible": audit["psr"]["eligible"], "fpr_eligible": audit["fpr"]["eligible"]},
        "gates": gates,
        "requirements_lock": {"path": relative(lock), "sha256": digest(lock), "freeze_status": "candidate"},
        "timing_estimate": {"pilot_wall_seconds": 14899.33, "pilot_applicable_runs": 33,
                            "three_replicate_linear_reference_hours": round(14899.33 * 3 / 3600, 2),
                            "limitations": "Linear reference from the complete U07 v17 pilot only; formal discovery, database resets, recovery, laptop load, and human annotation time may change the duration."}}
    write_json(output / "manifest.json", manifest)
    # The inventory lives outside the ZIP so the manifest can pin the archive
    # without creating a circular archive/manifest hash dependency.
    backup_inventory = {"scope": "private-U07-candidate-backup", "same_disk": True, "files": {}}
    for path in (output / "manifest.json", output / "formal-schedule.csv", runtime_path, lock):
        copy = backup_directory / path.name
        shutil.copyfile(path, copy)
        if digest(path) != digest(copy):
            raise ValueError("Backup metadata hash mismatch.")
        backup_inventory["files"][relative(copy)] = digest(copy)
    backup_inventory["files"][relative(backup_path)] = digest(backup_path)
    write_json(backup_directory / "inventory.json", backup_inventory)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-runtime", type=Path, help="Read local service metadata and write a private runtime JSON.")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--pilot", type=Path, default=PILOT,
                        help="Pilot evidence directory under results/raw/pilot/; defaults to the audited v17 pilot.")
    args = parser.parse_args()
    if args.capture_runtime:
        output = args.capture_runtime.resolve()
        if not output.is_relative_to((ROOT / "results/raw").resolve()):
            parser.error("Runtime JSON must stay under results/raw/.")
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, capture_runtime(args.pilot))
        print(json.dumps({"runtime": relative(output), "captured": True}))
        return
    if not all((args.runtime, args.plan, args.output_dir)):
        parser.error("Provide --runtime, --plan and --output-dir, or --capture-runtime.")
    result = prepare(args.plan.resolve(), args.runtime.resolve(), args.output_dir, args.pilot)
    print(json.dumps({"ready_for_formal": result["ready_for_formal"], "protocol_frozen": False,
                      "applicable_runs": result["formal_plan"]["applicable_runs"],
                      "pending_gates": [key for key, value in result["gates"].items() if value["status"] != "passed"]}, indent=2))


if __name__ == "__main__":
    main()
