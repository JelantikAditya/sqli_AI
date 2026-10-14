# Naskah metodologi lingkungan lokal

Tanggal: 14 Oktober 2026.
Status: narasi metode yang ditetapkan, siap dipakai sebagai dasar revisi Bab 3.
Ini bukan laporan implementasi lengkap atau hasil eksperimen formal.
Rujukan operasional: keputusan-metodologi-lokal-langchain-2026-10-14.md dan
local-sqli-v5-pilot. Versi software/model final mengikuti manifest T08.

## Rancangan lingkungan pengujian

Penelitian menggunakan pendekatan Dynamic Application Security Testing
(DAST) dengan akses black-box terhadap Damn Vulnerable Web Application
(DVWA). Target dijalankan pada empat level keamanan, yaitu Low, Medium,
High, dan Impossible. Pengujian dibatasi pada SQL injection error-based,
boolean-based blind, dan time-based blind. Penentuan keberhasilan menggunakan
observasi HTTP, diagnostik basis data yang terlihat pada respons, perbedaan
konten, dan perbandingan waktu respons. Kode sumber aplikasi dan isi basis
data internal tidak digunakan oleh sistem sebagai dasar keputusan serangan.

Lingkungan penelitian disesuaikan dari rancangan dua mesin menjadi satu
laptop lokal. DVWA dan MariaDB dijalankan menggunakan Docker, sedangkan
OWASP ZAP menggunakan container pada jaringan Docker yang sama. Python,
Ollama dan ChromaDB dijalankan pada host laptop. Akses executor ke DVWA
menggunakan alamat loopback, sementara ZAP mengakses service DVWA melalui
jaringan container. Dengan topologi ini, jalur eksperimen aktif tidak memerlukan
Google Colab, network tunnel atau penyimpanan hasil pada Google Drive.
Seluruh artefak pengujian disimpan pada disk lokal dengan dataset pilot dan
formal yang terpisah.

Perangkat lokal yang didokumentasikan pada tahap pengembangan menggunakan
Intel Core i5-11400H, RAM terpasang 16 GB dan NVIDIA GeForce RTX 3050
Laptop GPU dengan VRAM 4096 MiB. CPU/RAM berasal dari catatan pemeriksaan
7 Oktober; GPU/VRAM diperiksa ulang pada 14 Oktober. Spesifikasi ini bukan
jaminan bahwa seluruh model dimuat di GPU. Qwen 2.5 7B dengan quantization
Q4_K_M telah diuji pada pilot lokal sebelumnya. Manifest formal akan mencatat
digest model, versi runtime dan penempatan CPU/GPU yang benar-benar digunakan.
Durasi serta kelayakan keseluruhan matriks ditentukan melalui pilot terpadu.

## Orkestrasi dan pemrosesan LLM

LangChain dipertahankan sebagai lapisan penyusun pipeline LLM yang akan
dijalankan lokal. Chain serial menghubungkan penyusunan konteks dan prompt,
generasi kandidat, serta analisis evidence respons. Controller Python
bertanggung jawab atas urutan eksperimen, budget kandidat, seed, deduplikasi,
retry yang dibatasi, state attempt dan checkpoint/resume. HTTP executor
menangani sesi DVWA, verifikasi level, token/helper, reset database dan
konfirmasi kandidat. Pembagian ini menjaga keputusan pengendalian eksperimen
tetap eksplisit dan dapat ditelusuri melalui ledger.

Model Qwen 2.5 7B dipanggil melalui API Ollama lokal dengan output JSON yang
divalidasi terhadap schema. Pada konfigurasi pilot, temperature ditetapkan 0,
context 4096, batas output 768 token dan seed replikasi 42, 43 serta 44.
Inferensi model dan probe HTTP dijalankan secara serial tanpa overlap.
Pengukuran time-based hanya mencakup waktu request HTTP sesuai kontrol
executor, sehingga waktu inferensi tidak dimasukkan ke indikator delay.
Total durasi pipeline dicatat terpisah untuk penilaian kelayakan operasional.

Knowledge-level RAG menggunakan korpus JSON terstruktur dari OWASP Testing
Guide v4.2 dan bagian SQL Injection PayloadsAllTheThings. Sembilan entri yang
telah direview diubah menjadi embedding dengan nomic-embed-text melalui
Ollama dan disimpan dalam ChromaDB persisten lokal. Struktur entri, prefix
embedding, sumber dan hash index mengikuti kontrak korpus yang sudah tersedia.
Sistem mengambil top-k awal dua entri menggunakan deskripsi injection point
ZAP yang telah diverifikasi, kemudian menyisipkannya sebagai konteks generasi.

