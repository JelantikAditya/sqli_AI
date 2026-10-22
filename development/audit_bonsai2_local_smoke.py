"""Re-score saved Bonsai smoke outputs offline without changing model claims."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

from jsonschema import Draft202012Validator

import qwen_api_p2_analysis as p2

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    saved_summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    requests = json.loads((directory / "requests.json").read_text(encoding="utf-8"))
    references = {row["case_id"]: row["expected"] for row in json.loads(
        (directory / "synthetic-reference.json").read_text(encoding="utf-8"))["cases"]}
    results = []
    for item in requests:
        response = json.loads((directory / f"{item['case_id']}.response.json").read_text(encoding="utf-8"))
        choice = response["choices"][0]
        content = choice["message"]["content"]
        output = json.loads(content)
        Draft202012Validator(item["schema"]).validate(output)
        row = {"case_id": item["case_id"], "schema_valid": True,
               "finish_reason": choice["finish_reason"],
               "decode_tokens_per_second": response["timings"]["predicted_per_second"]}
        if "document" in item:
            parsed = p2.parse(item["document"], item["prepared"], {"status": "ok", "content": content})
            truth = references[item["case_id"]]
            expected_trials = {trial["trial"]: trial["outcome"] for trial in truth["trial_assessments"]}
            actual_trials = {trial["trial"]: trial["outcome"] for trial in output["trial_assessments"]}
            row.update(raw_decision=output["decision"], expected_decision=truth["decision"],
                       verdict_match=output["decision"] == truth["decision"],
                       trial_outcomes_match=actual_trials == expected_trials,
                       parsed_status=parsed["status"], parse_error=parsed["error"], warnings=parsed["warnings"])
            row["full_contract_pass"] = (row["verdict_match"] and row["trial_outcomes_match"]
                                         and parsed["status"] == "ok" and not parsed["warnings"]
                                         and choice["finish_reason"] == "stop")
        else:
            row["readiness_pass"] = output == references[item["case_id"]]
        results.append(row)
    domain = [row for row in results if "full_contract_pass" in row]
    source_paths = [directory / name for name in (
        "manifest.json", "summary.json", "requests.json", "synthetic-reference.json", "gpu-telemetry.json")]
    source_paths.extend(directory.glob("*.response.json"))
    return {
        "directory": str(directory.relative_to(ROOT)),
        "profile": manifest.get("profile", "non-thinking"),
        "call_count": len(results), "json_schema_valid_count": len(results),
        "domain_case_count": len(domain),
        "domain_verdict_match_count": sum(row["verdict_match"] for row in domain),
        "domain_full_contract_pass_count": sum(row["full_contract_pass"] for row in domain),
        "domain_mean_wall_seconds": round(statistics.mean(
            row["wall_seconds"] for row in saved_summary["cases"] if row["case_id"] != "json-readiness"), 3),
        "decode_tokens_per_second_range": [round(min(row["decode_tokens_per_second"] for row in domain), 2),
                                            round(max(row["decode_tokens_per_second"] for row in domain), 2)],
        "peak_sampled_gpu_used_mib": saved_summary["peak_sampled_gpu_used_mib"],
        "startup_seconds": saved_summary["startup_seconds"],
        "server_stopped": saved_summary["server_stopped"], "cases": results,
        "raw_artifact_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in source_paths},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    installation = json.loads((ROOT / "models/bonsai2-9b/install-receipt.json").read_text(encoding="utf-8"))
    report = {
        "schema": "bonsai2-local-smoke-audit-v1", "audited_at": datetime.now(timezone.utc).isoformat(),
        "model_id": installation["model_id"], "model_revision": installation["model_revision"],
        "model_sha256": next(asset["sha256"] for asset in installation["assets"] if asset["name"] == "model"),
        "runtime_release": installation["runtime_release"], "server_sha256": installation["server_sha256"],
        "hardware": {"gpu": "NVIDIA GeForce RTX 3050 Laptop GPU", "vram_mib": 4096,
                     "ram_gib": 15.73, "cpu": "Intel Core i5-11400H", "driver": "577.00"},
        "hardware_fit_observed": True, "analysis_gate_passed": False,
        "experiment_scope": "development smoke; three repeated synthetic fixtures per profile",
        "independent_holdout": False, "human_annotations": False, "formal_FPR": False, "formal_PSR": False,
        "paid_api_calls": 0, "dvwa_requests": 0,
        "profiles": [audit(directory.resolve()) for directory in args.directories],
    }
    # Readiness must follow measured results, rather than a hard-coded success.
    report["analysis_gate_passed"] = any(
        profile["domain_full_contract_pass_count"] == profile["domain_case_count"]
        for profile in report["profiles"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "profiles": [
        {key: value for key, value in profile.items() if key not in ("cases", "raw_artifact_sha256")}
        for profile in report["profiles"]]}, indent=2))


if __name__ == "__main__":
    main()
