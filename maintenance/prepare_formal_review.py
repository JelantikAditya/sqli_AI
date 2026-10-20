"""Prepare F02 artifacts offline while preserving the completed formal dataset."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from aggregate_metrics import aggregate, csv_rows
from blind_review import export_runs, import_annotations
from experiment_dataset import load_runs
from rag_pipeline import load_catalog
from run_decision_evaluator import summarize_fpr_replicate


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def inventory(paths):
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def prepare(directory, output):
    directory = Path(directory).resolve()
    output = Path(output).resolve()
    raw_root = (ROOT / "results/raw").resolve()
    require(directory.is_relative_to(raw_root / "formal"), "Use a formal experiment directory.")
    require(output.is_relative_to(raw_root) and not output.exists(), "Use a new results/raw output directory.")
    require(not output.is_relative_to(directory), "Keep derived review artifacts outside the source dataset.")
    protocol_path = ROOT / "dvwa/local_experiment_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    require(protocol["status"] == "frozen", "Formal review requires the frozen protocol.")
    source_files = [p for p in directory.rglob("*") if p.is_file()]
    source_files += [protocol_path, ROOT / "dvwa/experiment_scenarios.json",
                     ROOT / "dvwa/aggregate_metrics.py", ROOT / "dvwa/blind_review.py",
                     ROOT / "dvwa/experiment_dataset.py", ROOT / "dvwa/run_decision_evaluator.py",
                     ROOT / "docs/prosedur-validator-u04.md", Path(__file__).resolve()]
    before = inventory(source_files)
    events = [json.loads(line) for line in (directory / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    experiment_id = events[0]["experiment_id"]
    # The official loader checks final attempt selection and evidence/analysis hashes.
    runs = load_runs(directory)
    completed = [r for r in runs if r["status"] == "completed"]
    expected_counts = {"completed": 99, "excluded": 9}
    require(dict(Counter(r["status"] for r in runs)) == expected_counts, "Formal dataset is incomplete.")
    require(all(r["metric_eligible"] and len(r["candidates"]) == 10 for r in completed),
            "Each final completed run must have ten eligible candidates.")
    catalog = {s["scenario_id"]: s for s in load_catalog()["scenarios"]}
    for rep in (1, 2, 3):
        actual = Counter(r["condition_id"] for r in completed if r["replicate"] == rep)
        require(actual == {"A": 12, "B": 12, "C": 9}, "Replicate coverage differs from the formal plan.")
    for run in runs:
        if run["status"] == "excluded":
            require(run["condition_id"] == "C" and run["scenario_id"] in {"S10", "S11", "S12"},
                    "Unexpected exclusion in the final dataset.")
            continue
        kind = catalog[run["scenario_id"]]["probe_kind"]
        roles = {"baseline", "single"} if kind == "single_error" else (
            {"baseline", "true_condition", "false_condition"} if kind == "boolean_pair"
            else {"baseline", "single", "no_delay_control"})
        expected = Counter((trial, role) for trial in (1, 2, 3) for role in roles)
        for candidate in run["candidates"]:
            actual = Counter((o["confirmation_index"], o["payload_role"]) for o in candidate["observations"])
            require(actual == expected, "A candidate lacks the expected three complete confirmation groups.")

    # Verify preservation of R1/R2 independently of the current checkpoint.
    amendment_path = directory / "runner-amendment-b-index-v1/runner-amendment.json"
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    history = amendment["preserved_history"]
    ledger_bytes = (directory / "ledger.jsonl").read_bytes()
    prefix = hashlib.sha256(ledger_bytes[:history["ledger_prefix_bytes"]]).hexdigest()
    require(prefix == history["ledger_prefix_sha256"], "Historical ledger prefix changed.")
    historical_files = json.loads((ROOT / history["inventory_path"]).read_text(encoding="utf-8"))["files"]
    protected = {name: value for name, value in historical_files.items()
                 if "/attempts/" in name and any(f"-r{rep}/" in name for rep in (1, 2))}
    require(protected and all(digest(ROOT / name) == value for name, value in protected.items()),
            "Historical R1/R2 attempt artifacts changed.")
    require(all(e.get("replicate") not in (1, 2) for e in events[history["ledger_event_count"]:]
                if e["event_type"].startswith("attempt_")), "R1/R2 were re-executed after the amendment.")

    output.parent.mkdir(parents=True, exist_ok=True)
    exported = export_runs(runs, output)
    public = output / "validator"
    package = json.loads((public / "packets.json").read_text(encoding="utf-8"))
    packets = package["packets"]
    mapping = json.loads((output / "mapping.private.json").read_text(encoding="utf-8"))["mapping"]
    require(len(packets) == len(mapping) == 990, "Expected 990 blinded candidate packets.")
    require(all(set(p) == {"review_id", "technique", "injection_point", "candidate", "observations"}
                for p in packets), "Unexpected public packet fields.")
    require(all(o.get("review_excerpt") for p in packets for o in p["observations"]),
            "At least one observation lacks review evidence.")
    public_text = (public / "packets.json").read_text(encoding="utf-8")
    for field in ("condition_id", "rag_mode", "payload_source", "ground_truth", "system_decision",
                  "confirmed_success", "evidence_status", "run_id", "attempt_id", "unit_id", "scenario_id"):
        require(f'"{field}"' not in public_text, "A private label leaked into the public packets.")
    with (public / "annotations.csv").open(encoding="utf-8", newline="") as stream:
        annotation_rows = list(csv.DictReader(stream))
    require(len(annotation_rows) == 990 and all(not r["decision"] and not r["justification"]
                                              and not r["validator_id"] for r in annotation_rows),
            "Annotation decisions must remain blank for the independent validator.")
    try:
        import_annotations(output, public / "annotations.csv", "VAL-01")
    except ValueError as exc:
        require("Every decision requires" in str(exc), "Unexpected importer rejection: " + str(exc))
    else:
        raise ValueError("The importer incorrectly accepted uncompleted annotations.")

    # An empty annotation list keeps PSR undefined; it is never labelled human review.
    report = aggregate(runs, [], experiment_id=experiment_id)
    report.update(scope="formal-metric-readiness-pending-independent-review",
                  annotations_status="pending", validator_id=None, annotation_record_count=0,
                  intended_validator_alias="VAL-01", source_ledger_sha256=digest(directory / "ledger.jsonl"),
                  review_package_sha256=exported["package_sha256"])
    require(not report["psr"]["eligible"], "PSR must be withheld before independent annotation.")
    accounting = []
    for condition in ("A", "B"):
        for rep in (1, 2, 3):
            summaries = [r["analysis_summary"] for r in completed if r["condition_id"] == condition
                         and r["replicate"] == rep and r["scenario_id"] in {"S10", "S11", "S12"}]
            row = summarize_fpr_replicate(summaries, experiment_id=experiment_id,
                                         condition_id=condition, replicate=rep)
            expected = next(r for r in report["fpr"]["condition_replicates"]
                            if r["condition_id"] == condition and r["replicate"] == rep)
            require(row["primary_fpr"] == expected["fpr"] and row["FP"] == expected["FP"]
                    and row["TN"] == expected["TN"], "FPR evaluator and aggregator disagree.")
            accounting.append(row)
    report["fpr"]["abstention_accounting"] = accounting
    write_json(output / "metrics.pending-review.json", report)
    columns, rows = csv_rows(report)
    with (output / "metrics.pending-review.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with (output / "negative-run-audit.csv").open("x", encoding="utf-8", newline="") as stream:
        columns = ["unit_id", "condition_id", "scenario_id", "replicate", "system_decision",
                   "binary_decision_eligible", "execution_status", "analysis_completed_count",
                   "expected_budget", "attempt_id", "run_id"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for run in completed:
            if run["condition_id"] in {"A", "B"} and run["scenario_id"] in {"S10", "S11", "S12"}:
                summary = run["analysis_summary"]
                row = {k: run[k] for k in columns if k in run}
                row.update({k: summary[k] for k in
                            ("system_decision", "binary_decision_eligible", "execution_status",
                             "analysis_completed_count", "expected_budget")})
                writer.writerow(row)

    guide = """# Petunjuk review bukti SQL injection

