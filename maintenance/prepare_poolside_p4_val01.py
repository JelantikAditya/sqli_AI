"""Build a fresh, blinded VAL-01 packet from the locked Poolside Laguna P4 cohort."""

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
from blind_review import export_runs
from experiment_dataset import load_runs
from rag_pipeline import load_catalog


OUTPUT = ROOT / "results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01"
RECOVERY1 = ROOT / "results/raw/formal/poolside-laguna-p4-recovery1-20261023"
REPLICATE3 = ROOT / "results/raw/formal/poolside-laguna-p4-replicate3-20261023"
AMENDMENT = ROOT / "results/raw/formal/poolside-p4-s5b-r3-amend1-20261023"
ASSEMBLY = ROOT / "docs/evidence/poolside-laguna-p4-replicate3-assembly-draft-2026-10-23.json"
EXPECTED_REUSE_AUDIT_SHA256 = "631d873fb5a17e529368c8f7c69bf23b488301b924f035accda4dbc6bc21ec57"
def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def inventory(paths):
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(paths))}


def verify_observations(runs):
    catalog = {item["scenario_id"]: item for item in load_catalog()["scenarios"]}
    observation_count = 0
    for run in runs:
        scenario = catalog[run["scenario_id"]]
        if "error" in scenario["sqli_type"]:
            roles = {"baseline", "single"}
        elif "boolean" in scenario["sqli_type"]:
            roles = {"baseline", "true_condition", "false_condition"}
        else:
            roles = {"baseline", "single", "no_delay_control"}
        expected = Counter((trial, role) for trial in (1, 2, 3) for role in roles)
        for candidate in run["candidates"]:
            actual = Counter((observation["confirmation_index"], observation["payload_role"])
                             for observation in candidate["observations"])
            require(actual == expected, "A final P4 candidate is missing a required observation.")
            require(all(observation.get("review_excerpt") for observation in candidate["observations"]),
                    "A final P4 observation lacks a sanitized review excerpt.")
            observation_count += len(candidate["observations"])
    return observation_count


