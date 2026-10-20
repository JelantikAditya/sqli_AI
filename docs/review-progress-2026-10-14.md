# Review progres T01-T08, 14 Oktober 2026

> Status aktif diperbarui pada 16 Oktober di [rencana penyelesaian](rencana-penyelesaian-2026-10-16.md).
> Bagian review awal di bawah mempertahankan snapshot dan bukti pada tanggal
> masing-masing; gunakan bagian pembaruan U00-U06 untuk perkembangan setelahnya.

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
| T04 | Persiapan sumber SecLists dan eksekusinya melalui ledger terpenuhi: commit/file/hash/baris/transformasi terkunci, C S1-S9 menghasilkan 90 kandidat dan 270 konfirmasi valid setelah reset per run. Budget dan aturan 3/3 sama dengan LLM; mixed evidence tetap bukan sukses. | Freeze sumber/seleksi berada di T08. Perbandingan PSR formal menunggu matriks dan anotasi yang memenuhi syarat. |
| T05 | Runner subset dan lifecycle terbukti: C S1-S9 selesai 9/9; subset S1 A/B/C terbaru menghasilkan A/C lengkap, B excluded untuk budget tidak lengkap, C tetap dijalankan dengan reset baru, dan execute-resume mempertahankan hash ledger tanpa attempt tambahan. Pemeriksaan baseline/role probe menolak data hilang, duplikat, dan lintas attempt. 118 tes offline lulus. | Perbandingan S1 A/B/C budget penuh terbaru belum terpenuhi karena B duplikat. Matriks lengkap dan pilot gangguan proses nyata di tengah-run tetap perlu bukti T07. |
| T06 | Persiapan validasi dan agregasi tersedia: paket blind, form/prosedur, exporter/importer, agregator, serta fixture hasil diketahui sudah dibuat dan diuji offline. VAL-01 dan prosedur pilot dikonfirmasi; review prosedur tiga kandidat selesai. | Anotasi formal belum tersedia. Sampel U06 empat kandidat masih menunggu review; FPR/PSR formal belum dihitung karena data eligible dan anotasi belum lengkap. |
| T07 | Belum selesai. Ada pilot adaptif S1, pilot runner A/B S1, dan pilot SecLists S1-S9 yang terpisah. | Pilot terpadu seluruh teknik/level, termasuk Impossible, serta baseline deteksi SQLi aktif ZAP. |
| T08 | Belum selesai. Konfigurasi tetap pilot. Validator VAL-01 dan prosedur pilot sudah dikonfirmasi, tetapi validasi formal dan gate U06 belum selesai. | Manifest serta freeze kode/model/dependency/prompt/korpus/index/SecLists/protokol setelah semua gate terbukti. |

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

Catatan berikut merekam inspeksi entrypoint sebelum pilot LangChain adaptif
S1 A/B yang dijalankan pada 14 Oktober. Bukti pilot setelahnya di bawah
menunjukkan integrasi LangChain dan feedback adaptif pada subset S1.

Pada snapshot kode yang diperiksa saat itu, `dvwa/run_local_experiments.py:555` memanggil
`generate_candidate_batch.py` untuk membuat seluruh batch, lalu pada baris 602
memanggil `validation_loop.py`. Snapshot tersebut belum memanggil
`adaptive_s1_loop.py` atau `analyze_with_qwen` untuk memakai respons sebagai
feedback generasi.

Log T05 pada snapshot tersebut berisi runtime_setup, run_start, payload,
decision, dan run_end; keputusan berasal dari executor berbasis aturan. Pilot
LangChain S1 A/B pada 14 Oktober menjadi bukti sesudah snapshot itu. Percobaan
r2 tetap tersimpan sebagai histori operasional: A selesai, sedangkan B invalid
setelah Qwen mengulang kandidat hingga batas regenerasi. Perbaikan prompt retry
dicatat pada versi kode r3, dan run r3 terpisah menjaga hash snapshot serta
histori tetap jelas.

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
3. T06 sudah memiliki paket, prosedur, dan agregator. Tinjau sampel U06 dengan
   VAL-01, impor anotasi, lalu audit exclusion dan eligibility agregator.
4. Tutup U06, termasuk stabilitas budget A/B dan coverage baseline SQLi aktif
   ZAP, sebelum memulai freeze T08.
5. Bekukan T08, kemudian jalankan matriks formal 99 condition-run dan anotasi.

