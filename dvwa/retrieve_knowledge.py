"""Retrieve relevant local reference chunks for one DVWA scenario."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rag_pipeline import ROOT, load_catalog, read_manifest, retrieve_chunks, scenario_query


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="Scenario ID S1 through S12")
    parser.add_argument("--manifest", required=True, type=Path, help="Knowledge base manifest path")
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_catalog()
    scenarios = {item["scenario_id"]: item for item in catalog["scenarios"]}
    if args.scenario not in scenarios:
        raise SystemExit("Unknown scenario. Choose S1 through S12.")
    if not 1 <= args.top_k <= 10:
        raise SystemExit("--top-k must be between 1 and 10.")

    manifest = read_manifest(args.manifest)
    query = scenario_query(scenarios[args.scenario])
    retrieval = retrieve_chunks(query, manifest, args.top_k)
    retrieval_document = {
        "schema_version": "1.0.0",
        "scenario_id": args.scenario,
        "query": query,
        "retrieval": retrieval,
        "retrieved_chunk_ids": [item["chunk_id"] for item in retrieval["chunks"]],
    }

    raw_directory = ROOT / "results" / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = raw_directory / f"retrieval-{args.scenario}-{timestamp}-{uuid4().hex[:6]}.json"
    with output_path.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(retrieval_document, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(f"Retrieval record: {output_path}")
    print(json.dumps({"knowledge_base_id": retrieval["knowledge_base_id"], "chunk_count": len(retrieval["chunks"]), "retrieved_chunk_ids": retrieval_document["retrieved_chunk_ids"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
