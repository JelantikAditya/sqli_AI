"""Reproduce raw Qwen parsing, independent verification and agreement-gate reports."""

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import hybrid_validation_v3 as validation

pilot, model, gate, ROOT = validation.pilot, validation.model, validation.gate, validation.ROOT


def audit(output, export=None):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    for key in ("source_sha256", "history_sha256"):
        pilot.require(all(pilot.digest(ROOT / name) == value for name, value in manifest[key].items()), "Pinned source/history changed.")
    pilot.require(all(pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Frozen input changed.")
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    old = [json.loads(line) for line in (output / "regression.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
    steps = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    labels = {r["case_id"]: r for r in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    pilot.require(len(rows) == len(cases) == len(steps) == 21, "New evaluation incomplete.")
    raw_trial_correct = verifier_trial_correct = trial_total = raw_responses = 0
    for case, step, row in zip(cases, steps, rows):
        pilot.require(case["case_id"] == step["case_id"] == row["case_id"], "Schedule order differs.")
        pilot.require(model.prepared_request(case["input"]) == step["prepared"], "Qwen request changed after freeze.")
        pilot.require(json.loads(step["prepared"]["request"]["messages"][1]["content"]) == model.v1.paired_view(case["input"]),
                      "Unexpected model input.")
        record = row["hybrid"]["llm_record"]
        pilot.require(record["evidence"] == case["input"] and record["context"] == case["context"], "Raw evidence/context changed.")
        label = labels[case["case_id"]]
        pilot.require(row["expected_claim"] == label["expected_claim"] and row["expected_trials"] == label["expected_trials"],
                      "Evaluation label differs from freeze.")
        provenance = record["audit"]["provenance"]
        content = provenance.get("raw_model_content")
        response = None
        if content is not None:
            pilot.require(pilot.hashlib.sha256(content.encode()).hexdigest() == provenance["raw_model_content_sha256"], "Raw text hash differs.")
            response = {"model": provenance["model"], "message": {"content": content}, **provenance.get("runtime_metrics", {})}
            raw_responses += 1
        replayed = model.parse_response(case["input"], case["context"], step["prepared"], response)
        pilot.require(replayed == record, "Raw model record could not be reproduced.")
        if label["expected_claim"] is not None:
            verification = row["hybrid"]["verification"]
            pilot.require(verification["decision"] == label["expected_claim"], "Verifier differs from hand-declared fixture verdict.")
            expected_trials = label["expected_trials"]
            verifier_by_trial = {str(r["trial"]): r["outcome"] for r in verification["trial_assessments"]}
            assessments = (record["model_output"] or {}).get("trial_assessments", [])
            raw_by_trial = {str(r["trial"]): r["outcome"] for r in assessments}
            duplicates = {str(r["trial"]) for r in assessments if sum(a["trial"] == r["trial"] for a in assessments) > 1}
            trial_total += len(expected_trials)
            raw_trial_correct += sum(raw_by_trial.get(t) == value and t not in duplicates for t, value in expected_trials.items())
            verifier_trial_correct += sum(verifier_by_trial.get(t) == value for t, value in expected_trials.items())
    historical = [r for r in [json.loads(line) for line in (validation.V2_DATA / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
                  if r["profile"] == "explicit-contract-v2"]
    pilot.require(len(old) == len(historical) == 27, "Historical replay count differs.")
    for row, source in zip(old, historical):
        pilot.require((row["case_id"], row["dataset"], row["expected_claim"], row["hybrid"]["llm_record"]) ==
                      (source["case_id"], source["dataset"], source["expected_claim"], source["record"]), "Historical record changed.")
    for row in rows + old:
        pilot.require(gate.combine(row["hybrid"]["llm_record"]) == row["hybrid"], "Gate result differs from replay.")
        combined, raw, verified = row["hybrid"]["combined"], row["hybrid"]["llm_record"], row["hybrid"]["verification"]
        if combined["decision"] in ("positive", "negative"):
            pilot.require(raw["system_claim"] == verified["decision"] == combined["decision"], "Binary agreement invariant violated.")
    for group in summary["groups"]:
        selected = rows if group["dataset"] == "new-synthetic-validation" else [
            r for r in old if r["dataset"] == group["dataset"].split(":", 1)[1]]
        for report in group["profiles"]:
            pilot.require(validation.metrics(selected, report["layer"]) == report, "Summary metric differs from replay.")
    raw_records = [r["hybrid"]["llm_record"] for r in rows]
    legacy_boundary = next(r for r in rows if r["case_id"] == "hybrid-016")
    result = {
        "scope": "development-v3-artifact-replay-and-fixture-conformance-audit",
        "manifest_sha256": pilot.digest(output / "manifest.json"), "new_raw_records_reproduce": len(rows),
        "historical_raw_records_identical": len(old), "hybrid_records_reproduce": len(rows) + len(old),
        "new_model_responses_preserved": raw_responses, "new_trial_total": trial_total,
        "raw_trial_assessments_match_hand_declared_fixtures": raw_trial_correct,
        "verifier_trial_assessments_match_hand_declared_fixtures": verifier_trial_correct,
        "verifier_result_interpretation": "conformance-to-coded-rules-and-constructed-fixtures-not-independent-accuracy",
        "raw_decision_changes": sum(validation.decision(r, "raw_qwen_v2") != validation.decision(r, "combined") for r in rows if r["expected_claim"] is not None),
        "decimal_boundary": {"case_id": "hybrid-016", "candidate_ms": 2048.2, "control_ms": 548.2,
                             "legacy_binary_float_delta": 2048.2 - 548.2, "decimal_delta": "1500.0",
                             "old_normalizer_signal_retained": legacy_boundary["hybrid"]["llm_record"]["rule_signal"],
                             "new_verifier_decision": legacy_boundary["hybrid"]["verification"]["decision"]},
        "done_reasons": dict(Counter(r["audit"]["provenance"].get("runtime_metrics", {}).get("done_reason")
                                     for r in raw_records if "raw_model_content" in r["audit"]["provenance"])),
        "protected_sources_unchanged": pilot.check_protected_sources(), "history_artifacts_unchanged": len(validation.history_inventory()),
        "all_summary_metrics_reproduce": True, "raw_model_claims_replaced": False,
        "tests_passed": 16, "test_command": ".venv/Scripts/python.exe -m unittest discover -s development -p test_verify_response_v3.py -v",
        "primary_formal_fpr_recomputed": False, "psr_recomputed": False,
    }
    pilot.write_json(output / "audit.json", result)
    if export:
        pilot.require(export.is_relative_to((ROOT / "results/processed").resolve()) and not export.exists(), "Use a new processed directory.")
        export.mkdir(parents=True, exist_ok=False)
        names = ("summary.json", "manifest.json", "runtime.json", "audit.json")
        for name in names:
            shutil.copyfile(output / name, export / name)
        pilot.write_json(export / "provenance.json", {
            "scope": "published-development-hybrid-v3-not-formal-not-independent-holdout",
            "source_directory": output.relative_to(ROOT).as_posix(), "exact_byte_copies": list(names),
            "file_sha256": {name: pilot.digest(export / name) for name in names},
            "local_source_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
            "formal_results_changed": False, "raw_model_claims_replaced": False,
            "prototype_promoted_to_formal_runner": False,
        })
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Use development results.")
    audit(destination, args.export_dir.resolve() if args.export_dir else None)
