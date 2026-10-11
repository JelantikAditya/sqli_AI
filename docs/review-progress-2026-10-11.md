# Review progres TA per 11 Oktober 2026

## Kesimpulan

Proyek sudah mencapai prototipe komponen: lab, discovery terautentikasi, korpus knowledge-level RAG, embedding, dan retrieval memiliki bukti pengembangan. Sistem otomatis end-to-end sesuai proposal dan eksperimen untuk menjawab FPR/PSR belum selesai. Belum ada dasar untuk menyimpulkan RAG menurunkan FPR atau payload LLM mengungguli SecLists.

Review ini memeriksa kode, notebook, artefak lokal, dokumentasi, dan proposal PDF pada `sources/103062300037_I GUSTI AGUNG JELANTIK ADITYA BASKARA.pdf`, khususnya Bab 3 halaman tercetak 24-35. File sumber tidak diubah. Bukti runtime terbaru yang ditemukan bertanggal 7 Oktober 2026. Aktivitas pada Drive atau mesin lain yang tidak tercermin dalam workspace tidak dapat dinilai.

## Temuan yang paling memengaruhi penyelesaian

1. **Prioritas tinggi: validation loop belum memenuhi rancangan adaptif proposal.** `dvwa/validation_loop.py:392` memakai indikator tetap untuk error, boolean, dan waktu. Loop di baris 560 hanya mengulang kandidat yang telah disediakan. Tidak ada analisis respons oleh Qwen atau umpan balik ke generator untuk mencoba strategi baru setelah gagal. Proposal halaman 26 meminta kedua perilaku tersebut. Komponen ini baru executor dan pendeteksi sinyal awal.
2. **Prioritas tinggi: discovery belum memberi input lengkap untuk pipeline.** Parser pada `dvwa/parse_zap_report.py:100` menelusuri instance alert, lalu hanya menerima instance berparameter `id` pada koordinat katalog. Empat report normalized menghasilkan nol kandidat untuk Low, Medium, dan Impossible, serta satu kandidat High untuk S8/S9, masih `unverified`. Berhasil crawl tidak otomatis berarti semua injection point terinventarisasi. Dibutuhkan bukti request/form terautentikasi yang lengkap untuk jalur formal.
3. **Prioritas tinggi: evaluasi belum memiliki dataset formal.** Hanya ditemukan satu log validation manual S1 dengan satu replikasi dan `human_validation=pending`. Tidak ditemukan batch generasi nyata RAG-off/on, audit generasi nyata, atau hasil pembanding SecLists dalam direktori hasil yang diperiksa. Retrieval dan smoke JSON bukan data PSR/FPR.
4. **Prioritas tinggi: bukti untuk human validator belum lengkap.** Runner menyimpan indikator, timing, dan hash respons (`dvwa/validation_loop.py:372`), tanpa cuplikan respons yang dapat dibaca validator. Log juga menampilkan `rag_mode` pada baris 363 dan 486. Proposal halaman 35 meminta bukti respons, justifikasi, validator independen, dan kondisi RAG disembunyikan. Log internal boleh tetap mencatat kondisi, tetapi paket review yang disanitasi dan dibutakan serta pencatatan keputusan akhir belum ditemukan.
5. **Prioritas menengah: jalur formal Colab belum terverifikasi.** Notebook telah tersedia, tetapi salinan lokal tidak memuat output eksekusi. Dokumen terbaru juga menyatakan belum dijalankan. Runner notebook secara eksplisit hanya menerima sumber LLM (`notebooks/colab_langchain_setup.ipynb:841`), sehingga SecLists belum dapat melewati jalur remote yang sama.
6. **Prioritas menengah: CVSS dan laporan otomatis belum diimplementasikan.** Proposal halaman 26 dan 34 memintanya sebagai keluaran pelaporan, bukan metrik utama. Tidak ditemukan modul penilaian CVSS atau generator laporan temuan akhir dalam kode yang diperiksa.

## Status setiap komponen

