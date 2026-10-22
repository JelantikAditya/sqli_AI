# Paket validasi manual buta P3, 22 Oktober 2026

Paket untuk validator VAL-01 siap digunakan. Paket publik memuat **270 kandidat** dari 27 unit yang lengkap. Setiap kandidat memiliki tiga trial dan bukti respons DVWA yang disanitasi. Enam unit parsial dan tiga slot yang dikecualikan oleh desain tidak masuk paket.

[Unduh ZIP untuk validator](<../results/raw/pilot-review/poolside-s21-p3-r1-20261022-batch01/review-paket-20261022-batch01.zip>)

Bagikan hanya ZIP tersebut. Isinya terdiri dari `packets.json`, `annotations.csv` yang masih kosong, dan `PETUNJUK.md`. Kondisi eksperimen, sumber kandidat, identitas model, ground truth, klaim analisis, serta keputusan sistem tidak disertakan. Mapping privat tersimpan terpisah di direktori kerja dan jangan dibagikan.

Packet mengikuti kriteria VAL-01: error-based dibandingkan dengan baseline, boolean-based memakai true dan false condition, dan time-based dibandingkan dengan kontrol tanpa delay memakai ambang 1.500 ms. ID review baru dan urutan acak digunakan untuk batch ini.

Validasi paket memastikan 270 ID unik, 2.190 observasi lengkap, semua cuplikan tersedia, dan tidak ada metadata sumber atau kondisi pada packet publik. Importer menolak lembar anotasi yang masih kosong. Persiapan paket tidak mengirim request ke API atau DVWA. Metrik FPR dan PSR tetap ditahan sampai anotasi manusia lengkap dan diperiksa.

Checksum SHA-256 `packets.json`: `397e627fec4621e3ea40f3e22d993e0ff047f2ab12fcc093bbdab2e5ab50b6e8`

Checksum SHA-256 ZIP: `ed5f0fe29c61cc5f0737e30bb82512fbba56a56fd18d40af89f3ca198ef87450`
