# Review progres T01-T08, 14 Oktober 2026

## Pembaruan setelah penutupan T01

Pada kelanjutan sesi 14 Oktober, **T01 selesai pada kontrak evaluasi dan
keputusan metodologi**. Protokol v5 telah menetapkan konfirmasi 3/3, abstention
run, metodologi lokal/peran LangChain dan rotasi A/B/C. Lihat
[penutupan T01](keputusan-urutan-kondisi-2026-10-14.md).
Perubahan kode pada kelanjutan sesi ini menambahkan chain LangChain serial untuk
generasi dan analisis Qwen serta mengarahkan unit runner S1 A/B ke loop adaptif.
Pilot lokal ledger r3 kini membuktikan jalur tersebut berjalan untuk S1 A/B.
Status ini hanya menutup pembuktian subset pilot, bukan T02-T05 secara penuh.

## Kesimpulan review awal sebelum perubahan T01

Milestone teknis terjauh yang memiliki bukti adalah **T05 pada subset pilot S1 A/B**.
Langkah berikutnya adalah T06, disertai penutupan sisa T01/T03 dan integrasi loop
adaptif T02 ke runner T05. Ini tidak berarti T01 sampai T05 seluruhnya sudah final.
Protokol masih berstatus pilot; eksperimen formal dan metrik final belum tersedia.

## Dasar pemeriksaan

- Workspace lokal pada commit `9c9114c`, 12 Oktober 2026, pukul 19:04:14 WIB.
- Working tree bersih sebelum review. Tidak melakukan fetch remote.
- Memeriksa kode, konfigurasi, dokumentasi, evidence tersanitasi, serta ringkasan
  record log mentah. Aktivitas yang tidak tersimpan di workspace ini tidak dinilai.
- Menjalankan ulang `python -B -m unittest discover -s tests -v` dengan interpreter
  `.venv`: **69 test lulus**, exit code 0. Sebagian memakai mock dan bukan bukti
  bahwa seluruh kombinasi model/target telah dijalankan nyata.
- Hash SHA-256 log validation dan audit generasi A/B pilot T05 cocok dengan evidence.
- Memeriksa log SecLists S1-S9: masing-masing 10 kandidat, 30 decision record,
  dan tidak ditemukan runtime_failure record.
- Tidak menjalankan scan, inferensi model, probe serangan, atau reset database
  pada review ini. Tidak mengubah file `sources/`.

## Pemetaan tugas

| Tugas | Status berdasarkan bukti | Yang masih diperlukan |
| --- | --- | --- |
| T01 | Selesai pada kelanjutan 14 Oktober: kontrak konfirmasi 3/3, abstention run, unit/budget/retry, metodologi lokal/LangChain, review korpus dan urutan formal tercatat pada v5. | Pembuktian implementasi T02-T07 dan freeze T08 tetap gerbang terpisah. |
| T02 | Kriteria alur S1 terpenuhi: LangChain serial, discovery, generasi, executor, analisis, feedback/regenerasi, dan histori tercatat. Pilot A/B r3 pernah menjalankan 10 kandidat per kondisi. Pada pilot ABC terbaru B berhenti di 4 kandidat setelah batas duplikasi habis; hasilnya excluded, tanpa retry lintas attempt. | Perbaiki keragaman generasi yang masih tidak stabil, perluas alur ke teknik/level lain untuk T07, dan lakukan audit manusia atas klaim. |
| T03 | Kriteria kontrol executor terpenuhi pada pilot 14 Oktober: semua S1-S12 berjalan dengan tiga konfirmasi, reset/login/level, Medium select, High helper, token Impossible, kontrol timing payload yang sama dengan SLEEP(0), dan pembedaan error sesi/kandidat. 113 tes offline lulus. | Pelaksanaan seluruh kondisi LLM/SecLists pada matriks terpadu tetap bagian T07; pilot kontrol manual tidak menjadi dataset formal. |
| T04 | Persiapan sumber SecLists dan eksekusinya melalui ledger terpenuhi: commit/file/hash/baris/transformasi terkunci, C S1-S9 menghasilkan 90 kandidat dan 270 konfirmasi valid setelah reset per run. Budget dan aturan 3/3 sama dengan LLM; mixed evidence tetap bukan sukses. | Freeze sumber/seleksi berada di T08. Perbandingan PSR formal menunggu validator dan matriks terpadu. |
| T05 | Runner subset dan lifecycle terbukti: C S1-S9 selesai 9/9; subset S1 A/B/C terbaru menghasilkan A/C lengkap, B excluded untuk budget tidak lengkap, C tetap dijalankan dengan reset baru, dan execute-resume mempertahankan hash ledger tanpa attempt tambahan. Pemeriksaan baseline/role probe menolak data hilang, duplikat, dan lintas attempt. 118 tes offline lulus. | Perbandingan S1 A/B/C budget penuh terbaru belum terpenuhi karena B duplikat. Matriks lengkap dan pilot gangguan proses nyata di tengah-run tetap perlu bukti T07. |
| T06 | Belum memenuhi kriteria. Fondasi analisis/satu keputusan run dan fungsi confusion_class sudah ada di analyze_response.py. | Paket blind, form/prosedur validator independen, serta agregator FPR/PSR lintas replikasi dengan fixture hasil diketahui belum tersedia. |
| T07 | Belum selesai. Ada pilot adaptif S1, pilot runner A/B S1, dan pilot SecLists S1-S9 yang terpisah. | Pilot terpadu seluruh teknik/level, termasuk Impossible, serta baseline deteksi SQLi aktif ZAP. |
| T08 | Belum selesai. Konfigurasi tetap pilot dan validator pending. | Manifest serta freeze kode/model/dependency/prompt/korpus/index/SecLists/protokol setelah semua gate terbukti. |

