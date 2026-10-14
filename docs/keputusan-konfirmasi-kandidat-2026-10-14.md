# Keputusan T01: konfirmasi kandidat 3/3

Tanggal: 14 Oktober 2026.
Dipilih dan disetujui oleh peneliti melalui chat proyek.
Protokol aktif: `local-sqli-v2-pilot`, status tetap `pilot`.
Dokumen ini mencatat tahap konfirmasi v2. Kelanjutan pada hari yang sama
menetapkan [keputusan run INCONCLUSIVE](keputusan-run-inconclusive-2026-10-14.md)
pada local-sqli-v3-pilot. Aturan kandidat 3/3 tetap berlaku; hash/verifikasi
v2 di dokumen ini merupakan snapshot tahap sebelumnya, bukan kode aktif v3.

## Unit dan aturan yang disetujui

Satu kandidat logis diuji tepat tiga konfirmasi valid pada satu
scenario-condition-pipeline-replicate. Payload, injection point, dan teknik
tetap sama. Keputusan ini berlaku identik pada kondisi A/B/C.

| Konfirmasi positif | evidence_status | confirmed_success | PSR |
| --- | --- | --- | --- |
| 3/3 | CONSISTENT_POSITIVE | true | Memenuhi syarat bukti keberhasilan; masuk penyebut dan dapat masuk pembilang setelah validasi. |
| 2/3 | MIXED_EVIDENCE | false | Masuk penyebut kandidat valid, tidak masuk pembilang. |
| 1/3 | MIXED_EVIDENCE | false | Masuk penyebut kandidat valid, tidak masuk pembilang. |
| 0/3 | CONSISTENT_NEGATIVE | false | Masuk penyebut kandidat valid, tidak masuk pembilang. |
| Runtime gagal | RUNTIME_INVALID | null | Seluruh attempt invalid dan dikeluarkan dari analisis utama. |

Record development yang hanya memiliki satu/dua konfirmasi, memiliki lebih
dari tiga, atau bukan trial 1/2/3 diberi INCOMPLETE_CONFIRMATIONS dan
confirmed_success=null. Record tersebut tidak menjadi keberhasilan terkonfirmasi.
Status ini diperlukan agar smoke lama satu konfirmasi tidak disalahartikan
sebagai kegagalan valid atau sukses formal.

Satu konfirmasi bukan selalu satu request HTTP:

- Error-based: baseline normal dan kandidat, dengan diagnostik basis data baru.
- Boolean blind: baseline dan pasangan true/false pada koordinat yang sama.
- Time blind: baseline, kandidat delay, dan kontrol tanpa delay yang cocok;
  indikator per konfirmasi memakai selisih minimal 1500 ms sesuai protokol pilot.

Tiga konfirmasi bukan tiga kandidat. Pasangan boolean tetap satu kandidat.
Tiga konfirmasi juga bukan tiga pengulangan pipeline. Aturan mean dan SD antar
pengulangan yang disetujui 12 Oktober tetap berlaku tanpa voting antar-run.

Ambang 3/3 menetapkan reproducibility yang diminta pada tiga pengamatan.
Ambang ini tidak menjamin hilangnya seluruh noise atau kesalahan pengukuran;
validitas baseline, pasangan kontrol, sesi, dan anotasi tetap diperiksa.

## Hasil bercampur final, tanpa probe tambahan

Hasil 1/3 dan 2/3 merupakan hasil akhir kandidat pada iterasi berjalan.
Tidak ada putaran tambahan untuk kandidat yang sama, termasuk ketika Qwen
mengeluarkan feedback_action=collect_more_evidence. Permintaan model tersebut
disimpan, tetapi executor tidak melaksanakannya.

Runner adaptif meneruskan evidence dan klaim kandidat sebelumnya untuk
generasi kandidat baru yang unik. Fixed budget tetap dipenuhi meskipun ada
kandidat berhasil. Retry generasi untuk JSON/payload invalid atau duplikasi
berbeda dari pengulangan konfirmasi kandidat yang sudah dieksekusi.

Runtime error tetap menginvalidasi seluruh attempt. Pemulihan mengikuti
protokol yang sudah ada: perbaiki lingkungan, login baru dan reset database,
lalu mulai attempt baru dengan log attempt lama dipertahankan. Automatic
runtime retries tetap nol. Aturan ini bukan retry untuk mixed evidence.

## Bukti dan klaim model dipisahkan

Ledger analisis menyimpan:

- evidence_status dan jumlah konfirmasi valid/positif: klasifikasi bukti objektif.
- confirmed_success: true hanya untuk tepat tiga konfirmasi positif valid.
- qwen_claim: VULNERABLE, NOT_VULNERABLE, INCONCLUSIVE, atau null jika model
  belum memberi hasil. Nilai INCONCLUSIVE diperlukan untuk mempertahankan
  keluaran model asli tanpa memaksakan keputusan biner.
- system_claim dan model_output: keluaran asli positive/negative/inconclusive,
  alasan, referensi evidence, serta usulan feedback tetap dipertahankan.
