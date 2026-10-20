# Korpus rev2, renderer dan pemeriksaan retrieval v5

Tanggal: 20 Oktober 2026. Status: persiapan development dan pemeriksaan request
selesai. Belum ada inferensi Qwen, evaluasi keputusan, release pilot atau
perhitungan ulang FPR/PSR.

## Koreksi isi dan atribusi review

Konten terbaru adalah [corpus.rev2.json](../knowledge/analysis-v5/corpus.rev2.json),
dengan struktur tetap 7 chunk/35 field/38 pernyataan: 13 parafrasa sumber dan
25 adaptasi editorial. Dua field marker-stability kini membatasi pekerjaan
model secara mandiri pada marker yang disediakan. Template/normalisasi tetap
menjadi tanggung jawab persiapan bukti bila metode tersebut digunakan.

Review yang diteruskan pengguna adalah **review berbantuan AI**. Belum ada
rekaman pemeriksaan atau adopsi oleh peneliti manusia. Seluruh pernyataan dan
status researcher_review tetap pending. Instruksi pengguna untuk melanjutkan
pekerjaan development tidak diubah menjadi persetujuan ilmiah atas isi korpus.

[ai-review-feedback.json](../results/processed/analysis-v5-renderer-readiness-20261020/ai-review-feedback.json)
merangkum asal review dan mengoreksi atribusi dokumen sebelumnya. Label
researcher-feedback atau verified_by_researcher pada arsip rev1 merupakan
atribusi lama yang sudah dikoreksi oleh catatan ini. Arsip tersebut tetap
disimpan sebagai riwayat, bukan bukti verifikasi/adopsi manusia.
[Keputusan desain rev2](../knowledge/analysis-v5/design-decisions.rev2.json)
juga menyebut asal AI dan adopsi peneliti yang belum tercatat.

## Perilaku renderer

[analysis_rag_v5.py](../development/analysis_rag_v5.py) menyiapkan request dari
kontrak analisis v2, lalu menambahkan pembungkus referensi yang sama pada A/B.
Tidak tersedia fungsi pemanggilan chat pada modul ini.

- Model, system prompt, schema keluaran, seed, temperature, context dan output
  budget sama dalam setiap pasangan A/B.
- measured_evidence muncul sebelum reference_context. Bukti merupakan
  paired_view yang sama pada kedua kondisi, termasuk seluruh trial dan pasangan
  pembanding yang tersedia dalam proyeksi itu.
- Baseline benign pada boolean/time memang tidak termasuk paired_view sesuai
  kontrak sebelumnya. Pembatasan itu berlaku sebelum retrieval pada A dan B;
  penambahan referensi tidak membuang baris pembanding tambahan.
- A mempunyai reference_context kosong. B memakai chunk utuh dengan kelima
  field dan origin per pernyataan. Tidak ada pengambilan satu field secara lepas.
- Metadata review, kontrak prompt, hash feedback dan canary evaluator tidak
  masuk messages. Query tidak bergantung pada observasi, marker, durasi atau
  flag validitas hasil uji.
- Query dan policy disimpan sebelum embedding. Chunk umum conclusion-scope
  eligible untuk tiga teknik; chunk lain difilter sesuai teknik.

Guard byte membatasi referensi pada 8.000 byte dan isi messages pada 18.000
byte. Kelebihan menyebabkan error, tanpa pemotongan bukti atau chunk. Guard
tersebut **bukan bukti jumlah token atau kecukupan context Qwen**. Exact token
count dan truncation runtime perlu diperiksa sebelum pilot chat.

## Pemeriksaan request yang disimpan

Ada sembilan probe bentuk input: complete, missing-trial dan invalid-runtime
untuk masing-masing teknik. Ini fixture pemeriksaan renderer, bukan holdout
atau dataset untuk mengukur akurasi Qwen.

Profil utama menghasilkan 18 request A/B. Profil sekunder top-3 menghasilkan
18 pratinjau request tambahan, tanpa panggilan chat. Semua pasangan lolos
pemeriksaan kontrak dan kesamaan paired evidence setelah serialisasi.
Canary evaluator dan review_excerpt tidak ikut masuk ke model messages.

Buka [pratinjau request](../outputs/analysis-v5-renderer-review/request-preview.md).
Di sana tersedia sembilan file payload API lengkap: A, B top-2 dan B top-3
untuk satu fixture complete per teknik. Periksa messages[0].content,
messages[1].content, format dan options. File berisi payload yang disiapkan;
belum ada klaim bahwa server Qwen menerima atau memprosesnya.

Isi message B terbesar pada probe ini adalah 6.231 byte untuk top-2 dan
7.535 byte untuk top-3. Tidak ada pemotongan pada renderer. Belum ada
pengukuran token, truncation server, prompt_eval_count atau output Qwen.

## Hasil retrieval dengan embedding lokal

