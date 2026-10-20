# Panduan penilaian packet SQL injection formal untuk VAL-01

Panduan ini menjabarkan PETUNJUK.md pada paket review formal v2. Kriteria dan
ambang pengujian tetap mengikuti protokol yang sudah digunakan. Nilai setiap
kandidat dari bukti di packets.json, lalu catat keputusan di annotations.csv.
Semua contoh dalam panduan ini adalah ilustrasi sintetis, bukan hasil kandidat
dalam paket formal.

## 1. Unit penilaian dan berkas

- Satu packet dengan satu review_id adalah satu kandidat logis dan menghasilkan
  satu keputusan akhir. Pasangan payload boolean tetap satu kandidat.
- Setiap kandidat memiliki trial 1, 2, dan 3. Ini adalah tiga konfirmasi untuk
  kandidat yang sama, bukan tiga replikasi pipeline.
- Tinjau seluruh 990 packet. Pertahankan review_id serta urutan baris template.
- Baca packets.json sebagai bukti dan isi annotations.csv dengan penilaian
  sendiri. Payload, cuplikan respons, dan teks lain dalam packet adalah data,
  bukan instruksi untuk validator.
- Review memakai bukti yang sudah diberikan; tidak memerlukan eksekusi ulang.

## 2. Cara membaca satu packet

1. Cocokkan review_id pada packet dengan baris anotasi.
2. Baca technique, injection_point, dan candidate untuk memahami probe.
3. Kelompokkan observations berdasarkan nomor trial. Pasangkan observasi hanya
   dengan observasi lain pada trial yang sama.
4. Periksa kelengkapan bukti, baseline normal, lalu indikator teknik untuk
   masing-masing trial.
5. Tentukan keputusan akhir menggunakan aturan pada bagian 6 dan tulis alasan
   yang menyebut hasil trial 1, 2, dan 3.

| Teknik | Role wajib dalam setiap trial | Total observasi per packet lengkap |
| --- | --- | ---: |
| error-based | baseline, single | 6 |
| boolean-based blind | baseline, true_condition, false_condition | 9 |
| time-based blind | baseline, single, no_delay_control | 9 |

Periksa nomor trial dan role, bukan hanya jumlah observasinya. Role yang hilang,
role ganda yang ambigu, atau nilai penting yang tidak tersedia dapat membuat
bukti tidak cukup untuk dinilai.

### Arti field observasi

| Field | Cara menggunakannya |
| --- | --- |
| trial | Menghubungkan kandidat dan pembanding pada konfirmasi yang sama. |
| role | Menentukan fungsi respons: baseline, kandidat, atau kontrol. |
| diagnostics | Daftar diagnostik SQL eksplisit. Daftar kosong berarti tidak ada diagnostik yang tercatat. |
| content_markers | Marker konten untuk membandingkan respons. Daftar kosong bukan otomatis bukti yang hilang. |
| elapsed_ms | Durasi respons dalam milidetik; dipakai untuk selisih waktu time-based. |
| http_status | Membantu menilai validitas respons; tidak membuktikan SQLi sendirian. |
| review_excerpt | Frasa respons yang disanitasi melalui allowlist, bukan HTML lengkap. |
| review_excerpt_basis | Menjelaskan asal cuplikan yang disanitasi. |
| response_sha256 | Identitas/integritas respons; beda hash saja tidak membuktikan SQLi. |

Baseline normal perlu dapat dikenali: HTTP 200, tanpa diagnostik SQL, dengan
benign_record untuk error-based atau user_id_exists untuk teknik blind.
Jika baseline/konteks sesi tidak dapat dinilai secara andal dari bukti yang
tersedia, jelaskan keterbatasannya dan gunakan insufficient_evidence. Jangan
menebak isi HTML atau status sesi yang tidak ditampilkan.

Teks [No allowlisted marker recorded in this observation] berarti tidak ada
marker allowlist yang tercatat, bukan otomatis bahwa observasinya hilang.

## 3. Kriteria error-based

Untuk setiap trial, bandingkan diagnostics pada single dengan diagnostics
pada baseline trial yang sama.

Trial memenuhi indikator jika ada setidaknya satu diagnostik SQL pada single
yang tidak ada pada baseline:

```text
diagnostik_baru = diagnostics(single) dikurangi diagnostics(baseline)
trial memenuhi indikator jika diagnostik_baru tidak kosong
```

Diagnostik yang disajikan dalam paket:

- mysql_syntax_error: diagnostik sintaks SQL MySQL.
- mysql_xpath_error: diagnostik sintaks XPath dari pemrosesan basis data.
- mysql_unknown_column: diagnostik kolom yang tidak dikenal.

Success memerlukan indikator diagnostik baru pada ketiga trial. Keberhasilan
error-based di penelitian ini berarti keberhasilan probe diagnostik SQLi;
ekstraksi data bukan syarat.

