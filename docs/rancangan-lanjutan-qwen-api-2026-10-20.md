# Rancangan kerja lanjutan penelitian dengan API Qwen3.8-27B

Disusun: 20 Oktober 2026. Tenggat peneliti: 30 Oktober 2026.
Target internal: hasil dan naskah lengkap pada 28 Oktober; 29 Oktober untuk koreksi dan 30 Oktober untuk pengumpulan.
Status: usulan kerja dan desain eksperimen. Penyusunan dokumen ini tidak menjalankan API, DVWA, atau eksperimen formal baru.

## 1. Arah dan posisi penelitian

Lanjutkan penelitian menggunakan layanan API dengan alias `Qwen3.8-27B` sebagai backend LLM pada versi eksperimen baru. Pertahankan pertanyaan utama: implementasi pipeline DAST, kontribusi RAG terhadap FPR, dan perbandingan PSR payload LLM+RAG dengan SecLists. Keberhasilan penyelesaian penelitian berarti metode terlaksana dan kesimpulan didukung data, termasuk jika RAG setara atau lebih buruk.

Tetap gunakan DVWA lokal pada Low, Medium, High, dan Impossible; tiga teknik SQLi adalah error-based, boolean-based blind, dan time-based blind. Executor menggunakan bukti HTTP black-box. API menerima fitur dan konteks tersanitasi; aplikasi DVWA tidak perlu dipublikasikan atau diberi tunnel agar dapat dipanggil model.

Proposal pada Bab 1.4 butir 4 masih membatasi model pada Qwen2.5 7B mandiri tanpa API pihak ketiga. Karena itu, siapkan usulan revisi Bab 1, Bab 2 yang menjelaskan pemilihan model, serta Bab 3 sebelum mengklaim eksperimen API sebagai implementasi proposal yang sama. Diskusikan perubahan tersebut dengan pembimbing. Jangan menyatakan revisi telah diterima tanpa bukti. File proposal asli dalam `sources/` tetap menjadi referensi baca saja.

Rumusan pengganti batasan model yang diusulkan:

> Komponen LLM diakses melalui API pihak ketiga menggunakan alias layanan Qwen3.8-27B. Model dan konfigurasi pemanggilan dibuat identik pada kondisi RAG aktif dan nonaktif. Endpoint, tanggal pengujian, parameter, serta nama model yang dilaporkan layanan dicatat untuk mendukung keterlacakan eksperimen. Identitas bobot model tidak diverifikasi secara independen.

Dalam tujuan penelitian, gunakan rumusan netral seperti "menguji apakah payload dinamis memiliki PSR lebih tinggi". Hasil tidak harus memenuhi dugaan awal bahwa LLM atau RAG unggul.

## 2. Titik awal yang sudah tersedia

| Bagian | Bukti saat ini | Implikasi untuk pekerjaan berikutnya |
|---|---|---|
| Eksperimen formal versi pertama | 99 run selesai dan 990 anotasi VAL-01; PSR utama B 27,78%, C 74,81% | Simpan sebagai hasil versi pertama. Angka ini bukan hasil Qwen API. |
| FPR versi pertama | Undefined karena S10 inconclusive; coverage negatif 66,67% per kelompok | Pertahankan nilainya; jangan mengubah abstention menjadi TN. |
| Pilot analisis v5 r2 | A 23/36 benar; B2/B3 24/36; satu kenaikan disertai trial rekaan | Dataset ini sudah menjadi development. Belum ada bukti kuat manfaat RAG analisis. |
| Uji umum API | Qwen lulus 3/3 soal tunggal dan 9/9 giliran dalam tiga percakapan pendek | Akses dan format dasar terbukti; kemampuan analisis SQLi belum diuji lewat API. |
| Infrastruktur | Discovery ZAP, executor DVWA, retrieval lokal, ledger, dan alur review tersedia | Gunakan kembali komponen yang masih sesuai; perubahan dibuat pada versi baru. |

Model yang diminta adalah `Qwen3.8-27B`. Respons Qwen pada uji umum melaporkan `self-dploy/Qwen3.8-27B`. Penyebutan dalam naskah harus membedakan alias layanan dari identitas model resmi yang belum terverifikasi. Rerata sekitar 11,6 detik pada percakapan umum tidak dipakai langsung untuk memprediksi durasi eksperimen SQLi.

## 3. Desain eksperimen utama yang diusulkan