Nomic lokal meng-embed tujuh chunk dan 12 query. Ranking memakai cosine pada
Chroma EphemeralClient yang berada di memori, tanpa membuka indeks formal.
Vector, kandidat ranking, distance dan query disimpan untuk audit/replay.

Tiga query adalah query yang dipakai renderer. Sembilan query diagnostik
menanyakan topik tertentu, termasuk scope pada ketiga teknik. Rubrik awal
dibuat Codex sebelum embedding dan masih memerlukan review manusia. Grade
rubrik dan required_topics tidak diberikan ke fungsi embedding/retrieval.

| Query utama | Chunk terpilih top-2, sesuai urutan | Topik inti yang tertinggal |
| --- | --- | --- |
| Error-based | conclusion-scope, sql-diagnostics | baseline-comparison |
| Boolean-based blind | conclusion-scope, boolean-direction | marker-stability |
| Time-based blind | conclusion-scope, timing-control | timing-confounders |

Kedua chunk terpilih tetap berkaitan dengan tugas. Namun, setiap query utama
hanya mencakup satu dari dua topik teknik yang ditentukan rubrik sementara.
Dengan definisi ini, **0/3 query utama mempunyai coverage lengkap pada top-2**.
Ini adalah diagnostik coverage tugas, bukan FPR atau precision retrieval
berdasarkan gold manusia.

Sebaliknya, **9/9 query diagnostik spesifik menemukan topik sasarannya pada
top-2**. Hasil ini menunjukkan perbedaan perilaku pada query umum dan query
topik dalam konfigurasi sekarang; tidak membuktikan generalisasi pada query
baru atau bahwa pengetahuan akan memperbaiki keputusan Qwen.

Evaluasi top-3 sudah dicantumkan sebagai profil sekunder pada design.json
sebelum embedding. Ranking yang sama menunjukkan coverage kedua topik teknik
pada **3/3 query utama** jika tiga chunk diambil. Ini juga mengambil seluruh
tiga chunk eligible per teknik, sehingga bukan bukti retrieval menjadi lebih
selektif. Konteks bertambah panjang.

Pratinjau payload top-3 dibuat setelah hasil ranking dibuka, dari ranking yang
sama tanpa embedding ulang, reranking atau perubahan query. Waktu penyusunan
kode pratinjau tersebut dicatat eksplisit. Profil sekunder belum dipromosikan
menjadi konfigurasi pilot; hasil top-2 awal tetap utuh.

## Artefak, pemeriksaan dan batas kesiapan

- [Ringkasan retrieval](../results/processed/analysis-v5-renderer-readiness-20261020/retrieval-summary.json).
- [Form relevansi](../results/processed/analysis-v5-renderer-readiness-20261020/relevance-review.template.json):
  36 baris query/kandidat dengan grade AI sementara; seluruh human_grade kosong.
- [Integritas request utama](../results/processed/analysis-v5-renderer-readiness-20261020/request-integrity.json)
  dan [sekunder](../results/processed/analysis-v5-renderer-readiness-20261020/secondary-top3-integrity.json).
- [Audit korpus rev2](../results/processed/analysis-v5-renderer-readiness-20261020/audit.final.json):
  seluruh 1.087 file baseline tetap sama, termasuk 959 file inventory formal,
  draft rev1, evidence dan source lock terdahulu.

Tujuh uji renderer lulus untuk kesamaan kontrak/bukti, isolasi metadata,
query tanpa observasi, penolakan referensi/proyeksi yang berubah, validitas
ranking/teknik, guard tanpa pemotongan, dan filter multi-teknik pada Chroma
memori. Uji retrieval dengan vector buatan hanya memeriksa wiring, bukan
kualitas embedding. Hasil retrieval yang dilaporkan di atas memakai Nomic
yang sebenarnya, dicatat terpisah dari uji wiring.

Metadata usage dalam corpus.rev2.json adalah snapshot saat draft ditulis.
Embedding dan hasil retrieval setelahnya dicatat pada artefak readiness;
tidak ada pengubahan hash korpus untuk menuliskan hasil eksperimen.

Pemeriksaan ulang offline atas artefak yang sudah disimpan:

```powershell
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5_rev2.py
.\.venv\Scripts\python.exe development/inspect_analysis_v5_readiness.py
```

Perintah kedua mereproduksi request utama/sekunder dan memeriksa hash tanpa
embedding, jaringan, Qwen chat atau DVWA. Snapshot sumber, vector dan request
lengkap berada di data/raw atau results/raw yang dikecualikan dari Git.

Sebelum pilot chat, pekerjaan yang tersisa adalah penilaian relevansi manusia,
pemilihan profil retrieval dengan alasan dan anggaran konteks, preflight token/
truncation serta verifikasi digest Qwen, dan penetapan kasus evaluasi baru yang
terpisah dari fixture renderer. Status isi korpus masih menunggu pemeriksaan
dan adopsi peneliti; tidak ada peningkatan keputusan model yang sudah terbukti.
