# Qualification Laguna Q4 v5

Tanggal: 2026-10-23  
Status: qualification live selesai dan gate lulus; belum eligible untuk data formal

## Paket yang dijalankan

- Experiment ID: `poolside-s21-p3-q4-v5-20261023`.
- Protocol ID: `poolside-laguna-s21-sqli-v5-qualification-structure-feedback`.
- Profil generasi: `poolside-laguna-sqli-generation-v5-explicit-structure-feedback`.
- Kebijakan retry: `poolside-unit-wide-unseen-family-structure-feedback-v5`.
- Plan: `development/poolside_laguna_qualification_plan_20261023_q4_v5.json`.
- Budget: `development/poolside_laguna_qualification_budget_20261023_q4_v5.json`.
- Bukti persiapan: `docs/evidence/poolside-laguna-q4-v5-dry-run-2026-10-23.json`.
- Assessment live: `results/raw/pilot/poolside-s21-p3-q4-v5-20261023/qualification-assessment.json`.
- Audit pemakaian token dan respons: `docs/evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json`.

Budget tetap 10 kandidat valid per unit untuk menjaga paparan kandidat yang sama
di seluruh kondisi dan mempertahankan perbandingan dengan qualification
sebelumnya. Angka ini merupakan batas operasional protokol, bukan jumlah yang
dibuktikan optimal oleh jurnal atau analisis power.

## Hasil qualification live

- Qualification gate lulus: seluruh 24 unit A/B selesai dengan 10 kandidat
  valid per unit; tidak ada unit yang hilang atau parsial. `formal_eligible`
  tetap `false`.
- Runner memakai 506 dari batas 960 panggilan API. Semua 506 respons HTTP 200,
  seluruhnya berakhir dengan `finish_reason=stop`, dan semuanya memiliki data
  penggunaan token.
- Total penggunaan tercatat 610.910 prompt token dan 70.092 completion token.
  Plafon completion adalah 1.228.800 token, sehingga sekitar 5,70% terpakai.
  Completion terpanjang pada satu respons adalah 356 token; generasi terpanjang
  42 token. Tidak ada indikasi kuota kandidat gagal karena kehabisan token.
- Dari 266 percobaan generasi, 240 menghasilkan kandidat, tujuh ditolak karena
  format, dan 19 tidak menghasilkan struktur valid yang berbeda. Percobaan
  ulang mengatasi seluruh 26 hasil tersebut dan semua 24 unit tetap mencapai
  kuota. Dengan demikian, kegagalan percobaan generasi tidak menjadi kegagalan
  unit di Q4.
- Prompt v5 terbesar memakai 1.891 input token pada generasi dan 1.310 pada
  analisis. Nilai ini dicatat untuk pemantauan konteks; respons tidak terpotong
  berdasarkan `finish_reason`.
- Batas biaya akun Poolside masih belum diverifikasi. Pemakaian token adalah
  bukti volume, bukan biaya uang; laporan ini tidak menyimpulkan biaya akun.

Hasil ini hanya qualification untuk kesiapan generator dan pipeline. Hasil
Q4 tidak menghasilkan metrik FPR/PSR formal, bukan replikasi formal, dan tidak
boleh digabungkan dengan hasil formal lokal atau qualification sebelumnya.

## Validasi dan dasar persiapan

- Seluruh 24 unit A/B terjadwal dan applicable. Batas cohort adalah 240
  kandidat, 720 konfirmasi logis, maksimum 960 panggilan API, enam jam, dan
  1.228.800 completion token.
- Dry-run plan/budget lulus sebelum eksekusi; dry-run tidak mengirim request
  API atau DVWA. Hash paket tersimpan pada bukti dry-run.
- Generator v5 menambahkan feedback signature struktur untuk mengurangi
  kandidat duplikat. Replay offline Q3 mempertahankan hasil parser/hash dan
  meluluskan 250 pemeriksaan feedback signature; replay tersebut menguji
  integritas, bukan performa model.
- Audit Q3 sebelumnya menunjukkan seluruh 274 respons generasi berakhir
  `stop`, maksimum 52 completion token dari batas 1.024 per request, dan total
  66.624 completion token. Empat unit Q3 parsial ditolak karena tidak
  menghasilkan struktur baru yang lolos deduplikasi. Ini mendukung diagnosis
  bahwa masalah Q3 adalah keragaman/struktur kandidat, bukan plafon token.
- Sembilan belas tes generator v4/v5 lulus. Validasi sintaks Python, JSON, dan
  `git diff --check` juga lulus saat persiapan.

## Tindakan berikutnya

1. Simpan qualification Q4 sebagai bukti kesiapan pipeline, terpisah dari data
   formal.
2. Sebelum P4 formal, dokumentasikan amendemen metode penggunaan model/API,
   tetapkan dan verifikasi batas belanja, lalu periksa kesiapan DVWA,
   autentikasi, level, baseline, serta timing.
3. Setelah gate metode dan lingkungan dipenuhi, bekukan protokol P4, dataset
   baru, tiga replikasi, prosedur validasi buta, dan rencana agregasi. Jangan
   mengisi unit parsial Q3 secara retroaktif atau memakai anotasi qualification
   sebagai pengganti anotasi formal.

Runner v5 dapat dijalankan ulang dengan `--execute` hanya jika qualification
baru memang dibutuhkan dan ID eksperimen baru telah disiapkan. Untuk audit
Q4 yang telah selesai, gunakan raw run dan assessment yang tercantum di atas.
