# Rencana penyelesaian tugas akhir

Tanggal penyusunan: 16 Oktober 2026.
Status: diperbarui 19 Oktober 2026 setelah R3, anotasi VAL-01 dan agregasi F02.
Ruang lingkup tetap DAST/black-box pada DVWA Low, Medium, High, dan Impossible,
untuk SQL injection error-based, boolean-based blind, dan time-based blind.

## Prinsip pengerjaan

- Pisahkan data pilot dan data formal. Setiap perubahan kode, prompt, korpus,
  atau protokol yang memengaruhi hasil memakai snapshot dan experiment ID baru.
- Pertahankan klaim Qwen, sinyal executor, dan keputusan validator sebagai
  keluaran yang berbeda.
- Jangan menyetel prompt memakai fixture U01 yang sudah dibuka. Mismatch model
  dicatat sebagai hasil kinerja.
- Jangan mengisi budget kandidat yang kurang dengan payload manual atau
  SecLists, dan jangan menggabungkan attempt berbeda untuk melengkapi satu run.
- File dalam sources/ tetap menjadi referensi baca saja.

## Status terkini per 19 Oktober

- U07 selesai dengan release formal v18-r2 dan protokol frozen.
- F01 selesai: R1/R2/R3 masing-masing 33 run applicable completed; 9 slot
  C/Impossible excluded sesuai desain. Tidak ada unit invalid pada checkpoint akhir.
- F02 selesai untuk penerimaan, validasi dan agregasi: seluruh 990 anotasi
  terbaru VAL-01 diimpor. PSR utama eligible pada 540 kandidat B/C S1-S9.
- FPR utama undefined karena S10 inconclusive pada A/B di ketiga replikasi;
  coverage keputusan negatif 2/3 per kelompok. Mean PSR B=27,78% dan C=74,81%,
  dengan SD sampel 0,00 dan 1,70 poin persentase pada tiga replikasi.
- Lihat [progres formal](progress-2026-10-19.md) dan
  [hasil VAL-01](f02-hasil-val01-2026-10-19.md).

## Riwayat audit per 17 Oktober

- U06.3 menjalankan ulang 33 run applicable pada snapshot v15 yang sama. Ledger
  final memiliki 28 completed, lima excluded karena budget kandidat tidak
  penuh, tiga slot C/S10-S12 yang tidak berlaku, dan nol invalid. Loader
  memverifikasi seluruh 36 slot serta hash artefak.
- Budget A/B lengkap pada 19 dari 24 run. A mencapai 10/10 pada 10/12 run; B
  pada 9/12. Lima incomplete berisi 8 atau 9 kandidat, tanpa invalid runtime.
  Ini menjadi gate yang tercatat, bukan hasil yang diisi ulang atau disamarkan.
- Pilot S3 terpisah v15 mencapai 10/10 pada A dan B untuk replicate 1. Bukti
  tersebut tetap terpisah dari matriks terpadu.
- Follow-up API eksplisit U06.2 membuktikan coverage 2/2 koordinat pada Low,
  Medium, High, dan Impossible. Low/Impossible memakai GET; Medium/High
  memakai POST. Alert hanya berlaku pada sesi dan koordinat pilot yang diuji.
- Empat anotasi blind VAL-01 sudah diimpor dan alur U06.4 selesai sebagai pilot.
  Agregator tetap menahan PSR/FPR karena coverage tidak lengkap.
- U07 telah diaudit. Pilot v17 menyelesaikan 33 run applicable, dengan tiga
  slot C/S10-S12 dikecualikan sesuai desain, nol run invalid, dan nol mismatch
  budget. Peneliti menyetujui korpus utama untuk penggunaan formal dan index
  yang disetujui sudah dipulihkan. Plan revalidasi v18 mengunci hash keenam
  file index, tetapi belum dijalankan. Paket kesiapan terbaru mencatat 8/11
  gate lulus dan 184 tes offline lulus. Tiga gate masih pending: revalidasi
  pilot dengan index terpin, bukti preflight runtime/log Ollama, dan release
  manifest formal. Protokol aktif masih berstatus pilot. Lihat
  [laporan U07](u07-freeze-kesiapan-formal-2026-10-17.md).