Untuk tenggat ini, pertahankan penempatan RAG pada generasi dan regenerasi payload sebagaimana desain formal sebelumnya. Analisis respons pada A dan B menggunakan model, kontrak, dan prompt dasar yang sama tanpa retrieval tambahan. Dengan demikian, perbandingan utama mengukur efek konteks RAG pada generasi terhadap hasil dan klaim keseluruhan pipeline.

| Kondisi | Generator | RAG generasi/regenerasi | RAG analisis | Cakupan |
|---|---|---|---|---|
| A | Qwen3.8-27B API | Nonaktif; tanpa akses vector store | Nonaktif | S1-S12 |
| B | Qwen3.8-27B API | Aktif, sumber dan top-k dibekukan | Nonaktif | S1-S12 |
| C | SecLists dengan seleksi dan transformasi terpin | Tidak berlaku | Tidak menggunakan LLM | S1-S9 |

- S1-S9: tiga teknik pada Low, Medium, dan High, sebagai skenario positif.
- S10-S12: tiga teknik pada Impossible, sebagai kontrol negatif.
- Tiga replikasi pipeline R1/R2/R3. Setiap kondisi applicable memiliki sepuluh kandidat logis dan tiga konfirmasi per kandidat.
- Satu pasangan boolean merupakan satu kandidat logis. Jumlah kandidat, konfirmasi, dan request HTTP fisik harus dilaporkan sebagai satuan berbeda.
- Setiap run memakai login baru, reset yang tercatat, verifikasi level dan injection point, serta baseline. Gunakan rotasi kondisi dari jadwal yang dibekukan untuk menyeimbangkan posisi A/B/C.
- A/B memakai backend, format bukti, budget, batas output, retry, dan kebijakan validasi yang sama. Perbedaan perlakuan utama adalah konteks retrieval generasi.
- RAG memakai korpus proposal terstruktur yang telah disetujui, embedding Nomic dan Chroma lokal, dengan top-k awal 2. Pin hash korpus, index, seleksi, query dan chunk yang benar-benar digunakan.
- Korpus analisis v5 rev2 yang menambahkan rujukan PortSwigger tidak otomatis menjadi korpus utama. Basis sumber proposal saat ini adalah OWASP WSTG dan PayloadsAllTheThings. Adopsi korpus atau penempatan RAG analisis yang berbeda memerlukan desain serta narasi metode baru sebelum pengujian hasil utama.

Jika desain ini dipertahankan, jangan menyimpulkan bahwa hasilnya mengisolasi manfaat RAG pada klasifikasi respons. Pengujian RAG analisis menggunakan bukti berpasangan yang sama dapat menjadi studi pendamping terpisah setelah pekerjaan utama selesai; tidak menjadi syarat pengumpulan pada 30 Oktober.

## 4. Paket pekerjaan dan hasil yang dapat diperiksa

### P0. Selaraskan metode dan kesiapan penilaian

1. Siapkan daftar perubahan proposal: backend API, model layanan, topologi lokal ditambah layanan inferensi, keterlacakan versi, dan keterbatasan reproduksi.
2. Ketersediaan validator independen untuk review 25-27 Oktober telah dikonfirmasi peneliti pada 20 Oktober. Ukur waktu review beberapa packet terlebih dahulu dan proyeksikan beban 990 kandidat; jangan menganggap seluruh anotasi cukup dikerjakan pada 27 Oktober saja. Tanggung jawab peneliti adalah menyiapkan paket blind baru dan menerima anotasi; validator memberikan penilaian dan alasan secara mandiri. Pertahankan kriteria inti VAL-01 untuk PSR, tetapi buat review ID dan packet baru dari bukti API. Lihat [protokol review blind Qwen API](protokol-review-blind-qwen-api-2026-10-20.md).
3. Tetapkan ID eksperimen baru, misalnya `qwen38-api-sqli-v2`, beserta ruang data baru. Nama ini masih usulan, belum menjadi rilis formal.

Hasil: draft amendemen, matriks kondisi, jadwal, serta rencana penilaian. Keputusan akademis yang belum selesai dicatat sebagai pending.

### P1. Buat adapter API dan jalur pipeline versi baru

