"""Release a frozen formal protocol from an audited U07 candidate package."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError

from experiment_protocol import load_protocol
from prepare_formal_freeze import REQUIRED_GATE_IDS, digest, read_json, relative, source_files
from run_local_experiments import validate_knowledge_snapshot

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "dvwa/local_experiment_protocol.json"
APPROVAL_SCHEMA_PATH = ROOT / "schemas/formal-freeze-approval.schema.json"
PLAN_SCHEMA_PATH = ROOT / "schemas/local-run-plan.schema.json"
RELEASE_GATE = "runtime-manifest-frozen"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def resolve_project_path(value: str | Path, field: str) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError(f"{field} must resolve inside the project workspace.")
    return resolved


def resolve_raw_path(value: str | Path, field: str) -> Path:
    path = resolve_project_path(value, field)
    if not path.is_relative_to((ROOT / "results/raw").resolve()):
        raise ValueError(f"{field} must stay under results/raw/.")
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with temporary.open("xb") as destination:
        destination.write(data)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: dict) -> None:
    atomic_write_bytes(path, json_bytes(value))


def git_value(*arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout.strip()


def file_hash_map() -> dict[str, str]:
    return {relative(path): digest(path) for path in source_files()}


def source_tree_hash(hashes: dict[str, str]) -> str:
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def check_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {relative(path)}")
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"{label} hash changed: {relative(path)}")


def verify_zip(path: Path, expected_hash: str, label: str) -> None:
    check_hash(path, expected_hash, label)
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"{label} is not a readable ZIP archive.") from error
    if bad_member is not None:
        raise ValueError(f"{label} CRC check failed at {bad_member}.")


def load_candidate(candidate_directory: Path) -> tuple[Path, dict]:
    directory = resolve_raw_path(candidate_directory, "--candidate-dir")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Candidate directory must contain manifest.json.")
    manifest = read_json(manifest_path)
    if manifest.get("scope") != "U07-formal-readiness-candidate":
        raise ValueError("Manifest is not a U07 formal-readiness candidate.")
    if manifest.get("formal_evaluation_executed") is not False:
        raise ValueError("Release candidate must not claim that formal evaluation ran.")
    if manifest.get("protocol_frozen") is not False or manifest.get("ready_for_formal") is not False:
        raise ValueError("Expected an unreleased candidate manifest with protocol_frozen=false.")
    return manifest_path, manifest


def verify_candidate(candidate_directory: Path) -> tuple[Path, dict, dict]:
    """Recheck the candidate's current bytes and all pre-release gate evidence."""
    manifest_path, manifest = load_candidate(candidate_directory)
    gates = manifest.get("gates")
    if not isinstance(gates, dict) or set(gates) != REQUIRED_GATE_IDS:
        raise ValueError("Candidate gate inventory does not match the required U07 gate set.")
    if gates.get(RELEASE_GATE, {}).get("status") != "pending":
        raise ValueError("Candidate must leave only runtime-manifest-frozen pending for release.")
    other_pending = sorted(gate_id for gate_id, gate in gates.items()
                           if gate_id != RELEASE_GATE and gate.get("status") != "passed")
    if other_pending:
        raise ValueError("Release blocked by pending gates: " + ", ".join(other_pending))

    if manifest.get("base_git_revision") != git_value("rev-parse", "HEAD"):
        raise ValueError("Candidate Git revision differs from HEAD. Regenerate readiness from the current commit.")
    if manifest.get("working_tree_status", "").strip() or git_value("status", "--porcelain=v1"):
        raise ValueError("Release requires the candidate source snapshot and current Git working tree to be clean.")

    source_hash_path = resolve_raw_path(manifest.get("source_hashes", ""), "source_hashes")
    source_hashes = read_json(source_hash_path)
    if not isinstance(source_hashes, dict) or source_tree_hash(source_hashes) != manifest.get("source_tree_sha256"):
        raise ValueError("Candidate source hash inventory does not match source_tree_sha256.")
    current_hashes = file_hash_map()
    if current_hashes != source_hashes:
        changed = sorted(name for name in set(current_hashes) | set(source_hashes)
                         if current_hashes.get(name) != source_hashes.get(name))
        raise ValueError("Candidate source snapshot changed: " + ", ".join(changed[:12]))

    protocol_record = manifest.get("protocol", {})
    protocol_path = resolve_project_path(protocol_record.get("path", ""), "protocol.path")
    check_hash(protocol_path, protocol_record.get("sha256", ""), "Candidate protocol")
    protocol = read_json(protocol_path)
    if protocol.get("status") != "pilot":
        raise ValueError("Candidate protocol must still be in pilot status before release.")

    plan_record = manifest.get("formal_plan", {})
    plan_path = resolve_project_path(plan_record.get("path", ""), "formal_plan.path")
    check_hash(plan_path, plan_record.get("sha256", ""), "Formal plan")
    plan = read_json(plan_path)
    Draft202012Validator(read_json(PLAN_SCHEMA_PATH)).validate(plan)
    if (plan.get("dataset") != "formal" or plan_record.get("applicable_runs") != 99
            or plan_record.get("by_condition") != {"A": 36, "B": 36, "C": 27}
            or plan_record.get("candidate_slots") != 990):
        raise ValueError("Candidate formal plan is not the approved 99-run, 990-candidate matrix.")
    knowledge = validate_knowledge_snapshot(plan.get("knowledge_snapshot", {}), ROOT)
    if (knowledge.get("index_file_sha256") != manifest.get("formal_knowledge_snapshot", {}).get("index_file_sha256")
            or knowledge.get("index_file_sha256") != manifest.get("knowledge", {}).get("index_file_sha256")
            or manifest.get("knowledge", {}).get("formal_use_decision") != "approved"):
        raise ValueError("Formal plan, current index, and approved corpus receipt do not identify the same snapshot.")

    if not manifest.get("offline_checks", {}).get("passed"):
        raise ValueError("The candidate's offline contract suite did not pass.")
    offline = manifest["offline_checks"]
    check_hash(resolve_raw_path(offline.get("log", ""), "offline_checks.log"),
               offline.get("log_sha256", ""), "Offline test log")
    lock = manifest.get("requirements_lock", {})
    check_hash(resolve_raw_path(lock.get("path", ""), "requirements_lock.path"),
               lock.get("sha256", ""), "Requirements lock")

    source_archive = manifest.get("source_archive", {})
    archive_path = resolve_raw_path(source_archive.get("path", ""), "source_archive.path")
    backup_path = resolve_raw_path(source_archive.get("backup_copy", ""), "source_archive.backup_copy")
    verify_zip(archive_path, source_archive.get("sha256", ""), "Candidate evidence archive")
    check_hash(backup_path, source_archive.get("backup_copy_sha256", ""), "Candidate evidence backup")
    if digest(backup_path) != digest(archive_path):
        raise ValueError("Candidate evidence archive and backup copy differ.")

    pilot = manifest.get("pilot", {})
    pilot_path = resolve_raw_path(pilot.get("path", ""), "pilot.path")
    ledger_path = pilot_path / "ledger.jsonl"
    plan_snapshot_path = pilot_path / "plan.snapshot.json"
    check_hash(ledger_path, pilot.get("ledger_sha256", ""), "Pilot ledger")
    check_hash(plan_snapshot_path, pilot.get("plan_snapshot_sha256", ""), "Pilot plan snapshot")
    if (pilot.get("run_count") != 36
            or pilot.get("status_counts") != {"completed": 33, "excluded": 3}
            or pilot.get("all_applicable_runs_metric_eligible") is not True
            or pilot.get("incomplete_runs")
            or pilot.get("retrieval_index_snapshot_pinned") is not True
            or pilot.get("retrieval_index_file_sha256") != knowledge.get("index_file_sha256")):
        raise ValueError("Pilot evidence is incomplete or does not pin the approved index bytes.")

    runtime = manifest.get("runtime", {})
    server_log = runtime.get("pilot_server_log", {})
    if (gates.get("context-and-runtime-preflight", {}).get("status") != "passed"
            or server_log.get("coverage_verified") is not True
            or server_log.get("positive_truncation_count") != 0
            or server_log.get("explicit_input_truncation_warnings") != 0):
        raise ValueError("Runtime preflight or Ollama log evidence is incomplete.")
    log_snapshot = server_log.get("snapshot_path")
    if not log_snapshot:
        raise ValueError("Candidate runtime package does not preserve its verified Ollama log.")
    check_hash(resolve_raw_path(log_snapshot, "pilot_server_log.snapshot_path"),
               server_log.get("sha256", ""), "Ollama server log")

    return manifest_path, manifest, protocol


