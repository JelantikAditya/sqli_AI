# Rencana perbaikan setelah eksperimen formal pertama

Tanggal: 19 Oktober 2026.
Status: pilot v1, kontrak v2, shadow verifier v3, dan pilot RAG analisis v4
selesai di development/. V2 memperbaiki konsistensi reason_code. Gate v3
menahan klaim dengan tambahan abstention. Pada v4, A/B sama-sama tepat 12/18
verdict dan 37/51 trial; tambahan retrieval belum meningkatkan hasil. Varian
belum dipromosikan ke runner. Acuan formal tetap
formal-sqli-v1-20261017, R1/R2/R3. Kode dan protokol frozen tidak diubah. Lihat
[hasil pilot v1](pilot-perbaikan-analisis-v1-2026-10-19.md) dan
[validasi v2](validasi-kontrak-analisis-v2-2026-10-19.md), serta
[shadow v3](varian-verifikasi-hibrida-v3-2026-10-19.md), dan
[pilot RAG v4](pilot-rag-analisis-v4-2026-10-19.md).

## Temuan dari audit

### 1. Interpretasi bukti oleh model merupakan masalah langsung FPR

Pada S11 R3 kandidat pertama, baik A maupun B mempunyai marker user_id_missing
pada true_condition dan false_condition di ketiga trial. Model tetap memberi
positive pada ketiga trial dan keputusan akhir. Pada masing-masing run S11 R3,
sepuluh klaim kandidat positif tidak didukung keberhasilan executor.

Pada S12 B R3 kandidat pertama, waktu kandidat trial 1 adalah 4,22 ms dan
kontrol 3,86 ms, sehingga delta 0,36 ms. Model menyatakan ambang 1500 ms tercapai.
Seluruh indikator kandidat tersebut 0/3. Contoh A S12 R3 juga menunjukkan klaim
positif yang berlawanan dengan bukti. Ini menunjukkan kesalahan klasifikasi
model, tanpa membuktikan mekanisme internal yang menyebabkannya.

Sumber lokal di results/raw/formal/formal-sqli-v1-20261017/attempts/:

- formal-sqli-v1-20261017-a-s11-r3/attempt-1-5cd595a683/adaptive/adaptive-s11-off-run-6bf4bccf43614d24.json
- formal-sqli-v1-20261017-b-s11-r3/attempt-1-36fc209cdf/adaptive/adaptive-s11-on-run-6b984c3c2dbe4989.json
- formal-sqli-v1-20261017-a-s12-r3/attempt-1-02b90b5f84/adaptive/adaptive-s12-off-run-59d0859148304687.json
- formal-sqli-v1-20261017-b-s12-r3/attempt-1-f2b90a322e/adaptive/adaptive-s12-on-run-8d135e061677473b.json

Prompt pada dvwa/analyze_response.py sudah meminta pasangan kontrol yang benar,
perhitungan ambang, dan konsistensi tiga trial. Menambahkan ulang kalimat 3/3
saja belum merupakan solusi yang terbukti.

### 2. Retrieval belum membantu tahap analisis respons

dvwa/local_experiment_protocol.json menetapkan RAG pada generasi dan regenerasi
payload saja. Retrieval pada analisis respons dinonaktifkan pada A dan B. Oleh
karena itu, eksperimen ini belum mengukur manfaat retrieval pengetahuan pada
klasifikasi bukti HTTP.

Kebijakan run di dvwa/run_decision_policy.py memberi keputusan positive bila
ada satu klaim kandidat positive pada run lengkap. Kesalahan kandidat dapat
menjadi false positive run. Mengubah aturan ini setelah melihat FPR mengubah
definisi sistem; itu tidak memperbaiki kesalahan interpretasi model yang terlihat.

### 3. Kandidat generasi perlu diperiksa terpisah dari klasifikasi

dvwa/adaptive_s1_loop.py menetapkan pembeda slot 101 sampai 110 dan mewajibkan
angka itu ada pada setiap nilai kandidat. Pada sampel B S2 R3, pasangan
101 AND 1=1 dan 101 AND 1=2 sama-sama mendapat respons missing, sementara
baseline 1 mendapat exists. Sampel time-based Low juga memakai 101 atau 109
sebagai ID awal dan tidak menghasilkan matched delay yang diperlukan.

