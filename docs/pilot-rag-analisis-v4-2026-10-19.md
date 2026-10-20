# Pilot RAG pada analisis respons v4

Tanggal: 19 Oktober 2026.
Status: implementasi, 12 uji offline, 36 inferensi dan audit selesai. Pada
konfigurasi ini, tambahan retrieval belum meningkatkan keputusan atau asesmen
trial dibandingkan A. Varian belum dipromosikan ke runner formal.

## Pertanyaan dan batas eksperimen

Pilot menguji apakah referensi pengetahuan umum yang diretrieve pada tahap
analisis memperbaiki interpretasi bukti SQLi oleh Qwen. Klaim mentah model
menjadi keluaran utama. Verifier/gate v3 tetap audit sekunder dan tidak
mengganti keluaran untuk mengklaim manfaat RAG.

Ini pengembangan metode baru: eksperimen formal pertama memakai RAG pada
generasi/regenerasi payload, sedangkan v4 memakai retrieval pada analisis saja.
Pilot tidak membuat payload baru, tidak mengirim request DVWA, dan tidak
menghasilkan PSR baru. Hasil R1/R2/R3 dan anotasi VAL-01 tetap utuh.

## Desain A/B yang dipin

| Komponen | A | B |
| --- | --- | --- |
| Model | qwen2.5:7b dengan digest yang sama | Sama |
| System prompt | Kontrak v2 + petunjuk referensi umum | Identik |
| Pengukuran | Pasangan bukti dan delta eksplisit | Identik |
| Schema output dan opsi | Seed 42, temperature 0, context 4096, output 768 | Identik |
| reference_context | Kosong | Dua entri hasil semantic retrieval |
| Verifier v3 | Audit sekunder | Aturan yang sama |

System prompt yang sama menjelaskan bahwa referensi umum bukan observasi atau
instruksi. Tabel operasional kandidat tetap berlaku ketika istilah sumber umum
berbeda: bukti lengkap 0/3 dinilai negative; mixed/incomplete dinilai inconclusive.
Schema keluaran tetap meminta asesmen trial, rekap model, verdict dan reason_code.

Perubahan bersama pada pembungkus prompt v4 berlaku pada A dan B. Karena itu,
A v4 tidak boleh dibandingkan langsung dengan akurasi v2/v3 pada dataset lama
untuk menyimpulkan efek retrieval. Perbandingan utama adalah A versus B pada
kasus baru yang sama. Panjang konteks B bertambah; pilot ini tidak mempunyai
kontrol teks plasebo dengan panjang setara untuk mengisolasi pengaruh volume
teks dari isi referensinya.

Referensi yang diproyeksikan memberi konsep SQLi dan perbandingan kontrol
secara umum. Sebagian informasi tersebut sudah ada pada prompt dasar yang
rinci. Proyeksi tidak menambahkan contoh kerja numerik atau tabel konfirmasi
khusus; aturan operasional tersebut berada pada system prompt yang sama.
Hasil pilot mengukur tambahan referensi umum ini dan tidak mewakili semua
desain korpus, query, contoh verifikasi atau model RAG yang mungkin.

## Pengetahuan dan retrieval

Korpus asal tetap knowledge/sqli-entries.json: sembilan entri editorial dari
snapshot OWASP WSTG v4.2 dan PayloadsAllTheThings yang dipin dengan commit,
hash, path dan nomor baris. Korpus baru merupakan proyeksi lengkap tiap entri
atas title, vulnerability_type, functional_semantics, detection_method dan
limitations. Payload contoh, root cause dan mitigation tidak dimasukkan.

Dua frasa nama target pada limitations dianonimkan secara literal: DVWA result
menjadi result for a particular target, serta no DVWA level menjadi no target
configuration. Tidak ada label kasus, hasil pengujian lama atau aturan baru
yang ditambahkan. Korpus asal dan seluruh snapshot sumber tidak diedit.
Proyeksi mewarisi lisensi CC BY-SA 4.0 dan atribusi pada
[NOTICE korpus](../knowledge/NOTICE.md). Metadata beku tetap memuat
researcher_review=pending agar hash tidak berubah. Persetujuan peneliti atas
korpus asal pada 12 dan 17 Oktober tercatat terpisah dalam
[keputusan korpus formal](keputusan-korpus-formal-u07-2026-10-17.md).
Persetujuan tersebut tidak dinyatakan sebagai review manusia independen atas
proyeksi analisis ini. Review teknis per field kemudian tersedia dalam
[review kurasi analisis](review-rag-analisis-2026-10-19.md).