def approval_template(manifest_path: Path, manifest: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "scope": "formal-protocol-freeze",
        "decision": "pending",
        "candidate_manifest_path": relative(manifest_path),
        "candidate_manifest_sha256": digest(manifest_path),
        "formal_plan_sha256": manifest["formal_plan"]["sha256"],
        "protocol_sha256": manifest["protocol"]["sha256"],
        "corpus_decision_sha256": manifest["knowledge"]["formal_decision_sha256"],
        "formal_execution_approval": False,
        "authority": None,
    }


def validate_approval(approval_path: Path, manifest_path: Path, manifest: dict) -> dict:
    path = resolve_raw_path(approval_path, "--approval")
    approval = read_json(path)
    Draft202012Validator(read_json(APPROVAL_SCHEMA_PATH)).validate(approval)
    expected = approval_template(manifest_path, manifest)
    for key in ("scope", "candidate_manifest_path", "candidate_manifest_sha256",
                "formal_plan_sha256", "protocol_sha256", "corpus_decision_sha256",
                "formal_execution_approval"):
        if approval.get(key) != expected[key]:
            raise ValueError(f"Freeze approval does not match the current candidate field {key}.")
    if approval.get("decision") != "approved-for-formal-freeze":
        raise ValueError("Freeze approval must contain decision=approved-for-formal-freeze.")
    return approval


