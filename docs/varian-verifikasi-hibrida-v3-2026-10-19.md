# Varian verifikasi deterministik dan keputusan gabungan v3

Tanggal: 19 Oktober 2026.
Status: implementasi, 16 uji offline, 20 inferensi dan audit selesai. Varian
memblokir klaim yang bertentangan dengan bukti dengan menambah abstention.
Kriteria coverage belum tercapai; varian tetap shadow dan belum masuk runner formal.

## Arsitektur dan cakupan

Keluaran disimpan dalam tiga bagian terpisah:

1. llm_record: seluruh record Qwen v2, termasuk keputusan, reason_code, alasan,
   asesmen trial, output mentah, warning dan provenance. Bagian ini disalin
   tanpa mengubah klaim serta diberi SHA-256.
2. verification: penilaian deterministik dari pengukuran HTTP yang sama.
3. combined: keputusan hasil kebijakan kesepakatan biner.

Verifier tidak menerima scenario ID, level DVWA, expected outcome, anotasi
validator, atau label sukses executor. Fungsi verify(document) hanya menerima
kontrak pengukuran. Implementasinya terpisah dari positive_evidence_groups,
confirmation_result dan classify_confirmations pada kode frozen. Kombinasi
tidak memakai rule_signal, confirmed_success, claim_supported atau warning
label milik normalizer lama sebagai jawaban.

Model tetap qwen2.5:7b. Prompt, schema keluaran model, seed=42,
temperature=0, num_ctx=4096 dan num_predict=768 sama dengan v2. Verifier berjalan
setelah inferensi dan hasilnya tidak disisipkan kembali ke prompt. Retrieval
analisis nonaktif. Ini bukan pengujian kontribusi RAG.

## Aturan yang dibekukan

- Error-based: diagnostik SQL pada kandidat harus baru dibandingkan baseline.
  HTTP 500 saja tidak cukup.
- Boolean: true_condition harus memiliki marker exists saja, sedangkan
  false_condition memiliki missing saja. Kedua respons harus memenuhi status
  blind yang valid dan tidak mengandung diagnostik SQL.
- Timing: kandidat dan matched no-delay control harus memiliki marker valid
  yang sama, status blind valid, tanpa diagnostik SQL, serta delta >= ambang.
- Status blind valid adalah HTTP 200, atau HTTP 404 dengan marker missing saja.
- Positive memerlukan tepat trial 1, 2, 3 dan tiga indikator positif. Negative
  memerlukan tepat tiga trial itu dan nol indikator positif. Mixed atau trial
  yang hilang menghasilkan inconclusive.
- Pasangan pengukuran yang tidak lengkap menghasilkan inconclusive. ID atau
  role ambigu, schema invalid, dan runtime invalid menghasilkan not_evaluable.
- Respons lengkap yang gagal indikator, termasuk marker kontrol tidak cocok
  atau status blind tidak valid, dinilai negative untuk teknik tersebut.
  Ini tidak menyatakan aplikasi aman.

Kode versi verifier: measured-evidence-decimal-v3.
Kebijakan gabungan: binary-agreement-else-abstain-v3.

| Qwen | Verifier | Keputusan gabungan |
| --- | --- | --- |
| positive | positive | positive |
| negative | negative | negative |
| Keputusan biner berbeda | Keputusan biner berbeda | inconclusive |
| Salah satu inconclusive | Valid atau inconclusive | inconclusive |
| Model error/referensi tidak valid | Bukti valid | inconclusive |
| Apa pun | Input/runtime invalid | not_evaluable |

Keputusan biner juga mensyaratkan input hash yang cocok dan referensi pembanding
lengkap. Reason_code keputusan gabungan ditetapkan dari verifier atau alasan
abstention; reason_code Qwen tetap tersimpan terpisah. Penjelasan bahasa alami
model tidak dinyatakan telah diverifikasi, walaupun verdict biner diterima.

## Angka desimal pada batas timing

Verifier mengurangkan Decimal(str(candidate_ms)) dan Decimal(str(control_ms)).
Ini mendefinisikan perbandingan berdasarkan representasi desimal pengukuran
yang diberikan. Kebijakan aritmetika diberi versi tersendiri.

Kasus hybrid-016 memakai 2048,2 - 548,2 = 1500,0 ms. Pengurangan binary float
Python menghasilkan 1499,9999999999998. Normalizer frozen tetap memakai
perhitungan lamanya, sehingga sinyal diagnostiknya pada kasus ini dapat berbeda
dari verifier v3. Kedua hasil tetap disimpan. Tidak ada patch terhadap kode
atau hasil formal untuk menyamakan kedua versi.