Rincian run dan hash: [evidence U06 v15](evidence/u06-v15-integrated-pilot-2026-10-16.json).

Rujukan utama: [review progres 14 Oktober](review-progress-2026-10-14.md),
[laporan U06](u06-pilot-zap-baseline-2026-10-14.md),
[prosedur validator U04](prosedur-validator-u04.md), dan
[agregator U05](u05-agregasi-metrik-2026-10-14.md).

## Checklist pekerjaan

### D01. Selaraskan dokumentasi status

Status: selesai.

- [x] Buat backlog penyelesaian bertanggal dan tautkan dari README.
- [x] Tambahkan snapshot status terkini ke README.
- [x] Selaraskan tabel T06 di review progres dengan status U04 dan U05.
  Bedakan alat persiapan yang selesai dari anotasi serta metrik formal yang
  masih menunggu data.
- [x] Perbarui status VAL-01 pada protokol dan status review korpus pada
  panduan sumber kandidat.
- [x] Koreksi narasi metodologi yang masih menyebut LangChain lokal belum
  terintegrasi. Nyatakan bahwa bukti integrasi saat ini terbatas pada pilot S1.
- [x] Perbarui README DVWA dan tandai petunjuk Colab sebagai jalur historis
  yang ditunda.
- [x] Beri tautan ke status terbaru pada catatan progres 11-12 Oktober.
  Pertahankan isi evidence dan angka historisnya.

Kriteria selesai: README menjadi pintu masuk status aktif, setiap status
pending yang telah berubah diberi konteks atau tautan, dan tidak ada konflik
antara ringkasan milestone dengan rincian U04-U06.

### U06.1. Stabilkan budget generasi A/B pada loop live

Status: selesai untuk pilot S3 A/B replicate 1. Pilot v15 mencapai budget
10/10 pada kedua arm dalam batas retry. U06.3 kemudian menguji matriks terpadu:
19/24 run A/B mencapai 10/10, sedangkan lima run dicatat incomplete.

- Telusuri duplikasi, kandidat invalid, dan batas retry pada generasi yang
  berjalan bersama analisis serta executor, bukan hanya pada preflight.
- Evaluasi perubahan prompt atau corpus sebagai versi terpisah. Setiap corpus
  baru perlu keputusan review dan hash tersendiri.
- Pastikan A dan B memakai profil generasi, budget, guard, dan batas retry yang
  sama. Perbedaan perlakuannya hanya konteks retrieval pada generasi/regenerasi.
- Tetap catat run sebagai excluded bila budget tidak tercapai. Jangan menaikkan
  retry atau mengubah budget setelah melihat hasil tanpa keputusan protokol
  versi baru.

Evidence update 16 Oktober: pilot `u06-s3-candpilot-v12-20261016` menghasilkan
2/10 kandidat unik pada A dan 2/10 pada B. Prompt v13 menambahkan instruksi
retry khusus duplikasi; pilot `u06-s3-candpilot-v13-20261016` menghasilkan
3/10 pada A dan 2/10 pada B. Keempat run tetap excluded dan tidak eligible
untuk metrik. v14 kemudian mencapai 10/10 pada A dan 8/10 pada B; B tetap
excluded. Pada v15, generator meminta 10 opsi pada tiap panggilan lalu memilih
satu opsi valid yang belum pernah dicoba. Budget tetap 10, retry maksimal 2,
temperature 0, dan profil struktur A/B identik. Hasil v15: A dan B masing-masing
10/10 kandidat unik, 10/10 analisis selesai, 0 kandidat invalid runtime, dan
seluruh event regenerasi tercatat. A tidak mengambil chunk vector store; B
mengambil dua chunk. Ringkasan dan batas interpretasi ada di
[laporan U06](u06-pilot-zap-baseline-2026-10-14.md).

Kriteria selesai untuk pasangan S3: kedua condition-run mencapai 10 kandidat
unik dalam batas retry, seluruh regenerasi tercatat, tidak ada kandidat
runtime-invalid, dan A tidak mengambil chunk vector store. Stabilitas pada
seluruh matriks tetap dinilai di U06.3 dan lima pengecualian dicatat di sana.

### U06.2. Buktikan coverage baseline ZAP aktif

