"""Reproduce the locked r2 pilot results from saved responses without model calls."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))

import analysis_v5_pilot_rev2 as pilot

OUT = ROOT / "results/processed/analysis-v5-pilot-r2-execution-20261020"


def audit():
    cases, labels, requests, request_audit = pilot.verify()
    schedule = pilot.read(pilot.OUT / "schedule.lock.json")
    raw_path = pilot.RAW / "events.jsonl"
    events = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    recorded = pilot.read(pilot.RAW / "summary.json")
    reproduced = pilot.summarize(cases, labels, schedule, events)
    if {key: value for key, value in recorded.items() if key not in ("session_status", "events_sha256")} != reproduced:
        raise ValueError("Saved summary does not reproduce from its events.")
    if recorded["events_sha256"] != pilot.digest(raw_path):
        raise ValueError("Event bytes differ from the runtime summary.")

    adoption = pilot.read(OUT / "researcher-adoption.json")
    for field, path in (("manifest_sha256", pilot.OUT / "manifest.lock.json"),
                        ("protocol_sha256", pilot.OUT / "protocol.lock.json"),
                        ("explanation_sha256", pilot.GUIDE),
                        ("input_sha256", pilot.OUT / "inputs.lock.json"),
                        ("labels_sha256", pilot.OUT / "labels.ai.lock.json"),
                        ("corpus_sha256", pilot.rag.checker.CORPUS)):
        if adoption[field] != pilot.digest(path):
            raise ValueError(f"Researcher adoption no longer binds to {field}.")

    docs = {row["case_id"]: row["input"] for row in cases}
    truth = {row["case_id"]: row for row in labels["cases"]}
    planned = {slot["slot_id"]: slot for slot in schedule}
    request_map = {(r["case_id"], r["profile"]): r["request"] for r in requests}
    token_map = {(r["case_id"], r["profile"]): r["prompt_tokens"] for r in request_audit}
    starts, responses, finished = {}, {}, {}
    visited, skips = [], []
    for event in events:
        sid = event["slot_id"]
        slot = planned[sid]
        if any(event[key] != value for key, value in slot.items()):
            raise ValueError("Event has inconsistent scheduled identity.")
        cid, profile = slot["case_id"], slot["profile"]
        if event["event"] == "skipped":
            if pilot.dataset.eligible(docs[cid]) or event["attempted"] is not False:
                raise ValueError("An eligible slot was skipped or invalid slot was attempted.")
            skips.append(sid)
            visited.append(sid)
        elif event["event"] == "attempt_started":
            if sid in starts or not pilot.dataset.eligible(docs[cid]):
                raise ValueError("Retry or invalid input reached model execution.")
            if event["request_sha256"] != pilot.rag.sha(request_map[(cid, profile)]):
                raise ValueError("Started attempt did not use its locked request.")
            starts[sid] = event
            visited.append(sid)
        elif event["event"] == "response_received":
            if sid not in starts or sid in responses or sid in finished:
                raise ValueError("Unexpected or duplicate model response.")
            responses[sid] = event["response"]
        elif event["event"] == "finished":
            if sid not in starts or sid in finished:
                raise ValueError("Unstarted or duplicate finish event.")
            if sid in responses:
                parsed = pilot.parse_output(docs[cid], request_map[(cid, profile)], responses[sid], token_map[(cid, profile)])
                if any(event.get(key) != value for key, value in parsed.items()):
                    raise ValueError("Recorded parse/audit does not reproduce from raw model response.")
            elif event.get("error") != "transport-error":
                raise ValueError("Finished attempt lacks its raw response.")
            finished[sid] = event
        else:
            raise ValueError("Unknown event type.")
    if visited != [slot["slot_id"] for slot in schedule[:len(visited)]]:
        raise ValueError("Execution order differs from the locked balanced schedule.")
    if recorded["session_status"] == "completed" and (len(visited) != len(schedule) or len(finished) != len(starts)):
        raise ValueError("A completed session lacks scheduled or finalized slots.")

    rows = []
    for slot in schedule:
        cid, profile, sid = slot["case_id"], slot["profile"], slot["slot_id"]
        reference = truth[cid]
        if sid in skips:
            status, decision, record = "input_invalid", None, {}
        elif sid not in starts:
            status, decision, record = "unattempted", None, {}
        else:
            record = finished.get(sid, {"status": "analysis_error", "error": "interrupted-attempt"})
            status, decision = record["status"], record.get("decision")
        expected = reference["trial_assessments"]
        trial_correct = sum(status == "ok" and len(actual) == 1 and actual[0]["outcome"] == trial["outcome"]
                            for trial in expected
                            for actual in [[row for row in record.get("trial_assessments", []) if row["trial"] == trial["trial"]]])
        rows.append({**slot, "technique": docs[cid]["technique"],
            "reference": reference["decision"] or "input_invalid", "status": status,
            "raw_decision": decision, "correct": status == "ok" and decision == reference["decision"],
            "reason_code": (record.get("model_output") or {}).get("reason_code"),
            "error": record.get("error"), "trial_correct": trial_correct,
            "trial_denominator": len(expected) if sid in starts else 0,
            "warnings": record.get("warnings", []), "elapsed_seconds": record.get("elapsed_seconds"),
            "prompt_tokens": record.get("runtime_metrics", {}).get("prompt_eval_count"),
            "generated_tokens": record.get("runtime_metrics", {}).get("eval_count"),
            "done_reason": record.get("runtime_metrics", {}).get("done_reason")})

    by_technique = {}
    for profile in pilot.PROFILES:
        by_technique[profile] = {}
        for technique in pilot.rag.TECHNIQUES:
            subset = [r for r in rows if r["profile"] == profile and r["technique"] == technique
                      and r["status"] in ("ok", "analysis_error")]
            n = len(subset)
            correct = sum(r["correct"] for r in subset)
            by_technique[profile][technique] = {"attempted": n, "correct": correct,
                "accuracy": correct / n if n else None,
                "analysis_errors": sum(r["status"] == "analysis_error" for r in subset),
                "wrong_positive_claims_on_negative_reference": sum(r["reference"] == "negative" and r["raw_decision"] == "positive" for r in subset),
                "trial_correct": sum(r["trial_correct"] for r in subset),
                "trial_denominator": sum(r["trial_denominator"] for r in subset)}

    preserved = pilot.read(pilot.OUT / "preservation.lock.json")
    manifest = pilot.read(pilot.OUT / "manifest.lock.json")
    result = {"scope": "synthetic-development-only", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary_reproduces": True, "parses_reproduced_from_raw_responses": len(responses),
        "attempted_slots": len(starts), "finalized_slots": len(finished), "skipped_invalid_slots": len(skips),
        "execution_order_matches_lock": True, "retry_count": 0,
        "protected_files_unchanged": len(preserved),
        "source_pins_checked": len(manifest["source_sha256"]),
        "artifact_pins_checked": len(manifest["artifact_sha256"]),
        "researcher_adoption_receipt_matches": True,
        "warning_counts": dict(Counter(w for row in rows for w in row["warnings"])),
        "formal_FPR_PSR_recomputed": False, "model_calls_during_audit": 0, "dvwa_requests_during_audit": 0}
    return recorded, result, rows, by_technique


def export(summary, result, rows, by_technique):
    paths = [OUT / name for name in ("summary.json", "audit.json", "case-results.csv", "by-technique.json", "provenance.json", "README.md")]
    if any(path.exists() for path in paths):
        raise ValueError("Export exists; preserve published results instead of overwriting them.")
    pilot.write_new(OUT / "summary.json", summary)
    pilot.write_new(OUT / "audit.json", result)
    pilot.write_new(OUT / "by-technique.json", by_technique)
    with (OUT / "case-results.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row, "warnings": "|".join(row["warnings"])} for row in rows)
    lines = ["# Hasil pilot analisis v5 r2", "",
        "Peneliti menyetujui penjelasan r2 dan kelanjutan pilot melalui pesan langsung sebelum inferensi.",
        "Receipt adopsi disimpan terpisah; metadata pending pada paket lock adalah snapshot saat freeze.",
        "Kasus sintetis buatan AI; persetujuan bukan gold manusia independen atau bukti manfaat RAG formal.", "",
        "| Profil | Benar / dicoba | Akurasi | Error | Trial benar / tersedia | Reason accuracy | Reason consistency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for profile in pilot.PROFILES:
        row = summary["profiles"][profile]
        def pct(value):
            return f"{100*value:.2f}%" if value is not None else "undefined"
        lines.append(f"| {profile} | {row['raw_correct']}/{row['attempted_eligible']} | {pct(row['raw_accuracy'])} | {row['analysis_errors']} | {row['trial_correct']}/{row['trial_denominator']} | {pct(row['reason_code_accuracy'])} | {pct(row['reason_code_consistency'])} |")
    primary = summary["primary"]
    lines += ["", f"Status sesi: {summary['session_status']}. Kesimpulan prespecified: {primary['conclusion']}.",
        f"Delta akurasi A/B3 (B3 dikurangi A), poin persentase: {primary['paired_accuracy_difference_percentage_points']}.",
        "", "Transisi pasangan A/B3:", ""]
    for name, transition in primary["paired_correctness_transitions"].items():
        lines.append(f"- {name}: {transition['count']}; ID: {', '.join(transition['case_ids']) or 'tidak ada'}.")
    lines += ["", "B2 pembanding deskriptif; B3 memuat seluruh tiga chunk eligible per teknik.",
        "Hasil A/B3 tidak mengisolasi manfaat selektivitas ranking retrieval.",
        "Tidak ada perubahan hasil formal R1/R2/R3 atau FPR/PSR formal.", "",
        "Reproduksi audit tanpa model atau DVWA:", "", "```powershell",
        ".\\.venv\\Scripts\\python.exe maintenance/audit_analysis_v5_pilot_rev2.py", "```", ""]
    with (OUT / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    provenance = {"pilot_id": pilot.OUT.name, "scope": "synthetic-development-only",
        "files": {path.relative_to(ROOT).as_posix(): pilot.digest(path) for path in
                  [Path(__file__), pilot.OUT / "manifest.lock.json", pilot.OUT / "protocol.lock.json",
                   pilot.RAW / "runtime-before.json", pilot.RAW / "events.jsonl", pilot.RAW / "summary.json",
                   OUT / "researcher-adoption.json", *[p for p in paths if p.name != "provenance.json"]]}}
    pilot.write_new(OUT / "provenance.json", provenance)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    summary, result, rows, by_technique = audit()
    if args.export:
        export(summary, result, rows, by_technique)
    print(json.dumps(result))
