# Validasi kontrak keputusan analisis respons v2

Tanggal: 19 Oktober 2026.
Status: kontrak v2, 12 uji offline, 41 inferensi dan audit selesai. Konsistensi
reason_code membaik, tetapi kriteria keputusan/trial belum tercapai. V2 belum
dipromosikan ke runner formal.

## Perubahan yang diuji

V2 mempertahankan penyajian pasangan bukti dan delta waktu dari v1. Aturan
teknik, input pengukuran, model Qwen 2.5 7B, seed=42, temperature=0,
num_ctx=4096 dan num_predict=768 sama pada kedua profil. Retrieval analisis
tetap nonaktif. Ini evaluasi pengembangan kontrak keluaran, bukan ablasi RAG.

Setelah trial_assessments, model diminta menghasilkan confirmation_summary
yang berisi nomor trial teramati serta hitungan trial positif dan negatif.
Hitungan ini dihasilkan model, bukan dihitung dari indikator executor lalu
diberikan sebagai jawaban. Prompt memuat tabel keputusan berikut:

| Kelengkapan trial | Jumlah positif | Keputusan |
| --- | ---: | --- |
| Tepat trial 1, 2, 3 | 3 | positive |
| Tepat trial 1, 2, 3 | 0 | negative |
| Tepat trial 1, 2, 3 | 1 atau 2 | inconclusive |
| Selain tepat trial 1, 2, 3 | Berapa pun | inconclusive |

Prompt juga menyebut pemetaan reason_code secara literal:

| Teknik | positive | negative | inconclusive |
| --- | --- | --- | --- |
| Error-based | new_database_diagnostic | no_new_database_diagnostic | insufficient_evidence |
| Boolean-based blind | boolean_difference | no_boolean_difference | insufficient_evidence |
| Time-based blind | matched_delay | no_matched_delay | insufficient_evidence |

Schema meminta rekap model, tetapi tidak memakai conditional schema untuk
memaksa kesesuaian keputusan/kode. Inkonstistensi tetap bisa muncul dan dinilai.
Perubahan prompt, penambahan rekap dan schema merupakan satu paket kontrak v2;
evaluasi ini tidak mengisolasi pengaruh tiap perubahan secara individual.

## Desain evaluasi yang dibekukan sebelum inferensi

- 17 kasus sintetis baru: 16 runtime-valid dan satu baseline invalid.
- Pada setiap teknik terdapat kasus positif 3/3, negatif 0/3, mixed, dan
  incomplete. Mixed meliputi 1/3 dan 2/3; incomplete mencakup satu trial
  negatif serta dua trial positif bernomor 1 dan 3.
- Empat kasus tambahan meliputi delta tepat 1500 ms, delta 1499,99 ms,
  delay besar dengan marker kontrol berbeda, dan diagnostik SQL yang sudah
  ada pada baseline. Seluruhnya memakai bukti sintetis baru.
- Kedua profil dinilai pada 17 kasus yang sama, dengan urutan profil pertama
  diselang-seling. Ada 32 inferensi dan dua skip baseline invalid.
- Sepuluh kasus pilot v1 yang sudah dibuka dipakai sebagai regresi v2 saja:
  sembilan inferensi dan satu skip. Hasil regresi tidak digabungkan ke
  penyebut validasi baru dan tidak disebut holdout baru.
- Total 41 inferensi, 44 record, satu pass dan satu seed. Tidak ada retry
  otomatis, request DVWA, atau penyetelan kontrak setelah inferensi dimulai.
- Label evaluator dan nama diagnostik kasus disimpan di evaluation.private.json,
  terpisah dari input dan request model. Nomor skenario, level, metadata
  kondisi, hasil formal, dan jawaban validator tidak masuk prompt.

Paket lokal: results/raw/development/response-analysis-v2-20261019/.
Input, label evaluator, seluruh request, schema dan source dipin melalui
manifest.json sebelum inferensi. Digest Qwen diwajibkan sama dengan pilot v1.

SHA-256 manifest sebelum inferensi:
`db85faf79fc55d0d47e43b5edbbf84034f7fc32bf5dd5d8bc7c73f04f647704b`.