Status: selesai. Follow-up API eksplisit membuktikan 2/2 koordinat pada keempat
level dengan method yang sesuai katalog: GET untuk Low/Impossible dan POST
untuk Medium/High. Semua setup plan memverifikasi level/auth, seluruh scan
selesai, dan setiap koordinat terlihat pada request HAR bertanda rule 40018
serta 40019.

- Tetapkan cara membedakan request active scanner dari request seed, spider,
  atau requestor.
- Buktikan coverage pada koordinat yang direncanakan untuk tiap level, termasuk
  GET Low/Impossible, POST Medium, dan helper session/cookie High.
- Simpan provenance scan, rule, koordinat, level, autentikasi, dan report.
- Tafsirkan ketiadaan alert hanya setelah coverage koordinat terbukti.

Evidence update 16 Oktober: baseline v2 semula hanya membuktikan 1/2 koordinat
Low dan 0/2 pada level lain. Follow-up API eksplisit membuktikan 2/2 koordinat
per level. Low dan Impossible memakai GET; Medium dan High memakai POST
`id=1&Submit=Submit`. Semua koordinat memiliki request HAR dengan header
scanner ID yang mengandung rule 40018 dan 40019. Low dan Medium masing-masing
menghasilkan satu alert rule 40018 pada endpoint utama; High dan Impossible
tidak menghasilkan alert. Hasil ini hanya berlaku untuk sesi, level, policy,
dan koordinat pilot tersebut. Lihat
[laporan U06](u06-pilot-zap-baseline-2026-10-14.md).

Kriteria selesai: report dapat menunjukkan request scanner yang dapat
diatribusikan ke setiap koordinat target dalam sesi serta level yang benar.
Koordinat tanpa coverage tetap ditandai unresolved.

### U06.3. Jalankan ulang pilot terpadu

Status: selesai sebagai pilot terpadu; lima gate budget A/B belum lulus. Plan
`u06-v15-integrated-20261016` mencakup 33 condition-run applicable pada satu
snapshot. Tiga slot C/S10-S12 tidak berlaku sesuai desain.

- Buat snapshot kode, prompt, korpus/index, model, protokol, dan plan baru.
- Beri experiment ID baru. Jangan mengubah atau melanjutkan ledger U06 lama.
- Jalankan A/B untuk S1-S12 dan C untuk S1-S9, dengan budget 10 kandidat,
  tiga konfirmasi, reset per condition-run, dan urutan protokol v5.
- Untuk closeout U06 yang terpadu, catat 33 run applicable pada snapshot yang
  sama. Pilot SecLists terdahulu tetap menjadi evidence terpisah.
- Catat durasi, request, retry, duplicate, invalid, excluded, hasil analisis,
  dan hash artefak.

Hasil: A menyelesaikan 10/12 run, B 9/12, dan C 9/9. Lima run incomplete
adalah A/S1 (8/10), A/S10 (9/10), B/S3 (8/10), B/S6 (8/10), dan B/S9 (8/10).
Semua 231 kandidat LLM yang sempat dieksekusi selesai dianalisis; runtime
invalid 0. Audit generasi mencatat 255 panggilan, 24 langkah retry, 465
duplikasi, 1.640 opsi unik yang tidak dipilih, dan 16 opsi invalid yang ditolak
sebelum eksekusi. 90 kandidat kontrol SecLists pada C/S1-S9 selesai.

Durasi attempt berurutan 3 jam 54 menit. Summary, provenance, exclusion,
keputusan sistem, dan hash ledger/snapshot ada di
[evidence U06 v15](evidence/u06-v15-integrated-pilot-2026-10-16.json) dan
`results/raw/pilot/u06-v15-integrated-20261016/`. Keputusan S10-S12 A adalah
tidak evaluable, positif, positif; pada B adalah inconclusive, positif,
positif. Ini observasi pilot, bukan FPR final.

Kriteria selesai: 33 run pilot memiliki ledger dan provenance valid; semua
masalah budget yang belum lulus dicatat sebagai gate. Kriteria ini terpenuhi.
Pilot tidak menghasilkan metrik formal.

### U06.4. Tinjau sampel pilot dan jalankan audit agregator