Hipotesis pengembangan: pembeda keunikan sering menjadi ID seleksi utama dan
mengurangi kesempatan probe memperlihatkan perbedaan respons. Bukti HTTP ini
tidak membuktikan isi tabel atau bentuk query internal. Hipotesis perlu diuji
dengan anchor yang sudah dikonfirmasi melalui respons benign, tanpa akses
source code target atau database. Konteks kutip dan bentuk ekspresi juga perlu
diperiksa; mengganti nomor ID saja belum menjamin probe berhasil.

## Urutan perbaikan yang disarankan

### Tahap 1. Perbaiki penyajian dan penalaran bukti pada versi pengembangan

- Sajikan hanya pasangan pembanding relevan dan konteks validitas baseline.
  Boolean membandingkan true dengan false; timing membandingkan kandidat dengan
  matched no-delay control. Jangan menjadikan perubahan terhadap baseline
  benign sebagai bukti keberhasilan boolean/time.
- Hitung delta waktu dalam kode dan berikan angka delta eksplisit bersama
  durasi asli. Model tetap menilai bukti, tetapi tidak dibebani pengurangan
  angka yang dapat dihitung secara pasti.
- Pertahankan output per trial, referensi kedua sisi pembanding, dan klaim akhir.
  Evaluasi apakah keputusan benar-benar mengikuti indikator yang tersedia.
- Perbaikan input/prompt umum harus sama pada A dan B.
- Jika model saat ini tetap gagal pada evaluasi pengembangan terpisah, pemilihan
  model lain menjadi eksperimen lanjutan dengan versi dan biaya yang dicatat.

Jangan mengganti klaim mentah model dengan label executor. Jika lapisan
verifikasi deterministik kelak digunakan, simpan keluaran model dan keputusan
sistem gabungan secara terpisah, lalu jelaskan sistem baru itu dalam metode.

### Tahap 2. Uji peran retrieval pada verifikasi bukti

Sebagai varian metode baru, uji retrieval pada analisis respons di B, dengan
A memakai model, input pengukuran, dan prompt dasar yang sama tanpa retrieval.
Lokasi penggunaan RAG harus dinyatakan eksplisit dalam protokol baru.

Pengetahuan yang relevan mencakup cara membaca pasangan boolean, kontrol timing,
diagnostik SQL baru, dan contoh kegagalan indikator. Nilai relevansi chunk
terhadap teknik dan injection point, bukan sekadar jumlah dokumen atau top_k.

Jangan memasukkan scenario ID, level DVWA, expected outcome, label hasil formal,
atau jawaban validator ke query/prompt/korpus. Pengetahuan umum tidak boleh
menjadi bocoran label target.

Evaluasi retrieval dan kualitas keluaran secara terpisah. Pemisahan evaluasi
tersebut juga digunakan dalam dokumentasi resmi LangChain:
https://docs.langchain.com/langsmith/evaluate-rag-tutorial
Ini tidak memerlukan mengaktifkan tracing eksternal pada proyek lokal.

### Tahap 3. Uji perbaikan kebijakan kandidat

- Gunakan anchor benign yang keberadaannya sudah terkonfirmasi dari respons
  HTTP pada sesi dan injection point yang relevan.
- Pisahkan keunikan kandidat dari ID utama; variasikan struktur yang masih
  memenuhi teknik dan pembanding yang sah.
- Terapkan kebijakan kandidat yang sama pada A dan B. Jangan memberikan payload
  manual untuk menambal budget generasi.
- Pertahankan DAST/black-box, batas teknik SQLi, kontrol valid, budget dan
  pencatatan provenance. Perubahan budget atau aturan lain perlu alasan dan
  versi tersendiri.

Ubah satu komponen pada setiap perbandingan pengembangan agar penyebab perubahan
hasil dapat ditelusuri.

## Pengujian pengembangan sebelum eksperimen formal baru