Kesimpulan proyek keseluruhan: T01 selesai, kriteria alur S1 T02 tersedia,
kontrol T03 dan persiapan/eksekusi T04 terpenuhi. T05 sudah menangani subset,
budget exclusion, evidence, dan resume; kestabilan generasi B masih menjadi
gate U06. Persiapan T06 selesai, sedangkan anotasi formal dan metrik belum
tersedia. U06/T07 belum lolos gate pilot terpadu dan T08 belum dimulai.

## Pembaruan audit U00/U01 setelah review

U00 memperjelas bahwa integrasi LangChain lokal sudah terbukti pada pilot S1
A/B 14 Oktober. Field `implementation_readiness.local_langchain` tetap
`pending`, karena gerbang formal masih meminta integrasi seluruh teknik dan
level. Ini status gate cakupan penuh, bukan pernyataan bahwa LangChain belum
pernah berjalan. README dan protokol kini memakai penjelasan yang sama.

U01 memeriksa output mentah pada tujuh kandidat B dengan evidence executor
positif 3/3. Input Qwen berisi diagnostik `mysql_syntax_error` untuk ketiga
respons kandidat dan daftar diagnostik kosong untuk ketiga baseline. Qwen
menyebut perbedaan tersebut dengan benar, tetapi memberi keputusan `negative`.
Hash input/output cocok dengan catatan provenance; normalisasi ulang
menghasilkan record yang identik. Pilot awal menunjukkan kesalahan klasifikasi
Qwen, bukan kehilangan evidence atau perubahan pada normalizer.

Replay pengembangan pada tujuh fixture yang ditetapkan sebelum replay
mendapatkan satu kasus benar pada prompt revisi v6. Replay v8 kemudian cocok
pada 5/7 kasus keseluruhan dan 4/6 kasus valid. Mismatch tersisa menunjukkan
kesalahan klasifikasi model; output tetap menyimpan klaim Qwen dan sinyal
executor tidak menggantikannya. Peneliti menyetujui revisi gate U01: kecocokan
fixture tidak menjadi prasyarat kelulusan implementasi. Prompt v8 dibekukan
untuk validasi tertutup satu kali. Ringkasan tersanitasi dan source hash ada di
[evidence replay](evidence/u01-qwen-replay-2026-10-14.json), sementara replay
lengkap tersimpan lokal di `results/raw/u01-replay-v5-20261014/` dan
`results/raw/u01-replay-v6-20261014/`.

| Tugas rancangan | Status terbaru |
| --- | --- |
| U00 | Selesai untuk sinkronisasi status LangChain README/protokol/review. Gate tetap pending sampai pilot seluruh matriks. |
| U01 | Gate implementasi lulus: kontrak output, audit semantik, dan 145 tes penuh. Validasi tertutup satu kali pada 21 fixture cocok 14/21 keseluruhan dan 11/18 runtime-valid; mismatch dicatat sebagai kinerja model, bukan diperbaiki dari set yang telah dibuka. |
| U02 | Selesai pada subset pilot: enam condition-run A/B S1 seed 42/43/44 lengkap 10/10 kandidat unik; nol generation failure/duplikasi. Pilot terpadu lintas matriks menunggu U06. |
| U03 | Implementasi dan smoke wiring A/B S2-S12 selesai pada skala satu kandidat; S1 tercakup dalam pilot budget penuh U02. Budget penuh lintas matriks menunggu U06. |
| U04 | Exporter/importer, tes redaksi excerpt, form, dan prosedur tersedia. Alias `VAL-01` serta kualifikasi/independensi dikonfirmasi peneliti. Tiga anotasi prosedural selesai; satu label awal `success` direvisi menjadi `insufficient_evidence` atas persetujuan VAL-01 tanpa mengubah alasannya. Anotasi formal menunggu data formal. |
| U05 | Agregator FPR/PSR, ekspor JSON/CSV, audit TP/FP/TN/FN, dan fixture hasil diketahui selesai. Pilot SecLists dengan tiga anotasi VAL-01 sengaja ditahan: semua run PSR masih kekurangan anotasi dan tidak ada unit negatif A/B untuk FPR. Belum ada hasil metrik formal. |
| U06 | Berjalan, belum lolos gate selesai: 33 run terpadu dijalankan, 15/33 menyelesaikan 10 kandidat; recovery teruji; preflight prompt per teknik menyelesaikan 5/6 kombinasi A/B S2-S4; B/S3 tetap 6/10. ZAP Medium/High kini menjalankan rule SQLi, tetapi per-koordinat POST belum teratribusi. U07 tertahan oleh budget A/B dan coverage scanner. |
| U07 | Belum dimulai; menunggu evidence U00-U06 dan pemeriksaan freeze. |

