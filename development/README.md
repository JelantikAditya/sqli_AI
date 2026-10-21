# Pengembangan analisis respons setelah eksperimen formal

Folder ini berisi prototipe terpisah dari kode eksperimen frozen. Model tetap
Qwen 2.5 7B. Tidak ada perubahan pada hasil formal R1/R2/R3 atau anotasi VAL-01.

## Prototipe v1

`analyze_response_v1.py` menyajikan pasangan observasi sesuai teknik, menghapus
baseline benign dari pembandingan boolean/time, dan menambahkan delta waktu
yang dihitung dari angka pengukuran. Pengurangan memakai Decimal agar tidak
membulatkan nilai di sekitar ambang sebelum model membandingkannya. Tidak ada
label evaluator, hasil yang diharapkan, maupun keputusan executor di prompt.

JSON schema meminta trial_assessments lebih dahulu sebelum keputusan akhir.
Ini mengubah penyajian bukti dan urutan keluaran sebagai satu prototipe tahap
analisis; belum mengisolasi dampak masing-masing perubahan secara individual.

Klaim model tetap disimpan apa adanya. Parser/audit memakai normalizer frozen,
termasuk warning bila keputusan atau referensi bertentangan dengan bukti. RAG
analisis dinonaktifkan pada kedua profil untuk tahap pertama ini.

## Pilot kecil yang ditetapkan sebelum inferensi

`response_analysis_pilot.py` membuat sepuluh kasus sintetis baru: tiga positif,
tiga negatif, mixed 1/3, mixed 2/3, dua trial positif dengan trial ketiga hilang,
serta baseline invalid. Label evaluator disimpan dalam berkas private terpisah
dari input model. Kasus ini adalah pilot pengembangan, bukan holdout independen,
anotasi manusia atau FPR/PSR formal.

```powershell
.\.venv\Scripts\python.exe development/response_analysis_pilot.py `
  --output-dir results/raw/development/response-analysis-v1-20261019

.\.venv\Scripts\python.exe development/response_analysis_pilot.py `
  --output-dir results/raw/development/response-analysis-v1-20261019 `
  --call-model
```

Persiapan menyimpan hash input, label, request dan source sebelum inferensi.
Eksekusi membandingkan prompt frozen v8 dengan prototipe, pada model, seed,
context dan budget output yang sama. Kasus baseline invalid dihentikan pada
kedua profil tanpa inferensi; terdapat 18 panggilan model yang direncanakan. Urutan profil
pertama diselang-seling. Tidak ada retry otomatis atau request DVWA.

Keluaran meliputi manifest, input, label evaluator, request yang disiapkan,
digest model, output mentah, ledger, warning dan ringkasan. Ketepatan keputusan,
kesalahan pada kasus negatif/positif, abstention, analysis error dan runtime
dicatat terpisah. Satu seed dan kasus kecil ini tidak cukup untuk mengklaim
generalisasi atau penurunan FPR formal.

Hasil pilot yang sudah dibuka hanya menjadi bukti pengembangan. Evaluasi holdout
baru dan pilot A/B live tetap merupakan tahap berikutnya sebelum perubahan
metode dipakai pada eksperimen formal baru.

## Hasil pilot pertama

Pilot selesai: asesmen trial meningkat dari 15/26 menjadi 26/26, tetapi ketepatan
keputusan akhir tetap 6/9 pada kasus valid untuk kedua profil. Prototipe benar
pada enam kasus positif/negatif sederhana, tetapi salah pada mixed 1/3, mixed
2/3 dan trial yang tidak lengkap. Enam output juga mempunyai reason_code yang
tidak konsisten dengan keputusan. Prototipe belum dipasang ke runner formal.

Laporan rinci dan prioritas revisi kontrak verdict ada di
[hasil pilot v1](../docs/pilot-perbaikan-analisis-v1-2026-10-19.md).
Ringkasan terstruktur, identitas model dan hash sumber tersedia dalam
[arsip hasil pilot](../results/processed/response-analysis-dev-v1-20261019/README.md).

## Revisi kontrak v2

`analyze_response_v2.py` mempertahankan input pasangan pengukuran v1 dan meminta
rekap trial dari model sebelum keputusan akhir. Prompt memuat tabel keputusan
eksplisit serta kode literal untuk setiap teknik. Rekap dan keputusan tetap
berasal dari Qwen; audit tidak mengganti klaim yang salah.

`response_analysis_validation_v2.py` membekukan perbandingan v1/v2 pada 17 kasus
sintetis baru serta regresi v2 pada 10 kasus lama. Ada 41 inferensi yang
direncanakan dan tiga skip runtime invalid. Kasus regresi dipisahkan dari
penyebut validasi baru. Model, digest, seed dan budget sama dengan pilot v1.
Tidak ada retrieval analisis atau request DVWA.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_response_analysis_v2.py -v

.\.venv\Scripts\python.exe development/response_analysis_validation_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019

.\.venv\Scripts\python.exe development/response_analysis_validation_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019 --call-model

.\.venv\Scripts\python.exe development/audit_response_analysis_v2.py `
  --output-dir results/raw/development/response-analysis-v2-20261019 `
  --export-dir results/processed/response-analysis-dev-v2-20261019
```