1. Buat client di `development/` yang menghubungkan generasi dan analisis ke `https://api.hcnsec.cn/v1/chat/completions`. Jangan hanya mengganti string model pada fungsi Ollama: transport, envelope respons, opsi runtime dan pencatatan harus disesuaikan.
2. Pertahankan orkestrasi serial LangChain/controller yang sudah tersedia melalui wrapper versi baru. Hindari mengubah modul dan protokol lama yang dipin.
3. Pisahkan konfigurasi provider, base URL, model, timeout dan budget dari kredensial. Key diperoleh dari environment atau input tersembunyi dan tidak masuk manifest atau repository.
4. Catat request hash, prompt version, model diminta/dilaporkan, response ID, waktu, HTTP status, `finish_reason`, token usage, dan respons mentah tersanitasi. Perubahan metadata model yang tidak dikenali menghentikan kelanjutan batch untuk diperiksa.
5. Awali preflight domain pada `temperature=0` dan batas output 1024 token. Uji kecukupannya untuk generasi dan analisis. Jika perlu perubahan budget, lakukan sebelum holdout dan freeze; gunakan batas yang sama pada kedua kondisi. Jangan menyalin `num_ctx` atau `num_predict` Ollama langsung sebagai parameter API.
6. Jangan mengasumsikan dukungan seed, context window, JSON schema, atau perilaku reasoning dari layanan. Verifikasi dukungan yang diperlukan, catat bagian yang tidak diketahui, dan validasi JSON secara lokal. R1/R2/R3 tetap blok eksekusi; seed atau temperature 0 tidak menjamin keluaran deterministik.
7. Nonaktifkan retry transport tersembunyi. Simpan attempt gagal; resume harus memeriksa checkpoint agar request yang sudah selesai tidak terkirim ulang. Regenerasi karena kandidat invalid/duplikat mengikuti budget yang dinyatakan, maksimum dua retry per slot seperti rancangan awal.

Hasil: client dan wrapper versi baru, konfigurasi tanpa rahasia, serta pemeriksaan offline yang mencakup respons rusak, timeout, truncation, metadata model dan resume. Tes tidak memanggil API berbayar.

### P2. Uji kompetensi SQLi dan kualitas pembacaan bukti

1. Gunakan kembali 36 kasus eligible dan enam kasus invalid dari pilot r2 sebagai set diagnosis yang sudah diketahui. Jalankan paling banyak satu analisis Qwen API tanpa RAG per kasus eligible; kasus invalid berhenti sebelum API. Ini bukan holdout atau FPR formal.
2. Ukur verdict, asesmen trial, pembacaan marker/kontrol, perbandingan ambang 1500 ms, trial yang hilang, ID observasi dan konsistensi reason code. Prioritaskan kesalahan yang sebelumnya terlihat: trial rekaan, arah boolean terbalik, dan nilai di bawah ambang yang dianggap memenuhi ambang.
3. Lakukan penyesuaian terbatas pada set development. Simpan setiap versi dan hasil gagal. Kontrak akhir analisis dipilih sebelum membuka hasil set evaluasi baru.
4. Siapkan 18 kasus baru: tiga teknik, tiga kelas bukti kandidat (positive/negative/inconclusive), masing-masing dua kasus. Utamakan bukti HTTP baru yang tersanitasi; kasus gangguan atau trial hilang diberi label sebagai konstruksi uji jika dibuat secara terkontrol. Tambahkan enam kasus input invalid untuk gate.
5. Label referensi dinilai dan dikunci oleh penilai independen sebelum inferensi set baru. Jika penilaian independen belum tersedia, sebut set itu development, bukan holdout independen. Label serta petunjuk ground truth tidak masuk prompt atau retrieval.
6. Kelas bukti kandidat negative berarti keberhasilan payload tidak didukung bukti. Ini bukan otomatis ground truth bahwa injection point tidak rentan. FPR formal menggunakan label skenario Impossible dan keputusan run.
7. Pada set baru, simpan hasil satu kali tanpa tuning ulang. Sebanyak 18 inferensi eligible merupakan rencana, bukan jumlah yang sudah dijalankan. Bukti yang hilang tidak boleh dilengkapi model; pelanggaran struktural harus ditandai sesuai kontrak baru dan respons mentah tetap disimpan.

Hasil: tabel diagnosis lama, dataset baru beserta provenance/label, hasil kelayakan analisis, dan daftar batas kemampuan. Tidak mensyaratkan B harus lebih unggul atau mengubah skor agar RAG terlihat berhasil.

### P3. Periksa generasi payload dan pilot end-to-end

