"""Compare completed P2 analysis outputs with the locked blinded-review labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

from run_qwen_api_p2_eval import DEFAULT_OUTPUT, DEFAULT_REQUESTS, load_requests, utc_now, write_json_atomic


DECISIONS = ("positive", "negative", "inconclusive")
DEFAULT_ANNOTATIONS = DEFAULT_OUTPUT / "operator/annotations-VAL-01.locked.csv"
DEFAULT_LOCK = DEFAULT_OUTPUT / "operator/annotation-lock.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def calculate_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [case for case in cases if case["scored"]]
    agreements = sum(case["agreement"] is True for case in resolved)
    matrix = {reference: {prediction: 0 for prediction in DECISIONS} for reference in DECISIONS}
    per_label = {}
    for reference in DECISIONS:
        group = [case for case in cases if case["reference_decision"] == reference]
        scored_group = [case for case in group if case["scored"]]
        correct = sum(case["agreement"] is True for case in scored_group)
        for case in scored_group:
            matrix[reference][case["model_decision"]] += 1
        per_label[reference] = {
            "reference_count": len(group),
            "scored_count": len(scored_group),
            "coverage": rate(len(scored_group), len(group)),
            "exact_agreement_count": correct,
            "exact_agreement_on_scored": rate(correct, len(scored_group)),
        }

    per_technique = {}
    techniques = sorted({case["technique"] for case in cases})
    for technique in techniques:
        group = [case for case in cases if case["technique"] == technique]
        scored_group = [case for case in group if case["scored"]]
        correct = sum(case["agreement"] is True for case in scored_group)
        technique_matrix = {reference: {prediction: 0 for prediction in DECISIONS}
                            for reference in DECISIONS}
        for case in scored_group:
            technique_matrix[case["reference_decision"]][case["model_decision"]] += 1
        per_technique[technique] = {
            "case_count": len(group),
            "scored_count": len(scored_group),
            "coverage": rate(len(scored_group), len(group)),
            "exact_agreement_count": correct,
            "exact_agreement_on_scored": rate(correct, len(scored_group)),
            "confusion_matrix_reference_rows_prediction_columns": technique_matrix,
        }

    return {
        "case_count": len(cases),
        "scored_count": len(resolved),
        "unresolved_count": len(cases) - len(resolved),
        "coverage": rate(len(resolved), len(cases)),
        "exact_agreement_count": agreements,
        "exact_agreement_on_scored": rate(agreements, len(resolved)),
        "confusion_matrix_reference_rows_prediction_columns": matrix,
        "by_reference_label": per_label,
        "by_technique": per_technique,
    }


def assess(run_dir: Path, requests_path: Path, annotations_path: Path,
           lock_path: Path, output_path: Path) -> dict[str, Any]:
    requests, request_digest = load_requests(requests_path)
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    results_summary = json.loads((run_dir / "evaluation-results.json").read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    annotation_bytes = annotations_path.read_bytes()

    if manifest.get("requests_sha256") != request_digest:
        raise ValueError("Run manifest does not match the frozen request packet")
    if results_summary.get("requests_sha256") != request_digest:
        raise ValueError("Result summary does not match the frozen request packet")
    if lock.get("prepared_requests_sha256") != request_digest:
        raise ValueError("Annotation lock does not match the frozen request packet")
    annotation_digest = sha256_bytes(annotation_bytes)
    if lock.get("annotation_sha256") != annotation_digest:
        raise ValueError("Locked annotation file hash does not match its receipt")
    if lock.get("researcher_confirmation") != "confirmed_all_candidate_labels":
        raise ValueError("Researcher confirmation of all candidate labels is not recorded")

    with annotations_path.open(encoding="utf-8-sig", newline="") as stream:
        annotation_rows = list(csv.DictReader(stream))
    labels: dict[str, str] = {}
    for row in annotation_rows:
        review_id = row.get("review_id", "")
        decision = row.get("decision", "")
        if not review_id or review_id in labels:
            raise ValueError("Annotations must have unique, non-empty review IDs")
        if decision not in DECISIONS:
            raise ValueError(f"Invalid reference decision for {review_id}")
        if row.get("validator_id") != lock.get("validator_id"):
            raise ValueError(f"Validator ID mismatch for {review_id}")
        labels[review_id] = decision

    request_by_id = {row["review_id"]: row for row in requests}
    result_by_id = {row["review_id"]: row for row in results_summary.get("cases", [])}
    expected_ids = [row["review_id"] for row in requests]
    if set(labels) != set(expected_ids) or set(result_by_id) != set(expected_ids):
        raise ValueError("Request, annotation, and result IDs must match exactly")
    if results_summary.get("saved_result_count") != len(expected_ids):
        raise ValueError("The result summary is incomplete")

    cases = []
    for review_id in expected_ids:
        result = result_by_id[review_id]
        analysis = result.get("analysis")
        decision = analysis.get("decision") if isinstance(analysis, dict) else None
        scored = (
            result.get("api_status") == "ok"
            and result.get("analysis_status") == "parsed"
            and decision in DECISIONS
        )
        reference = labels[review_id]
        cases.append({
            "review_id": review_id,
            "technique": request_by_id[review_id]["document"]["technique"],
            "reference_decision": reference,
            "api_status": result.get("api_status"),
            "analysis_status": result.get("analysis_status"),
            "model_decision": decision if scored else None,
            "scored": scored,
            "agreement": reference == decision if scored else None,
            "request_completion_unknown": bool(result.get("request_completion_unknown", False)),
        })

    assessment = {
        "schema": "qwen-api-p2-assessment-v1",
        "assessed_at_utc": utc_now(),
        "run_state": manifest.get("state"),
        "requested_model": manifest.get("requested_model"),
        "prompt_version": manifest.get("prompt_version"),
        "rag_mode": manifest.get("rag_mode"),
        "requests_sha256": request_digest,
        "reference": {
            "validator_id": lock.get("validator_id"),
            "researcher_confirmation": lock.get("researcher_confirmation"),
            "annotation_sha256": annotation_digest,
            "label_counts": dict(sorted(Counter(labels.values()).items())),
        },
        "metric_scope": {
            "agreement": "Exact decision match with the locked blinded-review labels, conditional on a parsed API response.",
            "coverage": "Parsed API decisions divided by all 18 planned cases.",
            "unresolved_policy": "Ambiguous requests and transport timeouts are excluded from the agreement denominator and retained as unresolved.",
            "formal_FPR_claim": False,
            "formal_PSR_claim": False,
        },
        "metrics": calculate_metrics(cases),
        "unresolved_cases": [case for case in cases if not case["scored"]],
        "cases": cases,
    }
    write_json_atomic(output_path, assessment)
    return assessment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--requests", type=Path, default=DEFAULT_REQUESTS)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    annotations = (args.annotations or (run_dir / "operator/annotations-VAL-01.locked.csv")).resolve()
    lock = (args.lock or (run_dir / "operator/annotation-lock.json")).resolve()
    output = (args.output or (run_dir / "evaluation-assessment.json")).resolve()
    try:
        assessment = assess(run_dir, args.requests.resolve(), annotations, lock, output)
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps({
        "state": assessment["run_state"],
        "assessment_file": str(output),
        "metrics": assessment["metrics"],
        "formal_FPR_claim": False,
        "formal_PSR_claim": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
