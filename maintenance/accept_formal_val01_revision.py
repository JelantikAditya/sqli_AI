"""Archive and ingest supplied human annotations using the frozen metric functions."""

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from aggregate_metrics import aggregate, csv_rows
from analyze_response import positive_evidence_groups
from blind_review import import_annotations
from experiment_dataset import load_runs

PACKAGE = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2"
EXPERIMENT = ROOT / "results/raw/formal/formal-sqli-v1-20261017"
INITIAL_CSV = ROOT / "outputs/val01-format-20261019/annotations_VAL-01.csv"
FIELDS = ["review_id", "validator_id", "decision", "justification"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, document):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def accept(source, output):
    source, output = source.resolve(), output.resolve()
    require(output.is_relative_to(PACKAGE) and not output.exists(), "Use a new return directory in the review package.")
    original_hash = digest(source)
    inventory = json.loads((PACKAGE / "source-inventory.private.json").read_text(encoding="utf-8"))
    require(all(digest(ROOT / name) == value for name, value in inventory.items()), "A protected experiment source changed.")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        supplied = list(reader)
        require(reader.fieldnames == FIELDS, "Unexpected annotation columns.")
    require(all(set(row) == set(FIELDS) and all(v is not None for v in row.values()) for row in supplied),
            "CSV contains missing or extra fields.")
    # The user attributes this source to VAL-01. Preserve their judgments verbatim.
    imported = import_annotations(PACKAGE, source, "VAL-01")
    require(len(imported["annotations"]) == 990, "Expected all 990 independent annotations.")
    with INITIAL_CSV.open(encoding="utf-8-sig", newline="") as stream:
        initial = {row["review_id"]: row for row in csv.DictReader(stream)}
    packets = json.loads((PACKAGE / "validator/packets.json").read_text(encoding="utf-8"))["packets"]
    packet_by_id = {packet["review_id"]: packet for packet in packets}
    changes = [{"review_id": row["review_id"], "technique": packet_by_id[row["review_id"]]["technique"],
                "old_decision": initial[row["review_id"]]["decision"], "new_decision": row["decision"],
                "old_justification": initial[row["review_id"]]["justification"],
                "new_justification": row["justification"]}
               for row in supplied if initial[row["review_id"]]["decision"] != row["decision"]]

    # Corroboration is an audit, not replacement or generation of human decisions.
    trial_audit = []
    for annotation in supplied:
        packet = packet_by_id[annotation["review_id"]]
        document = {"technique": packet["technique"], "runtime_status": "valid", "baseline_valid": True,
                    "time_threshold_ms": 1500, "observations": [
                        {**o, "role": "candidate" if o["role"] == "single" else o["role"],
                         "observation_id": f'{o["trial"]}:{o["role"]}'} for o in packet["observations"]]}
        positives = len(positive_evidence_groups(document))
        stated = re.findall(r"Indikator terpenuhi ([0-3])/3", annotation["justification"])
        require(stated == [str(positives)], "A justification trial count differs from packet evidence.")
        require((annotation["decision"] == "success") == (positives == 3), "Human decision needs separate adjudication.")
        if packet["technique"] == "time-based blind":
            cited = re.findall(r"Trial ([123]): delta=single (-?\d+(?:\.\d+)?) - no_delay_control (-?\d+(?:\.\d+)?) = (-?\d+(?:\.\d+)?) ms \((>=|<)1500 ms\)", annotation["justification"])
            require(len(cited) == 3 and {c[0] for c in cited} == {"1", "2", "3"}, "Time justification lacks three matched deltas.")
            for trial, single, control, delta, comparison in cited:
                pair = {o["role"]: o for o in packet["observations"] if o["trial"] == int(trial)}
                measured_single, measured_control = pair["single"]["elapsed_ms"], pair["no_delay_control"]["elapsed_ms"]
                measured_delta = measured_single - measured_control
                require(math.isclose(float(single), measured_single, abs_tol=1e-8)
                        and math.isclose(float(control), measured_control, abs_tol=1e-8)
                        and math.isclose(float(delta), measured_delta, abs_tol=0.005001)
                        and (comparison == ">=") == (measured_delta >= 1500), "A cited timing calculation differs from its trial.")
        trial_audit.append({"review_id": annotation["review_id"], "positive_trials": positives,
                            "decision": annotation["decision"], "trial_count_matches": True})

    runs = load_runs(EXPERIMENT)
    require(Counter(run["status"] for run in runs) == {"completed": 99, "excluded": 9}, "Incomplete formal dataset.")
    amap = {(a["unit_id"], a["candidate_id"]): a for a in imported["annotations"]}
    disagreements = [amap[(run["unit_id"], c["candidate_id"])]["review_id"]
                     for run in runs for c in run.get("candidates", [])
                     if (amap[(run["unit_id"], c["candidate_id"])]["decision"] == "success")
                     != (c["confirmed_success"] is True and c["evidence_status"] == "CONSISTENT_POSITIVE")]
    require(not disagreements, "Human/executor differences require a separate adjudication record.")
    report = aggregate(runs, imported["annotations"], experiment_id="formal-sqli-v1-20261017")
    require(report["annotations_complete"] and report["psr"]["eligible"], "PSR annotations are incomplete.")
    pending = json.loads((PACKAGE / "metrics.pending-review.json").read_text(encoding="utf-8"))
    require(all(report["fpr"][key] == pending["fpr"][key] for key in ("eligible", "condition_replicates", "summary")),
            "Human review must not change stored-system FPR.")
    # Independently reconcile the per-replicate counts and sample-SD summaries.
    for row in report["psr"]["condition_replicates"]:
        annotations = [a for a in imported["annotations"] if a["condition_id"] == row["condition_id"]
                       and a["replicate"] == row["replicate"] and a["scenario_id"] in {f"S{i}" for i in range(1, 10)}]
        successes = sum(a["decision"] == "success" for a in annotations)
        require(len(annotations) == row["valid_candidates"] == 90 and successes == row["success_count"]
                and math.isclose(successes / 90, row["psr"]), "PSR count reconciliation failed.")
    for row in report["psr"]["summary"]:
        values = [r["psr"] for r in report["psr"]["condition_replicates"] if r["condition_id"] == row["condition_id"]]
        require(math.isclose(statistics.mean(values), row["mean"]) and math.isclose(statistics.stdev(values), row["sample_sd"]),
                "PSR mean/sample SD reconciliation failed.")

    output.mkdir(parents=True, exist_ok=False)
    archived = output / "annotations.as-received.csv"
    shutil.copyfile(source, archived)
    report.update(validator_id="VAL-01", source_ledger_sha256=digest(EXPERIMENT / "ledger.jsonl"),
                  annotation_record_count=990, annotation_source_sha256=original_hash,
                  review_package_sha256=imported["annotations"][0]["package_sha256"])
    write_json(output / "annotations.imported.json", imported)
    write_json(output / "metrics.reviewed.json", report)
    columns, rows = csv_rows(report)
    with (output / "metrics.reviewed.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "annotation-revisions.private.json", {"scope": "initial-versus-latest-human-review", "changes": changes})
    write_json(output / "trial-corroboration.private.json", {"scope": "audit-only-no-human-label-replacement", "rows": trial_audit})
    require(digest(source) == digest(archived) == original_hash, "The source CSV changed.")
    require(all(digest(ROOT / name) == value for name, value in inventory.items()), "A protected source changed during review.")
    receipt = {"scope": "formal-review-ingestion-receipt", "created_at": datetime.now(timezone.utc).isoformat(),
               "validator_id": "VAL-01", "validator_attribution": "User supplied this file as the latest VAL-01 assessment.",
               "source": str(source), "source_sha256": original_hash, "archived_source": str(archived),
               "previous_normalized_csv": str(INITIAL_CSV), "previous_normalized_csv_sha256": digest(INITIAL_CSV),
               "package_sha256": report["review_package_sha256"], "annotation_count": 990,
               "decision_counts": dict(Counter(a["decision"] for a in supplied)),
               "decisions_by_technique": {t: dict(Counter(a["decision"] for a in supplied
                   if packet_by_id[a["review_id"]]["technique"] == t)) for t in sorted({p["technique"] for p in packets})},
               "decision_change_count": len(changes), "decision_changes_by_technique": dict(Counter(c["technique"] for c in changes)),
               "transitions": dict(Counter(c["old_decision"] + "->" + c["new_decision"] for c in changes)),
               "justifications_changed": sum(a["justification"] != initial[a["review_id"]]["justification"] for a in supplied),
               "human_executor_disagreements": disagreements, "matched_time_calculations_verified": 990,
               "trial_count_statements_verified": len(trial_audit), "protected_sources_verified": len(inventory),
               "source_preservation": "all_hashes_unchanged_before_and_after", "psr_eligible": report["psr"]["eligible"],
               "fpr_eligible": report["fpr"]["eligible"], "fpr_unchanged_by_review": True,
               "raw_experiments_rerun": False,
               "outputs": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    write_json(output / "acceptance.audit.private.json", receipt)
    print(json.dumps({"output": str(output), "annotations": receipt["decision_counts"],
                      "changed_decisions": len(changes), "psr_replicates": report["psr"]["condition_replicates"],
                      "psr_summary": report["psr"]["summary"], "fpr_eligible": report["fpr"]["eligible"],
                      "protected_sources_verified": len(inventory)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    accept(args.source, args.output_dir)