### U06: pilot terpadu dan baseline ZAP aktif

Pilot `u06-integrated-pilot-20261014` menjalankan 33 slot applicable: A/B
S1-S12 dan C S1-S9. Lima belas run mencapai 10/10 kandidat; 18 run A/B
incomplete, dengan 124 slot kandidat belum terpenuhi dari 330 slot. Audit
generasi A/B mencatat 65 keluaran duplikat dan 5 kandidat invalid. C
menyelesaikan 9/9 run. Ledger mencatat 206 kandidat valid, 1.551 logical probe,
4.428 HTTP request, 79,1 menit durasi attempt, dan nol invalid runtime. FPR dan
PSR ditahan karena coverage tidak lengkap serta belum ada anotasi VAL-01 pada
data U06.

Uji interupsi proses mencatat `orchestrator_interrupted`, attempt invalid,
attempt baru, reset database, dan `state_reused=false`. Retry 1/10 kandidat
tetap dikecualikan. Resume berikutnya no-op, sehingga kontrol recovery terbukti
tetapi budget retry belum siap.

Prompt generation v11 menambah guidance per probe kind. Generation-only
preflight lokal mencapai 10/10 pada lima dari enam kombinasi A/B S2-S4. B/S3
time-based berhenti di 6/10 karena duplikasi, dan tetap 6/10 saat profil
diperluas menjadi 16. Preflight tidak mengirim request ke DVWA dan tidak
menjadi data eksperimen. Suite offline saat ini lulus 158 tes.

ZAP aktif sudah dibatasi pada SQLi umum 40018 dan MySQL time-based 40019. Low
dan Impossible mengirim request rule, tetapi coordinate coverage yang dapat
diverifikasi belum lengkap. Setelah scan diarahkan ke seluruh context DVWA,
Medium mencatat 32/20 URL-rule dan High 34/18. HAR menyimpan request POST yang
memuat parameter input di kedua koordinat tiap level, tetapi tanpa tag
`X-ZAP-Scan-ID`; itu belum membuktikan bahwa request tersebut berasal dari
active scanner, sebab seed dan spider juga tercatat di HAR. Maka coverage
bertanda tetap 0/2 dan alert kosong belum ditafsirkan sebagai hasil negatif.
Paket blind empat kandidat sudah siap untuk VAL-01 dan belum dianotasi.

U06 masih terbuka. Sebelum U07, stabilkan generation budget A/B dan tutup
coverage ZAP pada POST, session, cookie, lalu ulangi bagian terdampak dengan
experiment ID dan snapshot baru. Detail, hash, durasi, eligibility, dan log
scan tercatat di [laporan U06](u06-pilot-zap-baseline-2026-10-14.md) dan
[evidence U06](evidence/u06-integrated-pilot-2026-10-14.json).

### U02: hasil pilot diagnostik kedua

Ledger `results/raw/pilot/u02-s1-ab-diversity-r2-20261014/ledger.jsonl`
mencatat A/B pada S1, seed 42, satu replikasi. A memakai 10 kandidat unik,
30 decision record, dan 60 observasi payload; semua kandidat mendapat tiga
konfirmasi dan run memenuhi budget. B menghabiskan sepuluh upaya generasi
dalam tiga kesempatan per slot, tetapi semuanya ditolak oleh guard karena
keluar dari teknik error-based. Output contoh yang tercatat memuat
`1' AND SLEEP(5)--`; tidak ada probe kandidat yang dikirim untuk kondisi B.
Ledger mempertahankan B sebagai `run_excluded` dengan
`incomplete_candidate_budget`. Run ini tidak dipakai dalam FPR atau PSR.

Hasil ini menunjukkan guard teknik yang baru mencegah payload di luar cakupan
mencapai DVWA. Prompt technique-scoped belum mengatasi ketidakpatuhan Qwen
saat RAG aktif, sehingga perbaikan U02 belum lolos dan implementasi U03 tidak
boleh dianggap terverifikasi oleh pilot S1 ini. Tidak ada pengulangan run
yang dikecualikan. Ringkasan dan batas interpretasi dicatat di
[rancangan tugas](rancangan-tugas-2026-10-14.md).

