# Pemeriksaan isi salinan indeks B, 21 Oktober 2026

Status: **pemeriksaan selesai, keputusan peneliti masih diperlukan**. Snapshot aktif dan arsip yang disetujui diperiksa pada salinan terpisah. Salinan aktif stabil selama penyalinan, hash sebelum dan sesudah copy cocok, dan tidak ada file WAL/SHM tambahan. Arsip acuan cocok dengan hash receipt U07.

## Hasil isi

- Koleksi `sqli_knowledge` berisi 9 record pada kedua snapshot. Seluruh ID embedding dan ID entri sama.
- Dokumen dan metadata untuk semua 9 record cocok persis dengan hasil rekonstruksi `prepare_documents` dari korpus dan source lock yang hash-nya disetujui.
- Model pada manifest adalah `nomic-embed-text` dengan format `nomic-search-prefix-v1`. Koleksi memakai dimensi 768 dan jarak `cosine`. Knowledge base ID diturunkan ulang dari konfigurasi dan cocok.
- Vektor tersimpan cocok per ID antara snapshot aktif dan arsip. 9 dari 9 query menggunakan vektor tersimpan juga menghasilkan urutan dan jarak yang sama.
- Perbedaan SQLite hanya pada tabel `acquire_write`, dengan satu baris tambahan di snapshot aktif. Byte `data_level0.bin` tetap berbeda. Hasil pemeriksaan Chroma diambil dari salinan kerja sementara; Chroma menulis ulang beberapa file hanya pada salinan kerja itu.

Tidak ada model embedding, API, atau DVWA yang dipanggil. Indeks aktif sumber, salinan bukti, baseline lama, receipt, dan `sources/` tidak diubah. Perbedaan byte indeks tetap dicatat, bukan disamarkan.

Laporan ini menunjukkan kesesuaian record dan konfigurasi yang diperiksa, tetapi bukan receipt atau persetujuan untuk menjalankan pilot B. Persetujuan lama `approved-for-formal-use` tetap memiliki `formal_execution_approval: false`; receipt pilot baru hanya dapat dibuat setelah keputusan eksplisit peneliti.
