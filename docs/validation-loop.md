# Validation loop SQLi pada DVWA

## Status dan batas MVP

`validation_loop.py` menerima kandidat dari file JSON, menjalankan satu skenario
per run pada DVWA lokal, mengklasifikasikan sinyal black-box, dan menulis JSONL
ke `results/raw/`. Runner file ini terpisah dari `adaptive_s1_loop.py`, yang
menghubungkan Qwen dan feedback untuk pengembangan S1 Low. SecLists disiapkan
melalui adapter provenance dan memakai executor yang sama.

Target dikunci pada loopback port `4280`. Runner memverifikasi login dan level
DVWA pada sesi yang sama sebelum mengirim kandidat. Batas default adalah 10
kandidat, tiga replikasi, timeout 15 detik per request, dan pemrosesan serial.
HTTP response, cookie, token, serta rahasia lain tidak disimpan di log.

## Cara kerja

1. Memilih satu skenario dari S1–S12 di `dvwa/experiment_scenarios.json`.
2. Login, memastikan indikator sesi masuk, mengatur level, lalu memastikan
   level tersebut terpilih.
3. Mengambil baseline benign `id=1` untuk tiap kandidat/replikasi. Baseline
   menjadi pembanding waktu dan memastikan indikator error yang sudah ada pada
   respons normal tidak dihitung sebagai sinyal baru.
4. Mengirim kandidat sesuai mekanisme endpoint. Pada High, runner mengirim ke
   helper input dahulu, lalu membaca halaman modul SQLi.
5. Mendeteksi error SQL baru, pasangan boolean `User ID exists`/`User ID is
   MISSING`, atau delta waktu minimal 1.500 ms terhadap kontrol benign `id=1`
   yang dikirim berpasangan dengan kandidat.
6. Menulis satu baris JSONL per payload yang dikirim dan satu baris keputusan
   per kandidat/replikasi. Keputusan manusia selalu dimulai sebagai `pending`.

Untuk blind boolean, satu kandidat memuat pasangan `true_payload` dan
`false_payload`. Pasangan dihitung berhasil jika respons masing-masing
menunjukkan indikator yang diharapkan. Satu kandidat boolean mengirim dua
payload pada setiap replikasi.

Label `TP`, `FP`, `TN`, atau `FN` pada log adalah klasifikasi sementara dari
sinyal otomatis terhadap label skenario. FPR/PSR final tetap memerlukan review
bukti dan persetujuan validator manusia sesuai protokol penelitian.

Kegagalan jaringan, login, sesi, level, form, reset, atau baseline dicatat
sebagai `runtime_failure`, menghentikan attempt, dan tidak diklasifikasikan
sebagai kegagalan payload. Protokol menetapkan invalidasi seluruh
condition-attempt, tanpa retry otomatis. Perbaiki lingkungan, mulai attempt
baru dengan login baru, dan reset database sebelum mengulang condition-run.
Data keputusan yang sempat tercatat pada attempt invalid tetap tersimpan untuk
audit dan tidak boleh masuk metrik.

## Menyiapkan file kandidat

Salin `dvwa/validation_payloads.template.json` ke lokasi lokal yang tidak
disinkronkan atau dibagikan. Ganti placeholder dengan payload penelitian yang
telah disetujui dan isi `scenario_id`, sumber, serta mode RAG. Kandidat error
dan time-based menggunakan `payload`; kandidat boolean menggunakan
`true_payload` dan `false_payload`. Format lengkap ada di
`schemas/validation-payloads.schema.json`.

Untuk batch LLM/SecLists dengan provenance dan pemeriksaan sumber, gunakan
[`candidate-sources.md`](candidate-sources.md) dan `dvwa/prepare_candidate_batch.py`.

`source` bernilai `LLM`, `SecLists`, atau `manual`. Untuk LLM, `rag_mode` harus
`on` atau `off`. SecLists/manual memakai `not_applicable`. Kandidat manual
berguna untuk smoke run protokol dan tidak dimasukkan ke perbandingan PSR.

## Menjalankan satu skenario

Pastikan container DVWA hidup dan database sampel sudah disiapkan. Jalankan
PowerShell dari root repositori. Contoh berikut menjalankan satu skenario
error-based pada lab lokal:

```powershell
python dvwa/validation_loop.py `
  --scenario S1 `
  --payload-file dvwa/validation_payloads.local.json `
  --confirm-local-dvwa
```

Untuk me-reset database sampel sebelum login, tambahkan `--reset-before-run`.
Perintah ini menghapus data pada database DVWA dan memulihkan akun sampel
`admin` / `password`. Runner hanya mengirim POST setelah memeriksa form setup
lokal, token CSRF, metode POST, action, dan marker sukses. Flag tersebut
opt-in dan jangan digunakan jika database lokal berisi data yang perlu
dipertahankan.

Gunakan satu file kandidat yang hanya berisi skenario yang dipilih. Replikasi
default adalah tiga dan dapat diturunkan untuk pemeriksaan protokol dengan
`--repetitions 1`; runner tidak menerima lebih dari tiga. Output bertimestamp
disimpan di `results/raw/`, yang diabaikan Git.

Jangan masukkan URL tunnel atau host lain. Untuk mengubah kredensial lokal,
set `DVWA_USERNAME` dan `DVWA_PASSWORD` di environment proses atau file
`dvwa/.env`; nilainya tidak dicetak dan tidak masuk ke JSONL.

## Runner Colab melalui tunnel

Untuk batch yang dibuat di Colab, gunakan bagian **11. Validasi satu batch ke
DVWA melalui tunnel bertoken** pada `notebooks/colab_langchain_setup.ipynb`.
Runner ini terpisah dari skrip lokal yang dikunci ke loopback. Ia hanya menerima
HTTPS Cloudflare Quick Tunnel (`*.trycloudflare.com`), memasang
`X-Lab-Token` pada tiap request/redirect, memakai cookie jar sementara, lalu
memastikan login dan security level pada sesi DVWA yang sama.

Jalankan lebih dulu `notebooks/colab_dvwa_smoke.ipynb`, pilih file batch yang
sudah direview dari `MyDrive/TA-SQLi/candidate-batches/`, dan mulai dengan
`REPETITIONS = 1`. Cell runner menampilkan kandidat sebelum meminta frasa
`SEND_SELECTED_BATCH_TO_MY_DVWA`. Tanpa frasa itu tidak ada request yang
dikirim. URL tunnel dan token diminta saat run dan tidak disimpan. JSONL
disimpan ke `MyDrive/TA-SQLi/validation-logs/` tanpa cookie, password, token,
URL, atau response body; keputusan manusia tetap `pending`.

Notebook runner belum dijalankan di Colab. Smoke run awal pada remote runner
harus diperlakukan sebagai pemeriksaan protokol, bukan data formal FPR/PSR.

## Arti sinyal

- Error-based: indikator SQL/database pada respons kandidat yang tidak muncul
  pada respons baseline.
- Boolean-based blind: respons payload kondisi true memuat indikator exists,
  dan respons kondisi false memuat indikator missing.
- Time-based blind: durasi request kandidat dikurangi baseline sekurang-
  kurangnya 1.500 ms.

Ambang waktu mengikuti validasi ground truth 1 Oktober 2026. Sinyal otomatis
adalah bukti untuk ditinjau, bukan hasil final. Simpan data mentah lokal dan
bagikan hanya log yang telah disanitasi.
