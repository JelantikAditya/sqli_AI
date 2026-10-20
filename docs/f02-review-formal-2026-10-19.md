# F02: paket review formal dan audit kelayakan metrik

Tanggal: 19 Oktober 2026. Eksperimen: `formal-sqli-v1-20261017`.

Pembaruan setelah review: 990 anotasi terbaru VAL-01 sudah diterima dan diimpor.
PSR utama B/C sudah dihitung; FPR utama tetap undefined akibat abstention S10.
Hasil, riwayat revisi dan provenance ada di
[hasil VAL-01](f02-hasil-val01-2026-10-19.md).

Bagian di bawah merekam persiapan paket sebelum anotasi diterima. Pada tahap
persiapan tersebut, F01 sudah selesai untuk R1, R2, dan R3; anotasi manusia
independen belum tersedia. Paket yang digunakan adalah versi **v2** pada
`results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/`.
Versi v1 adalah keluaran persiapan terdahulu dan tidak digunakan untuk handoff.

## Dataset dan preservasi

Loader resmi memverifikasi pemilihan attempt final, hash batch, log validasi,
hasil adaptive, integritas event analisis, dan ringkasan keputusan run.

| Item | Hasil |
| --- | ---: |
| Slot terencana | 108 |
| Run completed | 99 |
| Slot C/Impossible excluded sesuai desain | 9 |
| Kandidat valid pada attempt final | 990 |
| Observasi baseline/payload/kontrol | 7.920 |
| Kandidat B/C S1-S9 untuk PSR utama | 540 |
| Anotasi formal diterima | 0 |

Setiap run completed memiliki 10 kandidat. Setiap kandidat memiliki tiga grup
konfirmasi lengkap beserta baseline dan pasangan kontrol sesuai teknik.
Pemeriksaan sebelum dan sesudah persiapan mencakup 959 file dan tidak menemukan
perubahan sumber. Prefix 273 event lama tetap sama; seluruh 542 file attempt
historis R1/R2 cocok dengan inventory preservasi. R1/R2 tidak dijalankan ulang.
Kedua belas receipt preflight B pada R3 juga cocok dengan hash ledger.

Checkpoint akhir memiliki nol unit invalid/running/planned/retried. Ledger tetap
menyimpan **10 attempt invalid historis**, yaitu tiga pada R1 dan tujuh pada R2.
Attempt tersebut tidak dipilih sebagai hasil akhir dan tidak dihapus. Nol invalid
pada checkpoint tidak berarti tidak pernah terjadi kegagalan runtime.

## Paket untuk VAL-01

Bagikan hanya `paket-validator.zip`, yang berisi:

- `packets.json`: 990 packet ber-ID acak, dengan bukti yang disanitasi.
- `annotations.csv`: 990 baris; identitas, keputusan, dan alasan masih kosong.
- `PETUNJUK.md`: arti field, tiga trial, kontrol, dan cara mengisi anotasi.

Kondisi, sumber kandidat, ground truth, klaim Qwen, keputusan executor, dan ID
run/attempt tidak dimasukkan ke metadata publik. Mapping dan laporan audit
berada di luar arsip validator. Seluruh observasi memiliki review excerpt.
Importer menolak template yang belum diisi; tidak ada keputusan manusia yang
dibuat otomatis atau diambil dari anotasi pilot.

Hash SHA-256 `packets.json`:
`be339b984d5a25e0d77eb6124f7dfea128d8b657272af020674103c41f504e6e`.

Exporter beku masih memakai string readiness `ready_for_pilot_review` untuk
semua paket yang excerpt-nya lengkap. Audit terpisah menetapkan paket ini
`ready_for_independent_formal_review` berdasarkan dataset formal yang tervalidasi.
Byte paket dan kode exporter tidak diubah untuk mengganti label tersebut.

## Hasil audit FPR

