# Automation Penetration Testing SQL Injection dengan LLM dan RAG

Repositori implementasi tugas akhir untuk pengujian **DAST/black-box** pada
**DVWA**. Ruang lingkup penelitian adalah SQL injection error-based,
boolean-based blind, dan time-based blind pada level Low, Medium, High, serta
Impossible. Evaluasi utama membandingkan **FPR** sistem dengan/tanpa RAG dan
**PSR** payload LLM terhadap SecLists.

## Status

- Lingkungan DVWA dan MariaDB berjalan melalui Docker Compose.
- Empat level keamanan DVWA telah diuji melalui antarmuka web.
- Tunnel sementara bertoken tersedia untuk akses Colab selama eksperimen.
- Komponen ZAP, LLM, retrieval, validasi payload, dan pengukuran FPR/PSR
  masih dalam pengembangan mengikuti jadwal penelitian.

Petunjuk menjalankan lab ada di [dvwa/README.md](dvwa/README.md).

## Prinsip reproduksibilitas

- Gunakan hanya target DVWA milik sendiri pada lingkungan terkontrol.
- Catat image Docker, level keamanan, endpoint, jenis SQLi, konfigurasi
  RAG, sumber payload, seed, dan nomor pengulangan pada setiap percobaan.
- Simpan hasil agregat dan contoh log yang telah disanitasi dalam repositori.
  Simpan token, cookie, dump database, artefak mentah, model besar, serta PDF
  referensi di luar Git.
- Proposal dan artikel referensi dicantumkan sebagai sitasi bibliografis dalam
  paper, bukan disalin sebagai PDF ke repositori ini.
