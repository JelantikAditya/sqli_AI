# Rancangan kerja eksperimen lokal TA

Tanggal: 11 Oktober 2026.

## Keputusan lingkungan

Sesuai arahan peneliti, pengujian berikutnya dilakukan pada laptop sendiri. Colab dan tunneling ditunda dari jalur kerja aktif. Target tetap DVWA milik peneliti, pada lingkungan terkunci dan terkendali.

Ruang lingkup tetap DAST/black-box, empat level DVWA, tiga teknik SQLi (error-based, boolean-based blind, time-based blind), FPR untuk ablasi RAG, serta PSR untuk LLM versus SecLists. Perubahan lokasi komputasi dicatat sebagai penyesuaian metodologi; file proposal pada `sources/` tetap menjadi referensi asli.

Komponen lokal: DVWA/MariaDB dan ZAP dalam Docker, Python untuk orkestrasi, Ollama Qwen 2.5 7B, Nomic, Chroma, serta penyimpanan evidence pada disk laptop. Jika LangChain tetap merupakan komponen metodologi, jalankan orkestrator LangChain secara lokal dan gunakan executor DVWA yang sudah ada. Pemindahan lingkungan tidak dengan sendirinya menghapus komponen metodologi tersebut.

## Titik awal

Gunakan korpus JSON dan index terstruktur aktif yang sudah ada. Pertahankan hasil smoke S1 sebagai bukti pengembangan. Bukti tersebut belum menjadi data eksperimen formal.

Hambatan inti: inventaris input ZAP belum lengkap, loop belum melakukan analisis respons dan regenerasi oleh LLM, pembanding SecLists belum dieksekusi, serta paket review manusia dan agregasi metrik belum tersedia.

## Tahapan dan kriteria selesai

| Tahap | Pekerjaan | Keluaran | Kriteria selesai |
| --- | --- | --- | --- |
| 1. Protokol lokal | Tetapkan unit run, indikator sukses, budget, pengulangan, reset, seed, dan definisi metrik; catat keputusan review korpus. | Protokol eksperimen dan manifest konfigurasi. | Tidak ada keputusan evaluasi utama yang berubah setelah melihat hasil formal. |
| 2. Discovery | Ekspor request/form dari sesi ZAP terautentikasi, bukan hanya alert; lengkapi parser dan verifikasi GET/POST, parameter, helper High, serta state/token. | Inventaris injection point dengan provenance dan status verifikasi. | Semua koordinat input yang diperlukan S1-S12 tercakup; nol alert tidak diartikan sebagai nol input. |
| 3. Loop adaptif | Hubungkan discovery, retrieval, generator, executor, analisis respons Qwen, serta regenerasi berbasis kegagalan. | Runner lokal terintegrasi dengan riwayat iterasi. | Kegagalan menghasilkan kandidat berikutnya dengan alasan perubahan yang tercatat; budget, duplikasi, dan kegagalan runtime ditangani. |
| 4. Pembanding dan evidence | Siapkan SecLists versi tetap, adapter teknik, executor yang sama, bukti yang disanitasi, ID review acak, serta pencatatan keputusan validator. | Batch SecLists dan paket review yang menyembunyikan kondisi. | Kedua sumber dapat dieksekusi pada protokol yang sama; validator tidak melihat mode RAG atau sumber kandidat. |
| 5. Pilot | Uji S1, S2, S3; lanjut Medium/High dan kontrol Impossible. Jalankan generator/model nyata. | Laporan pilot dan daftar masalah yang diselesaikan. | Error, boolean, timing, helper High, token Impossible, dan kegagalan sesi ditangani tanpa langkah manual yang tidak tercatat. |
| 6. Eksperimen formal | Bekukan versi, jalankan matriks kondisi dan tiga pengulangan, lalu validasi manusia. | Dataset formal dan ledger kelengkapan run. | Seluruh run valid lengkap; kegagalan infrastruktur diperbaiki/diulang sesuai protokol dan tidak diam-diam dihitung sebagai serangan gagal. |
| 7. Evaluasi dan pelaporan | Hitung FPR/PSR, laporkan jumlah sampel dan hasil per teknik/level; tambahkan CVSS, laporan otomatis, serta pembahasan TA. | Tabel hasil, laporan temuan, dan bahan Bab Hasil/Pembahasan. | Metrik dapat ditelusuri ke log serta keputusan validator dan tidak melampaui cakupan bukti. |

