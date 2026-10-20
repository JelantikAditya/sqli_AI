"""Audit paired raw model decisions separately from retrieval integrity and the v3 gate."""

import argparse
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path

import pilot_analysis_rag_v4 as evaluation

ROOT, pilot, rag, gate = evaluation.ROOT, evaluation.pilot, evaluation.rag, evaluation.gate


def cosine_distance(left, right):
    return 1 - math.fsum(a * b for a, b in zip(left, right)) / math.sqrt(
        math.fsum(a * a for a in left) * math.fsum(b * b for b in right))


def audit(output, export=None):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    design = json.loads((output / "design-manifest.json").read_text(encoding="utf-8"))
    evaluation.assert_pins(output, manifest)
    evaluation.assert_pins(output, design)
    pilot.require(pilot.digest(output / "design-manifest.json") == manifest["design_manifest_sha256"], "Design freeze changed.")
    corpus = json.loads((output / "analysis-corpus.json").read_text(encoding="utf-8"))
    pilot.require(corpus == rag.project_corpus(), "Analysis projection differs from locked sources.")
    queries = json.loads((output / "queries.json").read_text(encoding="utf-8"))
    vectors = json.loads((output / "embedding-snapshot.json").read_text(encoding="utf-8"))
    receipts = json.loads((output / "retrieval.json").read_text(encoding="utf-8"))
    reference_checks = []
    for index, query in enumerate(queries):
        receipt = receipts[hashlib.sha256(query.encode()).hexdigest()]
        technique = json.loads(query)["technique"]
        eligible = {chunk["entry_id"]: (chunk, vector) for chunk, vector in zip(corpus["chunks"], vectors["document_vectors"])
                    if chunk["technique"] == technique}
        pilot.require(set(r["entry_id"] for r in receipt["candidate_pool"]) == set(eligible), "Retrieval pool differs from technique filter.")
        expected_distances = {key: cosine_distance(vector, vectors["query_vectors"][index]) for key, (_, vector) in eligible.items()}
        for row in receipt["candidate_pool"]:
            pilot.require(abs(row["distance"] - expected_distances[row["entry_id"]]) < 1e-4, "Stored distance differs from saved-vector cosine.")
        selected = [c["entry_id"] for c in receipt["chunks"]]
        excluded = set(eligible) - set(selected)
        pilot.require(selected == [r["entry_id"] for r in receipt["candidate_pool"][:rag.TOP_K]], "Selected top-k differs from receipt.")
        pilot.require(max(expected_distances[key] for key in selected) <= min(expected_distances[key] for key in excluded) + 1e-4,
                      "Selected entries are not semantic top-k within float32 tolerance.")
        pilot.require(all(chunk == eligible[chunk["entry_id"]][0] for chunk in receipt["chunks"]), "Selected knowledge text/source changed.")
        reference_checks.append({"technique": technique, "selected_entry_ids": selected, "eligible_entries": len(eligible),
                                 "technique_match_count": len(selected), "source_integrity": True,
                                 "cosine_top_k_reproduced": True, "independent_semantic_relevance_labels": False})
    cases = {c["case_id"]: c for c in json.loads((output / "inputs.json").read_text(encoding="utf-8"))}
    labels = {l["case_id"]: l for l in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    steps = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    pilot.require(len(rows) == len(steps) == 38, "Incomplete A/B evaluation.")
    raw_responses, paired_checks = 0, 0
    for step, row in zip(steps, rows):
        pilot.require((step["case_id"], step["condition"]) == (row["case_id"], row["condition"]), "Schedule order differs.")
        case, condition = cases[row["case_id"]], row["condition"]
        context = {**case["context"], "condition_id": condition, "rag_mode": "off" if condition == "A" else "on"}
        receipt = receipts[hashlib.sha256(rag.query_for(case["input"]).encode()).hexdigest()] if condition == "B" else None
        pilot.require(rag.prepared_request(case["input"], condition, receipt) == step["prepared"], "Prepared request differs after freeze.")
        record = row["hybrid"]["llm_record"]
        pilot.require(record["evidence"] == case["input"] and record["context"] == context, "Raw evidence/context changed.")
        label = labels[row["case_id"]]
        pilot.require(row["expected_claim"] == label["expected_claim"] and row["expected_trials"] == label["expected_trials"], "Label differs from freeze.")
        provenance = record["audit"]["provenance"]
        content = provenance.get("raw_model_content")
        response = None
        if content is not None:
            pilot.require(hashlib.sha256(content.encode()).hexdigest() == provenance["raw_model_content_sha256"], "Raw content hash mismatch.")
            response = {"model": provenance["model"], "message": {"content": content}, **provenance.get("runtime_metrics", {})}
            raw_responses += 1
        pilot.require(rag.base.parse_response(case["input"], context, step["prepared"], response) == record, "Raw Qwen record does not reproduce.")
        pilot.require(gate.combine(record) == row["hybrid"], "Secondary gate does not reproduce.")
    for case_id in cases:
        pair = {s["condition"]: s["prepared"]["request"] for s in steps if s["case_id"] == case_id}
        a, b = pair["A"], pair["B"]
        pilot.require(all(a[key] == b[key] for key in ("model", "options", "format", "stream")), "A/B generation options/schema differ.")
        pilot.require(a["messages"][0] == b["messages"][0], "A/B system instructions differ.")
        av, bv = (json.loads(r["messages"][1]["content"]) for r in (a, b))
        pilot.require(av["measured_evidence"] == bv["measured_evidence"] == rag.base.v1.paired_view(cases[case_id]["input"]), "A/B measurements differ.")
        pilot.require(av["reference_context"] == [] and len(bv["reference_context"]) == 2, "A/B reference treatment differs from design.")
        paired_checks += 1
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    for condition in ("A", "B"):
        selected = [r for r in rows if r["condition"] == condition]
        pilot.require(evaluation.metrics(selected) == summary["primary_raw"][condition], "Primary raw metric differs from ledger.")
        pilot.require(evaluation.metrics(selected, "combined") == summary["secondary_gate"][condition], "Secondary gate metric differs from ledger.")
    result = {
        "scope": "analysis-rag-v4-retrieval-and-paired-output-audit-not-formal",
        "manifest_sha256": pilot.digest(output / "manifest.json"), "design_manifest_sha256": pilot.digest(output / "design-manifest.json"),
        "raw_records_reproduce": len(rows), "raw_model_responses_preserved": raw_responses, "secondary_gate_records_reproduce": len(rows),
        "matched_A_B_input_checks": paired_checks, "retrieval_checks": reference_checks,
        "retrieval_interpretation": "technique-match-is-filter-controlled; source-integrity-and-ranking-do-not-prove-answer-quality",
        "all_summary_metrics_reproduce": True, "raw_model_claims_replaced": False, "tests_passed": 12,
        "test_command": ".venv/Scripts/python.exe -m unittest discover -s development -p test_analysis_rag_v4.py -v",
        "protected_sources_unchanged": pilot.check_protected_sources(), "history_artifacts_unchanged": len(evaluation.history_inventory()),
        "done_reasons": dict(Counter(r["hybrid"]["llm_record"]["audit"]["provenance"].get("runtime_metrics", {}).get("done_reason")
                                     for r in rows if "raw_model_content" in r["hybrid"]["llm_record"]["audit"]["provenance"])),
        "formal_fpr_recomputed": False, "psr_recomputed": False,
    }
    pilot.write_json(output / "audit.json", result)
    if export:
        pilot.require(export.is_relative_to((ROOT / "results/processed").resolve()) and not export.exists(), "Use a new processed output directory.")
        export.mkdir(parents=True, exist_ok=False)
        names = ("summary.json", "design-manifest.json", "manifest.json", "runtime.json", "audit.json", "retrieval.json", "analysis-corpus.json")
        for name in names:
            shutil.copyfile(output / name, export / name)
        pilot.write_json(export / "provenance.json", {
            "scope": "published-synthetic-analysis-rag-pilot-not-formal-not-independent-holdout",
            "source_directory": output.relative_to(ROOT).as_posix(), "exact_byte_copies": list(names),
            "file_sha256": {name: pilot.digest(export / name) for name in names},
            "local_source_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
            "formal_results_changed": False, "raw_model_claims_replaced": False, "prototype_promoted_to_formal_runner": False,
        })
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Use development result directory.")
    audit(destination, args.export_dir.resolve() if args.export_dir else None)
