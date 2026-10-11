# Audit status proyek TA, 11 Oktober 2026

## Kesimpulan

Proyek berada pada tahap **prototipe dengan integrasi lokal terbatas yang sudah terbukti berjalan**. Lab, discovery terautentikasi, korpus terstruktur, embedding, retrieval, generasi Qwen, dan eksekusi kandidat sudah memiliki implementasi. Bukti terbaru mencakup satu pasangan RAG-off/on untuk S1 pada DVWA Low. Pipeline adaptif lengkap dan eksperimen formal untuk menjawab FPR/PSR belum selesai.

Audit ini memperbarui pembacaan status setelah `review-progress-2026-10-11.md`. Review lama mendahului smoke pasangan S1; pernyataannya bahwa belum ditemukan generasi nyata sudah tidak berlaku. Acuan kemajuan setelahnya adalah `progress-2026-10-11.md`, bukti JSON, serta artefak aktual yang diperiksa ulang.

Tidak diberikan persentase penyelesaian karena milestone belum memiliki bobot yang disepakati. Jumlah file dan jumlah test tidak mencerminkan besarnya pekerjaan eksperimen yang tersisa.

## Dasar dan batas audit

- Membaca proposal PDF 38 halaman, terutama Bab 3 halaman tercetak 24-35; kode, notebook, dokumentasi, manifest index, serta hasil lokal.
- Menjalankan ulang unit test dan pemeriksaan sintaks, membaca ringkasan artefak serta memverifikasi hash log terbaru.
- Tidak menjalankan ulang scan, inferensi model, request serangan, atau reset lab. Status layanan sedang hidup tidak diperiksa.
- File di `sources/` tidak diubah. Aktivitas pada Drive, Colab, atau mesin lain yang tidak tercermin dalam workspace tidak dapat dinilai.
- Template XLSX ditemukan di `outputs/ta-experiment-log/`; isi dan formulanya tidak diaudit dan tidak dihitung sebagai bukti hasil eksperimen.

## Pekerjaan yang sudah memiliki bukti

| Komponen | Status aktual | Bukti dan batas kesimpulan |
| --- | --- | --- |
| Rancangan skenario | Tersedia | Katalog S1-S12 mencakup empat level DVWA dan tiga teknik SQLi, label positif/negatif, koordinat request, dan tiga replikasi default. |
| Lab DVWA dan MariaDB | Pernah terverifikasi | Compose, helper, dan dokumentasi tersedia; smoke terbaru membuktikan sesi Low berhasil pada saat run. Empat level dilaporkan sudah diuji sebelumnya. |
| Akses Colab ke DVWA | Pernah terverifikasi untuk koneksi | Catatan 28 September mencakup tunnel bertoken dan pemeriksaan login/level. Ini berbeda dari menjalankan pipeline penuh di Colab. |
| Ground truth | Baseline terdokumentasi | Catatan 1 Oktober mencatat 12 skenario x 3 replikasi: sembilan skenario positif dan tiga negatif. Audit ini tidak mengulang pengujian atau memverifikasi semua respons mentah baseline. |
| ZAP terautentikasi | Discovery pasif terbukti | Empat report normalized mencatat autentikasi verified. Belum merupakan baseline deteksi SQLi aktif yang siap dihitung FPR-nya. |
| Kontrak data dan parser | Implementasi tersedia | Schema, parser report, katalog bersama, batch normalizer, dan log JSONL tersedia. Kelengkapan injection point masih bermasalah. |
| Korpus knowledge-level RAG | Dibangun dan direview teknis | Sembilan entri JSON, tiga per teknik, dari OWASP WSTG v4.2 dan PayloadsAllTheThings. Integritas sumber/schema diuji; keputusan peneliti masih pending. |
| Embedding dan vector store | Memiliki bukti runtime lokal | Nomic dan Chroma memakai index aktif `sqli-knowledge-ec9d1b2feda12dd3`, sembilan entri. Index PDF terdahulu hanya diagnostik. |
| Retrieval | Memiliki bukti terbatas | Artefak retrieval tersedia untuk S1/S2/S3/S8/S9; pasangan terbaru mengambil dua entri error-based. Belum membuktikan kualitas retrieval seluruh skenario formal. |
| Generasi Qwen RAG-off/on | Smoke nyata berhasil | Dua batch kandidat dan dua audit generasi nyata S1 tersedia dengan comparison ID sama, seed 42, temperatur 0, dan context 4096. |
| Eksekusi kandidat lokal | Smoke S1 berhasil | Masing-masing kondisi menghasilkan satu keputusan otomatis positif pada satu replikasi, dengan SQL error baru terhadap baseline. Status manusia masih pending. |
| Pengujian kode | Lulus pada audit ini | 17 unit test lulus; 22 file Python lulus parsing sintaks; code cell dua notebook lulus compile statis. Ini tidak mencakup eksperimen end-to-end seluruh skenario. |