Status: selesai untuk validasi alur pilot. Empat anotasi VAL-01 sudah diterima,
diimpor, dan diaudit. Sampel ini hanya memvalidasi alur review, bukan coverage
anotasi atau metrik formal.

- Bagikan hanya folder validator, tanpa mapping privat, label kondisi,
  sumber kandidat, ground truth, atau klaim sistem.
- Impor keputusan dengan alias validator yang sudah ditetapkan dan cek ID,
  cakupan, duplikasi, serta alasan anotasi.
- Jalankan agregator pada pilot untuk memastikan coverage dan exclusion
  dilaporkan. Jangan menyajikan hasil pilot sebagai metrik penelitian.

Paket publik ada di
`results/raw/u06-v15-integrated-review-sample-20261016/validator/`; hanya folder
`validator/` yang boleh dibagikan. Paket memuat empat kandidat dan tidak
memiliki field kondisi, sumber kandidat, ground truth, atau klaim sistem.
Hash paket: `0430c09924409ce536129cd1d17c007a899d953c558df5d764cc39621e09e77e`.
Mapping dan aturan sampling tersimpan privat satu tingkat di atas folder itu.
Audit pra-anotasi ada di `results/raw/pilot/u06-v15-integrated-20261016/`.
CSV awal VAL-01 memiliki masalah quoting. Jawaban asli dipertahankan dan salinan
`validator/annotations.fixed.csv` dibuat dengan kolom yang benar. Empat ID cocok
dengan paket, alias VAL-01 dan seluruh keputusan/alasan lolos validasi. Distribusi
keputusan adalah dua `failure`, satu `insufficient_evidence`, dan satu `success`.
Perbaikan importer menormalkan CRLF sebelum memeriksa hash paket agar paket
Windows tetap lolos pemeriksaan integritas.

Impor tersimpan di `annotations.imported.json`; audit pilot ada di
`results/raw/pilot/u06-v15-integrated-20261016/review-audit.json` dan `.csv`.
PSR tetap tidak eligible: 0 dari 18 baris run memenuhi cakupan anotasi. FPR
tetap tidak eligible: 0 dari 6 replikasi memenuhi coverage formal. Tidak ada
metrik FPR/PSR yang dilaporkan sebagai hasil penelitian.

Kriteria selesai terpenuhi untuk U06.4: paket ditinjau secara blind, impor lolos
validasi, dan agregator menahan metrik yang belum eligible dengan alasan yang
dapat ditelusuri. U07 mulai diaudit pada 17 Oktober, sesuai laporan terpisah.

### U07. Freeze kesiapan formal

Status terkini: selesai dengan release formal v18-r2 pada 18 Oktober.
Uraian dan checklist berikut menyimpan tahapan audit sebelumnya.

Snapshot 17 Oktober: pilot v17 lulus pemeriksaan kelengkapan:
33 run applicable selesai, tiga slot C/Impossible dikecualikan sesuai desain,
tanpa run invalid atau mismatch budget. Snapshot index yang disetujui sudah
dipulihkan dan plan v18 mem-pin hash keenam file index, tetapi pilot v18 belum
dijalankan. Paket kesiapan terbaru mencatat 8/11 gate lulus dan 184 tes offline
lulus. Tiga gate masih pending: revalidasi pilot dengan index terpin,
preflight runtime dengan bukti log Ollama yang mencakup rentang pilot, dan
release manifest formal. Protokol aktif tetap berstatus pilot. Keputusan korpus
tidak dengan sendirinya menyetujui eksekusi dataset formal. Detail ada di
[laporan U07](u07-freeze-kesiapan-formal-2026-10-17.md).

#### Checklist operasional pilot revalidasi v18

Checklist ini hanya untuk menutup bukti pilot dan kesiapan runtime U07. Pilot
v18 tetap memakai dataset `pilot`; checklist ini tidak menjalankan atau
menyetujui dataset formal.

**Sebelum run**

- [ ] Peneliti menyetujui revalidasi pilot v18 dan penggunaan DVWA lokal.
  Persetujuan penggunaan korpus saja bukan persetujuan menjalankan pilot atau
  dataset formal.
