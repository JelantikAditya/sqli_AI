# Review progres proyek TA, 12 Oktober 2026

> Snapshot status per 12 Oktober. Perkembangan setelah tanggal ini dirangkum di
> [README](../README.md) dan [rencana penyelesaian aktif](rencana-penyelesaian-2026-10-16.md).
> Temuan dan angka berikut dipertahankan sebagai catatan historis.

## Kesimpulan

Proyek sudah memiliki prototipe lokal yang membuktikan alur discovery ZAP,
generasi Qwen dengan/tanpa RAG, dan eksekusi kandidat untuk satu skenario S1
di DVWA Low. Pipeline adaptif lengkap dan evaluasi penelitian belum selesai.
Belum ada hasil yang mendukung kesimpulan bahwa RAG menurunkan FPR atau
payload LLM mengungguli SecLists.

Konteks pengujian adalah DVWA milik peneliti pada lingkungan lokal terkunci
untuk TA S1 Teknologi Informasi. Cakupan tetap DAST/black-box, empat level
DVWA, tiga teknik SQLi, ablasi FPR, dan perbandingan PSR.

## Dasar dan batas pemeriksaan

- Membaca proposal PDF asli, khususnya Bab 3 halaman tercetak 24-35.
- Memeriksa kode, dokumentasi, korpus, manifest vector store, report ZAP,
  log validation, notebook, Git lokal, dan riwayat chat proyek yang relevan.
- Bukti runtime terbaru yang ditemukan bertanggal 11 Oktober 2026.
- Menjalankan ulang unit test, parsing sintaks, validasi schema offline,
  pencocokan hash, dan compile statis code cell notebook.
- Tidak menjalankan scan, inferensi model, request pengujian, reset DVWA,
  atau pemeriksaan layanan yang sedang hidup.
- Tidak mengubah file pada sources/. Aktivitas di mesin lain yang tidak
  tercermin pada workspace/chat yang dibaca tidak dapat dinilai.
- Template XLSX tersedia; isinya tidak diaudit dan tidak dihitung sebagai
  hasil eksperimen.

## Sudah dikerjakan dan memiliki bukti

| Komponen | Bukti dan batas kesimpulan |
| --- | --- |
| Lab DVWA/MariaDB | Compose tersedia, port web terikat ke 127.0.0.1:4280, image DVWA/database menggunakan digest. Empat level pernah diuji; tidak diperiksa apakah layanan sedang hidup saat review ini. |
| Skenario dan ground truth | Katalog S1-S12 tersedia. Catatan 1 Oktober mendokumentasikan tiga replikasi per skenario: S1-S9 positif dan S10-S12 negatif. Ini baseline target, bukan hasil evaluasi sistem LLM/RAG. |
| Discovery ZAP terautentikasi | Empat report terbaru memiliki inventaris delapan injection point verified, dua per level, mencakup koordinat S1-S12. Form/token Impossible dan helper High ditangani. Discovery ini pasif, bukan baseline deteksi SQLi aktif. |
| Parser dan kontrak data | Ekspor HAR, normalizer, schema, provenance, sanitasi, dan gate input terverifikasi tersedia. Tidak lagi bergantung hanya pada instance alert. |
| Korpus knowledge-level RAG | Sembilan entri JSON, tiga per teknik, dari snapshot OWASP WSTG v4.2 dan PayloadsAllTheThings. Review teknis selesai; review peneliti masih pending. |
| Embedding, Chroma, retrieval | Manifest dan index terstruktur aktif tersedia, dengan bukti runtime lokal Nomic dan retrieval. Index PDF lama merupakan diagnostik awal. |
| Generasi Qwen lokal | Qwen 2.5 7B Q4_K_M sudah menghasilkan kandidat RAG-off/on. Prompt v3 tidak membawa scenario ID, level, atau label ground truth ke model. |
| Smoke integrasi S1 | Pasangan terbaru menggunakan input ZAP Low terverifikasi, seed 42, temperatur 0, context 4096, satu kandidat dan satu replikasi per kondisi. Jalur discovery ke generator dan executor sudah terbukti untuk S1. |
| Protokol pilot lokal | Konfigurasi, validator konfigurasi, dan snapshot tersedia. Matriks direncanakan 99 run: 36 RAG-off, 36 RAG-on, 27 SecLists. Seed 42/43/44 dan usulan budget 10 kandidat per run sudah dicatat. Status belum frozen. |
| Dokumentasi dan versioning | Commit lokal terbaru 07f8616 pada 11 Oktober. Sebelum laporan ini dibuat working tree bersih; HEAD sama dengan origin/main yang tersimpan lokal. Riwayat chat mencatat push berhasil. Remote tidak di-fetch ulang pada review ini. |
| Draft tulisan | Chat "Menulis Bab 1 dan Bab 2" memuat draft Introduction dan Related Work dengan sitasi, termasuk versi Related Work yang dipadatkan untuk paper enam halaman. Ini draft dalam chat, belum naskah final lengkap. |

## Hasil smoke terbaru

Comparison ID: s1-zap-inputs-pilot-20261011.

| Pengamatan S1, Low, error-based | RAG-off | RAG-on |
| --- | --- | --- |
| SQL error baru terhadap baseline | Tidak | Ya |
| Prediksi berdasarkan sinyal aturan | Negatif | Positif |
| Kandidat per kondisi | 1 | 1 |
| Replikasi per kondisi | 1 | 1 |
| Human validation | pending | pending |

Sinyal negatif off hanya berarti kriteria diagnostik error-based tidak
terpenuhi; tidak menetapkan kegagalan semua kemungkinan teknik dari kandidat
tersebut. Sinyal positif on menunjukkan diagnostik SQL, bukan bukti ekstraksi
data. Pasangan sebelumnya memakai prompt/input berbeda dan tidak digabungkan
ke dataset formal. Tidak ada penghitungan FPR/PSR formal pada kedua smoke.