## Pekerjaan parsial dan hambatan utama

### 1. Discovery belum menjadi pemasok input lengkap

Hasil empat report normalized yang diperiksa ulang:

| Level | Kandidat injection point | Cakupan katalog |
| --- | ---: | --- |
| Low | 0 | Tidak ada kandidat normalized |
| Medium | 0 | Tidak ada kandidat normalized |
| High | 1 | Helper blind untuk S8/S9, status unverified |
| Impossible | 0 | Tidak ada kandidat normalized |

Parser mengambil koordinat dari instance alert. Daftar alert tidak otomatis mencakup semua form/request yang berhasil dijelajahi. Smoke S1 memakai `scenario-catalog-smoke`, kemudian mencocokkan form HTTP aktual; belum membuktikan alur ZAP ke generator secara penuh. Inventaris request/input terautentikasi perlu dilengkapi dan diverifikasi untuk seluruh skenario.

### 2. Validation loop belum adaptif sesuai proposal

`dvwa/validation_loop.py` mengeksekusi kandidat yang sudah tersedia dan mendeteksi sinyal dengan aturan error, perbedaan marker boolean, atau ambang waktu. Pengulangan yang ada mengulang kandidat/replikasi. Belum ada analisis respons oleh Qwen dan feedback untuk menghasilkan strategi baru ketika gagal, sebagaimana rancangan halaman 26 proposal.

Untuk time-based, kode membandingkan satu respons kandidat dengan baseline pada setiap replikasi. Kontrol timing dan penanganan jitter pada jalur tunnel perlu dibuktikan sebelum hasil formal diinterpretasikan.

### 3. Runtime Colab penuh belum dibuktikan

Notebook koneksi memiliki tiga code cell dan notebook LangChain sebelas code cell. Keduanya tidak menyimpan output ataupun execution count pada salinan lokal. Dokumentasi terbaru juga menyatakan pipeline Colab belum dijalankan. Runner notebook saat ini hanya menerima batch LLM, sehingga pembanding SecLists belum dapat menggunakan jalur remote yang sama.

### 4. SecLists baru memiliki adapter

Normalizer sudah memeriksa identitas versi, hash file, nomor baris, dan kesesuaian payload. Tidak ditemukan batch hasil maupun log eksekusi SecLists di direktori hasil yang diperiksa. Pemilihan wordlist, pembentukan pasangan boolean, budget sebanding, serta run pembanding masih diperlukan.

### 5. Human validation belum selesai

Semua keputusan validation yang ditemukan masih `pending`: satu smoke manual S1 terdahulu serta dua keputusan LLM dari pasangan terbaru. Evidence S1 sudah menambahkan frasa diagnostik yang disanitasi, tetapi evidence internal masih menunjukkan kondisi RAG. Paket review yang menyembunyikan kondisi, validator independen, justifikasi, dan keputusan akhir belum tersedia.

## Pekerjaan yang belum memiliki hasil atau implementasi lengkap