- [x] Plan `u07-v18-index-pinned-20261017` tetap berstatus `pilot`, mencakup
  36 slot: 33 planned dan 3 excluded pada C/S10-S12, kondisi A/B/C, budget
  10 kandidat, serta 3 konfirmasi per kandidat. Validasi statis juga
  menemukan 12 pemetaan discovery skenario/replicate dengan empat report unik,
  serta tiga file sumber SecLists dengan hash yang cocok dengan selection
  manifest.
- [x] Plan pilot dan plan formal mem-pin enam hash Chroma yang sama dengan
  receipt. SHA-256 byte file plan dan hash kanonis runner dicatat di bawah.
  Perubahan implementasi sudah di-commit pada `1565bfc`. Snapshot hash sumber
  dan HEAD akhir pemeriksaan dicatat pada
  `results/raw/ollama-u07-v18-20261018-112053/static-readiness.json`.
  Index tidak dibangun ulang atau diubah.
- [x] Plan v18 memakai receipt pilot terpisah berstatus `approved-for-pilot-use`,
  berdasarkan persetujuan eksplisit peneliti pada 18 Oktober 2026. Receipt
  `results/raw/decision-receipts/u07-v18-pilot-corpus-decision-20261018.json`
  mengikat corpus dan keenam file index; plan pilot hanya memperbarui
  `knowledge_snapshot`. SHA-256 byte file plan
  `51ecab922e8158cffd9379a12a15e1fa7e5cef55394113c3fb50740110d634da`;
  hash kanonis plan yang dicatat runner ke ledger
  `c61ec8b7c7f9e0458c41ccd13c89348942c409c9c55c2decd3f4399a85860bfe`.
  Keduanya memakai representasi berbeda, jadi nilainya tidak harus sama.
  Corpus, manifest, index, dan receipt formal tidak diubah.
- [x] Pemeriksaan read-only 18 Oktober 2026: container `dvwa-dvwa-1` dan
  `dvwa-db-1` aktif; login DVWA pada `127.0.0.1:4280` merespons HTTP 200;
  database `dvwa` memiliki tabel `users` dan empat tabel total. Tunnel serta
  gateway berhenti, dan model `qwen2.5:7b` serta `nomic-embed-text:latest`
  tersedia melalui API Ollama lokal. Tidak ada reset database. Pemeriksaan
  status Compose memerlukan placeholder sementara untuk `ZAP_API_KEY` karena
  variabel itu tidak ada di shell inspeksi; container tidak diubah.
- [x] Perubahan runner, schema, tool release, dan panduan U07 sudah ditinjau
  dan di-commit sebagai `1565bfc`. Ledger pilot akan merekam hash runner/schema;
  kandidat freeze sesudahnya mensyaratkan commit yang sama dengan `HEAD` dan
  working tree bersih. Koreksi assertion dan regression check receipt pilot
  dicatat pada pemeriksaan lanjutan sebelum run.
- [x] Log aktif terkonfirmasi setelah restart Ollama idle yang disetujui
  peneliti pada 18 Oktober. Server PID `20380`, parent launcher `20884`, mulai
  pukul 11:22:22 WIB dan mendengarkan pada `127.0.0.1:11434`. Launcher
  tersembunyi menggabungkan stdout/stderr dengan flush per baris ke
  `$env:LOCALAPPDATA\Ollama\server-u07-v18-20261018-112053.log`.
  Marker startup, PID launcher, dan GET metadata cocok; ukuran log bertambah
  setelah request. Versi Ollama `0.40.6`, hash executable, dan seluruh digest
  model tetap sama. `OLLAMA_DEBUG=1` dan `OLLAMA_HOST=127.0.0.1:11434` hanya
  berlaku pada proses ini. Bukti ada di
  `results/raw/ollama-u07-v18-20261018-112053/session-active.json`.
- [x] Baseline offline sebelum pilot: 186 tes lulus, termasuk penolakan
  receipt non-pilot saat eksekusi pilot, attestation pilot yang mengikat index
  persis, serta validasi tanpa mengubah asset formal. Log lengkap ada di
  `results/raw/ollama-u07-v18-20261018-112053/tests.log`.
