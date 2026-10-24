# Persiapan Qualification Laguna Q3

Tanggal: 2026-10-23
Status: Q3 selesai dijalankan, gate qualification gagal

## Ringkasan

Paket qualification Poolside Laguna S 2.1 dijalankan sebagai eksperimen generasi kandidat SQLi v4 setelah konfirmasi pengguna. Paket ini tetap berstatus qualification, bukan data formal. Eksekusi selesai pada 2026-10-23 sekitar 04:56 UTC.

## Yang sudah disiapkan

- Generator v4 memakai bank 40 referensi keluarga struktural untuk tiap tipe probe: `single_error`, `boolean_pair`, dan `single_time`. Scheduler memilih keluarga yang belum diminta di unit terkait. Nilai referensi internal tidak dikirim ke model; parser serta kebijakan validasi yang ada tetap menentukan penerimaan kandidat.
- Batas retry per slot adalah tiga permintaan generasi. Budget token memulihkan penggunaan dari checkpoint dan memakai reservasi penuh bila penggunaan token sebelumnya tidak tercatat.
- Plan dan budget Q3 baru mencakup 24 unit A/B, 240 kandidat, 720 logical confirmations, paling banyak 960 panggilan API, waktu enam jam, dan plafon 1.228.800 completion token.
- File budget mencatat batas belanja akun sebagai belum diverifikasi. Informasi publik Poolside menyebut akses Laguna S 2.1 gratis untuk waktu terbatas, tetapi itu tidak memastikan kuota atau batas biaya akun yang digunakan proyek ini. Lihat [halaman model Poolside](https://poolside.ai/models).

## Pemeriksaan yang lulus

- Replay offline terhadap rekaman Q2 menjalankan ulang 269 respons generasi pada 24 unit. Hash respons dan hasil parser cocok dengan bukti tersimpan; tidak ditemukan benturan ID keluarga atau kunci struktural yang sudah diterima.
- Replay tidak mengubah 1.732 file sumber. Replay mengirim nol request API dan nol request DVWA.
- Tujuh tes generator dan budget lulus.
- Dry-run Q3 melaporkan 24 dari 24 unit terjadwal dan applicable, 240 kandidat, 720 logical confirmations, hingga 960 panggilan API, dan 1.228.800 completion token. `execution_started` bernilai `false`.
- Hash plan dan bukti replay cocok dengan yang dipatok di file budget. `git diff --check` bersih.

## Hasil eksekusi live

- Seluruh 24 unit dicoba. Dua puluh unit mencapai kuota 10 kandidat; empat dikecualikan karena budget kandidat tidak lengkap. Gate qualification gagal dan `formal_eligible` bernilai `false`.
- Unit yang tidak lengkap: A/S3 (4/10), A/S12 (4/10), B/S3 (4/10), dan B/S8 (9/10).
- Runner memakai 495 dari maksimum 960 panggilan: 274 generasi dan 221 analisis. Semua 495 request memiliki hasil HTTP 200. Penggunaan yang dilaporkan adalah 66.624 completion token, tanpa request yang kehilangan data penggunaan token.
- Hasil generator: 221 respons menghasilkan kandidat, 47 berstatus `no_valid_distinct_candidate`, dan 6 berformat kandidat tidak valid. ID keluarga yang dijadwalkan tetap unik dalam setiap unit, tetapi beberapa respons tidak memberi struktur kandidat baru yang lolos deduplikasi.
- Audit token atas seluruh 274 request generasi menemukan `finish_reason=stop` pada semuanya. Output generasi terpanjang hanya 52 completion token dari batas 1.024 token per request; total completion token seluruh run adalah 66.624 dari plafon 1.228.800, sekitar 5,42%. Keempat unit yang tidak lengkap berstatus `no_valid_distinct_candidate` pada percobaan yang ditolak, bukan respons terpotong. Bukti ini tidak mendukung hipotesis bahwa kuota token menyebabkan kegagalan.
- Rincian pada unit tidak lengkap: A/S3 memiliki 5 respons duplikat/tidak berbeda setelah validasi, A/S12 memiliki 5, B/S3 memiliki 3, dan B/S8 memiliki 4. Q3 menggunakan 495 dari plafon 960 panggilan API, sehingga plafon panggilan juga tidak habis.
- Database DVWA di-reset untuk seluruh 24 unit sesuai protokol.
- Budget tidak mencatat biaya dolar aktual. Batas atau tarif akun Poolside masih belum terverifikasi, sehingga biaya tidak dapat disimpulkan dari jumlah token saja.

## Iterasi v5 offline setelah Q3

- Audit empat unit yang tidak lengkap menemukan respons model mengulang struktur yang sudah diterima, meskipun family ID request berbeda. Di seluruh run, 47 respons berstatus `no_valid_distinct_candidate` dan 6 berformat kandidat tidak valid.
- Profil v5 menambahkan pola family abstrak serta daftar signature struktur terdahulu dan yang ditolak ke prompt. Signature memakai normalisasi yang sama dengan parser untuk huruf besar/kecil, whitespace, dan angka. Parser dan kebijakan penerimaan tetap sama.
- Replay 274 respons Q3 melalui profil v5 mempertahankan 221 kandidat dan semua status parser, tanpa mismatch hash request. Sebanyak 250 pemeriksaan memastikan signature kandidat terdahulu masuk ke feedback retry. Tidak ada benturan family ID, request API, atau request DVWA; 1.708 file run Q3 tetap tidak berubah.
- Sebelas tes v4/v5 lulus bersama. Replay memakai respons dari prompt v4, sehingga ini memvalidasi integritas dan rendering feedback v5, bukan performa model v5.

Replay Q2 sebelumnya hanya memeriksa kompatibilitas parser serta disiplin scheduler terhadap respons Q2 yang dibuat dengan prompt lebih lama. Replay Q3 v5 juga tidak memprediksi kualitas atau keberhasilan generasi v5.

## Tindakan berikutnya

1. Pertahankan Q3 sebagai qualification gagal dan jangan gabungkan hasilnya ke dataset formal atau metrik FPR/PSR formal.
2. Siapkan runner, plan, dan budget qualification baru yang mematok profil v5, lalu dry-run dan audit hash sumber sebelum mempertimbangkan cohort live berikutnya.
4. Tetapkan plafon biaya akun yang dapat diverifikasi sebelum qualification live berikutnya. Hasil Q3 tetap tidak menggantikan amendemen metode atau P4 formal tiga replikasi.

Dry-run yang dapat diulang:

```powershell
.\.venv\Scripts\python.exe development\run_bounded_poolside_qualification_v4.py
```

Q3 sudah dieksekusi dengan flag `--execute`, `--confirm-local-dvwa`, `--confirm-database-reset`, dan `--confirm-api-spending`. Jangan menjalankan ulang ID eksperimen yang sama; gunakan ID dan plan baru untuk qualification berikutnya.