1. Audit kewajiban angka pembeda slot 101-110 pada generator lama. Pada versi baru, identitas kandidat disimpan sebagai metadata dan deduplikasi dilakukan pada struktur payload; angka unik tidak boleh diwajibkan mengubah makna nilai injection point. Uji perubahan ini pada development dan terapkan sama pada A/B.
2. Verifikasi koordinat ZAP, method, helper sesi/cookie pada High, token, baseline dan kontrol dari antarmuka HTTP. Model tidak menerima label level keamanan atau label skenario.
3. Jalankan kontrol executor S1-S12 dan verifikasi pengukuran timing. Waktu panggilan LLM/API dicatat terpisah dan tidak masuk delta HTTP SQLi. Inferensi dan probe tidak overlap.
4. Jalankan satu matriks pilot lengkap: 24 run A/B ditambah sembilan C, total 33 run, sepuluh kandidat per run. Pilot dan formal memakai direktori serta ID berbeda. Hasil pilot tidak digabung ke hasil formal.
5. Periksa pencapaian budget, duplikasi, refusal, truncation, analysis error, input invalid, trial rekaan, dan penyelesaian konfirmasi. Klaim mentah, bukti executor dan label validator tetap tiga keluaran berbeda.
6. Ukur durasi dan penggunaan API pada workload SQLi sesungguhnya. Periksa kecukupan kuota dan jadwal validator sebelum memulai matriks formal. Kegagalan model dan refusal dicatat, tidak diisi dengan payload manual atau SecLists pada A/B.

Hasil: laporan pilot lintas teknik dan level, estimasi durasi/kuota yang bersumber dari pilot, dan paket kesiapan. Perubahan kebijakan kandidat, prompt atau parser pada versi ini harus disebutkan saat membandingkan dengan versi lama; peningkatan tidak boleh diatribusikan hanya kepada pergantian model.

### P4. Bekukan konfigurasi dan jalankan formal versi baru

Sebelum formal, kunci hash kode, parameter, prompt, kontrak, korpus/index, discovery, SecLists, jadwal kondisi, reset, aturan success 3/3, agregasi, abstention, exclusion dan pemulihan attempt. Review desain yang diwajibkan protokol baru harus terdokumentasi sebelum eksekusi. Manifest lama tidak ditulis ulang.

Rencana formal:

| Kondisi | Run per replikasi | Replikasi | Total run | Kandidat logis |
|---|---:|---:|---:|---:|
| A | 12 | 3 | 36 | 360 |
| B | 12 | 3 | 36 | 360 |
| C | 9 | 3 | 27 | 270 |
| Total applicable | 33 | 3 | 99 | 990 |

Terdapat sembilan slot C/Impossible yang tidak berlaku. Sebanyak 990 kandidat memerlukan 2970 konfirmasi logis; jumlah request HTTP fisik lebih besar karena kontrol dan baseline. PSR utama B/C mencakup 540 kandidat; kondisi A boleh dilaporkan sebagai hasil tambahan yang didefinisikan sebelumnya. FPR setiap kondisi LLM memiliki tiga run negatif per replikasi, total sembilan run negatif per kondisi pada tiga replikasi.

Pada A/B terdapat 720 kandidat yang dianalisis. Bila setiap slot kandidat menggunakan satu panggilan generasi, ada sekurang-kurangnya 1440 panggilan LLM untuk formal yang lengkap tanpa retry. Dengan maksimum tiga panggilan generasi per slot, batas konfigurasi itu menjadi 2160 generasi dan 720 analisis, total 2880 panggilan pada attempt terencana. Angka ini tidak mencakup pilot, preflight, atau attempt pengganti yang diinvalidasi; tetapkan batas pemulihan dan anggaran keseluruhan setelah pilot. Banyak saran dalam satu respons tetap dihitung satu panggilan API.

Jangan menjanjikan jam selesai atau biaya sebelum durasi dan kuota domain diukur. Tetapkan batas durasi serta jumlah request sebelum pengiriman. Gangguan provider, HTTP 401/402/429, perubahan model yang tidak dikenali dan korupsi checkpoint menghentikan batch; setiap pemulihan memakai kebijakan yang dibekukan. Jangan fallback otomatis ke model lain.

### P5. Validasi, agregasi dan penulisan

