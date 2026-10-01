# Validasi ground truth DVWA — 1 Oktober 2026

## Lingkungan dan metode

- Target: instance DVWA lokal di Docker, `127.0.0.1:4280`.
- Akses: sesi login DVWA; level keamanan disetel dan diverifikasi pada sesi untuk setiap run.
- Database sampel diinisialisasi melalui halaman setup sebelum uji karena login awal ditolak.
- Cakupan tetap SQLi error-based, boolean-based blind, dan time-based blind. Tidak ada active scan ZAP; request uji dikirim terbatas melalui klien HTTP ke dua modul SQLi lokal.
- Setiap skenario diuji tiga kali. Kontrol benign `id=1` menghasilkan record pada ketiga replikasi di setiap level.
- Sinyal error: respons menampilkan exception/sintaks SQL dari database.
- Sinyal boolean: kondisi true menghasilkan “User ID exists”, kondisi false menghasilkan “User ID is MISSING”.
- Sinyal waktu: selisih terhadap request baseline `id=1` sekurang-kurangnya 1,5 detik dengan fungsi delay dua detik.

## Peta injection point per level

| Level | Modul error-based | Modul boolean/time blind |
| --- | --- | --- |
| Low | `GET /vulnerabilities/sqli/`, parameter `id` | `GET /vulnerabilities/sqli_blind/`, parameter `id` |
| Medium | `POST /vulnerabilities/sqli/`, parameter `id` (select) | `POST /vulnerabilities/sqli_blind/`, parameter `id` (select) |
| High | `POST /vulnerabilities/sqli/session-input.php`, field `id`; nilai dipakai oleh modul SQLi melalui state sesi | `POST /vulnerabilities/sqli_blind/cookie-input.php`, field `id`; nilai disimpan sebagai cookie `id` |
| Impossible | `GET /vulnerabilities/sqli/`, parameter `id` dan token form | `GET /vulnerabilities/sqli_blind/`, parameter `id` dan token form |

Di High, halaman modul menampilkan tautan popup untuk mengubah ID, bukan form langsung. Karena itu crawl ZAP tradisional yang sebelumnya dijalankan belum menemukan kedua helper tersebut; URL helper dipetakan dengan mengikuti kontrol UI DVWA dan memeriksa request/response.

## Hasil tiga replikasi per skenario

| Level | Error-based: sinyal SQL error | Boolean blind: true/false berbeda | Time blind: delay terukur | Ground truth |
| --- | ---: | ---: | ---: | --- |
| Low | 3/3 | 3/3 | 3/3, delta 2,00–2,03 dtk | Positif untuk tiga tipe |
| Medium | 3/3 | 3/3 | 3/3, delta 1,98–2,00 dtk | Positif untuk tiga tipe |
| High | 3/3 | 3/3 | 3/3, delta 2,00–2,01 dtk | Positif untuk tiga tipe |
| Impossible | 0/3 | 0/3 | 0/3, delta 0,00–0,02 dtk | Negatif untuk tiga tipe |

Medium menggunakan payload kondisi dan waktu numerik karena field `id` berupa select. Low dan High menggunakan bentuk kondisi bertanda kutip; pada High, nilai dikirim melalui helper popup. Pemilihan bentuk input menyesuaikan request aktual pada tiap level, bukan satu payload yang dipaksakan ke semua level.

## Interpretasi

Hasil ini mengonfirmasi 9 skenario positif S1–S9 dan 3 kontrol negatif S10–S12 pada instance DVWA yang diuji, masing-masing tiga replikasi. Ground truth ini menjadi label aktual untuk eksperimen berikutnya. Hasil tersebut tidak mengukur akurasi ZAP, LLM, atau RAG; sistem utama tetap perlu diuji terhadap label ini secara terpisah.

Untuk pengujian utama, ulangi validasi setelah setiap reset atau perubahan konfigurasi DVWA. Simpan raw response, cookie sesi, dan detail autentikasi secara lokal; samarkan sebelum berbagi.