Source_refs mewarisi daftar referensi entri asal, termasuk bagian yang dapat
mendukung field yang tidak ditampilkan pada proyeksi. Integritas koordinat dan
hash tidak berarti setiap kalimat proyeksi telah ditinjau ulang per field.

Embedding memakai nomic-embed-text lokal dengan prefix document/query.
Chroma 1.5.9 digunakan melalui EphemeralClient dengan telemetry nonaktif.
Collection hanya berada di memori dan tidak membuka store formal. Chroma
mendokumentasikan penggunaan client memori dalam
[Chroma Clients](https://docs.trychroma.com/docs/run-chroma/clients), serta
filter metadata pada
[Metadata Filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering).

Query hanya berisi teknik SQLi, koordinat injection point dan tugas umum
interpretasi paired HTTP evidence. Query tidak berisi observasi, marker hasil,
durasi, jumlah trial positif, runtime outcome, nomor skenario, level, label
evaluator, atau klaim model. Terdapat tiga query unik. Perubahan nilai
pengukuran atau baseline_valid tidak mengubah query.

Setiap query menggunakan filter teknik, cosine distance dan top_k=2 dari tiga
entri yang eligible. Tidak ada reranking atau penggantian chunk setelah melihat
hasil inferensi. Vektor dokumen/query, seluruh candidate pool, distance, entri
terpilih dan sumbernya disimpan agar ranking dapat diperiksa tanpa embedding ulang.

| Teknik | Entri terpilih |
| --- | --- |
| Error-based | sqli-error-quote, sqli-error-message |
| Boolean-based blind | sqli-boolean-numeric, sqli-boolean-quoted |
| Time-based blind | sqli-time-conditional, sqli-time-repeated |

Kualitas retrieval dan keputusan dinilai terpisah. Kesesuaian teknik 2/2
merupakan konsekuensi filter metadata, bukan bukti relevansi semantik independen.
Pemeriksaan hash/sumber dan cosine ranking juga tidak membuktikan model memakai
referensi dengan benar. Tidak ada gold relevansi independen pada pilot ini.

## Kasus dan freeze sebelum inferensi

- 19 kasus sintetis baru: tiga positif, enam negatif, sembilan inconclusive,
  serta satu baseline invalid. Ada 51 trial pada 18 kasus valid.
- Tiap teknik mempunyai kasus 3/3, 0/3, mixed 1/3, mixed 2/3, dan incomplete.
- Tiga kasus tambahan adalah delta timing 1499,97 ms di bawah ambang 1500 ms,
  delay dengan marker kontrol tidak cocok, dan pasangan boolean terbalik.
- Tiap kasus diberi pengukuran yang identik pada A/B; urutan kondisi pertama
  diselang-seling. Terdapat 36 inferensi dan dua skip baseline invalid.
- Satu seed dan satu pass, tanpa retry otomatis atau tuning setelah inferensi.
- Label verdict/trial ditetapkan berdasarkan rancangan kasus pada berkas private
  terpisah. Label tidak dihasilkan dari verifier dan tidak masuk query, korpus,
  request Qwen, atau fungsi verifier.
- Koordinat input berasal dari katalog untuk pilot sintetis; ini tidak
  membuktikan generalisasi pada seluruh level atau injection point DVWA.
- Kasus lama tidak diperlakukan sebagai holdout. Kasus baru ini juga merupakan
  validasi pengembangan sintetis dan tidak disebut holdout independen.

Desain dibekukan sebelum embedding. Hasil retrieval dan seluruh request
dibekukan lagi sebelum panggilan Qwen pertama:

- Design manifest SHA-256:
  bd6394f6962fd6865eb21828b3b704c80031ef048e509a17204a0fad002e9fa2.
- Manifest request/retrieval SHA-256:
  8774b4e86d66895980aacd939bbd9c93ab38a555e46a1e21826e1c4b65a7724f.

Kriteria empiris yang dipin: B mempunyai lebih banyak verdict benar dan lebih
sedikit klaim positif pada fixture negatif daripada A, tanpa menurunkan jumlah
kontrol positif terdeteksi, coverage negatif, atau ketepatan trial. Analysis
error harus nol. Kriteria tidak otomatis mempromosikan metode ke runner formal.

Retrieval diprakomputasi sekali untuk tiga query yang tetap. Durasi retrieval
disimpan terpisah pada runtime.json. total_model_seconds pada ringkasan adalah
durasi langkah inferensi, parsing dan audit sekunder, bukan waktu retrieval
setiap kasus atau benchmark kecepatan model yang direplikasi.

## Evaluasi dan interpretasi

Metrik utama dilaporkan dari klaim mentah pada setiap kondisi: verdict benar,
kesalahan positif/negatif, abstention per kelas, coverage, ketepatan trial,
konsistensi reason_code dan runtime. Hasil gate v3 dilaporkan terpisah agar
perubahan akibat abstention tidak diatribusikan kepada retrieval.

Unit utama pilot adalah fixture kandidat, bukan scenario-condition-replicate
formal. Karena itu, hitungan pada fixture negatif tidak disebut FPR formal,
dan tidak ada perhitungan ulang FPR/PSR penelitian. Jika B berkurang klaim
positif keliru dengan mengurangi coverage atau menambah abstention pada kontrol
positif, keterbatasan itu wajib dilaporkan.

## Hasil utama dari klaim mentah

Penyebut di bawah hanya mencakup 18 kasus runtime-valid baru per kondisi.
Baseline invalid dihentikan tanpa inferensi pada kedua kondisi.

| Ukuran | A tanpa retrieval | B dengan retrieval |
| --- | ---: | ---: |
| Verdict sesuai evaluator | 12/18 | 12/18 |
| Asesmen trial sesuai indikator | 37/51 | 37/51 |
| Reason_code konsisten dengan decision | 18/18 | 18/18 |
| Fixture positif terdeteksi | 2/3 | 2/3 |
| Abstention pada fixture positif | 1/3 | 1/3 |
| Klaim negative pada fixture positif | 0/3 | 0/3 |
| Fixture negatif diberi negative | 3/6 | 3/6 |
| Klaim positive pada fixture negatif | 3/6 | 3/6 |
| Coverage biner fixture negatif | 6/6 | 6/6 |
| Keputusan biner pada 9 fixture inconclusive | 2 | 2 |
| Coverage biner seluruh kasus valid | 10/18 | 10/18 |
| Analysis error | 0 | 0 |

Seluruh 18 pasangan valid mempunyai verdict dan trial_assessments yang sama.
Tidak ada pasangan A salah/B benar atau A benar/B salah. Kriteria peningkatan
verdict dan pengurangan klaim positif keliru tidak tercapai; kriteria tidak
menurunkan kontrol positif, coverage negatif dan ketepatan trial terpenuhi
sebagai hasil yang sama. Tidak ada penyetelan ulang setelah hasil dibuka.

Kesalahan verdict yang sama pada A/B:

- rag-004: mixed error-based 2/3 dibaca sebagai nol trial positif dan diputuskan
  negative, meskipun dua kandidat mengandung diagnostik baru.
- rag-005: dua trial error-based positif tanpa trial ketiga tetap diputuskan
  positive. Ini pelanggaran kelengkapan walaupun asesmen dua trial benar.
- rag-011: timing 3/3 positif menjadi inconclusive; dua pasangan valid dengan
  HTTP 404 dan marker missing dinilai negative.
- rag-016: delta 1499,97 ms diklaim mencapai ambang 1500 ms.
- rag-017: delay besar diterima walaupun marker kandidat dan kontrol berbeda.
- rag-018: pasangan boolean terbalik dinilai positive.

Pada rag-015, verdict incomplete yang benar masih menyertai asesmen trial
yang keliru: trial positif pertama dibaca negative. Ini alasan tambahan
untuk mempertahankan metrik trial terpisah dari akurasi verdict.

Konsistensi reason_code tetap terjaga pada set ini. Namun, kode yang sesuai
decision tidak memastikan decision atau pembacaan trial sesuai pengukuran.
Hasil sama pada 18 fixture tidak menetapkan ekuivalensi umum kedua metode,
dan tidak menjelaskan mekanisme internal penggunaan referensi oleh model.

## Retrieval dan runtime dinilai terpisah

Audit sumber, filter teknik dan ranking cosine lulus pada tiga query. Top-k
dapat diperiksa dari vektor tersimpan tanpa panggilan embedding tambahan.
Selisih maksimum cosine hitung ulang terhadap hasil Chroma sekitar
0,000000455, di bawah toleransi float32 0,0001. Tidak ada gold relevansi
semantik independen, sehingga hasil ini tidak dinyatakan sebagai akurasi
retrieval independen.

QA runtime menunjukkan konteks B memang berbeda: prompt_eval_count A berada
pada 698-962 token dan B pada 979-1254 token. Pada kasus pertama A=766 dan
B=1047 token, dengan dua entry ID tercatat pada provenance B. Ini mendukung
pemeriksaan treatment pada request; bukan pengukuran attention atau bukti
model memakai setiap referensi untuk menalar.

Seluruh 36 inferensi selesai dengan done_reason=stop. Waktu langkah inferensi,
parsing dan audit sekunder total sekitar 635,79 detik untuk A dan 654,79 detik
untuk B. Wall time fase inferensi sekitar 1290,63 detik atau 21 menit 31 detik.
Embedding dan retrieval sekali di awal memerlukan sekitar 3,63 detik. Satu
pass ini tidak menjadi benchmark kecepatan yang direplikasi.

## Hasil gate sekunder dan keputusan tahap ini

Pada kedua kondisi, gate memberi verdict tepat 14/18 dan nol klaim positif
pada enam fixture negatif. Tiga klaim positif mentah menjadi inconclusive;
coverage negatif turun dari 6/6 ke 3/6. Satu abstention pada fixture positif
tetap bertahan. Coverage biner seluruh kasus valid turun dari 10/18 ke 5/18.
Kesamaan hasil gate A/B tidak menunjukkan manfaat tambahan retrieval.

Hasil v4 dipertahankan sebagai temuan pengembangan tanpa peningkatan pada
konfigurasi yang diuji. Tidak ada dasar untuk mempromosikan varian ini atau
menulis penurunan FPR formal karena RAG. Korpus kecil, query tetap per teknik,
tumpang tindih pengetahuan dengan prompt dasar, satu seed, kasus sintetis,
serta ketiadaan gold relevansi independen membatasi interpretasi.

Langkah berikutnya adalah evaluasi bukti HTTP baru yang dinilai independen,
dengan kriteria dan metode dibekukan sebelum inferensi. Kegagalan v4 tidak
boleh disembunyikan dengan mengubah chunk/prompt lalu melaporkan ulang set
yang sama sebagai holdout. Korpus atau representasi baru perlu versi baru dan
set evaluasi baru. Klaim mentah tetap keluaran utama untuk ablasi RAG.

## Reproduksi dan preservasi

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_analysis_rag_v4.py -v

# Gunakan direktori baru untuk pilot lain.
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

Kedua fase jaringan hanya mengakses Ollama lokal. Embedding dibuat sekali
untuk sembilan dokumen dan tiga query; tidak ada embedding ulang saat inferensi
atau audit. Source v1/v2/v3, snapshot pengetahuan, 959 sumber formal dan
artefak historis dipin. Tidak ada request/reset DVWA, akses source code target,
perubahan indeks formal, atau pengulangan R1/R2/R3.

Audit akhir lulus: 38 record mentah dan 38 hasil gate direproduksi, seluruh
36 keluaran model tetap utuh, serta 19 pasangan request mempunyai system
prompt, pengukuran, schema dan opsi yang sama. Satu-satunya treatment input
adalah dua referensi pada B. Seluruh 959 sumber formal dan 26 artefak
historis v1/v2/v3 tetap cocok dengan hash yang dipin.

Ringkasan hasil, manifest, runtime, audit, retrieval dan proyeksi korpus ada di
[arsip hasil v4](../results/processed/analysis-rag-ab-v4-20261019/README.md).
