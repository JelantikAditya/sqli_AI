# Audit kegagalan generasi Poolside P3

- **Tanggal:** 22 Oktober 2026
- **Cohort sumber:** `poolside-s21-p3-r1-20261022`
- **Status:** audit offline selesai; qualification v2 disiapkan, belum dijalankan

## Temuan

Replay offline memeriksa 296 respons generasi dari 24 unit A/B. Semua status
parser cocok dengan ledger, tidak ada hash request yang berbeda, dan inventaris
1.916 artefak cohort tetap sama. Replay mengirim 0 request ke API dan 0 request
ke DVWA.

| Unit parsial | Slot terakhir | Temuan pada tiga percobaan |
| --- | ---: | --- |
| A/S1 | 10 | Tiga respons JSON rusak identik; prompt retry 1 dan 2 juga identik. |
| B/S4 | 10 | Pola sama dengan A/S1. |
| A/S7 | 10 | Pola sama dengan A/S1. |
| A/S6 | 10 | Duplikat dari slot 9, satu kandidat melanggar aturan karena memuat dua SLEEP, lalu duplikat slot 9 lagi. Prompt retry 1 dan 2 identik. |
| B/S2 | 8 | Tiga usulan merupakan duplikat struktur dari kandidat yang diterima sebelumnya setelah angka dinormalisasi. |
| B/S11 | 6 | Tiga usulan duplikat dari slot terdahulu; dua memakai operator `>` walau family slot meminta `<`. |

Penyebab utamanya adalah retry tidak selalu membawa alasan format yang rinci,
prompt retry tertentu berulang, beberapa family berdekatan meminta bentuk yang
sama setelah normalisasi angka, dan parser tidak menggunakan respons invalid
sebagai umpan balik retry. Batas tiga request generasi per slot sudah bekerja;
perubahan ini tidak menambah jumlah retry atau melonggarkan parser maupun
kebijakan kandidat.

## Perubahan v2

`development/poolside_laguna_generation_v2.py` menyediakan prompt version dan
retry policy baru. Sepuluh family utama per teknik ditetapkan menurut nomor
slot dan dua family fallback dipilih secara deterministik pada retry. Kondisi
A dan B memakai jadwal family yang sama. Setiap retry mencantumkan indeks
percobaan, kode validasi, dan cuplikan respons sebelumnya maksimal 400 karakter
sebagai data tidak tepercaya. Parser tetap menolak JSON rusak, duplikat, dan
kandidat yang melanggar kebijakan. Tidak ada perbaikan otomatis terhadap JSON
atau penggantian payload oleh kode.

Plan qualification memuat kondisi A/B saja pada 12 skenario di empat level,
sehingga mencakup 24 unit LLM, 240 kandidat, dan 720 konfirmasi logis. Kondisi
SecLists tidak diperlukan untuk menilai perubahan generasi API. Plan dan budget
qualification disimpan terpisah di
`development/poolside_laguna_qualification_plan_20261022.json` dan
`development/poolside_laguna_qualification_budget_20261022.json`. Runner hanya
menerima ID baru `poolside-s21-p3-q1-20261022`, mempertahankan 10 kandidat,
maksimal tiga request generasi per slot, tiga konfirmasi, tanpa retry transport,
serta ceiling 960 request dan enam jam. Gate lulus memerlukan seluruh 24 unit
A/B menghasilkan 10 kandidat valid. Hasil qualification tetap terpisah dari P3
r1 dan tidak eligible sebagai data formal.

## Validasi offline

- Lima regression check v2 lulus menggunakan respons tiruan, termasuk JSON
  rusak, retry duplikat, normalisasi angka, serta kandidat time-based dengan dua
  SLEEP.
- Dry-run runner memvalidasi plan, hash 45 sumber runtime, kecocokan payload
  analisis P2 sebanyak 18 kasus, dan estimasi batas 960 request.
- Belum ada request API, reset database, atau pengujian target untuk cohort
  qualification. Keberhasilan v2 masih harus dibuktikan lewat cohort tersebut.

Rincian replay yang dapat direproduksi tersimpan di
`docs/evidence/poolside-p3-generation-audit-2026-10-22.json`. Rincian respons
dan artefak mentah tetap lokal di `results/raw/development/`.