Suite lengkap pada interpreter `.venv` proyek lulus **134 tes** setelah
perubahan U02. Python global gagal mengimpor modul yang memerlukan `jsonschema`;
hasil global itu bukan hasil suite resmi.

### U03: smoke loop adaptif lintas skenario

Controller kini memilih schema output berdasarkan `probe_kind`, menghitung
pasangan Boolean sebagai satu kandidat, menurunkan diagnostik dan marker dari
respons lokal, dan memberi feedback terstruktur tanpa melanjutkan konfirmasi.
Runner ledger menerima semua skenario A/B dan menulis kembali payload, decision,
candidate evidence, serta batch sesuai schema eksperimen. Uji sinyal time-based
memakai marker yang cocok dan perbedaan waktu terhadap matched control.

DVWA lokal menjalani 12 smoke satu kandidat: A/RAG-off pada S2-S12 dan
B/RAG-on pada S2. Semua run mendapat tiga konfirmasi dengan sesi/level valid.
Sepuluh analisis pada smoke asli berstatus completed; S5 dan S8 menyimpan
`analysis_error` karena parser lama menolak evidence references duplikat.
Normalizer baru menghapus hanya ID berulang dari representasi terstruktur,
menyimpan teks mentah dan raw hash, serta menambahkan warning eksplisit. Replay
offline atas dua output mentah persis kini menghasilkan record completed. S5
tetap memiliki klaim inconclusive yang tidak cocok dengan evidence executor
CONSISTENT_NEGATIVE; warning mismatch dipertahankan. Qwen fresh replay pada
evidence sama memberi klaim berbeda, jadi ini belum membuktikan akurasi model.
Konversi runner ledger juga lulus pada S2, S3, S4, S7, S9, S10-S12 dan S2-B;
S8 adapter menolak record original dengan analysis_error sesuai guard. Detail
hash ada di [evidence U03](evidence/u03-adaptive-shape-smoke-2026-10-14.json).

Semua smoke hanya memakai satu dari sepuluh kandidat, sehingga `pilot_slot_limit`
menandainya belum lengkap dan tidak eligible untuk metrik. U03 memenuhi wiring
lintas bentuk input; pilot A/B dengan budget penuh seluruh matriks belum
dijalankan. U01 kini lulus gate implementasi dan validasi tertutup pengembangan
telah dilaporkan; mismatch Qwen dipertahankan sebagai hasil kinerja. Untuk U04,
alias validator `VAL-01` sudah dicatat. Peneliti mengonfirmasi validator
memahami SQLi dan tidak terlibat dalam pengembangan. Audit dataset pilot
menemukan 24 kandidat dengan 144 observasi; body respons memang tidak tersedia,
tetapi log menyimpan marker allowlist sehingga exporter membuat excerpt
normalisasi turunan dan secara eksplisit menandai basisnya. Paket blind tiga
kandidat telah direview VAL-01 untuk uji prosedur, mencakup mixed evidence,
bukti konsisten, serta kandidat yang ditolak pada sesi valid. Paket berisi 21
observasi, ID acak, tanpa label kondisi/sumber/klaim, dan lolos cek kebocoran.
Tiga anotasi pilot berhasil lolos validasi impor. Satu keputusan pada kasus
time-based direvisi dari `success` menjadi `insufficient_evidence` atas
persetujuan VAL-01; alasan aslinya dipertahankan. Anotasi ini hanya menguji
prosedur, bukan data formal. Prosedur tersedia di
[prosedur validator U04](prosedur-validator-u04.md).
Suite lengkap setelah perubahan U04 lulus **149 tes**.

### U03: smoke tambahan kondisi B, 14 Oktober

Kondisi B/RAG-on dijalankan pada S3-S12 dengan report ZAP terverifikasi untuk
setiap level. Semua sepuluh run memakai satu kandidat dari budget sepuluh,
tiga konfirmasi, dan reset database sampel DVWA. Runtime valid dan analisis
Qwen selesai pada seluruh run. Evidence executor menunjukkan empat kandidat
positif dan enam negatif. Klaim model cocok secara biner pada lima run; tiga
klaim inconclusive terjadi pada evidence negatif, sementara S11 dan S12
Impossible memiliki klaim positif pada evidence negatif. Semua klaim dan
evidence dipertahankan terpisah. Ini smoke wiring, bukan FPR/PSR atau anotasi
validator. Rincian per run dan hash ada di
[evidence U03 tambahan](evidence/u03-adaptive-cross-condition-smoke-2026-10-14.json).

