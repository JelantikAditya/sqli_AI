# Qualification Poolside Laguna Q1, 22 Oktober 2026

## Keputusan

Qualification terpisah `poolside-s21-p3-q1-20261022` telah mengeksekusi semua
24 unit A/B. Hasilnya **gagal gate kelengkapan**: 19 unit mencapai 10 kandidat
valid, sedangkan 5 unit dikecualikan setelah anggaran generasi tidak terpenuhi.
Karena syaratnya setiap unit harus mencapai 10 kandidat, `qualification_passed`
dan `formal_eligible` bernilai `false`. Cohort ini tidak menghasilkan metrik
formal FPR atau PSR.

## Cakupan dan kelengkapan

| Kondisi | Unit lengkap | Unit excluded | Kandidat valid | Target kandidat |
| --- | ---: | ---: | ---: | ---: |
| A, tanpa RAG | 12/12 | 0 | 120 | 120 |
| B, dengan RAG | 7/12 | 5 | 109 | 120 |
| Total | 19/24 | 5 | 229 | 240 |

Unit yang tidak mencapai kuota adalah B/S4 (9/10), B/S7 (9/10), serta B/S8,
B/S11, dan B/S12 (masing-masing 7/10). Semua 12 unit kondisi A lengkap.
Kegagalan terkonsentrasi di kondisi B, tetapi hasil ini sendiri belum
membuktikan bahwa RAG menyebabkan masalah; hubungan antara konteks retrieval,
format keluaran, dan duplikasi kandidat perlu ditinjau.

Audit generasi menunjukkan respons pertama slot yang gagal pada B/S4 dan B/S7
tidak memenuhi format kandidat, lalu dua percobaan fallback tidak menghasilkan
kandidat valid yang berbeda. Pada B/S8, B/S11, dan B/S12, slot akhir kehabisan
hingga tiga percobaan tanpa kandidat valid yang unik. Retry untuk generasi
memang terjadi sesuai protokol. Penyebabnya bukan error transport.

## Layanan dan target lokal

- Laguna S 2.1 melaporkan model `poolside/laguna-s-2.1` pada semua 503 request.
- Seluruh 503 request menerima HTTP 200 dan status transport `ok`: 274 request
  generasi dan 229 request analisis. Tidak ada transport failure yang tercatat.
- Pemakaian tercatat 596.433 prompt token dan 68.038 completion token, total
  664.471 token. Latensi kumulatif respons API 2.539,545 detik; median 4,43
  detik per request.
- Runner melakukan 24 reset database DVWA lokal dan 5.010 request HTTP ke
  target. Ini adalah hasil qualification generasi, bukan pengukuran FPR/PSR.

## Batas interpretasi dan tindak lanjut

Qualification ini hanya menguji kelengkapan generasi pada 12 skenario A/B
dengan satu replikasi. Hasil kandidat atau keputusan sistem pada unit lengkap
tidak divalidasi manual buta dan tidak boleh diperlakukan sebagai dataset
formal. Data Q1 juga tidak digabung dengan pilot Poolside sebelumnya, Qwen,
atau hasil model lokal.

Sebelum P4 formal, telaah event generasi pada lima unit excluded, khususnya
perbedaan antara kondisi A dan B. Jika profil prompt atau strategi fallback
diubah, bekukan perubahan dan buat ID qualification baru. Ulangi gate dengan
seluruh 24 unit pada profil yang sama sebelum menyusun budget tiga replikasi
formal. Jangan mengisi slot yang gagal secara retroaktif atau menggabungkan
Q1 dengan cohort baru.

## Artefak

- Assessment mesin: `results/raw/pilot/poolside-s21-p3-q1-20261022/qualification-assessment.json`
- Ledger dan checkpoint: direktori raw yang sama, diabaikan Git.
- Ringkasan metadata yang aman untuk Git: [evidence Q1](evidence/poolside-laguna-qualification-q1-2026-10-22.json).
- Plan yang dipin: [plan qualification](../development/poolside_laguna_qualification_plan_20261022.json).

Konten kandidat, prompt, respons mentah, kredensial API, dan artefak target
tetap berada di `results/raw/` lokal dan tidak dimasukkan ke laporan ini.
