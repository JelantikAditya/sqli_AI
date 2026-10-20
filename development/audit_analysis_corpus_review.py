"""Check the traceability of an editorial review; do not infer semantic truth or call models."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/processed/analysis-rag-corpus-review-20261019"
PILOT = ROOT / "results/processed/analysis-rag-ab-v4-20261019"
NOTES = ROOT / "development/analysis_corpus_review_notes.json"
FORMAL = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, value):
    # Never replace an existing review artifact, source, experiment record or index.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def check_inventory(inventory):
    for name, expected in inventory.items():
        require(sha(ROOT / name) == expected, f"Protected file changed: {name}")
    return len(inventory)


def prepare():
    require(not OUTPUT.exists(), "Use a new review directory; do not overwrite a prior review.")
    corpus = read(ROOT / "knowledge/sqli-entries.json")
    lock = read(ROOT / "knowledge/sources.lock.json")
    formal = read(FORMAL)
    check_inventory(formal)
    approval = read(ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json")
    require(sha(ROOT / "knowledge/sqli-entries.json") == approval["approved_snapshot"]["corpus_sha256"],
            "Current corpus differs from the human-approved snapshot.")
    protected = dict(formal)
    # File hashes alone, without opening Chroma or importing the experiment runners.
    paths = [NOTES, FORMAL, Path(__file__), ROOT / "development/analyze_response_v1.py",
             ROOT / "development/analyze_response_v2.py", ROOT / "development/analysis_rag_v4.py",
             ROOT / "development/verify_response_v3.py",
             ROOT / "docs/evidence/review-peneliti-2026-10-12.md",
             ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json",
             ROOT / "docs/keputusan-korpus-formal-u07-2026-10-17.md"]
    for folder in (ROOT / "knowledge", ROOT / "data/raw/knowledge-sources"):
        paths.extend(p for p in folder.rglob("*") if p.is_file())
    for name in approval["approved_snapshot"]["index_file_sha256"]:
        paths.append(ROOT / name)
    for folder in (ROOT / "results/raw/development", ROOT / "results/processed"):
        for run in folder.iterdir():
            if run.is_dir() and run.name.startswith(("response-analysis-", "analysis-rag-ab-v4-")):
                paths.extend(p for p in run.rglob("*") if p.is_file())
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        actual = sha(path)
        require(relative not in protected or protected[relative] == actual, f"Conflicting baseline: {relative}")
        protected[relative] = actual
    OUTPUT.mkdir(parents=True)
    write_new(OUTPUT / "review-baseline.json", {
        "review_id": "analysis-rag-corpus-review-20261019", "formal_source_count": len(formal),
        "source_lock_sha256": sha(ROOT / "knowledge/sources.lock.json"),
        "original_metadata_review_status": corpus["curation"]["researcher_review"],
        "source_snapshot_files": sum(len(s["files"]) for s in lock["sources"]),
        "protected_file_sha256": protected,
    })
    print(json.dumps({"phase": "prepare", "protected_files": len(protected), "formal_sources": len(formal)}))


def source_segment(ref, lock):
    source = next(s for s in lock["sources"] if s["source_id"] == ref["source_id"])
    file = next(f for f in source["files"] if f["repository_path"] == ref["repository_path"])
    path = ROOT / file["snapshot_path"]
    require(sha(path) == file["snapshot_sha256"], "Locked source snapshot changed.")
    require(ref["source_sha256"] == file["sha256"] and ref["commit"] == source["commit"],
            "Source provenance does not match lock.")
    start, end = ref["line_start"], ref["line_end"]
    require(1 <= start <= end, "Invalid source range.")
    if file["snapshot_kind"] == "full-file":
        lines = path.read_text(encoding="utf-8").split("\n")
        require(end <= len(lines), "Source range exceeds snapshot.")
        segment = lines[start - 1:end]
    else:
        snapshot = read(path)
        require(snapshot["source_sha256"] == file["sha256"], "Selected snapshot origin differs.")
        section = next(s for s in snapshot["sections"] if s["line_start"] <= start <= end <= s["line_end"])
        # Selected snapshots serialize a final blank source line with a trailing newline.
        lines = section["text"].split("\n")
        require(len(lines) == section["line_end"] - section["line_start"] + 1,
                "Selected-section line coordinates differ.")
        segment = lines[start - section["line_start"]:end - section["line_start"] + 1]
    require(segment and ref["section"].lower() in "\n".join(segment).lower(), "Source heading missing.")
    return {**ref, "snapshot_path": file["snapshot_path"], "snapshot_sha256": sha(path),
            "reviewed_segment_sha256": hashlib.sha256("\n".join(segment).encode()).hexdigest()}


def build_review():
    baseline = read(OUTPUT / "review-baseline.json")
    protected = dict(baseline["protected_file_sha256"])
    checker_name = Path(__file__).relative_to(ROOT).as_posix()
    checker_revision = None
    if sha(Path(__file__)) != protected[checker_name]:
        # A failed initial check must not force a rewrite of the original baseline.
        # Record this checker's repair separately; every source remains protected.
        checker_revision = read(OUTPUT / "review-checker-revision.json")
        require(checker_revision["baseline_sha256"] == sha(OUTPUT / "review-baseline.json")
                and checker_revision["original_checker_sha256"] == protected[checker_name]
                and checker_revision["revised_checker_sha256"] == sha(Path(__file__))
                and checker_revision["changed_file"] == checker_name,
                "Unrecorded checker revision; source baselines cannot be bypassed.")
        del protected[checker_name]
    count = check_inventory(protected)
    notes, corpus, lock = read(NOTES), read(PILOT / "analysis-corpus.json"), read(ROOT / "knowledge/sources.lock.json")
    originals = {e["entry_id"]: e for e in read(ROOT / "knowledge/sqli-entries.json")["entries"]}
    notes_by_id = {e["entry_id"]: e for e in notes["entries"]}
    require(len(notes_by_id) == len(notes["entries"]) == len(corpus["chunks"]) == 9, "Review requires nine unique entries.")
    require(set(notes_by_id) == set(originals), "Review does not cover the original entries.")
    require(notes["independent_or_blinded"] is False and notes["human_approval_of_this_review"] == "not-recorded",
            "Do not promote an agent review to independent or human approval.")
    for source in lock["sources"]:
        for file in source["files"]:
            require(sha(ROOT / file["snapshot_path"]) == file["snapshot_sha256"], "Source snapshot differs from lock.")
    receipts = read(PILOT / "retrieval.json")
    selected = {c["entry_id"] for r in receipts.values() for c in r["chunks"]}
    reviewed = []
    for chunk in corpus["chunks"]:
        entry_id = chunk["entry_id"]
        values, annotation = json.loads(chunk["text"]), notes_by_id[entry_id]
        require(hashlib.sha256(chunk["text"].encode()).hexdigest() == chunk["text_sha256"], "Chunk hash differs.")
        expected = {k: originals[entry_id][k] for k in values}
        expected["limitations"] = expected["limitations"].replace("DVWA result", "result for a particular target").replace(
            "no DVWA level", "no target configuration")
        require(values == expected, "Projection differs from the original plus the two recorded anonymizations.")
        substantive = {"functional_semantics", "detection_method", "limitations"}
        require(set(annotation["fields"]) == substantive, "Every substantive field needs an annotation.")
        require(set(values) == substantive | {"title", "vulnerability_type"}, "Unexpected projected fields.")
        require(values["vulnerability_type"] == chunk["technique"], "Technique label differs.")
        references = [source_segment(ref, lock) for ref in chunk["source_refs"]]
        fields = []
        for field, value in values.items():
            if field in substantive:
                note = annotation["fields"][field]
            else:
                note = {"rating": "editorial_label", "source_ref_indices": [0, 1],
                        "note": "Label kurasi sesuai mekanisme pada dua rujukan; tidak menetapkan hasil target."}
            require(note["rating"] in notes["rating_definitions"] and note["note"], "Missing review rationale.")
            require(note["source_ref_indices"] and all(0 <= i < len(references) for i in note["source_ref_indices"]),
                    "Invalid per-field citation.")
            fields.append({"field": field, "value": value, "rating": note["rating"], "note": note["note"],
                           "supporting_references": [references[i] for i in note["source_ref_indices"]]})
        require(all(ref["section"] == "Remediation" for ref in references[2:]), "Unexpected unused pointer.")
        reviewed.append({"entry_id": entry_id, "technique": chunk["technique"], "selected_in_v4": entry_id in selected,
                         "chunk_text_sha256": chunk["text_sha256"], "disposition": annotation["disposition"],
                         "fields": fields, "inherited_references_unused_for_projected_fields": references[2:]})
    for row in notes["coverage_review"]:
        require(set(row["selected_entries"]) <= selected, "Coverage claims reference an unselected entry.")
        if row.get("available_entry"):
            require(row["available_entry"] in originals and row["available_entry"] not in selected,
                    "Available-but-unretrieved entry differs from retrieval.")
    require(len(selected) == 6 and len(reviewed) == 9, "Actual retrieval scope differs.")
    approval = read(ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json")
    require(approval["decision"] == "approved-for-formal-use"
            and approval["approved_snapshot"]["corpus_sha256"] == corpus["source_corpus_sha256"]
            == sha(ROOT / "knowledge/sqli-entries.json")
            and approval["approved_snapshot"]["source_lock_sha256"] == sha(ROOT / "knowledge/sources.lock.json"),
            "Approval receipt does not match the reviewed source corpus.")
    formal_count = check_inventory(read(FORMAL))
    index_comparison = []
    for name, expected in approval["approved_snapshot"]["index_file_sha256"].items():
        # Historical byte identity and preservation during this review are distinct checks.
        current = sha(ROOT / name)
        index_comparison.append({"path": name, "approval_sha256": expected, "current_sha256": current,
                                 "matches_historical_approval": current == expected,
                                 "unchanged_since_review_baseline": current == protected[name]})
    check_inventory(protected)
    ratings = Counter(f["rating"] for e in reviewed for f in e["fields"])
    return {"review_id": notes["review_id"], "review_type": notes["review_type"], "reviewer": notes["reviewer"],
            "independent_or_blinded": False, "human_approval_of_this_review": "not-recorded",
            "scope": "technical-source-fidelity-and-task-coverage-not-a-new-rag-experiment",
            "source_corpus_sha256": corpus["source_corpus_sha256"], "projection_sha256": sha(PILOT / "analysis-corpus.json"),
            "retrieval_sha256": sha(PILOT / "retrieval.json"), "notes_sha256": sha(NOTES),
            "baseline_sha256": sha(OUTPUT / "review-baseline.json"),
            "checker_revision": checker_revision,
            "checker_revision_sha256": sha(OUTPUT / "review-checker-revision.json") if checker_revision else None,
            "original_corpus_review": {"frozen_metadata": corpus["researcher_review"],
                "documented_pilot_approval_date": "2026-10-12", "formal_use_approval_date": "2026-10-17",
                "receipt": "docs/evidence/u07-formal-corpus-decision-2026-10-17.json",
                "interpretation": "pending-is-frozen-metadata-not-current-absence-of-original-corpus-approval",
                "approval_extends_automatically_to_analysis_projection": False},
            "rating_definitions": notes["rating_definitions"], "entries": reviewed,
            "coverage_review": notes["coverage_review"],
            "proposed_changes_for_new_version_only": notes["proposed_changes_for_new_version_only"],
            "summary": {"entries_reviewed": 9, "projected_fields_reviewed": sum(ratings.values()),
                "selected_entries_in_v4": len(selected), "field_rating_counts": dict(ratings),
                "scope_ambiguities": sum(f["rating"] == "scope_ambiguity" for e in reviewed for f in e["fields"]),
                "entries_with_unused_remediation_reference": len(reviewed), "coverage_requirements_reviewed": len(notes["coverage_review"])},
            "historical_index_comparison": index_comparison,
            "historical_index_interpretation": "Two active index files already differ at baseline from the 17 October receipt; preserve and report, without opening Chroma or inferring a content change.",
            "mechanical_checks": {"protected_files_unchanged": count, "formal_sources_unchanged": formal_count,
                "review_checker_revisions_recorded": int(checker_revision is not None),
                "formal_index_files_unchanged_since_review_baseline": sum(r["unchanged_since_review_baseline"] for r in index_comparison),
                "formal_index_files_match_historical_approval": sum(r["matches_historical_approval"] for r in index_comparison),
                "locked_source_files_match_hashes": baseline["source_snapshot_files"],
                "per_field_source_ranges_resolve": True, "projection_values_match_frozen_corpus": True,
                "checks_prove_semantic_truth": False, "checks_prove_retrieval_relevance": False},
            "model_calls": 0, "embedding_calls": 0, "dvwa_requests": 0,
            "original_corpus_modified": False, "formal_metrics_recomputed": False,
            "causal_explanation_of_v4_null_result_established": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "review", "verify"), required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
        return
    review = build_review()
    if args.phase == "review":
        write_new(OUTPUT / "review.json", review)
    else:
        require(read(OUTPUT / "review.json") == review, "Review artifact no longer reproduces from its pinned inputs.")
    print(json.dumps({"phase": args.phase, "summary": review["summary"], "mechanical_checks": review["mechanical_checks"]}))


if __name__ == "__main__":
    main()
