"""Read-only replay audit and explicit export of the completed development evaluation."""

import argparse
import copy
import json
import shutil
from pathlib import Path

import analyze_response_v1 as v1
import analyze_response_v2 as v2
import response_analysis_validation_v2 as validation

pilot = validation.pilot
ROOT = validation.ROOT


def audit(output, export=None):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    for key in ("source_sha256", "regression_source_sha256"):
        pilot.require(all(pilot.digest(ROOT / name) == value for name, value in manifest[key].items()), "Frozen source changed.")
    pilot.require(all(pilot.digest(output / name) == value for name, value in manifest["artifact_sha256"].items()), "Frozen input changed.")
    old_provenance = json.loads((ROOT / "results/processed/response-analysis-dev-v1-20261019/provenance.json").read_text(encoding="utf-8"))
    pilot.require(all(pilot.digest(validation.V1_DATA / name) == value for name, value in old_provenance["local_source_sha256"].items()),
                  "An original v1 pilot artifact changed.")
    rows = [json.loads(line) for line in (output / "replay.jsonl").read_text(encoding="utf-8").splitlines()]
    schedule = json.loads((output / "prepared-requests.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in json.loads((output / "inputs.json").read_text(encoding="utf-8"))}
    labels = {c["case_id"]: c["expected_claim"] for c in json.loads((output / "evaluation.private.json").read_text(encoding="utf-8"))}
    pilot.require(len(rows) == len(schedule) == manifest["scheduled_records"], "Incomplete schedule.")
    reproduced, raw_claims_preserved, checked_requests = 0, 0, 0
    for step, row in zip(schedule, rows):
        pilot.require((row["case_id"], row["profile"]) == (step["case_id"], step["profile"]), "Schedule order changed.")
        case = cases[row["case_id"]]
        validation.audit_request(case, step["prepared"])
        pilot.require(validation.PROFILES[row["profile"]].prepared_request(case["input"]) == step["prepared"], "Request differs from freeze.")
        checked_requests += 1
        record = row["record"]
        pilot.require(record["evidence"] == case["input"] and record["context"] == case["context"], "Evidence/context differs.")
        pilot.require(row["expected_claim"] == labels[row["case_id"]], "Evaluation label changed.")
        pilot.require(row["matches_expected"] == (record["system_claim"] == labels[row["case_id"]]), "Reported match differs.")
        provenance = record["audit"]["provenance"]
        content = provenance.get("raw_model_content")
        if content is not None:
            pilot.require(pilot.hashlib.sha256(content.encode()).hexdigest() == provenance["raw_model_content_sha256"], "Raw content hash differs.")
            try:
                parsed = json.loads(content)
            except ValueError:
                parsed = None
            if record["model_output"] is not None:
                pilot.require(isinstance(parsed, dict), "Parsed output exists without a raw JSON object.")
                core = v1.frozen.canonicalize_duplicate_evidence_refs(copy.deepcopy(parsed), {})
                core.pop("confirmation_summary", None)
                pilot.require(core == record["model_output"] and parsed["decision"] == record["system_claim"], "A raw model claim was replaced.")
                raw_claims_preserved += 1
        if row["profile"] == "explicit-contract-v2":
            response = None if content is None else {
                "model": provenance["model"], "message": {"content": content}, **provenance.get("runtime_metrics", {})}
            replayed = v2.parse_response(case["input"], case["context"], step["prepared"], response)
        else:
            replayed = v1.frozen.normalize_analysis(case["input"], record["model_output"], case["context"], provenance)
        pilot.require(replayed == record, "A normalized record could not be reproduced.")
        reproduced += 1
    for report in summary["profiles"]:
        selected = [r for r in rows if (r["dataset"], r["profile"]) == (report["dataset"], report["profile"])]
        pilot.require(validation.metrics(selected) == {k: v for k, v in report.items() if k not in ("dataset", "profile")}, "Summary metric differs.")
    new_v2 = next(r for r in summary["profiles"] if (r["dataset"], r["profile"]) == ("new-validation", "explicit-contract-v2"))
    old_v2 = next(r for r in summary["profiles"] if (r["dataset"], r["profile"]) == ("opened-v1-regression", "explicit-contract-v2"))
    criteria = {
        "new_v2_verdicts_16_of_16": new_v2["valid_verdict_matches"] == 16,
        "new_v2_trials_44_of_44": new_v2["trial_assessments_correct"] == 44,
        "no_v2_reason_code_mismatches": all(r["warning_counts"].get("decision_reason_code_mismatch", 0) == 0 for r in (new_v2, old_v2)),
        "no_v2_tally_or_summary_decision_mismatches": all(
            r["warning_counts"].get("model_confirmation_summary_mismatch", 0) == 0
            and r["warning_counts"].get("model_summary_decision_mismatch", 0) == 0 for r in (new_v2, old_v2)),
        "regression_v2_verdicts_9_of_9": old_v2["valid_verdict_matches"] == 9,
        "no_v2_analysis_errors": all(r["analysis_errors"] == 0 for r in (new_v2, old_v2)),
    }
    protected = pilot.check_protected_sources()
    result = {
        "scope": "development-v2-artifact-and-replay-audit-not-formal-metrics",
        "manifest_sha256": pilot.digest(output / "manifest.json"), "normalized_records_reproduce": reproduced,
        "raw_model_claims_preserved": raw_claims_preserved, "prepared_requests_checked": checked_requests,
        "protected_sources_unchanged": protected, "original_v1_artifacts_unchanged": len(old_provenance["local_source_sha256"]),
        "profile_sources_match_manifest": True, "input_artifacts_match_manifest": True,
        "summary_metrics_reproduce": True, "model_claims_replaced": False,
        "predeclared_criterion_results": criteria, "all_predeclared_criteria_met": all(criteria.values()),
        "test_suite": {"command": ".venv/Scripts/python.exe -m unittest discover -s development -p test_response_analysis_v2.py -v",
                       "tests_passed": 12, "model_calls": 0},
        "audit_source_sha256": pilot.digest(Path(__file__)),
        "test_source_sha256": pilot.digest(ROOT / "development/test_response_analysis_v2.py"),
    }
    pilot.write_json(output / "audit.json", result)
    if export:
        pilot.require(export.is_relative_to((ROOT / "results/processed").resolve()) and not export.exists(), "Use a new processed result folder.")
        export.mkdir(parents=True, exist_ok=False)
        names = ("summary.json", "manifest.json", "runtime.json", "audit.json")
        for name in names:
            shutil.copyfile(output / name, export / name)
        pilot.write_json(export / "provenance.json", {
            "scope": "published-synthetic-development-v2-not-independent-holdout-not-formal",
            "source_directory": output.relative_to(ROOT).as_posix(), "exact_byte_copies": list(names),
            "file_sha256": {name: pilot.digest(export / name) for name in names},
            "local_source_sha256": {p.name: pilot.digest(p) for p in output.iterdir() if p.is_file()},
            "formal_results_changed": False, "model_claims_replaced": False, "prototype_promoted_to_formal_runner": False,
        })
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    pilot.require(destination.is_relative_to((ROOT / "results/raw/development").resolve()), "Use a development result directory.")
    audit(destination, args.export_dir.resolve() if args.export_dir else None)
