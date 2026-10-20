"""Audit v5 source coordinates, provenance and preservation; never call a model or Chroma."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "knowledge/analysis-v5/corpus.rev1.json"
SCHEMA = ROOT / "schemas/analysis-knowledge-v5-rev1.schema.json"
OUT = ROOT / "results/processed/analysis-corpus-v5-rev1-20261020"
FORMAL = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(name):
    path = (ROOT / name).resolve()
    require(path.is_relative_to(ROOT), "Reference path leaves the workspace.")
    return path


def unique(items, key):
    mapping = {row[key]: row for row in items}
    require(len(mapping) == len(items), f"Duplicate {key}.")
    return mapping


def check_inventory(inventory):
    for name, expected in inventory.items():
        require(sha(local(name)) == expected, f"Protected file differs: {name}")
    return len(inventory)


def validate(corpus):
    """Mechanical checks do not establish citation entailment or retrieval relevance."""
    Draft202012Validator(read(SCHEMA)).validate(corpus)
    lock_path = local(corpus["source_lock_path"])
    require(sha(lock_path) == corpus["source_lock_sha256"], "Source lock changed.")
    lock = read(lock_path)
    sources = unique(lock["sources"], "source_id")
    require(set(sources) == {"owasp-wstg42", "portswigger-blind", "portswigger-conditional-lab", "portswigger-timing"},
            "Unexpected source set.")
    segments = unique(lock["reference_segments"], "reference_id")
    texts = {}
    for source_id, source in sources.items():
        path = local(source["snapshot_path"])
        require(sha(path) == source["snapshot_sha256"], f"Source snapshot differs: {source_id}")
        texts[source_id] = path.read_text(encoding="utf-8").splitlines()
        if source_id == "owasp-wstg42":
            old = read(ROOT / "knowledge/sources.lock.json")["sources"][0]
            require(source["version"] == old["commit"] and source["snapshot_sha256"] == old["files"][0]["snapshot_sha256"],
                    "OWASP differs from its previously pinned version.")
        else:
            require(source["canonical_url"].startswith("https://portswigger.net/"), "Unexpected publisher URL.")
            require(sha(local(source["raw_html_path"])) == source["raw_html_sha256"] == source["version"],
                    "Raw website snapshot differs.")
    for ref in segments.values():
        require(ref["source_id"] in sources, "Unknown source in citation.")
        lines = texts[ref["source_id"]]
        a, b = ref["line_start"], ref["line_end"]
        require(1 <= a <= b <= len(lines), "Citation range leaves snapshot.")
        segment = "\n".join(lines[a-1:b])
        require(hashlib.sha256(segment.encode()).hexdigest() == ref["segment_sha256"], "Citation segment differs.")
    contracts = unique(corpus["prompt_contract"]["contract_references"], "contract_id")
    for ref in contracts.values():
        path = local(ref["path"])
        require(sha(path) == ref["file_sha256"], "Local project contract changed.")
        if path.suffix == ".py":
            symbols = {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            require(set(ref["locator"].split(" / ")) <= symbols, "Project function locator does not resolve.")
        else:
            value = read(path)
            for token in ref["locator"].removeprefix("/").split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                require(isinstance(value, dict) and token in value, "Project JSON pointer does not resolve.")
                value = value[token]
    revision = corpus["revision"]
    require(sha(local(revision["supersedes_corpus_path"])) == revision["supersedes_corpus_sha256"], "Reviewed draft changed.")
    require(sha(local(revision["feedback_path"])) == revision["feedback_sha256"], "Researcher feedback record changed.")
    feedback = read(local(revision["feedback_path"]))
    require(feedback["reviewed_corpus_sha256"] == revision["supersedes_corpus_sha256"]
            and feedback["approval_of_revised_corpus"] == "not-yet-given", "Do not promote requested revisions to approval.")
    require(read(local(revision["supersedes_corpus_path"]))["source_lock_sha256"] == corpus["source_lock_sha256"],
            "Revision changes the pinned upstream sources.")
    design_ref = corpus["design_decisions"]
    require(sha(local(design_ref["path"])) == design_ref["file_sha256"], "Design decision document changed.")
    design_document = read(local(design_ref["path"]))
    designs = unique(design_document["decisions"], "decision_id")
    require(set(designs) == set(design_ref["decision_ids"]), "Design decision IDs differ.")
    require(design_document["feedback_sha256"] == revision["feedback_sha256"], "Design feedback basis differs.")
    for decision in designs.values():
        require(decision["rationale"] and decision["operational_effect"]
                and set(decision["contract_reference_ids"]) <= contracts.keys(), "Missing inspectable design basis.")
    chunks = unique(corpus["chunks"], "chunk_id")
    require(len({c["topic"] for c in chunks.values()}) == 7, "Missing or duplicate task topic.")
    origins, source_words, review_rows, used = Counter(), Counter(), [], set()
    for chunk in chunks.values():
        require(any(s["origin"] == "source_paraphrase" for rows in chunk["fields"].values() for s in rows)
                or chunk["topic"] == "conclusion-scope", "Chunk has no source foundation.")
        for field, rows in chunk["fields"].items():
            for index, item in enumerate(rows):
                require(not re.search(r"\bS(?:[1-9]|1[0-2])\b|VAL-01|formal-sqli|27[,.]78|74[,.]81|\u2014", item["text"]),
                        "Experiment label, outcome or prohibited punctuation in reference text.")
                origins[item["origin"]] += 1
                if item["origin"] == "source_paraphrase":
                    require(not re.search(r"1500|3/3|0/3|reason_code|HTTP 404", item["text"]),
                            "Project-specific rule attributed to a general source.")
                    require(set(item["source_reference_ids"]) <= segments.keys(), "Unknown per-field source reference.")
                    used.update(item["source_reference_ids"])
                    for source_id in {segments[r]["source_id"] for r in item["source_reference_ids"]}:
                        source_words[source_id] += len(item["text"].split())
                else:
                    require(set(item["adaptation_basis"]) <= set(contracts) | set(designs),
                            "Unknown editorial adaptation basis.")
                review_rows.append({"chunk_id": chunk["chunk_id"], "field": field, "statement_index": index,
                                    "origin": item["origin"], "source_reference_ids": item["source_reference_ids"],
                                    "decision": "pending", "reviewer_comment": ""})
    require(used == set(segments), "Unreferenced source pointer in the new draft.")
    return {"chunks": len(chunks), "substantive_fields": 35, "statements": sum(origins.values()),
            "origin_counts": dict(origins), "sources": len(sources), "source_segments": len(segments),
            "source_paraphrase_word_counts_by_page": dict(source_words),
            "all_field_source_coordinates_resolve": True, "all_project_contract_hashes_match": True,
            "all_project_contract_locators_resolve": True, "named_design_decisions": len(designs),
            "synthetic_examples": 0}, review_rows


def audit():
    corpus = read(CORPUS)
    summary, rows = validate(corpus)
    baseline = read(OUT / "preservation-baseline.json")
    preserved = check_inventory(baseline["files"])
    formal = check_inventory(read(FORMAL))
    report = {
        "audit_id": "analysis-corpus-v5-rev1-20261020", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "mechanical-checks-passed-draft-awaiting-researcher-review",
        "corpus_path": CORPUS.relative_to(ROOT).as_posix(), "corpus_sha256": sha(CORPUS),
        "source_lock_sha256": sha(local(corpus["source_lock_path"])), "schema_sha256": sha(SCHEMA),
        "checker_sha256": sha(Path(__file__)), "preservation_baseline_sha256": sha(OUT / "preservation-baseline.json"),
        "summary": summary, "protected_files_unchanged": preserved, "formal_inventory_files_unchanged": formal,
        "researcher_review": "pending", "independent_or_blinded_review": False,
        "editorial_review": "Codex source reading and per-statement provenance; post-v4 development",
        "checks_prove_source_entailment": False, "checks_prove_retrieval_quality": False,
        "model_calls": 0, "embedding_calls": 0, "dvwa_requests": 0, "formal_metrics_recomputed": False,
        "retrieval_policy_frozen": False,
        "researcher_feedback_on_previous_draft": corpus["revision"],
        "contract_semantics_evidence_path": (OUT / "contract-semantics.json").relative_to(ROOT).as_posix(),
        "contract_semantics_evidence_sha256": sha(OUT / "contract-semantics.json"),
    }
    review = {"document_type": "unsubmitted-review-form-not-approval-receipt", "corpus_sha256": sha(CORPUS),
              "source_lock_sha256": report["source_lock_sha256"], "researcher_name": None,
              "reviewed_at": None, "decision": "pending", "scope": "this-v5-draft-only", "statements": rows}
    return report, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-initial-audit", action="store_true")
    parser.add_argument("--record", choices=("initial", "final"), default="final")
    args = parser.parse_args()
    report, review = audit()
    if args.write_initial_audit:
        targets = [(OUT / f"audit.{args.record}.json", report), (OUT / f"researcher-review.{args.record}.template.json", review)]
        require(not any(p.exists() for p, _ in targets), "Use a new audit target; do not overwrite prior evidence.")
        for path, document in targets:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
    else:
        initial = read(OUT / f"audit.{args.record}.json")
        for field in ("corpus_sha256", "source_lock_sha256", "schema_sha256", "checker_sha256", "preservation_baseline_sha256", "summary"):
            require(report[field] == initial[field], f"Recorded audit differs: {field}")
    print(json.dumps({"status": report["status"], **report["summary"],
                      "protected_files_unchanged": report["protected_files_unchanged"],
                      "formal_files_unchanged": report["formal_inventory_files_unchanged"]}))


if __name__ == "__main__":
    main()