Baseline deteksi SQLi ZAP tersendiri dapat disiapkan sebagai acuan tambahan proposal setelah discovery lengkap. Bedakan dari passive discovery dan dari atribusi kontribusi RAG.

## Usulan protokol awal

Bagian berikut merupakan rancangan yang perlu ditetapkan sebelum run formal, bukan konfigurasi yang sudah diimplementasikan.

### Kondisi dan pengulangan

- A: Qwen tanpa RAG, S1-S12, tiga pengulangan.
- B: Qwen dengan RAG, S1-S12, tiga pengulangan.
- C: SecLists, S1-S9, tiga pengulangan.
- FPR utama membandingkan A dan B. PSR utama diusulkan membandingkan B dan C; A dapat dilaporkan sebagai pembanding tambahan.
- Total matriks: 72 run LLM dan 27 run SecLists, yaitu 99 run skenario-kondisi-pengulangan. Satu run memuat beberapa kandidat dan beberapa request; 99 bukan jumlah request HTTP.
- Ulangi pipeline LLM dari keadaan awal pada tiap pengulangan. Gunakan seed berbeda antarpengulangan dan seed sama untuk pasangan A/B pada pengulangan yang sama, misalnya 42, 43, 44. Seed dicatat; bukan jaminan output selalu identik.
- Gunakan inventaris discovery yang sama untuk pasangan A/B agar input pembanding identik; ekspor bukti baru tiap pengulangan dengan prosedur discovery yang sama. SecLists memakai urutan terpilih yang dibekukan sebelum hasil diketahui.

### Budget dan kontrol

- Usulan awal: 10 kandidat per run, mengikuti batas katalog saat ini; pastikan kelayakan laptop melalui pilot sebelum membekukannya.
- Pada eksperimen PSR, eksekusi budget kandidat yang ditetapkan meskipun kandidat sebelumnya berhasil, agar penghentian dini tidak mengubah penyebut antarkondisi. Mode berhenti setelah berhasil, bila digunakan untuk demonstrasi operasional, dilaporkan terpisah.
- Satu kandidat boolean adalah satu pasangan true/false. Satu kandidat time-based mencakup probe delay dan kontrol tanpa delay, dengan pengukuran ulang yang jumlahnya sama antarkondisi. Catat jumlah request aktual karena kandidat tidak selalu setara dengan satu request.
- Terapkan aturan identik untuk timeout, kandidat duplikat, JSON tidak valid, retry generasi, dan batas request. Kekurangan kandidat terhadap budget dicatat sebagai masalah kelengkapan; jangan diam-diam mengurangi penyebut.
- A/B memakai model dan quantization yang sama, prompt dasar sama, temperatur sama, token limit sama, algoritme analisis respons sama, serta kebijakan feedback yang sama. RAG-on menambahkan konteks retrieval; RAG-off tidak membaca vector store. Setiap penggunaan retrieval selama feedback juga dicatat.
- Bekukan hash korpus, source lock, index, top-k, prompt, script, model, versi paket, serta digest image. Image ZAP saat ini memakai tag `stable`; catat digest aktual untuk run formal.
- Gunakan sesi autentikasi baru dan verifikasi level pada setiap run. Tetapkan mekanisme reset data lewat antarmuka setup DVWA dan cek baseline setelahnya. Restart container web saja tidak mereset volume MariaDB.
- Pisahkan inferensi model dari pengukuran HTTP. Jalankan probe serial; hindari generasi/inferensi bersamaan dengan pengukuran timing. Catat load CPU/GPU dan timeout untuk menjelaskan gangguan laptop.

### Informasi untuk model

Ground truth, outcome yang diharapkan, dan label positif/negatif hanya berada pada evaluator. Usulan default: keluarkan scenario ID dan level keamanan dari prompt generasi/analisis; model menerima metode, path, parameter, teknik yang sedang diuji, serta observasi black-box. Kode saat ini masih menyertakan level pada prompt generator sehingga perlu disesuaikan bila usulan ini dipakai.

State sesi dan token boleh digunakan executor untuk membuat request valid. Jangan membaca source code DVWA atau database internal untuk menentukan keberhasilan serangan; gunakan respons HTTP, konten, dan timing.

