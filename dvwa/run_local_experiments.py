"""Plan, execute, and resume bounded experiments against the local DVWA only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError

from confirmation_policy import CONFIRMATION_POLICY_ID, classify_confirmations
from adaptive_candidate_policy import candidate_probe_payload
from analyze_response import trial_rule_signals
from execution_order_policy import ordered_run_slots
from experiment_protocol import DEFAULT_PROTOCOL, load_protocol
from prepare_candidate_batch import validate_batch
from rag_pipeline import load_catalog
from validation_loop import (ROOT, emit_candidate_evidence, require_local_target,
                             validate_candidates)


PLAN_SCHEMA_VERSION = "1.0.0"
PROTOCOL_SNAPSHOT_PATH = DEFAULT_PROTOCOL
CONDITION_IDS = {"A", "B", "C"}


class ExecutionFailure(RuntimeError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        document = json.load(source)
    if not isinstance(document, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return document


def resolve_project_path(value: str | Path, root: Path, field: str) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"{field} must resolve inside the project workspace.")
    return resolved


def validate_knowledge_snapshot(snapshot: dict, root: Path = ROOT, *, verify_index: bool = True) -> dict:
    """Pin a plan to a reviewed local RAG manifest, corpus, and decision receipt."""
    legacy_fields = {"manifest_path", "manifest_sha256", "corpus_path", "corpus_sha256",
                     "review_decision_path", "review_decision_sha256"}
    pinned_fields = legacy_fields | {"source_lock_path", "source_lock_sha256", "index_file_sha256"}
    if not isinstance(snapshot, dict) or set(snapshot) not in (legacy_fields, pinned_fields):
        raise ValueError("knowledge_snapshot must pin manifest, corpus, and review decision paths and hashes.")
    is_index_pinned = set(snapshot) == pinned_fields
    path_fields = ["manifest_path", "corpus_path", "review_decision_path"]
    hash_fields = [("manifest_sha256", "manifest_path"), ("corpus_sha256", "corpus_path"),
                   ("review_decision_sha256", "review_decision_path")]
    if is_index_pinned:
        path_fields.append("source_lock_path")
        hash_fields.append(("source_lock_sha256", "source_lock_path"))
    resolved = {field: resolve_project_path(snapshot[field], root, f"knowledge_snapshot.{field}")
                for field in path_fields}
    for hash_field, path_field in hash_fields:
        expected = snapshot[hash_field]
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError(f"knowledge_snapshot.{hash_field} must be a SHA-256 hash.")
        if not resolved[path_field].is_file() or sha256_file(resolved[path_field]) != expected:
            raise ValueError(f"knowledge_snapshot {path_field} is missing or its hash changed.")

    manifest = read_json(resolved["manifest_path"])
    corpus = read_json(resolved["corpus_path"])
    decision = read_json(resolved["review_decision_path"])
    manifest_corpus = resolve_project_path(manifest.get("corpus_path", ""), root,
                                           "knowledge manifest corpus_path")
    store_value = manifest.get("store_path", "")
    store_path = resolve_project_path(store_value, root, "knowledge manifest store_path")
    vectorstore_root = (root / "data" / "vectorstore").resolve()
    if not store_path.is_relative_to(vectorstore_root):
        raise ValueError("Knowledge manifest store_path must stay under data/vectorstore/.")
    if (manifest_corpus != resolved["corpus_path"]
            or manifest.get("corpus_sha256") != snapshot["corpus_sha256"]
            or manifest.get("corpus_kind") != "structured-sqli-knowledge-v1"
            or manifest.get("purpose") != "proposal-rag"):
        raise ValueError("knowledge_snapshot manifest does not identify the pinned proposal corpus.")
    if is_index_pinned:
        if manifest.get("source_lock_sha256") != snapshot["source_lock_sha256"]:
            raise ValueError("knowledge_snapshot manifest does not identify the pinned source lock.")
        expected_index = snapshot["index_file_sha256"]
        if not isinstance(expected_index, dict) or not expected_index:
            raise ValueError("knowledge_snapshot.index_file_sha256 must pin every active Chroma file.")
        observed_index = {}
        for relative_path, expected_hash in expected_index.items():
            if not isinstance(relative_path, str):
                raise ValueError("knowledge_snapshot.index_file_sha256 contains an invalid path or hash.")
            candidate = Path(relative_path)
            if (candidate.is_absolute() or ".." in candidate.parts
                    or not isinstance(expected_hash, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)):
                raise ValueError("knowledge_snapshot.index_file_sha256 contains an invalid path or hash.")
            resolved_index = resolve_project_path(relative_path, root, "knowledge_snapshot index file")
            if not resolved_index.is_relative_to(store_path) or not resolved_index.is_file():
                raise ValueError("knowledge_snapshot index file must exist inside the pinned Chroma store.")
            observed_index[relative_path.replace("\\", "/")] = sha256_file(resolved_index)
        active_index = {path.relative_to(root).as_posix(): sha256_file(path)
                        for path in store_path.rglob("*") if path.is_file()}
        if verify_index and (observed_index != expected_index or active_index != expected_index):
            raise ValueError("knowledge_snapshot index_file_sha256 differs from the active Chroma store.")
    candidate_decisions = {"approved-for-generation-only-preflight", "approved-for-pilot-use"}
    if decision.get("decision") in candidate_decisions:
        common_candidate_checks = (
            decision.get("candidate_corpus_sha256") == snapshot["corpus_sha256"]
            and decision.get("formal_experiment_approval") is False
        )
        corpus_reviewed = corpus.get("curation", {}).get("researcher_review") == "reviewed"
        if decision.get("decision") == "approved-for-generation-only-preflight":
            if not common_candidate_checks or not corpus_reviewed:
                raise ValueError("knowledge_snapshot review decision does not match the corpus or its permitted use.")
        elif corpus_reviewed:
            # Preserve compatibility with pilot receipts for corpora whose review flag is already pinned.
            if not common_candidate_checks:
                raise ValueError("knowledge_snapshot review decision does not match the corpus or its permitted use.")
        else:
            # A receipt may carry the researcher's review attestation when changing the shared corpus metadata
            # would invalidate a separately approved formal snapshot. Bind that attestation to the full index.
            if not is_index_pinned:
                raise ValueError("A pilot receipt for an unreviewed corpus must pin the source lock and full index.")
            authority = decision.get("authority", {})
            expected_approval = {"corpus_sha256": snapshot["corpus_sha256"],
                                 "source_lock_sha256": snapshot["source_lock_sha256"],
                                 "knowledge_base_id": manifest.get("knowledge_base_id"),
                                 "entry_count": manifest.get("entry_count"),
                                 "index_file_sha256": snapshot["index_file_sha256"]}
            if (not common_candidate_checks
                    or decision.get("schema_version") != "1.0.0"
                    or decision.get("researcher_review_status") != "reviewed"
                    or authority.get("role") != "researcher"
                    or authority.get("basis") != "explicit-user-approval"
                    or not isinstance(authority.get("quote"), str)
                    or not authority["quote"].strip()
                    or decision.get("approved_snapshot") != expected_approval):
                raise ValueError("knowledge_snapshot pilot receipt must attest researcher review and match the pinned corpus and index.")
    elif decision.get("decision") == "approved-for-formal-use" and is_index_pinned:
        authority = decision.get("authority", {})
        expected_approval = {"corpus_sha256": snapshot["corpus_sha256"],
                             "source_lock_sha256": snapshot["source_lock_sha256"],
                             "knowledge_base_id": manifest.get("knowledge_base_id"),
                             "entry_count": manifest.get("entry_count"),
                             "index_file_sha256": snapshot["index_file_sha256"]}
        if (decision.get("schema_version") != "1.0.0"
                or decision.get("scope") != "main-nine-entry-corpus-formal-use-after-u07-gates"
                or authority.get("role") != "researcher"
                or authority.get("basis") != "explicit-user-approval"
                or decision.get("formal_execution_approval") is not False
                or decision.get("approved_snapshot") != expected_approval):
            raise ValueError("knowledge_snapshot formal receipt does not match the pinned corpus and index.")
    else:
        raise ValueError("knowledge_snapshot review decision does not match the corpus or its permitted use.")
    resolved_paths = {f"{field}_resolved": resolved[field] for field in path_fields}
    return {**snapshot, **resolved_paths, "knowledge_base_id": manifest.get("knowledge_base_id"),
            "store_path_resolved": store_path}


def validate_formal_execution_approval(approval_path: Path, plan_path: Path, plan: dict,
                                       protocol: dict, root: Path = ROOT, *,
                                       runner_amendment: dict | None = None) -> dict:
    """Verify an explicit execution receipt against this plan and active frozen release."""
    if plan.get("dataset") != "formal" or protocol.get("status") != "frozen":
        raise ValueError("Formal execution approval is valid only for a frozen formal plan.")
    release_record = protocol.get("formal_freeze_release", {})
    release_value = release_record.get("release_manifest_path")
    if not isinstance(release_value, str) or not release_value:
        raise ValueError("The active frozen protocol does not pin a formal release manifest.")
    release_path = resolve_project_path(release_value, root, "formal_freeze_release.release_manifest_path")
    if not release_path.is_file():
        raise ValueError("The formal release manifest pinned by the protocol is missing.")
    release_hash = sha256_file(release_path)
    release = read_json(release_path)
    if (release.get("scope") != "formal-protocol-freeze-release"
            or release.get("status") != "released"
            or release.get("ready_for_formal") is not True
            or release.get("protocol_frozen") is not True
            or release.get("formal_evaluation_executed") is not False
            or release.get("formal_execution_authorized") is not False
            or not isinstance(release.get("gates"), dict)
            or not release["gates"]
            or any(gate.get("status") != "passed" for gate in release["gates"].values())):
        raise ValueError("The pinned release manifest is not a complete, unreleased formal package.")

    release_rel = release_path.relative_to(root.resolve()).as_posix()
    if release_record.get("release_manifest_path") != release_rel:
        raise ValueError("Active protocol and release manifest paths disagree.")
    freeze_approval = release.get("approval", {})
    if (freeze_approval.get("path") != release_record.get("approval_path")
            or freeze_approval.get("sha256") != release_record.get("approval_sha256")
            or freeze_approval.get("formal_execution_approval") is not False
            or freeze_approval.get("decision") != "approved-for-formal-freeze"):
        raise ValueError("Freeze approval in the release differs from the active protocol receipt.")
    freeze_approval_path = resolve_project_path(freeze_approval.get("path", ""), root,
                                                "release.approval.path")
    if not freeze_approval_path.is_file() or sha256_file(freeze_approval_path) != freeze_approval.get("sha256"):
        raise ValueError("Researcher freeze approval receipt is missing or changed.")
    freeze_approval_value = read_json(freeze_approval_path)
    freeze_schema = read_json(root / "schemas/formal-freeze-approval.schema.json")
    Draft202012Validator(freeze_schema).validate(freeze_approval_value)
    candidate_record = release.get("candidate", {})
    if (freeze_approval_value.get("decision") != "approved-for-formal-freeze"
            or freeze_approval_value.get("formal_execution_approval") is not False
            or freeze_approval_value.get("candidate_manifest_path") != candidate_record.get("manifest_path")
            or freeze_approval_value.get("candidate_manifest_sha256") != candidate_record.get("manifest_sha256")
            or freeze_approval_value.get("formal_plan_sha256") != release.get("formal_plan", {}).get("sha256")
            or freeze_approval_value.get("protocol_sha256") != release.get("protocol", {}).get("before_sha256")
            or candidate_record.get("manifest_path") != release_record.get("candidate_manifest_path")
            or candidate_record.get("manifest_sha256") != release_record.get("candidate_manifest_sha256")):
        raise ValueError("Freeze approval does not bind the released candidate package.")
    candidate_path = resolve_project_path(candidate_record.get("manifest_path", ""), root,
                                          "release.candidate.manifest_path")
    if not candidate_path.is_file() or sha256_file(candidate_path) != candidate_record.get("manifest_sha256"):
        raise ValueError("Released candidate manifest is missing or changed.")
    candidate = read_json(candidate_path)
    if (candidate.get("scope") != "U07-formal-readiness-candidate"
            or candidate.get("protocol", {}).get("sha256") != release.get("protocol", {}).get("before_sha256")
            or candidate.get("protocol", {}).get("status") != "pilot"
            or candidate.get("source_tree_sha256") != candidate_record.get("source_tree_sha256")
            or candidate.get("formal_evaluation_executed") is not False
            or candidate.get("protocol_frozen") is not False):
        raise ValueError("Released candidate does not match the pre-freeze protocol snapshot.")
    candidate_gates = candidate.get("gates", {})
    release_gates = release.get("gates", {})
    if (not isinstance(candidate_gates, dict) or set(candidate_gates) != set(release_gates)
            or [gate_id for gate_id, gate in candidate_gates.items()
                if gate.get("status") != "passed"] != ["runtime-manifest-frozen"]
            or any(gate.get("status") != "passed" for gate in release_gates.values())):
        raise ValueError("Candidate and release gate inventories do not show a complete U07 freeze.")

    def verify_pinned_file(path_value: str, expected_hash: str, label: str) -> Path:
        path = resolve_project_path(path_value, root, label)
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ValueError(f"Released {label} is missing or changed.")
        return path

    source_archive = release.get("source_archive", {})
    source_archive_path = verify_pinned_file(source_archive.get("path", ""),
                                             source_archive.get("sha256", ""), "source_archive.path")
    source_archive_backup = verify_pinned_file(source_archive.get("backup_copy", ""),
                                               source_archive.get("backup_copy_sha256", ""),
                                               "source_archive.backup_copy")
    if sha256_file(source_archive_path) != sha256_file(source_archive_backup):
        raise ValueError("Candidate source archive and backup copy differ.")
    try:
        with zipfile.ZipFile(source_archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Candidate source archive failed CRC validation.")
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("Candidate source archive is not readable.") from error

    requirements_lock = release.get("requirements_lock", {})
    verify_pinned_file(requirements_lock.get("path", ""), requirements_lock.get("sha256", ""),
                       "requirements_lock.path")
    offline_checks = release.get("offline_checks", {})
    verify_pinned_file(offline_checks.get("log", ""), offline_checks.get("log_sha256", ""),
                       "offline_checks.log")
    pilot = release.get("pilot", {})
    pilot_directory = resolve_project_path(pilot.get("path", ""), root, "release.pilot.path")
    if not pilot_directory.is_relative_to((root / "results/raw/pilot").resolve()):
        raise ValueError("Released pilot evidence must remain under results/raw/pilot/.")
    verify_pinned_file(str(pilot_directory / "ledger.jsonl"), pilot.get("ledger_sha256", ""),
                       "pilot.ledger")
    verify_pinned_file(str(pilot_directory / "plan.snapshot.json"), pilot.get("plan_snapshot_sha256", ""),
                       "pilot.plan_snapshot")
    pilot_server_log = release.get("runtime_preflight", {}).get("pilot_server_log", {})
    if release.get("runtime_preflight", {}).get("passed") is not True:
        raise ValueError("Formal release does not record a passed runtime preflight.")
    verify_pinned_file(pilot_server_log.get("snapshot_path", ""), pilot_server_log.get("sha256", ""),
                       "runtime_preflight.pilot_server_log")

    release_archive = release.get("release_evidence_archive", {})
    archive_path = resolve_project_path(release_archive.get("path", ""), root,
                                        "release.release_evidence_archive.path")
    backup_path = resolve_project_path(release_archive.get("backup_copy", ""), root,
                                       "release.release_evidence_archive.backup_copy")
    if (release_archive.get("crc_verified") is not True
            or not archive_path.is_file() or sha256_file(archive_path) != release_archive.get("sha256")
            or not backup_path.is_file() or sha256_file(backup_path) != release_archive.get("backup_copy_sha256")
            or sha256_file(archive_path) != sha256_file(backup_path)):
        raise ValueError("Formal release evidence archive or backup is missing or changed.")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Formal release evidence archive failed CRC validation.")
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("Formal release evidence archive is not readable.") from error

    active_protocol_hash = sha256_file(root / Path("dvwa/local_experiment_protocol.json"))
    protocol_release = release.get("protocol", {})
    protocol_snapshot_path = resolve_project_path(protocol_release.get("snapshot_path", ""), root,
                                                  "release.protocol.snapshot_path")
    if (protocol_release.get("path") != "dvwa/local_experiment_protocol.json"
            or protocol_release.get("after_sha256") != active_protocol_hash
            or protocol_release.get("snapshot_sha256") != active_protocol_hash
            or not protocol_snapshot_path.is_file()
            or sha256_file(protocol_snapshot_path) != active_protocol_hash):
        raise ValueError("Active protocol bytes do not match the released protocol snapshot.")

    plan_resolved = plan_path.resolve()
    plan_rel = plan_resolved.relative_to(root.resolve()).as_posix()
    plan_file_hash = sha256_file(plan_resolved)
    release_plan = release.get("formal_plan", {})
    if (release_plan.get("path") != plan_rel
            or release_plan.get("sha256") != plan_file_hash):
        raise ValueError("The formal plan does not match the plan pinned in the release manifest.")
    plan_knowledge = plan.get("knowledge_snapshot", {})
    release_corpus = release.get("corpus", {})
    candidate_knowledge = candidate.get("knowledge", {})
    candidate_snapshot = candidate.get("formal_knowledge_snapshot", {})
    if (release_corpus.get("decision_path") != plan_knowledge.get("review_decision_path")
            or release_corpus.get("decision_sha256") != plan_knowledge.get("review_decision_sha256")
            or release_corpus.get("corpus_sha256") != plan_knowledge.get("corpus_sha256")
            or release_corpus.get("source_lock_sha256") != plan_knowledge.get("source_lock_sha256")
            or release_corpus.get("index_file_sha256") != plan_knowledge.get("index_file_sha256")
            or candidate_knowledge.get("formal_use_decision") != "approved"
            or candidate_knowledge.get("formal_decision_path") != release_corpus.get("decision_path")
            or candidate_knowledge.get("formal_decision_sha256") != release_corpus.get("decision_sha256")
            or candidate_snapshot.get("review_decision_sha256") != release_corpus.get("decision_sha256")
            or candidate_snapshot.get("source_lock_sha256") != release_corpus.get("source_lock_sha256")
            or candidate_snapshot.get("index_file_sha256") != release_corpus.get("index_file_sha256")):
        raise ValueError("Formal plan corpus receipt and index do not match the released U07 snapshot.")

    snapshot = release.get("released_source_snapshot", {})
    source_hash_path = resolve_project_path(snapshot.get("path", ""), root,
                                            "release.released_source_snapshot.path")
    if not source_hash_path.is_file() or sha256_file(source_hash_path) != snapshot.get("sha256"):
        raise ValueError("Released source hash inventory is missing or changed.")
    with source_hash_path.open("r", encoding="utf-8") as source:
        source_hashes = json.load(source)
    if not isinstance(source_hashes, dict):
        raise ValueError("Released source hash inventory must be a JSON object.")
    encoded_hashes = json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if sha256_bytes(encoded_hashes) != snapshot.get("source_tree_sha256"):
        raise ValueError("Released source tree digest does not match its inventory.")
    current_source_hashes = source_snapshot_hashes(root)
    if runner_amendment is not None:
        # The original release stays immutable; only this explicitly bound runner may differ.
        runner = "dvwa/run_local_experiments.py"
        if source_hashes.get(runner) != runner_amendment["runner_before_sha256"]:
            raise ValueError("Runner amendment does not start from the released runner.")
        source_hashes = {**source_hashes, runner: runner_amendment["runner_after_sha256"]}
    if current_source_hashes != source_hashes:
        differences = sorted(name for name in set(current_source_hashes) | set(source_hashes)
                             if current_source_hashes.get(name) != source_hashes.get(name))
        raise ValueError("Source inventory differs from the formal release snapshot: "
                         + ", ".join(differences[:12]))

    approval_resolved = resolve_project_path(approval_path, root, "--formal-execution-approval")
    if not approval_resolved.is_file():
        raise ValueError("Formal execution approval receipt does not exist.")
    approval = read_json(approval_resolved)
    schema = read_json(root / "schemas/formal-execution-approval.schema.json")
    Draft202012Validator(schema).validate(approval)
    approval_rel = approval_resolved.relative_to(root.resolve()).as_posix()
    if runner_amendment is not None and (
            approval_rel != runner_amendment["original_execution_approval_path"]
            or sha256_file(approval_resolved) != runner_amendment["original_execution_approval_sha256"]):
        raise ValueError("Runner amendment must retain the original execution approval.")
    if (approval.get("decision") != "approved-for-formal-execution"
            or approval.get("experiment_id") != plan.get("experiment_id")
            or approval.get("formal_plan_path") != plan_rel
            or approval.get("formal_plan_sha256") != plan_file_hash
            or approval.get("release_manifest_path") != release_rel
            or approval.get("release_manifest_sha256") != release_hash
            or approval.get("formal_execution_approval") is not True):
        raise ValueError("Formal execution approval does not match this experiment, plan, and release.")
    return {
        "scope": approval["scope"],
        "decision": approval["decision"],
        "formal_execution_approval": True,
        "experiment_id": approval["experiment_id"],
        "formal_plan_path": plan_rel,
        "formal_plan_sha256": plan_file_hash,
        "release_manifest_path": release_rel,
        "release_manifest_sha256": release_hash,
        "approval_path": approval_rel,
        "approval_sha256": sha256_file(approval_resolved),
        "authority": approval["authority"],
    }


def adaptive_manifest_args(plan: dict, unit: dict, root: Path = ROOT) -> list[str]:
    """Return a hash-checked manifest override for the planned RAG-on run only."""
    if unit.get("condition_id") != "B" or plan.get("knowledge_snapshot") is None:
        return []
    snapshot = validate_knowledge_snapshot(plan["knowledge_snapshot"], root)
    return ["--manifest", str(snapshot["manifest_path_resolved"])]


def validate_plan(plan: dict, protocol: dict, root: Path = ROOT, *, verify_index: bool = True) -> dict:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(f"plan schema_version must be {PLAN_SCHEMA_VERSION}.")
    experiment_id = plan.get("experiment_id")
    if not isinstance(experiment_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", experiment_id):
        raise ValueError("experiment_id must be a 1-32 character lowercase slug.")
    dataset = plan.get("dataset")
    if dataset not in {"pilot", "formal"}:
        raise ValueError("dataset must be pilot or formal.")
    if dataset == "formal" and protocol.get("status") != "frozen":
        raise ValueError("Formal dataset execution is blocked until the protocol is frozen.")
    replication = protocol.get("replication", {})
    if (replication.get("fresh_login_each_run") is not True
            or replication.get("reset") != "dvwa-setup-http-before-each-condition-run"):
        raise ValueError("Each condition-run must begin with a fresh login and the configured DVWA database reset.")

    condition_ids = plan.get("condition_ids")
    scenario_ids = plan.get("scenario_ids")
    replicates = plan.get("replicates")
    if (not isinstance(condition_ids, list) or not condition_ids
            or len(set(condition_ids)) != len(condition_ids)
            or any(item not in CONDITION_IDS for item in condition_ids)):
        raise ValueError("condition_ids must be a non-empty unique subset of A, B, and C.")
    if (not isinstance(scenario_ids, list) or not scenario_ids
            or len(set(scenario_ids)) != len(scenario_ids)):
        raise ValueError("scenario_ids must be a non-empty unique list.")
    catalog = load_catalog()
    scenario_map = {item["scenario_id"]: item for item in catalog["scenarios"]}
    if any(item not in scenario_map for item in scenario_ids):
        raise ValueError("scenario_ids must refer to the experiment scenario catalog.")
    if (not isinstance(replicates, list) or not replicates
            or any(type(item) is not int or item not in {1, 2, 3} for item in replicates)
            or len(set(replicates)) != len(replicates)):
        raise ValueError("replicates must be a non-empty unique subset of 1, 2, and 3.")

    discovery_reports = plan.get("discovery_reports", {})
    if not isinstance(discovery_reports, dict):
        raise ValueError("discovery_reports must map each scenario ID to replicate paths.")
    resolved_reports = {}
    for scenario_id, per_replicate in discovery_reports.items():
        if scenario_id not in scenario_map or not isinstance(per_replicate, dict):
            raise ValueError("discovery_reports contains an unknown scenario or invalid replicate map.")
        resolved_reports[scenario_id] = {}
        for replicate_text, path_text in per_replicate.items():
            if replicate_text not in {"1", "2", "3"} or not isinstance(path_text, str) or not path_text:
                raise ValueError("Each discovery report needs a replicate number and project-relative path.")
            resolved_reports[scenario_id][int(replicate_text)] = resolve_project_path(
                path_text, root, "discovery report"
            )

    source_root = plan.get("seclists_source_root")
    resolved_source_root = None
    if source_root is not None:
        if not isinstance(source_root, str) or not source_root:
            raise ValueError("seclists_source_root must be a non-empty project-relative path or null.")
        resolved_source_root = resolve_project_path(source_root, root, "seclists_source_root")

    c_scenarios = set(next(item for item in protocol["conditions"]
                           if item["condition_id"] == "C")["scenario_ids"])
    if "C" in condition_ids and c_scenarios.intersection(scenario_ids) and resolved_source_root is None:
        raise ValueError("Plans containing condition C must set seclists_source_root.")
    knowledge_snapshot = plan.get("knowledge_snapshot")
    knowledge_resolved = None
    if dataset == "formal" and "B" in condition_ids:
        if not isinstance(knowledge_snapshot, dict) or "index_file_sha256" not in knowledge_snapshot:
            raise ValueError("Formal RAG plans must pin the exact Chroma index file hashes.")
    if knowledge_snapshot is not None:
        if "B" not in condition_ids:
            raise ValueError("knowledge_snapshot is only valid for a plan containing RAG-on condition B.")
        knowledge_resolved = validate_knowledge_snapshot(knowledge_snapshot, root, verify_index=verify_index)
    return {
        **plan,
        "condition_ids": condition_ids,
        "scenario_ids": scenario_ids,
        "replicates": replicates,
        "discovery_reports_resolved": resolved_reports,
        "seclists_source_root_resolved": resolved_source_root,
        "knowledge_snapshot_resolved": knowledge_resolved,
    }


def planned_units(plan: dict, protocol: dict, root: Path = ROOT) -> list[dict]:
    condition_map = {item["condition_id"]: item for item in protocol["conditions"]}
    seed_map = {index: seed for index, seed in enumerate(protocol["replicate_seeds"], start=1)}
    units = []
    for slot in ordered_run_slots(protocol, scenario_ids=plan["scenario_ids"],
                                  condition_ids=plan["condition_ids"], replicates=plan["replicates"]):
        scenario_id, replicate, condition_id = (slot[k] for k in ("scenario_id", "replicate", "condition_id"))
        report = plan["discovery_reports_resolved"].get(scenario_id, {}).get(replicate)
        report_hash = sha256_file(report) if report is not None and report.is_file() else None
        condition = condition_map[condition_id]
        applicable = slot["applicable"]
        units.append({
            **{key: value for key, value in slot.items() if key != "applicable"},
            "unit_id": f"{plan['experiment_id']}-{condition_id.lower()}-{scenario_id.lower()}-r{replicate}",
            "source": condition["source"], "rag_mode": condition["rag_mode"],
            "seed": seed_map[replicate],
            "discovery_report": str(report) if report else None,
            "discovery_sha256": report_hash,
            "status": "planned" if applicable else "excluded",
            "exclusion_reason": None if applicable else "condition_does_not_include_scenario",
        })
    return units


def artifact_hashes(root: Path = ROOT) -> dict[str, str]:
    names = ("dvwa/run_local_experiments.py", "dvwa/experiment_protocol.py",
             "dvwa/rag_pipeline.py", "dvwa/validation_loop.py",
             "dvwa/generate_candidate_batch.py", "dvwa/build_seclists_batches.py",
             "dvwa/local_experiment_protocol.json", "dvwa/experiment_scenarios.json",
             "dvwa/prepare_candidate_batch.py",
             "dvwa/confirmation_policy.py", "schemas/candidate-evidence.schema.json",
             "dvwa/run_decision_policy.py", "dvwa/run_decision_evaluator.py",
             "dvwa/methodology_policy.py",
             "dvwa/execution_order_policy.py", "requirements-orchestration.txt", "requirements-rag.txt",
             "dvwa/analyze_response.py", "dvwa/adaptive_s1_loop.py", "dvwa/adaptive_candidate_policy.py",
             "dvwa/summarize_zap_active.py", "dvwa/zap-active-sqli.template.yaml",
             "dvwa/run_zap_active_baseline.ps1", "dvwa/run_zap_api_explicit.ps1",
             "dvwa/summarize_zap_api_active.py", "dvwa/compose.yaml",
             "schemas/analysis-ledger.schema.json",
             "dvwa/langchain_runtime.py",
             "schemas/local-run-plan.schema.json", "schemas/experiment-ledger-event.schema.json",
             "schemas/validation-payloads.schema.json", "schemas/candidate-batch.schema.json",
             "dvwa/release_formal_freeze.py", "schemas/formal-freeze-approval.schema.json",
             "schemas/formal-execution-approval.schema.json",
             "docs/candidate-sources.md", "docs/evidence/seclists-selection-plan-2026-10-12.json")
    return {name: sha256_file(root / Path(name)) for name in names if (root / Path(name)).is_file()}


def source_snapshot_hashes(root: Path = ROOT) -> dict[str, str]:
    """Mirror the U07 source inventory so added and changed files both block F01."""
    files = [path for folder in ("dvwa", "schemas", "knowledge", "tests")
             for path in (root / folder).glob("*")
             if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".ps1", ".md"}
             and ".local." not in path.name]
    files.extend(root.glob("requirements*.txt"))
    return {path.resolve().relative_to(root.resolve()).as_posix(): sha256_file(path)
            for path in sorted(set(files))}


def validate_condition_b_runner_amendment(path: Path, plan_path: Path, plan: dict,
                                          protocol: dict, root: Path = ROOT) -> dict:
    """Bind the B recovery patch to the unchanged release and preserved R1/R2 history."""
    path = resolve_project_path(path, root, "runner amendment")
    amendment = read_json(path)
    authority = amendment.get("authority", {})
    if (amendment.get("schema_version") != "1.0.0"
            or amendment.get("scope") != "condition-b-index-recovery-r3"
            or amendment.get("decision") != "approved-for-condition-b-runner-amendment"
            or amendment.get("runner_amendment_approval") is not True
            or amendment.get("formal_execution_approval") is not False
            or amendment.get("condition_ids") != ["B"]
            or amendment.get("applies_to_replicates") != [3]
            or amendment.get("preserve_replicates") != [1, 2]
            or authority.get("role") != "researcher"
            or authority.get("basis") != "explicit-user-approval"
            or not isinstance(authority.get("quote"), str) or not authority["quote"].strip()):
        raise ValueError("An explicit B-only runner amendment preserving R1/R2 is required.")
    release_path = protocol.get("formal_freeze_release", {}).get("release_manifest_path")
    if (plan.get("dataset") != "formal" or protocol.get("status") != "frozen"
            or amendment.get("experiment_id") != plan["experiment_id"]
            or amendment.get("formal_plan_path") != plan_path.resolve().relative_to(root.resolve()).as_posix()
            or amendment.get("formal_plan_sha256") != sha256_file(plan_path)
            or amendment.get("protocol_sha256") != sha256_file(root / "dvwa/local_experiment_protocol.json")
            or amendment.get("release_manifest_path") != release_path
            or amendment.get("release_manifest_sha256") != sha256_file(
                resolve_project_path(release_path, root, "original release"))
            or amendment.get("runner_after_sha256") != sha256_file(root / "dvwa/run_local_experiments.py")):
        raise ValueError("Runner amendment does not match the active plan, protocol, release, or runner.")
    directory = root / "results/raw/formal" / plan["experiment_id"]
    snapshot_path = directory / "plan.snapshot.json"
    snapshot = read_json(snapshot_path)
    if (amendment.get("plan_snapshot_sha256") != sha256_file(snapshot_path)
            or snapshot.get("artifact_sha256", {}).get("dvwa/run_local_experiments.py")
            != amendment.get("runner_before_sha256")):
        raise ValueError("Runner amendment does not match the original experiment snapshot.")
    history = amendment.get("preserved_history", {})
    prefix_size = history.get("ledger_prefix_bytes")
    ledger_path = directory / "ledger.jsonl"
    if type(prefix_size) is not int or prefix_size < 1:
        raise ValueError("Runner amendment must pin the preserved ledger prefix.")
    with ledger_path.open("rb") as source:
        prefix = source.read(prefix_size)
        suffix = source.read()
    if (len(prefix) != prefix_size or not prefix.endswith(b"\n")
            or sha256_bytes(prefix) != history.get("ledger_prefix_sha256")):
        raise ValueError("Preserved R1/R2 ledger prefix changed.")
    events = [json.loads(line) for line in prefix.splitlines()]
    if len(events) != history.get("ledger_event_count"):
        raise ValueError("Preserved ledger event count differs from the amendment.")
    original = ExperimentLedger(directory, plan["experiment_id"], events)
    validate_ledger_schedule(original, plan, protocol)
    states = original.statuses()
    for replicate in (1, 2):
        selected = [state for state in states.values() if state["unit"]["replicate"] == replicate]
        if not selected or any(state["status"] not in {"completed", "excluded"} for state in selected):
            raise ValueError("Runner amendment requires completed R1/R2; they cannot be replayed.")
    if any(state["attempt_count"] for state in states.values() if state["unit"]["replicate"] == 3):
        raise ValueError("Runner amendment must precede the first R3 attempt.")
    expected_record = {**amendment, "amendment_path": path.relative_to(root).as_posix(),
                       "amendment_sha256": sha256_file(path)}
    amendment_recorded = False
    for line in suffix.splitlines():
        event = json.loads(line)
        if "condition_b_runner_amendment" in event:
            if event["condition_b_runner_amendment"] != expected_record:
                raise ValueError("Recorded runner amendment differs from the approved receipt.")
            amendment_recorded = True
        unit = states.get(event.get("unit_id"), {}).get("unit", {})
        if event.get("event_type", "").startswith("attempt_") and unit.get("replicate") in {1, 2}:
            raise ValueError("Preserved R1/R2 contain a new attempt after the amendment boundary.")
        if (event.get("event_type", "").startswith("attempt_") and unit.get("replicate") == 3
                and not amendment_recorded):
            raise ValueError("R3 attempt precedes its recorded runner amendment.")
    inventory_path = resolve_project_path(history.get("inventory_path", ""), root, "preserved history inventory")
    if sha256_file(inventory_path) != history.get("inventory_sha256"):
        raise ValueError("Preserved history inventory changed.")
    inventory = read_json(inventory_path)["files"]
    attempts = directory / "attempts"
    preserved_attempts = {name for name in inventory
                          if name.startswith(attempts.relative_to(root).as_posix() + "/")}
    current_attempts = {file.relative_to(root).as_posix()
                        for unit in attempts.glob("*") if unit.name.endswith(("-r1", "-r2"))
                        for file in unit.rglob("*") if file.is_file()}
    if current_attempts != preserved_attempts:
        raise ValueError("Preserved R1/R2 artifact inventory changed.")
    dynamic = {ledger_path.relative_to(root).as_posix(),
               (directory / "checkpoint.json").relative_to(root).as_posix()}
    for name, expected in inventory.items():
        if name not in dynamic and sha256_file(resolve_project_path(name, root, "preserved artifact")) != expected:
            raise ValueError(f"Preserved R1/R2 artifact changed: {name}")
    archive_path = resolve_project_path(amendment.get("index_archive_path", ""), root, "approved index archive")
    if sha256_file(archive_path) != amendment.get("index_archive_sha256"):
        raise ValueError("Approved recovery archive changed.")
    expected = plan["knowledge_snapshot"]["index_file_sha256"]
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if any(names.count(name) != 1 for name in expected):
            raise ValueError("Recovery archive must contain exactly one copy of each pinned index file.")
        payload = {name: archive.read(name) for name in expected}
    if {name: sha256_bytes(value) for name, value in payload.items()} != expected:
        raise ValueError("Recovery archive does not contain the approved index bytes.")
    return {**expected_record, "index_payload_resolved": payload}


def condition_b_amendment_record(amendment: dict) -> dict:
    return {key: value for key, value in amendment.items() if not key.endswith("_resolved")}


def prepare_condition_b_index(unit: dict, attempt: dict, plan: dict,
                              directory: Path, root: Path = ROOT) -> dict | None:
    """Restore and verify synchronously before B retrieval, without database or model calls."""
    amendment = plan.get("condition_b_runner_amendment_resolved")
    if unit["condition_id"] != "B" or amendment is None:
        return None
    if unit["replicate"] not in amendment["applies_to_replicates"]:
        raise ValueError("Condition B amendment is restricted to R3.")
    snapshot = validate_knowledge_snapshot(plan["knowledge_snapshot"], root, verify_index=False)
    store = snapshot["store_path_resolved"]
    expected = snapshot["index_file_sha256"]

    def hashes() -> dict:
        result = {}
        for file in store.rglob("*"):
            if file.is_symlink():
                raise ValueError("Index recovery refuses symbolic links.")
            if file.is_file():
                resolved = resolve_project_path(file, root, "active index file")
                if not resolved.is_relative_to(store):
                    raise ValueError("Active index file escapes the pinned store.")
                result[file.relative_to(root).as_posix()] = sha256_file(file)
        return result

    started = time.monotonic()
    before = hashes()
    if set(before) != set(expected):
        raise ValueError("Active Chroma file inventory changed; automatic restore is refused.")
    recovery_root = resolve_project_path(directory / "index-recovery/synchronous-b", root, "index recovery output")
    recovery_root.mkdir(parents=True, exist_ok=True)
    receipt_path = recovery_root / f"{attempt['attempt_id']}.json"
    if receipt_path.exists():
        raise ValueError("Condition B preflight receipt already exists.")
    backup = None
    if before != expected:
        backup_path = recovery_root / f"{attempt['attempt_id']}-backup"
        shutil.copytree(store, backup_path)
        if hashes() != before:
            raise ValueError("Chroma changed during backup; stop the other index writer before retrying.")
        # Only byte drift is repaired. Metadata, file inventory and corpus guards remain strict.
        for name, payload in amendment["index_payload_resolved"].items():
            if sha256_bytes(payload) != expected[name]:
                raise ValueError("Recovery source bytes changed before restoration.")
            resolve_project_path(name, root, "recovery destination").write_bytes(payload)
        backup = backup_path.relative_to(root).as_posix()
    after = hashes()
    if after != expected:
        raise ValueError("Chroma hash verification failed after synchronous recovery.")
    validate_knowledge_snapshot(plan["knowledge_snapshot"], root)
    record = {"status": "restored-and-verified" if backup else "verified-unchanged",
              "unit_id": unit["unit_id"], "attempt_id": attempt["attempt_id"],
              "amendment_sha256": amendment["amendment_sha256"],
              "preserved_active_backup": backup, "before_index_file_sha256": before,
              "index_file_sha256": after, "elapsed_seconds": time.monotonic() - started,
              "database_reset_performed": False, "probe_submissions": 0,
              "recorded_at_utc": now_utc()}
    safe_write_json(receipt_path, record)
    return {"receipt_path": receipt_path.relative_to(root).as_posix(),
            "receipt_sha256": sha256_file(receipt_path), "status": record["status"],
            "elapsed_seconds": record["elapsed_seconds"]}


def safe_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(value, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    for attempt in range(6):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 5:
                raise
            # Antivirus/indexing software can briefly hold an existing checkpoint on Windows.
            time.sleep(min(0.05 * (2 ** attempt), 0.5))


class ExperimentLedger:
    """Append-only event log plus an atomically replaced checkpoint."""

    def __init__(self, directory: Path, experiment_id: str, events: list[dict] | None = None):
        self.directory = directory
        self.experiment_id = experiment_id
        self.events = events or []
        self.path = directory / "ledger.jsonl"
        self.checkpoint_path = directory / "checkpoint.json"

    @classmethod
    def create(cls, directory: Path, plan: dict, protocol: dict, plan_hash: str,
               protocol_hash: str, root: Path = ROOT,
               formal_execution_authorization: dict | None = None):
        directory.mkdir(parents=True, exist_ok=False)
        ledger = cls(directory, plan["experiment_id"])
        safe_write_json(directory / "plan.snapshot.json", {
            "plan": {key: value for key, value in plan.items() if not key.endswith("_resolved")},
            "plan_sha256": plan_hash,
            "protocol_id": protocol["protocol_id"],
            "protocol_status": protocol["status"],
            "protocol_sha256": protocol_hash,
            "git_revision": git_revision(root),
            "artifact_sha256": artifact_hashes(root),
            "formal_execution_authorization": formal_execution_authorization,
            "created_at_utc": now_utc(),
        })
        ledger.append("experiment_created", dataset=plan["dataset"], plan_sha256=plan_hash,
                      protocol_sha256=protocol_hash, protocol_id=protocol["protocol_id"],
                      **({"formal_execution_authorization": formal_execution_authorization}
                         if formal_execution_authorization is not None else {}))
        for unit in planned_units(plan, protocol, root):
            if unit["status"] == "excluded":
                ledger.append("run_excluded", **unit)
            else:
                ledger.append("run_planned", **unit)
        return ledger

    @classmethod
    def resume(cls, directory: Path, plan: dict, plan_hash: str, protocol_hash: str,
               root: Path = ROOT,
               formal_execution_authorization: dict | None = None,
               runner_amendment: dict | None = None):
        path = directory / "ledger.jsonl"
        if not path.is_file():
            raise ValueError("Cannot resume: ledger.jsonl is missing.")
        events = []
        event_ids = set()
        with path.open("r", encoding="utf-8") as source:
            for number, line in enumerate(source, start=1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Ledger line {number} is invalid JSON.") from exc
                if event.get("experiment_id") != plan["experiment_id"]:
                    raise ValueError("Ledger belongs to a different experiment_id.")
                if (event.get("schema_version") != "1.0.0" or event.get("sequence") != number
                        or not isinstance(event.get("event_id"), str) or event["event_id"] in event_ids):
                    raise ValueError(f"Ledger sequence or event identity is invalid at line {number}.")
                event_ids.add(event["event_id"])
                events.append(event)
        created = next((event for event in events if event["event_type"] == "experiment_created"), None)
        if not created or created.get("plan_sha256") != plan_hash or created.get("protocol_sha256") != protocol_hash:
            raise ValueError("Resume plan or protocol differs from the saved experiment snapshot.")
        snapshot = read_json(directory / "plan.snapshot.json")
        authorization_events = [event.get("formal_execution_authorization") for event in events
                                if event["event_type"] == "formal_execution_authorized"]
        authorization_records = [record for record in (
            snapshot.get("formal_execution_authorization"),
            created.get("formal_execution_authorization"), *authorization_events) if record is not None]
        if authorization_records and any(record != authorization_records[0]
                                         for record in authorization_records[1:]):
            raise ValueError("Formal execution authorization records disagree within the saved ledger.")
        saved_authorization = authorization_records[0] if authorization_records else None
        if (formal_execution_authorization is not None and saved_authorization is not None
                and formal_execution_authorization != saved_authorization):
            raise ValueError("Resume formal execution receipt differs from the saved authorization.")
        if (formal_execution_authorization is not None and saved_authorization is None
                and any(event["event_type"] in {"attempt_started", "attempt_completed", "attempt_invalid"}
                        for event in events)):
            raise ValueError("Cannot authorize a formal ledger after an attempt has already started.")
        current_artifacts = artifact_hashes(root)
        saved_artifacts = snapshot.get("artifact_sha256", {})
        if saved_artifacts != current_artifacts:
            differences = {name for name in set(saved_artifacts) | set(current_artifacts)
                           if saved_artifacts.get(name) != current_artifacts.get(name)}
            recoveries = [event for event in events
                          if event.get("event_type") == "attempt_completed"
                          and event.get("recovery_method") == "offline_adaptive_artifact_aggregation"]
            authorized_recovery = any(
                differences == {"dvwa/run_local_experiments.py"}
                and event.get("runner_hash_before") == saved_artifacts.get("dvwa/run_local_experiments.py")
                and event.get("runner_hash_after") == current_artifacts.get("dvwa/run_local_experiments.py")
                for event in recoveries)
            authorized_amendment = (
                runner_amendment is not None and plan.get("dataset") == "formal"
                and differences == {"dvwa/run_local_experiments.py"}
                and runner_amendment["runner_before_sha256"] == saved_artifacts.get("dvwa/run_local_experiments.py")
                and runner_amendment["runner_after_sha256"] == current_artifacts.get("dvwa/run_local_experiments.py"))
            if not authorized_recovery and not authorized_amendment:
                raise ValueError("Resume code or schema hashes differ from the saved experiment snapshot.")
        ledger = cls(directory, plan["experiment_id"], events)
        if formal_execution_authorization is not None and saved_authorization is None:
            ledger.append("formal_execution_authorized",
                          formal_execution_authorization=formal_execution_authorization)
            snapshot["formal_execution_authorization"] = formal_execution_authorization
            safe_write_json(directory / "plan.snapshot.json", snapshot)
        elif saved_authorization is not None and snapshot.get("formal_execution_authorization") is None:
            snapshot["formal_execution_authorization"] = saved_authorization
            safe_write_json(directory / "plan.snapshot.json", snapshot)
        validate_ledger_schedule(ledger, plan, load_protocol())
        ledger.checkpoint()
        return ledger

    def append(self, event_type: str, **details) -> dict:
        event = {
            "schema_version": "1.0.0",
            "event_id": uuid4().hex,
            "sequence": len(self.events) + 1,
            "experiment_id": self.experiment_id,
            "event_type": event_type,
            "recorded_at_utc": now_utc(),
            **details,
        }
        line = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as destination:
            destination.write(line)
            destination.flush()
            os.fsync(destination.fileno())
        self.events.append(event)
        self.checkpoint()
        return event

    def statuses(self) -> dict[str, dict]:
        statuses: dict[str, dict] = {}
        for event in self.events:
            unit_id = event.get("unit_id")
            if not unit_id:
                continue
            state = statuses.setdefault(unit_id, {"status": "planned", "attempt_count": 0})
            event_type = event["event_type"]
            if event_type == "run_excluded":
                state.update(status="excluded", exclusion_reason=event.get("exclusion_reason"))
                if "condition_id" in event:
                    state["unit"] = {key: value for key, value in event.items()
                                     if key not in {"schema_version", "event_id", "sequence", "experiment_id",
                                                    "event_type", "recorded_at_utc"}}
            elif event_type == "run_planned":
                state["unit"] = {key: value for key, value in event.items()
                                 if key not in {"schema_version", "event_id", "sequence", "experiment_id",
                                                "event_type", "recorded_at_utc"}}
            elif event_type == "attempt_started":
                state["attempt_count"] += 1
                state.update(status="retried" if state["attempt_count"] > 1 else "running",
                             active_attempt_id=event["attempt_id"], last_attempt_id=event["attempt_id"])
            elif event_type == "attempt_completed":
                if event.get("metric_eligible") is False:
                    state.update(status="excluded", exclusion_reason=event.get("exclusion_reason"),
                                 last_attempt_id=event.get("attempt_id"))
                else:
                    state.update(status="completed", last_attempt_id=event.get("attempt_id"))
                state.pop("active_attempt_id", None)
            elif event_type == "attempt_invalid":
                state.update(status="invalid", failure_code=event.get("failure_code"),
                             last_attempt_id=event.get("attempt_id"))
                state.pop("active_attempt_id", None)
        return statuses

    def checkpoint(self) -> None:
        statuses = self.statuses()
        counts = {name: sum(1 for state in statuses.values() if state["status"] == name)
                  for name in ("planned", "running", "retried", "completed", "invalid", "excluded")}
        safe_write_json(self.checkpoint_path, {
            "schema_version": "1.0.0", "experiment_id": self.experiment_id,
            "event_count": len(self.events),
            "last_event_id": self.events[-1]["event_id"] if self.events else None,
            "status_counts": counts, "runs": statuses, "updated_at_utc": now_utc(),
        })


def git_revision(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def recover_interrupted_attempts(ledger: ExperimentLedger) -> int:
    active: dict[str, dict] = {}
    for event in ledger.events:
        unit_id = event.get("unit_id")
        if not unit_id:
            continue
        if event["event_type"] == "attempt_started":
            active[unit_id] = event
        elif event["event_type"] in {"attempt_completed", "attempt_invalid"}:
            if active.get(unit_id, {}).get("attempt_id") == event.get("attempt_id"):
                active.pop(unit_id, None)
    for unit_id, event in active.items():
        ledger.append("attempt_invalid", unit_id=unit_id, attempt_id=event["attempt_id"],
                      run_id=event["run_id"], attempt_number=event["attempt_number"],
                      failure_code="interrupted_attempt_outcome_unknown", attack_failure=False,
                      recovery_action="repair_environment_then_start_new_attempt_after_database_reset",
                      state_reused=False)
    return len(active)


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


@contextmanager
def experiment_lock(directory: Path, recover_stale: bool = False):
    path = directory / "orchestrator.lock"
    token = f"{os.getpid()} {uuid4().hex}"
    for attempt in range(2):
        try:
            with path.open("x", encoding="ascii") as destination:
                destination.write(token + "\n")
                destination.flush()
                os.fsync(destination.fileno())
            break
        except FileExistsError:
            if attempt or not recover_stale:
                raise RuntimeError("Another orchestrator may be using this experiment directory.")
            try:
                owner = path.read_text(encoding="ascii").strip().split()
                owner_pid = int(owner[0])
            except (OSError, ValueError, IndexError) as exc:
                raise RuntimeError("Experiment lock is unreadable; inspect it before resuming.") from exc
            if process_is_alive(owner_pid):
                raise RuntimeError("Another orchestrator is still using this experiment directory.")
            path.unlink()
    else:
        raise RuntimeError("Could not acquire experiment lock.")
    try:
        yield
    finally:
        try:
            if path.read_text(encoding="ascii").strip() == token:
                path.unlink()
        except OSError:
            pass


def parse_summary(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def run_command(command: list[str], log_path: Path, root: Path = ROOT) -> subprocess.CompletedProcess:
    completed = subprocess.run(command, cwd=root, text=True, encoding="utf-8", errors="replace",
                               capture_output=True, check=False)
    log_path.write_text("$ " + subprocess.list2cmdline(command) + "\n\n" + completed.stdout
                        + ("\n[stderr]\n" + completed.stderr if completed.stderr else ""),
                        encoding="utf-8", newline="\n")
    return completed


def candidate_fingerprint(candidate: dict) -> str:
    content = {key: candidate[key] for key in ("payload", "true_payload", "false_payload") if key in candidate}
    return sha256_bytes(json_bytes(content))


def candidate_policy_violation(candidate: dict, scenario: dict) -> str | None:
    values = [candidate.get(key) for key in ("payload", "true_payload", "false_payload")
              if isinstance(candidate.get(key), str)]
    if not values or any(len(value) > 1024 or any(ord(char) < 32 for char in value) for value in values):
        return "candidate_shape_out_of_bounds"
    joined = "\n".join(values)
    if ";" in joined:
        return "stacked_statement_separator"
    if re.search(r"\b(?:drop|delete|insert|update|truncate|alter|create|grant|revoke|load_file|benchmark|pg_sleep|waitfor|dbms_lock|xp_cmdshell|sys_exec)\b|\binto\s+(?:out|dump)file\b", joined, re.I):
        return "out_of_scope_side_effect_or_resource_probe"
    sleeps = re.findall(r"\bsleep\s*\(\s*([^()]*)\s*\)", joined, re.I)
    is_time_probe = scenario["sqli_type"] == "time-based blind"
    if sleeps and not is_time_probe:
        return "delay_outside_time_based_scenario"
    total_delay = 0.0
    for expression in sleeps:
        try:
            seconds = float(expression)
        except ValueError:
            return "unbounded_or_dynamic_delay"
        if not 0 < seconds <= 2:
            return "delay_exceeds_two_second_cap"
        total_delay += seconds
    if total_delay > 2:
        return "combined_delay_exceeds_two_second_cap"
    return None


def prepare_run_batch(batch_path: Path, unit: dict, scenario: dict, max_candidates: int,
                      run_id: str, output_path: Path, map_path: Path) -> dict:
    batch = read_json(batch_path)
    candidates = validate_candidates(batch, scenario, max_candidates)
    expected_condition = {"A": ("LLM", "off"), "B": ("LLM", "on"), "C": ("SecLists", "not_applicable")}[unit["condition_id"]]
    if {(item["source"], item["rag_mode"]) for item in candidates} != {expected_condition}:
        raise ValueError("Candidate source and RAG mode do not match the planned condition.")
    violations = []
    for candidate in candidates:
        reason = candidate_policy_violation(candidate, scenario)
        if reason:
            violations.append({"source_candidate_id": candidate["candidate_id"],
                               "payload_sha256": candidate_fingerprint(candidate),
                               "rejection_code": reason})
    if violations:
        raise ExecutionFailure("candidate_policy_rejected", {
            "generated_candidate_count": len(candidates),
            "candidate_generation_failed_count": max(0, max_candidates - len(candidates)),
            "duplicate_candidate_count": 0,
            "policy_rejected_candidate_count": len(violations),
            "policy_rejections": violations,
        })

    seen: dict[str, str] = {}
    selected = []
    id_map = []
    for index, candidate in enumerate(candidates, start=1):
        fingerprint = candidate_fingerprint(candidate)
        source_id = candidate["candidate_id"]
        if fingerprint in seen:
            id_map.append({"candidate_id": None, "source_candidate_id": source_id,
                           "payload_sha256": fingerprint, "duplicate_of": seen[fingerprint],
                           "executed": False})
            continue
        new_id = f"{run_id}-c{len(selected) + 1:03d}"
        selected_candidate = {**candidate, "candidate_id": new_id}
        selected.append(selected_candidate)
        seen[fingerprint] = new_id
        id_map.append({"candidate_id": new_id, "source_candidate_id": source_id,
                       "payload_sha256": fingerprint, "duplicate_of": None, "executed": True})

    if not selected:
        raise ExecutionFailure("no_unique_candidates", {"generated_candidate_count": len(candidates),
                                                            "duplicate_candidate_count": len(candidates)})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_json(output_path, {"schema_version": "1.0.0", "candidates": selected})
    safe_write_json(map_path, {"run_id": run_id, "candidate_id_map": id_map})
    return {"generated_candidate_count": len(candidates), "unique_candidate_count": len(selected),
            "duplicate_candidate_count": len(candidates) - len(selected),
            "candidate_generation_failed_count": max(0, max_candidates - len(candidates)),
            "runner_batch_sha256": sha256_file(output_path), "runner_batch_path": str(output_path),
            "candidate_id_map_path": str(map_path)}


def candidate_evidence_stats(records, unit, attempt, candidate_ids, root=ROOT):
    """Verify candidate summaries against the three original confirmation decisions."""
    summaries = [r for r in records if r.get("record_type") == "candidate_evidence"]
    if (len(summaries) != len(candidate_ids)
            or {r.get("candidate_id") for r in summaries} != set(candidate_ids)):
        raise ExecutionFailure("candidate_evidence_count_mismatch")
    validator = Draft202012Validator(read_json(root / "schemas/candidate-evidence.schema.json"))
    for summary in summaries:
        try:
            validator.validate(summary)
        except ValidationError as exc:
            raise ExecutionFailure("candidate_evidence_schema_invalid") from exc
        matching = [r for r in records if r.get("record_type") == "decision"
                    and r.get("candidate_id") == summary["candidate_id"]]
        signals = {r.get("confirmation_index"): r.get("system_signal") for r in matching}
        if len(matching) != 3 or set(signals) != {1, 2, 3}:
            raise ExecutionFailure("candidate_confirmation_count_mismatch")
        expected = {
            **classify_confirmations(signals), "confirmation_signals": [signals[i] for i in (1, 2, 3)],
            "run_id": attempt["run_id"], "attempt_id": attempt["attempt_id"],
            "experiment_id": matching[0].get("experiment_id"),
            "condition_id": unit["condition_id"], "scenario_id": unit["scenario_id"],
            "replicate": unit["replicate"], "payload_source": unit["source"],
            "rag_mode": unit["rag_mode"], "qwen_claim": None,
        }
        if any(summary.get(key) != value for key, value in expected.items()):
            raise ExecutionFailure("candidate_evidence_semantics_mismatch")
        for decision in matching:
            for key in ("run_id", "attempt_id", "experiment_id", "condition_id", "scenario_id",
                        "replicate", "payload_source", "rag_mode"):
                if decision.get(key) != expected[key]:
                    raise ExecutionFailure("candidate_confirmation_context_mismatch")
    return {
        "confirmation_policy_id": CONFIRMATION_POLICY_ID,
        "candidate_evidence_records": len(summaries),
        "confirmed_success_count": sum(r["confirmed_success"] is True for r in summaries),
        "mixed_evidence_count": sum(r["evidence_status"] == "MIXED_EVIDENCE" for r in summaries),
    }


def validate_probe_evidence(records, scenario, unit, attempt, candidate_ids, experiment_id):
    """Require every original probe role exactly once per valid confirmation."""
    roles = {"single_error": {"baseline", "single"},
             "boolean_pair": {"baseline", "true_condition", "false_condition"},
             "single_time": {"baseline", "single", "no_delay_control"}}[scenario["probe_kind"]]
    groups = {}
    expected_context = {"run_id": attempt["run_id"], "attempt_id": attempt["attempt_id"],
                        "experiment_id": experiment_id, "condition_id": unit["condition_id"],
                        "scenario_id": unit["scenario_id"], "replicate": unit["replicate"],
                        "payload_source": unit["source"], "rag_mode": unit["rag_mode"]}
    for record in records:
        if record.get("record_type") != "payload":
            continue
        if any(record.get(key) != value for key, value in expected_context.items()):
            raise ExecutionFailure("probe_evidence_context_mismatch")
        key = (record.get("candidate_id"), record.get("confirmation_index"))
        role = record.get("payload_role")
        # Adaptive observations use candidate for the executor's single role.
        role = "single" if role == "candidate" else role
        if role in groups.setdefault(key, set()):
            raise ExecutionFailure("duplicate_probe_evidence")
        groups[key].add(role)
    expected_keys = {(candidate_id, confirmation) for candidate_id in candidate_ids
                     for confirmation in (1, 2, 3)}
    if set(groups) != expected_keys or any(value != roles for value in groups.values()):
        raise ExecutionFailure("probe_evidence_incomplete")


def execute_adaptive_s1_unit(unit: dict, attempt: dict, plan: dict, protocol: dict,
                             unit_directory: Path, root: Path,
                             adaptive_result_path: Path | None = None) -> dict:
    """Run S1 through adaptive LangChain generation, shared evidence rules, and Qwen analysis."""
    report = Path(unit["discovery_report"])
    if not report.is_file() or sha256_file(report) != unit["discovery_sha256"]:
        raise ExecutionFailure("verified_discovery_missing_or_changed")
    adaptive_directory = unit_directory / "adaptive"
    validation_log = unit_directory / "validation.jsonl"
    generation = protocol["generation"]
    comparison_id = plan["experiment_id"]
    command = [sys.executable, str(root / "dvwa" / "adaptive_s1_loop.py"),
               "--scenario", unit["scenario_id"], "--rag-mode", unit["rag_mode"], "--zap-report", str(report),
               "--comparison-id", comparison_id, "--replicate", str(unit["replicate"]),
               "--pilot-slots", str(generation["candidate_budget"]),
               "--model", generation["model"], "--temperature", str(generation["temperature"]),
               "--num-ctx", str(generation["num_ctx"]), "--num-predict", str(generation["num_predict"]),
               "--run-id", attempt["run_id"], "--attempt-id", attempt["attempt_id"],
               "--output-dir", str(adaptive_directory), "--reset-before-run", "--confirm-local-dvwa"]
    if adaptive_result_path is None:
        # A supplied adaptive result is postprocessed offline. Do not revalidate
        # the active manifest when P4 already used its isolated archive copy.
        command.extend(adaptive_manifest_args(plan, unit, root))
        result = run_command(command, unit_directory / "adaptive-command.log", root)
        summary = parse_summary(result.stdout)
        result_path_text = summary.get("output")
        if result.returncode != 0 or not result_path_text:
            raise ExecutionFailure("adaptive_s1_process_failed", {
                "stderr_tail": result.stderr[-1000:], "stdout_tail": result.stdout[-1000:]})
        adaptive_path = Path(result_path_text).resolve()
    else:
        adaptive_path = adaptive_result_path.resolve()
    if not adaptive_path.is_relative_to((root / "results" / "raw").resolve()) or not adaptive_path.is_file():
        raise ExecutionFailure("adaptive_s1_output_missing_or_outside_raw")
    adaptive = read_json(adaptive_path)
    candidate_records = adaptive.get("candidate_records", [])
    candidate_events = [event for event in adaptive.get("events", [])
                        if event.get("kind") == "candidate_analysis"]
    generation_events = [event for event in adaptive.get("events", []) if event.get("kind") == "generation"]
    if (adaptive.get("stop_reason") == "generation_exhausted" and generation_events
            and generation_events[-1]["data"].get("status") == "model_service_error"):
        raise ExecutionFailure("local_model_service_unavailable", {
            "generated_candidate_count": len(candidate_events),
            "http_request_calls": adaptive.get("runtime", {}).get("http_request_attempt_count"),
            "database_reset_performed": bool(adaptive.get("runtime", {}).get("database_reset")),
            "adaptive_result_path": str(adaptive_path)})
    if not candidate_records and adaptive.get("stop_reason") == "generation_exhausted":
        return {"candidate_budget": generation["candidate_budget"],
                "generated_candidate_count": 0, "unique_candidate_count": 0,
                "duplicate_candidate_count": 0, "candidate_generation_failed_count": generation["candidate_budget"],
                "valid_candidates_executed": 0, "candidate_evidence_records": 0,
                "confirmed_success_count": 0, "mixed_evidence_count": 0,
                "decision_records": 0, "payload_records": 0, "confirmations_per_candidate": 3,
                "logical_probe_submissions": 0,
                "http_request_calls": adaptive.get("runtime", {}).get("http_request_attempt_count"),
                "database_reset_performed": bool(adaptive.get("runtime", {}).get("database_reset")),
                "budget_complete": False, "metric_eligible": False,
                "exclusion_reason": "incomplete_candidate_budget", "system_decision": "not_evaluable",
                "analysis_run_status": "incomplete", "binary_decision_eligible": False,
                "psr_evidence_eligible": False, "adaptive_result_path": str(adaptive_path),
                "adaptive_result_sha256": sha256_file(adaptive_path)}
    if adaptive.get("stop_reason") == "runtime_invalid" or not candidate_records:
        runtime = adaptive.get("runtime", {})
        failure_code = adaptive.get("runtime_failure_code") or adaptive.get("stop_reason") or "adaptive_s1_no_candidates"
        raise ExecutionFailure(failure_code, {
            "generated_candidate_count": len(candidate_events),
            "candidate_generation_failed_count": max(0, generation["candidate_budget"] - len(candidate_events)),
            "http_request_calls": runtime.get("http_request_attempt_count"),
            "database_reset_performed": bool(runtime.get("database_reset")),
            "adaptive_result_path": str(adaptive_path),
            "attack_failure": False})
    if (len(candidate_records) != len(candidate_events)
            or any(record.get("analysis_status") != "completed" for record in candidate_records)):
        runtime = adaptive.get("runtime", {})
        raise ExecutionFailure("adaptive_s1_analysis_incomplete", {
            "generated_candidate_count": len(candidate_events),
            "candidate_generation_failed_count": max(0, generation["candidate_budget"] - len(candidate_events)),
            "http_request_calls": runtime.get("http_request_attempt_count"),
            "database_reset_performed": bool(runtime.get("database_reset")),
            "adaptive_result_path": str(adaptive_path)})

    scenario = {item["scenario_id"]: item for item in load_catalog()["scenarios"]}[unit["scenario_id"]]
    records = []
    candidate_rows = []
    if validation_log.exists() and validation_log.stat().st_size != 0:
        raise ExecutionFailure("adaptive_s1_validation_log_already_populated")
    with validation_log.open("w" if validation_log.exists() else "x",
                             encoding="utf-8", newline="\n") as output:
        for event, analysis in zip(candidate_events, candidate_records):
            data = event["data"]
            if data.get("record") != analysis:
                raise ExecutionFailure("adaptive_s1_analysis_event_mismatch")
            candidate_id = analysis["context"]["candidate_id"]
            candidate_values = (data["candidate"] if "candidate" in data
                                else {"payload": data["payload"]})
            observations = analysis["evidence"]["observations"]
            signals = trial_rule_signals(analysis["evidence"])
            if set(signals) != {1, 2, 3}:
                raise ExecutionFailure("adaptive_s1_confirmation_count_mismatch")
            derived = classify_confirmations(signals)
            if any(analysis.get(key) != derived[key] for key in
                   ("evidence_status", "valid_confirmation_count", "positive_confirmation_count",
                    "confirmed_success")):
                raise ExecutionFailure("adaptive_s1_evidence_semantics_mismatch")
            candidate = {"candidate_id": candidate_id, "source": "LLM", "rag_mode": unit["rag_mode"],
                         **candidate_values}
            for observation in observations:
                role = observation["role"]
                payload_record = {"record_type": "payload", "run_id": attempt["run_id"],
                                  "attempt_id": attempt["attempt_id"], "experiment_id": plan["experiment_id"],
                                  "condition_id": unit["condition_id"], "candidate_id": candidate_id,
                                  "scenario_id": unit["scenario_id"], "replicate": unit["replicate"],
                                  "confirmation_index": observation["trial"],
                                  "payload_source": "LLM", "rag_mode": unit["rag_mode"],
                                  "payload_role": "single" if role == "candidate" else role,
                                  "payload": candidate_probe_payload(candidate_values, role),
                                  "http_status": observation["http_status"],
                                  "response_time_ms": observation["elapsed_ms"],
                                  "response_sha256": observation["response_sha256"],
                                  "review_excerpt": observation.get("review_excerpt"),
                                  "response_indicators": observation["diagnostics"],
                                  "content_markers": observation["content_markers"],
                                  "human_validation": "pending"}
                output.write(json.dumps(payload_record, ensure_ascii=False) + "\n")
                records.append(payload_record)
            for index in range(1, 4):
                decision = {"record_type": "decision", "run_id": attempt["run_id"],
                            "attempt_id": attempt["attempt_id"], "experiment_id": plan["experiment_id"],
                            "condition_id": unit["condition_id"], "candidate_id": candidate_id,
                            "scenario_id": unit["scenario_id"], "replicate": unit["replicate"],
                            "confirmation_index": index, "payload_source": "LLM",
                            "rag_mode": unit["rag_mode"], "system_signal": signals[index]}
                output.write(json.dumps(decision, ensure_ascii=False) + "\n")
                records.append(decision)
            evidence_record = emit_candidate_evidence(
                output, attempt["run_id"], scenario, candidate, unit["replicate"], signals,
                attempt_id=attempt["attempt_id"], experiment_id=plan["experiment_id"],
                condition_id=unit["condition_id"])
            records.append(evidence_record)
            candidate_rows.append({"candidate_id": candidate_id, **candidate_values})
        runtime = adaptive["runtime"]
        output.write(json.dumps({"record_type": "run_end", "attempt_status":
                                 "complete" if adaptive["run_summary"]["execution_status"] == "complete" else "incomplete",
                                 "logical_probe_submissions": sum(3 * (3 if scenario["probe_kind"] != "single_error" else 2)
                                                                   for _ in candidate_rows),
                                 "http_request_calls": runtime["http_request_attempt_count"],
                                 "database_reset_performed": bool(runtime["database_reset"])}) + "\n")
    validate_probe_evidence(records, scenario, unit, attempt,
                            {row["candidate_id"] for row in candidate_rows}, plan["experiment_id"])
    evidence_stats = candidate_evidence_stats(records, unit, attempt,
                                              {row["candidate_id"] for row in candidate_rows}, root)
    batch_path = unit_directory / "adaptive-candidates.json"
    retrieval = adaptive["runtime"]["retrieval"]
    first_prompt_audit = next((event["data"]["audit"] for event in adaptive["events"]
                               if event.get("kind") == "generation"
                               and event["data"].get("status") == "generated"), {})
    batch_document = {"schema_version": "1.0.0", "scenario_id": unit["scenario_id"], "source": "LLM",
                      "rag_mode": unit["rag_mode"],
                      "provenance": {"comparison_id": plan["experiment_id"],
                                     "model": generation["model"],
                                     "prompt_version": first_prompt_audit.get("prompt_version", "sqli-adaptive-candidate-v2"),
                                     "temperature": generation["temperature"], "seed": unit["seed"],
                                     "knowledge_base_id": retrieval["knowledge_base_id"] if retrieval else None,
                                     "retrieved_chunk_ids": [item["chunk_id"] for item in retrieval["chunks"]]
                                     if retrieval else [],
                                     "retrieval_top_k": generation["top_k"] if retrieval else None},
                      "candidates": candidate_rows}
    validate_batch(batch_document, None)
    safe_write_json(batch_path, batch_document)
    audit_path = unit_directory / "adaptive-generation-audit.json"
    generation_feedback_events = [event for event in adaptive["events"]
                                  if event.get("kind") in {"generation", "feedback"}]
    safe_write_json(audit_path, {"events": generation_feedback_events,
                                 "events_sha256": sha256_bytes(json_bytes(generation_feedback_events))})
    generated_count = len(candidate_rows)
    budget_complete = (generated_count == generation["candidate_budget"]
                       and adaptive.get("stop_reason") == "budget_exhausted"
                       and adaptive.get("run_summary", {}).get("execution_status") == "complete")
    return {
        **evidence_stats, "generated_candidate_count": generated_count,
        "unique_candidate_count": generated_count, "duplicate_candidate_count": 0,
        "candidate_generation_failed_count": max(0, generation["candidate_budget"] - generated_count),
        "runner_batch_sha256": sha256_file(batch_path), "runner_batch_path": str(batch_path),
        "candidate_id_map_path": None,
        "condition_id": unit["condition_id"], "scenario_id": unit["scenario_id"],
        "replicate": unit["replicate"], "seed": unit["seed"],
        "source_batch_sha256": sha256_file(batch_path),
        "generation_audit_sha256": sha256_file(audit_path),
        "discovery_sha256": unit["discovery_sha256"],
        "validation_log_path": str(validation_log), "validation_log_sha256": sha256_file(validation_log),
        "adaptive_result_path": str(adaptive_path), "adaptive_result_sha256": sha256_file(adaptive_path),
        "analysis_ledger_path": str(adaptive_path),
        "analysis_run_status": adaptive["run_summary"]["run_status"],
        "system_decision": adaptive["run_summary"]["system_decision"],
        "binary_decision_eligible": adaptive["run_summary"]["binary_decision_eligible"],
        "psr_evidence_eligible": adaptive["run_summary"]["psr_evidence_eligible"],
        "candidate_budget": generation["candidate_budget"], "valid_candidates_executed": generated_count,
        "decision_records": generated_count * 3,
        "payload_records": generated_count * 3 * (2 if scenario["probe_kind"] == "single_error" else 3),
        "confirmations_per_candidate": 3,
        "logical_probe_submissions": generated_count * 3 * (3 if scenario["probe_kind"] != "single_error" else 2),
        "http_request_calls": adaptive["runtime"]["http_request_attempt_count"],
        "database_reset_performed": bool(adaptive["runtime"]["database_reset"]),
        "budget_complete": budget_complete, "metric_eligible": budget_complete,
        "exclusion_reason": None if budget_complete else "incomplete_candidate_budget",
    }


def validation_record_stats(validation_log: Path, candidate_details: dict,
                            protocol: dict) -> dict:
    records = []
    if validation_log.is_file():
        with validation_log.open("r", encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    decisions = [record for record in records if record.get("record_type") == "decision"]
    payload_records = [record for record in records if record.get("record_type") == "payload"]
    failure = next((record for record in reversed(records)
                    if record.get("record_type") == "runtime_failure"), {})
    run_end = next((record for record in reversed(records)
                    if record.get("record_type") == "run_end"), {})
    return {
        "valid_candidates_executed": len({record.get("candidate_id") for record in decisions}),
        "decision_records": len(decisions),
        "payload_records": len(payload_records),
        "confirmations_per_candidate": protocol["validation"]["confirmations_per_candidate"],
        "logical_probe_submissions": run_end.get("logical_probe_submissions",
                                                   failure.get("logical_probe_submissions")),
        "http_request_calls": run_end.get("http_request_calls", failure.get("http_request_calls")),
        "database_reset_performed": (any(record.get("record_type") == "runtime_setup"
                                          and record.get("database_reset") for record in records)
                                      or failure.get("database_reset_performed", False)),
        "partial_validation_log_sha256": sha256_file(validation_log) if validation_log.is_file() else None,
        "candidate_budget": candidate_details["candidate_budget"],
    }


def execute_unit(unit: dict, attempt: dict, plan: dict, protocol: dict,
                 data_directory: Path, root: Path = ROOT) -> dict:
    unit_directory = data_directory / "attempts" / unit["unit_id"] / attempt["attempt_id"]
    unit_directory.mkdir(parents=True, exist_ok=False)
    scenario_map = {item["scenario_id"]: item for item in load_catalog()["scenarios"]}
    scenario = scenario_map[unit["scenario_id"]]
    generation = protocol["generation"]
    raw_root = (root / "results" / "raw").resolve()
    if not unit_directory.resolve().is_relative_to(raw_root):
        raise ValueError("Attempt output must stay under results/raw/.")

    # Every LLM scenario uses the same bounded adaptive generation/feedback loop.
    if unit["condition_id"] in {"A", "B"}:
        return execute_adaptive_s1_unit(unit, attempt, plan, protocol, unit_directory, root)

    if unit["condition_id"] in {"A", "B"}:
        report = Path(unit["discovery_report"])
        if not report.is_file():
            raise ExecutionFailure("verified_discovery_missing", {"path": str(report)})
        actual_discovery_hash = sha256_file(report)
        if actual_discovery_hash != unit["discovery_sha256"]:
            raise ExecutionFailure("verified_discovery_changed", {"path": str(report)})
        comparison_id = f"{plan['experiment_id']}-{unit['scenario_id'].lower()}-r{unit['replicate']}"
        generated_directory = unit_directory / "generated"
        command = [sys.executable, str(root / "dvwa" / "generate_candidate_batch.py"),
                   "--scenario", unit["scenario_id"], "--rag-mode", unit["rag_mode"],
                   "--comparison-id", comparison_id, "--seed", str(unit["seed"]),
                   "--candidate-count", str(generation["candidate_budget"]),
                   "--top-k", str(generation["top_k"]), "--num-ctx", str(generation["num_ctx"]),
                   "--num-predict", str(generation["num_predict"]),
                   "--model", generation["model"], "--temperature", str(generation["temperature"]),
                   "--zap-report", str(report), "--require-verified-discovery",
                   "--output-dir", str(generated_directory)]
        result = run_command(command, unit_directory / "generation-command.log", root)
        summary = parse_summary(result.stdout)
        if result.returncode != 0 or not summary.get("batch_path"):
            raise ExecutionFailure("generation_failed", {"return_code": result.returncode,
                                                             "stdout_tail": result.stdout[-1000:],
                                                             "stderr_tail": result.stderr[-1000:],
                                                             "generated_candidate_count": 0,
                                                             "candidate_generation_failed_count": generation["candidate_budget"],
                                                             "duplicate_candidate_count": 0})
        batch_path = Path(summary["batch_path"]).resolve()
        generation_audit = Path(summary["audit_path"]).resolve()
        if not batch_path.is_relative_to(raw_root) or not generation_audit.is_relative_to(raw_root):
            raise ExecutionFailure("generation_output_outside_raw_directory")
        source_batch_sha256 = sha256_file(batch_path)
        audit_sha256 = sha256_file(generation_audit)
    else:
        source_root = plan["seclists_source_root_resolved"]
        if not source_root.is_dir():
            raise ExecutionFailure("seclists_source_root_missing", {"path": str(source_root)})
        batch_directory = unit_directory / "seclists-batches"
        command = [sys.executable, str(root / "dvwa" / "build_seclists_batches.py"),
                   "--source-root", str(source_root), "--output-dir", str(batch_directory)]
        result = run_command(command, unit_directory / "seclists-build-command.log", root)
        if result.returncode != 0:
            raise ExecutionFailure("seclists_batch_build_failed", {"return_code": result.returncode,
                                                                      "stderr_tail": result.stderr[-1000:]})
        batch_path = batch_directory / f"{unit['scenario_id']}.json"
        if not batch_path.is_file():
            raise ExecutionFailure("seclists_batch_missing", {"path": str(batch_path)})
        source_batch_sha256 = sha256_file(batch_path)
        audit_sha256 = None
        actual_discovery_hash = unit["discovery_sha256"]

    prepared_path = unit_directory / "runner-input.json"
    id_map_path = unit_directory / "candidate-id-map.json"
    batch_details = prepare_run_batch(batch_path, unit, scenario, generation["candidate_budget"],
                                      attempt["run_id"], prepared_path, id_map_path)
    validation_log = unit_directory / "validation.jsonl"
    validation_command = [sys.executable, str(root / "dvwa" / "validation_loop.py"),
                          "--scenario", unit["scenario_id"], "--payload-file", str(prepared_path),
                          "--confirmations", str(protocol["validation"]["confirmations_per_candidate"]),
                          "--replicate", str(unit["replicate"]), "--run-id", attempt["run_id"],
                          "--attempt-id", attempt["attempt_id"], "--experiment-id", plan["experiment_id"],
                          "--condition-id", unit["condition_id"], "--reset-before-run",
                          "--output", str(validation_log), "--confirm-local-dvwa"]
    result = run_command(validation_command, unit_directory / "validation-command.log", root)
    if result.returncode != 0:
        raise ExecutionFailure("executor_process_failed", {"return_code": result.returncode,
                                                              "stdout_tail": result.stdout[-1000:],
                                                              "stderr_tail": result.stderr[-1000:],
                                                              **batch_details,
                                                              **validation_record_stats(validation_log,
                                                                                       {"candidate_budget": generation["candidate_budget"]},
                                                                                       protocol)})

    records = []
    with validation_log.open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                records.append(json.loads(line))
    run_end = next((record for record in reversed(records)
                    if record.get("record_type") == "run_end"), None)
    if not run_end or run_end.get("attempt_status") != "complete":
        failure = next((record for record in reversed(records)
                        if record.get("record_type") == "runtime_failure"), {})
        raise ExecutionFailure(failure.get("runtime_failure_code", "executor_incomplete"), {
            "validation_log_path": str(validation_log),
            **batch_details,
            **validation_record_stats(validation_log, {"candidate_budget": generation["candidate_budget"]},
                                      protocol),
            "attack_failure": False,
        })

    payload_records = [record for record in records if record.get("record_type") == "payload"]
    decisions = [record for record in records if record.get("record_type") == "decision"]
    executed_ids = {record["candidate_id"] for record in decisions}
    expected_decisions = (batch_details["unique_candidate_count"]
                          * protocol["validation"]["confirmations_per_candidate"])
    confirmation_map: dict[str, set[int]] = {}
    invalid_confirmation_record = False
    for record in decisions:
        candidate_id = record.get("candidate_id")
        confirmation_index = record.get("confirmation_index")
        if not isinstance(candidate_id, str) or type(confirmation_index) is not int:
            invalid_confirmation_record = True
            continue
        confirmation_map.setdefault(candidate_id, set()).add(confirmation_index)
    expected_confirmations = set(range(1, protocol["validation"]["confirmations_per_candidate"] + 1))
    if (len(decisions) != expected_decisions
            or set(confirmation_map) != set(attempt_candidate["candidate_id"] for attempt_candidate in
                                             json.loads(prepared_path.read_text(encoding="utf-8"))["candidates"])
            or any(indices != expected_confirmations for indices in confirmation_map.values())
            or invalid_confirmation_record
            or any(record.get("replicate") != unit["replicate"] for record in decisions)
            ):
        raise ExecutionFailure("executor_record_count_mismatch", {
            "expected_decision_records": expected_decisions,
            "actual_decision_records": len(decisions),
            "validation_log_path": str(validation_log),
        })

    budget_complete = (batch_details["unique_candidate_count"] == generation["candidate_budget"]
                       and batch_details["duplicate_candidate_count"] == 0
                       and batch_details["candidate_generation_failed_count"] == 0)
    validate_probe_evidence(records, scenario, unit, attempt, executed_ids, plan["experiment_id"])
    evidence_stats = candidate_evidence_stats(records, unit, attempt, executed_ids, root)
    return {
        **batch_details,
        **evidence_stats,
        "condition_id": unit["condition_id"], "scenario_id": unit["scenario_id"],
        "replicate": unit["replicate"], "seed": unit["seed"],
        "source_batch_sha256": source_batch_sha256, "generation_audit_sha256": audit_sha256,
        "discovery_sha256": actual_discovery_hash,
        "validation_log_path": str(validation_log), "validation_log_sha256": sha256_file(validation_log),
        "candidate_budget": generation["candidate_budget"],
        "valid_candidates_executed": len(executed_ids),
        "decision_records": len(decisions), "payload_records": len(payload_records),
        "confirmations_per_candidate": protocol["validation"]["confirmations_per_candidate"],
        "logical_probe_submissions": run_end.get("logical_probe_submissions"),
        "http_request_calls": run_end.get("http_request_calls"),
        "database_reset_performed": bool(run_end.get("database_reset_performed")),
        "budget_complete": budget_complete,
        "metric_eligible": budget_complete,
        "exclusion_reason": None if budget_complete else "incomplete_candidate_budget_or_duplicates",
    }


def summarize(ledger: ExperimentLedger) -> dict:
    states = ledger.statuses()
    counts = {status: sum(1 for state in states.values() if state["status"] == status)
              for status in ("planned", "running", "retried", "completed", "invalid", "excluded")}
    return {"experiment_id": ledger.experiment_id, "run_count": len(states), "status_counts": counts,
            "ledger_path": str(ledger.path), "checkpoint_path": str(ledger.checkpoint_path)}


def execute_plan(plan_path: Path, *, execute: bool = False, resume: bool = False,
                 retry_invalid: bool = False, confirm_local_dvwa: bool = False,
                 confirm_database_reset: bool = False,
                 one_replicate_per_session: bool = False,
                 formal_execution_approval_path: Path | None = None,
                 condition_b_runner_amendment_path: Path | None = None, root: Path = ROOT,
                 execute_one=execute_unit) -> dict:
    plan_path = plan_path.resolve()
    if not plan_path.is_relative_to(root.resolve()):
        raise ValueError("--plan must resolve inside the project workspace.")
    if condition_b_runner_amendment_path is not None and not (resume and execute):
        raise ValueError("--condition-b-runner-amendment requires --resume --execute.")
    plan = validate_plan(read_json(plan_path), load_protocol(), root,
                         verify_index=condition_b_runner_amendment_path is None)
    protocol = load_protocol()
    runner_amendment = None
    if condition_b_runner_amendment_path is not None:
        runner_amendment = validate_condition_b_runner_amendment(
            condition_b_runner_amendment_path, plan_path, plan, protocol, root)
        plan["condition_b_runner_amendment_resolved"] = runner_amendment
    if retry_invalid and not execute:
        raise ValueError("--retry-invalid requires --execute so every retry gets a fresh database reset.")
    if one_replicate_per_session and not execute:
        raise ValueError("--one-replicate-per-session requires --execute.")
    if formal_execution_approval_path is not None and not execute:
        raise ValueError("--formal-execution-approval requires --execute.")
    if execute and plan["dataset"] == "formal" and formal_execution_approval_path is None:
        raise ValueError("Formal dataset execution requires --formal-execution-approval bound to this plan and release.")
    if formal_execution_approval_path is not None and plan["dataset"] != "formal":
        raise ValueError("--formal-execution-approval can only be used with a formal dataset plan.")
    formal_execution_authorization = None
    if execute:
        if not confirm_local_dvwa or not confirm_database_reset:
            raise ValueError("Execution requires --confirm-local-dvwa and --confirm-database-reset.")
        if plan["dataset"] == "formal":
            formal_execution_authorization = validate_formal_execution_approval(
                formal_execution_approval_path, plan_path, plan, protocol, root,
                runner_amendment=runner_amendment)
        snapshot = plan.get("knowledge_snapshot_resolved")
        if snapshot is not None and "B" in plan["condition_ids"]:
            decision = read_json(snapshot["review_decision_path_resolved"])
            required_decision = ("approved-for-pilot-use" if plan["dataset"] == "pilot"
                                 else "approved-for-formal-use")
            if decision.get("decision") != required_decision:
                raise ValueError(f"Condition B execution requires a corpus receipt with decision={required_decision}.")
        require_local_target(protocol["target_origin"])
    plan_hash = sha256_bytes(json_bytes({key: value for key, value in plan.items()
                                         if not key.endswith("_resolved")}))
    protocol_hash = sha256_file(PROTOCOL_SNAPSHOT_PATH)
    data_directory = root / "results" / "raw" / plan["dataset"] / plan["experiment_id"]
    if resume:
        ledger = ExperimentLedger.resume(data_directory, plan, plan_hash, protocol_hash, root,
                                         formal_execution_authorization, runner_amendment)
    else:
        if data_directory.exists():
            raise ValueError("Experiment directory already exists. Use --resume with the unchanged plan.")
        ledger = ExperimentLedger.create(data_directory, plan, protocol, plan_hash, protocol_hash, root,
                                         formal_execution_authorization)

    with experiment_lock(data_directory, recover_stale=resume):
        if runner_amendment is not None:
            record = condition_b_amendment_record(runner_amendment)
            recorded = [event["condition_b_runner_amendment"] for event in ledger.events
                        if "condition_b_runner_amendment" in event]
            if recorded and any(value != record for value in recorded):
                raise ValueError("Saved runner amendment differs from the supplied receipt.")
            if not recorded:
                ledger.append("formal_execution_authorized",
                              formal_execution_authorization=formal_execution_authorization,
                              condition_b_runner_amendment=record)
        recovered = recover_interrupted_attempts(ledger) if resume else 0
        return execute_ledger(ledger, plan, protocol, data_directory, execute=execute,
                              retry_invalid=retry_invalid,
                              one_replicate_per_session=one_replicate_per_session,
                              recovered=recovered, root=root,
                              execute_one=execute_one)


def recover_adaptive_s1_attempt(plan_path: Path, root: Path = ROOT) -> dict:
    """Finish ledger aggregation from a completed, immutable adaptive result without probing DVWA."""
    plan_path = plan_path.resolve()
    if not plan_path.is_relative_to(root.resolve()):
        raise ValueError("--recover-adaptive-artifact plan must resolve inside the project workspace.")
    protocol = load_protocol()
    plan = validate_plan(read_json(plan_path), protocol, root)
    plan_hash = sha256_bytes(json_bytes({key: value for key, value in plan.items()
                                         if not key.endswith("_resolved")}))
    protocol_hash = sha256_file(PROTOCOL_SNAPSHOT_PATH)
    data_directory = root / "results" / "raw" / plan["dataset"] / plan["experiment_id"]
    snapshot = read_json(data_directory / "plan.snapshot.json")
    if snapshot.get("plan_sha256") != plan_hash or snapshot.get("protocol_sha256") != protocol_hash:
        raise ValueError("Recovery plan or protocol differs from the saved experiment snapshot.")
    saved_artifacts = snapshot.get("artifact_sha256", {})
    current_artifacts = artifact_hashes(root)
    differences = {name for name in set(saved_artifacts) | set(current_artifacts)
                   if saved_artifacts.get(name) != current_artifacts.get(name)}
    if differences != {"dvwa/run_local_experiments.py"}:
        raise ValueError(f"Recovery requires all snapshotted artifacts to match except the runner; differences: {sorted(differences)}")

    events = []
    with (data_directory / "ledger.jsonl").open("r", encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
            event = json.loads(line)
            if (event.get("experiment_id") != plan["experiment_id"]
                    or event.get("schema_version") != "1.0.0"
                    or event.get("sequence") != number):
                raise ValueError(f"Ledger identity or sequence is invalid at line {number}.")
            events.append(event)
    ledger = ExperimentLedger(data_directory, plan["experiment_id"], events)
    validate_ledger_schedule(ledger, plan, protocol)
    active = {}
    for event in events:
        if event.get("event_type") == "attempt_started":
            active[event["unit_id"]] = event
        elif event.get("event_type") in {"attempt_completed", "attempt_invalid"}:
            if active.get(event.get("unit_id"), {}).get("attempt_id") == event.get("attempt_id"):
                active.pop(event["unit_id"], None)
    matches = [(unit_id, event) for unit_id, event in active.items()
               if event.get("condition_id") == "A" and event.get("scenario_id") == "S1"]
    if len(matches) != 1:
        raise ValueError("Expected exactly one unfinished S1 condition A attempt for artifact recovery.")
    unit_id, attempt_event = matches[0]
    run_event = next((event for event in events
                      if event.get("event_type") == "run_planned" and event.get("unit_id") == unit_id), None)
    if run_event is None:
        raise ValueError("The unfinished attempt has no matching planned run.")
    unit = {key: value for key, value in run_event.items()
            if key not in {"schema_version", "event_id", "sequence", "experiment_id",
                           "event_type", "recorded_at_utc"}}
    attempt = {key: attempt_event[key] for key in
               ("run_id", "attempt_id", "attempt_number", "retry_of_attempt_id")}
    unit_directory = data_directory / "attempts" / unit_id / attempt["attempt_id"]
    adaptive_files = list((unit_directory / "adaptive").glob("adaptive-s1-*.json"))
    if len(adaptive_files) != 1:
        raise ValueError("Expected exactly one saved adaptive S1 result for the unfinished attempt.")
    adaptive_path = adaptive_files[0]
    adaptive = read_json(adaptive_path)
    runtime = adaptive.get("runtime", {})
    reset = runtime.get("database_reset", {})
    context = adaptive.get("run_summary", {}).get("context", {})
    if (adaptive.get("stop_reason") != "budget_exhausted"
            or adaptive.get("run_summary", {}).get("execution_status") != "complete"
            or runtime.get("model") != protocol["generation"]["model"]
            or runtime.get("protocol_sha256") != hashlib.sha256(
                json.dumps(protocol, sort_keys=True, ensure_ascii=False,
                            allow_nan=False).encode()).hexdigest()
            or not reset.get("success_markers_verified")
            or reset.get("status") != 200
            or context.get("run_id") != attempt["run_id"]
            or context.get("attempt_id") != attempt["attempt_id"]
            or len(adaptive.get("candidate_records", [])) != protocol["generation"]["candidate_budget"]):
        raise ValueError("Saved adaptive artifact does not prove a complete, reset, correctly assigned attempt.")

    details = execute_adaptive_s1_unit(unit, attempt, plan, protocol, unit_directory, root,
                                       adaptive_result_path=adaptive_path)
    details.update(recovery_method="offline_adaptive_artifact_aggregation",
                   recovery_probe_replayed=False,
                   runner_hash_before=saved_artifacts["dvwa/run_local_experiments.py"],
                   runner_hash_after=current_artifacts["dvwa/run_local_experiments.py"])
    ledger.append("attempt_completed", unit_id=unit_id, run_id=attempt["run_id"],
                  attempt_id=attempt["attempt_id"], attempt_number=attempt["attempt_number"], **details)
    result = summarize(ledger)
    result["offline_artifact_recovery"] = True
    return result


def validate_ledger_schedule(ledger, plan, protocol):
    """The original planned events must still represent the canonical selected schedule."""
    slots = list(ordered_run_slots(protocol, scenario_ids=plan["scenario_ids"],
                                  condition_ids=plan["condition_ids"], replicates=plan["replicates"]))
    events = [e for e in ledger.events if e["event_type"] in {"run_planned", "run_excluded"}
              and "condition_id" in e]
    if len(events) != len(slots):
        raise ValueError("Saved planned order is incomplete or contains duplicate units.")
    for event, slot in zip(events, slots):
        expected = {key: value for key, value in slot.items() if key != "applicable"}
        expected.update(
            event_type="run_planned" if slot["applicable"] else "run_excluded",
            unit_id=f"{plan['experiment_id']}-{slot['condition_id'].lower()}-{slot['scenario_id'].lower()}-r{slot['replicate']}",
            seed=protocol["replicate_seeds"][slot["replicate"] - 1])
        if any(event.get(key) != value for key, value in expected.items()):
            raise ValueError("Saved planned order differs from the recorded rotation.")


def ordered_ledger_states(ledger):
    return sorted(ledger.statuses().items(), key=lambda item: item[1]["unit"]["planned_slot_index"])


def execute_ledger(ledger: ExperimentLedger, plan: dict, protocol: dict, data_directory: Path,
                   *, execute: bool, retry_invalid: bool, recovered: int, root: Path,
                   execute_one, one_replicate_per_session: bool = False) -> dict:

    session_replicate = None
    if execute and one_replicate_per_session:
        unfinished = [state["unit"]["replicate"] for _, state in ordered_ledger_states(ledger)
                      if state["status"] not in {"completed", "excluded"}]
        session_replicate = min(unfinished, default=None)

    if execute:
        for unit_id, state in ordered_ledger_states(ledger):
            if state["status"] != "planned":
                continue
            unit = state["unit"]
            if unit["condition_id"] in {"A", "B"}:
                report = Path(unit["discovery_report"]) if unit["discovery_report"] else None
                if report is None or not report.is_file() or not unit.get("discovery_sha256"):
                    raise ValueError(f"Verified discovery report missing for {unit['unit_id']}.")
                if sha256_file(report) != unit["discovery_sha256"]:
                    raise ValueError(f"Discovery report changed after planning: {unit['unit_id']}.")
            if unit["condition_id"] == "C" and not plan["seclists_source_root_resolved"].is_dir():
                raise ValueError("Pinned SecLists source directory is missing.")

    recoverable_invalids = [unit_id for unit_id, state in ledger.statuses().items()
                            if state["status"] == "invalid"]
    if recoverable_invalids and execute and not retry_invalid:
        result = summarize(ledger)
        result.update(recovered_interrupted_attempts=recovered,
                      blocked_by_invalid_runs=recoverable_invalids,
                      next_action="repair the local runtime, then resume with --retry-invalid",
                      **({"replicate_session": {"status": "blocked_by_invalid_runs",
                                                  "replicate": session_replicate}}
                         if one_replicate_per_session else {}))
        return result

    if execute:
        for unit_id, state in ordered_ledger_states(ledger):
            unit = state.get("unit")
            if unit is None:
                continue
            if (one_replicate_per_session and session_replicate is not None
                    and unit["replicate"] > session_replicate):
                break
            if state["status"] in {"completed", "excluded"}:
                continue
            was_invalid = state["status"] == "invalid"
            if was_invalid and not retry_invalid:
                break
            if state["status"] not in {"planned", "invalid"}:
                continue
            attempt_number = state["attempt_count"] + 1
            prior_attempt = state.get("last_attempt_id") if was_invalid else None
            run_id = "run-" + uuid4().hex[:16]
            attempt_id = f"attempt-{attempt_number}-" + uuid4().hex[:10]
            attempt = {"run_id": run_id, "attempt_id": attempt_id,
                       "attempt_number": attempt_number, "retry_of_attempt_id": prior_attempt}
            if was_invalid:
                ledger.append("attempt_retried", unit_id=unit_id, run_id=run_id, attempt_id=attempt_id,
                              attempt_number=attempt_number, retry_of_attempt_id=prior_attempt,
                              state_reused=False, reset_required=True)
            ledger.append("attempt_started", **unit, run_id=run_id, attempt_id=attempt_id,
                          attempt_number=attempt_number, retry_of_attempt_id=prior_attempt,
                          reset_required=True, fresh_login_required=True, state_reused=False)
            index_preflight = None
            try:
                if unit["condition_id"] == "B":
                    index_preflight = prepare_condition_b_index(unit, attempt, plan, data_directory, root)
                details = execute_one(unit, attempt, plan, protocol, data_directory, root)
                if index_preflight is not None:
                    details["condition_b_index_preflight"] = index_preflight
            except KeyboardInterrupt:
                ledger.append("attempt_invalid", unit_id=unit_id, run_id=run_id, attempt_id=attempt_id,
                              attempt_number=attempt_number, failure_code="orchestrator_interrupted",
                              attack_failure=False, state_reused=False,
                              recovery_action="repair_environment_then_start_new_attempt_after_database_reset")
                raise
            except Exception as failure:
                code = failure.code if isinstance(failure, ExecutionFailure) else "orchestrator_error"
                details = failure.details if isinstance(failure, ExecutionFailure) else {
                    "message": str(failure), "exception_type": type(failure).__name__}
                if index_preflight is not None:
                    details = {**details, "condition_b_index_preflight": index_preflight}
                budget = protocol["generation"]["candidate_budget"]
                generated_count = details.get("generated_candidate_count", 0)
                ledger.append("attempt_invalid", unit_id=unit_id, run_id=run_id, attempt_id=attempt_id,
                              attempt_number=attempt_number, failure_code=code, failure_details=details,
                              candidate_budget=budget, generated_candidate_count=generated_count,
                              candidate_generation_failed_count=details.get(
                                  "candidate_generation_failed_count", max(0, budget - generated_count)),
                              duplicate_candidate_count=details.get("duplicate_candidate_count", 0),
                              valid_candidates_executed=details.get("valid_candidates_executed", 0),
                              decision_records=details.get("decision_records", 0),
                              payload_records=details.get("payload_records", 0),
                              confirmations_per_candidate=protocol["validation"]["confirmations_per_candidate"],
                              logical_probe_submissions=details.get("logical_probe_submissions"),
                              http_request_calls=details.get("http_request_calls"),
                              database_reset_performed=details.get("database_reset_performed", False),
                              budget_complete=False,
                              attack_failure=False, state_reused=False,
                              recovery_action="repair_environment_then_start_new_attempt_after_database_reset")
                break
            ledger.append("attempt_completed", unit_id=unit_id, run_id=run_id, attempt_id=attempt_id,
                          attempt_number=attempt_number, **details)
            if details.get("metric_eligible") is False:
                ledger.append("run_excluded", unit_id=unit_id, run_id=run_id, attempt_id=attempt_id,
                              exclusion_reason=details.get("exclusion_reason", "incomplete_budget"),
                              metric_eligible=False)

    result = summarize(ledger)
    result["recovered_interrupted_attempts"] = recovered
    if execute and one_replicate_per_session and session_replicate is not None:
        states = ordered_ledger_states(ledger)
        replicate_states = [state for _, state in states
                            if state["unit"]["replicate"] == session_replicate]
        block_finished = bool(replicate_states) and all(
            state["status"] in {"completed", "excluded"} for state in replicate_states)
        remaining_replicates = [state["unit"]["replicate"] for _, state in states
                                if state["unit"]["replicate"] > session_replicate
                                and state["status"] not in {"completed", "excluded"}]
        next_replicate = min(remaining_replicates, default=None)
        if block_finished and next_replicate is not None:
            ledger.append("execution_paused", replicate=session_replicate,
                          next_replicate=next_replicate,
                          pause_policy_id="one-replicate-per-session-v1",
                          pause_reason="replicate_block_finished")
            result = summarize(ledger)
            result["recovered_interrupted_attempts"] = recovered
            result["replicate_session"] = {
                "status": "paused_at_replicate_boundary",
                "finished_replicate": session_replicate,
                "next_replicate": next_replicate,
            }
            result["next_action"] = (
                "Lanjutkan plan dan ledger yang sama dengan --resume --execute "
                "--one-replicate-per-session."
            )
        else:
            result["replicate_session"] = {
                "status": "plan_complete" if block_finished else "replicate_incomplete",
                "finished_replicate": session_replicate if block_finished else None,
                "next_replicate": next_replicate,
            }
    elif execute and one_replicate_per_session:
        result["replicate_session"] = {"status": "plan_already_complete"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Local JSON plan, stored outside sources/.")
    parser.add_argument("--recover-adaptive-artifact", action="store_true",
                        help="Rebuild one interrupted S1 A ledger summary from its saved adaptive artifact, without sending probes.")
    parser.add_argument("--resume", action="store_true", help="Continue an existing ledger without reusing session state.")
    parser.add_argument("--execute", action="store_true", help="Generate candidates and send probes to local DVWA.")
    parser.add_argument("--one-replicate-per-session", action="store_true",
                        help="Run the next unfinished replicate block, record a pause at its boundary, then return.")
    parser.add_argument("--retry-invalid", action="store_true",
                        help="Start new attempts for invalid runs after runtime repair; each attempt resets the database.")
    parser.add_argument("--confirm-local-dvwa", action="store_true",
                        help="Confirm the configured target is the researcher's local DVWA.")
    parser.add_argument("--confirm-database-reset", action="store_true",
                        help="Confirm the runner may reset the local DVWA sample database before each condition-run.")
    parser.add_argument("--formal-execution-approval", type=Path,
                        help="Researcher-authored formal execution receipt bound to the active release and exact plan.")
    parser.add_argument("--condition-b-runner-amendment", type=Path,
                        help="Explicit B index recovery amendment for R3, preserving completed R1/R2 and the original release.")
    args = parser.parse_args()
    if args.recover_adaptive_artifact and (args.execute or args.resume or args.retry_invalid
                                            or args.one_replicate_per_session
                                            or args.formal_execution_approval or args.condition_b_runner_amendment):
        parser.error("--recover-adaptive-artifact cannot be combined with execution, resume, retry, or replicate-session flags.")
    result = (recover_adaptive_s1_attempt(args.plan) if args.recover_adaptive_artifact else
              execute_plan(args.plan, execute=args.execute, resume=args.resume,
                           retry_invalid=args.retry_invalid,
                           confirm_local_dvwa=args.confirm_local_dvwa,
                           confirm_database_reset=args.confirm_database_reset,
                           one_replicate_per_session=args.one_replicate_per_session,
                           formal_execution_approval_path=args.formal_execution_approval,
                           condition_b_runner_amendment_path=args.condition_b_runner_amendment))
    print(json.dumps(result,
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
