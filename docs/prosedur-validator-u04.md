# Prosedur validasi manusia U04

Status: draft prosedur untuk review pilot. Jangan gunakan untuk anotasi formal
sampai protokol dibekukan dan paket final tersedia.

## Identitas dan independensi

- Alias validator yang dicatat peneliti: `VAL-01`.
- Ketersediaan validator independen telah dikonfirmasi peneliti pada 14 Oktober
  2026.
- Peneliti mengonfirmasi VAL-01 memahami SQLi dan tidak terlibat dalam
  pengembangan sistem pada 14 Oktober 2026. Catatan ini memakai alias saja;
  jangan mencantumkan nama pribadi di artefak repo.

## Isi paket dan blind

Paket publik berada di subfolder `validator/` di dalam direktori eksperimen lokal.
File `mapping.private.json` berada satu tingkat di atas folder tersebut dan
tidak boleh dibagikan kepada validator. Paket memuat ID acak, teknik, titik
injeksi, kandidat, baseline dan tiga konfirmasi. Kondisi A/B/C, sumber kandidat,
ground truth, klaim Qwen, serta keputusan executor tetap berada di mapping atau
ledger internal.

`review_excerpt` adalah teks normalisasi dari frasa allowlist, bukan potongan
HTML mentah. Field `review_excerpt_basis` menjelaskan apakah normalisasi dibuat
saat capture respons atau dirender dari marker allowlist yang sudah tersimpan
pada log lama. Cuplikan turunan marker bukan kutipan body asli. Cuplikan dapat
menampilkan diagnostik SQL umum, marker boolean, dan marker record benign dengan
nilai dinamis disamarkan. Paket juga memberi status
HTTP, waktu, hash respons, diagnostik ternormalisasi dan content marker. Tidak
ada body respons, cookie, token, nilai record, nama kolom dinamis, atau query
mentah. Paket tanpa excerpt atau marker allowlist pada satu atau lebih observasi
diberi status `incomplete_legacy_missing_excerpts` dan belum boleh direview.
Paket pilot saat ini ada di
`results/raw/u04-validator-pilot-20261014/validator/`. Bagikan hanya isi folder
`validator/`; file `mapping.private.json` adalah rahasia peneliti.

## Form anotasi

Validator mengisi satu baris untuk setiap `review_id` pada `annotations.csv`:

- `validator_id`: gunakan alias `VAL-01`.
- `decision`: pilih `success`, `failure`, atau `insufficient_evidence`.
- `justification`: jelaskan bukti yang terlihat, termasuk trial yang mendukung
  keputusan atau alasan evidence belum cukup. Jangan menebak kondisi atau sumber.

Keputusan adalah penilaian manusia atas bukti kandidat dan konfirmasi. Itu tidak
mengganti klaim sistem atau ground truth evaluator. Jangan menghapus kandidat
hanya karena klaim sistem berbeda dari keputusan validator.

## Klarifikasi dan perbedaan pendapat

Sebelum anotasi formal, peneliti boleh menjawab pertanyaan tentang arti field,
status runtime, dan format bukti secara seragam untuk semua packet. Jangan
membuka kondisi atau ground truth saat klarifikasi. Simpan pertanyaan dan jawaban
bersama catatan prosedur.

Jika `VAL-01` menyatakan `insufficient_evidence`, pertahankan keputusan itu dan
catat alasan. Jangan meminta perubahan keputusan setelah membuka label. Jika
reviewer dan peneliti berbeda pendapat, simpan anotasi awal apa adanya dan
rekam adjudikasi terpisah setelah blind dibuka. Jika nanti ada validator kedua,
simpan kedua anotasi; jangan menimpa hasil pertama. Protokol formal harus
menentukan aturan agregasi sebelum data formal dibuka.

## Alur ekspor-impor

1. Ekspor paket ke direktori baru di `results/raw/`.
2. Periksa `review_readiness`, jumlah packet, field publik, cuplikan, ID acak,
   dan kebocoran kondisi pada nama file/metadata.
3. Salin hanya folder `validator/` untuk penilaian. Jangan sertakan mapping,
   manifest yang membuka label, atau ledger internal.
4. Setelah seluruh ID dianotasi, impor CSV menggunakan alias yang sama.
5. Verifikasi cakupan ID, keunikan ID, label, alasan, hash paket dan jumlah
   anotasi sebelum menyimpan hasil impor sebagai artefak lokal.

Tes pilot harus mencakup mixed evidence dan kandidat yang ditolak target walau
sesi valid. Paket pilot lama dapat dipakai untuk prosedur bila log menyimpan
marker allowlist; validator akan melihat basis marker tersebut dan bukan teks
respons asli.
