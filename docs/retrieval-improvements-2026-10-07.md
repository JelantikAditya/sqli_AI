# Perbaikan retrieval RAG lokal — 7 Oktober 2026

## Masalah dan perubahan

Retrieval S1 sebelumnya berhasil secara teknis, tetapi mengambil abstrak,
daftar pustaka, dan studi terkait. Tahap ini memperbaiki pemilihan konteks dari
referensi yang sudah tersedia sebelum menambah sumber.

| Masalah | Perbaikan |
| --- | --- |
| Query metadata skenario mengangkat materi umum | Query `sqli-technique-query-v2` berfokus pada teknik dan bukti respons; sama untuk semua level dalam satu teknik |
| Bibliografi dan metadata publikasi masuk konteks | Anotasi bagian PDF dan filter sebelum pemilihan konteks |
| Proposal memuat rancangan serta label ground truth | Seluruh chunk proposal dikecualikan dari konteks generator |
| Dense retrieval melewatkan uraian teknis | Pool 100 hasil semantik ditambah pencarian frasa teknis pada seluruh body korpus memakai embedding yang sudah ada |
| Kata SQL dan error pada kalimat terpisah dianggap bukti | Pencocokan frasa database error diperketat; skor memprioritaskan bukti teknik |
| Overlap menghabiskan ruang prompt | Dedup overlap shingle lima kata; threshold 0,40 |
| Top-k memaksakan materi umum | Skor minimum 6; kekurangan hasil dicatat sebagai `shortfall` |
| Seleksi sulit direproduksi | Log versi query, kebijakan lengkap, hash kode selector/anotasi, asal kandidat, skor, dan alasan penolakan |

Aturan ada di `dvwa/retrieval_policy.json`, implementasi di
`dvwa/retrieval_selection.py`. Bobot: penyebutan teknik 2, bukti utama 6,
pengamatan respons 1, indikasi validasi 1. Skor merupakan heuristik seleksi,
bukan probabilitas relevansi. Aturan berlaku umum, tidak memilih ID chunk
atau halaman tertentu secara manual.

## Korpus dan anotasi

Knowledge base tetap `sqli-kb-a7b087430b0276aa`: 15 PDF, 329 halaman,
1.950 chunk. Tahap ini tidak membangun ulang embedding atau mengubah teks
chunk. Hash seluruh 15 PDF cocok dengan manifest sesudah pengujian.

| Anotasi | Jumlah chunk |
| --- | ---: |
| Body, masih memerlukan seleksi relevansi | 1.447 |
| References | 377 |
| Campuran body dan references | 19 |
| Metadata publikasi/front matter | 14 |
| Proposal yang dikecualikan | 93 |

Sebanyak 503 chunk ditandai untuk dikecualikan. Anotasi heading/metadata
merupakan heuristik, bukan labeling manual seluruh korpus. Chunk yang gagal
dipetakan juga ditolak. Tidak ada SecLists atau hasil evaluasi baru yang
ditambahkan sebagai referensi generator.

Sidecar aktif:
`data/vectorstore/sqli-kb-a7b087430b0276aa/curation-6c6423c65b030ba7.json`.
Policy SHA-256:
`6c6423c65b030ba711740ad5fa9b922bb7befb24d0a006f2bdc035ec73dfe0af`.
Annotation SHA-256:
`2a8f9c5f1a9ce5e302cfbe69ea0a4e9461d00754bae233b5f133ad27a07cf5c5`.

## Perbandingan S1

Baseline: `results/raw/retrieval-S1-20261007T090400Z-eb31e3.json`.
Hasil akhir: `results/raw/retrieval-S1-20261007T094806Z-a1ebe7.json`.
Keduanya memakai index/model embedding sama dan top-k 5. Perbandingan ini
mengubah query, filter, ekspansi leksikal, ranking, dan dedup sekaligus;
bukan ablasi masing-masing komponen.

