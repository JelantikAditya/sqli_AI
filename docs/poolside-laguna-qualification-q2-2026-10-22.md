# Qualification Poolside Laguna Q2, RAG tanpa contoh payload, 22 Oktober 2026

## Keputusan

Qualification `poolside-s21-p3-q2-20261022` telah menjalankan semua 24 unit
A/B. Hasilnya **gagal gate kelengkapan**: 21 unit mencapai kuota 10 kandidat,
sedangkan tiga unit B dikecualikan. `qualification_passed` dan
`formal_eligible` bernilai `false`. Cohort ini tidak menghasilkan metrik formal
FPR atau PSR.

## Profil yang diuji

Kondisi A tetap tanpa retrieval. Kondisi B tetap mengambil dua chunk per unit
dari indeks Chroma yang sama dengan Q1, tetapi projection sebelum prompt
menghapus field `payload_examples`. Field konseptual lain, seperti teknik,
semantik, metode deteksi, keterbatasan, dan mitigasi, tetap tersedia. Korpus,
indeks, query, top-k, generator Laguna S 2.1, retry, parser, kebijakan kandidat,
dan profil analisis P2 tidak diubah.

- Experiment ID: `poolside-s21-p3-q2-20261022`.
- Protocol ID: `poolside-laguna-s21-sqli-v3-qualification-no-examples`.
- Prompt version: `poolside-laguna-sqli-generation-v3-rag-no-payload-examples`.
- Retrieval projection: `structured-chunks-remove-payload-examples-v1`.
- Plan: [plan Q2](../development/poolside_laguna_qualification_plan_20261022_v2.json).
- Budget: [budget Q2](../development/poolside_laguna_qualification_budget_20261022_v2.json).

Plan mempertahankan 12 skenario, dua kondisi, satu replikasi, 10 kandidat per
unit, tiga konfirmasi, tanpa retry transport atau penggantian otomatis, ceiling
960 request API, dan batas waktu enam jam.

## Kelengkapan

| Kondisi | Unit lengkap | Unit excluded | Kandidat valid | Target kandidat |
| --- | ---: | ---: | ---: | ---: |
| A, tanpa RAG | 12/12 | 0 | 120 | 120 |
| B, RAG tanpa contoh payload | 9/12 | 3 | 115 | 120 |
| Total | 21/24 | 3 | 235 | 240 |

Unit excluded adalah B/S7 dan B/S10, masing-masing 9/10, serta B/S11, 7/10.
Pada S7 dan S10, respons utama slot terakhir berformat JSON tidak valid, lalu
dua fallback tidak menghasilkan kandidat valid yang berbeda. B/S11 mengalami
enam percobaan berstatus `no_valid_distinct_candidate` pada beberapa slot.
Tidak ada unit yang dikeluarkan akibat error transport.

## Audit request dan generasi

Semua **138 dari 138 request generasi B** diperiksa dari berkas request yang
benar-benar dikirim. Masing-masing tetap memuat dua chunk, tetapi tidak satu
pun memuat field atau teks `payload_examples`. Panjang teks chunk setelah
projection berkisar 948 sampai 1.038 karakter, di bawah batas 1.800 karakter.

| Indikator generasi | A, tanpa RAG | B, RAG tanpa contoh payload |
| --- | ---: | ---: |
| Percobaan generasi | 131 | 138 |
| Kandidat yang diterima | 120 | 115 |
| Respons kandidat berformat tidak valid | 4 | 3 |
| Percobaan `no_valid_distinct_candidate` | 7 | 20 |
| Rata-rata token prompt per request generasi, termasuk retry | 779,3 | 1.283,9 |
| Median token prompt per request generasi | 816 | 1.304,5 |

Seluruh 504 request API berhasil dengan HTTP 200 dan model yang dilaporkan tetap
`poolside/laguna-s-2.1`: 269 request generasi dan 235 request analisis. Total
pemakaian adalah 557.974 prompt token, 69.233 completion token, dan 627.207
token keseluruhan. Median latensi API 4,425 detik per request. Gate ini hanya
mengukur kelengkapan generasi, bukan akurasi deteksi.

## Perbandingan deskriptif dengan Q1

| Indikator | Q1, B dengan contoh payload | Q2, B tanpa contoh payload |
| --- | ---: | ---: |
| Unit B lengkap | 7/12 | 9/12 |
| Kandidat B valid | 109/120 | 115/120 |
| `no_valid_distinct_candidate` pada B | 29 | 20 |
| Rata-rata token prompt generasi B | 1.565,5 | 1.283,9 |

Tiga skenario B yang sebelumnya belum lengkap menjadi lengkap pada Q2, yaitu
S4, S8, dan S12. S10 berubah dari lengkap menjadi tidak lengkap; S7 dan S11
tetap tidak lengkap. Uji eksak McNemar dua sisi pada empat pasangan skenario
yang berubah menghasilkan `p = 0,625`. Kedua cohort hanya satu replikasi dan
tidak menggunakan seed API yang mengendalikan generasi, sehingga perubahan ini
bersifat deskriptif, bukan bukti bahwa penghapusan contoh menyebabkan
perbaikan. Pengurangan token prompt B sekitar 18% konsisten dengan field contoh
yang dihapus, tetapi kualitas deteksi belum diuji.

## Batas interpretasi dan tindak lanjut

Penghapusan `payload_examples` mengurangi panjang prompt B dan disertai
kelengkapan generasi yang lebih tinggi dibanding Q1, tetapi gate 24/24 masih
gagal. Kegagalan yang tersisa berkaitan dengan format dan keragaman kandidat,
bukan kegagalan provider. Hasil ini tidak boleh digabung dengan Q1, pilot r1,
Qwen, atau data model lokal dan tidak boleh disebut hasil formal.

Sebelum P4, tinjau event generasi dan kebijakan keunikan untuk B/S7, B/S10, dan
B/S11. Jika generator atau retry diubah, bekukan profil serta budget baru dan
gunakan ID qualification baru. Jangan mengulang hanya tiga unit gagal atau
mengisi slot Q2 secara retroaktif. Validasi buta dan penghitungan FPR/PSR belum
dilakukan.

## Artefak

- Assessment mesin: `results/raw/pilot/poolside-s21-p3-q2-20261022/qualification-assessment.json`
- Ledger dan checkpoint: direktori raw yang sama, diabaikan Git.
- Evidence ringkas yang aman untuk Git: [evidence Q2](evidence/poolside-laguna-qualification-q2-2026-10-22.json).
- Runtime, request, respons, dan salinan sumber: direktori raw lokal yang sama.

Konten kandidat, request mentah, respons model, kredensial API, dan artefak
target tidak dimasukkan ke laporan ini.
