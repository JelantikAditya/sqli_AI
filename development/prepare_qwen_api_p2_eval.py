"""Prepare a blinded human-reference packet for the Qwen API P2 evaluation.

Reads and hash-checks the completed U06 v15 source ledger. Writes only a new,
ignored development output directory. It never calls the API or edits source data.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dvwa"), str(ROOT / "development")]

import experiment_dataset
import qwen_api_p2_analysis as adapter
import rag_pipeline
from validation_loop import sanitized_review_excerpt_from_markers


SOURCE_DIR = ROOT / "results/raw/pilot/u06-v15-integrated-20261016"
DEFAULT_OUTPUT = ROOT / "results/raw/development/qwen38-api-p2-eval-20261021-ready"
SEED = 20261021
TECHNIQUES = ("error-based", "boolean-based blind", "time-based blind")
SQL_DIAGNOSTICS = {"mysql_syntax_error", "mysql_xpath_error", "mysql_unknown_column"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False).encode("utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def source_run_artifacts(source_dir: Path) -> dict[str, dict]:
    events = [json.loads(line) for line in (source_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    result = {}
    for event in events:
        if event.get("event_type") == "attempt_completed" and event.get("run_id"):
            result[event["run_id"]] = {
                "attempt_id": event.get("attempt_id"),
                "runner_batch_sha256": event.get("runner_batch_sha256"),
                "validation_log_sha256": event.get("validation_log_sha256"),
                "metric_eligible": event.get("metric_eligible"),
            }
    return result


def valid_blind(row: dict) -> bool:
    return not row["diagnostics"] and (row["http_status"] == 200 or (
        row["http_status"] == 404 and row["content_markers"] == ["user_id_missing"]))


def trial_signal(technique: str, group: dict[str, dict]) -> bool:
    if technique == "error-based":
        return bool(set(group["candidate"]["diagnostics"]) - set(group["baseline"]["diagnostics"]))
    if technique == "boolean-based blind":
        true_row, false_row = group["true_condition"], group["false_condition"]
        return (valid_blind(true_row) and valid_blind(false_row)
                and true_row["content_markers"] == ["user_id_exists"]
                and false_row["content_markers"] == ["user_id_missing"])
    candidate, control = group["candidate"], group["no_delay_control"]
    return (valid_blind(candidate) and valid_blind(control)
            and candidate["content_markers"] == control["content_markers"]
            and candidate["content_markers"] in (["user_id_exists"], ["user_id_missing"])
            and Decimal(str(candidate["elapsed_ms"])) - Decimal(str(control["elapsed_ms"])) >= Decimal("1500"))


def normalized_document(technique: str, scenario: dict, observations: list[dict]) -> dict:
    roles_by_technique = {
        "error-based": {"single": "candidate", "baseline": "baseline"},
        "boolean-based blind": {"baseline": "baseline", "true_condition": "true_condition",
                                "false_condition": "false_condition"},
        "time-based blind": {"baseline": "baseline", "single": "candidate",
                             "no_delay_control": "no_delay_control"},
    }
    roles = roles_by_technique[technique]
    converted = []
    for source_row in observations:
        if source_row.get("record_type") != "payload":
            continue
        source_role = source_row["payload_role"]
        if source_role not in roles:
            continue
        row = {
            "observation_id": f"obs-{len(converted) + 1:03d}",
            "trial": int(source_row["confirmation_index"]),
            "role": roles[source_role],
            "http_status": int(source_row["http_status"]),
            "elapsed_ms": source_row["response_time_ms"],
            "response_sha256": source_row["response_sha256"],
            # Only SQL diagnostics belong in this field. Executor-derived indicators
            # such as time_delta_over_threshold must never become model evidence.
            "diagnostics": sorted(set(source_row["response_indicators"]) & SQL_DIAGNOSTICS),
            "content_markers": list(source_row["content_markers"]),
            "review_excerpt": sanitized_review_excerpt_from_markers(
                sorted(set(source_row["response_indicators"]) & SQL_DIAGNOSTICS),
                source_row["content_markers"]),
        }
        converted.append(row)
    document = {
        "schema_version": "1.0.0",
        "technique": technique,
        # The contract projects only technique and paired evidence to the model.
        # Coordinates here are canonical placeholders, not original scenario metadata.
        "injection_point": {
            "method": "GET",
            "input_path": "/vulnerabilities/sqli/" if technique == "error-based" else "/vulnerabilities/sqli_blind/",
            "result_path": "/vulnerabilities/sqli/" if technique == "error-based" else "/vulnerabilities/sqli_blind/",
            "parameter": "id",
        },
        "runtime_status": "valid",
        "baseline_valid": True,
        "time_threshold_ms": 1500,
        "observations": converted,
    }
    return document


def source_key(run: dict, candidate: dict) -> str:
    return f"{run['experiment_id']}|{run.get('run_id', '')}|{candidate['candidate_id']}"


def inspect_source(source_dir: Path) -> tuple[list[dict], dict, dict]:
    runs = experiment_dataset.load_runs(source_dir)
    catalog = rag_pipeline.load_catalog()
    scenarios = {item["scenario_id"]: item for item in catalog["scenarios"]}
    artifacts = source_run_artifacts(source_dir)
    candidates = []
    for run in runs:
        if run["status"] != "completed" or not run["metric_eligible"]:
            continue
        scenario = scenarios[run["scenario_id"]]
        technique = scenario["sqli_type"]
        for candidate in run["candidates"]:
            source_obs = [row for row in candidate["observations"] if row.get("record_type") == "payload"]
            expected_roles = {
                "error-based": {"baseline", "single"},
                "boolean-based blind": {"baseline", "true_condition", "false_condition"},
                "time-based blind": {"baseline", "single", "no_delay_control"},
            }[technique]
            by_trial: dict[int, dict[str, dict]] = {}
            for row in source_obs:
                by_trial.setdefault(int(row["confirmation_index"]), {})[row["payload_role"]] = row
            if sorted(by_trial) != [1, 2, 3] or any(set(group) != expected_roles for group in by_trial.values()):
                continue
            mapped = normalized_document(technique, scenario, source_obs)
            mapped_groups = {}
            for row in mapped["observations"]:
                mapped_groups.setdefault(row["trial"], {})[row["role"]] = row
            trial_outcomes = [trial_signal(technique, mapped_groups[i]) for i in (1, 2, 3)]
            positives = sum(trial_outcomes)
            strata = "positive" if positives == 3 else "negative" if positives == 0 else "mixed"
            candidates.append({
                "key": source_key(run, candidate),
                "technique": technique,
                "scenario_id": run["scenario_id"],
                "condition_id": run["condition_id"],
                "replicate": run["replicate"],
                "run_id": run.get("run_id"),
                "attempt_id": run.get("attempt_id"),
                "candidate_id": candidate["candidate_id"],
                "candidate_source_sha256": canonical_hash(source_obs),
                "run_artifacts": artifacts.get(run.get("run_id"), {}),
                "response_sha256s": [row["response_sha256"] for row in source_obs],
                "signal_stratum_for_sampling_only": strata,
                "positive_trial_count_for_sampling_only": positives,
                "document": mapped,
            })
    return candidates, scenarios, artifacts


def select_distinct(pool: list[dict], count: int, used: set[str], rng: random.Random) -> list[dict]:
    if count == 0:
        return []
    available = [item for item in pool if item["key"] not in used]
    rng.shuffle(available)
    chosen = []
    scenarios = set()
    for item in available:
        if item["scenario_id"] not in scenarios:
            chosen.append(item)
            scenarios.add(item["scenario_id"])
            if len(chosen) == count:
                return chosen
    for item in available:
        if item not in chosen:
            chosen.append(item)
            if len(chosen) == count:
                return chosen
    raise ValueError(f"Insufficient unique source candidates: need {count}, found {len(chosen)}")


def make_inconclusive(item: dict, omitted_trial: int) -> tuple[dict, dict]:
    document = json.loads(json.dumps(item["document"]))
    before = len(document["observations"])
    document["observations"] = [row for row in document["observations"] if row["trial"] != omitted_trial]
    if len(document["observations"]) == before:
        raise ValueError("Requested omitted trial was not present in a source candidate")
    return document, {"construction": "whole_trial_omitted", "omitted_trial": omitted_trial}


def reviewer_packet(review_id: str, document: dict) -> dict:
    shown_roles = {
        "error-based": {"baseline", "candidate"},
        "boolean-based blind": {"true_condition", "false_condition"},
        "time-based blind": {"candidate", "no_delay_control"},
    }[document["technique"]]
    entries = []
    for observation in document["observations"]:
        if observation["role"] not in shown_roles:
            continue
        entry = {
            "observation_id": observation["observation_id"],
            "role": observation["role"],
            "http_status": observation["http_status"],
            "diagnostics": list(observation["diagnostics"]),
            "content_markers": list(observation["content_markers"]),
            "sanitized_excerpt": sanitized_review_excerpt_from_markers(
                observation["diagnostics"], observation["content_markers"]),
        }
        if "elapsed_ms" in observation:
            entry["elapsed_ms"] = observation["elapsed_ms"]
        entries.append(entry)
    trial_groups = {}
    for observation in document["observations"]:
        trial_groups.setdefault(observation["trial"], {})[observation["role"]] = observation
    comparisons = []
    for trial in sorted(trial_groups):
        group = trial_groups[trial]
        row = {"trial": trial, "observations": [e for e in entries if next(
            o["trial"] for o in document["observations"] if o["observation_id"] == e["observation_id"]) == trial]}
        if document["technique"] == "time-based blind" and "candidate" in group and "no_delay_control" in group:
            row["candidate_minus_control_ms"] = float(
                Decimal(str(group["candidate"]["elapsed_ms"]))
                - Decimal(str(group["no_delay_control"]["elapsed_ms"]))
            )
        comparisons.append(row)
    return {"review_id": review_id, "technique": document["technique"], "comparisons": comparisons}


def create_packet(output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Output exists; refusing to overwrite: {output_dir}")
    source_dir = SOURCE_DIR.resolve()
    candidates, _scenarios, artifacts = inspect_source(source_dir)
    rng = random.Random(SEED)
    selected = []
    used: set[str] = set()
    by_tech = {tech: [item for item in candidates if item["technique"] == tech] for tech in TECHNIQUES}

    for technique in TECHNIQUES:
        for strata in ("positive", "negative"):
            rows = select_distinct([item for item in by_tech[technique]
                                    if item["signal_stratum_for_sampling_only"] == strata], 2, used, rng)
            for item in rows:
                used.add(item["key"])
                selected.append((technique, strata, item, item["document"], {"construction": "complete_source_candidate"}))

    for technique in TECHNIQUES:
        natural_mixed = select_distinct([item for item in by_tech[technique]
                                         if item["signal_stratum_for_sampling_only"] == "mixed"],
                                        1 if technique == "time-based blind" else 0, used, rng)
        for item in natural_mixed:
            used.add(item["key"])
            selected.append((technique, "inconclusive", item, item["document"], {"construction": "natural_mixed_source_candidate"}))
        missing_count = 2 - len(natural_mixed)
        if missing_count:
            pool = [item for item in by_tech[technique]
                    if item["signal_stratum_for_sampling_only"] in {"positive", "negative"}]
            incomplete = select_distinct(pool, missing_count, used, rng)
            for index, item in enumerate(incomplete):
                used.add(item["key"])
                omitted_trial = (2, 3)[index % 2]
                document, construction = make_inconclusive(item, omitted_trial)
                selected.append((technique, "inconclusive", item, document, construction))

    # Randomize reviewer IDs and order independently from hidden sampling strata.
    rng.shuffle(selected)
    review_rows = []
    public_packets = []
    private_map = []
    prepared_rows = []
    used_ids = set()
    for technique, strata, source, document, construction in selected:
        review_id = "rv-" + uuid.uuid4().hex[:12]
        while review_id in used_ids:
            review_id = "rv-" + uuid.uuid4().hex[:12]
        used_ids.add(review_id)
        prepared = adapter.prepare(document)
        prepared_rows.append({
            "review_id": review_id,
            "document": document,
            "prepared": prepared,
            "request_sha256": prepared["request_sha256"],
        })
        public_packets.append(reviewer_packet(review_id, document))
        private_map.append({
            "review_id": review_id,
            "technique": technique,
            "sampling_stratum_private": strata,
            "positive_trial_count_private": source["positive_trial_count_for_sampling_only"],
            "source": {key: source[key] for key in (
                "key", "scenario_id", "condition_id", "replicate", "run_id", "attempt_id",
                "candidate_id", "candidate_source_sha256", "run_artifacts", "response_sha256s")},
            "construction": construction,
            "input_sha256": prepared["document_sha256"],
            "request_sha256": prepared["request_sha256"],
        })
        review_rows.append({"review_id": review_id})

    if len(public_packets) != 18:
        raise ValueError(f"Expected 18 blinded cases, created {len(public_packets)}")
    counts = {tech: {decision: sum(1 for packet, row in zip(public_packets, selected)
                                         if packet["technique"] == tech and row[1] == decision)
                     for decision in ("positive", "negative", "inconclusive")} for tech in TECHNIQUES}
    if any(counts[tech] != {"positive": 2, "negative": 2, "inconclusive": 2} for tech in TECHNIQUES):
        raise ValueError(f"Sampling failed to meet 2/2/2 balance: {counts}")

    output_dir.mkdir(parents=True)
    blind_dir = output_dir / "validator"
    operator_dir = output_dir / "operator"
    blind_dir.mkdir()
    operator_dir.mkdir()
    write_json(blind_dir / "packets.json", {"packet_version": "qwen-api-p2-blind-review-v1", "cases": public_packets})
    with (blind_dir / "annotations.template.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=("review_id", "validator_id", "decision", "justification"))
        writer.writeheader()
        for row in review_rows:
            writer.writerow({**row, "validator_id": "", "decision": "", "justification": ""})
    (blind_dir / "INSTRUCTIONS.md").write_text(
        "# Instruksi anotasi independen P2\n\n"
        "Nilai bukti respons yang ditampilkan per `review_id` tanpa mencari payload, kondisi, skenario, atau hasil executor. "
        "Isi satu baris untuk setiap ID pada `annotations.template.csv`. Gunakan tepat satu keputusan: `positive`, `negative`, atau `inconclusive`.\n\n"
        "- `positive`: bukti memenuhi aturan teknik pada ketiga trial yang tersedia. Error-based memerlukan diagnostik SQL baru pada kandidat terhadap baseline; boolean-based memerlukan marker `user_id_exists` pada true dan `user_id_missing` pada false, tanpa diagnostik dan dengan status valid; time-based memerlukan marker valid yang sama pada kandidat dan kontrol, tanpa diagnostik, serta delta bertanda kandidat dikurangi kontrol minimal 1500 ms.\n"
        "- `negative`: ketiga trial lengkap dan tidak ada trial positif berdasarkan aturan teknik tersebut. Ini berarti bukti payload tidak menunjukkan sinyal yang diuji, bukan bahwa aplikasi aman.\n"
        "- `inconclusive`: ada trial yang hilang, bukti tidak lengkap, atau hasil trial campuran sehingga aturan keputusan tidak mendukung positif maupun negatif.\n\n"
        "Status blind valid adalah HTTP 200, atau HTTP 404 dengan marker tunggal `user_id_missing`. Jangan mengisi trial yang hilang. Untuk error-based, HTTP 500 saja bukan diagnostik SQL. Untuk boolean-based, baseline tidak menentukan hasil. Untuk time-based, gunakan delta berpasangan, jangan membandingkan kandidat dengan baseline atau merata-ratakan trial. Catat alasan singkat yang merujuk pada bukti dan trial. Label ini adalah referensi penilai untuk evaluasi P2, terpisah dari label VAL-01 dan metrik formal FPR/PSR.\n",
        encoding="utf-8")
    write_json(operator_dir / "sampling-map.private.json", {
        "notice": "Private operator mapping. Sampling strata are executor-rule sampling only, not independent ground truth.",
        "cases": private_map,
    })
    with (operator_dir / "prepared-requests.jsonl").open("w", encoding="utf-8") as stream:
        for row in prepared_rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")

    invalid_gates = []
    for technique in TECHNIQUES:
        base = next(row["document"] for row in prepared_rows if row["document"]["technique"] == technique)
        runtime_invalid = json.loads(json.dumps(base))
        runtime_invalid.update(runtime_status="invalid", runtime_failure_code="network_error", observations=[])
        baseline_invalid = json.loads(json.dumps(base))
        baseline_invalid.update(baseline_valid=False, runtime_failure_code="baseline_invalid")
        for gate_name, document in (("runtime-invalid", runtime_invalid), ("baseline-invalid", baseline_invalid)):
            try:
                adapter.prepare(document)
            except ValueError as error:
                invalid_gates.append({"technique": technique, "gate": gate_name, "api_call": False,
                                      "blocked": True, "reason": str(error)})
            else:
                raise AssertionError(f"Invalid gate was not blocked: {technique}/{gate_name}")
    write_json(operator_dir / "gate-validation.json", {"cases": invalid_gates, "blocked_count": len(invalid_gates), "api_calls": 0})

    public_bytes = (blind_dir / "packets.json").read_bytes()
    private_bytes = (operator_dir / "sampling-map.private.json").read_bytes()
    request_bytes = (operator_dir / "prepared-requests.jsonl").read_bytes()
    source_ledger_bytes = (source_dir / "ledger.jsonl").read_bytes()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "P2 blinded human-reference packet and frozen no-RAG API requests; preparation only",
        "api_called": False,
        "formal_metrics_claimed": False,
        "adviser_decision": "Researcher reports adviser agreed to try the LLM API; this does not record formal proposal amendment approval.",
        "source": {
            "experiment_id": "u06-v15-integrated-20261016",
            "ledger_sha256": sha256_bytes(source_ledger_bytes),
            "completed_metric_eligible_candidate_count": sum(1 for item in candidates),
            "source_artifacts_hash_checked_by": "dvwa/experiment_dataset.py load_runs",
        },
        "selection": {
            "seed": SEED,
            "blind_case_count": len(public_packets),
            "balanced_sampling_counts_private": counts,
            "strata_are_ground_truth": False,
            "new_independent_annotations_received": False,
            "annotation_decisions_allowed": ["positive", "negative", "inconclusive"],
        },
        "prompt": {"version": adapter.PROMPT_VERSION, "rag_mode": "off",
                   "max_output_tokens": adapter.MAX_OUTPUT_TOKENS, "timeout_seconds": adapter.TIMEOUT_SECONDS,
                   "request_count_prepared": len(prepared_rows), "request_hashes": [r["request_sha256"] for r in prepared_rows]},
        "gate_validation": {"invalid_cases": len(invalid_gates), "blocked_before_api": len(invalid_gates), "api_calls": 0},
        "files": {
            "validator/packets.json": sha256_bytes(public_bytes),
            "operator/sampling-map.private.json": sha256_bytes(private_bytes),
            "operator/prepared-requests.jsonl": sha256_bytes(request_bytes),
            "operator/gate-validation.json": sha256_bytes((operator_dir / "gate-validation.json").read_bytes()),
        },
        "source_scripts": {
            "development/qwen_api_p2_analysis.py": sha256_bytes((ROOT / "development/qwen_api_p2_analysis.py").read_bytes()),
            "development/analyze_response_v2.py": sha256_bytes((ROOT / "development/analyze_response_v2.py").read_bytes()),
            "development/prepare_qwen_api_p2_eval.py": sha256_bytes(Path(__file__).read_bytes()),
        },
    }
    write_json(operator_dir / "manifest.json", manifest)

    # Defense-in-depth scan: the reviewer export must not carry hidden source IDs or model labels.
    public_text = public_bytes.decode("utf-8").lower()
    forbidden = ("ground_truth", "scenario_id", "condition_id", "run_id", "candidate_id", "payload_source",
                 "sampling_stratum", "positive_trial_count", "expected_decision", "model_decision")
    leaks = [term for term in forbidden if term in public_text]
    if leaks:
        raise ValueError(f"Blind packet includes forbidden private fields: {leaks}")
    return {"output_dir": str(output_dir), "counts": counts, "invalid_gates_blocked": len(invalid_gates),
            "prepared_requests": len(prepared_rows), "api_called": False,
            "public_sha256": sha256_bytes(public_bytes), "private_map_sha256": sha256_bytes(private_bytes)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = create_packet(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
