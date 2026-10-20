# Revisi kecil korpus analisis v5, rev1

Tanggal: 20 Oktober 2026. Status: revisi selesai untuk review ulang; belum
dibekukan untuk pilot. Acuan konten kini adalah
[corpus.rev1.json](../knowledge/analysis-v5/corpus.rev1.json).
[Draft yang direview sebelumnya](../knowledge/analysis-v5/corpus.json),
source lock dan audit sebelumnya tetap disimpan tanpa perubahan.

## Tindak lanjut review peneliti

| Masukan | Perubahan rev1 | Bukti |
| --- | --- | --- |
| R1: peran matcher | supporting_conditions pada sql-diagnostics menyatakan model menggunakan identifier dari executor/adapter, tanpa menjalankan matcher ulang. | execute_candidate, observation_document, paired_view |
| R2: ekstraksi template | Parafrasa WSTG dijelaskan sebagai metode persiapan bila template dipakai. Adaptasi terpisah menegaskan input saat ini hanya marker terstruktur. | supporting_conditions pada marker-stability; design-input-boundary |
| R3: diagnostik baru | Mengikat kebaruan pada selisih identifier, sekaligus menjelaskan gate baseline yang terpisah. | Pemeriksaan fungsi frozen dan contract-semantics.json |
| R4: validated injection point | Menjadi titik input yang sama dalam konteks sesi pengujian tervalidasi; tidak berarti kerentanan sudah terbukti. | evidence_to_compare pada baseline-comparison |
| R5: research-design | Seluruh pemakaian penanda umum diganti ID keputusan yang mempunyai rationale, operational_effect dan rujukan kontrak. | design-decisions.rev1.json |
| R6: sintaks delay | Pernyataan ketergantungan sintaks pada engine dihapus dari teks retrieval analisis. | conclusion_limits pada timing-control |

Satu penyesuaian terkait R1/R2 juga dilakukan pada timing-confounders:
evidence_to_compare sekarang menyebut pasangan waktu dan flag validitas yang
memang tersedia. Teks sebelumnya menyebut transport failures dan runtime notes;
paired_view saat ini tidak mengirim catatan tersebut. Model tidak diminta
menilai telemetry yang tidak diberikan.

Struktur tetap **7 chunk / 35 field / 38 pernyataan**. Distribusi menjadi
**13 source_paraphrase / 25 researcher_adaptation**: satu parafrasa sintaks
delay dihapus dan satu adaptasi batas input ditambahkan pada marker-stability.
Tidak ada contoh sintetis di dalam korpus.

## Semantik diagnostik yang diverifikasi dari implementasi

Ada dua lapisan yang perlu dibedakan:

1. **Gate pengukuran live.** validation_loop.execute_candidate menolak baseline
   yang mengandung marker diagnostik dengan baseline_invalid sebelum kandidat
   disubmit. Status/marker baseline dan sesi juga mempunyai pemeriksaan sendiri.
2. **Aturan indikator.** Pada pengukuran yang lolos gate, kebaruan memakai
   selisih himpunan identifier diagnostik. Executor dan fungsi frozen
   analyze_response.positive_evidence_groups menggunakan arah yang sama.

```python
new_identifiers = set(candidate_diagnostics) - set(baseline_diagnostics)
indicator_present = bool(new_identifiers)
```

Karena itu, contoh baseline A dan kandidat A+B mempunyai anggota baru pada
lapisan operasi himpunan, tetapi baseline seperti itu **ditolak pada alur
live**. Hasil operasi tersebut tidak boleh ditafsirkan sebagai keberhasilan
live atau izin mengabaikan baseline_invalid.

Input Qwen berbentuk array identifier unik, bukan flag boolean. Schema input
mengizinkan mysql_syntax_error, mysql_xpath_error dan mysql_unknown_column.
Pada jalur error live, executor mengirim indikator baru ke callback; adapter
menyalinnya ke diagnostics, sementara baseline yang sudah lolos gate memiliki
array kosong. paired_view meneruskan array yang disediakan. Qwen tidak melihat
HTML mentah atau menjalankan ulang regex.

