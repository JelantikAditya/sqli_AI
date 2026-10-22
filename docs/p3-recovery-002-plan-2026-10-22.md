# Draft rencana pilot P3 baru, 22 Oktober 2026

Rencana baru `qwen38-api-r2-20261022` disiapkan setelah pilot
`qwen38-api-p3-v3-pilot-20261022` berhenti akibat timeout transport pada
analisis S2-B. Rencana mempertahankan protocol v3 dan menggunakan ID, plan,
budget, ledger, serta folder hasil baru.

## Cakupan dan batas

Rencana mengulang satu cohort penuh: **33 slot applicable**, meliputi kondisi
A/B/C pada S1-S12 dengan satu replikasi. Tiga slot C/Impossible dikecualikan
sesuai desain. Hasil eksperimen ID lain tidak digabungkan. Ini menjaga semua
perbandingan dalam cohort baru memakai urutan dan snapshot runtime yang sama.

Draft budget menetapkan maksimum **960 request API**, maksimum enam jam, nol
retry transport otomatis, dan nol attempt pengganti otomatis. A/B masing-masing
memerlukan hingga 10 kandidat dengan tiga konfirmasi; kondisi C memakai
SecLists lokal. Batas ini adalah ceiling, bukan jaminan durasi atau nilai
tagihan provider.

Dry-run launcher berhasil dengan estimasi terburuk 960 request dan 36 slot
terencana. Tidak ada request API, request DVWA, reset database, atau ledger
run yang dibuat saat menyiapkan draft ini. Semua 32 hash source runtime sama
dengan snapshot v3 sebelumnya. Pemeriksaan akses kecil setelah pilot mendapat
HTTP 200 dan `API_OK` dalam 1,704 detik, tetapi belum menguji kestabilan beban
analisis.

## Berkas

- Plan: `development/qwen_api_p3_v3_recovery_002_plan.template.json`
- Budget draft: `development/qwen_api_p3_v3_recovery_002_budget_20261022.json`
- Receipt dry-run: `docs/evidence/p3-recovery-002-draft-2026-10-22.json`
- Pilot v3 sebelumnya: `results/raw/pilot/qwen38-api-p3-v3-pilot-20261022/`

Peneliti kemudian menyetujui satu eksekusi bounded pada ID ini. Run berhenti
setelah 25 request API ketika analisis S1-B mengalami read timeout. Hasil
parsial dan rekonsiliasi audit dicatat di
[laporan recovery-002](p3-recovery-002-results-2026-10-22.md) dan
[receipt audit](evidence/p3-recovery-002-execution-audit-2026-10-22.json).
ID ini tidak boleh di-resume atau ditambah attempt pengganti otomatis.