| Komponen | Status | Penjelasan progres dan bukti | Syarat penyelesaian berikutnya |
| --- | --- | --- | --- |
| Cakupan dan rancangan skenario | Tersedia | `experiment_scenarios.json` memuat S1-S12, empat level, tiga teknik, koordinat request, dan protokol tiga replikasi. | Tetapkan unit evaluasi, budget kandidat/iterasi, reset, dan aturan agregasi sebelum run formal. |
| Literatur dan proposal | Dokumen tersedia | Ada proposal 38 halaman PDF dan 14 PDF referensi lain. Bab rancangan menjadi acuan review. | Ketersediaan dokumen tidak membuktikan seluruh kajian pustaka selesai; sinkronkan rancangan dengan implementasi aktual. |
| Lab DVWA dan MariaDB | Terverifikasi sebelumnya | Compose dan helper tersedia; catatan pengujian mencakup login serta Low/Medium/High/Impossible. | Periksa ulang sesi dan konfigurasi ketika eksperimen dimulai. Review ini tidak memeriksa layanan sedang hidup. |
| Koneksi Colab ke DVWA | Terverifikasi sebelumnya | Catatan 28 September membuktikan tunnel bertoken, penolakan tanpa token, login, dan empat level. | Jalankan ulang untuk sesi baru; konektivitas terdahulu tidak membuktikan pipeline Colab penuh. |
| Ground truth | Baseline terdokumentasi | Catatan 1 Oktober melaporkan 12 skenario x 3 replikasi: sembilan positif dan tiga negatif. | Verifikasi kembali setelah perubahan/reset lingkungan dan pertahankan bukti; tidak diuji ulang dalam review ini. |
| ZAP terautentikasi | Selesai untuk discovery pasif | Empat report normalized mencatat autentikasi verified. Dokumen run menjelaskan pemeriksaan login/level. | Baseline deteksi SQLi ZAP tersendiri belum dapat disimpulkan dari passive scan atau screenshot agregat. |
| Parser ZAP dan kontrak data | Parsial | Parser, schema, dan empat hasil normalized ada. Hanya High menghasilkan kandidat S8/S9. | Lengkapi inventaris request/input seluruh skenario dan verifikasi koordinatnya. |
| Korpus knowledge-level RAG | Implementasi tersedia; review belum selesai | Sembilan entri JSON, tiga per teknik, enam komponen proposal, referensi sumber, commit/hash terkunci. `researcher_review` masih pending. | Review ketepatan isi, adaptasi contoh, dan relevansi sembilan entri oleh peneliti. |
| Embedding dan Chroma | Terverifikasi lokal | Bukti 7 Oktober mencatat Nomic 768 dimensi, sembilan entri terstruktur, persistensi, dan index aktif `sqli-knowledge-ec9d1b2feda12dd3`. | Buktikan build/reuse pada runtime formal dan bekukan manifest. |
| Retrieval | Terverifikasi terbatas | Lima retrieval tersedia untuk S1/S2/S3/S8/S9, top-k 2. S1-S3 memakai katalog smoke; S8-S9 memakai report High. | Uji input formal semua skenario serta kualitas konteks. Lima retrieval bukan lima eksperimen end-to-end. |
| Qwen lokal | Smoke berhasil | Artefak `outputs/ollama-local-smoke/smoke-2026-10-07.json` dan catatan menunjukkan Qwen 2.5 7B Q4_K_M menghasilkan JSON pendek. | Uji generasi kandidat nyata dengan konteks RAG dan budget token aktual. |
| Generator RAG-off/on | Kode tersedia; runtime belum dibuktikan | Generator menyimpan prompt, query, provenance, konteks, dan opsi. Unit test pasangan menggunakan respons model tiruan. | Hasilkan pasangan nyata dengan kontrol sama, periksa validitas output dan kecukupan context. |
| Validation runner lokal | Smoke sangat terbatas | Satu file JSONL berisi satu payload manual S1 dan satu keputusan otomatis TP, masih pending. | Uji error/boolean/time pada semua level; lengkapi feedback adaptif sesuai proposal. |
| Pipeline LangChain Colab | Kode tersedia | Sebelas code cell berisi setup sampai runner; compile statis berhasil. | Jalankan notebook pada runtime aktual dan simpan bukti end-to-end. |
| SecLists | Adapter tersedia; eksperimen belum | Normalizer memeriksa commit, hash file, nomor baris, dan isi payload. | Tetapkan wordlist versi tetap, seleksi per teknik, pasangan boolean, serta eksekusi yang sebanding dengan LLM. |
| Human validation | Belum selesai | Status pending sudah disiapkan dalam log. | Siapkan paket bukti yang menyembunyikan kondisi, validator independen, justifikasi, dan keputusan final. |
| FPR dan PSR | Belum dilakukan | Tidak ditemukan hasil agregat formal atau skrip agregasi metrik pada kode yang diperiksa. Ada berkas template spreadsheet; isi/formulanya tidak diaudit pada review ini. | Kumpulkan hasil berpasangan yang seimbang, review keputusan, lalu hitung dan analisis metrik. |
| CVSS dan pelaporan | Belum ditemukan implementasinya | Termasuk keluaran proposal, tetapi belum tampak pada kode. | Implementasikan penilaian beserta alasannya dan laporan temuan setelah validasi. |
| Dokumentasi implementasi | Cukup lengkap; belum laporan akhir | README, kontrak, panduan runner, catatan progres, dan bukti sanitasi tersedia. | Susun hasil eksperimen, pembahasan, keterbatasan, dan kesimpulan penelitian setelah data tersedia. |

