# Hasil cohort P3 Poolside, 22 Oktober 2026

Cohort `poolside-s21-p3-r1-20261022` selesai dijalankan pada DVWA lokal `http://127.0.0.1:4280` menggunakan model `poolside/laguna-s-2.1`. Waktu eksekusi 17:04:02 sampai 17:56:08 WIB, sekitar 52 menit.

## Hasil eksekusi

- Seluruh 36 slot cohort memperoleh status terminal: 27 selesai dan 9 dikecualikan.
- Dari 24 unit LLM A/B, 18 mencapai anggaran 10 kandidat valid. Enam unit parsial dikecualikan dari evaluasi karena gagal mengisi seluruh anggaran.
- Kondisi C selesai pada S1 sampai S9, sebanyak 90 kandidat dari SecLists. Tiga slot C untuk S10 sampai S12 dikecualikan sesuai desain karena skenario Impossible.

| Skenario | A: kandidat valid | B: kandidat valid |
|---|---:|---:|
| S1 | 9/10* | 10/10 |
| S2 | 10/10 | 7/10* |
| S3 | 10/10 | 10/10 |
| S4 | 10/10 | 9/10* |
| S5 | 10/10 | 10/10 |
| S6 | 9/10* | 10/10 |
| S7 | 9/10* | 10/10 |
| S8 | 10/10 | 10/10 |
| S9 | 10/10 | 10/10 |
| S10 | 10/10 | 10/10 |
| S11 | 10/10 | 5/10* |
| S12 | 10/10 | 10/10 |

Tanda `*` berarti anggaran unit tidak lengkap dan hasilnya tidak layak untuk metrik. Rinciannya: S1-A 9/10, S2-B 7/10, S4-B 9/10, S6-A 9/10, S7-A 9/10, dan S11-B 5/10. Tiga unit berhenti setelah tiga respons berformat kandidat yang tidak valid. Tiga unit lain kehabisan percobaan untuk mendapat kandidat yang cukup berbeda atau lolos kebijakan. Di semua unit ini, respons HTTP provider tetap 200.

## Kesehatan API dan target

- Poolside menerima 524 panggilan: 296 generasi dan 228 analisis. Seluruhnya HTTP 200, status transport `ok`, dan melaporkan model yang sama.
- Tidak ada error layanan atau retry transport. Semua berkas panggilan memiliki `request.json`, `request-started.json`, dan `result.json`. SHA-256 payload cocok di catatan request dan response untuk seluruh panggilan. Profil parameter sesuai anggaran: temperatur 0, thinking nonaktif, token maksimum 1.024 untuk generasi dan 2.048 untuk analisis.
- Pemakaian token tercatat 613,353 prompt dan 68,552 completion, total 681,905. Waktu kumulatif yang dilaporkan API 2440.5 detik.
- Runner melakukan 33 reset database DVWA dan mencatat 7,026 request HTTP ke target lokal.

## Integritas dan batas interpretasi

Hash audit cocok untuk semua 3568 file yang sudah ada sebelum cohort: tidak ada file yang hilang atau berubah. Setiap hash file `adaptive-generation-audit.json` juga cocok dengan ledger cohort.

Hasil ini menunjukkan konektivitas Poolside stabil selama cohort P3. Hambatan yang terlihat ada pada format dan keragaman kandidat, sehingga enam unit tidak dapat masuk ke evaluasi penuh. Ini satu cohort pilot, jadi hasilnya belum membuktikan keunggulan model atau menyelesaikan evaluasi tesis. Metrik FPR dan PSR belum dihitung; kandidat dan keputusan sistem masih perlu validasi manual buta sesuai protokol.

Data mentah dan ledger: `results/raw/pilot/poolside-s21-p3-r1-20261022/`. Rincian audit mesin ada di `docs/evidence/poolside-p3-execution-audit-2026-10-22.json`.