- Ekspor paket blind yang menyembunyikan kondisi dan sumber kandidat, dengan ID acak, bukti serta urutan trial yang dapat diperiksa. Tabel pemetaan internal tidak diberikan kepada validator. Pertahankan bukti yang diperlukan untuk audit waktu dan marker, bukan hanya ringkasan kesimpulan.
- Impor anotasi tanpa mengganti penilaian agar cocok dengan model. Ketidaksesuaian atau bukti belum cukup ditangani dengan prosedur tercatat.
- Hitung PSR/FPR, coverage, analysis error, abstention, kelengkapan, serta hasil per teknik, level dan replikasi. Simpan numerator/denominator agar semua persentase dapat dihitung ulang.
- Tulis Bab 3 pada saat integrasi dan freeze. Tulis metode penilaian dan kerangka tabel Bab 4 sebelum formal; isi hasil setelah validasi. Bab 5 mengikuti data yang benar-benar selesai.
- Laporkan eksperimen lama dan baru secara terpisah. Pada tenggat ini tidak perlu membuka studi banyak model, arsitektur agent baru, atau domain kerentanan tambahan.

## 5. Aturan evaluasi yang dipertahankan

**FPR** memakai `FP / (FP + TN)` pada unit negatif evaluable. Unit utama adalah keputusan run, bukan jumlah trial atau jumlah payload. FP berarti run pada ground truth negatif menghasilkan klaim positive. Payload gagal pada titik rentan tidak otomatis FP; efektivitas payload dinilai melalui PSR. Pemisahan label aktual dan prediksi mengikuti definisi [confusion matrix scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.confusion_matrix.html).

Untuk menjaga pembacaan terhadap versi pertama, FPR utama baru diusulkan tetap ditahan bila seluruh unit negatif terencana belum memiliki keputusan biner yang valid. Laporkan coverage, jumlah abstention dan error. Jangan memaksa inconclusive menjadi negative, menghilangkan unit bermasalah tanpa laporan, atau menyebut rasio pada subset evaluable sebagai FPR seluruh matriks. Kebijakan ketat ini adalah aturan studi, bukan ketentuan universal confusion matrix.

**PSR** memakai jumlah kandidat yang sukses terkonfirmasi 3/3 dan tervalidasi manusia dibagi seluruh kandidat valid dalam run eligible. Bukti 1/3 dan 2/3 bukan sukses dan tetap berada dalam penyebut bila runtime valid. Unit boolean tetap satu pasangan kandidat. Bukti teknis diambil dari respons/kontrol HTTP sesuai teknik, dengan rujukan [OWASP WSTG v4.2 untuk SQLi](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05-Testing_for_SQL_Injection/); angka ambang dan tiga konfirmasi adalah aturan proyek.

Hitung metrik per replikasi lalu mean dan SD sampel. Dengan hanya tiga skenario negatif per kondisi/replikasi, resolusi FPR adalah 33,33 poin persentase bila lengkap. Tiga replikasi pada satu DVWA tidak mewakili banyak aplikasi independen. Hasil 0 FP jika terjadi tidak membuktikan FPR umum nol. Klaim signifikansi atau generalisasi lintas aplikasi tidak dibuat dari desain kecil ini.

