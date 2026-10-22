# Smoke test AISUBS GPT Saver dan Luna

Status 22 Oktober 2026: smoke test dengan key lokal sudah dijalankan.
Daftar model menerima HTTP 200 dan memuat `gpt-6-luna`. Request chat
menerima HTTP 502 `upstream_error` dengan pesan `Upstream request failed`.
Akses generasi Luna belum berhasil diverifikasi. Ini cek koneksi, bukan
eksperimen SQLi atau hasil FPR/PSR. Konfigurasi dan hasil Qwen tetap terpisah.

## Hasil eksekusi awal

| Pemeriksaan | Hasil | Latensi |
| --- | --- | --- |
| `GET /v1/models` | HTTP 200, `gpt-6-luna` terdaftar | 1,057 detik |
| `POST /v1/chat/completions` | HTTP 502, `upstream_error` | 1,951 detik |

Total dua request, tanpa retry atau fallback. Belum ada respons model,
metadata model hasil generasi, atau data penggunaan token. Tidak ada dasar
untuk menyimpulkan kuota yang terpotong bernilai nol. Provider melaporkan
kegagalan upstream; penyebab teknis yang lebih spesifik belum diketahui.

[Receipt respons tersanitasi](../results/raw/aisubs-luna-smoke/20261022T093505377022Z.json)
menyimpan hasil kedua request. Delapan pemeriksaan offline sebelum eksekusi
lulus, termasuk batas request, penghentian ketika model tidak terdaftar,
penanganan error, penolakan redirect, dan redaksi key.

## Rencana yang dijalankan

1. Satu `GET https://api.aisubs.id/v1/models` dengan key AISUBS.
2. Jika dan hanya jika daftar itu memuat `gpt-6-luna`, satu
   `POST https://api.aisubs.id/v1/chat/completions` yang meminta `API_OK`.
3. Batas keluaran `max_completion_tokens=128`, `reasoning_effort=none`, tanpa
   streaming. Timeout daftar model 20 detik; timeout chat 60 detik.
4. Tidak ada retry atau fallback model. Error daftar model, Luna tidak
   terdaftar, error chat, metadata model berbeda, respons tidak selesai, dan
   isi tidak sesuai dilaporkan terpisah. Tidak ada request ke DVWA.

Parameter tersebut adalah permintaan ke gateway. Kepatuhan provider pada
parameter dan identitas model upstream tidak dapat dibuktikan hanya dari
metadata. Model yang tidak terdaftar belum tentu tidak dapat dipanggil;
smoke test ini berhenti agar tidak menebak alias.

## Memasukkan key secara lokal

Skrip membaca `AISUBS_API_KEY` dari environment terlebih dahulu, lalu satu
entri dengan nama yang sama pada `.env.aisubs.local` di root proyek.
File lokal itu sudah dicakup aturan ignore Git. Jangan gunakan key HCNSEC
untuk endpoint AISUBS.

Alternatif tanpa menyimpan key: jalankan dari terminal interaktif dengan
input tersembunyi. Dari root proyek di PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' '.\development\run_aisubs_luna_smoke.py' --run --prompt-key
```

Skrip tidak mencetak atau menyimpan nilai key. Body respons dan pesan error
disanitasi sebelum dicatat apabila provider menggemakan key tersebut.

## Persiapan tanpa jaringan

```powershell
& '.\.venv\Scripts\python.exe' '.\development\run_aisubs_luna_smoke.py' --dry-run
& '.\.venv\Scripts\python.exe' '.\development\run_aisubs_luna_smoke.py' --check-key
```

Setelah key tersedia secara lokal, eksekusi tanpa prompt:

```powershell
& '.\.venv\Scripts\python.exe' '.\development\run_aisubs_luna_smoke.py' --run
```

Setiap eksekusi dengan key membuat receipt baru di
`results/raw/aisubs-luna-smoke/`, yang sudah di-ignore Git. Receipt memuat
timestamp UTC, payload dan hash request chat, status HTTP, latensi, model
yang dilaporkan, penggunaan token, respons yang disanitasi, dan jumlah
request. Hasil ini belum mengukur kualitas generasi/analisis SQLi.

## Referensi

- [OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [OpenAI Chat Completions](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)
- [Dokumentasi AISUBS](https://aisubs.id/apisubs/docs)

Sebelum smoke test, Luna belum tercantum dalam daftar GPT Saver AISUBS pada
dokumentasi publik yang terbaca, dan daftar model tanpa key membalas
`API_KEY_REQUIRED`. Pemeriksaan terautentikasi di atas kemudian menemukan
Luna pada daftar model, tetapi pemanggilan generasinya gagal. Keberadaan
model dalam katalog belum membuktikan layanan inferensinya dapat dipakai.
