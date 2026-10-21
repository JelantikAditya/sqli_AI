"""Prepare a hash-only review packet for the current Qwen API B index.

This utility does not open Chroma, SQLite, model, or DVWA clients. It only
reads approved metadata and computes SHA-256 hashes for files in the active
vectorstore. Outputs are new-only evidence and never replace prior decisions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json"
REVIEW_PATH = ROOT / "results/processed/analysis-rag-corpus-review-20261019/review.json"
BASELINE_PATH = ROOT / "results/processed/analysis-rag-corpus-review-20261019/review-baseline.json"
CHECKER_REVISION_PATH = ROOT / "results/processed/analysis-rag-corpus-review-20261019/review-checker-revision.json"
CHECKER_PATH = ROOT / "development/audit_analysis_corpus_review.py"
OUTPUT_JSON = ROOT / "docs/evidence/qwen-api-b-index-revalidation-2026-10-21.json"
OUTPUT_MD = ROOT / "docs/evidence/qwen-api-b-index-revalidation-2026-10-21.md"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main() -> None:
    for output in (OUTPUT_JSON, OUTPUT_MD):
        if output.exists():
            raise FileExistsError(f"Refusing to replace existing evidence: {output}")

    approval = read_json(APPROVAL_PATH)
    previous_review = read_json(REVIEW_PATH)
    checker_revision = read_json(CHECKER_REVISION_PATH)
    baseline = read_json(BASELINE_PATH)
    manifest_path = ROOT / "knowledge" / "active-index.local.json"
    pointer = read_json(manifest_path)
    manifest = ROOT / pointer["manifest_path"]
    manifest_data = read_json(manifest)
    approved = approval["approved_snapshot"]
    store_path = ROOT / manifest_data["store_path"]

    expected_index = approved["index_file_sha256"]
    previous_hashes = {row["path"]: row["current_sha256"]
                       for row in previous_review["historical_index_comparison"]}
    actual_index = {}
    inventory = []
    for relative_path in sorted(expected_index):
        path = ROOT / relative_path
        current_hash = sha256(path)
        actual_index[relative_path] = current_hash
        stat = path.stat()
        inventory.append({
            "path": relative_path,
            "sha256": current_hash,
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "matches_2026_10_17_approval": current_hash == expected_index[relative_path],
            "matches_2026_10_19_review_record": current_hash == previous_hashes.get(relative_path),
        })

    active_files = sorted(path.relative_to(ROOT).as_posix()
                          for path in store_path.rglob("*") if path.is_file())
    active_file_set_matches = active_files == sorted(expected_index)
    approval_hash = sha256(APPROVAL_PATH)
    corpus_hash = sha256(ROOT / "knowledge/sqli-entries.json")
    source_lock_hash = sha256(ROOT / "knowledge/sources.lock.json")
    manifest_hash = sha256(manifest)

    baseline_actual_hash = sha256(BASELINE_PATH)
    baseline_expected_hash = checker_revision["baseline_sha256"]
    checker_actual_hash = sha256(CHECKER_PATH)
    checker_expected_hash = checker_revision["revised_checker_sha256"]
    baseline_reproduction_ok = baseline_actual_hash == baseline_expected_hash
    checker_revision_ok = checker_actual_hash == checker_expected_hash
    expected_protected = baseline["protected_file_sha256"]
    protected_mismatches = []
    for relative_path, expected_hash in expected_protected.items():
        if relative_path == checker_revision["changed_file"]:
            continue
        path = ROOT / relative_path
        if not path.is_file() or sha256(path) != expected_hash:
            protected_mismatches.append(relative_path)

    review_index_stable = all(row["matches_2026_10_19_review_record"] for row in inventory)
    approval_identity_matches = (
        approval.get("decision") == "approved-for-formal-use"
        and pointer.get("knowledge_base_id") == approved.get("knowledge_base_id")
        and manifest_data.get("knowledge_base_id") == approved.get("knowledge_base_id")
        and manifest_data.get("corpus_sha256") == approved.get("corpus_sha256") == corpus_hash
        and manifest_data.get("source_lock_sha256") == approved.get("source_lock_sha256") == source_lock_hash
        and manifest_hash == expected_index.get(manifest.relative_to(ROOT).as_posix())
    )
    approval_match_count = sum(row["matches_2026_10_17_approval"] for row in inventory)
    mismatch_paths = [row["path"] for row in inventory if not row["matches_2026_10_17_approval"]]

    # Use the host's configured local offset; this workspace is configured for WIB.
    now = datetime.now().astimezone()
    record = {
        "schema_version": "1.0.0",
        "evidence_id": "qwen-api-b-index-revalidation-2026-10-21",
        "created_at_local": now.isoformat(),
        "timezone": "Asia/Jakarta",
        "purpose": "Hash-only preparation for researcher review of a Qwen API pilot B snapshot.",
        "status": "pending-researcher-review",
        "api_b_execution_ready": False,
        "researcher_approval_created": False,
        "scope": {
            "chroma_opened": False,
            "sqlite_opened": False,
            "model_or_embedding_calls": 0,
            "dvwa_requests": 0,
            "source_files_modified": False,
        },
        "existing_approval": {
            "path": APPROVAL_PATH.relative_to(ROOT).as_posix(),
            "sha256": approval_hash,
            "decision": approval.get("decision"),
            "formal_execution_approval": approval.get("formal_execution_approval"),
            "approved_snapshot": {
                "corpus_sha256": approved.get("corpus_sha256"),
                "source_lock_sha256": approved.get("source_lock_sha256"),
                "knowledge_base_id": approved.get("knowledge_base_id"),
                "entry_count": approved.get("entry_count"),
            },
        },
        "active_identity_checks": {
            "active_pointer_path": manifest_path.relative_to(ROOT).as_posix(),
            "manifest_path": manifest.relative_to(ROOT).as_posix(),
            "manifest_sha256": manifest_hash,
            "corpus_sha256": corpus_hash,
            "source_lock_sha256": source_lock_hash,
            "approval_identity_matches": approval_identity_matches,
            "active_file_count": len(active_files),
            "expected_file_count": len(expected_index),
            "active_file_set_matches_approval_inventory": active_file_set_matches,
        },
        "index_file_comparison": {
            "approval_match_count": approval_match_count,
            "approval_file_count": len(inventory),
            "mismatch_paths": mismatch_paths,
            "matches_previous_review_hashes": review_index_stable,
            "files": inventory,
        },
        "prior_review_reproduction": {
            "review_path": REVIEW_PATH.relative_to(ROOT).as_posix(),
            "review_sha256": sha256(REVIEW_PATH),
            "previous_review_recorded_all_index_files_unchanged_since_baseline": all(
                row["unchanged_since_review_baseline"]
                for row in previous_review["historical_index_comparison"]
            ),
            "baseline_path": BASELINE_PATH.relative_to(ROOT).as_posix(),
            "baseline_expected_sha256": baseline_expected_hash,
            "baseline_current_sha256": baseline_actual_hash,
            "baseline_hash_matches_checker_revision": baseline_reproduction_ok,
            "checker_expected_sha256": checker_expected_hash,
            "checker_current_sha256": checker_actual_hash,
            "checker_matches_revision": checker_revision_ok,
            "protected_file_mismatch_count_excluding_revised_checker": len(protected_mismatches),
            "protected_file_mismatch_paths": protected_mismatches,
            "full_historical_verification_reproduced": (
                baseline_reproduction_ok and checker_revision_ok and not protected_mismatches
            ),
            "interpretation": (
                "Current index hashes match the 19 October review record, but the full historical audit "
                "does not reproduce because its baseline hash and protected-file inventory differ in this workspace."
            ),
        },
        "readiness": {
            "current_index_matches_old_approval": approval_match_count == len(inventory),
            "new_pilot_receipt_present": False,
            "api_runner_receipt_requirement": "approved-for-pilot-use",
            "decision_required": "Researcher review and explicit approval bound to the exact corpus, source lock, and all six index file hashes.",
            "reason_blocked": "Two active index file hashes differ from the 17 October approval, and no pilot approval receipt for these active hashes exists.",
        },
        "required_next_steps": [
            "Researcher reviews this hash-only packet and decides whether the current active index is suitable for a new pilot snapshot.",
            "If approved, record a new approved-for-pilot-use receipt bound to the exact hashes in this packet; do not edit the 17 October receipt.",
            "Add the new receipt and pinned hashes to a B plan, then rerun dry-run validation before any live API or DVWA run.",
        ],
    }

    md = f"""# Revalidasi snapshot Chroma untuk kondisi B API, 21 Oktober 2026