Kriteria yang ditetapkan: keputusan v2 tepat 16/16 pada validasi baru,
asesmen trial tepat 44/44, nol mismatch kode/rekap, nol analysis error, serta
keputusan tepat 9/9 pada regresi. Pencapaian kriteria ini tidak mempromosikan
v2 secara otomatis ke eksperimen formal.

## Hasil pada kasus baru

Penyebut berikut hanya memakai 16 kasus runtime-valid baru. Baseline invalid
ditahan tanpa inferensi pada kedua profil.

| Ukuran | V1 | V2 |
| --- | ---: | ---: |
| Keputusan akhir sesuai evaluator | 10/16 | 11/16 |
| Asesmen trial sesuai indikator | 33/44 | 32/44 |
| reason_code konsisten dengan decision | 9/16 | 16/16 |
| Mismatch decision/reason_code | 7 | 0 |
| Klaim positif pada 6 fixture negatif | 3 | 3 |
| Klaim negative pada 4 fixture positif | 0 | 0 |
| Abstention pada 10 fixture biner | 0 | 0 |
| Keputusan biner pada 6 fixture inconclusive | 3 | 2 |
| Analysis error | 0 | 0 |
| Median detik per kasus valid | 31,05 | 32,44 |

Konsistensi kode berarti kode cocok dengan keputusan model, bukan bahwa
keputusan atau diagnosis tersebut benar menurut bukti. Pada v2, tiga fixture
negatif tetap diklaim positif dengan kode positif yang konsisten.

Temuan penting:

- new-004: model merekap dua trial positif bernomor 1 dan 3 dengan benar,
  tetapi tetap memberi positive. Audit mendeteksi pertentangan rekap/verdict.
- new-006: pasangan boolean terbalik dibaca sebagai pasangan positif oleh kedua
  profil. V2 juga menyebut arah marker yang berlawanan dengan input di alasannya.
- new-007: trial negatif pada mixed boolean 2/3 dibaca positif, sehingga model
  merangkum bukti sebagai 3/3 positif.
- new-008: verdict inconclusive benar pada kedua profil, tetapi trial negatif
  tunggal dibaca positif. Akurasi verdict menyembunyikan kesalahan per trial.
- new-012: v2 memperbaiki verdict incomplete menjadi inconclusive, tetapi
  salah membaca salah satu dari dua trial positif sebagai negatif.
- new-014: delta eksplisit 1499,99 ms tetap diklaim mencapai ambang 1500 ms.
  Alasan v2 secara literal menyatakan 1499,99 >= 1500.
- new-015: delay 1800 ms dianggap cukup meskipun marker kandidat dan kontrol
  berbeda. Kedua profil mengklaim positive.

Dengan demikian, kenaikan satu keputusan akhir tidak disertai kenaikan
ketepatan trial. Paket kontrak v2 memperbaiki pemilihan kode pada set ini,
tetapi belum memenuhi kriteria keputusan dan pembacaan bukti yang ditetapkan.
Temuan ini tidak membuktikan mekanisme internal penyebab kesalahan model.

## Hasil regresi pada kasus v1 yang sudah dibuka

V2 menghasilkan keputusan tepat 7/9 pada kasus runtime-valid, asesmen trial
tepat 24/26, serta reason_code konsisten pada 9/9 output. Baseline invalid
diblokir tanpa inferensi. Tidak ada analysis error atau referensi tidak dikenal.

- regression-case-005: bukti timing 3/3 positif dibaca negative/positive/negative
  sehingga verdict menjadi inconclusive. Dua trial dengan HTTP 404 dan marker
  missing merupakan pasangan valid sesuai aturan, tetapi dinilai negatif.
- regression-case-009: dua trial error-based positif tanpa trial ketiga tetap
  diberi positive. Rekap dua trial benar, tetapi verdict melanggar tabel.

Ada satu abstention pada enam fixture biner dan satu keputusan biner pada tiga
fixture inconclusive. Klaim positif pada tiga fixture negatif berjumlah nol.
Angka ini merupakan hasil regresi sintetis dan tidak menggantikan hasil formal.

