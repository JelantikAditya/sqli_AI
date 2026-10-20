# Pilot perbaikan analisis respons v1

Tanggal: 19 Oktober 2026.
Status: prototipe dan pilot selesai; belum diintegrasikan ke runner formal.
Model tetap Qwen 2.5 7B. Tidak ada pergantian ke Bonsai.

## Tujuan dan batas perubahan

Tahap pertama rencana perbaikan memperjelas penyajian bukti HTTP kepada model.
Implementasi berada di development/, terpisah dari dvwa/, schemas/ dan tests/
yang dipin eksperimen formal. Seluruh 959 hash sumber F02 tetap sama sebelum
dan sesudah pilot. R1/R2/R3 serta penilaian VAL-01 tidak diubah atau diulang.

Perubahan pada prototipe:

1. Error-based memakai pasangan baseline/candidate. Boolean memakai pasangan
   true_condition/false_condition. Time-based memakai candidate/no_delay_control.
2. Baseline benign tidak dimasukkan sebagai pembanding keberhasilan boolean/time;
   status baseline_valid tetap tersedia sebagai konteks validitas runtime.
3. Delta waktu dihitung dari angka pengukuran dengan Decimal dan diberikan
   bersama kedua durasi. Tidak ada label expected, positif/negatif evaluator,
   ground truth atau hasil executor yang diberikan kepada model.
4. Urutan properti JSON meminta asesmen trial sebelum keputusan akhir.
5. Output mentah disimpan; parser dan audit memakai normalizer frozen yang sama.
   Klaim salah tetap dicatat, termasuk warning konsistensi.

Ini satu paket perubahan penyajian tahap analisis. Pilot belum mengisolasi
dampak setiap perubahan secara individual. Retrieval analisis tetap nonaktif
pada kedua profil, sehingga pilot ini tidak mengukur manfaat RAG.

## Desain pilot yang dibekukan sebelum inferensi

- Sepuluh kasus sintetis baru, tidak menyalin respons U01 atau dataset formal.
- Tiga kasus positif, tiga negatif, mixed 1/3, mixed 2/3, dua trial positif
  dengan trial ketiga hilang, dan satu kasus baseline invalid.
- Dua profil: frozen-v8 dan measured-pairs-v1.
- Model qwen2.5:7b, temperature=0, seed=42, num_ctx=4096, num_predict=768.
- Satu pass pada satu seed. Profil pertama diselang-seling antar kasus.
- Label evaluator berada dalam berkas terpisah dan tidak masuk request model.
- 18 inferensi model; kasus baseline invalid diblokir pada kedua profil.
- Tidak ada retry otomatis, inferensi paralel, atau request ke DVWA.

SHA-256 manifest sebelum inferensi:
`75b005a98250f636b91078927bce596b959e96c7991fb80e6196d82d0d0196aa`.

Lokasi artefak:
`results/raw/development/response-analysis-v1-20261019/`.

Direktori memuat inputs.json, evaluation.private.json, prepared-requests.json,
manifest.json, runtime.json, replay.jsonl, summary.json dan trial-audit.private.json.
Prompt, schema, angka pengukuran, label evaluator dan source dibekukan sebelum
inferensi. Identitas model aktual dicatat pada runtime.json.

Salinan ringkasan terstruktur yang dipublikasikan tersedia dalam
[arsip hasil pilot](../results/processed/response-analysis-dev-v1-20261019/README.md).
Arsip menyertakan manifest, identitas model, ringkasan audit trial dan provenance
SHA-256. Input, request, output mentah dan berkas private tetap di arsip lokal.

## Hasil

| Ukuran pada pilot | Frozen v8 | Prototipe v1 |
| --- | ---: | ---: |
| Keputusan akhir cocok, kasus runtime valid | 6/9 | 6/9 |
| Keputusan/skip cocok, termasuk baseline invalid | 7/10 | 7/10 |
| Asesmen trial cocok dengan indikator | 15/26 | 26/26 |
| Klaim positif pada tiga fixture negatif | 1 | 0 |
| Abstention pada enam fixture biner | 2 | 0 |
| Salah menyatakan negative pada tiga fixture positif | 0 | 0 |
| Analysis error | 0 | 0 |
| Warning decision_reason_code_mismatch, per record | 0 | 6 |
| Warning model_claim_trial_assessment_mismatch, per record | 2 | 3 |
| Warning trial_assessment_evidence_mismatch, per record | 5 | 0 |

Klaim positif pada fixture negatif adalah kesalahan klasifikasi bukti sintetis,
bukan FP pada unit scenario-condition-replicate yang digunakan FPR formal.
Jumlah trial 26 berasal dari delapan kasus lengkap dan satu kasus dua trial.
Kasus baseline invalid tidak dimasukkan ke penilaian trial maupun penyebut
sembilan kasus runtime-valid.

### Hasil per kasus