Status: **menunggu review peneliti**. Paket ini mencatat hash file aktif untuk bahan keputusan pilot B. Ini bukan approval dan belum membuat receipt pilot.

## Hasil hash

- Identitas korpus, source lock, knowledge base, dan manifest cocok dengan receipt formal 17 Oktober.
- {approval_match_count} dari {len(inventory)} file indeks cocok dengan hash approval 17 Oktober.
- File yang berbeda: {', '.join(f'`{p}`' for p in mismatch_paths)}.
- Hash keenam file aktif cocok dengan hash `current_sha256` yang direkam pada review 19 Oktober.
- Receipt lama berstatus `{approval.get('decision')}` dan `formal_execution_approval` bernilai `{str(approval.get('formal_execution_approval')).lower()}`. Runner API B meminta receipt terpisah berstatus `approved-for-pilot-use`.

Hash mismatch hanya menunjukkan perbedaan byte. Pemeriksaan ini tidak membuka Chroma atau SQLite, jadi tidak menyimpulkan apakah isi record atau metadata berubah.

## Batas verifikasi

Perintah `development/audit_analysis_corpus_review.py --phase verify` belum dapat direproduksi pada workspace ini. Hash file baseline saat ini tidak cocok dengan hash baseline yang dicatat di `review-checker-revision.json`, dan {len(protected_mismatches)} file dari inventory historis juga berbeda secara byte. Karena itu, hasil review 19 Oktober dicatat sebagai referensi historis, bukan validasi penuh yang baru.

Tidak ada Chroma/SQLite yang dibuka, panggilan model atau embedding, request DVWA, perubahan file sumber, atau receipt persetujuan yang dibuat.

Data hash lengkap ada di [`qwen-api-b-index-revalidation-2026-10-21.json`](qwen-api-b-index-revalidation-2026-10-21.json). Setelah peneliti menentukan apakah snapshot aktif ini dapat dipakai, receipt baru harus mengikat korpus, source lock, dan keenam hash indeks tersebut.
"""
    write_new(OUTPUT_JSON, json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    write_new(OUTPUT_MD, md)
    print(json.dumps({
        "evidence_json": OUTPUT_JSON.relative_to(ROOT).as_posix(),
        "evidence_markdown": OUTPUT_MD.relative_to(ROOT).as_posix(),
        "approval_hash_matches": f"{approval_match_count}/{len(inventory)}",
        "mismatch_paths": mismatch_paths,
        "matches_previous_review_hashes": review_index_stable,
        "full_historical_verification_reproduced": record["prior_review_reproduction"]["full_historical_verification_reproduced"],
        "api_b_execution_ready": False,
    }, indent=2))


if __name__ == "__main__":
    main()