1. Gunakan hasil formal sekarang untuk diagnosis. Jangan menyajikannya kembali
   sebagai data validasi yang belum pernah dilihat setelah penyetelan.
2. Siapkan kasus pengembangan dan holdout baru yang terpisah, meliputi indikator
   3/3, 0/3, mixed 1/3 dan 2/3, kontrol tidak sesuai, serta bukti tidak lengkap.
   Label evaluator disimpan di luar input model dan retrieval.
3. Evaluasi analisis pada observasi tersimpan terlebih dahulu. Langkah ini tidak
   memerlukan eksekusi ulang DVWA, tetapi tetap memerlukan inferensi model jika
   ingin mengukur perubahan output model. Ini evaluasi pengembangan.
4. Setelah kandidat perbaikan menunjukkan hasil yang layak pada holdout, lakukan
   pilot A/B baru yang mencakup kontrol positif dan negatif. Jangan hanya
   memilih kasus S11/S12 yang sudah diketahui bermasalah.
5. Bekukan konfigurasi baru sebelum eksperimen formal berikutnya. Laporkan
   false positive, false negative, abstention, coverage, PSR, dan runtime agar
   penurunan FPR tidak sekadar akibat meningkatnya abstention atau kegagalan
   mendeteksi semua kasus positif.

Kasus lama U01 serta hasil formal yang sudah terbuka tidak menjadi holdout baru.
Tahap pertama kini mempunyai prototipe dan pilot sintetis baru yang ditetapkan
sebelum inferensi. Pilot membandingkan prompt frozen v8 dan penyajian pasangan
pengukuran v1 pada Qwen 2.5 7B, dengan model, seed dan budget yang sama.
Rinciannya ada di [panduan pengembangan](../development/README.md). Pilot ini
bukan holdout independen atau pengujian DVWA. Pada pilot v1, retrieval analisis
belum diterapkan. Retrieval analisis kemudian diuji pada v4; perbaikan kebijakan
kandidat masih merupakan tahap yang belum diterapkan.

Pilot pertama selesai dengan 18 inferensi Qwen. Asesmen trial meningkat dari
15/26 menjadi 26/26, tetapi keputusan akhir tetap 6/9 pada kasus valid. Prototipe
regresi pada mixed 1/3, mixed 2/3 dan trial tidak lengkap, serta mempunyai enam
warning reason_code. Kontrak keputusan akhir menjadi prioritas berikutnya
sebelum tahap retrieval analisis. Semua klaim asli dan kegagalan dipertahankan.

Revisi v2 kemudian menambahkan rekap trial yang dihasilkan model dan pemetaan
kode literal. Evaluasi dibekukan sebelum 41 inferensi: perbandingan v1/v2 pada
17 kasus baru dan regresi v2 pada 10 kasus lama. Pada 16 kasus baru yang valid,
verdict v2 tepat 11/16 dibandingkan v1 10/16. Mismatch reason_code turun 7 ke 0,
tetapi asesmen trial turun 33/44 ke 32/44. Klaim positif pada enam fixture
negatif tetap tiga pada kedua profil. Regresi v2 tepat 7/9 dan 24/26 trial.

Kriteria yang ditetapkan belum tercapai. Seluruh 25 output v2 memakai kode yang
konsisten dengan decision, tetapi pembacaan marker/kontrol, perbandingan ambang,
dan kepatuhan pada trial yang hilang masih gagal. Audit 44 record serta
preservasi 959 sumber formal lulus. Langkah berikutnya harus menangani kegagalan
tersebut pada varian dan kasus baru sebelum mengklaim perbaikan analisis.
Jika menambahkan verifikasi deterministik, klaim LLM dan keputusan gabungan
harus dipisahkan dan metode diberi versi baru. Lihat
[laporan v2](validasi-kontrak-analisis-v2-2026-10-19.md).

