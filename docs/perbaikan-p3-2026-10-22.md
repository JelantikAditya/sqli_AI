# Penutupan P2 dan perbaikan integrasi P3, 22 Oktober 2026

Catatan ini merekam checkpoint perbaikan analisis sebelum pilot live v2.
Perkembangan setelahnya, termasuk kontrol/smoke yang selesai, pilot yang
berhenti dan perbaikan status generasi v3, ada di
[laporan lanjutan P3](p3-smoke-kontrol-2026-10-22.md).

**P2 ditutup oleh peneliti dengan satu kasus unresolved sebagai keterbatasan.
Ketiga temuan integrasi P3 sudah diperbaiki dan diverifikasi offline.** Pilot
live lintas skenario dan eksperimen formal API belum dijalankan.

## Keputusan P2

Peneliti secara langsung menerima hasil run-005 dan meminta penutupan P2
serta kelanjutan perbaikan P3. Keputusan disimpan dalam
[receipt penutupan P2](evidence/qwen-api-p2-closure-2026-10-22.json), terpisah
dari receipt eksekusi yang sudah dibekukan.

Hasil yang diterima tetap 17/18 evaluable, agreement 17/17 dan coverage
94,44%. Kasus `rv-e6f30675d8d4` tetap unresolved akibat timeout, tanpa
verdict model. Tidak ada pengiriman ulang, penggantian label atau penggabungan
run sebagai sampel independen. Penutupan milestone bukan klaim FPR/PSR formal.

## Perbaikan P3

| Temuan | Perubahan | Verifikasi |
| --- | --- | --- |
| P3-01, gate input invalid terlambat | Validasi struktur/koordinat dan kelayakan runtime/baseline dilakukan sebelum rendering pesan dan request API. Input invalid menghasilkan `runtime_invalid` tanpa klaim model. | Enam kasus invalid dari tiga teknik menghasilkan nol panggilan API; rendering pesan juga tidak dijalankan. |
| P3-02, penolakan parser menjadi `completed` | Hanya output parser berstatus `ok` masuk normalizer sebagai model output valid. Respons yang ditolak disimpan dalam audit; record analisis berstatus `analysis_error`, dengan `system_claim=null`. | Trial rekaan, referensi lintas trial, ID tak dikenal, referensi tingkat atas tidak lengkap dan JSON rusak tertahan. Ringkasan run tidak memberi keputusan biner eligible dari record tersebut. |
| P3-03, profil analisis berbeda dari P2 | Callback memakai `qwen_api_p2_analysis.prepare/parse` dan runtime memakai konfigurasi analisis yang sama dengan P2. Hash payload checkpoint harus cocok dengan hash request P2. | Seluruh 18 payload paket P2 cocok. Replay 17 respons pada A dan B menghasilkan 34 callback dan 34 payload checkpoint yang cocok. |

Profil analisis aktif adalah `qwen38-api-p2-explicit-evidence-v1`, tanpa RAG,
temperature 0, maksimum output 2048 token dan timeout 90 detik. Analisis
tidak menambahkan `chat_template_kwargs`. Generasi tetap memakai profil
sebelumnya, termasuk `enable_thinking=false`; penempatan RAG generasi A/B
tidak diubah.

Perbaikan tidak mengoreksi verdict model yang salah secara semantik.
Klaim positive yang lolos struktur tetapi tidak didukung bukti tetap
disimpan sebagai positive dan diberi warning untuk evaluasi. Warning rekap
trial juga tidak otomatis diganti menjadi verdict lain.

## Versi dan preservasi

- Protokol aktif dinaikkan menjadi **`qwen38-api-sqli-v2-pilot`**. Prompt
  analisis dan source adapter P2 ikut dipin pada snapshot runtime.
- Plan baru: `development/qwen_api_p3_v2_pilot_plan.template.json`, dengan
  experiment ID `qwen38-api-p3-v2-pilot-20261022`. Plan lama tidak diubah.
- Sebelum perubahan, 1.158 file dipin. Sesudah perubahan, **1.155 file tetap
  sama**; tepat tiga file runtime/config yang direncanakan berubah.
- **34 file source sebelum perubahan diarsipkan dan hash-nya cocok.** Arsip
  lokal berada di `results/raw/development/p3-repair-20261022-v2/legacy-source/`.
- Hasil formal lokal, seluruh artefak P2, korpus, indeks dan PDF dalam
  `sources/` tetap utuh. Receipt eksekusi lama tidak ditulis ulang.
- Snapshot/protocol lama tidak boleh diganti untuk meloloskan resume.
  Runtime baru menolak resume terhadap snapshot berbeda; gunakan experiment
  ID baru untuk jalur v2. Arsip sumber lama tersedia untuk reproduksi v1.

## Hasil pengujian

**192 tes regresi lulus**, nol failure/error/skip, termasuk 13 tes integrasi
P3 baru. Tes mencakup gate sebelum API, penolakan parser, penghentian loop
adaptif, preservasi verdict salah, kesamaan profil aktual dan penolakan drift.

Selain regresi, replay memakai 17 respons P2 tersimpan, bukan inferensi baru.
Setiap respons diproses melalui callback A dan B; keputusan dan payload
checkpoint cocok pada seluruh 34 replay. Seluruh 18 payload P2 juga
direproduksi dari bukti aslinya. Pengujian A/B pada 36 fixture eligible
memastikan pesan analisisnya identik dengan builder P2.

Audit memakai pemblokiran socket: **nol request API nyata, nol request DVWA
dan nol upaya koneksi terdeteksi**. Tidak ada credential yang dimuat oleh
audit. Pemeriksaan AST terpisah mencocokkan lima fungsi generasi/retrieval
dengan arsip sebelum perubahan; seluruhnya sama.

Evidence terstruktur ada di
[audit perbaikan P3](evidence/p3-repair-audit-2026-10-22.json). Log tes dan
inventory lokal berada di `results/raw/development/p3-repair-audit-20261022-v2/`.

Reproduksi audit dengan direktori keluaran baru:

```powershell
.\.venv\Scripts\python.exe maintenance/audit_p3_repairs.py `
  --output-dir results/raw/development/p3-repair-audit-recheck
```

## Pekerjaan berikutnya

Perbaikan offline selesai; P3 secara keseluruhan belum selesai. Urutan
berikutnya adalah smoke generasi terisolasi, kontrol executor aktual S1-S12,
penetapan budget khusus pilot, lalu 33 run applicable beserta review
independen dan pengukuran durasi/kuota.

Draft v2 tetap mencakup A=12, B=12 dan C=9, dengan tiga slot C/Impossible
excluded: 330 kandidat dan 990 konfirmasi logis. Worst-case adalah 960
request API pada attempt terencana. Ceiling umum 5.760 pada config bukan
budget spending pilot yang otomatis disetujui. Tidak ada eksekusi live dari
pekerjaan perbaikan ini, dan tidak ada formal API yang dijalankan.