- [ ] Pertahankan server dan log sesi tersebut selama seluruh attempt pilot,
  lalu capture log ke `results/raw/`. Nama `server*.log` di lokasi standar
  dikenali alat capture runtime. Kesiapan log aktif belum membuktikan cakupan
  waktu pilot; `pilot_server_log.coverage_verified` baru dinilai sesudah run.
  Log aktif akan bertambah dan hash-nya memang berubah; hash evidence harus
  mengacu pada salinan snapshot setelah run, bukan dipaksakan tetap sama
  dengan snapshot preflight.
  Jika server berhenti atau direstart, buat sesi log baru dan catat kembali
  identitas proses sebelum pilot.
- [x] Tinjau plan melalui validator statis tanpa membuat ledger, mengirim
  probe, atau menjalankan inference. Gunakan fungsi validasi langsung;
  CLI runner tanpa `--execute` tetap dapat membuat metadata eksperimen:

```powershell
@'
import collections, json, sys
from pathlib import Path
sys.path.insert(0, "dvwa")
from experiment_protocol import load_protocol
from run_local_experiments import planned_units, validate_plan
protocol = load_protocol()
path = Path("dvwa/local_run_plan.u07-v18-index-pinned-20261017.json")
plan = validate_plan(json.loads(path.read_text(encoding="utf-8")), protocol)
print(dict(collections.Counter(unit["status"] for unit in planned_units(plan, protocol))))
'@ | & .\.venv\Scripts\python.exe -
```

**Jalankan dan pulihkan hanya sesuai protokol**

- [ ] Jalankan pilot dengan konfirmasi eksplisit bahwa target adalah DVWA lokal
  dan reset database sampel diizinkan. Runner melakukan login baru dan reset
  sebelum setiap condition-run:

```powershell
& .\.venv\Scripts\python.exe dvwa/run_local_experiments.py `
  --plan dvwa/local_run_plan.u07-v18-index-pinned-20261017.json `
  --execute --confirm-local-dvwa --confirm-database-reset
```

- [ ] Jika proses terputus, simpan ledger dan artefak apa adanya. Jangan ganti
  seed, budget, prompt, plan, atau gabungkan attempt. Setelah penyebab runtime
  diperbaiki, gunakan prosedur resume/retry yang tercatat di
  `dvwa/README.md`; attempt baru wajib tercatat dengan login dan reset baru.
- [ ] Catat waktu mulai dan selesai, kondisi runtime, gangguan, dan tindakan
  pemulihan. Jangan menafsirkan keberhasilan konfirmasi pilot sebagai PSR/FPR.

**Audit hasil dan tutup gate**

- [ ] Loader memverifikasi seluruh 36 slot: 33 completed, tiga exclusion yang
  direncanakan, semua 33 run applicable eligible, 10 kandidat per run, tanpa
  budget mismatch atau run invalid yang belum terselesaikan.
- [ ] Verifikasi cakupan S1-S12 pada A/B dan S1-S9 pada C, provenance serta
  hash ledger/artefak, isolasi retrieval A/B, analisis tanpa retrieval, dan
  telemetri token untuk seluruh panggilan.
- [ ] Jalankan offline contract suite pada snapshot final U07 dan simpan log
  lengkap ke folder kesiapan baru, misalnya
  `results/raw/u07-formal-readiness-20261018-v18/`:

```powershell
New-Item -ItemType Directory -Force results/raw/u07-formal-readiness-20261018-v18 | Out-Null
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v `
  *> results/raw/u07-formal-readiness-20261018-v18/tests.log
```

- [ ] Setelah pilot selesai, capture runtime dengan path pilot v18 secara
  eksplisit. Pastikan `pilot_server_log.coverage_verified` bernilai `true`,
  `positive_truncation_count` dan `explicit_input_truncation_warnings` bernilai
  nol, startup Python bersih, dependency konsisten, model cocok, serta runtime
  hanya mencatat lab lokal:

```powershell
& .\.venv\Scripts\python.exe dvwa/prepare_formal_freeze.py `
  --capture-runtime results/raw/u07-formal-readiness-20261018-v18/runtime.json `
  --pilot results/raw/pilot/u07-v18-index-pinned-20261017
