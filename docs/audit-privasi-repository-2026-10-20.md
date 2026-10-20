# Audit privasi sebelum publikasi repository

Tanggal pemeriksaan: 20 Oktober 2026.

Pemeriksaan ini mencakup snapshot branch kandidat terhadap `main` dan semua file yang akan masuk ke PR. Snapshot berisi 542 file terlacak, dengan 444 file berubah dari `main` (120.977 penambahan baris dan 233 penghapusan).

- Tidak ada file terlacak di `sources/`, `results/raw/`, `data/raw/`, atau `data/vectorstore/`. Isi `sources/` memang dikecualikan Git sesuai aturan proyek.
- Di `results/zap/`, hanya `.gitignore` yang terlacak. Capture HAR, log, dan hasil lokal yang mungkin berisi lalu lintas sesi diabaikan Git.
- `.venv`, file `.env`, dan artefak runtime lokal tidak masuk snapshot. Aturan ignore diperkuat untuk file environment dan format kunci privat/sertifikat umum.
- Pemindaian file teks dan isi arsip tidak menemukan pola umum API key, token GitHub, kredensial AWS, bearer token, private key PEM, email, atau cookie sesi. Pemindaian pola bukan bukti matematis bahwa semua bentuk rahasia sudah tidak ada.
- Dua CSV anotasi VAL-01 hanya berisi `review_id`, `validator_id`, `decision`, dan `justification`; identitas validator direpresentasikan sebagai `VAL-01`.
- Rujukan ke profil Windows lokal di dokumentasi dan skrip normalisasi diganti dengan path generik/argumen CLI.

Sebelum publikasi, tinjau ulang isi file yang memang dimaksudkan sebagai artefak penelitian, terutama anotasi anonim dan hasil respons model. Credential baru tidak boleh dimasukkan ke repository.
