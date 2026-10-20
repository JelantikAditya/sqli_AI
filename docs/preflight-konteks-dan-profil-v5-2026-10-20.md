# Penilaian relevansi, preflight konteks dan kandidat profil v5

Tanggal: 20 Oktober 2026. Penilaian relevansi AI dan preflight konteks selesai.
Sembilan panggilan Qwen dipakai khusus untuk pemeriksaan konteks, dengan
keluaran dihentikan pada token pertama. Tidak ada verdict yang dievaluasi,
request DVWA, perubahan data formal atau perhitungan ulang FPR/PSR.

## Hasil utama

- Seluruh 36 request blueprint top-2/top-3 dihitung dengan tokenizer resmi
  yang vocabulary, added tokens dan merge-nya cocok dengan model lokal.
- Sembilan probe runtime, yaitu A/B top-2/B top-3 pada tiga fixture complete,
  mempunyai prompt_eval_count persis sama dengan hitungan penuh offline.
- Prompt terbesar berisi **1.684 token**. Context tetap **4.096 token**, dengan
  num_predict tetap **768 token**, sehingga margin minimum adalah
  **4.096 - 1.684 - 768 = 1.644 token**.
- Model lokal mempunyai digest yang sama dengan Qwen pada formal/v4. Tidak
  ada penggantian model atau perubahan prompt untuk memperbaiki verdict.
- Seluruh **1.126 file** baseline tetap sama, termasuk arsip formal dan
  seluruh artefak renderer/retrieval yang mendahului preflight.

## Metode penghitungan dan pemeriksaan runtime

Tokenizer berasal dari Qwen/Qwen2.5-7B-Instruct pada commit
a09a35458c702b33eeacc393d103063234e8bc28. Yang diunduh hanya tokenizer dan
konfigurasinya, bukan bobot model. Pencocokan terhadap metadata GGUF lokal
meliputi 151.643 vocabulary entry, 22 added token dan 151.387 merge entry.
[Tokenizer resmi yang dipin](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/a09a35458c702b33eeacc393d103063234e8bc28/tokenizer.json).

Penghitungan mencakup framing ChatML, satu system message, satu user message
dan prefix assistant pada cabang template model yang dipakai. Cabang tools
atau history tambahan ditolak oleh checker. Payload messages dan schema yang
disimpan dipertahankan; perubahan khusus probe hanya options.stop=["{"].

Nilai num_ctx=4096 dan num_predict=768 tidak diturunkan. Stop tambahan
mengakhiri sampling segera ketika pembuka objek JSON muncul. Semua sembilan
probe menghasilkan eval_count=1 dan done_reason=stop. Karena keluaran sengaja
dipotong sebelum menjadi JSON lengkap, hasilnya tidak diperlakukan sebagai
klaim analisis, kegagalan schema model, atau data akurasi.