```

- [ ] Bangun paket kesiapan baru dengan plan formal yang mem-pin index yang
  sama dan pilot v18 sebagai evidence terpilih. Jangan memakai default pilot
  v17 pada tahap ini:

```powershell
& .\.venv\Scripts\python.exe dvwa/prepare_formal_freeze.py `
  --runtime results/raw/u07-formal-readiness-20261018-v18/runtime.json `
  --plan dvwa/local_run_plan.formal-20261017-approved-index.json `
  --output-dir results/raw/u07-formal-readiness-20261018-v18 `
  --pilot results/raw/pilot/u07-v18-index-pinned-20261017
```

- [ ] Pastikan gate `retrieval-index-snapshot-pinned` dan
  `context-and-runtime-preflight` berstatus `passed` pada manifest baru.
  Karena log Ollama v17 tidak ditemukan, nyatakan dengan jelas bahwa log v18
  adalah bukti runtime pilot revalidasi, bukan log v17 yang berhasil dipulihkan.
- [ ] Tinjau semua 11 gate, hash arsip/backup, lock dependency, plan, hasil
  offline suite, dan status working tree. Kandidat tidak boleh diubah setelah
  hash approval dibuat. Setelah seluruh gate selain `runtime-manifest-frozen`
  lulus dan working tree bersih, audit kandidat dengan tool release:

```powershell
& .\.venv\Scripts\python.exe dvwa/release_formal_freeze.py `
  --candidate-dir results/raw/u07-formal-readiness-20261018-v18 --check
& .\.venv\Scripts\python.exe dvwa/release_formal_freeze.py `
  --candidate-dir results/raw/u07-formal-readiness-20261018-v18 `
  --write-approval-template
```

- [ ] Peneliti meninjau hash kandidat, formal plan, protokol, receipt korpus,
  arsip, dan seluruh evidence, lalu mengisi keputusan pada
  `formal-freeze-approval.json`. Hanya receipt `approved-for-formal-freeze`
  yang terikat pada hash tersebut dapat dipakai untuk membuat release
  manifest dan membekukan protokol. Perintah release lengkap ada di
  `dvwa/README.md`. Jangan mengubah status frozen hanya dengan mengedit JSON.
- [ ] Sebelum F01, dapatkan keputusan terpisah untuk menjalankan dataset formal.
  Setelah release U07, siapkan 12 discovery ZAP baru sesuai tiga replikasi;
  jangan memakai ulang report pilot. Buat receipt `formal-dataset-execution`
  untuk `experiment_id`, hash plan, dan hash release manifest yang tepat.
  Runner formal mensyaratkan flag `--formal-execution-approval` saat
  `--execute` dan `--resume --execute`; freeze saja tidak mengizinkan F01.

Kriteria lulus pilot v18: seluruh slot dan budget memenuhi kontrak, hash
index pilot sama dengan receipt korpus dan plan formal, kedua gate bukti pilot
berstatus passed, dan paket kesiapan baru dapat direproduksi serta ditinjau.
Release manifest dan persetujuan eksekusi formal tetap menjadi keputusan
terpisah.

- Catat commit kode, dependency, runtime, digest model/embedding/image Docker,
  versi LangChain, prompt, corpus, index, top-k, SecLists, ZAP policy, serta
  protokol v5 yang dipilih.
- Pastikan prompt tidak mengalami truncation yang tidak tercatat.
- Periksa warning startup interpreter yang pernah dicatat. Perbaiki atau
  dokumentasikan runtime bersih yang akan dipakai.
- Tetapkan lokasi dataset formal, backup, ruang disk, penamaan output, dan
  rencana pemulihan.
- Siapkan plan baru untuk 99 condition-run: A 36, B 36, C 27. Budget 10
  berarti 990 slot kandidat terencana jika budget itu dipertahankan.
- Pastikan setiap formal gate menunjuk evidence yang memenuhi cakupannya.

Kriteria selesai: manifest dan plan dapat direproduksi; seluruh formal gate
memiliki evidence; dataset formal baru terpisah dari pilot. Jangan menandai
protokol frozen jika ada gate yang belum terpenuhi.

### F01. Jalankan eksperimen formal

Status: selesai 19 Oktober 2026. R1/R2/R3 masing-masing menyelesaikan 33 run
applicable; 99 run completed, 9 excluded sesuai desain, 0 unit invalid pada
checkpoint akhir. Artefak R1/R2 dipertahankan tanpa pengujian ulang.