| Peringkat | Sebelum | Sesudah |
| --- | --- | --- |
| 1 | `gptsqli.pdf` hlm. 1: metadata penulis/abstrak umum | `SQLi.pdf` hlm. 4: observasi pesan error mesin SQL dan interpretasinya |
| 2 | `gptsqli.pdf` hlm. 17: daftar pustaka | `gptsqli.pdf` hlm. 12: keterbatasan menganggap database error sebagai keberhasilan injeksi dalam benchmark paper tersebut |
| 3 | `[8] 123_Automated+Penetration+Testing+Tools+(3).pdf` hlm. 8: studi terkait | `gptsqli.pdf` hlm. 11: awal pembahasan keterbatasan tersebut; paragraf berlanjut ke halaman berikutnya |
| 4 | `gptsqli.pdf` hlm. 1: pengantar black-box umum | Tidak diisi; tidak ada kandidat tambahan yang lolos |
| 5 | `[8] 123_Automated+Penetration+Testing+Tools+(3).pdf` hlm. 8: studi terkait/validasi umum | Tidak diisi; tidak ada kandidat tambahan yang lolos |

S1: 100 kandidat semantik + 23 tambahan leksikal, 3 terpilih, `shortfall: 2`.
Tidak ada bibliografi/proposal dalam konteks terpilih; satu kandidat overlap
ditolak. Dua hasil pertama lebih langsung terkait teknik/interpretasi bukti
daripada baseline. Hasil ketiga masih fragmen paragraf dan perlu diperiksa
saat menyusun konteks final. Kriteria benchmark paper tersebut tidak menjadi
ground truth atau kriteria universal untuk DVWA.

## Verifikasi dan batas kesiapan

- Enam unit test lulus: prioritas filter sumber/bagian, dedup/shortfall,
  query tanpa level/label, regresi frasa database error, pemulihan kandidat
  leksikal, provenance batch RAG-on/off, serta kompatibilitas batch lama.
- Uji integrasi S1/S2/S3 berhasil, masing-masing mengambil 3/5/5 chunk.
  Seluruh hasil memenuhi filter dan skor minimum. S2/S3 baru diperiksa secara
  teknis; kualitas keseluruhan konteksnya belum dinilai manual.
- Index sintetis dibuka dari proses baru, tetap berisi 3 dokumen dan hanya
  mengembalikan fixture error-based untuk query S1.
- Collection produksi tetap berisi 1.950 chunk; 15 hash PDF tidak berubah.
- Ringkasan audit: `outputs/rag-retrieval-review/verification-2026-10-07.json`.

Belum ada generasi batch, request SQLi baru ke DVWA, atau pengukuran FPR/PSR.
Perbaikan konteks S1 belum membuktikan penurunan FPR. Parameter dikembangkan
melalui review S1; bekukan konfigurasi setelah review ketiga teknik dan sebelum
evaluasi formal. Pertimbangkan chunking mengikuti paragraf/subbagian untuk
fragmen lintas halaman. Notebook Colab belum memakai selector baru; jangan
menggabungkan hasilnya sebagai satu konfigurasi dengan pipeline lokal sebelum
menyamakan kebijakan.

## Menjalankan ulang

Dari root proyek, dengan Ollama aktif dan dependensi `.venv` terpasang:

```powershell
# Index lama, atau setelah kebijakan/kode selector berubah.
.\.venv\Scripts\python.exe dvwa/retrieval_selection.py --manifest data/vectorstore/sqli-kb-a7b087430b0276aa/manifest.json
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S1 --manifest data/vectorstore/sqli-kb-a7b087430b0276aa/manifest.json --top-k 5

# Pembanding query dan retrieval lama, tanpa filter baru.
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S1 --manifest data/vectorstore/sqli-kb-a7b087430b0276aa/manifest.json --top-k 5 --retrieval-mode legacy
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Build baru membuat sidecar otomatis. Perubahan kebijakan/byte kode selector
mengubah policy hash. Retrieval menolak sidecar dengan identitas/hash yang
tidak sesuai. Generator lokal memakai seleksi baru secara default dan
mencatat provenance tersebut di batch serta audit lengkap. Field tambahan
opsional untuk batch lama; jika disediakan, RAG-on harus memiliki identitas
valid dan RAG-off harus menggunakan `null`.