Shadow v3 kemudian mengimplementasikan verifier pengukuran yang terpisah dan
gate kesepakatan biner. Model/prompt tetap v2. Pada 20 kasus valid baru,
verdict Qwen/gabungan tepat 15/20 dan 17/20. Tiga klaim positif keliru menjadi
inconclusive, sehingga coverage negatif turun 7/7 ke 4/7. Empat kontrol positif
tetap terdeteksi. Enam belas uji offline serta audit 48 record lulus, dan
959 sumber formal beserta 16 artefak v1/v2 tetap utuh.

Kriteria coverage v3 belum tercapai. Rekomendasi saat ini adalah memakai gate
sebagai audit sekunder, mempertahankan klaim mentah untuk evaluasi RAG, dan
menguji bukti HTTP baru dengan penilaian independen sebelum perubahan metode
utama. Nol klaim positif keliru setelah gate tidak berarti FPR utama 0%.
Verifier-only pada fixture sintetis menguji kesesuaian aturan dan belum
menjadi bukti akurasi independen. Lihat
[hasil dan batas v3](varian-verifikasi-hibrida-v3-2026-10-19.md).

Pilot v4 menguji retrieval analisis pada B, dengan A memakai prompt dasar dan
pengukuran yang sama tanpa referensi. Dua entri per teknik diretrieve dari
proyeksi korpus OWASP/PayloadsAllTheThings pada Chroma memori terpisah. Ada
36 inferensi, dua skip runtime invalid, dan 19 pasangan kasus baru.

Pada 18 kasus valid, kedua kondisi sama-sama tepat 12/18 verdict dan 37/51 trial,
dengan tiga klaim positif pada enam fixture negatif. Semua pasangan valid
mempunyai verdict dan asesmen trial yang sama. Kriteria peningkatan belum
tercapai. Audit 38 record, sumber/ranking retrieval serta 19 pasangan request
lulus. Seluruh 959 sumber formal dan 26 artefak historis tetap utuh.

Temuan v4 dipertahankan tanpa tuning pada set yang sama atau promosi ke metode
formal. Langkah berikutnya adalah evaluasi bukti HTTP baru dengan penilaian
independen dan desain yang dipin. Hasil ini mengukur tambahan referensi umum
pada konfigurasi v4, bukan menetapkan efek semua bentuk RAG. Lihat
[hasil dan batas v4](pilot-rag-analisis-v4-2026-10-19.md).

Review kurasi setelah v4 selesai pada sembilan entri/45 field. Proyeksi
menggabungkan konsep sumber dengan kontrol editorial; satu kalimat boolean
memerlukan klarifikasi scope hasil kandidat. Metadata pending bukan status
persetujuan terkini korpus asal: keputusan peneliti 12 dan 17 Oktober tercatat
terpisah. Review teknis ini tidak mengubah korpus maupun hasil eksperimen.
Sebelum pilot berikutnya, siapkan versi baru dengan provenance per field,
konteks verifikasi yang scope-nya jelas, dan penilaian relevansi pada query
baru sebelum freeze. Aturan proyek tidak boleh diatribusikan kepada upstream.
Lihat [review dan cakupan tugas](review-rag-analisis-2026-10-19.md).

## Dampak pada hasil dan runtime

- R1/R2/R3 dan anotasi VAL-01 tetap menjadi hasil versi formal pertama.
- FPR resmi versi tersebut tetap undefined; 66,67% tetap angka sensitivitas
  dengan asumsi S10 dihitung TN.
- Bukti keberhasilan perbaikan memerlukan versi eksperimen baru. Replay analisis
  tidak menghasilkan PSR baru dari payload generasi yang belum dieksekusi.
- Diagnosis dan replay pengembangan dapat dimulai tanpa mengulang keseluruhan
  pengujian. Durasi pilot/formal baru tidak ditetapkan sebelum cakupan dipilih.
- Perbaikan tidak menjamin B mengungguli A. Jika keduanya tetap setara pada data
  baru, hasil itu perlu dilaporkan sesuai data.

Prioritas pertama adalah kesalahan analisis respons yang langsung terlihat
pada S11/S12. Setelah itu, uji kontribusi retrieval dan kebijakan kandidat
secara terpisah sebelum mempertimbangkan pengujian formal berikutnya.