- Eksperimen formal ablasi RAG pada S1-S12 dengan tiga pengulangan sesuai unit eksperimen yang ditetapkan.
- Eksperimen PSR LLM versus SecLists pada S1-S9, dengan aturan keberhasilan dan budget yang sebanding.
- Hasil validasi manusia final, agregasi FPR/PSR, analisis per level/teknik, serta pembahasan penelitian.
- Baseline deteksi SQLi ZAP tersendiri yang dapat dipertanggungjawabkan sebagai acuan tambahan proposal. Hasil discovery pasif tidak menggantikannya.
- Modul penilaian CVSS dan generator laporan temuan akhir. CVSS merupakan keluaran pelaporan, bukan metrik utama.
- Naskah hasil dan kesimpulan TA berdasarkan eksperimen final; belum ditemukan di workspace yang diperiksa.

## Hal metodologis yang perlu ditetapkan sebelum eksperimen

1. **Keberhasilan payload:** smoke error-based membuktikan sinyal SQL error, belum ekstraksi data. Tetapkan kriteria sukses setiap teknik sebelum menghitung PSR.
2. **Unit pengulangan:** tiga pengiriman payload yang sama berbeda dari tiga pengulangan pipeline dengan generasi ulang. Tetapkan unit, seed, reset, dan batas iterasi.
3. **FPR dan keputusan validator:** proposal halaman 34 mendefinisikan FP berdasarkan ground truth negatif, sedangkan halaman 35 berpotensi memasukkan temuan yang tidak lolos checklist sebagai FP. Selaraskan definisinya; bukti tidak cukup tidak otomatis berarti target ground truth negatif.
4. **Penyebut metrik:** FPR memerlukan kasus negatif; bila FP+TN nol, hasil tidak terdefinisi, bukan 0%. PSR sesuai proposal tidak dihitung untuk Impossible.
5. **Lingkungan formal:** proposal menempatkan Qwen/RAG/ZAP/LangChain di Colab dengan ngrok, sementara bukti terkini terutama lokal dan tunnel terdokumentasi memakai Cloudflare. Putuskan dan dokumentasikan penyelarasan metodologi.
6. **Informasi dalam prompt:** generator lokal menyertakan scenario ID dan level keamanan pada prompt meskipun query retrieval tidak membawa label ground truth/level. Ini perlu diputuskan sebagai bagian protokol black-box karena dapat memberi petunjuk karakter target kepada model. Audit ini tidak menyimpulkan adanya kebocoran label hasil eksperimen.

## Verifikasi yang dilakukan ulang

- `python -m unittest discover -s tests -v`: 17 test, semuanya lulus. Cakupan meliputi korpus, provenance, retrieval, isolasi RAG-off, serta sanitasi evidence; sebagian interaksi model/vector store memakai mock.
- Parsing sintaks: 19 modul pada `dvwa/` dan tiga file test, total 22.
- Compile statis notebook: 3 + 11 code cell; nol output eksekusi tersimpan.
- Dua file validation JSONL: total tiga keputusan, semuanya S1 dan pending; satu manual, satu LLM-off, satu LLM-on.
- Hash log pasangan S1 cocok dengan `docs/evidence/progress-2026-10-11.json`.
- Git: commit terbaru yang ditemukan bertanggal 7 Oktober. Perubahan 11 Oktober pada README/generator dan sejumlah file baru belum di-commit. Kode terbaru ada secara lokal; perlu dicatat dalam versi reproduksibel setelah dirapikan.

## Urutan penyelesaian yang disarankan

1. Tetapkan definisi keberhasilan, FP/TN, unit replikasi, budget, reset, runtime formal, dan keputusan review korpus.
2. Lengkapi input discovery ZAP dan verifikasi koordinat seluruh skenario.
3. Implementasikan analisis respons LLM serta regenerasi dengan batas iterasi yang sama untuk RAG-off/on.
4. Buktikan satu pasangan S1 pada runtime formal dari discovery sampai bukti untuk validator; kemudian smoke boolean/time dan level lain.
5. Lengkapi jalur SecLists, paket review yang menyembunyikan kondisi, dan pencatatan keputusan validator.
6. Jalankan eksperimen formal, validasi manusia, lalu agregasi metrik. Selesaikan CVSS, laporan otomatis, dan pembahasan TA.

Langkah terdekat yang disarankan adalah membekukan protokol evaluasi singkat sebelum memperluas run. Ini mengurangi kemungkinan data yang sudah dikumpulkan harus diulang karena definisi atau unit perbandingannya berubah.