Dokumentasi Ollama menyatakan prompt_eval_count sebagai jumlah token prompt.
Pemeriksaan membandingkannya dengan hitungan lengkap, bukan menyimpulkan
ketiadaan truncation hanya dari jumlah token yang masih di bawah batas.
[API chat Ollama](https://docs.ollama.com/api/chat). Parameter stop dan batas
num_predict dijelaskan pada [Modelfile Reference](https://docs.ollama.com/modelfile#valid-parameters-and-values).

| Teknik | A: token prompt | B top-2 | B top-3 | Margin top-3 setelah cadangan 768 |
| --- | ---: | ---: | ---: | ---: |
| Error-based | 768 | 1.252 | 1.509 | 1.819 |
| Boolean-based blind | 838 | 1.297 | 1.591 | 1.737 |
| Time-based blind | 956 | 1.414 | 1.684 | 1.644 |

Angka tersebut sama pada tokenizer offline dan respons API untuk probe
masing-masing. Tidak teramati kehilangan panjang token input pada sembilan
probe ini. Pemeriksaan tidak membuktikan model memperhatikan setiap bagian
prompt, menyelesaikan output analisis penuh, atau bahwa prompt masa depan
yang lebih panjang pasti muat. Audit log server tidak dipakai pada tahap ini;
ini bukan release kesiapan formal U07.

Stop tambahan **tidak ikut digunakan pada pilot analisis**. Pilot memakai
opsi aslinya dan tetap harus mencatat output terpotong, done_reason, analysis
error dan waktu proses ketika menghasilkan jawaban penuh.

## Penilaian relevansi AI sesudah ranking

[relevance-review.ai.json](../results/processed/analysis-v5-context-preflight-20261020/relevance-review.ai.json)
memuat 36 penilaian query/chunk dengan rationale, grade AI dan kolom human_grade
yang tetap null. Ini review editorial Codex setelah ranking terbuka, bukan
gold relevansi independen. Rubrik AI yang ditetapkan sebelum embedding tetap
disimpan pada arsip readiness dan tidak diganti.

Review isi membedakan relevansi dari kelengkapan:

- conclusion-scope yang dipilih pada tiga query utama tetap relevan sebagai
  pembatas klaim. Pada review lanjutan, kontribusinya dinilai complementary,
  bukan irrelevant. Grade lanjutan ini tidak mengganti grade awal.
- sql-diagnostics, boolean-direction dan timing-control menjawab bagian utama
  query masing-masing, tetapi top-2 meninggalkan baseline-comparison,
  marker-stability dan timing-confounders.
- Top-3 menambahkan topik yang tertinggal. Kenaikan coverage terjadi dengan
  mengambil seluruh tiga chunk eligible, bukan bukti bahwa semantic ranking
  memilih isi yang lebih baik dari himpunan kandidat yang lebih besar.
- Pembahasan template tetap dibaca sebagai persiapan upstream; model hanya
  membandingkan marker yang tersedia. Potensi timing noise tetap dibedakan
  dari penyebab spesifik yang benar-benar diukur.

Pemeriksaan atau adopsi peneliti manusia belum tercatat. Tidak ada statement
researcher_review yang diubah dari pending. Instruksi melanjutkan pekerjaan
development tidak dijadikan persetujuan ilmiah atas isi/rubrik.

## Kandidat profil pilot pengembangan

[pilot-profile.candidate.json](../results/processed/analysis-v5-context-preflight-20261020/pilot-profile.candidate.json)
mengikat hash korpus rev2, source lock, digest model, opsi dan bukti konteks.

| Profil | Konteks referensi | Peran pada pengembangan |
| --- | --- | --- |
| A | Kosong | Pembanding tanpa referensi |
| B2 | Dua chunk hasil ranking | Pembanding retrieval top-2 yang tetap dipertahankan |
| B3 | Tiga chunk eligible sesuai ranking | Kandidat utama untuk mencakup seluruh topik teknik |

Pilihan kerja yang disiapkan adalah **A dibanding B3**, dengan **B2 sebagai
pembanding sekunder**. Alasan pemilihannya adalah coverage topik dan kelayakan
konteks pada input yang diperiksa, bukan hasil verdict model. Semua profil
memakai kontrak, schema, pengukuran, seed dan budget yang sama; pembeda hanya
reference_context.

B3 adalah kontrol konteks pengetahuan lengkap yang eligible untuk teknik itu.
Perbandingan A/B3 mengukur penambahan konteks pengetahuan pada rancangan ini.
Hasilnya tidak boleh diatribusikan kepada selektivitas ranking semantik atau
digeneralisasi ke korpus besar tanpa pembanding lain. Profil B2 memungkinkan
diagnosis tambahan tentang pengaruh jumlah referensi/konteks.

Profil ini merupakan kandidat development yang konkret, bukan release formal
atau perubahan metodologi pada dataset R1/R2/R3. Tidak ada pilot pengukuran
keputusan yang dijalankan pada langkah ini.

## Batas data evaluasi dan langkah berikutnya

Fixture renderer dan sembilan probe konteks tidak masuk denominator kinerja
Qwen. Kasus v1 sampai v4 yang sudah dibuka tetap merupakan data pengembangan.
Kasus evaluasi berikutnya harus ditetapkan sebelum inferensi performa, dengan
label evaluator di luar prompt/query/retrieval. Mengganti angka atau hash
saja tidak membuktikan independensi holdout.

Tahap berikutnya adalah menyiapkan kasus baru yang mencakup indikator positif,
negatif, mixed, incomplete dan kontrol tidak sesuai, lalu mem-pin jadwal A/B2/B3
sebelum inferensi. Raw claim dipertahankan; verifier deterministik tetap
lapisan terpisah. Laporkan false positive, false negative, abstention, coverage,
analysis error, runtime dan completion output, tanpa mengubah metrik formal.

## Artefak dan reproduksi

- [Ringkasan runtime](../results/processed/analysis-v5-context-preflight-20261020/runtime-context-summary.json).
- [36 hitungan token offline](../results/processed/analysis-v5-context-preflight-20261020/offline-token-counts.json).
- [Penilaian relevansi AI](../results/processed/analysis-v5-context-preflight-20261020/relevance-review.ai.json).
- [Kandidat profil pilot](../results/processed/analysis-v5-context-preflight-20261020/pilot-profile.candidate.json).

Tokenizer, metadata model, request probe dan respons mentah berada pada
results/raw/development/analysis-v5-context-preflight-20261020, yang dikecualikan
dari Git. Lima tes guard lulus: selisih token runtime ditolak, cadangan output
konfigurasi tetap diperhitungkan, output exhaustion/length stop ditolak, dan
cabang template yang belum diperiksa ditolak.

Verifikasi ulang offline, tanpa panggilan model atau jaringan:

```powershell
.\.venv\Scripts\python.exe development/verify_analysis_v5_context.py
```

Verifikasi ini menghitung ulang 36 request, merekonsiliasi sembilan respons API,
memeriksa tokenizer/digest/probe delta dan seluruh file baseline yang dilindungi.