## Masih parsial

1. Validation loop sudah mengeksekusi kandidat dan mendeteksi SQL error,
   marker boolean, serta selisih waktu. Belum ada analisis respons oleh Qwen
   atau feedback untuk regenerasi ketika gagal. Replikasi kandidat yang sama
   berbeda dari loop adaptif yang dijanjikan proposal halaman 26.
2. Tiga konfirmasi kandidat, matched no-delay timing control, pemulihan sesi,
   dan reset per condition-run sudah ditulis dalam protokol tetapi belum
   diterapkan sebagai satu runner lengkap.
3. SecLists memiliki adapter/provenance validator. Belum ditemukan pemilihan
   wordlist yang dibekukan, batch SecLists nyata, atau log eksekusinya.
4. Semua lima keputusan validation yang ditemukan masih pending. Paket review
   dengan kondisi/sumber disembunyikan, validator independen, dan keputusan
   final belum tersedia.
5. Protokol sudah jauh lebih jelas, tetapi pilot seluruh teknik/level, keputusan
   korpus, pemilihan SecLists, kesiapan validator, dan freeze runtime masih
   diperlukan sebelum eksperimen formal.
6. Koneksi Colab/tunnel pernah diverifikasi, dan notebook tersedia. Pipeline
   penuh belum dibuktikan pada Colab. Karena arah aktif sudah lokal, Colab
   merupakan jalur yang ditunda; uraian metodologi perlu diselaraskan dengan
   laptop lokal. Orkestrasi LangChain lokal juga belum terbukti sebagai alur
   penuh apabila komponen ini dipertahankan dalam metodologi.

## Belum selesai atau belum memiliki hasil

- Runner adaptif terpadu dengan budget, histori iterasi, deduplikasi,
  penanganan runtime error, checkpoint/resume, dan reset otomatis.
- Pilot LLM nyata boolean/time dan level Medium/High/Impossible.
- Pembanding SecLists dengan executor serta budget yang sebanding.
- Eksperimen formal 99 run pada matriks pilot, setelah protokol dibekukan.
- Validasi manusia independen dan dataset final yang dapat diaudit.
- Agregasi confusion matrix, FPR dan PSR per kondisi/teknik/level.
- Baseline deteksi SQLi ZAP tersendiri sebagai acuan tambahan proposal.
- Modul penilaian CVSS dan generator laporan akhir.
- Naskah hasil, pembahasan, kesimpulan, dan paper final berbasis data formal.

## Catatan yang memengaruhi validitas penelitian

- Bedakan definisi keberhasilan probe diagnostik error dari ekstraksi data;
  bekukan definisi sebelum pengumpulan data formal.
- Proposal halaman 34 mendefinisikan FP berdasarkan ground truth negatif,
  sedangkan checklist halaman 35 berpotensi memberi definisi berbeda.
  Protokol pilot mempertahankan klaim sistem sebelum review; selaraskan
  penulisan metodologi dan prosedur validator dengan definisi tersebut.
- FPR memerlukan kontrol Impossible. Smoke S1 saja tidak dapat menjawabnya.
  Tersedia sembilan unit negatif per kondisi pada rancangan tiga replikasi,
  berasal dari DVWA yang sama, bukan sembilan aplikasi independen.
- PSR formal hanya S1-S9. Penyebut nol harus dilaporkan tidak terdefinisi.
- Restart container web tidak sama dengan reset volume database.
- Audit dan roadmap awal 11 Oktober berisi status yang telah berubah:
  discovery kini lengkap untuk koordinat katalog, prompt sudah membuang label,
  dan perubahan terbaru sudah di-commit. Acuan terbaru adalah
  progress-local-discovery-2026-10-11.md beserta evidence JSON.

## Pemeriksaan ulang pada review ini

- 32 unit test lulus, exit code 0. Beberapa test memakai mock dan tidak
  menggantikan pengujian model/target nyata.
- 25 file Python lulus parsing sintaks.
- Empat normalized report lulus schema dengan dependency schema lokal.
- Hash empat report dan empat HAR cocok dengan ringkasan evidence.
- Hash log validation pasangan S1 terbaru cocok dengan evidence.
- Tiga log validation: lima keputusan, seluruhnya S1 dan pending.
- Dua notebook: 3 dan 11 code cell lulus compile statis; tidak ada output
  atau execution count tersimpan.
- Interpreter .venv mengeluarkan pesan lokasi Python dasar tidak ditemukan,
  tetapi unit test dan pemeriksaan offline berhasil. Penyebab pesan startup
  belum ditelusuri; jangan menganggapnya kegagalan unit test atau bukti
  runtime eksperimen formal siap.

## Urutan kerja yang paling logis

1. Bangun analisis respons Qwen dan feedback/regenerasi terbatas untuk S1,
   menggunakan discovery terverifikasi serta pencatatan prediksi terpisah.
2. Lengkapi konfirmasi, timing control, sesi/reset dan budget, lalu pilot
   boolean/time dan semua level.
3. Siapkan SecLists dan review manusia yang menyembunyikan kondisi; tetapkan
   review korpus serta selaraskan metodologi lokal.
4. Bekukan runtime/protokol, jalankan matriks formal, dan validasi hasil.
5. Hitung metrik yang dapat ditelusuri ke evidence, kemudian selesaikan
   CVSS, laporan otomatis, hasil/pembahasan, dan paper final.

Tidak diberikan persentase penyelesaian karena bobot milestone belum
ditetapkan. Fondasi teknis sudah terbangun, sedangkan eksperimen dan bukti
untuk menjawab rumusan masalah masih merupakan pekerjaan utama tersisa.