## Kriteria keberhasilan dan metrik

| Teknik | Bukti keberhasilan yang diusulkan |
| --- | --- |
| Error-based | Diagnostik SQL baru dibanding baseline dan konsisten ketika diuji ulang. Bedakan quote probe diagnostik dari error pembawa marker/data; laporkan definisi yang dipilih secara eksplisit. |
| Boolean blind | Pasangan true/false pada struktur dan injection point yang sama menghasilkan indikator konten yang konsisten dan berlawanan. |
| Time blind | Delay kandidat melampaui kontrol tanpa delay secara konsisten pada pengukuran ulang; kontrol tidak mengalami delay yang sama. Ambang 1.500 ms saat ini diuji melalui pilot sebelum dibekukan. |

**FPR = FP / (FP + TN).** Usulan unit utama adalah satu keputusan akhir per skenario-kondisi-pengulangan setelah seluruh budget, bukan satu label untuk setiap request. Pada matriks ini tersedia sembilan unit negatif per kondisi LLM, berasal dari tiga skenario Impossible x tiga pengulangan. Skenario/pengulangan berasal dari target yang sama, sehingga tidak boleh diperlakukan sebagai sembilan aplikasi independen.

Simpan prediksi sistem sebelum human review. Validator mengaudit bukti dan penetapan kelas tanpa mengubah klaim positif sistem menjadi negatif hanya karena temuannya ditolak. Jika sistem mengklaim kerentanan pada ground truth negatif, kejadian tersebut tetap dicatat sebagai FP. Tanpa prinsip ini, human filtering dapat membuat FPR tampak nol secara artifisial.

**PSR = kandidat berhasil / kandidat valid yang dieksekusi**, untuk S1-S9. Pasangan boolean dihitung sebagai satu kandidat, dan pengukuran ulang timing sebagai bukti satu kandidat. Kandidat SQL yang ditolak target tetap merupakan percobaan gagal bila request/session valid; kegagalan autentikasi, koneksi, atau baseline dicatat sebagai run tidak valid. Catat terpisah kegagalan generasi dan kelengkapan budget supaya PSR tidak menyembunyikannya.

Jika penyebut FPR atau PSR nol, laporkan tidak terdefinisi. Tidak ditemukannya FP pada dataset kecil tidak membuktikan RAG meningkatkan kinerja; laporkan jumlah FP/TN dan keterbatasan sampel. Selaraskan definisi FP berbasis ground truth dengan checklist validator pada proposal sebelum anotasi.

## Artefak implementasi yang disarankan

Nama berikut merupakan usulan modul baru, belum tersedia:

- `local_experiment_protocol.json`: konfigurasi formal.
- `export_zap_inputs.py` dan penyesuaian parser: inventaris request/form.
- `analyze_response.py` dan `adaptive_validation_loop.py`: analisis serta feedback Qwen.
- `run_local_experiments.py`: orkestrasi kondisi, replikasi, reset, checkpoint, dan resume.
- `build_validator_package.py`: evidence dengan kondisi disembunyikan dan mapping internal.
- `aggregate_metrics.py`: agregasi dengan audit penyebut/kelengkapan.
- Modul laporan/CVSS setelah jalur evaluasi stabil.

Evidence per kandidat memuat koordinat, payload, baseline, cuplikan respons yang disanitasi, timing, prediksi sistem, alasan, serta keputusan validator. Log internal tetap menyimpan provenance lengkap; paket eksternal untuk validator memakai ID acak dan membuang kondisi, sumber, nama file yang membocorkan kondisi, serta label hasil yang diharapkan.

## Pekerjaan berikutnya yang paling konkret

Selesaikan protokol singkat tahap 1, lalu kerjakan **ekspor dan parser injection point ZAP** sebagai perubahan teknis pertama. Setelah Low dan High menghasilkan inventaris yang benar, hubungkan input tersebut ke generator dan bangun loop adaptif untuk S1. Perluas ke S2/S3 setelah alur dan evidence S1 stabil.

Tidak perlu mengulang setup RAG atau memperbesar korpus sebelum pilot menunjukkan kebutuhan. Perubahan korpus setelah eksperimen formal dimulai memerlukan versi eksperimen baru. Waktu tiap tahap diukur dari pilot lokal, bukan diasumsikan dari smoke satu kandidat sebelumnya.
