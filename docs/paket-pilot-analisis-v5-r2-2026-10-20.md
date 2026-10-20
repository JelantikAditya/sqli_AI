# Revisi r2 paket pilot analisis v5

Tanggal: 20 Oktober 2026. Revisi ini menindaklanjuti review yang diteruskan
pengguna. Identitas, independensi reviewer, dan adopsi peneliti belum
ditetapkan oleh lampiran. Status researcher_review tetap pending. Penilaian
label pada lampiran adalah review konsistensi kontrak, bukan gold manusia.

Paket baru berada di results/processed/analysis-v5-pilot-20261020-r2.
Runner baru adalah development/analysis_v5_pilot_rev2.py. Paket asli, source
runner asli, korpus rev2, serta hasil formal R1/R2/R3 tetap dipertahankan.
Paket r2 mempertahankan byte input, 42 label, jadwal, 126 request, dan audit
token dari paket asli. Persiapan r2 tidak menjalankan inferensi atau DVWA.

Lampiran reviewer belum memeriksa source frozen, request aktual, atau
protocol.lock.json. Pemeriksaan lokal r2 melengkapinya secara mekanis:
42 label dan 102 asesmen trial dicocokkan langsung dengan trial_rule_signals
pada kode frozen. Audit request mereproduksi kesamaan A/B2/B3 kecuali
reference_context. Hasil ini tetap tidak menjadi validasi manusia independen.

## F-01: keluaran pada batas anggaran

Kebijakan konservatif dipertahankan, dengan klasifikasi berikut:

| Kondisi runtime atau isi | Perlakuan |
| --- | --- |
| done bukan true | generation-not-finished |
| done=true dan done_reason=length | generation-length-limit |
| done=true dengan reason selain stop/length | unexpected-completion-reason |
| eval_count hilang, non-integer, boolean, atau tidak positif | invalid-generation-token-count |
| done=true, done_reason=stop, eval_count integer >=768 | output-budget-rejection |
| stop dengan 1 sampai 767 token | Lanjut pemeriksaan JSON, schema, dan ID |
| Isi gagal JSON/schema setelah pemeriksaan runtime lolos | invalid-json-or-schema |

Mencapai 768 token tidak membuktikan JSON terpotong. JSON yang lengkap pada
batas tetap mendapat analysis_error karena kebijakan batas anggaran yang
ditetapkan sebelum inferensi. Runtime length stop dilaporkan terpisah dan
tidak disamakan dengan kegagalan parser. Pemeriksaan prompt token mismatch
mendahului kategori ini dan tetap menghentikan sesi.

Seluruh analysis_error tetap masuk penyebut kasus eligible yang dicoba dan
penyebut trial yang tersedia, dengan nol kredit. Respons mentah disimpan
sebelum parsing. Tidak ada retry atau perubahan batas 768 setelah hasil.

## F-02: struktur, makna, dan reason_code

| Kondisi | Perlakuan |
| --- | --- |
| JSON/schema rusak atau field wajib tidak ada | Analysis error |
| ID observasi tidak ada dalam kasus, pada level mana pun | Analysis error |
| ID ada tetapi pasangan kutipan hilang atau tidak relevan dengan trial | Warning semantik; verdict mentah dipertahankan |
| Outcome trial bertentangan dengan fitur yang disediakan | Warning semantik; asesmen dan verdict tidak dikoreksi |
| Trial yang diharapkan hilang atau ganda dalam array yang masih lolos schema | Warning semantik; nol untuk trial terkait, penyebut tetap |
| reason_code cocok dengan decision yang salah | Konsisten secara internal; akurasi terhadap referensi tetap salah |

Schema tetap berlaku lebih dahulu. Seluruh field trial_assessments yang
hilang berbeda dari satu entry trial yang tidak ada dalam array yang valid.
Array yang melanggar minItems/maxItems adalah schema error. Penilaian trial
memberi satu kredit hanya jika ada tepat satu asesmen dengan outcome yang
benar. Kualitas citation merupakan audit pendamping dan tidak diam-diam
mengubah definisi akurasi trial atau keputusan mentah.

Reason-code accuracy membandingkan kode model dengan kode untuk label
referensi dan teknik kasus. Reason-code consistency membandingkan kode
model dengan decision model sendiri dan tekniknya. Keduanya menggunakan
seluruh kasus eligible yang dicoba sebagai penyebut; error mendapat nol.
Kode yang konsisten bukan bukti keputusan benar.

## Laporan pasangan dan batas cakupan

Laporan utama tetap akurasi tiga kelas A versus B3. Tambahan deskriptif
menampilkan salah ke benar, benar ke salah, keduanya benar, dan keduanya
salah, lengkap dengan ID kasus. Analysis error termasuk salah. Pasangan
dengan attempt terinterupsi ditandai; kasus tanpa attempt A/B3 lengkap
ditampilkan terpisah. Sesi tidak lengkap tetap tidak memperoleh kesimpulan
perbandingan penuh. B2 tetap pembanding sekunder.

Batas cakupan 42 kasus yang dipertahankan:

- Runtime invalid di dataset selalu memiliki observasi kosong. Dataset ini
  belum menguji observasi lengkap positif dengan runtime invalid.
- Baseline invalid selalu sejalan dengan diagnostik baseline. Input dengan
  flag valid yang bertentangan dengan diagnostik belum menjadi kasus pilot.
- Gate runner memvalidasi schema dan memakai runtime_status/baseline_valid
  dari upstream. Penetapan flag yang benar menjadi tanggung jawab executor;
  pilot sintetis tidak menguji proses penetapannya secara end to end.
- Empat kasus positif boolean terutama memvariasikan pola HTTP 200/404.
  Cakupan mekanismenya masih terbatas.
- pilot-032 menggabungkan diagnostik kontrol dan delta negatif. Diagnosis
  penyebab perlu membaca asesmen trial, bukan hanya verdict.

Uji offline menggunakan client simulasi dan bukan hasil Qwen. Paket tidak
menjadi holdout independen dan tidak memberikan FPR/PSR formal baru.

## Berkas dan verifikasi

- [Tabel kasus](../outputs/analysis-v5-pilot-review-r2/cases.review.md).
- [Input yang sama](../results/processed/analysis-v5-pilot-20261020-r2/inputs.lock.json).
- [Protokol r2](../results/processed/analysis-v5-pilot-20261020-r2/protocol.lock.json).
- [Review yang diterima](../results/processed/analysis-v5-pilot-20261020-r2/review-feedback.source.txt).
- [Receipt review](../results/processed/analysis-v5-pilot-20261020-r2/review-feedback.lock.json).
- [Audit kontrak frozen](../results/processed/analysis-v5-pilot-20261020-r2/frozen-contract-audit.lock.json).
- [Ringkasan kesiapan](../results/processed/analysis-v5-pilot-20261020-r2/readiness-summary.json).

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p 'test_analysis*v5*.py' -v
.\.venv\Scripts\python.exe development/analysis_v5_pilot_rev2.py
```

Verifikasi memeriksa kembali hash parent, seluruh sumber yang dipin,
preservasi artefak historis, identitas byte enam artefak parent, serta
reproduksi request/token. CLI default hanya memverifikasi offline. Eksekusi
model memerlukan opsi --execute tersendiri pada runner r2.