- Jalankan 99 condition-run sesuai urutan v5 dan seed yang ditetapkan.
- Jalankan satu blok replikasi per sesi dengan `--one-replicate-per-session`.
  Pada sesi berikutnya, resume ledger yang sama dengan plan, release, dan
  receipt eksekusi yang sama. Runner mencatat pause pada batas replikasi.
- Sertakan perubahan runner dan schema pause ini saat membangun ulang paket
  kesiapan dan release formal; approval harus terikat pada snapshot terbaru.
- Untuk setiap run, terapkan login baru, reset database, verifikasi level,
  discovery yang sesuai, baseline, budget, dan ledger.
- Pertahankan run invalid, excluded, abstention, dan hasil negatif sebagai
  kategori terpisah. Gunakan aturan recovery protokol, bukan pengulangan untuk
  mencari hasil yang diinginkan.
- Validasi hash plan dan artefak secara berkala tanpa mengubah hasil mentah.

Kriteria selesai: dataset formal dapat dimuat melalui loader, memiliki provenance
lengkap, serta menunjukkan coverage dan alasan exclusion untuk seluruh run.

### F02. Anotasi blind dan hitung FPR/PSR

Status: selesai untuk penerimaan anotasi, pemeriksaan dan agregasi. Seluruh
990 anotasi terbaru VAL-01 diimpor; PSR utama B/C eligible. Mean PSR B=27,78%
dan C=74,81%, SD sampel masing-masing 0,00 dan 1,70 poin persentase. FPR utama
tetap undefined karena S10 inconclusive pada seluruh A/B, dengan coverage
negatif 2/3 per kelompok. Semua hash sumber tetap sama dan anotasi awal
dipertahankan. Detail ada di [hasil VAL-01](f02-hasil-val01-2026-10-19.md).

- Buat dan tinjau paket blind untuk seluruh kandidat yang memenuhi syarat.
- Anotasi bukti dengan VAL-01 tanpa membuka kondisi atau label ground truth
  sebelum tahap yang ditetapkan prosedur.
- Hitung FPR dari klaim sistem yang tersimpan sebelum review pada S10-S12.
- Hitung PSR B/C pada S1-S9 sesuai bukti 3/3 dan keputusan validator.
- Laporkan metrik per replikasi, mean dan SD sampel. Sertakan coverage,
  penyebut, exclusion, dan nilai undefined.

Kriteria selesai: setiap angka dapat ditelusuri ke run, kandidat, evidence,
dan anotasi. Agregator menolak metrik utama jika run atau anotasi belum lengkap.

### F03. Selesaikan analisis dan pelaporan TA

Status: siap dimulai setelah penerimaan anotasi dan agregasi F02 selesai.
Data PSR tersedia; FPR utama yang undefined wajib dipertahankan dan dibahas
sebagai keterbatasan, bukan diubah menjadi nol atau dihitung dari anotasi manusia.

- Analisis hasil per kondisi, teknik, level, dan replikasi tanpa memperlakukan
  skenario dari satu DVWA sebagai aplikasi independen.
- Bahas mismatch klaim Qwen dan konsekuensinya terhadap FPR/PSR.
- Siapkan penilaian CVSS hanya untuk temuan yang dikonfirmasi dan laporan
  temuan sesuai kebutuhan proposal.
- Tulis hasil, pembahasan, keterbatasan, kesimpulan, dan rekomendasi.
- Pastikan naskah tetap pada cakupan DAST SQLi DVWA yang disetujui.

Kriteria selesai: seluruh kesimpulan didukung data formal dan batas generalisasi
serta keterbatasan ditulis dengan jelas.

## Urutan dependensi

- D01 dapat berjalan bersamaan dengan U06.1 dan U06.2.
- U06.1 dan U06.2 dilanjutkan ke U06.3.
- U06.3 dilanjutkan ke U06.4 dan U07.
- U07 dilanjutkan ke F01, lalu F02, lalu F03.

Estimasi waktu formal belum ditetapkan. Durasi 79,1 menit pada U06 lama tidak
memenuhi budget kandidat penuh dan tidak cukup untuk memproyeksikan durasi
eksperimen formal.
