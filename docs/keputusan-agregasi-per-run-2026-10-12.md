# Keputusan agregasi metrik: per-run averaging

Tanggal: 12 Oktober 2026.
Dipilih oleh peneliti melalui chat proyek.
Status: bagian dari protokol pilot, bukan hasil eksperimen formal.

## Aturan utama

Setiap skenario-kondisi dijalankan melalui tiga pengulangan pipeline
independen. Hasil tiap pengulangan dipertahankan. Hitung metrik per replikasi,
kemudian ambil mean aritmetika dan standar deviasi sampel, ddof=1.

Tidak ada voting 3/3 atau majority vote antar-run untuk mengganti hasil dengan
satu label skenario. Sukses pada Run 1 dan gagal pada Run 2/3 tetap menjadi
tiga hasil berbeda. Konfirmasi respons di dalam satu run berbeda dari tiga
pengulangan pipeline; per-run averaging tidak menentukan aturan konfirmasi
internal tersebut. Aturan internal yang belum final tetap dicatat pending.

## Unit perhitungan

Konfigurasi memuat 99 condition-run: A/B masing-masing 12 skenario x tiga
replikasi, C sembilan skenario x tiga replikasi. Pada pelaporan per kondisi,
Run r berarti kelompok condition-run dengan nomor replikasi r yang sama,
bukan satu request HTTP.

Untuk kondisi dan kelompok skenario yang sama pada replikasi r:

`PSR_r = kandidat berhasil_r / kandidat valid dieksekusi_r`

`FPR_r = FP_r / (FP_r + TN_r)`

`mean(M) = (M_1 + M_2 + M_3) / 3`

`SD(M) = sqrt(sum((M_r - mean(M))^2) / (3 - 1))`

SD dilaporkan dalam satuan sama dengan metrik. Jika metrik ditampilkan sebagai
persen, SD dinyatakan dalam poin persentase.

### PSR

- Hitung per skenario-kondisi-replikasi untuk S1-S9, kemudian mean +/- SD
  antar tiga replikasi.
- Untuk ringkasan suatu kelompok, jumlahkan pembilang dan penyebut kandidat
  di dalam replikasi yang sama, kemudian mean antar-replikasi. Jangan mengganti
  ringkasan utama dengan pooling ketiga replikasi menjadi satu rasio.
- Satu pasangan boolean adalah satu kandidat. Pengukuran kontrol/konfirmasi
  merupakan evidence kandidat, bukan tambahan kandidat pada penyebut.
- PSR utama membandingkan B (RAG-on) dan C (SecLists). Hasil A dapat dicatat
  sebagai tambahan tanpa mengubah perbandingan utama.
- Keberhasilan error-based mengikuti diagnostik basis data eksplisit yang
  dipilih peneliti. Hasil final memakai anotasi validator yang terdokumentasi.

### FPR dan confusion matrix

- Tetapkan satu klaim akhir sistem per skenario-kondisi-replikasi. Rekam klaim
  sebelum review dan gunakan ground truth pada evaluator, bukan prompt model.
- Hitung TP, FP, TN, FN sebagai bilangan bulat pada masing-masing replikasi.
  Laporkan hitungan mentah dan mean/SD hitungan bila diperlukan. Mean hitungan
  dapat pecahan dan harus diberi label rata-rata, bukan jumlah kejadian aktual.
- FPR A/B keseluruhan memakai tiga kontrol negatif S10-S12 per replikasi;
  penyebutnya tiga jika seluruh unit valid dan lengkap. S1-S9 menyumbang
  TP/FN, bukan FP/TN.
- FPR per kelompok yang hanya berisi skenario positif, misalnya Low saja,
  tidak terdefinisi karena tidak ada FP+TN. Jangan mengisinya dengan 0%.
- FPR per teknik dapat memakai kontrol Impossible teknik yang sama. Cantumkan
  ukuran sampel; seluruh skenario berasal dari satu DVWA.

## Contoh perhitungan buatan

PSR suatu skenario dengan 10 kandidat per replikasi:

| Replikasi | Kandidat berhasil/valid | PSR |
| --- | --- | --- |
| 1 | 6/10 | 60% |
| 2 | 4/10 | 40% |
| 3 | 2/10 | 20% |

Ringkasan: mean PSR 40%, SD 20 poin persentase. Tidak ada vonis berhasil/gagal
tunggal berdasarkan berapa run yang sukses.

FPR suatu kondisi pada tiga kontrol negatif per replikasi:

| Replikasi | FP | TN | FPR |
| --- | ---: | ---: | ---: |
| 1 | 0 | 3 | 0% |
| 2 | 1 | 2 | 33,33% |
| 3 | 0 | 3 | 0% |

Ringkasan: mean FPR 11,11%, SD sekitar 19,25 poin persentase. Angka di kedua
tabel adalah ilustrasi, bukan hasil proyek.

## Runtime error, data tidak lengkap, dan penyebut nol

Timeout koneksi, kehilangan autentikasi, atau baseline invalid tidak otomatis
berarti payload gagal. Simpan sebagai masalah runtime, lalu pulihkan/ulang
menurut kebijakan attempt. Jika state tidak dapat dipastikan, ulangi run dari
reset sambil mempertahankan log attempt lama.

Request/session valid yang menunjukkan kandidat ditolak aplikasi atau tidak
memenuhi indikator dinilai sebagai kandidat gagal. Timeout yang belum dapat
dibedakan dari gangguan infrastruktur bukan bukti time-based SQLi.

Ringkasan formal untuk kelompok yang metriknya berlaku membutuhkan tiga
replikasi valid, lengkap, dan memiliki penyebut terdefinisi. Run dengan budget
kurang dicatat excluded dan dilaporkan. Jika ada replikasi belum lengkap,
jangan mengisi 0% atau diam-diam menghitung mean dua run sebagai hasil tiga run.
Tampilkan status incomplete; ringkasan eksploratif parsial harus berlabel
terpisah dan mencantumkan n_valid.

Untuk kelompok yang memang tidak memiliki penyebut menurut desain, hasil
tetap undefined meskipun semua run lengkap, misalnya FPR pada Low saja atau
PSR Impossible. N/A tidak diganti nol dan tidak dimasukkan ke mean.

Pada arah aktif proyek, pengujian dilakukan lokal. Contoh timeout ngrok yang
diberikan peneliti bukan konfigurasi yang sedang digunakan. Per-run averaging
tetap dipakai untuk mengukur variasi hasil pipeline lokal.

## Implementasi dan pekerjaan tersisa

Konfigurasi metrics kini menetapkan per-run-arithmetic-mean, stddev_ddof=1,
cross_run_success_vote=none, dan kebutuhan replikasi lengkap. Pemeriksa
protokol menolak konfigurasi yang bertentangan dengan kebijakan ini.

Agregator data eksperimen aktual belum diimplementasikan pada perubahan ini.
Runner, ledger, keputusan final per run, paket validator, dan agregator tetap
bagian T02-T06. Manifest/hasil lama tidak diubah, dan status formal tetap pilot.

Penjelasan peneliti menyebut Mereani & Shafie (2025) dan nomor sitasi yang
belum dipetakan dalam pesan. Dokumen ini mencatat keputusan metode; dukungan
bibliografis spesifik perlu dicocokkan dengan sumber asli saat naskah disusun.