Paket formal ini berisi 990 kandidat dengan ID acak. Penilaian dilakukan oleh
validator independen beralias VAL-01. Lengkapi annotations.csv menggunakan
packets.json. Pertahankan review_id, urutan baris, dan nama kolom.

Isi validator_id dengan VAL-01, decision dengan success, failure, atau
insufficient_evidence, dan justification dengan alasan berdasarkan observasi.
Sebutkan trial serta pasangan kontrol yang mendukung keputusan. Nilai keputusan
dan alasan sengaja kosong sampai validator melakukan review.

Setiap kandidat memiliki tiga trial lengkap. Error-based memakai baseline dan
single; boolean memakai baseline, true_condition, false_condition; time-based
memakai baseline, single, no_delay_control. Selisih waktu adalah waktu single
dikurangi no_delay_control pada trial yang sama, dengan ambang 1500 ms.

Success memerlukan pola yang konsisten pada ketiga trial: diagnostik database
baru terhadap baseline untuk error-based, respons true/false yang sesuai untuk
boolean, atau delay terhadap kontrol yang cocok dan respons valid untuk time.
Perbedaan hash atau HTTP status saja tidak membuktikan SQL injection. Pada
boolean, respons missing dapat memakai 404 bila marker yang sesuai tercatat.
Pada time-based, kedua respons harus valid dengan signature konten yang sama
serta tanpa diagnostik SQL. Bila bukti lengkap tetapi pola keberhasilan tidak
terpenuhi, pilih failure. Bila bukti yang disajikan belum cukup untuk menilai,
pilih insufficient_evidence dan jelaskan bagian yang tidak cukup.