Gunakan direktori baru saat menyiapkan evaluasi baru. Paket yang sudah dimulai
tidak ditimpa atau diulang otomatis. Audit memeriksa sumber yang dipin,
reproduksi ledger, kesesuaian ringkasan, preservasi klaim, seluruh 959 sumber
formal, dan artefak asli pilot v1. Lihat
[desain dan hasil validasi v2](../docs/validasi-kontrak-analisis-v2-2026-10-19.md).

Evaluasi v2 selesai: 41 inferensi, tiga skip runtime invalid, dan audit
reproduksi 44 record lulus. Pada 16 kasus baru, verdict v1/v2 tepat 10/16 dan
11/16; asesmen trial 33/44 dan 32/44. Mismatch reason_code turun dari 7 ke 0.
Regresi v2 pada kasus lama tepat 7/9, dengan asesmen trial 24/26. Seluruh
25 output v2 mempunyai kode konsisten dengan keputusan, tetapi keputusan
dan bukti belum selalu sesuai. Kriteria yang dibekukan belum tercapai dan v2
belum dipromosikan ke runner formal. Lihat
[arsip terstruktur](../results/processed/response-analysis-dev-v2-20261019/README.md).

## Verifier dan agreement gate v3

`verify_response_v3.py` mengevaluasi pengukuran secara deterministik tanpa
memakai label executor atau evaluator. `combine(record)` mempertahankan seluruh
record Qwen di llm_record, lalu menambahkan verification dan combined. Keputusan
biner hanya diterima jika Qwen dan verifier sepakat. Konflik menjadi
inconclusive; input/runtime invalid menjadi not_evaluable. Penjelasan bahasa
alami Qwen tetap belum dianggap terverifikasi.

`hybrid_validation_v3.py` membekukan 21 kasus baru, dengan 20 inferensi Qwen v2
dan satu skip runtime invalid. Model, prompt dan budget tidak berubah. Replay
27 record lama dihitung tanpa inferensi ulang dan dilaporkan terpisah. Verifier
memakai Decimal, termasuk pada batas 2048,2 - 548,2 = 1500,0 ms; normalizer lama
tetap disimpan dengan hasil binary float aslinya.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_verify_response_v3.py -v

.\.venv\Scripts\python.exe development/hybrid_validation_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019

.\.venv\Scripts\python.exe development/hybrid_validation_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019 --call-model

.\.venv\Scripts\python.exe development/audit_hybrid_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019 `
  --export-dir results/processed/response-analysis-hybrid-v3-20261019
```

Klaim mentah, hasil verifier dan hasil gabungan adalah tiga keluaran berbeda.
Penurunan klaim positif keliru setelah gate harus dilaporkan bersama abstention
dan coverage. Verifier-only pada kasus yang dibangun dari aturan yang sama
merupakan uji kesesuaian implementasi, bukan akurasi independen. Tidak ada
perhitungan ulang metrik formal atau request DVWA pada evaluasi ini. Lihat
[protokol dan hasil v3](../docs/varian-verifikasi-hibrida-v3-2026-10-19.md).

Evaluasi selesai: 16 uji offline lulus, 20 inferensi baru selesai, dan 48 record
hibrida dapat direproduksi. Verdict tepat naik dari Qwen 15/20 ke gabungan
17/20, dengan kontrol positif tetap 4/4. Tiga klaim positif pada fixture
negatif menjadi abstention; coverage negatif turun 7/7 ke 4/7. Seluruh 959
sumber formal dan 16 artefak v1/v2 tetap utuh. Kriteria coverage belum tercapai;
gate tetap shadow/audit sekunder. Lihat
[arsip hasil v3](../results/processed/response-analysis-hybrid-v3-20261019/README.md).