def frozen_protocol_bytes(protocol_path: Path, protocol: dict, approval_path: Path,
                          approval_sha256: str, candidate_manifest_path: Path,
                          candidate_manifest_sha256: str, release_manifest_path: Path) -> bytes:
    original = protocol_path.read_text(encoding="utf-8")
    replacements = (
        ('"status": "pilot"', '"status": "frozen"'),
        ('"implementation_readiness": {"local_langchain": "pending"}',
         '"implementation_readiness": {"local_langchain": "verified"}'),
        ('"independent_validator": "pending"', '"independent_validator": "ready"'),
    )
    updated = original
    for before, after in replacements:
        if updated.count(before) != 1:
            raise ValueError("Protocol format changed; refusing an ambiguous freeze update: " + before)
        updated = updated.replace(before, after, 1)
    marker = '  "formal_gate": ['
    if updated.count(marker) != 1:
        raise ValueError("Protocol does not contain one formal_gate field for the release receipt.")
    release_record = {
        "approval_path": relative(approval_path),
        "approval_sha256": approval_sha256,
        "candidate_manifest_path": relative(candidate_manifest_path),
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "release_manifest_path": relative(release_manifest_path),
    }
    release_line = "  \"formal_freeze_release\": " + json.dumps(
        release_record, ensure_ascii=False, separators=(",", ":")) + ",\n"
    updated = updated.replace(marker, release_line + marker, 1)
    parsed = json.loads(updated)
    if parsed.get("status") != "frozen":
        raise ValueError("Prepared protocol did not enter frozen status.")
    return updated.encode("utf-8")