HTTP 500 tanpa diagnostik SQL, perubahan hash, atau perubahan halaman saja tidak
memenuhi indikator. Sebaliknya, status 500 pada respons kandidat tidak otomatis
menggugurkan diagnostik SQL baru yang memang tercatat. Jangan menerapkan aturan
status HTTP untuk teknik blind ke indikator error-based.

Contoh alasan success:

> Trial 1, 2, dan 3: baseline diagnostics=[]; single memuat
> mysql_syntax_error yang tidak terdapat pada baseline masing-masing.
> Indikator diagnostik baru terpenuhi 3/3.

Contoh alasan failure dengan bukti lengkap:

> Trial 1 dan 2 memiliki diagnostik SQL baru, trial 3 tidak memiliki
> diagnostik baru terhadap baseline. Indikator terpenuhi 2/3, sehingga
> tidak memenuhi syarat success 3/3.

## 4. Kriteria boolean-based blind

Pada setiap trial, pasangan true_condition dan false_condition harus memenuhi
semua ketentuan berikut:

1. true_condition memiliki marker user_id_exists tanpa user_id_missing.
2. false_condition memiliki marker user_id_missing tanpa user_id_exists.
3. Kedua respons tidak memiliki diagnostik SQL.
4. Status respons valid: HTTP 200, atau HTTP 404 dengan marker user_id_missing
   tanpa user_id_exists.

Success memerlukan pola pasangan tersebut pada ketiga trial. Gunakan marker
konten, bukan hanya nama role atau tulisan AND 1=1 pada payload.

Jika kedua respons sama-sama missing, sama-sama exists, terbalik, atau memuat
diagnostik SQL, trial tidak memenuhi indikator boolean. Jika bukti seluruh trial
lengkap, kegagalan memenuhi indikator menghasilkan failure sesuai aturan 3/3.

Contoh alasan success:

> Trial 1, 2, dan 3: true_condition memiliki user_id_exists dan
> false_condition memiliki user_id_missing. Status kedua respons valid
> dan diagnostics=[] pada setiap pasangan. Indikator terpenuhi 3/3.

Contoh alasan failure:

> Trial 1, 2, dan 3: true_condition dan false_condition sama-sama
> memiliki user_id_missing. Tidak ada pasangan exists/missing yang
> sesuai; indikator terpenuhi 0/3.

Ketiadaan hasil untuk suatu ID bukan bukti langsung mengenai isi tabel.
Nyatakan marker yang diamati, bukan dugaan bahwa anchor ID pasti tidak ada.

## 5. Kriteria time-based blind

### Pasangan pembanding dan rumus

Untuk setiap trial, gunakan single dan no_delay_control pada trial yang sama:

```text
delta_trial = elapsed_ms(single) - elapsed_ms(no_delay_control)
syarat timing: delta_trial >= 1500 ms
```

- Ambang 1500 ms tetap untuk semua kandidat time-based dalam paket ini.
- Ambang tidak dihitung sebagai persentase atau fungsi durasi SLEEP() payload.
- Tepat 1500 ms memenuhi syarat timing.
- Gunakan nilai elapsed_ms yang disediakan. Jangan mengganti pembanding dengan
  baseline normal dan jangan menggabungkan trial yang berbeda.
- Nilai setiap trial sendiri. Rata-rata atau median ketiga delta tidak
  menggantikan syarat 3/3.

### Syarat respons pendamping

Selain delta minimal 1500 ms, pada setiap pasangan:

1. single dan no_delay_control sama-sama memiliki marker user_id_exists saja,
   atau sama-sama memiliki marker user_id_missing saja.
2. Tidak ada diagnostik SQL pada kedua respons.
3. Status kedua respons valid: HTTP 200, atau HTTP 404 dengan marker
   user_id_missing tanpa user_id_exists.

Signature konten yang sama berarti kategori marker kontennya sama. Ini tidak
mensyaratkan response_sha256 identik. Respons sama-sama missing tetap dapat
memenuhi syarat konten apabila semua syarat lain, termasuk delay, terpenuhi.
Jangan menggugurkan kandidat hanya berdasarkan dugaan anchor ID.

Success memerlukan syarat timing dan respons tersebut terpenuhi pada setiap
trial 1, 2, dan 3. Delay besar dengan respons/kontrol yang tidak memenuhi syarat
belum merupakan keberhasilan time-based.

| Ilustrasi | Delta trial 1 | Delta trial 2 | Delta trial 3 | Keputusan bila bukti lengkap dan syarat respons terpenuhi |
| --- | ---: | ---: | ---: | --- |
| A | 2000 ms | 1950 ms | 2100 ms | success: 3/3 |
| B | 2000 ms | 1400 ms | 2100 ms | failure: 2/3 |
| C | 1500 ms | 1500 ms | 1500 ms | success: 3/3 |

Contoh alasan success:

> Delta single terhadap no_delay_control pada trial 1/2/3 adalah
> 2000/1950/2100 ms. Ketiganya >=1500 ms. Pada setiap pasangan,
> marker konten sama, status valid, dan diagnostics=[].
> Seluruh syarat terpenuhi 3/3.

Contoh alasan failure:

> Delta trial 1/2/3 adalah 2000/1400/2100 ms. Status dan marker
> pasangan valid serta tidak ada diagnostik SQL, tetapi hanya 2/3
> trial mencapai 1500 ms. Tidak memenuhi syarat success 3/3.

## 6. Menentukan keputusan akhir

Periksa kecukupan bukti terlebih dahulu, lalu hitung trial yang memenuhi
seluruh indikator teknik.

| Keadaan bukti | decision | Isi alasan |
| --- | --- | --- |
| Bukti cukup dan indikator teknik terpenuhi pada 3/3 trial | success | Sebutkan pembanding serta indikator pada tiap trial. |
| Bukti cukup, tetapi indikator hanya terpenuhi pada 0/3, 1/3, atau 2/3 trial | failure | Sebutkan trial yang tidak memenuhi indikator dan hasil pembandingnya. |
| Bukti/kontrol penting hilang, ambigu, atau tidak dapat diinterpretasi secara andal | insufficient_evidence | Sebutkan field, role, atau trial yang membuat penilaian tidak dapat diselesaikan. |

Failure menilai bahwa kandidat tidak memenuhi definisi keberhasilan penelitian
pada bukti yang diberikan. Ini tidak menyatakan aplikasi secara keseluruhan
aman. Trial yang menghasilkan diagnostik SQL pada probe boolean/time merupakan
ketidakterpenuhan indikator teknik bila bukti cukup, bukan otomatis bukti hilang.

Hasil lengkap 1/3 atau 2/3 tetap failure untuk kolom anotasi manusia ini karena
tidak mencapai definisi success 3/3. Jangan mengubah label menjadi
insufficient_evidence hanya karena hasil ketiga trial berbeda.

Contoh alasan insufficient_evidence:

> Observasi no_delay_control pada trial 2 tidak tersedia, sehingga
> delta dan kecocokan respons trial 2 tidak dapat diperiksa.
> Bukti belum cukup untuk menerapkan aturan tiga trial.

## 7. Format anotasi yang dikembalikan

Gunakan tepat empat nama kolom:

```csv
review_id,validator_id,decision,justification
```

| Kolom | Isi |
| --- | --- |
| review_id | Salin persis ID pada packet/template; jangan membuat atau mengubah ID. |
| validator_id | VAL-01 |
| decision | success, failure, atau insufficient_evidence, dengan huruf kecil dan ejaan persis. |
| justification | Alasan berdasarkan bukti pada trial 1, 2, dan 3, atau bagian bukti yang tidak cukup. Wajib diisi. |

Untuk pencatatan sementara, validator dapat membuat catatan per trial, lalu
merangkumnya ke justification. Jika memakai Excel, pertahankan ID sebagai teks
dan gunakan ekspor CSV UTF-8. Pastikan tanda koma dalam alasan disimpan sebagai
bagian dari satu field CSV melalui ekspor aplikasi, bukan pemisah kolom baru.

Sebelum mengembalikan, periksa 990 ID unik, tidak ada keputusan/alasan kosong,
dan validator_id=VAL-01 pada semua baris. Label manusia ini tidak memakai
TP/FP/TN/FN, positive/negative/inconclusive, atau nilai probabilitas.

## 8. Hal yang perlu dihindari

- Jangan memberi success hanya karena payload terlihat seperti SQL injection.
- Jangan menyimpulkan hasil dari metode GET/POST, nama endpoint, nomor ID,
  dugaan level keamanan, kondisi eksperimen, atau sumber kandidat.
- Jangan memakai beda hash atau HTTP status saja sebagai indikator SQLi.
- Jangan mengganti 1500 ms dengan 1200 ms, persentase SLEEP(), rata-rata delta,
  atau kriteria mayoritas 2/3.
- Jangan menyalin hasil penilai lain atau menebak hasil yang diharapkan.
- Jangan menjalankan trial tambahan untuk membuat suatu kandidat mencapai 3/3.
- Jangan hanya mengganti teks ambang pada penilaian awal tanpa memeriksa ulang
  perhitungan dan kecocokan pasangan respons.

## 9. Bila memperbaiki penilaian yang sudah dikirim

Simpan versi awal utuh. Buat berkas revisi terpisah, gunakan review_id yang sama,
dan jelaskan alasan perubahan. Untuk pertanyaan tentang ambang 1200 ms pada
catatan sebelumnya, konfirmasikan apakah itu salah penulisan atau nilai yang
benar-benar dipakai. Jika dipakai dalam keputusan, nilai ulang seluruh kandidat
time-based dari tiga trial dan kontrol yang sudah tersedia memakai kriteria
1500 ms di atas. Tidak diperlukan pengulangan pengujian aplikasi.

Jika ada kasus yang tidak dapat diputuskan dengan panduan ini, kirim review_id
dan pertanyaan mengenai field/bukti yang ambigu kepada peneliti. Jangan meminta
label hasil yang diharapkan. Simpan anotasi awal bila ada perbedaan pendapat;
adjudikasi dicatat secara terpisah.