## Pilot RAG pada analisis v4

`analysis_rag_v4.py` memakai system prompt, schema, opsi Qwen dan pengukuran
yang sama pada A/B. A menerima reference_context kosong; B menerima dua
proyeksi entri dari korpus OWASP/PayloadsAllTheThings yang dipin. Semantic
retrieval memakai Nomic lokal, cosine distance dan filter teknik pada Chroma
EphemeralClient. Tidak ada pembukaan atau perubahan indeks formal.

`pilot_analysis_rag_v4.py` membekukan desain sebelum embedding dan membekukan
hasil retrieval serta semua request sebelum inferensi. Ada 19 kasus baru,
36 inferensi berpasangan dan dua skip runtime invalid. Query hanya memakai
teknik, koordinat injection point dan tugas interpretasi umum. Label evaluator
dan hasil pengukuran tidak masuk query; payload contoh tidak masuk referensi.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_analysis_rag_v4.py -v

.\.venv\Scripts\python.exe development/pilot_analysis_rag_v4.py `
  --output-dir results/raw/development/analysis-rag-ab-v4-20261019 --phase prepare

.\.venv\Scripts\python.exe development/pilot_analysis_rag_v4.py `
  --output-dir results/raw/development/analysis-rag-ab-v4-20261019 --phase retrieve

.\.venv\Scripts\python.exe development/pilot_analysis_rag_v4.py `
  --output-dir results/raw/development/analysis-rag-ab-v4-20261019 --phase run

.\.venv\Scripts\python.exe development/audit_analysis_rag_v4.py `
  --output-dir results/raw/development/analysis-rag-ab-v4-20261019 `
  --export-dir results/processed/analysis-rag-ab-v4-20261019
```

Gunakan direktori baru untuk pilot lain; tidak ada overwrite atau retry
otomatis. Keluaran utama adalah klaim mentah Qwen. Verifier v3 tetap audit
sekunder dan tidak dipakai untuk mengklaim penurunan FPR karena RAG. Evaluasi
retrieval (sumber, teknik, ranking) dipisahkan dari keputusan model. Lihat
[metode dan hasil v4](../docs/pilot-rag-analisis-v4-2026-10-19.md).

Pilot v4 selesai: 12 uji offline lulus, 36 inferensi selesai, serta 38 record
mentah dan gate dapat direproduksi. A/B sama-sama tepat 12/18 verdict dan
37/51 trial; tiga klaim positif keliru dari enam fixture negatif tetap ada.
Semua 18 pasangan valid mempunyai verdict dan asesmen trial yang sama. Dua
kriteria peningkatan belum tercapai dan tidak ada promosi ke runner formal.
Seluruh 959 sumber formal serta 26 artefak v1/v2/v3 tetap utuh. Lihat
[arsip terstruktur v4](../results/processed/analysis-rag-ab-v4-20261019/README.md).

## Review teknis kurasi analisis

Review setelah v4 memeriksa sembilan entri/45 field terhadap snapshot sumber
dan delapan kebutuhan verifikasi. Anotasi Codex tersimpan pada
analysis_corpus_review_notes.json; ini bukan gold relevansi independen atau
review manusia. Satu ambiguitas scope boolean dicatat untuk versi baru.

audit_analysis_corpus_review.py memeriksa hash, koordinat sumber, nilai proyeksi,
receipt persetujuan korpus asal dan preservasi 959 sumber formal. Baseline awal
dipertahankan bersama rekaman perbaikan checker. Dua file indeks yang berbeda
dari receipt lama dilaporkan terpisah dari preservasi selama review. Checker
tidak membuka Chroma atau memanggil model/target.

```powershell
python development/audit_analysis_corpus_review.py --phase verify
```

Verifikasi memerlukan arsip lokal yang dikecualikan dari Git. Lihat
[laporan review](../docs/review-rag-analisis-2026-10-19.md) dan
[artefak review](../results/processed/analysis-rag-corpus-review-20261019/README.md).

## Draft korpus analisis v5

