"""Import VAL-01 P4 annotations and calculate the frozen cohort metrics."""

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from aggregate_metrics import aggregate, csv_rows
from blind_review import import_annotations
from experiment_dataset import load_runs
from run_decision_evaluator import summarize_fpr_replicate


PACKAGE = ROOT / "results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01"
OUTPUT = PACKAGE
ANNOTATION_SOURCE = Path(r"C:\Users\ASUS TUF\Downloads\annotations (2).csv")
RECOVERY1 = ROOT / "results/raw/formal/poolside-laguna-p4-recovery1-20261023"
REPLICATE3 = ROOT / "results/raw/formal/poolside-laguna-p4-replicate3-20261023"
AMENDMENT = ROOT / "results/raw/formal/poolside-p4-s5b-r3-amend1-20261023"
ASSEMBLY = ROOT / "docs/evidence/poolside-laguna-p4-replicate3-assembly-draft-2026-10-23.json"
PACKAGE_SHA256 = "52fa92a88d28009504c2d68c70d08c5f117237bb171cf7dcfa314f44bd4fa51b"
EXPECTED_REUSE_AUDIT_SHA256 = "631d873fb5a17e529368c8f7c69bf23b488301b924f035accda4dbc6bc21ec57"
EXPECTED_ANNOTATIONS_SHA256 = "5cf2bc2bdeb02a12ad4ab2247ffec4221e37afe50b79cb67f14e18491fc02351"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, data):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def compose_runs():
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    require(assembly["status"] == "targeted-amendment-completed-pending-VAL01-and-human-validation",
            "P4 assembly has an unexpected status.")
    require(assembly["reuse"]["sha256"] == EXPECTED_REUSE_AUDIT_SHA256,
            "P4 assembly no longer binds the reviewed R1/R2 reuse audit.")
    require(digest(ROOT / assembly["reuse"]["path"]) == EXPECTED_REUSE_AUDIT_SHA256,
            "The R1/R2 reuse audit changed.")
    require(digest(REPLICATE3 / "ledger.jsonl") == assembly["candidate_hashes"]["execution_ledger"],
            "The R3 source ledger differs from the assembled cohort receipt.")
    require(digest(AMENDMENT / "ledger.jsonl")
            == assembly["targeted_amendment"]["execution_ledger_sha256"],
            "The targeted replacement ledger differs from the assembled cohort receipt.")
    package = json.loads((PACKAGE / "validator/packets.json").read_text(encoding="utf-8"))
    require(digest(PACKAGE / "validator/packets.json") == PACKAGE_SHA256
            and package["review_readiness"] == "ready_for_independent_formal_review"
            and len(package["packets"]) == 990,
            "The frozen VAL-01 packet changed or has unexpected coverage.")

    r12_all = load_runs(RECOVERY1)
    reused = [run for run in r12_all if run["replicate"] in (1, 2)]
    r3_all = load_runs(REPLICATE3)
    original_r3 = [run for run in r3_all if run["status"] == "completed" or
                   (run["status"] == "excluded" and run["condition_id"] == "C"
                    and run["scenario_id"] in {"S10", "S11", "S12"})]
    supplement = load_runs(AMENDMENT)
    require(Counter(run["status"] for run in reused) == {"completed": 66, "excluded": 6},
            "R1/R2 must contain 66 completed and six design-excluded units.")
    require(Counter(run["status"] for run in original_r3) == {"completed": 32, "excluded": 3},
            "R3 must contain 32 completed and three design-excluded units.")
    require(len(supplement) == 1 and supplement[0]["status"] == "completed"
            and supplement[0]["metric_eligible"]
            and (supplement[0]["condition_id"], supplement[0]["scenario_id"],
                 supplement[0]["replicate"]) == ("B", "S5", 3),
            "The B/S5/R3 replacement must be the one eligible supplemental unit.")
    runs = reused + original_r3 + supplement
    require(Counter(run["status"] for run in runs) == {"completed": 99, "excluded": 9},
            "The composite cohort must contain 99 complete and nine design-excluded units.")
    require(all(run["metric_eligible"] and len(run["candidates"]) == 10
                for run in runs if run["status"] == "completed"),
            "Every included completed unit must have ten metric-eligible candidates.")
    for replicate in (1, 2, 3):
        counts = Counter(run["condition_id"] for run in runs
                         if run["replicate"] == replicate and run["status"] == "completed")
        require(counts == {"A": 12, "B": 12, "C": 9},
                f"Condition coverage is incomplete in replicate {replicate}.")
    return runs


