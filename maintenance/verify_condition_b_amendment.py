"""Audit a B runner amendment and exercise recovery on an isolated index copy only."""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
import run_local_experiments as runner


def verify(amendment_path: Path) -> dict:
    receipt = runner.read_json(amendment_path)
    plan_path = ROOT / receipt["formal_plan_path"]
    protocol = runner.load_protocol()
    plan = runner.validate_plan(runner.read_json(plan_path), protocol, ROOT, verify_index=False)
    amendment = runner.validate_condition_b_runner_amendment(amendment_path, plan_path, plan, protocol, ROOT)
    approval = ROOT / receipt["original_execution_approval_path"]
    authorization = runner.validate_formal_execution_approval(approval, plan_path, plan, protocol, ROOT,
                                                              runner_amendment=amendment)
    # The default frozen-source guard must still reject an unamended runner change.
    try:
        runner.validate_formal_execution_approval(approval, plan_path, plan, protocol, ROOT)
    except ValueError as error:
        if "Source inventory differs" not in str(error):
            raise
    else:
        raise AssertionError("A changed runner was accepted without its amendment.")
    unexpected = {**runner.source_snapshot_hashes(ROOT), "dvwa/validation_loop.py": "0" * 64}
    with patch.object(runner, "source_snapshot_hashes", return_value=unexpected):
        try:
            runner.validate_formal_execution_approval(approval, plan_path, plan, protocol, ROOT,
                                                      runner_amendment=amendment)
        except ValueError as error:
            if "Source inventory differs" not in str(error):
                raise
        else:
            raise AssertionError("The B amendment accepted another changed source file.")

    # Copy the real six-file approved index and its pinned metadata into a disposable workspace.
    # No Chroma client, model, database reset, or HTTP executor is invoked.
    with tempfile.TemporaryDirectory(prefix="offline-b-amendment-", dir=ROOT / "results/raw") as value:
        temporary = Path(value).resolve()
        assert temporary.is_relative_to((ROOT / "results/raw").resolve())
        snapshot = plan["knowledge_snapshot"]
        for field in ("manifest_path", "corpus_path", "review_decision_path", "source_lock_path"):
            name = snapshot[field]
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        for name, payload in amendment["index_payload_resolved"].items():
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        target = next(name for name in snapshot["index_file_sha256"] if name.endswith("data_level0.bin"))
        original = (temporary / target).read_bytes()
        (temporary / target).write_bytes(bytes([original[0] ^ 1]) + original[1:])
        clone_plan = {"knowledge_snapshot": snapshot, "condition_b_runner_amendment_resolved": amendment}
        unit = {"condition_id": "B", "replicate": 3, "unit_id": "offline-b-copy-r3"}
        directory = temporary / "results/raw/formal/offline-copy"
        restored = runner.prepare_condition_b_index(unit, {"attempt_id": "offline-restored"},
                                                     clone_plan, directory, temporary)
        unchanged = runner.prepare_condition_b_index(unit, {"attempt_id": "offline-unchanged"},
                                                      clone_plan, directory, temporary)
        assert restored["status"] == "restored-and-verified"
        assert unchanged["status"] == "verified-unchanged"
        assert (temporary / target).read_bytes() == original

    inventory = runner.read_json(ROOT / receipt["preserved_history"]["inventory_path"])["files"]
    changed = [name for name, expected in inventory.items() if runner.sha256_file(ROOT / name) != expected]
    directory = ROOT / "results/raw/formal" / plan["experiment_id"]
    dynamic = {(directory / name).relative_to(ROOT).as_posix() for name in ("ledger.jsonl", "checkpoint.json")}
    immutable_changed = [name for name in changed if name not in dynamic]
    if immutable_changed:
        raise AssertionError(f"Historical files changed: {immutable_changed}")
    checkpoint = runner.read_json(directory / "checkpoint.json")
    r3_attempts = sum(state["attempt_count"] for state in checkpoint["runs"].values()
                      if state["unit"]["replicate"] == 3)
    return {"status": "passed", "checked_at_utc": runner.now_utc(),
            "runner_sha256": receipt["runner_after_sha256"],
            "amendment_sha256": runner.sha256_file(amendment_path),
            "original_formal_authorization_validated": authorization["formal_execution_approval"],
            "unamended_runner_rejected": True, "other_source_changes_rejected": True,
            "historical_files_unchanged": len(inventory) - len(changed),
            "dynamic_files_advanced": changed, "checkpoint_counts": checkpoint["status_counts"],
            "approved_index_bytes": sum(len(value) for value in amendment["index_payload_resolved"].values()),
            "isolated_restore_seconds": restored["elapsed_seconds"],
            "isolated_unchanged_check_seconds": unchanged["elapsed_seconds"],
            "benchmark_scope": "file copy and hash verification only, no model or HTTP calls",
            "formal_r3_attempts_started": r3_attempts, "database_resets": 0, "http_probe_submissions": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("amendment", type=Path)
    args = parser.parse_args()
    report = verify(args.amendment.resolve())
    output = args.amendment.resolve().parent / "verification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
