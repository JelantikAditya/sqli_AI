"""Reproduce the saved review with an in-memory LF view of CRLF-converted files."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs/evidence"
RECONCILIATION = EVIDENCE_DIR / "qwen-api-b-review-reconciliation-2026-10-21.json"
OUTPUT_JSON = EVIDENCE_DIR / "qwen-api-b-review-verification-2026-10-21.json"
OUTPUT_MD = EVIDENCE_DIR / "qwen-api-b-review-verification-2026-10-21.md"
CHECKER_REL = "development/audit_analysis_corpus_review.py"
CHECKER_PATH = ROOT / CHECKER_REL
REVIEW_DIR = ROOT / "results/processed/analysis-rag-corpus-review-20261019"
BASELINE_REL = "results/processed/analysis-rag-corpus-review-20261019/review-baseline.json"
REVISION_REL = "results/processed/analysis-rag-corpus-review-20261019/review-checker-revision.json"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if OUTPUT_JSON.exists() or OUTPUT_MD.exists():
        raise FileExistsError("Refusing to replace prior normalized-review verification.")

    reconciliation = json.loads(RECONCILIATION.read_text(encoding="utf-8"))
    revision = json.loads((REVIEW_DIR / "review-checker-revision.json").read_text(encoding="utf-8"))
    normalizable = set(reconciliation["protected_inventory_reconciliation"]["mismatched_paths"])
    normalizable.add(BASELINE_REL)
    normalizable.add(REVISION_REL)
    checker_hash = sha_bytes(CHECKER_PATH.read_bytes())
    if checker_hash != revision["revised_checker_sha256"]:
        raise ValueError("The active audit checker does not match its recorded revision.")
    if not reconciliation["verification_conclusion"]["format_normalized_protected_hashes_match"]:
        raise ValueError("The CRLF reconciliation did not establish an all-match normalized inventory.")

    for relative in sorted(normalizable):
        path = ROOT / relative
        data = path.read_bytes()
        normalized = data.replace(b"\r\n", b"\n")
        if b"\r" in normalized:
            raise ValueError(f"Unexpected bare carriage return in {relative}.")

    spec = importlib.util.spec_from_file_location("historical_review_checker", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the recorded historical checker.")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    original_sha = checker.sha

    def canonical_sha(path: Path) -> str:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(ROOT).as_posix()
        if relative in normalizable:
            return sha_bytes(resolved.read_bytes().replace(b"\r\n", b"\n"))
        return original_sha(resolved)

    checker.sha = canonical_sha
    reproduced = checker.build_review()
    recorded = checker.read(REVIEW_DIR / "review.json")
    if reproduced != recorded:
        different = sorted(key for key in set(reproduced) | set(recorded)
                           if reproduced.get(key) != recorded.get(key))
        raise ValueError(f"Normalized historical review differs in fields: {different}")

    baseline_data = (ROOT / BASELINE_REL).read_bytes()
    record = {
        "schema_version": "1.0.0",
        "evidence_id": "qwen-api-b-review-verification-2026-10-21",
        "created_at_local": datetime.now().astimezone().isoformat(),
        "purpose": "Reproduce the saved historical review while preserving every original receipt and file byte.",
        "checker": {
            "path": CHECKER_REL,
            "sha256": checker_hash,
            "revision_record_sha256": revision["revised_checker_sha256"],
            "matches_recorded_revision": True,
        },
        "normalization": {
            "method": "In-memory CRLF to LF normalization only for the baseline JSON, the checker-revision JSON, and 26 listed UTF-8 text files.",
            "baseline_original_sha256": sha_bytes(baseline_data),
            "baseline_recorded_sha256": revision["baseline_sha256"],
            "baseline_lf_normalized_sha256": sha_bytes(baseline_data.replace(b"\r\n", b"\n")),
            "protected_text_files_normalized": len(normalizable) - 2,
            "revision_record_lf_normalized_sha256": sha_bytes((ROOT / REVISION_REL).read_bytes().replace(b"\r\n", b"\n")),
            "revision_record_sha256_recorded_in_review": checker.read(REVIEW_DIR / "review.json")["checker_revision_sha256"],
            "revision_record_lf_hash_matches_saved_review": (
                sha_bytes((ROOT / REVISION_REL).read_bytes().replace(b"\r\n", b"\n"))
                == checker.read(REVIEW_DIR / "review.json")["checker_revision_sha256"]
            ),
            "original_baseline_or_inventory_rewritten": False,
            "decision_receipts_rewritten": False,
        },
        "verification": {
            "historical_build_review_reproduced": True,
            "reproduced_review_equals_saved_review_json": True,
            "historical_index_comparison_reproduced": True,
            "reviewed_entries": reproduced["summary"]["entries_reviewed"],
            "selected_entries_in_v4": reproduced["summary"]["selected_entries_in_v4"],
            "protected_files_checked": reproduced["mechanical_checks"]["protected_files_unchanged"],
            "formal_sources_checked": reproduced["mechanical_checks"]["formal_sources_unchanged"],
            "index_files_matching_2026_10_17_approval": reproduced["mechanical_checks"]["formal_index_files_match_historical_approval"],
            "index_files_unchanged_in_saved_review": reproduced["mechanical_checks"]["formal_index_files_unchanged_since_review_baseline"],
        },
        "scope": {
            "source_files_modified": False,
            "index_files_modified": False,
            "chroma_opened": False,
            "model_or_embedding_calls": 0,
            "dvwa_requests": 0,
            "pilot_or_formal_approval_created": False,
        },
        "interpretation": "The prior byte-exact command remains sensitive to Windows CRLF checkout conversion in the baseline, the checker-revision record, and 26 protected text files. The same recorded checker revision reproduces the entire saved review when comparing a transient LF-normalized view; no recorded baseline hash was replaced.",
    }
    md = f"""# Verifikasi ulang audit dengan normalisasi akhir baris, 21 Oktober 2026