Pada total 25 output v2 yang memanggil model, seluruh kode konsisten dengan
keputusan. Rekap jumlah trial juga cocok dengan asesmen model sendiri, tetapi
dua verdict incomplete tetap bertentangan dengan rekap tersebut. Rekap yang
benar secara internal tidak menjamin asesmen sesuai bukti pengukuran.

## Keputusan setelah evaluasi

Kriteria yang dibekukan tidak tercapai: keputusan baru 11/16, trial baru 32/44,
regresi 7/9, dan dua pertentangan rekap/verdict. Kriteria nol mismatch kode dan
nol analysis error tercapai. Seluruh keluaran disimpan tanpa perbaikan manual
dan tanpa retry atau penyetelan ulang pada dataset yang sama.

V2 dipertahankan sebagai varian pengembangan. Hasil ini mendukung perbaikan
konsistensi reason_code pada set yang diuji, tetapi belum mendukung klaim
perbaikan analisis secara menyeluruh. Klaim positif pada fixture negatif baru
tetap 3/6 dan ketepatan trial turun satu. Tidak ada bukti penurunan FPR formal,
peningkatan PSR, atau manfaat RAG dari evaluasi ini.

Langkah berikutnya perlu menargetkan pembacaan arah marker boolean, validitas
pasangan timing, perbandingan ambang, dan kepatuhan terhadap trial yang hilang.
Jika memakai verifikasi deterministik untuk operasi pasti tersebut, perlakukan
sebagai varian arsitektur baru: simpan klaim LLM dan keputusan gabungan secara
terpisah, serta jelaskan konsekuensinya pada metode dan ablasi FPR. Varian itu
belum diterapkan pada v2. Evaluasi berikutnya memerlukan kasus baru yang
ditetapkan sebelum inferensi; set v2 kini hanya boleh menjadi regresi.

## Preservasi dan audit

Kode baru berada di development/. Model output dan keputusan sistem tetap
berasal dari klaim mentah Qwen. Normalizer frozen hanya menghapus referensi
observasi duplikat sesuai perilaku lama; isi raw_model_content tetap disimpan.

Rekap tambahan model disimpan di provenance agar ledger frozen tetap memakai
enam properti keluaran lama. Audit mencatat rekap yang salah dan pertentangan
rekap/verdict. Tidak ada agregator yang mengganti keputusan model dengan label
executor atau hasil hitungan audit.

Dua belas uji offline lulus, termasuk preservasi klaim salah pada mixed dan
incomplete, reason_code tidak sesuai, rekap model yang salah, schema yang tidak
lengkap, penolakan request yang berubah setelah freeze, dan skip runtime invalid.

Audit akhir lulus: seluruh 44 record dapat direproduksi, 41 klaim mentah tetap
utuh, 44 request cocok dengan freeze, 959 hash sumber formal tetap sama, dan
seluruh delapan artefak asli pilot v1 tetap cocok. Ringkasan dapat dihitung
ulang identik dari ledger. Seluruh 41 inferensi selesai dengan done_reason=stop.

R1/R2/R3, anotasi VAL-01, FPR/PSR dan seluruh sumber formal tetap mengikuti versi
formal pertama. Tidak ada request DVWA atau perhitungan ulang metrik formal.
Salinan ringkasan, manifest, identitas model, hasil audit dan provenance tersedia
di [arsip hasil v2](../results/processed/response-analysis-dev-v2-20261019/README.md).

## Reproduksi

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_response_analysis_v2.py -v

# Gunakan direktori baru jika menyiapkan evaluasi lain.
.\.venv\Scripts\python.exe development/response_analysis_validation_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019

# Paket yang telah dimulai tidak dapat ditimpa atau diulang otomatis.
.\.venv\Scripts\python.exe development/response_analysis_validation_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019 --call-model

.\.venv\Scripts\python.exe development/audit_response_analysis_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019 `
  --export-dir results/processed/response-analysis-dev-v2-20261019
```

Kasus ini merupakan validasi sintetis pengembangan yang ditetapkan sebelum
inferensi. Kasus belum merupakan holdout independen, observasi HTTP DVWA baru,
atau bukti penurunan FPR formal dan peningkatan PSR.
