# Uji lokal Bonsai 2 9B, 22 Oktober 2026

**Hasil:** model berhasil dijalankan dengan akselerasi GPU pada laptop penelitian.
Kelayakan perangkat terbukti pada smoke test ini; kelayakan analisis SQLi belum
lolos seluruh pemeriksaan. Ini bukan P2 lengkap atau hasil FPR/PSR formal.

## Instalasi yang dipin

- GPU: NVIDIA GeForce RTX 3050 Laptop GPU, VRAM 4.096 MiB, driver 577.00.
- CPU: Intel Core i5-11400H, 6 core/12 logical processor; RAM 15,73 GiB.
- Model: `prism-ml/Ternary-Bonsai-2-9B-gguf`.
- Revisi model: `5b2abb02362efbed46bbe204014b02837778b2c2`.
- Berkas: `Ternary-Bonsai-2-9B-PTQ1_0.gguf`, 1.997.486.976 byte.
- SHA256 model: `3561df7ac7d26a71ffa991ac2db740b10841c3a350aa2676ccd3ff5d428b4e8b`.
- Runtime: PrismML llama.cpp `prism-b10787-73bfe6c`, Windows x64 CUDA 12.4.
- Versi executable teramati: build 10787, commit `73bfe6cc4`, MSVC 19.44.35229.0.
- Ketiga unduhan, yaitu model, runtime dan CUDA DLL, lolos ukuran dan SHA256
  sebelum executable dijalankan. Checksum berasal dari metadata LFS Hugging Face
  dan metadata aset GitHub release.

Model, arsip dan executable disimpan di `models/bonsai2-9b/`, yang sudah
dikecualikan dari Git. Tidak ada instalasi paket sistem, perubahan Ollama,
permintaan API berbayar, atau request DVWA. Server smoke dihentikan setelah
masing-masing pengujian; model tetap tersimpan untuk dipakai kembali.

## Profil dan batas pengujian

Keduanya memakai teks saja, tanpa vision projector atau speculative decoding,
context 4.096 token, satu slot, `-ngl 99`, Flash Attention aktif, batch 256,
microbatch 128, enam thread, dan seed 42. Endpoint terikat pada loopback
`http://127.0.0.1:18089/v1`.

| Parameter | Non-thinking | Bounded-thinking |
| --- | ---: | ---: |
| Temperature | 0,7 | 1,0 |
| Top-p | 0,8 | 0,95 |
| Top-k | 20 | 20 |
| Min-p | 0 | 0 |
| Presence penalty | 1,5 | 1,0 |
| Repeat penalty/window | 1,0 / 64 | 1,0 / 64 |
| Thinking | Nonaktif | Aktif, budget 1.024 token |
| Maksimum output kasus SQLi | 1.536 token | 2.048 token |

Sampling mengikuti profil small-model pengembang. Karena beberapa parameter
berubah bersamaan, hasil ini bukan isolasi pengaruh thinking saja.

Setiap profil mengirim empat request: satu JSON readiness tanpa constraint dan
tiga fixture SQLi sintetis. Fixture SQLi memakai pesan/kontrak P2 yang sudah ada,
tanpa RAG, ditambah JSON Schema enforcement pada runtime lokal. Label referensi
tidak dikirim ke model. Referensinya berasal dari aturan sintetis pengembangan,
bukan anotasi manusia atau holdout independen. Tiga fixture yang sama dipakai
pada kedua profil, sehingga enam respons domain bukan enam sampel independen.

## Hasil terukur

| Pemeriksaan | Non-thinking | Bounded-thinking |
| --- | ---: | ---: |
| Model siap setelah startup | 3,559 detik | 2,542 detik |
| Respons JSON valid | 4/4 | 4/4 |
| Verdict akhir sesuai referensi sintetis | 1/3 | 2/3 |
| Lolos verdict, asesmen trial, referensi, dan kontrak sekaligus | 1/3 | 1/3 |
| Rata-rata waktu per analisis SQLi | 6,432 detik | 20,961 detik |
| Kecepatan decode analisis | 65,31-68,17 token/detik | 65,43-67,79 token/detik |
| Puncak pemakaian GPU teramati | 2.231 MiB | 2.371 MiB |
| Timeout / kehabisan VRAM | Tidak teramati | Tidak teramati |