## Evaluasi sebelum inferensi

- 21 kasus sintetis baru: empat positif, tujuh negatif, sembilan inconclusive,
  serta satu baseline invalid. Ada 56 trial pada 20 kasus valid.
- Setiap teknik mencakup 3/3, 0/3, mixed 1/3, mixed 2/3, dan incomplete.
- Kasus tambahan: ambang desimal tepat, tepat di bawah ambang, kontrol timing
  tidak cocok, diagnostik yang sudah ada, dan status boolean tidak valid.
- Dua puluh inferensi Qwen; satu baseline invalid diblokir. Satu seed, satu
  pass, tanpa retry otomatis atau penyetelan setelah inferensi dimulai.
- Label verdict dan trial ditulis pada evaluation.private.json secara terpisah,
  berdasarkan rancangan kasus. Label tidak dihasilkan verifier, tidak masuk
  request Qwen, dan tidak diberikan kepada fungsi verify/combine.
- Verifier pada fixture yang sengaja dibangun dari aturan yang sama dinilai
  sebagai kesesuaian implementasi terhadap aturan. Hasil sempurna pada fixture
  bukan bukti akurasi independen atau generalisasi.
- Replay 27 record profil v2 yang sudah dibuka dilakukan tanpa inferensi ulang.
  Replay lama dipisahkan dari evaluasi baru.

Manifest dibekukan sebelum inferensi dengan SHA-256:
`0cf2e50e87038128eec2c3c755d9aec05f4f545e0d009bd910181dea1fc83d0d`.
Paket lokal: results/raw/development/response-analysis-hybrid-v3-20261019/.

Kriteria empiris yang ditetapkan adalah empat kontrol positif terdeteksi,
coverage biner tujuh fixture negatif lengkap, keputusan gabungan tepat 20/20,
serta nol analysis error. Pemenuhan kriteria tidak otomatis mempromosikan kode
ke runner formal atau membuktikan keunggulan metode.

## Replay v2 yang sudah dibuka

| Set lama | Verdict Qwen tepat | Verdict gabungan tepat | Coverage biner Qwen | Coverage biner gabungan |
| --- | ---: | ---: | ---: | ---: |
| Kasus v2 runtime-valid | 11/16 | 13/16 | 12/16 | 7/16 |
| Regresi v1 runtime-valid | 7/9 | 8/9 | 6/9 | 5/9 |

Pada enam fixture negatif set v2, klaim positif turun dari tiga menjadi nol,
tetapi ketiganya menjadi inconclusive. Coverage negatif turun dari 6/6 ke 3/6.
Pada regresi v1, satu abstention pada fixture positif tetap bertahan. Verifier
tidak menyelamatkan abstention model menjadi positive.

## Hasil pada kasus baru

Penyebut utama adalah 20 kasus runtime-valid baru. Satu baseline invalid
diblokir tanpa inferensi dan menghasilkan not_evaluable pada verifier/gabungan.

| Ukuran | Qwen v2 mentah | Gabungan v3 |
| --- | ---: | ---: |
| Verdict tepat | 15/20 | 17/20 |
| Kontrol positif terdeteksi | 4/4 | 4/4 |
| Fixture negatif diberi negative dengan benar | 4/7 | 4/7 |
| Klaim positive pada fixture negatif | 3/7 | 0/7 |
| Abstention pada fixture negatif | 0/7 | 3/7 |
| Keputusan biner pada 9 fixture inconclusive | 2 | 0 |
| Coverage biner pada fixture negatif | 7/7 | 4/7 |
| Coverage biner pada 11 fixture positif/negatif | 11/11 | 8/11 |
| Coverage biner pada seluruh kasus valid | 13/20 (65%) | 8/20 (40%) |

Ada lima perbedaan antara keputusan mentah dan gabungan:

- hybrid-005: positive dari dua trial error-based ditahan menjadi inconclusive.
- hybrid-015: negative dari satu trial timing ditahan menjadi inconclusive.
- hybrid-017: positive pada delta 1499,99 ms ditahan menjadi inconclusive.
- hybrid-018: positive pada delay besar dengan marker kontrol tidak cocok
  ditahan menjadi inconclusive.