def inspect_fpr_blocker():
    ledger_path = RECOVERY1 / "ledger.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    unit_id = "poolside-laguna-p4-20261023-a-s12-r2"
    final = next(event for event in reversed(events)
                 if event.get("unit_id") == unit_id and event["event_type"] == "attempt_completed")
    adaptive_path = (RECOVERY1 / final["adaptive_result_path"]).resolve()
    require(adaptive_path.is_relative_to(RECOVERY1.resolve())
            and digest(adaptive_path) == final["adaptive_result_sha256"],
            "The saved analysis artifact for the FPR abstention failed integrity checks.")
    adaptive = json.loads(adaptive_path.read_text(encoding="utf-8"))
    unresolved = [record for record in adaptive["candidate_records"]
                  if record["system_claim"] == "inconclusive"]
    require(len(unresolved) == 1 and unresolved[0]["rule_signal"] == "CONSISTENT_NEGATIVE"
            and {"trial_assessment_evidence_mismatch", "model_claim_evidence_mismatch"}
            <= set(unresolved[0]["analysis_warnings"]),
            "The saved S12 A/R2 abstention does not match the reviewed blocker signature.")
    return {
        "condition_id": "A", "scenario_id": "S12", "replicate": 2,
        "run_decision": "inconclusive", "candidate_analysis_inconclusive_count": 1,
        "executor_rule_signal": "CONSISTENT_NEGATIVE",
        "analysis_warnings": sorted(unresolved[0]["analysis_warnings"]),
    }


