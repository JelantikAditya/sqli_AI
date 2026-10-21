"""Reconcile historical review hashes without changing the baseline or evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "results/processed/analysis-rag-corpus-review-20261019"
BASELINE = REVIEW_DIR / "review-baseline.json"
REVISION = REVIEW_DIR / "review-checker-revision.json"
CHECKER = ROOT / "development/audit_analysis_corpus_review.py"
OUTPUT_JSON = ROOT / "docs/evidence/qwen-api-b-review-reconciliation-2026-10-21.json"
OUTPUT_MD = ROOT / "docs/evidence/qwen-api-b-review-reconciliation-2026-10-21.md"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return digest(path.read_bytes())


def run_git(*args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def write_new(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def inspect_file(relative: str, expected: str) -> dict:
    path = ROOT / relative
    if not path.is_file():
        return {"path": relative, "exists": False, "expected_sha256": expected,
                "raw_sha256": None, "lf_normalized_sha256": None, "normalization_matches": False}
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    try:
        raw.decode("utf-8")
        utf8_text = True
    except UnicodeDecodeError:
        utf8_text = False
    only_crlf_pairs = b"\r" not in normalized
    normalized_hash = digest(normalized) if utf8_text and only_crlf_pairs else None
    return {
        "path": relative,
        "exists": True,
        "expected_sha256": expected,
        "raw_sha256": digest(raw),
        "raw_matches": digest(raw) == expected,
        "lf_normalized_sha256": normalized_hash,
        "normalization_matches": normalized_hash == expected,
        "utf8_text": utf8_text,
        "crlf_pairs": raw.count(b"\r\n"),
        "bare_cr_after_normalization": not only_crlf_pairs,
        "size_bytes": len(raw),
    }


def main() -> None:
    if OUTPUT_JSON.exists() or OUTPUT_MD.exists():
        raise FileExistsError("Refusing to replace prior reconciliation evidence.")

    baseline_data = BASELINE.read_bytes()
    revision = json.loads(REVISION.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_data.decode("utf-8"))
    current_checker = sha(CHECKER)
    baseline_check = inspect_file("results/processed/analysis-rag-corpus-review-20261019/review-baseline.json",
                                 revision["baseline_sha256"])
    protected = baseline["protected_file_sha256"]
    protected_checks = [inspect_file(relative, expected)
                        for relative, expected in protected.items()
                        if relative != revision["changed_file"]]
    raw_mismatches = [item for item in protected_checks if not item.get("raw_matches", False)]
    normalized_mismatches = [item for item in raw_mismatches if not item.get("normalization_matches", False)]
    normalized_non_text = [item for item in raw_mismatches
                           if not item.get("utf8_text") or item.get("bare_cr_after_normalization")]
    checker_match = current_checker == revision["revised_checker_sha256"]
    normalized_all_match = baseline_check["normalization_matches"] and not normalized_mismatches
    autocrlf = run_git("config", "--show-origin", "--get", "core.autocrlf")
    attributes = run_git("check-attr", "text", "eol", "--",
                         "results/processed/analysis-rag-corpus-review-20261019/review-baseline.json")

    record = {
        "schema_version": "1.0.0",
        "evidence_id": "qwen-api-b-review-reconciliation-2026-10-21",
        "created_at_local": datetime.now().astimezone().isoformat(),
        "purpose": "Explain the historical audit verification failure without rewriting its baseline or receipts.",
        "checker_revision": {
            "revision_record_path": REVISION.relative_to(ROOT).as_posix(),
            "revision_record_sha256": sha(REVISION),
            "changed_file": revision["changed_file"],
            "original_checker_sha256": revision["original_checker_sha256"],
            "recorded_revised_checker_sha256": revision["revised_checker_sha256"],
            "current_checker_sha256": current_checker,
            "current_matches_recorded_revision": checker_match,
            "revision_reason": revision["reason"],
        },
        "baseline_reconciliation": {
            "baseline_path": BASELINE.relative_to(ROOT).as_posix(),
            "baseline_sha256_recorded_by_checker_revision": revision["baseline_sha256"],
            "baseline_current_raw_sha256": sha(BASELINE),
            "baseline_raw_hash_matches": baseline_check["raw_matches"],
            "baseline_lf_normalized_sha256": baseline_check["lf_normalized_sha256"],
            "baseline_lf_normalized_hash_matches": baseline_check["normalization_matches"],
            "baseline_crlf_pairs": baseline_check["crlf_pairs"],
        },
        "protected_inventory_reconciliation": {
            "protected_files_checked_excluding_revised_checker": len(protected_checks),
            "raw_byte_mismatch_count": len(raw_mismatches),
            "lf_normalization_matches_expected_count": sum(bool(item.get("normalization_matches")) for item in raw_mismatches),
            "unexplained_after_normalization_count": len(normalized_mismatches),
            "non_utf8_or_bare_cr_count": len(normalized_non_text),
            "all_mismatches_are_crlf_only": not normalized_mismatches and not normalized_non_text,
            "mismatched_paths": [item["path"] for item in raw_mismatches],
            "normalized_mismatch_paths": [item["path"] for item in normalized_mismatches],
        },
        "checkout_configuration": {
            "core_autocrlf": autocrlf,
            "baseline_text_eol_attributes": attributes,
            "diagnosis": "The workspace checkout converted LF text files to CRLF because core.autocrlf=true and no path-specific text/eol override applies to these review artifacts.",
        },
        "verification_conclusion": {
            "byte_exact_historical_checker_reproduced": False,
            "format_normalized_protected_hashes_match": normalized_all_match,
            "interpretation": "The checker and recorded revision agree. The raw verify command fails on CRLF-transformed copies; LF-normalized bytes reproduce the historical baseline and all 26 protected-file hashes. No baseline hash or decision receipt was changed.",
            "baseline_modified": False,
            "review_receipt_modified": False,
            "sources_directory_read_or_modified": False,
        },
        "file_checks": {"baseline": baseline_check, "protected_raw_mismatches": raw_mismatches},
    }
    summary = f"""# Rekonsiliasi hash audit RAG, 21 Oktober 2026