| Kondisi | Replikasi | FP | TN | Abstention | Coverage keputusan | FPR utama |
| --- | --- | ---: | ---: | --- | ---: | --- |
| A | R1 | 2 | 0 | S10 | 2/3 | undefined |
| A | R2 | 2 | 0 | S10 | 2/3 | undefined |
| A | R3 | 2 | 0 | S10 | 2/3 | undefined |
| B | R1 | 2 | 0 | S10 | 2/3 | undefined |
| B | R2 | 2 | 0 | S10 | 2/3 | undefined |
| B | R3 | 2 | 0 | S10 | 2/3 | undefined |

S10 (error-based, Impossible) berstatus `inconclusive` pada keenam run A/B.
Seluruhnya memiliki eksekusi dan analisis lengkap 10/10; status ini adalah
abstention model. S11 dan S12 memiliki keputusan sistem positive dan dicatat FP
terhadap ground truth negatif sesuai protokol.

Rasio pada subset yang sudah diputuskan adalah 100% dengan coverage 66,67% di
setiap kelompok. Rasio bersyarat ini hanya diagnostik. FPR utama serta mean/SD
tetap null karena satu kontrol negatif per kelompok tidak memiliki keputusan
biner. Tidak ada kesimpulan bahwa RAG menurunkan FPR.

Sesuai `keputusan-run-inconclusive-2026-10-14.md`, anotasi manusia tidak mengganti
klaim sistem, abstention tidak menjadi TN, dan run tidak diulang sampai memperoleh
keputusan biner. Anotasi VAL-01 nantinya dapat melengkapi PSR; FPR utama pada
dataset ini tetap undefined selama hasil asli dipertahankan.

## PSR dan kelanjutan

Agregator dijalankan dengan daftar anotasi kosong secara eksplisit, tanpa
membuat dokumen yang mengaku sebagai hasil validator. PSR per run, per skenario,
per replikasi, dan mean/SD ditahan sampai anotasi independen tersedia. Angka
keberhasilan executor belum menjadi PSR final.

VAL-01 perlu mengisi semua 990 baris dengan alias, `success`, `failure`, atau
`insufficient_evidence`, serta alasan berdasarkan observasi. Setelah CSV lengkap,
jalankan dari root proyek:

```powershell
.\.venv\Scripts\python.exe dvwa/blind_review.py import `
  --package-dir results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2 `
  --annotations results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/validator/annotations.csv `
  --validator-id VAL-01 `
  --output results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/annotations.imported.json

.\.venv\Scripts\python.exe dvwa/aggregate_metrics.py `
  --experiment-dir results/raw/formal/formal-sqli-v1-20261017 `
  --annotations results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/annotations.imported.json `
  --output results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/metrics.reviewed.json `
  --csv-output results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/metrics.reviewed.csv
```

Simpan CSV asli yang dikembalikan validator sebagai bukti. Jika lokasi CSV berbeda,
sesuaikan `--annotations`. Jangan membuka mapping kepada validator sebelum tahap
review selesai. Impor dan agregasi di atas belum dijalankan dengan anotasi manusia.

## Pemeriksaan

- 12 tes agregator dan 5 tes blind review lulus, termasuk penahanan FPR saat
  abstention, kebutuhan anotasi PSR, dan pemisahan metadata publik dari mapping.
- Evaluator FPR dan agregator resmi menghasilkan FP/TN serta eligibility sama.
- Arsip handoff hanya berisi tiga file publik; hash paket dan inventory disimpan.
- Tidak ada request ke DVWA, panggilan model, reset database, atau eksekusi ulang.

Artefak internal: `audit.private.json`, `source-inventory.private.json`,
`artifact-manifest.private.json`, `negative-run-audit.csv`,
`metrics.pending-review.json`, dan `metrics.pending-review.csv`.
Skrip reproduksi: `maintenance/prepare_formal_review.py`, dengan output baru di
`results/raw/`. Output dibuat eksklusif dan tidak menimpa paket yang sudah ada.