Pada kondisi RAG-on, retrieval dilakukan sebelum loop kandidat dan konteks
dipertahankan untuk generasi serta regenerasi berbasis feedback pada run
tersebut. Pada kondisi RAG-off, jalur retrieval dilewati dan vector store tidak
diakses. Analisis respons pada kedua kondisi menerima evidence tersanitasi
yang sama bentuknya tanpa retrieval tambahan. Oleh karena itu, ablasi menguji
kontribusi konteks RAG pada generasi/regenerasi terhadap hasil dan klaim sistem.
Label ground truth, scenario ID dan level keamanan tidak dimasukkan ke prompt.

## Kontrol, pengulangan dan evaluasi

Matriks formal terdiri atas kondisi A, Qwen RAG-off pada S1-S12; B, Qwen
RAG-on pada S1-S12; dan C, SecLists pada S1-S9. Tiga pengulangan pipeline
memberikan 99 condition-run. Pasangan A/B pada replikasi yang sama memakai
seed dan inventaris discovery yang sama. Setiap condition-run menggunakan
login baru, reset database sampel melalui antarmuka setup DVWA, verifikasi
level dan baseline normal. Replikasi dijalankan sebagai blok 1/2/3, masing-masing
mencakup S1-S12 secara numerik. Pada skenario bernomor ganjil, urutan kondisi
adalah ABC/BCA/CAB untuk replikasi 1/2/3; pada skenario genap CBA/ACB/BAC.
Kondisi C dikeluarkan dari eksekusi Impossible. Pola ditetapkan sebelum hasil
formal diketahui, memberi tiap kondisi satu posisi pertama/kedua/ketiga per
skenario positif. Resume melanjutkan jadwal awal tanpa mengacak ulang.

Budget awal adalah sepuluh kandidat logis per condition-run, dengan tepat
tiga konfirmasi valid per kandidat. Satu pasangan boolean dihitung sebagai
satu kandidat; pasangan delay/no-delay merupakan evidence satu kandidat
time-based. Keberhasilan terkonfirmasi mensyaratkan 3/3 indikator positif.
Hasil 1/3 atau 2/3 dicatat sebagai mixed evidence, tetap dalam penyebut PSR
dan tidak dihitung sebagai keberhasilan. Tidak dilakukan konfirmasi tambahan
atau pengulangan run otomatis untuk mengubah hasil bercampur/inconclusive.
Kegagalan runtime menginvalidasi attempt dan mengikuti pemulihan yang tercatat.

Klaim sistem dan status bukti disimpan terpisah sebelum human review. Pada run
dengan eksekusi serta analisis lengkap, sedikitnya satu klaim positif membuat
keputusan run positif. Tanpa klaim positif tetapi terdapat inconclusive,
keputusan tetap inconclusive; keputusan negatif memerlukan seluruh klaim
negatif. Run inconclusive tidak dipaksakan menjadi TN/FN. FPR utama A/B
menggunakan ground truth negatif Impossible dan hanya tersedia jika seluruh
unit negatif terencana memiliki keputusan biner evaluable. Coverage dan
kelengkapan tetap dilaporkan. PSR utama membandingkan kandidat B/C pada
S1-S9 berdasarkan aturan 3/3 dan anotasi validator independen. Metrik dihitung
per replikasi, kemudian diringkas menggunakan mean dan standar deviasi sampel.

Discovery ZAP terautentikasi berfungsi memperoleh koordinat input dan
provenance; passive discovery tidak diperlakukan sebagai baseline deteksi SQLi.
Baseline deteksi SQLi aktif ZAP disiapkan melalui prosedur tambahan pada pilot.
Validasi manusia menggunakan paket evidence yang menyembunyikan kondisi dan
sumber kandidat. CVSS menjadi keluaran pelaporan untuk temuan yang dikonfirmasi,
bukan pengganti FPR atau PSR.

## Batas penerapan naskah

Pada 14 Oktober, helper lokal dan pilot subset sudah tersedia, tetapi chain
LangChain lokal belum terintegrasi dan belum memiliki bukti end-to-end.
Penetapan metode ini menjadi acuan implementasi T02/T05. Naskah akhir harus
menyertakan bukti integrasi dan manifest T08 sebelum menggunakan pernyataan
bahwa seluruh metode telah direalisasikan dan eksperimen formal telah berjalan.