def prepare():
    imported_path = OUTPUT / "annotations-VAL-01.imported.json"
    metrics_path = OUTPUT / "metrics-P4-VAL01.json"
    csv_path = OUTPUT / "metrics-P4-VAL01.csv"
    audit_path = OUTPUT / "analysis-audit.private.json"
    for path in (imported_path, metrics_path, csv_path, audit_path):
        require(not path.exists(), f"Refusing to overwrite existing result: {path.name}")
    require(ANNOTATION_SOURCE.is_file(), "VAL-01 annotation CSV was not found at the supplied path.")
    source_sha = digest(ANNOTATION_SOURCE)
    require(source_sha == EXPECTED_ANNOTATIONS_SHA256,
            "The supplied VAL-01 CSV differs from the file verified for this import.")

    # The official importer verifies packet integrity, all 990 IDs, labels, and justifications.
    imported = import_annotations(PACKAGE, ANNOTATION_SOURCE, "VAL-01")
    require(len(imported["annotations"]) == 990, "The official importer returned an incomplete annotation set.")
    labels = Counter(item["decision"] for item in imported["annotations"])
    require(labels == {"success": 417, "failure": 573},
            "Imported label totals differ from the file validated in the previous step.")

    runs = compose_runs()
    metrics = aggregate(runs, imported["annotations"])
    metrics.update({
        "dataset_context": "P4 Poolside Laguna composite cohort after independent VAL-01 review",
        "validator_id": imported["validator_id"],
        "annotation_source_sha256": source_sha,
        "review_package_sha256": PACKAGE_SHA256,
        "composite_source_ledger_sha256": {
            "R1_R2": digest(RECOVERY1 / "ledger.jsonl"),
            "R3_original": digest(REPLICATE3 / "ledger.jsonl"),
            "B_S5_R3_targeted_replacement": digest(AMENDMENT / "ledger.jsonl"),
        },
    })

    # Independently recompute each FPR replicate using the evaluator-only contract.
    fpr_accounting = []
    completed = [run for run in runs if run["status"] == "completed"]
    for condition in ("A", "B"):
        for replicate in (1, 2, 3):
            summaries = [run["analysis_summary"] for run in completed
                         if run["condition_id"] == condition and run["replicate"] == replicate
                         and run["scenario_id"] in {"S10", "S11", "S12"}]
            experiment_ids = {summary["context"]["experiment_id"] for summary in summaries}
            require(len(experiment_ids) == 1,
                    "A negative-scenario FPR group mixes experiment identities.")
            evaluator_row = summarize_fpr_replicate(
                summaries, experiment_id=next(iter(experiment_ids)),
                condition_id=condition, replicate=replicate)
            aggregate_row = next(row for row in metrics["fpr"]["condition_replicates"]
                                 if row["condition_id"] == condition
                                 and row["replicate"] == replicate)
            require(evaluator_row["primary_fpr"] == aggregate_row["fpr"]
                    and evaluator_row["FP"] == aggregate_row["FP"]
                    and evaluator_row["TN"] == aggregate_row["TN"],
                    "Independent evaluator and aggregate FPR results disagree.")
            fpr_accounting.append(evaluator_row)
    metrics["fpr"]["independent_evaluator_crosscheck"] = fpr_accounting
    fpr_blocker = inspect_fpr_blocker()
    metrics["fpr"]["withheld_replicate_detail"] = fpr_blocker

    annotation_keys = {(item["unit_id"], item["candidate_id"])
                       for item in imported["annotations"]}
    eligible_keys = {(run["unit_id"], candidate["candidate_id"])
                     for run in runs if run["status"] == "completed"
                     for candidate in run["candidates"]}
    require(annotation_keys == eligible_keys and len(eligible_keys) == 990,
            "Imported VAL-01 annotations do not map one-to-one to the final candidate cohort.")

    write_new(imported_path, imported)
    columns, rows = csv_rows(metrics)
    with csv_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with metrics_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(metrics, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")

    audit = {
        "schema": "poolside-laguna-p4-val01-metric-audit-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": ("all_primary_metrics_eligible"
                   if metrics["psr"]["eligible"] and metrics["fpr"]["eligible"]
                   else "partial_metric_eligibility"
                   if metrics["psr"]["eligible"] or metrics["fpr"]["eligible"]
                   else "metrics_withheld_for_incomplete_eligibility"),
        "cohort_units": len(runs),
        "completed_metric_eligible_units": len(completed),
        "design_excluded_units": sum(run["status"] == "excluded" for run in runs),
        "candidate_annotations": len(imported["annotations"]),
        "annotation_decision_counts": dict(labels),
        "annotation_source_sha256": source_sha,
        "review_package_sha256": PACKAGE_SHA256,
        "annotation_import_verified": True,
        "annotation_candidate_mapping_one_to_one": True,
        "psr_eligible": metrics["psr"]["eligible"],
        "fpr_eligible": metrics["fpr"]["eligible"],
        "fpr_independent_evaluator_crosscheck": True,
        "fpr_withheld_replicate_detail": fpr_blocker,
        "psr_summary": metrics["psr"]["summary"],
        "fpr_summary": metrics["fpr"]["summary"],
        "system_confusion_by_replicate": metrics["system_confusion"]["condition_replicates"],
        "output_sha256": {
            "imported_annotations": digest(imported_path),
            "metrics_json": digest(metrics_path),
            "metrics_csv": digest(csv_path),
        },
        "api_requests": 0,
        "dvwa_requests": 0,
        "database_resets": 0,
    }
    write_new(audit_path, audit)
    return audit


if __name__ == "__main__":
    result = prepare()
    print(json.dumps({
        "status": result["status"],
        "annotations": result["candidate_annotations"],
        "decision_counts": result["annotation_decision_counts"],
        "psr_eligible": result["psr_eligible"],
        "psr_summary": result["psr_summary"],
        "fpr_eligible": result["fpr_eligible"],
        "fpr_summary": result["fpr_summary"],
        "outputs": result["output_sha256"],
    }, indent=2))