- claim_supported: klaim positif didukung hanya jika bukti 3/3 dan referensi
  model mencakup ketiga pasangan pembanding. Ini flag audit, bukan filter klaim.

Executor batch menyimpan candidate_evidence dengan qwen_claim=null karena
runner T05 saat ini belum memanggil analisis Qwen. Sinyal aturan tidak diganti
namanya menjadi klaim Qwen. Record decision tetap merupakan sinyal satu
konfirmasi, ditandai decision_scope=single-confirmation-rule-signal.
Confusion class diagnostik pada record per konfirmasi bukan unit FPR utama.

FPR utama tetap memakai satu klaim sistem per scenario-condition-replicate
dan ground truth evaluator. Klaim positif pada kontrol negatif adalah FP,
termasuk jika evidence_status MIXED_EVIDENCE atau CONSISTENT_NEGATIVE.
Pada target positif, klaim positif adalah TP menurut ground truth target;
ketidakcukupan dukungan bukti dicatat terpisah sebagai unsupported claim,
bukan otomatis FP. Ini memperjelas kolom audit pada matriks keputusan peneliti.

Ringkasan analisis tetap memakai klaim Qwen: ada satu klaim positif pada run
lengkap menghasilkan system_decision=positive, tanpa menyaringnya dengan
confirmed_success. Tanpa positif tetapi ada inconclusive, ringkasan tetap
inconclusive. Kebijakan final kemudian ditutup pada keputusan run v3;
jangan mengubahnya menjadi TN hanya untuk melengkapi confusion matrix.

PSR final tetap memerlukan prosedur validator T06. Penghitungan
confirmed_success_count merupakan hitungan bukti, bukan PSR formal.
Run yang budgetnya incomplete atau attempt-nya invalid tidak masuk analisis utama.

## Implementasi, versi, dan verifikasi

- `dvwa/confirmation_policy.py`: klasifikasi yang dipakai analisis dan executor.
- `dvwa/analyze_response.py`: rule_signal mengembalikan status bukti, bukan
  boolean minimal satu sinyal; prompt analisis menjadi sqli-response-analysis-v4.
- Ledger analisis menjadi schema_version=1.1.0. Record 1.0.0 lama tidak
  kompatibel dengan validator aktif; jangan mengganti versinya tanpa normalisasi
  ulang pada artefak baru yang ditautkan ke sumber lama.
- `dvwa/adaptive_s1_loop.py`: menghapus putaran konfirmasi tambahan,
  mempertahankan klaim dan meneruskan status bukti ke generasi berikutnya.
- `dvwa/validation_loop.py`: satu candidate_evidence per kandidat, termasuk
  kandidat yang mengalami runtime invalid setelah konfirmasi parsial.
- `dvwa/run_local_experiments.py`: memeriksa schema dan menghitung ulang
  ringkasan kandidat dari tiga decision record sebelum menyelesaikan attempt.
  Hash modul policy dan schema baru ikut penjagaan resume.
- Konfigurasi mengunci threshold=3, additional_confirmation_rounds=0, dan
  mixed_evidence_policy=retain-in-psr-denominator-not-success.
- Test offline mencakup 0/1/2/3 positif pada ketiga teknik dan A/B/C,
  jumlah submission tanpa tambahan, runtime invalid, integritas ringkasan,
  klaim unsupported yang tetap FP pada kontrol negatif, serta feedback kandidat baru.

Verifikasi akhir: **78 test lulus**, 35 file Python lulus parsing, 11 definisi
schema JSON valid, pemeriksa protokol menerima matriks 99 run berstatus pilot,
dan git diff --check lulus. Ringkasan serta hash 12 artefak implementasi tersedia
di [evidence offline](evidence/t01-confirmation-policy-offline-2026-10-14.json).

Tidak dilakukan inferensi model nyata, scan, probe ke DVWA, atau reset database
untuk perubahan ini. Bukti pilot 12 Oktober dan hasil mentah lama tidak diubah.
Perubahan protokol/kode memerlukan ID eksperimen baru; resume eksperimen lama
dengan konfigurasi baru harus ditolak oleh penjagaan hash.

## Status T01 setelah keputusan

Aturan konfirmasi bercampur ditutup pada tingkat keputusan dan implementasi
offline. Keputusan run inconclusive juga telah ditutup pada kelanjutan v3.
T01 secara keseluruhan tetap parsial: metodologi laptop lokal/peran LangChain
dan urutan kondisi formal masih perlu difinalisasi. Protokol belum frozen
dan T06-T08 belum dinyatakan selesai.

Pembaruan berikutnya pada 14 Oktober: metodologi lokal/peran LangChain
ditetapkan pada keputusan-metodologi-lokal-langchain-2026-10-14.md dan protokol
v4. Yang tersisa di T01 adalah urutan kondisi formal; pembuktian integrasi
framework tetap T02/T05. Urutan formal kemudian ditetapkan pada
[penutupan T01](keputusan-urutan-kondisi-2026-10-14.md), protokol v5.