| Kasus | Bukti sintetis | Expected evaluator | Frozen v8 | Prototipe v1 |
| --- | --- | --- | --- | --- |
| 001 | Error, diagnostik baru 3/3 | positive | positive | positive |
| 002 | Error, HTTP 500 tanpa diagnostik SQL | negative | negative | negative |
| 003 | Boolean, pasangan exists/missing 3/3 | positive | positive | positive |
| 004 | Boolean, kedua respons missing 3/3 | negative | positive | negative |
| 005 | Time, matched delay memenuhi indikator 3/3 | positive | inconclusive | positive |
| 006 | Time, delta kecil/negatif pada tiga trial | negative | inconclusive | negative |
| 007 | Boolean, mixed 1/3 | inconclusive | inconclusive | negative |
| 008 | Time, mixed 2/3 | inconclusive | inconclusive | positive |
| 009 | Error, dua trial positif dan trial ketiga hilang | inconclusive | inconclusive | positive |
| 010 | Baseline invalid | Tidak memanggil model | Diblokir | Diblokir |

Semua output yang dipanggil lolos parsing/schema dan selesai dengan done_reason
stop. Tidak ada kegagalan yang dihapus atau diganti dengan expected evaluator.
Dua puluh record dapat dinormalisasi ulang secara identik dari evidence,
output model dan provenance yang disimpan.

## Temuan yang membaik dan regresi

Penyajian baru membantu model menilai setiap pasangan observasi: seluruh 26
asesmen trial sesuai indikator. Pada frozen v8, hanya 15 asesmen trial cocok.
Prototipe mengenali keenam kasus positif/negatif sederhana dengan tepat.

Namun, keputusan akhir pada tiga kasus mixed/incomplete justru salah. Pada
kasus 007, model memberi asesmen negative/positive/negative dan alasan yang
menyatakan inconclusive, tetapi properti decision berisi negative. Pada kasus
008, asesmen positive/negative/positive diringkas menjadi positive. Pada kasus
009, dua trial positif tanpa trial ketiga juga diringkas menjadi positive.

Enam record prototipe mempunyai reason_code yang tidak sesuai dengan decision.
Kode insufficient_evidence muncul pada beberapa keputusan positive/negative.
Prototipe masih memakai petunjuk reason_code yang bersifat umum, sedangkan
prompt frozen menyebut pemetaan kode literal secara eksplisit. Ini celah
kontrak/prompt yang perlu ditangani pada revisi pengembangan berikutnya.

Hasil ini mendukung diagnosis yang lebih sempit: pembacaan pasangan bukti
membaik pada pilot, tetapi penggabungan trial menjadi verdict dan pemilihan
reason_code masih tidak konsisten. Tidak ada peningkatan ketepatan keputusan
akhir secara keseluruhan pada sembilan kasus valid. Akurasi verdict saja juga
dapat menyembunyikan asesmen trial yang salah pada profil lama.

## Runtime

Wall time pilot sekitar 609,11 detik atau 10 menit 9 detik, termasuk kedua
profil. Total waktu pemanggilan profil frozen sekitar 326,32 detik, dengan
median 37,21 detik per kasus valid. Prototipe sekitar 282,13 detik, median
30,91 detik per kasus valid. Ini pengamatan pada satu pass, bukan benchmark
kecepatan yang sudah direplikasi atau estimasi durasi eksperimen formal baru.

## Keputusan tahap pertama dan langkah berikutnya

Prototipe v1 belum dipromosikan ke pipeline formal. Hasil pilot dipertahankan
sebagai bukti pengembangan, termasuk regresinya. FPR/PSR formal tidak dihitung
ulang; FPR formal tetap undefined dan angka hipotetis 66,67% tidak diterapkan.

Sebelum tahap retrieval analisis, prioritaskan kontrak verdict akhir:

1. Nyatakan pemetaan jumlah trial positif dan kelengkapan trial sebagai tabel
   keputusan yang eksplisit; pemetaan reason_code juga perlu disebut literal.
2. Versikan revisi berikutnya dan simpan v1 beserta output aslinya. Kasus yang
   sudah dibuka hanya boleh dipakai sebagai regresi/pengembangan.
3. Gunakan set validasi baru untuk mengevaluasi revisi, dengan kasus negatif,
   positif, mixed dan incomplete. Jangan menyetel prompt berulang sampai
   angka pada pilot yang sama terlihat sempurna.
4. Jika ingin menambahkan agregator deterministik dari asesmen trial model,
   pisahkan keputusan agregator dari klaim model mentah dan nyatakan perubahan
   arsitektur/metriknya dalam protokol baru. Itu belum diterapkan di pilot ini.
5. Setelah kontrak analisis layak, lanjutkan evaluasi retrieval di analisis B
   dan kebijakan kandidat sebagai tahap yang terpisah.

Pilot sintetis kecil dan satu seed tidak membuktikan generalisasi, penurunan
FPR formal, peningkatan PSR, atau keunggulan RAG. Kode pengembangan tersedia
di [panduan development](../development/README.md).