review_excerpt adalah frasa allowlist yang dinormalisasi, bukan body HTML asli.
review_excerpt_basis menjelaskan asal cuplikan. Nilai record dan rincian query
disamarkan. Jangan menebak sumber kandidat, kondisi, atau hasil yang diharapkan.
Sampaikan pertanyaan format secara seragam melalui peneliti tanpa meminta label.

Kembalikan seluruh 990 baris yang sudah diisi. Pertahankan anotasi awal bila
ada perbedaan pendapat; adjudikasi dicatat terpisah. Simpan salinan pekerjaan
secara berkala. Paket ini tidak perlu menjalankan ulang aplikasi atau payload.
"""
    (public / "PETUNJUK.md").write_text(guide, encoding="utf-8", newline="\n")
    # Only blinded public files enter the handoff archive.
    archive = output / "paket-validator.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(public.iterdir()):
            bundle.write(path, arcname=path.name)
    with zipfile.ZipFile(archive) as bundle:
        require(set(bundle.namelist()) == {"PETUNJUK.md", "packets.json", "annotations.csv"},
                "The validator archive includes unexpected files.")

    receipts = [e["condition_b_index_preflight"] for e in events
                if e["event_type"] == "attempt_completed" and e.get("replicate") == 3
                and e.get("condition_id") == "B"]
    require(len(receipts) == 12 and all(digest(ROOT / r["receipt_path"]) == r["receipt_sha256"]
                                      for r in receipts), "B preflight receipt integrity failed.")
    after = inventory(source_files)
    require(before == after, "Source artifacts changed while preparing review.")
    write_json(output / "source-inventory.private.json", before)
    unit_replicates = {r["unit_id"]: r["replicate"] for r in runs}
    audit = {
        "scope": "formal-post-execution-audit", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id, "source_ledger_sha256": digest(directory / "ledger.jsonl"),
        "event_count": len(events), "status_counts": dict(Counter(r["status"] for r in runs)),
        "completed_candidates": sum(len(r["candidates"]) for r in completed),
        "observation_count": sum(len(c["observations"]) for r in completed for c in r["candidates"]),
        "historical_invalid_attempts_by_replicate": dict(Counter(
            str(unit_replicates[e["unit_id"]]) for e in events if e["event_type"] == "attempt_invalid")),
        "historical_invalid_attempt_total": sum(e["event_type"] == "attempt_invalid" for e in events),
        "review_readiness": "ready_for_independent_formal_review",
        "exporter_readiness_label": package["review_readiness"],
        "review_candidates": len(packets), "psr_required_candidates": 540,
        "annotations_completed": 0, "psr_eligible": report["psr"]["eligible"],
        "fpr_eligible": report["fpr"]["eligible"], "fpr_abstention_accounting": accounting,
        "source_preserved": before == after, "source_files_checked": len(before),
        "r1r2_ledger_prefix_preserved": True, "r1r2_attempt_files_preserved": len(protected),
        "r1r2_reexecuted": False, "b_r3_receipts_verified": len(receipts),
        "public_fields_checked": True, "excerpts_complete": True,
        "blank_annotations_rejected": True, "archive_contains_only_public_files": True,
        "package_sha256": exported["package_sha256"], "validator_zip_sha256": digest(archive),
        "preparation_http_requests": 0, "preparation_model_calls": 0, "preparation_database_resets": 0,
        "checks_status": "passed", "f02_status": "awaiting_independent_human_annotations",
    }
    write_json(output / "audit.private.json", audit)
    write_json(output / "artifact-manifest.private.json", inventory([p for p in output.rglob("*") if p.is_file()]))
    return {"output_directory": str(output), "review_candidates": len(packets),
            "observations": audit["observation_count"], "fpr_eligible": report["fpr"]["eligible"],
            "psr_eligible": report["psr"]["eligible"], "source_preserved": True,
            "checks_status": "passed", "validator_zip": str(archive)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.experiment_dir, args.output_dir), indent=2))