Draft 20 Oktober memuat tujuh topik analisis dan provenance per pernyataan.
Sumber terpilih adalah WSTG v4.2 serta tiga halaman PortSwigger. Tidak ada
perubahan pada renderer v4, prompt analisis atau runner formal. Lihat
[draft dan cara review](../docs/korpus-analisis-v5-2026-10-20.md).

prepare_analysis_sources_v5.py merekam snapshot sumber baru dan baseline
preservasi sebelum authoring. Script persiapan menolak menimpa source lock
atau snapshot yang sudah ada. Pemeriksaan draft yang telah disiapkan memakai:

```powershell
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5.py
```

Checker membaca schema, source lock, snapshot dan kontrak lokal tanpa membuka
Chroma, memanggil model atau mengirim probe. Seluruh status researcher_review
masih pending. Audit teknis tidak mengubahnya menjadi persetujuan manusia.

Review berbantuan AI kemudian meminta revisi kecil. Acuan tahap rev1 corpus.rev1.json
memakai schema/checker versi rev1; checker lama tetap dapat mereproduksi audit
draft sebelum revisi. check_analysis_contract_v5_rev1.py memeriksa fungsi
diagnostik frozen dengan stub offline tanpa mengimpor layanan atau client.

```powershell
.\.venv\Scripts\python.exe development/check_analysis_contract_v5_rev1.py
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5_rev1.py
```

Lihat [hasil revisi dan bukti kontrak](../docs/revisi-korpus-analisis-v5-rev1-2026-10-20.md).

## Renderer dan retrieval v5 rev2

Versi aktif untuk persiapan: corpus.rev2.json. Review sebelumnya diteruskan dari
AI; pemeriksaan dan adopsi peneliti belum tercatat. Status pending dipertahankan.

analysis_rag_v5.py menyiapkan request tanpa API chat, memakai whole chunk dan
paired evidence identik pada A/B. prepare_analysis_rag_v5.py mem-pin desain,
kemudian meng-embed korpus/query dengan Nomic lokal dan memeriksa request yang
disimpan. Tahap retrieve hanya dijalankan sekali pada direktori readiness ini.

inspect_analysis_v5_readiness.py memeriksa ulang artefak tersimpan dan preview
sekunder top-3 tanpa embedding/inferensi. Tujuh tes renderer sudah lulus.

```powershell
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5_rev2.py
.\.venv\Scripts\python.exe development/inspect_analysis_v5_readiness.py
```

Top-2 belum mencakup kedua topik teknik pada query utama. Pratinjau top-3
menambah coverage, dengan biaya konteks yang perlu diperiksa sebelum pilot.
Lihat [laporan dan batas kesiapan](../docs/renderer-retrieval-v5-2026-10-20.md).

## Preflight konteks dan kandidat profil v5

preflight_analysis_v5_context.py mencatat rencana sebelum sembilan probe chat
lokal, memakai request renderer yang sama dengan stop tambahan untuk mengakhiri
keluaran pada token pertama. Budget context/output tetap 4096/768. Verdict
tidak dinilai. Kelima tes guard konteks lulus.

verify_analysis_v5_context.py mereproduksi 36 hitungan input dan sembilan
respons runtime tanpa model/jaringan. review_analysis_v5_relevance.py mencatat
penilaian AI yang terpisah dari rubrik awal dan status peneliti manusia.

```powershell
.\.venv\Scripts\python.exe development/verify_analysis_v5_context.py
```

Kandidat profil A/B3 dan pembanding sekunder B2 disimpan bersama bukti konteks.
Kasus baru dan jadwal perlu disiapkan sebelum pilot evaluasi keputusan. Lihat
[hasil preflight](../docs/preflight-konteks-dan-profil-v5-2026-10-20.md).

## Paket persiapan pilot v5 terkunci

analysis_v5_pilot_cases.py menyiapkan 36 kasus eligible dan enam gate cases
sintetis, dengan label AI terpisah yang masih pending review peneliti.
analysis_v5_pilot.py mengunci input, label, 126 request A/B2/B3, jadwal seimbang,
kebijakan error/retry, serta definisi metrik sebelum inferensi. Runner menolak
input invalid sebelum panggilan model, menghitung seluruh token request aktual,
dan mempertahankan keputusan mentah dengan audit semantik terpisah.

