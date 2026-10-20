# Rancangan perbaikan U01: analisis respons Qwen

Tanggal: 14 Oktober 2026.
Status: kontrak output, audit semantik, dan tes offline diterapkan; gate
implementasi lulus. Validasi tertutup satu kali selesai dengan 11/18 klaim
runtime-valid cocok.
Dasar: replay inferensi segar `u01-replay-v9-20261014` dan kontrak analisis
aktif.

## Tujuan

Mengurangi salah klasifikasi Qwen pada bukti SQLi berulang dan memastikan
setiap klaim positif merujuk seluruh observasi pembanding yang diperlukan.
Perbaikan tidak boleh mengubah definisi bukti 3/3, system claim, FPR, atau PSR
secara diam-diam.

## Batas metodologi

- Simpan respons mentah, output terstruktur, klaim Qwen, evidence executor,
  status dukungan klaim, dan anotasi validator sebagai field terpisah.
- Jangan mengganti klaim Qwen dengan `rule_signal` atau `confirmed_success`.
  Ketidaksesuaian menjadi warning dan tetap masuk audit.
- Jangan memasukkan ground truth, klaim yang diharapkan, atau label fixture ke
  prompt yang dikirim ke model.
- Jangan menambah konfirmasi atau request DVWA untuk memperbaiki klasifikasi.
- Jangan mengubah FPR/PSR berdasarkan replay pengembangan.

## Perubahan yang direncanakan

1. Pertahankan v9 dan tujuh fixture tetap sebagai baseline regresi. Gunakan
   fixture tersebut untuk menemukan regresi, bukan sebagai satu-satunya bukti
   generalisasi.
2. Buat set validasi tertutup terpisah dengan fixture untuk tiga teknik. Setiap
   teknik memuat kasus positif 3/3, negatif 0/3, mixed 1/3, mixed 2/3, dua
   konfirmasi positif dengan konfirmasi ketiga hilang, kontrol spesifik teknik
   yang tidak memenuhi indikator, dan runtime invalid.
3. Naikkan versi prompt dan kontrak output. Minta Qwen mengeluarkan asesmen
   ringkas per trial beserta ID observasi pembanding, lalu klaim akhir. Untuk
   error-based, pasangan referensi mencakup baseline dan kandidat; untuk
   boolean-based, observasi true dan false; untuk time-based, kandidat dan
   kontrol tanpa delay.
4. Validasi struktur serta semantik setelah respons diterima. Hitung ulang
   sinyal executor secara independen, periksa kelengkapan trial, cek ID
   referensi dan cakupan pasangan. Simpan klaim Qwen apa adanya, tandai
   ketidaksesuaian klaim, dan tandai referensi positif yang tidak lengkap.
5. Pertahankan prompt RAG-off dan RAG-on analisis identik sesuai protokol.
   Perubahan prompt analisis tidak mengambil konteks retrieval.

## Gate penerimaan

- Schema output baru valid, tes kontrak dan semantik lulus, serta parser menjaga
  klaim Qwen apa adanya.
- Input runtime invalid dihentikan tanpa keputusan model. Referensi observasi
  tidak dikenal, asesmen trial yang bertentangan dengan executor, klaim pada
  trial yang tidak lengkap, dan sitasi pasangan yang kurang harus ditandai
  warning/status audit yang eksplisit.
- Replay tujuh fixture regresi dijalankan dan seluruh hasil dicatat. Kecocokan
  klasifikasi Qwen merupakan bukti kinerja model, bukan syarat lulus gate
  implementasi. Jangan menghapus atau mengubah mismatch untuk meluluskan gate.
- Set validasi tertutup dijalankan satu kali setelah prompt dan schema
  dibekukan. Gate ini selesai. Laporkan semua hasil, termasuk kegagalan.
  Jangan menyetel prompt memakai jawaban set yang sudah dibuka.
- Simpan hash prompt, schema, input fixture, output mentah, dan ringkasan hasil.
- Replay dan set validasi pengembangan tidak dihitung sebagai FPR atau PSR.
  Kinerja model dilaporkan pada pilot/formal sesuai protokol, termasuk semua
  klaim salah yang memenuhi aturan pencatatan.

## Urutan kerja

1. Rancang skema asesmen per trial dan warning sitasi.
2. Tambahkan tes unit semantik serta referensi untuk tiga teknik.
3. Siapkan dan bekukan fixture validasi sebelum menjalankan model.
4. Jalankan replay regresi dan validasi dengan Qwen lokal, tanpa request DVWA.
5. Audit hasil validasi dan laporkan kinerja model; jangan memakai replay pengembangan sebagai FPR/PSR.

Implementasi pengembangan saat ini memakai prompt
`sqli-response-analysis-v8-count-trials`, satu revisi terarah setelah v7.
Replay tujuh fixture cocok pada 5/7 secara keseluruhan dan 4/6 untuk kasus
runtime valid. Revisi memperbaiki verdict mixed 1/3 dan trial yang tidak
lengkap, tetapi model masih salah menggabungkan 0/3 dan membaca diagnostik
mixed 2/3. Hasil ini dicatat sebagai kesalahan kinerja pada set pengembangan,
bukan kegagalan gate implementasi. Prompt v8 dibekukan untuk validasi tertutup
satu kali. Validasi 21 fixture yang mencakup tiga teknik telah dijalankan satu
kali: 14/21 cocok keseluruhan, 11/18 untuk input runtime-valid. Tiga input
runtime-invalid dihentikan benar tanpa inferensi. Hasil rinci disimpan dalam
evidence U01; set ini bukan anotasi validator atau metrik formal. Jangan tuning
prompt dari set yang kini terbuka. Pilot/formal tetap menunggu dependensi
U01-U05, termasuk penetapan validator independen.

Rancangan ini tidak mengasumsikan prompt sebagai satu-satunya akar masalah.
Jika model gagal pada validasi, catat keterbatasan klasifikasi dan evaluasi
hipotesis penelitian dari hasil yang telah divalidasi, tanpa menimpa klaim
model menggunakan hasil executor.