**Nilai diagnostik di sini adalah hasil preprocessing yang tercatat.** Ini
bukan klaim bahwa Qwen melakukan deteksi error langsung pada respons mentah.
Penilaian enum/marker tetap terbatas pada matcher dan kontrak proyek.

## Keputusan desain yang dapat diperiksa

[design-decisions.rev1.json](../knowledge/analysis-v5/design-decisions.rev1.json)
memuat lima ID:

- design-input-boundary: batas informasi dan operasi yang tersedia bagi model.
- design-evidence-scope: pemisahan indikator, keputusan kandidat dan ekstraksi.
- design-no-unmeasured-causes: penyebab variasi waktu tidak boleh dikarang.
- design-marker-consistency: gunakan pemetaan marker dan pembanding yang sama.
- design-fixed-protocol: ketentuan pengukuran berasal dari kontrak bersama.

Setiap keputusan mempunyai dasar alasan dan efek operasional yang eksplisit,
serta rujukan ke kontrak kode. Path dan hash dokumennya diikat dalam korpus.
Dokumen ini mencatat usulan editorial yang direvisi dari masukan peneliti;
persetujuan terhadap hash rev1 masih pending.

## Verifikasi dan bahan review

[contract-semantics.json](../results/processed/analysis-corpus-v5-rev1-20261020/contract-semantics.json)
mencatat empat pemeriksaan aturan diagnostik, pemeriksaan hasil matcher berupa
array identifier, serta penolakan baseline diagnostik oleh fungsi executor
yang sebenarnya. Definisi fungsi diambil dari AST file kode; client dan
fungsi efek samping diganti stub offline. Tidak ada request ke target, reset
database, inferensi model atau pembukaan indeks.

[Audit rev1](../results/processed/analysis-corpus-v5-rev1-20261020/audit.final.json)
memverifikasi schema, seluruh sembilan rujukan sumber, hash/locator sepuluh
rujukan kontrak, lima keputusan desain, dan preservasi **1.072 file**. Cakupan
ini termasuk 959 file inventory formal serta draft/audit v5 sebelumnya.

Pemeriksaan ulang:

```powershell
.\.venv\Scripts\python.exe development/check_analysis_contract_v5_rev1.py
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5_rev1.py
```

Paket [review-evidence.zip](../outputs/analysis-v5-rev1-review/review-evidence.zip)
menyertakan file kode kontrak lengkap, schema, korpus, keputusan desain,
feedback dan manifest hash. Bagian source-navigation memberi URL, section,
koordinat snapshot dan anchor pendek untuk membantu pembacaan sumber. Paket
ini tidak menyertakan snapshot halaman lengkap. Verifikasi hash snapshot utuh
memerlukan file lokal data/raw yang dirujuk source lock; audit melaporkan
pemeriksaan pada file lokal tersebut.

Kecocokan hash korpus dengan source lock saja tidak membuktikan isi sumber.
Sebaliknya, pemeriksaan lokal hash dan rentang membuktikan identitas byte
terhadap snapshot yang dicatat, tanpa menggantikan penilaian dukungan semantik.
Audit tidak dinyatakan sebagai verifikasi independen yang sudah dilakukan
peneliti.

## Status review dan langkah berikutnya

Masukan peneliti dicatat sebagai
[minor revisions requested](../results/processed/analysis-corpus-v5-rev1-20261020/researcher-feedback.json)
untuk hash draft sebelumnya, beserta bagian yang sudah dan belum diverifikasi.
Catatan tersebut merupakan ringkasan masukan, bukan transkrip verbatim.
Status seluruh 38 pernyataan pada hash rev1 tetap pending untuk review ulang.
[Form rev1](../results/processed/analysis-corpus-v5-rev1-20261020/researcher-review.final.template.json)
mengikat hash revisi yang sekarang.

Sesudah review isi rev1 selesai, langkah berikutnya adalah menyiapkan renderer
dan evaluasi relevansi retrieval untuk kasus baru. Kebijakan query, pemilihan
chunk dan anggaran konteks perlu ditetapkan sebelum inferensi. Dokumen ini
tidak menyatakan korpus sudah frozen atau kinerja Qwen sudah meningkat.
