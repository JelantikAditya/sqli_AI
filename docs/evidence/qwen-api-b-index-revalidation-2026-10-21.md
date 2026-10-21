# Revalidasi snapshot Chroma untuk kondisi B API, 21 Oktober 2026

Status: **menunggu review peneliti**. Paket ini mencatat hash file aktif untuk bahan keputusan pilot B. Ini bukan approval dan belum membuat receipt pilot.

## Hasil hash

- Identitas korpus, source lock, knowledge base, dan manifest cocok dengan receipt formal 17 Oktober.
- 4 dari 6 file indeks cocok dengan hash approval 17 Oktober.
- File yang berbeda: `data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3/4176542f-e8f6-4a46-8652-598aedaf3721/data_level0.bin`, `data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3/chroma.sqlite3`.
- Hash keenam file aktif cocok dengan hash `current_sha256` yang direkam pada review 19 Oktober.
- Receipt lama berstatus `approved-for-formal-use` dan `formal_execution_approval` bernilai `false`. Runner API B meminta receipt terpisah berstatus `approved-for-pilot-use`.

Hash mismatch hanya menunjukkan perbedaan byte. Pemeriksaan ini tidak membuka Chroma atau SQLite, jadi tidak menyimpulkan apakah isi record atau metadata berubah.

## Batas verifikasi

Perintah `development/audit_analysis_corpus_review.py --phase verify` masih gagal pada perbandingan byte mentah karena checkout Windows mengonversi LF menjadi CRLF. Revisi checker cocok dengan record; baseline dan 26 file inventory cocok kembali setelah normalisasi CRLF ke LF di memori, tanpa mengubah hash baseline. Rekonsiliasi dan reproduksi review penuh ada di [catatan rekonsiliasi](qwen-api-b-review-reconciliation-2026-10-21.md) dan [hasil verifikasi](qwen-api-b-review-verification-2026-10-21.md).

Pemeriksaan isi pada salinan aktif dan arsip acuan ada di [laporan pemeriksaan snapshot](qwen-api-b-index-content-inspection-2026-10-21.md). Semua sembilan record, metadata, konfigurasi dan vektor cocok dengan acuan; dua hash file tetap berbeda dan tercatat di laporan tersebut.

Tidak ada Chroma/SQLite yang dibuka, panggilan model atau embedding, request DVWA, perubahan file sumber, atau receipt persetujuan yang dibuat.

Data hash lengkap ada di [`qwen-api-b-index-revalidation-2026-10-21.json`](qwen-api-b-index-revalidation-2026-10-21.json). Setelah peneliti menentukan apakah snapshot aktif ini dapat dipakai, receipt baru harus mengikat korpus, source lock, dan keenam hash indeks tersebut.
