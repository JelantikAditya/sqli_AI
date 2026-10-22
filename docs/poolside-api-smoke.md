# Smoke API Poolside

Paket ini memeriksa konektivitas langsung ke Poolside-hosted inference.
Gunakan API key dari Poolside Platform, bukan key OpenRouter atau HCNSEC.
Python standard library cukup; tidak ada dependency tambahan.

## Langkah penggunaan

Jalankan dari root proyek pada terminal PowerShell lokal:

```powershell
.\.venv\Scripts\python.exe development\run_poolside_smoke.py --save-key
.\.venv\Scripts\python.exe development\run_poolside_smoke.py --check-key
.\.venv\Scripts\python.exe development\run_poolside_smoke.py --dry-run
.\.venv\Scripts\python.exe development\run_poolside_smoke.py --run
```

Masukkan key hanya pada prompt tersembunyi `--save-key`. Key disimpan sebagai
teks biasa di `.env.poolside.local`, yang diabaikan Git oleh aturan `.env.*`.
Jangan mengirim key melalui chat. Environment `POOLSIDE_API_KEY`, bila diisi,
mengalahkan file lokal. `--check-key` hanya memeriksa ketersediaan credential;
validitas key terhadap provider baru diperiksa oleh `--run`.

## Batas dan profil

- Endpoint: `https://inference.poolside.ai/v1`.
- Model tetap: `poolside/laguna-s-2.1`; berhenti jika ID tidak terdaftar.
- Maksimum dua request: GET `/models`, lalu satu POST `/chat/completions`.
- Prompt hanya meminta `API_OK`; temperature 0, maksimum 128 token,
  `stream=false`, `chat_template_kwargs.enable_thinking=false`.
- Timeout GET 20 detik dan POST 60 detik; tanpa retry, redirect, atau fallback.
- Tidak menghubungi DVWA, menjalankan P2/P3, atau mengubah hasil Qwen.
- Log tersanitasi disimpan dengan nama baru dalam `results/raw/poolside-smoke/`.

Status `ok` mensyaratkan HTTP 200 pada kedua request, metadata model cocok,
`finish_reason=stop`, serta content tepat `API_OK` setelah trim whitespace.
Satu smoke yang sukses hanya membuktikan koneksi bekerja pada saat pengujian.
Kestabilan batch, format output tugas, dan kompetensi SQLi belum tervalidasi.

## Membaca kegagalan

- HTTP 401/403: periksa key, asal key, atau akses akun.
- HTTP 429: periksa kuota/rate limit sebelum mengirim ulang.
- HTTP 5xx atau timeout: simpan hasil sebagai kegagalan layanan/transport.
- `model-not-listed`: periksa katalog model akun; skrip tidak mengganti model.
- `model-metadata-mismatch`, `unfinished-response`, atau `unexpected-content`:
  tinjau respons dalam log sebelum mengubah profil pengujian.

Setelah koneksi berhasil, tahap berikutnya adalah smoke kontrak generasi dan
analisis serta validasi ulang paket P2 menggunakan Laguna. Perubahan model
memerlukan profil, identitas eksperimen, dan pencatatan metode tersendiri.

## Smoke kontrak dan paket P2 Poolside

`development/run_poolside_contract_smoke.py` memakai dua request maksimum:
satu generasi kandidat S1 berbasis koordinat black-box, lalu satu analisis
bukti dari paket P2 terkunci. Parser proyek memvalidasi kedua output.
Payload tidak dieksekusi ke DVWA dan label referensi tidak dimuat.

`development/run_poolside_p2_eval.py` menyiapkan 18 kasus dengan pesan dan
bukti asli yang sama, mengganti model menjadi Laguna S 2.1 dan menetapkan
thinking nonaktif. Profil Poolside memakai maksimum output 2048 token per
kasus dan timeout 60 detik, berbeda dari profil P2 Qwen yang timeout 90 detik
dan tidak mengatur thinking secara eksplisit. Tidak ada retry/fallback.

Periksa rencana secara offline sebelum membuat run baru:

```powershell
.\.venv\Scripts\python.exe development\run_poolside_contract_smoke.py --dry-run
.\.venv\Scripts\python.exe development\run_poolside_p2_eval.py --dry-run
```

Opsi `--run` mengeksekusi rencana dalam direktori baru; jangan memakainya
untuk sekadar membaca hasil. Log tersimpan di `results/raw/poolside-contract-smoke/`
dan `results/raw/poolside-p2/`. Runner P2 tidak membaca anotasi. Assessment
terhadap anotasi terkunci dilakukan setelah inferensi, melalui assessor P2
yang sudah ada, dengan path hasil dan anotasi yang disebut secara eksplisit.

Kasus lama yang digunakan kembali bukan holdout baru atau sampel tambahan
independen. Agreement dan coverage P2 bukan metrik formal FPR/PSR. Satu
kandidat generasi yang lolos parser juga belum membuktikan keberhasilan SQLi.

## Sumber resmi

- https://docs.poolside.ai/api/overview
- https://docs.poolside.ai/api/openai-api-examples

## Verifikasi offline

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_poolside_smoke.py -v
```