Dengan evidence awal A/S2-S12 dan B/S2, smoke tambahan ini melengkapi B/S3-S12.
Wiring A/B kini tercakup untuk S2-S12; S1 sudah mempunyai enam condition-run
pilot budget penuh pada U02. Suite penuh setelah perubahan dokumentasi lulus
145 tes. Pilot terpadu lintas matriks dan replikasi formal belum dijalankan.

### Penutupan U02 pada subset pilot

Setelah dua preflight awal hanya mencapai 0/10 dan 4/10 kandidat unik, prompt
v9 memberi sepuluh keluarga sintaks S1 dan menggeser keluarga pada retry.
Preflight dengan retrieval B tersimpan kemudian mencapai 10/10 kandidat unik
syntax-only, tanpa mengirim request ke DVWA. Bukti lengkap ada di
`results/raw/u02-generation-preflight-v9-20261014/generation-only-audit.json`.

Pilot enam condition-run baru, experiment ID
`u02-s1-ab-diversity-v9b-20261014`, menghasilkan:

| Kondisi | Replikasi/seed | Budget kandidat | Kandidat unik | Retry generasi | Decision sistem | Kandidat evidence 3/3 | Durasi attempt |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| A | 1 / 42 | 10/10 | 10 | 0 | positive | 3 | 122.1 dtk |
| B | 1 / 42 | 10/10 | 10 | 2 | positive | 3 | 143.2 dtk |
| A | 2 / 43 | 10/10 | 10 | 1 | positive | 8 | 115.0 dtk |
| B | 2 / 43 | 10/10 | 10 | 2 | positive | 3 | 142.0 dtk |
| A | 3 / 44 | 10/10 | 10 | 0 | positive | 3 | 123.3 dtk |
| B | 3 / 44 | 10/10 | 10 | 3 | positive | 2 | 144.5 dtk |

Semua run memakai tiga konfirmasi per kandidat, reset per run, dan mencatat
158 HTTP request. Semua payload lolos guard error-based syntax-only. Tidak ada
generation failure, attempt invalid, atau run excluded. Retry hanya
meregenerasi kandidat duplikat sebelum eksekusi. Loader dataset memeriksa
sequence ledger, hash
artifact, konteks attempt, serta ringkasan adaptif untuk keenam run. Hasil
keputusan/evidence di atas adalah hasil pilot teknis S1, bukan FPR/PSR formal
dan belum mendapat anotasi validator.

Plan awal `u02-s1-ab-diversity-v9-20261014` tertolak sebelum probe karena
mapping discovery untuk replikasi 2/3 belum dicantumkan. Plan dan ledger yang
terbentuk dipertahankan; pelaksanaan memakai plan baru yang lengkap. U02 kini
memenuhi kriterianya pada subset S1 A/B. Perluasan seluruh teknik dan level
tetap pekerjaan U03.

### U05: agregator FPR/PSR

Agregator membaca ground truth langsung dari katalog skenario dan menolak
perubahan label yang tidak sesuai matriks U05. FPR hanya memakai klaim sistem
sebelum review; perubahan anotasi VAL-01 tidak mengubah FP/TN. Coverage dan
alasan unresolved disimpan per replikasi, sementara denominator nol tetap
undefined. PSR memerlukan anotasi lengkap pada run positif yang valid; mixed
evidence tetap menjadi denominator dan tidak menjadi sukses.

Fixture hasil diketahui menguji TP/FN/FP/TN, tiga replikasi dengan mean dan SD
sampel, anotasi pending, mixed evidence, abstention, run invalid/incomplete,
penyebut nol, integritas anotasi, dan ekspor CSV. Uji pilot ledger C U04
mengimpor tiga keputusan VAL-01 dari 90 kandidat. Kesembilan run menunggu
anotasi kandidat lain, sehingga PSR tidak eligible. FPR A/B juga tidak eligible
karena pilot tidak memuat kondisi A/B atau skenario negatif S10-S12. Ini
menunjukkan gate menahan hasil yang tidak lengkap, bukan hasil evaluasi formal.
CLI menulis JSON/CSV pilot ke `results/raw/u05-validator-pilot-check-20261014-v2/`.
Suite penuh sesudah U05 lulus **156 tes**. Kontrak dan cara pakai tercatat di
[catatan U05](u05-agregasi-metrik-2026-10-14.md).