def build_release_package(candidate_directory: Path, manifest_path: Path, manifest: dict,
                          protocol: dict, approval_path: Path, approval: dict) -> dict:
    release_manifest_path = candidate_directory / "formal-release-manifest.json"
    release_protocol_path = candidate_directory / "local-experiment-protocol.frozen.json"
    before_protocol_path = candidate_directory / "local-experiment-protocol.before-freeze.json"
    hashes_path = candidate_directory / "released-source-file-sha256.json"
    evidence_zip_path = candidate_directory / "formal-release-evidence.zip"
    temporary_protocol = candidate_directory / ".frozen-protocol-validation.json"
    outputs = (release_manifest_path, release_protocol_path, before_protocol_path,
               hashes_path, evidence_zip_path, temporary_protocol)
    if any(path.exists() for path in outputs):
        raise ValueError("Release output already exists. Preserve it and use a new candidate package.")

    source_archive = manifest["source_archive"]
    backup_directory = resolve_raw_path(source_archive["backup_copy"], "source_archive.backup_copy").parent
    backup_zip = backup_directory / "formal-release-evidence.zip"
    if backup_zip.exists():
        raise ValueError("Formal release evidence backup already exists. Preserve it and use a new candidate package.")

    approval_path = resolve_raw_path(approval_path, "--approval")
    approval_hash = digest(approval_path)
    protocol_bytes = frozen_protocol_bytes(
        PROTOCOL_PATH, protocol, approval_path, approval_hash,
        manifest_path, digest(manifest_path), release_manifest_path)
    frozen_protocol = json.loads(protocol_bytes)
    atomic_write_bytes(temporary_protocol, protocol_bytes)
    try:
        load_protocol(temporary_protocol)
    finally:
        temporary_protocol.unlink(missing_ok=True)

    source_hashes = read_json(resolve_raw_path(manifest["source_hashes"], "source_hashes"))
    released_hashes = dict(source_hashes)
    protocol_rel = relative(PROTOCOL_PATH)
    if protocol_rel not in released_hashes:
        raise ValueError("Candidate source inventory does not include the active protocol.")
    released_hashes[protocol_rel] = sha256_bytes(protocol_bytes)
    hashes_bytes = json_bytes(released_hashes)
    atomic_write_bytes(release_protocol_path, protocol_bytes)
    atomic_write_bytes(before_protocol_path, PROTOCOL_PATH.read_bytes())
    atomic_write_bytes(hashes_path, hashes_bytes)

    evidence_inputs = {
        manifest_path: relative(manifest_path),
        resolve_raw_path(source_archive["path"], "source_archive.path"): source_archive["path"],
        approval_path: relative(approval_path),
        release_protocol_path: relative(release_protocol_path),
        before_protocol_path: relative(before_protocol_path),
        hashes_path: relative(hashes_path),
    }
    for key in ("log",):
        value = manifest.get("offline_checks", {}).get(key)
        if value:
            path = resolve_raw_path(value, "offline_checks.log")
            evidence_inputs[path] = relative(path)
    lock_path = resolve_raw_path(manifest["requirements_lock"]["path"], "requirements_lock.path")
    evidence_inputs[lock_path] = relative(lock_path)
    runtime_path = candidate_directory / "runtime.json"
    if runtime_path.is_file():
        evidence_inputs[runtime_path] = relative(runtime_path)

    temporary_zip = evidence_zip_path.with_name(evidence_zip_path.name + "." + uuid4().hex + ".tmp")
    with zipfile.ZipFile(temporary_zip, "x", zipfile.ZIP_DEFLATED) as archive:
        for source, arcname in sorted(evidence_inputs.items(), key=lambda item: item[1]):
            archive.write(source, arcname)
    with zipfile.ZipFile(temporary_zip) as archive:
        if archive.testzip() is not None:
            temporary_zip.unlink(missing_ok=True)
            raise ValueError("Formal release evidence archive failed CRC validation.")
    os.replace(temporary_zip, evidence_zip_path)
    evidence_zip_hash = digest(evidence_zip_path)
    shutil.copyfile(evidence_zip_path, backup_zip)
    if digest(backup_zip) != evidence_zip_hash:
        backup_zip.unlink(missing_ok=True)
        raise ValueError("Formal release evidence backup hash mismatch.")

    gates = copy.deepcopy(manifest["gates"])
    gates[RELEASE_GATE] = {
        "status": "passed",
        "evidence": relative(release_manifest_path),
        "reason": "All other readiness gates passed and the researcher approved this exact candidate manifest for protocol freeze.",
    }
    if any(gate.get("status") != "passed" for gate in gates.values()):
        raise ValueError("Not all required gates passed after applying the release decision.")

    return {
        "schema_version": "1.0.0",
        "scope": "formal-protocol-freeze-release",
        "status": "released",
        "release_id": manifest["formal_plan"]["path"].rsplit("/", 1)[-1].removesuffix(".json") + "-freeze",
        "released_at_utc": datetime.now(timezone.utc).isoformat(),
        "ready_for_formal": True,
        "protocol_frozen": True,
        "formal_evaluation_executed": False,
        "formal_execution_authorized": False,
        "candidate": {
            "manifest_path": relative(manifest_path),
            "manifest_sha256": digest(manifest_path),
            "source_tree_sha256": manifest["source_tree_sha256"],
            "git_revision": manifest["base_git_revision"],
        },
        "approval": {
            "path": relative(approval_path),
            "sha256": approval_hash,
            "decision": approval["decision"],
            "authority": approval["authority"],
            "formal_execution_approval": False,
        },
        "formal_plan": manifest["formal_plan"],
        "pilot": manifest["pilot"],
        "corpus": {
            "decision_path": manifest["knowledge"]["formal_decision_path"],
            "decision_sha256": manifest["knowledge"]["formal_decision_sha256"],
            "corpus_sha256": manifest["knowledge"]["corpus_sha256"],
            "source_lock_sha256": manifest["knowledge"]["source_lock_sha256"],
            "index_file_sha256": manifest["knowledge"]["index_file_sha256"],
        },
        "runtime_preflight": {
            "passed": gates["context-and-runtime-preflight"]["status"] == "passed",
            "pilot_server_log": manifest["runtime"]["pilot_server_log"],
        },
        "requirements_lock": manifest["requirements_lock"],
        "offline_checks": manifest["offline_checks"],
        "source_archive": {
            "path": source_archive["path"],
            "sha256": source_archive["sha256"],
            "backup_copy": source_archive["backup_copy"],
            "backup_copy_sha256": source_archive["backup_copy_sha256"],
        },
        "released_source_snapshot": {
            "path": relative(hashes_path),
            "sha256": digest(hashes_path),
            "source_tree_sha256": source_tree_hash(released_hashes),
        },
        "release_evidence_archive": {
            "path": relative(evidence_zip_path),
            "sha256": evidence_zip_hash,
            "backup_copy": relative(backup_zip),
            "backup_copy_sha256": digest(backup_zip),
            "crc_verified": True,
        },
        "protocol": {
            "path": relative(PROTOCOL_PATH),
            "before_sha256": manifest["protocol"]["sha256"],
            "after_sha256": sha256_bytes(protocol_bytes),
            "status": "frozen",
            "snapshot_path": relative(release_protocol_path),
            "snapshot_sha256": digest(release_protocol_path),
            "snapshot": frozen_protocol,
        },
        "gates": gates,
    }