Puncak VRAM merupakan pemakaian perangkat secara keseluruhan yang disampling
sekitar satu detik sekali, termasuk proses lain. Angka itu bukan jaminan peak
absolut atau batas aman untuk context/batch yang lebih besar. Kecepatan decode
dari timing server tidak sama dengan durasi end-to-end, terutama ketika thinking
menghasilkan token tambahan. Seluruh output selesai dengan `finish_reason=stop`.

### Kesalahan yang masih terlihat

1. **Error-based, tiga diagnostic positif:** kedua profil memberi verdict
   `inconclusive`, padahal setiap kandidat memiliki diagnostic SQL baru.
   Non-thinking juga tidak mencantumkan kedua sisi evidence pada asesmen trial
   sehingga parser menolaknya sebagai `missing-trial-evidence`.
2. **Boolean-based, marker kedua sisi sama:** kedua profil benar memberi
   `negative`, dengan asesmen dan referensi yang sesuai.
3. **Time-based mixed:** non-thinking keliru memberi `positive`.
   Bounded-thinking memberi `inconclusive` yang sesuai, tetapi salah menilai
   outcome salah satu trial. Verdict akhir yang sesuai tidak cukup untuk
   menyatakan seluruh analisis benar.

Struktur JSON yang valid pada kasus domain dibantu constrained decoding.
Kebenaran semantik tetap diuji terpisah. Output model tidak dikoreksi oleh audit.

## Menjalankan kembali

Jalankan dari root workspace menggunakan PowerShell:

```powershell
# Memverifikasi unduhan yang dipin; aset yang sudah valid digunakan kembali.
.\.venv\Scripts\python.exe development/setup_bonsai2_local.py

# Smoke baru menulis direktori hasil baru, lalu menghentikan server miliknya.
.\.venv\Scripts\python.exe development/run_bonsai2_local_smoke.py
.\.venv\Scripts\python.exe development/run_bonsai2_local_smoke.py --profile bounded-thinking

# Server lokal untuk pemakaian berikutnya; Ctrl+C menghentikannya.
.\.venv\Scripts\python.exe development/run_bonsai2_local_smoke.py --serve --profile bounded-thinking
```

Audit offline hasil yang sudah tersimpan:

```powershell
.\.venv\Scripts\python.exe development/audit_bonsai2_local_smoke.py `
  results/raw/development/bonsai2-9b-smoke-20261022T091829Z `
  results/raw/development/bonsai2-9b-smoke-20261022T092031Z `
  --output tmp/bonsai2-local-audit-recheck.json
```

## Keputusan dan langkah berikutnya

Instalasi dan uji runtime berhasil. Belum ada dasar untuk menutup P2 Bonsai atau
menjalankan P3/formal dengan asumsi kompetensi analisis sudah terpenuhi. Prioritas
berikutnya ialah diagnosis aturan diagnostic/error-based dan perbandingan timing
per trial, lalu evaluasi P2 model lokal dengan profil yang dibekukan. Hasil
pengembangan ini tidak digabung dengan cohort Qwen lokal atau Qwen API terdahulu.

Ringkasan dan hash raw tersedia dalam
[receipt audit](evidence/bonsai2-9b-local-smoke-2026-10-22.json).

Sumber runtime dan konfigurasi:
[model resmi](https://huggingface.co/prism-ml/Ternary-Bonsai-2-9B-gguf),
[format dan dukungan runtime](https://docs.prismml.com/download/formats),
[profil small-model](https://github.com/PrismML-Eng/Bonsai-demo/blob/main/SMALL-MODELS.md),
[runtime release](https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b10787-73bfe6c).