## Bukti terkuat yang sudah tersedia

### Pilot kontrol T03 dan ledger C T04, 14 Oktober

Lihat [laporan kontrol](t03-t04-controls-2026-10-14.md),
`docs/evidence/t03-executor-controls-live-2026-10-14.json`, dan
`docs/evidence/t04-seclists-ledger-live-2026-10-14.json`.
Kontrol manual S1-S12 seluruhnya runtime valid; C S1-S9 selesai 9/9 run dan
resume no-op. Tiga kandidat timing High C memiliki mixed evidence dan tetap
dicatat tanpa tambahan konfirmasi. FPR/PSR formal belum dihitung.

### Pilot lifecycle T05 S1 A/B/C terbaru

Evidence: `docs/evidence/t05-abc-s1-lifecycle-live-2026-10-14.json`.
Experiment: `t05-s1-abc2-20261014`.
A dan C menyelesaikan 10 kandidat; B hanya 4 lalu excluded untuk incomplete
budget. Seluruh kandidat yang dieksekusi mendapat tepat tiga konfirmasi, dan
C tetap berjalan setelah B berhenti. Execute-resume tidak mengubah hash ledger
atau menambah attempt/reset. Pilot ini membuktikan lifecycle yang jelas, tetapi
belum memenuhi perbandingan budget penuh A/B/C. Duplikasi B tetap masalah
operasional yang harus ditutup sebelum evaluasi formal.

### Pilot T05 A/B S1

Evidence: `docs/evidence/t05-ab-s1-live-pilot-2026-10-12.json`.

- S1 Low, error-based, replikasi 1, seed 42.
- A dan B masing-masing 10 kandidat unik, tiga konfirmasi per kandidat.
- Discovery sama, database di-reset sebelum setiap kondisi.
- A: 10 kandidat dengan 0/3 sinyal diagnostik.
- B: enam kandidat dengan 3/3 sinyal dan empat kandidat dengan 0/3 sinyal.
- Ledger mentah: tujuh event, dua attempt_started dan dua attempt_completed.
- Evidence mencatat resume setelah selesai sebagai no-op. Ledger yang diperiksa
  tetap memuat dua attempt dan tidak memiliki event invalid atau retry.
- Semua 60 decision record A/B masih human_validation=pending.

Hitungan ini adalah sinyal aturan pada pilot. Belum merupakan PSR final, belum
mengukur FPR, dan belum membuktikan pengaruh RAG secara formal. S1 merupakan
skenario positif; FPR membutuhkan kontrol negatif Impossible.

### Celah integrasi adaptif

Pada `dvwa/run_local_experiments.py:555`, jalur LLM memanggil
`generate_candidate_batch.py` untuk membuat seluruh batch, lalu pada baris 602
memanggil `validation_loop.py`. Jalur ini belum memanggil `adaptive_s1_loop.py`
atau `analyze_with_qwen` untuk memakai respons sebagai feedback generasi.