Retrieval dan keputusan model diperiksa terpisah: chunk yang relevan belum menjamin verdict benar. Pemisahan relevance retrieval, correctness dan groundedness juga terdapat pada [panduan evaluasi RAG LangChain](https://docs.langchain.com/langsmith/evaluate-rag-tutorial). Penilaian manusia dalam penelitian ini tetap menjadi rujukan; tidak diganti otomatis dengan LLM-as-judge.

## 6. Jadwal menuju 30 Oktober

Tanggal di bawah adalah hari kalender dan mencakup akhir pekan. Kelancaran provider dan ketersediaan peneliti/validator belum dijamin.

| Tanggal | Pekerjaan utama | Hasil minimum hari tersebut |
|---|---|---|
| 20 Oktober | Finalisasi rancangan dan draft perubahan metode; hubungi validator melalui peneliti | Daftar revisi proposal dan kesiapan jadwal review |
| 21 Oktober | Adapter API, wrapper pipeline, pencatatan, pemeriksaan offline | Jalur generasi/analisis versi baru dapat diperiksa tanpa menyentuh frozen code |
| 22 Oktober | Replay diagnosis lama; perbaikan terbatas; persiapan dan review kasus baru | Kontrak kandidat/analisis dan label evaluasi baru siap dikunci |
| 23 Oktober | Evaluasi 18 kasus baru plus enam invalid; kontrol executor S1-S12 | Laporan kelayakan domain dan keputusan kelanjutan yang terdokumentasi |
| 24 Oktober | Pilot lengkap 33 run; ukur durasi/kuota; finalisasi freeze | Paket siap formal atau laporan hambatan yang jelas |
| 25-26 Oktober | Formal R1/R2/R3 sesuai rotasi kondisi; mulai review independen per blok selesai | Rencana 99 run selesai; packet tersedia dan review telah dimulai |
| 27 Oktober | Selesaikan anotasi independen, audit dan agregasi | Tabel metrik baru beserta coverage dan numerator/denominator |
| 28 Oktober | Selesaikan hasil, pembahasan, keterbatasan, kesimpulan dan abstrak | Naskah lengkap untuk pemeriksaan akhir |
| 29 Oktober | Koreksi pembimbing, format, referensi dan audit silang angka | Berkas final siap dikumpulkan |
| 30 Oktober | Pemeriksaan berkas dan pengumpulan | Tidak ada eksperimen baru yang menjadi ketergantungan pengumpulan |

Penulisan latar metode, keterbatasan versi pertama dan kerangka tabel dimulai sejak 21 Oktober. Review paket yang sudah selesai dapat berjalan ketika blok formal berikutnya dieksekusi; jangan membuka kondisi kepada validator untuk mempercepatnya.

## 7. Batas keputusan agar tenggat tetap realistis

**Batas kesiapan utama: 24 Oktober malam.** Formal baru dilanjutkan jika kelayakan domain, budget kandidat, autentikasi/level, serialisasi timing, pencatatan/resume, kuota dan jadwal validasi memadai. Gate ini memeriksa keabsahan dan kelengkapan metode, bukan mensyaratkan RAG lebih bagus.

Jika belum layak, jangan mengurangi jumlah replikasi secara diam-diam, mencampur pilot/formal, menambah retry sampai hasil sesuai harapan, atau menukar backend. Gunakan hasil formal versi pertama yang sudah tervalidasi untuk penyelesaian naskah, dan laporkan percobaan API yang benar-benar selesai sebagai studi pendamping dengan batas cakupannya. Jika hanya sebagian formal versi baru selesai, laporkan sebagai partial dan tahan metrik utama yang belum eligible.

Jika persoalan akademis revisi API belum terselesaikan, nyatakan batas tersebut kepada pembimbing dan jangan mengklaim eksperimen API memenuhi batasan proposal lama. Jalur dokumentasi versi pertama tetap dapat diselesaikan sembari keputusan tersebut dibahas. Tidak ada model alternatif yang otomatis dipilih dalam rancangan ini.

Penurunan FPR atau kenaikan PSR bukan syarat untuk menyelesaikan penelitian. Jangan mengubah ground truth, label, parser atau definisi keberhasilan sesudah hasil formal terlihat. Set yang telah dipakai untuk diagnosis atau tuning tidak disebut holdout independen.

## 8. Pekerjaan pertama yang konkret

Mulai dari dua keluaran: draft revisi metode API dan adapter di `development/`. Setelah keduanya tersedia, jalankan uji SQLi pada kasus development yang sudah dikenal, lalu siapkan evaluasi baru. Tidak perlu mengulang uji percakapan umum yang sudah lulus.

## 9. Acuan yang diperiksa

- [Proposal asli, terutama Bab 1.4 dan Bab 3.4-3.5](../sources/103062300037_I%20GUSTI%20AGUNG%20JELANTIK%20ADITYA%20BASKARA.pdf).
- [Metodologi lokal dan penempatan RAG](metodologi-lokal-2026-10-14.md).
- [Hasil formal dan definisi FPR/PSR terkini](f02-hasil-val01-2026-10-19.md).
- [Hasil serta batas pilot v5 r2](hasil-pilot-analisis-v5-r2-2026-10-20.md).
- [Diagnosis generasi dan analisis setelah formal pertama](rencana-perbaikan-setelah-formal-2026-10-19.md).
- [Hasil uji umum API](../outputs/hcnsec-general-model-check-20261020T083859245179Z/report.md).
- [Hasil uji percakapan Qwen API](../outputs/hcnsec-qwen38-multiturn-20261020T085758633152Z/report.md).
- Dokumentasi primer OWASP, LangChain dan scikit-learn diakses pada 20 Oktober 2026; saran desain dan jadwal dalam dokumen ini merupakan usulan untuk proyek ini.
