# Protokol review blind untuk eksperimen Qwen API

Tanggal: 20 Oktober 2026. Status: rancangan prosedur untuk versi eksperimen baru `qwen38-api-sqli-v2`. Pilot prompt khusus S1 dan S3 pada DVWA Low telah berjalan dengan satu request API per skenario dan tiga konfirmasi executor. Dua packet pilot telah dinilai VAL-01 dan anotasinya diimpor. Ini bukan run formal; belum ada run API formal. Data dan anotasi formal terdahulu tidak diubah.

## Keputusan penilaian

Pertahankan kriteria inti pada panduan VAL-01 untuk menilai keberhasilan kandidat SQLi yang dipakai dalam PSR. Satu packet adalah satu kandidat logis. Boolean true/false tetap satu kandidat; keberhasilan memerlukan tiga trial yang semuanya memenuhi indikator teknik. Kriteria rinci error-based, boolean-based blind, time-based blind, kelengkapan bukti, dan `insufficient_evidence` tetap mengacu pada panduan VAL-01.

Yang digunakan kembali adalah **aturan penilaian**, bukan CSV, review ID, atau label dari eksperimen lama. Setiap ekspor untuk eksperimen API memakai review ID acak baru, urutan acak, dan packet baru dari bukti executor API. Anotasi lama tidak dipakai sebagai label kandidat API.

## Kesesuaian format packet

Eksportir `dvwa/blind_review.py` saat ini membuat packet publik dengan field:

```text
review_id, technique, injection_point, candidate, observations
```

Observasi menyediakan `trial`, `role`, `http_status`, `elapsed_ms`, `response_sha256`, `review_excerpt`, `review_excerpt_basis`, `diagnostics`, dan `content_markers`. Kriteria VAL-01 sudah memakai field tersebut. Eksportir tidak menampilkan kondisi A/B/C, sumber kandidat, ground truth, ID run, atau keputusan sistem pada packet publik. Pemetaan review ID ke run dan kondisi disimpan dalam `mapping.private.json` di direktori lokal privat.

Karena itu, untuk shape bukti yang sama **tidak diperlukan perubahan kriteria**. Setelah pilot API pertama menghasilkan bukti executor, lakukan pemeriksaan kompatibilitas sebelum mengekspor packet. Bila nama role, field, atau arti marker berubah, buat panduan tambahan dengan nomor versi baru dan uji pemetaan setiap field sebelum review. Jangan menebak bahwa format sudah kompatibel hanya dari respons API; yang dinilai validator adalah observasi DVWA yang dihasilkan executor.

## Prosedur untuk run API

1. Gunakan experiment ID baru `qwen38-api-sqli-v2`; jangan menambahkan run API ke ledger eksperimen Qwen lokal lama.
2. Sebelum run formal, selesaikan gate integrasi generasi dan analisis respons pada S1-S3. Pilot S1 dan S3 terbaru menunjukkan kandidat dapat diuji executor pada DVWA Low, tetapi belum membuktikan pipeline analisis penuh, seluruh teknik, level Medium/High/Impossible, atau kondisi A/B/C.
3. Setelah satu blok run selesai dan final selected attempts-nya dibekukan, muat run melalui loader eksperimen resmi. Ekspor packet blok itu ke direktori baru yang unik di `results/raw/formal-review/` memakai `blind_review.export_runs`. Simpan manifest privat berisi run ID yang tercakup agar run tidak diekspor dua kali ke batch berbeda.
4. Audit setiap batch: jumlah packet, keunikan review ID, urutan acak, cakupan trial dan role, kelengkapan cuplikan, serta pemisahan berkas publik dan mapping privat. Pastikan metadata model, kondisi, sumber, klaim analisis, ground truth, dan keputusan sistem tidak bocor ke packet. Setelah semua batch selesai, rekonsiliasi gabungan ke daftar run formal dan pastikan tidak ada run yang hilang atau ganda.
5. Berikan packet baru kepada validator dengan panduan VAL-01. Validator menilai dari bukti yang disajikan tanpa mengetahui kondisi atau sumber kandidat. `validator_id` menunjukkan identitas penilai, sedangkan `review_id` mengidentifikasi packet baru; keduanya tidak boleh disamakan.
6. Impor anotasi baru setelah semua ID tertutup tepat satu kali dan keputusan serta alasan lengkap. Hash packet dan CSV as-received disimpan untuk audit.

Rancangan formal memiliki 99 run selesai dan sepuluh kandidat per run, sehingga eksportir menyiapkan 990 packet bila seluruh run eligible. PSR utama memakai kandidat valid pada B dan C untuk S1-S9, sebanyak 540 kandidat. Kandidat A dapat tetap dinilai dan dilaporkan sebagai analisis tambahan yang telah ditetapkan sebelumnya. Ekspor per blok memungkinkan validator mulai menilai packet yang sudah final sambil blok eksperimen lain berjalan.

## Batas hubungan dengan FPR

Anotasi `success`, `failure`, dan `insufficient_evidence` menilai efektivitas kandidat untuk PSR. FPR dihitung terpisah dari keputusan biner sistem pada skenario negatif Impossible di kondisi API A/B. Jangan mengubah penilaian efektivitas payload menjadi label positif/negatif sistem, dan jangan memakai anotasi lama VAL-01 untuk mengisi keputusan API.

## Risiko penilai dan mitigasi

Jika orang yang sama menjadi validator lagi, pertahankan identitas validator internal yang sama sesuai catatan penerimaan, tetapi gunakan packet ID, urutan, dan bukti baru. Menyamarkan kondisi serta sumber membantu mengurangi bias. Karena satu validator saja tidak mengukur kesepakatan antarpenilai, hasil harus dilaporkan sebagai validasi oleh satu penilai independen, bukan reliabilitas antarpenilai. Bila tersedia penilai kedua tanpa mengganggu tenggat, subset yang ditentukan sebelum review dapat dipakai untuk mengukur agreement; jangan menambah atau memilih subset setelah melihat hasil.

Keterbatasan bukti yang sudah ada tetap berlaku: validator melihat marker dan cuplikan allowlist tersanitasi, bukan HTML mentah. Interpretasi dibatasi pada bukti yang disediakan dan kriteria operasional proyek, termasuk ambang timing 1500 ms.
