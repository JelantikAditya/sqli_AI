# Diagnosis analisis SQLi dengan alias API Qwen3.8-27B

Tanggal: 20 Oktober 2026. **Cakupan hanya development sintetis**, menggunakan 36 kasus eligible dan enam input invalid dari pilot analisis v5 r2. Tidak ada request SQLi baru ke DVWA pada diagnosis ini. Label pembanding dibuat AI dan pernah digunakan untuk pengembangan, sehingga hasil bukan holdout independen, FPR formal, atau PSR formal.

## Prosedur dan provenance

Satu request analisis tanpa RAG dikirim per kasus eligible. Enam kasus invalid berhenti di input gate dan tidak dikirim. Permintaan berasal dari prompt A/no-RAG terkunci, lalu diadaptasi ke chat API dengan JSON Schema disertakan dalam system prompt karena dukungan schema server belum diverifikasi. Skema dan ID bukti diperiksa lagi secara lokal. Tidak ada retry, fallback model, atau koreksi verdict model. Identitas trial dan observasi rekaan ditolak secara struktural; klaim yang secara isi salah tetap disimpan apa adanya.

Rencana pertama yang memakai encoding JSON tidak kanonis ditinggalkan sebelum panggilan API. Rencana v2 menjalankan sembilan attempt dengan `max_tokens=1024`. Lima respons terpotong dan satu mendapat HTTP 504, sehingga rencana v3 memakai `max_tokens=2048` hanya untuk 27 kasus yang belum pernah dikirim. Checkpoint v3 memuat hash sembilan respons v2 dan melarang pengiriman ulang. Karena batas output berbeda, angka gabungan 36 kasus menggambarkan proses diagnosis ini, **bukan performa satu konfigurasi yang seragam**.

Raw request, respons, dan checkpoint ada pada `results/raw/development/qwen38-api-analysis-diagnosis-20261020-v2` dan `...-v3` yang sengaja dikecualikan dari Git. [Audit replay](../results/processed/qwen38-api-diagnosis-20261020/audit.json) menyimpan hash raw, menghitung ulang parse dan skor, serta memastikan 36 attempt dan enam skip. Verifikasi penuh memerlukan arsip raw lokal.

## Hasil

| Batas output | Attempt | Keputusan benar | Analysis error | Catatan |
| --- | ---: | ---: | ---: | --- |
| 1.024 token | 9 | 3 | 6 | 5 truncation, 1 HTTP 504 |
| 2.048 token | 27 | 23 | 3 | 1 truncation, 2 timeout |
| Total proses diagnosis | 36 | 26 | 9 | 1 keputusan valid salah |

Respons API `ok` ada 27 dan seluruhnya lolos pemeriksaan struktur lokal. Dari 27 respons valid itu, 26 verdict sesuai label sintetis. Pada seluruh 36 attempt, 26 verdict benar dan sembilan analysis error tetap berada dalam penyebut. Asesmen trial yang cocok dengan referensi adalah 72/102 trial terencana; pada respons valid saja 72/75. Tidak ditemukan trial atau ID observasi rekaan pada respons valid. Itu belum berarti pemahaman bukti model selalu benar.

Per teknik, verdict benar pada 6/12 error-based, 9/12 boolean-based blind, dan 11/12 time-based blind. Perbedaan ini terutama memuat distribusi kegagalan layanan dan batas output yang tidak merata, sehingga bukan perbandingan kemampuan teknik yang terkontrol. Satu klaim positif keliru pada referensi negatif ditemukan di `pilot-031`.

Pada `pilot-031`, ketiga trial memiliki kandidat minus kontrol 1.900 ms, melebihi ambang 1.500 ms. Namun marker kandidat adalah `user_id_exists` sedangkan marker kontrol `user_id_missing` pada tiap trial. Aturan time-based mensyaratkan marker pasangan cocok sebelum menganggap delay sebagai indikator. Model menyebut marker `exists/missing` valid, menilai ketiga trial positif, dan mengeluarkan verdict positif; referensi operasional menilai ketiganya negatif. Parser mempertahankan klaim keliru itu agar dapat diaudit.

Metadata 33 respons dengan envelope model melaporkan `self-dploy/Qwen3.8-27B`; satu HTTP 504 dan dua timeout tidak mempunyai metadata model. Nama tersebut adalah laporan gateway, bukan verifikasi independen bobot upstream. Total waktu panggilan yang tercatat 1.584,397 detik untuk 36 attempt, termasuk kegagalan. Audit menjumlahkan 43.246 prompt token, 37.865 completion token, dan 27.664 reasoning token menurut usage gateway; ketiga attempt tanpa envelope tidak memberi usage.

## Implikasi untuk pekerjaan berikutnya

1. Batas 2.048 token jauh lebih layak daripada 1.024 pada kasus ini, tetapi satu truncation masih terjadi. Tetapkan batas final dari pilot generasi dan analisis sebelum freeze formal; jangan menyesuaikannya setelah melihat hasil holdout.
2. Kasus marker tidak cocok perlu menjadi fixture regresi interpretasi, bukan diubah labelnya agar cocok dengan model. Perbaikan prompt atau parser harus memiliki versi baru dan diuji pada set development terpisah.
3. Dataset baru yang belum pernah dipakai untuk tuning memerlukan label independen sebelum inferensi bila akan disebut holdout. Diagnosis ini sendiri tidak mendukung klaim penurunan FPR akibat RAG.