Log T05 yang diperiksa berisi runtime_setup, run_start, payload, decision, dan
run_end. Keputusan berasal dari executor berbasis aturan. Karena itu bukti
T02 adaptif dan bukti T05 budget penuh harus dibedakan: budget penuh T05 belum
telah ditutup untuk subset S1 A/B pada pilot r3. Percobaan r2 juga tersimpan
sebagai histori operasional: A selesai, sedangkan B invalid setelah Qwen
mengulang kandidat hingga batas regenerasi. Perbaikan prompt retry dicatat pada
versi kode r3, dan run r3 terpisah menjaga hash snapshot serta histori tetap jelas.

### Pilot T02/T05 LangChain S1 A/B, 14 Oktober

Evidence: `docs/evidence/t05-ab-s1-langchain-live-pilot-2026-10-14.json`.
Ledger: `results/raw/pilot/t02-s1-lc-r3-20261014/ledger.jsonl`.

- A dan B sama-sama lengkap 10/10 kandidat; masing-masing punya 30 decision
  record, 60 payload observation record, tiga konfirmasi per kandidat, reset
  database HTTP 200, dan 158 HTTP request tercatat.
- Kedua kondisi memakai `langchain-core` 1.6.10 melalui `RunnableSequence`,
  concurrency 1, external tracing mati. Resume ledger setelah selesai berhasil
  tanpa menjalankan ulang probe.
- Satu duplikasi generasi tercatat pada B lalu berhasil diregenerasi pada slot
  yang sama. Ini mengonfirmasi jalur regenerasi tercatat, bukan tambahan
  konfirmasi untuk kandidat sebelumnya.
- Keputusan sistem pada kedua run adalah negatif. Human validation masih
  pending; hasil pilot ini belum dipakai sebagai FPR/PSR formal.

### SecLists

Evidence: `docs/evidence/t04-seclists-pilot-2026-10-12.json`.
Commit sumber: `6ef78e5c253d9a6556f2d6339a7b635bf0a2115e`.
Sembilan skenario positif berjalan: 90 kandidat logis dan 270 decision record.
Pilot tersebut tidak me-reset database dan validasi manusia masih pending.

## Catatan konsistensi

- Review korpus sudah disetujui dalam
  `docs/evidence/review-peneliti-2026-10-12.md` dan konfigurasi machine-readable.
  Pernyataan pending pada beberapa dokumen lama sudah tertinggal.
- `README.md` masih menyebut 51 test; pemeriksaan saat ini menghasilkan 69.
- `docs/review-progress-2026-10-12.md` menggambarkan kondisi sebelum perubahan
  T02-T05 hari itu. Gunakan kode dan evidence terbaru untuk penilaian saat ini.
- Pesan startup interpreter tentang lokasi Python dasar masih muncul meskipun
  suite lulus. Penyebabnya belum ditelusuri; perlu ditutup pada kesiapan runtime T08.
- Baseline/discovery ZAP yang tersedia memakai passive scan; bukan baseline
  deteksi SQLi aktif yang diminta T07.

## Urutan lanjut yang disarankan

1. T01 telah ditutup pada kelanjutan sesi: gunakan keputusan v5 sebagai kontrak implementasi.
2. Tutup keragaman generasi B yang masih tidak stabil; pertahankan batas retry,
   identitas attempt, dan pengecualian incomplete budget secara transparan.
3. Bangun T06: paket blind, form validator, dan agregator yang menjaga klaim
   sistem sebelum review serta memisahkan konfirmasi dari kandidat/replikasi.
4. Jalankan T07, termasuk kontrol Impossible dan baseline SQLi aktif ZAP.
5. Bekukan T08, kemudian jalankan matriks formal 99 condition-run dan anotasi.

Kesimpulan proyek keseluruhan: T01 selesai, kriteria alur S1 T02 tersedia,
kontrol T03 dan persiapan/eksekusi T04 terpenuhi. T05 sudah menangani subset,
budget exclusion, evidence, dan resume; ketidakstabilan generasi B tetap perlu
diperbaiki untuk menghasilkan dataset sebanding. T06, T07, dan T08 belum selesai.
