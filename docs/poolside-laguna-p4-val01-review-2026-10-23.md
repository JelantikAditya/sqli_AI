# Paket review formal VAL-01 untuk P4 Poolside Laguna

Paket review blind baru untuk cohort formal P4 siap diserahkan kepada VAL-01.
Paket mencakup 990 kandidat dari 99 unit eligible: 66 unit R1/R2 yang
dipertahankan, 32 unit R3 lengkap, dan satu pengganti terarah B/S5/R3. Sembilan
slot C yang dikecualikan oleh desain dan sembilan kandidat dari unit parsial
yang digantikan tidak masuk penilaian.

## Pembaruan setelah review VAL-01

CSV yang dikembalikan VAL-01 telah lolos importer resmi untuk seluruh 990 ID.
Anotasi mencakup 417 `success` dan 573 `failure`. PSR eligible untuk kondisi B
dan C. FPR kondisi B eligible dengan nilai 0%; FPR kondisi A tertahan karena
replikasi 2 pada S12 berstatus `inconclusive`. Rincian hasil dan batas
interpretasinya ada di [laporan hasil VAL-01](hasil-val01-poolside-laguna-p4-2026-10-23.md).

Pembaruan terpisah setelah amandemen: analisis sensitivitas dengan unit
pengganti A/S12/R2 menghasilkan FPR A 0% pada matriks sensitivitas (n=3),
sementara hasil primer A VAL-01 tetap tertahan. Nilai ini tidak menggantikan
hasil primer dan PSR tidak dihitung ulang. Lihat [laporan sensitivitas](poolside-laguna-p4-a-s12-r2-sensitivity-result-2026-10-23.md)
untuk metode, bukti, dan batas interpretasinya.

Pada asesmen per-trial A2/S12, model memberi 2/3 negatif dan 1/3 positif,
sehingga keputusan skenario tetap `inconclusive` menurut aturan strict 3/3.
Pembacaan konservatif terpisah yang mengasumsikan abstention itu sebagai FP
menghasilkan FPR alternatif A 11,11% (SD sampel 19,25 poin persentase, n=3).
Ini bukan keluaran positif final yang diamati dan tidak mengubah FPR primer yang
tertahan menurut U05.

[Unduh ZIP untuk validator](<../results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01/paket-validator.zip>).
Bagikan hanya ZIP ini. Arsip berisi `packets.json`, `annotations.csv` kosong,
dan `PETUNJUK.md`. Jangan bagikan `mapping.private.json`, audit privat, manifest,
atau ledger sumber. ID review dan urutan packet dibuat baru untuk batch ini.

Paket menyajikan 7.920 observasi dengan excerpt allowlist yang disanitasi.
Kondisi eksperimen, sumber kandidat, model, ground truth, klaim analisis, dan
keputusan sistem tidak ada di file publik. Template mencakup 990 ID unik dan
awalnya belum berisi keputusan, alasan, atau identitas validator. Berkas asli
hasil review tetap disimpan oleh peneliti dan impor resmi ditautkan ke hash
packet ini.

SHA-256 `packets.json`:
`52fa92a88d28009504c2d68c70d08c5f117237bb171cf7dcfa314f44bd4fa51b`

SHA-256 ZIP:
`2e36371bfcfbc3af8262c7910c2130856c743e3674bb1a0ed72dc6bb19e19d45`

Pembuatan paket tidak mengirim request ke API atau DVWA dan tidak mereset
database. Receipt audit publik ada di
[`poolside-laguna-p4-val01-package-2026-10-23.json`](evidence/poolside-laguna-p4-val01-package-2026-10-23.json).