def release(candidate_directory: Path, approval_path: Path) -> dict:
    candidate_directory = resolve_raw_path(candidate_directory, "--candidate-dir")
    manifest_path, manifest, protocol = verify_candidate(candidate_directory)
    approval_path = resolve_raw_path(approval_path, "--approval")
    approval = validate_approval(approval_path, manifest_path, manifest)
    release_manifest_path = candidate_directory / "formal-release-manifest.json"
    output_paths = (release_manifest_path,
                    candidate_directory / "local-experiment-protocol.frozen.json",
                    candidate_directory / "local-experiment-protocol.before-freeze.json",
                    candidate_directory / "released-source-file-sha256.json",
                    candidate_directory / "formal-release-evidence.zip",
                    candidate_directory / ".frozen-protocol-validation.json")
    backup = resolve_raw_path(manifest["source_archive"]["backup_copy"],
                              "source_archive.backup_copy").parent / "formal-release-evidence.zip"
    if any(path.exists() for path in output_paths):
        raise ValueError("Release output already exists. Preserve it and use a new candidate package.")
    if backup.exists():
        raise ValueError("Formal release evidence backup already exists. Preserve it and use a new candidate package.")
    before_bytes = PROTOCOL_PATH.read_bytes()
    try:
        release_record = build_release_package(candidate_directory, manifest_path, manifest,
                                               protocol, approval_path, approval)
        frozen_bytes = (candidate_directory / "local-experiment-protocol.frozen.json").read_bytes()
        atomic_write_bytes(PROTOCOL_PATH, frozen_bytes)
        if digest(PROTOCOL_PATH) != release_record["protocol"]["after_sha256"]:
            raise ValueError("Active protocol hash differs from the staged release snapshot.")
        atomic_write_json(release_manifest_path, release_record)
        load_protocol(PROTOCOL_PATH)
    except Exception:
        if PROTOCOL_PATH.read_bytes() != before_bytes:
            atomic_write_bytes(PROTOCOL_PATH, before_bytes)
        for artifact in output_paths:
            artifact.unlink(missing_ok=True)
            for temporary in candidate_directory.glob(artifact.name + ".*.tmp"):
                temporary.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        raise
    return release_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True,
                        help="U07 readiness candidate directory under results/raw/.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="Audit release prerequisites without writing or freezing.")
    modes.add_argument("--write-approval-template", action="store_true",
                       help="Write a pending researcher approval template after all evidence gates pass.")
    modes.add_argument("--release", action="store_true",
                       help="Freeze the protocol using a matching explicit researcher approval receipt.")
    parser.add_argument("--approval", type=Path,
                        help="Researcher-authored formal-freeze approval JSON under results/raw/.")
    args = parser.parse_args()

    if args.approval and not args.release:
        parser.error("--approval can be used only with --release.")
    if args.release and not args.approval:
        parser.error("--release requires --approval.")

    try:
        if args.release:
            result = release(args.candidate_dir, args.approval)
            print(json.dumps({"status": result["status"], "ready_for_formal": True,
                              "protocol_frozen": True, "formal_execution_authorized": False,
                              "release_manifest": relative(resolve_raw_path(args.candidate_dir, "--candidate-dir")
                                                           / "formal-release-manifest.json")}, indent=2))
            return

        manifest_path, manifest, _ = verify_candidate(args.candidate_dir)
        if args.write_approval_template:
            output = manifest_path.parent / "formal-freeze-approval.json"
            if output.exists():
                raise ValueError("Approval file already exists. Preserve it and choose a new candidate package.")
            template = approval_template(manifest_path, manifest)
            Draft202012Validator(read_json(APPROVAL_SCHEMA_PATH)).validate(template)
            atomic_write_json(output, template)
            print(json.dumps({"template": relative(output), "decision": "pending",
                              "candidate_manifest_sha256": template["candidate_manifest_sha256"],
                              "formal_execution_approval": False}, indent=2))
            return

        print(json.dumps({"releaseable": True,
                          "candidate_manifest": relative(manifest_path),
                          "candidate_manifest_sha256": digest(manifest_path),
                          "formal_plan_sha256": manifest["formal_plan"]["sha256"],
                          "protocol_sha256": manifest["protocol"]["sha256"],
                          "formal_execution_authorized": False}, indent=2))
    except (OSError, ValueError, KeyError, ValidationError,
            zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