def prepare():
    require(not OUTPUT.exists(), "The VAL-01 output directory already exists; refusing to overwrite it.")
    assembly = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    require(assembly["status"] == "targeted-amendment-completed-pending-VAL01-and-human-validation",
            "The P4 assembly is not at the expected post-amendment state.")
    reuse_audit = ROOT / assembly["reuse"]["path"]
    require(assembly["reuse"]["sha256"] == EXPECTED_REUSE_AUDIT_SHA256
            and sha256(reuse_audit) == EXPECTED_REUSE_AUDIT_SHA256,
            "The R1/R2 reuse audit differs from the approved assembly.")
    require(json.loads(reuse_audit.read_text(encoding="utf-8"))["source_formal_output_path"]
            == "results/raw/formal/poolside-laguna-p4-recovery1-20261023",
            "The R1/R2 reuse audit points to an unexpected source directory.")
    require(sha256(REPLICATE3 / "ledger.jsonl") == assembly["candidate_hashes"]["execution_ledger"],
            "The completed R3 source ledger changed after the assembly.")
    require(sha256(AMENDMENT / "ledger.jsonl")
            == assembly["targeted_amendment"]["execution_ledger_sha256"],
            "The targeted amendment ledger changed after the assembly.")

    reused = [run for run in load_runs(RECOVERY1) if run["replicate"] in (1, 2)]
    original_r3 = load_runs(REPLICATE3)
    supplement = load_runs(AMENDMENT)
    require(Counter(run["status"] for run in reused) == {"completed": 66, "excluded": 6},
            "The preserved R1/R2 coverage does not match the assembly.")
    require(Counter(run["status"] for run in original_r3) == {"completed": 32, "excluded": 4},
            "The original R3 coverage differs from the assembly.")
    require(len(supplement) == 1 and supplement[0]["status"] == "completed"
            and (supplement[0]["condition_id"], supplement[0]["scenario_id"], supplement[0]["replicate"])
            == ("B", "S5", 3) and supplement[0]["metric_eligible"],
            "The targeted B/S5/R3 replacement is not exactly one eligible unit.")

    designed_exclusions = [run for run in reused + original_r3
                           if run["status"] == "excluded"
                           and run["condition_id"] == "C"
                           and run["scenario_id"] in {"S10", "S11", "S12"}]
    completed = [run for run in reused + original_r3 if run["status"] == "completed"] + supplement
    require(len(designed_exclusions) == 9, "Expected only the nine design-excluded C units.")
    require(sum(run["status"] == "excluded" for run in original_r3) == 4
            and any(run["condition_id"] == "B" and run["scenario_id"] == "S5"
                    and len(run["candidates"]) == 9 for run in original_r3),
            "The superseded partial B/S5/R3 attempt is not accounted for as excluded.")
    require(len(completed) == 99 and all(run["metric_eligible"] and len(run["candidates"]) == 10
                                         for run in completed),
            "The assembled formal cohort must contain 99 eligible ten-candidate units.")
    for replicate in (1, 2, 3):
        coverage = Counter(run["condition_id"] for run in completed if run["replicate"] == replicate)
        require(coverage == {"A": 12, "B": 12, "C": 9},
                f"P4 condition coverage differs in replicate {replicate}.")

    source_files = [p for directory in (RECOVERY1, REPLICATE3, AMENDMENT)
                    for p in directory.rglob("*") if p.is_file()]
    source_files.extend([ASSEMBLY, reuse_audit, ROOT / "dvwa/local_experiment_protocol.json",
                         ROOT / "dvwa/experiment_scenarios.json", ROOT / "dvwa/blind_review.py",
                         ROOT / "dvwa/experiment_dataset.py", ROOT / "docs/panduan-penilaian-val01-formal.md",
                         ROOT / "docs/prosedur-validator-u04.md", Path(__file__).resolve()])
    before = inventory(source_files)

    observation_count = verify_observations(completed)
    exported = export_runs(completed, OUTPUT)
    public_dir = OUTPUT / "validator"
    packet_path = public_dir / "packets.json"
    package = json.loads(packet_path.read_text(encoding="utf-8"))
    packets = package["packets"]
    require(len(packets) == 990 and len({p["review_id"] for p in packets}) == 990,
            "Expected 990 newly randomized review IDs.")
    require(all(set(packet) == {"review_id", "technique", "injection_point", "candidate", "observations"}
                for packet in packets), "Unexpected private metadata in the public packet schema.")
    public_text = packet_path.read_text(encoding="utf-8")
    forbidden = ("condition_id", "rag_mode", "payload_source", "ground_truth", "system_decision",
                 "confirmed_success", "evidence_status", "run_id", "attempt_id", "unit_id", "scenario_id",
                 "poolside/laguna", "Qwen")
    require(all(f'"{field}"' not in public_text for field in forbidden),
            "A private condition, model, or executor label leaked into the public packet.")
    require(all(observation.get("review_excerpt") for packet in packets
                for observation in packet["observations"]), "A public observation lacks a review excerpt.")

    package["review_readiness"] = "ready_for_independent_formal_review"
    packet_bytes = (json.dumps(package, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    packet_path.write_bytes(packet_bytes)
    mapping_path = OUTPUT / "mapping.private.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    package_hash = hashlib.sha256(packet_bytes).hexdigest()
    mapping["package_sha256"] = package_hash
    write_json(mapping_path, mapping)

    template_path = public_dir / "annotations.csv"
    with template_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 990 and all(not row["validator_id"] and not row["decision"]
                                     and not row["justification"] for row in rows),
            "The independent-review annotation template must remain blank.")
    guide = (ROOT / "docs/panduan-penilaian-val01-formal.md").read_text(encoding="utf-8")
    (public_dir / "PETUNJUK.md").write_text(guide, encoding="utf-8", newline="\n")
    archive = OUTPUT / "paket-validator.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(public_dir.iterdir()):
            bundle.write(path, arcname=path.name)
    with zipfile.ZipFile(archive) as bundle:
        require(set(bundle.namelist()) == {"PETUNJUK.md", "packets.json", "annotations.csv"},
                "The handoff ZIP must contain only blinded reviewer files.")

    after = inventory(source_files)
    require(before == after, "A source artifact changed while preparing the VAL-01 packet.")
    write_json(OUTPUT / "source-inventory.private.json", before)
    audit = {
        "schema": "poolside-laguna-p4-val01-package-audit-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_independent_formal_review",
        "validator_alias": "VAL-01",
        "composition": {
            "reused_replicates_1_2_completed_units": 66,
            "replicate_3_original_completed_units": 32,
            "targeted_b_s5_r3_replacement_units": 1,
            "design_excluded_units_omitted_from_review": 9,
            "superseded_partial_b_s5_r3_candidates_omitted": 9,
            "eligible_units": len(completed),
            "candidate_packets": len(packets),
            "observations": observation_count,
        },
        "checks": {
            "r1_r2_reuse_audit_verified": True,
            "r1_r2_preserved": True,
            "targeted_amendment_ledger_verified": True,
            "all_candidate_trials_complete": True,
            "all_sanitized_excerpts_present": True,
            "review_ids_unique": True,
            "public_packet_has_no_private_condition_or_model_labels": True,
            "annotation_template_blank": True,
            "zip_contains_only_public_validator_files": True,
            "source_artifacts_unchanged": True,
        },
        "source_ledgers": {
            "r1_r2": sha256(RECOVERY1 / "ledger.jsonl"),
            "replicate_3": sha256(REPLICATE3 / "ledger.jsonl"),
            "targeted_amendment": sha256(AMENDMENT / "ledger.jsonl"),
        },
        "source_files_checked": len(before),
        "package_sha256": package_hash,
        "zip_sha256": sha256(archive),
        "annotation_count": 0,
        "psr_status": "pending independent human annotations",
        "preparation_api_requests": 0,
        "preparation_dvwa_requests": 0,
        "preparation_database_resets": 0,
    }
    write_json(OUTPUT / "audit.private.json", audit)
    write_json(OUTPUT / "artifact-manifest.private.json",
               inventory([p for p in OUTPUT.rglob("*") if p.is_file()]))
    receipt = {
        "schema": audit["schema"], "status": audit["status"], "package_directory": OUTPUT.relative_to(ROOT).as_posix(),
        "reviewer_zip": (OUTPUT / "paket-validator.zip").relative_to(ROOT).as_posix(),
        "composition": audit["composition"], "checks": audit["checks"],
        "source_ledgers": audit["source_ledgers"], "package_sha256": package_hash,
        "zip_sha256": audit["zip_sha256"], "source_files_checked": len(before),
        "preparation_api_requests": 0, "preparation_dvwa_requests": 0,
        "preparation_database_resets": 0,
    }
    return receipt


if __name__ == "__main__":
    result = prepare()
    receipt_path = ROOT / "docs/evidence/poolside-laguna-p4-val01-package-2026-10-23.json"
    write_json(receipt_path, result)
    print(json.dumps({"status": result["status"], "reviewer_zip": result["reviewer_zip"],
                      "candidate_packets": result["composition"]["candidate_packets"],
                      "observations": result["composition"]["observations"],
                      "package_sha256": result["package_sha256"], "zip_sha256": result["zip_sha256"]},
                     indent=2))