Hasil rekonsiliasi berhasil. Checker aktif memiliki hash yang sama dengan revisi yang direkam. Tanpa mengubah file apa pun, checker tersebut membangun ulang seluruh `review.json` yang tersimpan dengan membandingkan tampilan LF sementara untuk baseline, receipt revisi checker, dan 26 file teks yang dikonversi ke CRLF oleh checkout Windows.

- Hasil review tersimpan cocok persis dengan hasil rekonstruksi.
- {reproduced['mechanical_checks']['protected_files_unchanged']} protected files dan {reproduced['mechanical_checks']['formal_sources_unchanged']} sumber formal lulus pemeriksaan inventory pada tampilan LF tersebut.
- Enam file indeks tetap dibandingkan sebagai byte asli. {reproduced['mechanical_checks']['formal_index_files_match_historical_approval']} dari enam cocok dengan receipt 17 Oktober, dan keenam hash cocok dengan hash yang dicatat review 19 Oktober.
- Baseline dan receipt lama tidak ditulis ulang. Normalisasi hanya berlangsung di memori.

Verifikasi ini merekonsiliasi reproducibility review historis. Persetujuan pilot B tetap keputusan terpisah dan belum dibuat.
"""
    with OUTPUT_JSON.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with OUTPUT_MD.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(md)
    print(json.dumps({
        "checker_revision_matches": True,
        "historical_review_reproduced": True,
        "saved_review_matches": True,
        "protected_files_checked": reproduced["mechanical_checks"]["protected_files_unchanged"],
        "formal_sources_checked": reproduced["mechanical_checks"]["formal_sources_unchanged"],
        "evidence_json": OUTPUT_JSON.relative_to(ROOT).as_posix(),
        "evidence_markdown": OUTPUT_MD.relative_to(ROOT).as_posix(),
    }, indent=2))


if __name__ == "__main__":
    main()