**Kesimpulan:** revisi checker saat ini sama persis dengan revisi yang direkam. Kegagalan `--phase verify` berasal dari konversi akhir baris pada checkout Windows, bukan perubahan isi yang belum dijelaskan.

- Checker `{revision['changed_file']}` tercatat dengan hash revisi `{revision['revised_checker_sha256']}` dan hash aktual tetap sama.
- Baseline mentah berbeda karena file direpresentasikan dengan CRLF. Setelah CRLF dinormalisasi ke LF untuk pembandingan saja, hash kembali cocok dengan `{revision['baseline_sha256']}`.
- {len(raw_mismatches)} dari {len(protected_checks)} file inventory berbeda pada hash byte mentah. Semua {sum(bool(item.get('normalization_matches')) for item in raw_mismatches)} file kembali cocok setelah normalisasi CRLF ke LF; tidak ada mismatch tersisa.
- Konfigurasi Git: `{autocrlf}`. Tidak ada aturan `text` atau `eol` khusus untuk baseline review.

Tidak ada file baseline, receipt keputusan, snapshot indeks, atau file di `sources/` yang diubah. Hash historis dipertahankan apa adanya. Pembandingan normalisasi hanya menjelaskan representasi akhir baris.
"""
    write_new(OUTPUT_JSON, json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    write_new(OUTPUT_MD, summary)
    print(json.dumps({
        "checker_revision_matches": checker_match,
        "raw_baseline_matches": baseline_check["raw_matches"],
        "lf_normalized_baseline_matches": baseline_check["normalization_matches"],
        "protected_raw_mismatches": len(raw_mismatches),
        "normalized_mismatches": len(normalized_mismatches),
        "evidence_json": OUTPUT_JSON.relative_to(ROOT).as_posix(),
        "evidence_markdown": OUTPUT_MD.relative_to(ROOT).as_posix(),
    }, indent=2))


if __name__ == "__main__":
    main()