Sebanyak 12 tes pilot baru dan 12 tes renderer/konteks lulus. Simulasi client
menguji 108 panggilan valid, 18 skip, error dalam denominator, abstention yang
terpisah, dan interupsi tanpa retry. Ini bukan hasil inferensi Qwen. Paket
serta preservasi 1.144 file telah diverifikasi offline, dengan margin konteks
minimum 1.634 token setelah cadangan output. Evaluasi pilot belum dijalankan.

```powershell
.\.venv\Scripts\python.exe development/analysis_v5_pilot.py
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_analysis*v5*.py -v
```

Snapshot sumber, tokenizer, embedding, dan respons mentah tetap di penyimpanan
lokal yang dikecualikan dari Git. Verifikasi penuh memerlukan arsip lokal itu.
Artefak terkunci dipertahankan byte-exact lewat .gitattributes. Lihat
[protokol pilot](../docs/paket-pilot-analisis-v5-2026-10-20.md) dan
[kasus untuk review](../outputs/analysis-v5-pilot-review/cases.review.md).

## Revisi r2 setelah review paket pilot

Gunakan analysis_v5_pilot_rev2.py untuk verifikasi paket revisi. Runner asli
dan paket asli tetap utuh. R2 mempertahankan byte kasus, label, jadwal,
request dan audit token, serta korpus rev2. Masukan review disimpan persis
seperti diterima tanpa dianggap sebagai adopsi peneliti.

F-01 mempertahankan batas output konservatif tetapi membedakan penolakan
anggaran, runtime length stop, keluaran belum selesai dan kegagalan JSON.
F-02 memperjelas struktur versus warning semantik, menambahkan warning
dukungan citation/outcome, memisahkan reason-code reference accuracy dari
internal consistency, dan menampilkan transisi benar/salah berpasangan A/B3.
Klaim dan asesmen model tidak dikoreksi. Batas cakupan gate dan fixture
dicatat dalam protokol. Inferensi belum dijalankan.

```powershell
.\.venv\Scripts\python.exe development/analysis_v5_pilot_rev2.py
.\.venv\Scripts\python.exe -m unittest discover -s development -p 'test_analysis*v5*.py' -v
```

Lihat [penjelasan r2](../docs/paket-pilot-analisis-v5-r2-2026-10-20.md).

## Hasil eksekusi pilot r2

Peneliti menyetujui penjelasan r2 dan kelanjutan pilot melalui pesan langsung;
receipt terpisah mengikat persetujuan ke artefak terkunci. Sesi model selesai
dengan 108 inferensi, 18 skip invalid, dan nol analysis error. Akurasi mentah
A=23/36 dan B2/B3=24/36. Selisih satu kasus berasal dari pilot-011, yang pada
B2/B3 mempunyai verdict benar disertai trial 2 rekaan. Asesmen trial turun
dari 75/102 ke 74/102, dan klaim positive keliru pada referensi negative tetap
enam pada setiap profil. Hasil tidak dipromosikan ke runner formal.

Audit mereproduksi seluruh respons/skor dan mempertahankan 1.183 hash file
historis. Tiga tes audit simulasi lulus, termasuk penolakan respons atau
ringkasan yang dimodifikasi. Ini terpisah dari 36 tes offline paket r2 yang
telah lulus saat persiapan. Tidak ada retry inferensi atau perubahan label.

```powershell
.\.venv\Scripts\python.exe maintenance/audit_analysis_v5_pilot_rev2.py
.\.venv\Scripts\python.exe -m unittest discover -s maintenance -p 'test_audit_analysis_v5_pilot_rev2.py' -v
```

Lihat [hasil, audit, dan keterbatasan](../docs/hasil-pilot-analisis-v5-r2-2026-10-20.md).

## Jalur pengembangan Qwen API 20 Oktober 2026

`qwen_api_client.py` menyediakan transport satu request tanpa retry, redirect,
atau fallback model. `qwen_api_analysis.py` mengadaptasi prompt analisis A
terkunci untuk diagnosis sintetis, sedangkan `qwen_api_generation.py` menyiapkan
kandidat dan validasi struktur tanpa memaksa angka slot ke nilai payload.
`qwen_api_diagnosis.py` serta `qwen_api_generation_smoke.py` memakai checkpoint
lokal di `results/raw/development/` yang dikecualikan dari Git. Jangan mengirim
ulang attempt yang sudah tercatat atau mencampur konfigurasi output berbeda
sebagai satu hasil formal.

