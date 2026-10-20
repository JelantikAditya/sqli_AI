"""Normalize the returned VAL-01 workbook without revising human judgments."""

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2"
EVIDENCE = PACKAGE / "returned-VAL-01-20261019"
OUTPUT = ROOT / "outputs/val01-format-20261019"
FIELDS = ["review_id", "validator_id", "decision", "justification"]
LABELS = {"BERHASIL": "success", "GAGAL": "failure"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="path to the returned VAL-01 workbook")
    source = parser.parse_args().source.expanduser().resolve()
    if not source.is_file():
        parser.error(f"source workbook does not exist: {source}")
    source_hash = digest(source)
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=False)
    data = list(workbook["Data"].iter_rows(values_only=True))
    expected = ["review_id", "technique", "method", "endpoint", "parameter",
                "anchor_id", "payload", "verdict", "detail_alasan"]
    if list(data[0]) != expected:
        raise ValueError("The source columns changed; review the mapping before conversion.")
    rows = data[1:]
    mapping = json.loads((PACKAGE / "mapping.private.json").read_text(encoding="utf-8"))
    packet_bytes = (PACKAGE / "validator/packets.json").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(packet_bytes).hexdigest() != mapping["package_sha256"]:
        raise ValueError("The original review packet failed its integrity check.")
    ids = [r[0] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(mapping["mapping"]):
        raise ValueError("Review IDs must match the v2 packet exactly once.")
    with (PACKAGE / "validator/annotations.csv").open(encoding="utf-8-sig", newline="") as f:
        expected_order = [r["review_id"] for r in csv.DictReader(f)]
    by_id = {}
    for row_number, row in enumerate(rows, start=2):
        if row[7] not in LABELS:
            raise ValueError(f"Unrecognized verdict at Data row {row_number}.")
        if not isinstance(row[8], str) or not row[8].strip():
            raise ValueError(f"Missing justification at Data row {row_number}.")
        # Retain the validator's complete reason verbatim, including any issues.
        by_id[row[0]] = dict(zip(FIELDS, [row[0], "VAL-01", LABELS[row[7]], row[8]]))
    annotations = [by_id[review_id] for review_id in expected_order]
    OUTPUT.mkdir(parents=True, exist_ok=False)
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    original = EVIDENCE / "evaluasi_pentest_sqli_llm.original.xlsx"
    shutil.copyfile(source, original)
    output_csv = OUTPUT / "annotations_VAL-01.csv"
    with output_csv.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(annotations)
    # This intermediate also records provenance for the workbook authoring step.
    audit = {
        "scope": "format-normalization-only",
        "source": source.name,
        "source_sha256": source_hash,
        "archived_source": original.relative_to(ROOT).as_posix(),
        "package": str(PACKAGE),
        "package_sha256": mapping["package_sha256"],
        "validator_id_basis": "User attributed the supplied workbook to VAL-01.",
        "source_sheet": "Data",
        "row_count": len(annotations),
        "decision_counts": dict(Counter(r["decision"] for r in annotations)),
        "field_mapping": {"review_id": "review_id", "validator_id": "VAL-01",
                          "verdict": "decision", "detail_alasan": "justification"},
        "label_mapping": LABELS,
        "source_order_matches_packet": ids == expected_order,
        "justifications_preserved_verbatim": True,
        "methodology_review": {
            "status": "requires_validator_confirmation_before_final_metrics",
            "issue": "Source time-based reasons cite 1200 ms; packet instructions require 1500 ms.",
            "affected_review_ids": [r[0] for r in rows if r[1] == "time-based blind" and "1200ms" in r[8]],
            "ratings_changed": False,
        },
        "csv": output_csv.relative_to(ROOT).as_posix(),
        "csv_sha256": digest(output_csv),
        "source_unchanged": digest(source) == source_hash == digest(original),
    }
    (EVIDENCE / "normalization.audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (EVIDENCE / "annotations.normalized.json").write_text(
        json.dumps({"fields": FIELDS, "rows": annotations}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(annotations), "counts": audit["decision_counts"],
                      "all_ids_match_v2": True, "reasons_preserved": True,
                      "source_unchanged": audit["source_unchanged"],
                      "csv": output_csv.relative_to(ROOT).as_posix(),
                      "methodology_flags": len(audit["methodology_review"]["affected_review_ids"])}))


if __name__ == "__main__":
    main()
