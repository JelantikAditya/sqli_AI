"""Freeze knowledge/cases, freeze semantic retrieval, then run paired analysis-only RAG."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import analysis_rag_v4 as rag
import hybrid_validation_v3 as previous

ROOT, pilot, gate = previous.ROOT, previous.pilot, previous.gate
EXPERIMENT_ID = "analysis-rag-ab-v4-20261019"


def new_cases():
    rng = random.Random(2026101904)
    catalog = {s["scenario_id"]: s for s in pilot.load_catalog()["scenarios"]}
    definitions = []
    for sid in ("S1", "S2", "S3"):
        definitions.extend([(sid, "positive", (1, 1, 1), (1, 2, 3), "positive"),
                            (sid, "negative", (0, 0, 0), (1, 2, 3), "negative"),
                            (sid, "mixed-one", (0, 1, 0), (1, 2, 3), "inconclusive"),
                            (sid, "mixed-two", (1, 0, 1), (1, 2, 3), "inconclusive"),
                            (sid, "incomplete", (1, 1), (2, 3) if sid == "S2" else (1, 2), "inconclusive")])
    definitions.extend([("S3", "below-threshold", (0, 0, 0), (1, 2, 3), "negative"),
                        ("S3", "unmatched-control", (0, 0, 0), (1, 2, 3), "negative"),
                        ("S2", "reversed-pair", (0, 0, 0), (1, 2, 3), "negative"),
                        ("S3", "invalid-baseline", (0, 0, 0), (1, 2, 3), None)])
    cases, labels = [], []
    for index, (sid, name, signals, trials, expected) in enumerate(definitions, 1):
        scenario, observations = catalog[sid], []

        def observe(trial, role, *, markers=None, diagnostics=None, status=200, elapsed=None):
            number = len(observations) + 1
            observations.append({"observation_id": f"obs-{number:03d}", "trial": trial, "role": role,
                                 "http_status": status, "elapsed_ms": round(rng.uniform(8, 27), 2) if elapsed is None else elapsed,
                                 "response_sha256": hashlib.sha256(f"v4-{index}-{number}-{rng.getrandbits(128)}".encode()).hexdigest(),
                                 "diagnostics": diagnostics or [], "content_markers": markers or []})

        for trial, signal in zip(trials, signals):
            observe(trial, "baseline", markers=["benign_record"] if sid == "S1" else ["user_id_exists"])
            if sid == "S1":
                observe(trial, "candidate", diagnostics=["mysql_unknown_column"] if signal else [], status=500)
            elif sid == "S2":
                reverse = name == "reversed-pair" and not signal
                observe(trial, "true_condition", markers=["user_id_exists"] if signal else ["user_id_missing"],
                        status=200 if signal else 404)
                observe(trial, "false_condition", markers=["user_id_exists"] if reverse else ["user_id_missing"],
                        status=200 if reverse else 404)
            else:
                control = round(rng.uniform(75, 125), 2)
                delta = rng.randint(1650, 2450) if signal else -5
                if name == "below-threshold":
                    delta = 1499.97
                elif name == "unmatched-control":
                    delta = 2300
                missing = trial != 2 and name not in ("below-threshold", "unmatched-control")
                markers, status = (["user_id_missing"], 404) if missing else (["user_id_exists"], 200)
                observe(trial, "candidate", markers=markers, status=status, elapsed=round(control + delta, 2))
                observe(trial, "no_delay_control", markers=["user_id_missing"] if name == "unmatched-control" else markers,
                        status=404 if name == "unmatched-control" else status, elapsed=control)
        document = {"schema_version": "1.0.0", "technique": scenario["sqli_type"],
                    "injection_point": {k: scenario[k] for k in ("method", "input_path", "result_path", "parameter")},
                    "runtime_status": "valid" if expected is not None else "invalid", "baseline_valid": expected is not None,
                    "time_threshold_ms": 1500, "observations": observations}
        rag.base.frozen.validate_input(document)
        case_id = f"rag-{index:03d}"
        context = {"experiment_id": EXPERIMENT_ID, "run_id": case_id, "attempt_id": "paired-1",
                   "candidate_id": "candidate-001", "scenario_id": sid, "replicate": 1,
                   "condition_id": "A", "source": "LLM", "rag_mode": "off"}
        cases.append({"case_id": case_id, "input": document, "context": context})
        labels.append({"case_id": case_id, "diagnostic_name": name, "expected_claim": expected,
                       "expected_trials": {str(t): "positive" if s else "negative" for t, s in zip(trials, signals)}})
    return cases, labels


def history_inventory():
    inventory = previous.history_inventory()
    folder = ROOT / "results/processed/response-analysis-hybrid-v3-20261019"
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    inventory.update({f"{provenance['source_directory']}/{name}": value for name, value in provenance["local_source_sha256"].items()})
    pilot.require(all(pilot.digest(ROOT / name) == value for name, value in inventory.items()), "A historical development artifact changed.")
    return inventory


def assert_pins(output, manifest):
    for key in ("source_sha256", "history_sha256"):
        pilot.require(all(pilot.digest(ROOT / name) == value for name, value in manifest[key].items()), "Pinned source/history changed.")
    pilot.require(all(pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Frozen artifact changed.")
    pilot.check_protected_sources()


def prepare(output):
    pilot.require(not output.exists(), "Use a new v4 pilot directory.")
    cases, labels = new_cases()
    pilot.require(Counter(l["expected_claim"] for l in labels) == Counter({"positive": 3, "negative": 6, "inconclusive": 9, None: 1}),
                  "Predeclared fixture counts changed.")
    corpus = rag.project_corpus()
    queries = sorted({rag.query_for(c["input"]) for c in cases})
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("inputs.json", cases), ("evaluation.private.json", labels), ("analysis-corpus.json", corpus), ("queries.json", queries)):
        pilot.write_json(output / name, value)
    sources = [Path(__file__), Path(rag.__file__), Path(rag.base.__file__), Path(rag.base.v1.__file__), Path(gate.__file__),
               Path(pilot.__file__), Path(previous.__file__), ROOT / "development/test_analysis_rag_v4.py",
               ROOT / "development/audit_analysis_rag_v4.py", ROOT / "dvwa/knowledge_corpus.py", ROOT / "dvwa/rag_pipeline.py",
               ROOT / "dvwa/analyze_response.py", ROOT / "dvwa/langchain_runtime.py", ROOT / "dvwa/confirmation_policy.py",
               ROOT / "dvwa/run_decision_policy.py", ROOT / "dvwa/experiment_scenarios.json", ROOT / "knowledge/sqli-entries.json",
               ROOT / "knowledge/sources.lock.json", ROOT / "knowledge/NOTICE.md", ROOT / "schemas/sqli-knowledge-corpus.schema.json",
               *[ROOT / "schemas" / name for name in ("qwen-analysis-input.schema.json", "qwen-analysis-output.schema.json", "analysis-ledger.schema.json")]]
    lock = json.loads((ROOT / "knowledge/sources.lock.json").read_text(encoding="utf-8"))
    sources.extend(ROOT / f["snapshot_path"] for s in lock["sources"] for f in s["files"])
    pilot.write_json(output / "design-manifest.json", {
        "scope": "paired-synthetic-analysis-rag-pilot-not-formal-not-independent-holdout", "experiment_id": EXPERIMENT_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model": rag.base.MODEL,
        "expected_model_digest": json.loads((previous.V2_DATA / "runtime.json").read_text())["digest"],
        "options": {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 768},
        "conditions": {"A": "same-base-instructions-no-reference-context", "B": "same-base-instructions-two-semantically-retrieved-references"},
        "new_cases": len(cases), "valid_cases": 18, "planned_model_calls": 36, "planned_runtime_invalid_skips": 2,
        "embedding_model": rag.EMBEDDING_MODEL, "retrieval_policy": rag.POLICY, "unique_queries": len(queries),
        "retrieval_evaluation": "source-integrity-technique-match-and-separate-context-review; no-independent-semantic-gold",
        "raw_claims_primary": True, "verifier_v3_secondary": True, "dvwa_requests": 0, "no_automatic_retry": True,
        "no_tuning_after_first_inference": True, "one_seed_one_pass": True, "order": "alternate-first-condition-by-case",
        "empirical_criteria": ["B-verdict-matches-greater-than-A", "B-false-positive-count-less-than-A",
                               "B-correct-positive-at-least-A", "B-negative-binary-coverage-at-least-A",
                               "B-trial-accuracy-at-least-A", "no-analysis-errors"],
        "formal_promotion": False, "formal_fpr_recomputed": False, "psr_recomputed": False,
        "protected_source_count": pilot.check_protected_sources(), "history_sha256": history_inventory(),
        "source_sha256": {p.resolve().relative_to(ROOT).as_posix(): pilot.digest(p) for p in sources},
        "artifact_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
    })
    print(json.dumps({"status": "design-frozen-before-embeddings", "cases": 19, "model_calls": 36, "queries": len(queries)}), flush=True)


def model_inventory():
    with build_opener(ProxyHandler({})).open(pilot.local_ollama_url() + "/api/tags", timeout=5) as response:
        return json.load(response)["models"]


def retrieve_and_freeze(output):
    design = json.loads((output / "design-manifest.json").read_text(encoding="utf-8"))
    assert_pins(output, design)
    pilot.require(not (output / "manifest.json").exists() and not (output / "retrieval-start.json").exists(), "Retrieval already started; no overwrite/retry.")
    models = model_inventory()
    qwen = next((m for m in models if m["name"] == rag.base.MODEL), None)
    embedder = next((m for m in models if m["name"].split(":")[0] == rag.EMBEDDING_MODEL), None)
    pilot.require(qwen is not None and qwen["digest"] == design["expected_model_digest"] and embedder is not None, "Pinned Qwen/installed embedder unavailable.")
    pilot.write_json(output / "retrieval-start.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                                                     "embedding_model": embedder["name"], "embedding_digest": embedder["digest"]})
    corpus = json.loads((output / "analysis-corpus.json").read_text(encoding="utf-8"))
    queries = json.loads((output / "queries.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    from rag_pipeline import embed_texts
    documents = embed_texts(embedder["name"], [c["text"] for c in corpus["chunks"]], batch_size=16, task="document")
    vectors = embed_texts(embedder["name"], queries, batch_size=16, task="query")
    receipts = rag.retrieve_from_vectors(corpus, documents, queries, vectors)
    pilot.write_json(output / "embedding-snapshot.json", {"model": embedder["name"], "digest": embedder["digest"],
                                                         "document_vectors": documents, "query_vectors": vectors})
    pilot.write_json(output / "retrieval.json", receipts)
    cases = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
    schedule = []
    for index, case in enumerate(cases):
        receipt = receipts[hashlib.sha256(rag.query_for(case["input"]).encode()).hexdigest()]
        for condition in ("A", "B") if index % 2 == 0 else ("B", "A"):
            schedule.append({"case_id": case["case_id"], "condition": condition,
                             "prepared": rag.prepared_request(case["input"], condition, receipt if condition == "B" else None)})
    pilot.write_json(output / "prepared-requests.json", schedule)
    pilot.write_json(output / "runtime.json", {"model": rag.base.MODEL, "digest": qwen["digest"], "details": qwen.get("details"),
                                               "embedding_model": embedder["name"], "embedding_digest": embedder["digest"],
                                               "chromadb_version": version("chromadb"), "retrieval_seconds": time.monotonic() - started})
    pilot.write_json(output / "manifest.json", {**design, "design_manifest_sha256": pilot.digest(output / "design-manifest.json"),
                                               "embedding_model_digest": embedder["digest"], "chromadb_version": version("chromadb"),
                                               "artifact_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"status": "retrieval-and-all-requests-frozen", "selected": {json.loads(r["query"])["technique"]:
                        [c["entry_id"] for c in r["chunks"]] for r in receipts.values()}, "planned_model_calls": 36}), flush=True)


def metrics(rows, layer="raw_qwen_v2"):
    report = previous.metrics(rows, layer)
    report["layer"] = "raw_qwen_v4" if layer == "raw_qwen_v2" else "secondary_combined_v3"
    trial_correct = trial_total = reason_consistent = 0
    warnings = Counter()
    for row in rows:
        if row["expected_claim"] is None:
            continue
        record = row["hybrid"]["llm_record"]
        output = record["model_output"] or {}
        assessments = output.get("trial_assessments", [])
        claims = {str(a["trial"]): a["outcome"] for a in assessments}
        duplicates = {str(a["trial"]) for a in assessments if sum(b["trial"] == a["trial"] for b in assessments) > 1}
        trial_total += len(row["expected_trials"])
        trial_correct += sum(claims.get(t) == value and t not in duplicates for t, value in row["expected_trials"].items())
        if output:
            reason_consistent += output["reason_code"] == gate.REASONS[record["evidence"]["technique"]].get(output["decision"], "insufficient_evidence")
        warnings.update(record["analysis_warnings"])
        warnings.update(record["audit"]["provenance"].get("development_contract_warnings", []))
    report.update(raw_trial_assessments_correct=trial_correct, raw_trial_total=trial_total,
                  raw_reason_code_consistent=reason_consistent, raw_warning_counts=dict(warnings),
                  analysis_errors=sum(r["hybrid"]["llm_record"]["analysis_status"] == "analysis_error" for r in rows),
                  total_model_seconds=sum(r["elapsed_seconds"] for r in rows))
    return report


def summarize(output, wall_seconds):
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    pilot.require(len(rows) == 38, "Incomplete paired evaluation; keep partial outputs.")
    primary = {condition: metrics([r for r in rows if r["condition"] == condition]) for condition in ("A", "B")}
    secondary = {condition: metrics([r for r in rows if r["condition"] == condition], "combined") for condition in ("A", "B")}
    a, b = primary["A"], primary["B"]
    criteria = {"B_verdicts_greater_than_A": b["verdict_matches"] > a["verdict_matches"],
                "B_false_positives_less_than_A": b["false_positive_on_negative_fixtures"] < a["false_positive_on_negative_fixtures"],
                "B_correct_positive_at_least_A": b["correct_positive"] >= a["correct_positive"],
                "B_negative_coverage_at_least_A": b["negative_fixture_binary_coverage_count"] >= a["negative_fixture_binary_coverage_count"],
                "B_raw_trial_accuracy_at_least_A": b["raw_trial_assessments_correct"] >= a["raw_trial_assessments_correct"],
                "no_analysis_errors": a["analysis_errors"] == b["analysis_errors"] == 0}
    pairs = []
    for case_id in dict.fromkeys(r["case_id"] for r in rows):
        pair = {r["condition"]: r for r in rows if r["case_id"] == case_id}
        pairs.append({"case_id": case_id, "expected_claim": pair["A"]["expected_claim"],
                      "A": previous.decision(pair["A"], "raw_qwen_v2"), "B": previous.decision(pair["B"], "raw_qwen_v2")})
    pilot.write_json(output / "summary.json", {
        "scope": "paired-synthetic-analysis-rag-pilot-not-formal-not-independent-holdout", "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": pilot.digest(output / "manifest.json"), "primary_raw": primary, "secondary_gate": secondary,
        "empirical_criteria": criteria, "all_empirical_criteria_met": all(criteria.values()),
        "paired_A_correct_B_wrong": sum(p["expected_claim"] is not None and p["A"] == p["expected_claim"] != p["B"] for p in pairs),
        "paired_A_wrong_B_correct": sum(p["expected_claim"] is not None and p["B"] == p["expected_claim"] != p["A"] for p in pairs),
        "records": len(rows), "model_calls": sum("raw_model_content" in r["hybrid"]["llm_record"]["audit"]["provenance"] for r in rows),
        "total_wall_seconds": wall_seconds, "formal_fpr_recomputed": False, "psr_recomputed": False,
        "raw_model_claims_replaced": False, "formal_promotion": False, "dvwa_requests": 0,
        "protected_sources_unchanged": pilot.check_protected_sources(), "history_artifacts_unchanged": len(history_inventory()), "pairs": pairs,
    })
    print(json.dumps({"status": "completed", "primary_raw": primary, "criteria": criteria}), flush=True)


def run(output):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert_pins(output, manifest)
    pilot.require(not (output / "replay.jsonl").exists(), "Already started; no overwrite or automatic retry.")
    actual = next((m for m in model_inventory() if m["name"] == rag.base.MODEL), None)
    pilot.require(actual is not None and actual["digest"] == manifest["expected_model_digest"], "Qwen digest changed.")
    cases = {c["case_id"]: c for c in json.loads((output / "inputs.json").read_text(encoding="utf-8"))}
    labels = {l["case_id"]: l for l in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    receipts = json.loads((output / "retrieval.json").read_text(encoding="utf-8"))
    schedule = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    with (output / "replay.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for step in schedule:
            case, condition = cases[step["case_id"]], step["condition"]
            context = {**case["context"], "condition_id": condition, "rag_mode": "off" if condition == "A" else "on"}
            receipt = receipts[hashlib.sha256(rag.query_for(case["input"]).encode()).hexdigest()] if condition == "B" else None
            print(json.dumps({"case_id": case["case_id"], "condition": condition, "status": "starting"}), flush=True)
            call_started = time.monotonic()
            record = rag.analyze(copy.deepcopy(case["input"]), context, condition, receipt, step["prepared"])
            label = labels[case["case_id"]]
            row = {"case_id": case["case_id"], "condition": condition, "expected_claim": label["expected_claim"],
                   "expected_trials": label["expected_trials"], "hybrid": gate.combine(record), "elapsed_seconds": time.monotonic() - call_started}
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            print(json.dumps({"case_id": case["case_id"], "condition": condition, "expected": label["expected_claim"],
                              "raw": record["system_claim"], "seconds": round(row["elapsed_seconds"], 2)}), flush=True)
            if record["audit"]["provenance"].get("analysis_error") == "model-service-unavailable":
                raise RuntimeError("Local model service unavailable; partial results retained without retry.")
    summarize(output, time.monotonic() - started)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepare", "retrieve", "run"), default="prepare")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Use development result directory.")
    {"prepare": prepare, "retrieve": retrieve_and_freeze, "run": run}[args.phase](destination)