## Catatan keselarasan proposal

- Jalur korpus utama sudah sesuai sumber OWASP WSTG v4.2 dan PayloadsAllTheThings. Index 15 PDF/1.950 chunk adalah riwayat diagnostik, bukan korpus final penelitian.
- Proposal menempatkan Qwen, RAG, ZAP, dan LangChain di Colab serta menyebut ngrok. Bukti berjalan saat ini terutama lokal dan koneksi memakai Cloudflare Quick Tunnel. Perbedaan ini perlu dicatat dan diselaraskan dalam metodologi. Smoke lokal tetap berguna sebagai verifikasi pengembangan.
- PSR pada proposal dihitung untuk S1-S9, bukan kontrol Impossible S10-S12. FPR memerlukan kasus negatif; jangan menganggap FPR pada subset seluruhnya positif bernilai nol ketika penyebut FP+TN nol.
- Proposal halaman 34 mendefinisikan FP berdasarkan ground truth negatif, tetapi halaman 35 dapat terbaca menggolongkan semua temuan yang gagal memenuhi checklist validator sebagai FP. Definisi operasional perlu diselaraskan sebelum anotasi agar bukti tidak memadai tidak otomatis menjadi false positive.
- Tiga kali eksekusi payload yang sama belum tentu identik dengan tiga pengulangan pipeline lengkap. Tetapkan apakah generasi, discovery, dan reset diulang pada setiap run, serta cara menyamakan budget antara kondisi.
- Indikator SQL error membuktikan sinyal teknik sesuai protokol saat ini. Arti keberhasilan payload perlu ditetapkan secara eksplisit agar tidak dicampur dengan klaim keberhasilan ekstraksi data.

## Pemeriksaan ulang pada 11 Oktober

- `python -m unittest discover -s tests -v`: 14 test lulus. Cakupan terutama integritas korpus, query, seleksi retrieval, provenance, dan pasangan generator dengan mock; bukan uji serangan end-to-end.
- Parsing sintaks: 20 file Python berhasil.
- Compile statis: seluruh code cell pada kedua notebook berhasil. Tidak ada output eksekusi tersimpan pada kedua salinan lokal.
- Empat report ZAP normalized: Low 0 kandidat, Medium 0, High 1 (S8/S9, unverified), Impossible 0.
- Hasil lokal yang ditemukan: 17 artefak retrieval dan satu log validation manual; tidak ditemukan batch formal LLM/SecLists di direktori hasil yang diperiksa.
- Tidak menjalankan serangan, mereset DVWA, menyalakan tunnel/model, atau mengubah file `sources/`. Keberhasilan layanan runtime saat ini tidak dinyatakan terverifikasi.

## Urutan penyelesaian yang disarankan

1. Selesaikan review sembilan entri dan bekukan definisi operasional evaluasi, unit replikasi, budget, serta lingkungan formal.
2. Lengkapi dan verifikasi injection point yang berasal dari request discovery untuk seluruh skenario.
3. Buktikan satu pasangan S1 RAG-off/on pada runtime formal sampai eksekusi DVWA dan bukti review, termasuk pemeriksaan context token.
4. Lengkapi analisis respons oleh LLM dan regenerasi payload dengan batas iterasi; gunakan protokol dan budget identik untuk kedua kondisi ablasi.
5. Siapkan SecLists pada jalur eksekusi yang sebanding, paket review yang menyembunyikan kondisi, serta penyimpanan bukti respons yang disanitasi.
6. Jalankan eksperimen formal tiga replikasi sesuai protokol: ablasi RAG pada S1-S12 dan PSR LLM/SecLists pada S1-S9. Jangan memasukkan smoke manual sebagai hasil pembanding.
7. Selesaikan validasi manusia, agregasi FPR/PSR, keluaran CVSS, laporan otomatis, dan pembahasan TA.

Tidak diberikan persentase penyelesaian karena belum ada pembobotan milestone yang disepakati. Banyaknya file atau keberhasilan smoke tidak mencerminkan porsi pekerjaan integrasi dan evaluasi yang tersisa.