Hasilnya ada pada [diagnosis analisis](../docs/hasil-diagnosis-qwen-api-2026-10-20.md),
[preflight generasi](../docs/hasil-preflight-generasi-qwen-api-2026-10-20.md), dan
[pilot generasi](../docs/hasil-pilot-generasi-qwen-api-2026-10-20.md). Audit replay:
`maintenance/audit_qwen_api_diagnosis.py`,
`maintenance/audit_qwen_api_generation_smoke.py`, dan
`maintenance/audit_qwen_api_generation_s2_context.py`. Semua audit membaca arsip raw
lokal dan tidak memanggil API atau DVWA.

Perbaikan prompt konteks telah menghasilkan satu kandidat S2 Low dengan hasil
`CONSISTENT_POSITIVE` pada tiga konfirmasi DVWA lokal. Ini hanya pilot teknis, bukan
hasil PSR/FPR atau gate formal. Uji prompt khusus S1 dan S3 kini selesai dengan
satu request per skenario. Kandidat keduanya lolos schema dan kebijakan lokal,
kemudian menghasilkan `CONSISTENT_POSITIVE` pada tiga konfirmasi DVWA Low per
kandidat. VAL-01 menilai dua packet pilot `success`; anotasi telah divalidasi dan
diimpor. Sampel ini tetap bukan skor formal PSR/FPR.
Lihat
[hasil uji prompt S1/S3](../docs/hasil-uji-prompt-khusus-s1-s3-2026-10-20.md)
dan checkpoint lokal pada `results/raw/development/`.

Jalankan `qwen_api_generation_s1_s3_context_smoke.py --report` untuk membaca
ringkasan generasi. Skrip hanya membaca checkpoint dan tidak mengulang request.
Log executor tiap skenario tersimpan pada folder run lokal yang sama.

## Adapter Qwen API ke ledger pilot

`run_qwen_api_experiments.py` menyediakan jalur terpisah untuk generasi dan
analisis API pada runner A/B. Ia memakai protokol berstatus pilot, menolak plan
formal, mem-pin source/config untuk resume, dan mencatat checkpoint setiap
request sebelum koneksi. Prompt API mengikuti batas DAST black-box. Belum ada
eksekusi API/DVWA melalui adapter ini.

Panduan, gate eksekusi, estimasi biaya, plan A S1 Low, serta plan B S1 Low
ada di
[runner Qwen API pilot](QWEN_API_PILOT.md).

## Evaluasi analisis API P2

`prepare_qwen_api_p2_eval.py` membekukan 18 request analisis tanpa RAG.
Runner mengirim setiap request paling banyak sekali. Key API diminta lewat
prompt tersembunyi bila belum tersedia pada environment. Jalankan dari root
project:

```powershell
.\.venv\Scripts\python.exe .\development\run_qwen_api_p2_eval.py `
  --execute --skip-ambiguous-and-continue
```

Jika proses terputus setelah request ditandai mulai, hasilnya dicatat sebagai
`ambiguous-no-response` dan tidak dikirim ulang. Timeout tanpa respons HTTP
dicatat sebagai `transport-error` dengan status penyelesaian tidak pasti;
opsi lanjut melewati hasil itu tanpa retry. Pengunci Windows memakai named
mutex agar dua runner tidak memproses batch yang sama bersamaan. Ringkasan JSON
selalu diperbarui di `results/raw/development/qwen38-api-p2-eval-20261021-run-001/evaluation-results.json`;
respons rinci per kasus ada di subfolder `results/`.

Setelah respons lengkap, bandingkan keluaran yang berhasil diparse dengan label
reviewer terkunci:

```powershell
.\.venv\Scripts\python.exe development/assess_qwen_api_p2_results.py
```

Hasilnya disimpan di `evaluation-assessment.json`. Agreement dihitung hanya
pada respons yang berhasil diparse; coverage tetap memakai seluruh 18 kasus.
Assessment P2 ini bukan perhitungan FPR atau PSR formal.

## Menjalankan tes offline dari clone publik

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s development -p 'test_*.py' -v
```

Sebagian suite mengaudit source snapshot dan receipt formal yang sengaja tidak
disimpan di Git. Suite tersebut akan berstatus `skipped` jika data lokal itu
belum dipasang. Ikuti pin dan instruksi pada [candidate sources](../docs/candidate-sources.md);
jangan memasukkan data sumber lokal atau artefak `results/raw/` ke commit publik.