- hybrid-020: positive pada pasangan boolean dengan HTTP 404/exists yang
  tidak memenuhi status blind valid ditahan menjadi inconclusive.

Dua perbedaan pertama memperbaiki verdict sesuai label incomplete. Tiga
perbedaan berikutnya memblokir klaim positif keliru, tetapi belum menghasilkan
keputusan negatif yang benar. Tidak ada peningkatan jumlah true negative.

Asesmen Qwen sesuai label trial pada 47/56 trial. Verifier sesuai pada 56/56
trial dan 20/20 verdict fixture. Hasil verifier ini merupakan kesesuaian
implementasi terhadap kasus yang dibangun dari aturan, bukan estimasi akurasi
independen. Gate tidak memperbaiki asesmen atau penjelasan asli Qwen.

Seluruh 20 inferensi selesai dengan done_reason=stop dan nol analysis error.
Prompt/model tidak diubah sepanjang evaluasi. Kontrol positif 4/4 serta nol
analysis error memenuhi kriteria. Coverage negatif 4/7 dan verdict 17/20
belum memenuhi target 7/7 dan 20/20 yang dibekukan sebelum inferensi.

## Konsekuensi metrik dan metode

Keputusan utama eksperimen formal pertama tetap klaim sistem frozen. FPR/PSR
R1/R2/R3 serta penilaian VAL-01 tidak dihitung ulang. Varian ini tidak menghasilkan
PSR generasi payload baru atau keputusan validator manusia baru.

Untuk studi baru, metrik mentah Qwen dan gabungan harus dilaporkan terpisah,
bersama kesalahan pada fixture positif/negatif, abstention dan coverage setiap
kelas. Nol klaim positif keliru setelah gate tidak boleh ditulis sebagai FPR
utama 0% jika keputusan negatif menjadi tidak lengkap. Unit fixture kandidat
di sini juga berbeda dari unit scenario-condition-replicate formal.

Jika gate dipakai pada eksperimen A/B, aturan, model dasar dan input harus sama
pada kedua kondisi. Pengaruh gate tidak boleh diatribusikan sebagai manfaat RAG.
Verifier-only dilaporkan sebagai pembanding aturan; keputusannya tidak otomatis
menjadi keputusan gabungan.

Rekomendasi setelah evaluasi adalah mempertahankan gate sebagai audit sekunder
terlebih dahulu. Klaim mentah tetap diperlukan untuk mengukur manfaat RAG pada
penelitian ini. Perlu evaluasi bukti HTTP baru dengan penilaian independen serta
desain A/B yang eksplisit sebelum menjadikan keputusan gabungan sebagai metode
utama baru. Menaikkan coverage atau mengganti konflik menjadi keputusan verifier
memerlukan varian baru; itu tidak dilakukan setelah melihat hasil v3.

## Reproduksi dan preservasi

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_verify_response_v3.py -v

# Gunakan direktori baru untuk evaluasi lain.
.\.venv\Scripts\python.exe development/hybrid_validation_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019

.\.venv\Scripts\python.exe development/hybrid_validation_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019 --call-model

.\.venv\Scripts\python.exe development/audit_hybrid_v3.py `
  --output-dir results/raw/development/response-analysis-hybrid-v3-20261019 `
  --export-dir results/processed/response-analysis-hybrid-v3-20261019
```

Kode baru berada di development/. Sumber formal, delapan artefak pilot v1 dan
delapan artefak evaluasi v2 dipin sebelum eksekusi. Tidak ada request DVWA,
akses source code target, query database, reset database, perubahan frozen
runner, atau inferensi ulang untuk replay lama.

Audit akhir lulus: 21 record mentah baru dapat direproduksi, 27 record lama
identik dengan sumber, dan seluruh 48 record hibrida dapat dihitung ulang.
Klaim mentah dari 20 inferensi baru tetap utuh. Seluruh 959 sumber formal serta
16 artefak v1/v2 tetap sama. Ringkasan metrik cocok dengan perhitungan dari ledger.

QA tambahan pada 27 record lama mengubah sinyal executor, confirmed_success,
claim_supported, warning dan metadata skenario/kondisi di salinan memori.
Hasil verifier dan keputusan gabungan tidak berubah. Sumber asli tidak diubah;
bukti tersimpan dalam metadata-independence-qa.json pada arsip lokal.

Salinan summary, manifest, runtime, audit dan provenance tersedia di
[arsip hasil v3](../results/processed/response-analysis-hybrid-v3-20261019/README.md).
