# Review progres proyek TA, 22 Oktober 2026

> Ini adalah snapshot sebelum replikasi P2 terakhir dan eksperimen Poolside
> Laguna. Gunakan [catatan progres terbaru](progress-2026-10-22.md) dan
> [checklist uji formal Laguna](laguna-formal-test-checklist-2026-10-22.md)
> untuk status setelah snapshot ini.

**Posisi proyek:** pipeline DAST SQLi dan eksperimen formal model lokal sudah
selesai sampai validasi serta agregasi. Pengembangan Qwen API berada pada P2
yang belum ditutup dan P3 yang baru menyelesaikan audit offline. Eksperimen
formal API belum dimulai. Penyelesaian analisis dan naskah TA masih menjadi
pekerjaan utama yang tersisa.

Review ini membaca berkas proyek, hasil terolah, receipt, kode callback,
proposal asli dan percakapan proyek yang relevan. Checkpoint eksperimen
terakhir yang ditemukan bertanggal 21 Oktober. Tidak ada request API, DVWA,
atau inferensi baru dalam review ini; kondisi layanan pada 22 Oktober belum
diuji. Berkas di `sources/` hanya dibaca.

## 1. Status berdasarkan bukti

| Area | Status | Bukti dan batas |
| --- | --- | --- |
| Lingkungan dan discovery | Implementasi serta bukti historis tersedia | DVWA empat level, discovery ZAP S1-S12, executor tiga teknik, kontrol baseline dan timing tersedia. Kesiapan sesi aktual perlu diperiksa sebelum run baru. |
| RAG dan orkestrasi lokal | Sudah dipakai dalam formal lokal | Korpus proposal, embedding Nomic, Chroma, loop generasi/analisis, deduplikasi, ledger dan checkpoint tersedia. |
| Formal lokal F01 | Selesai | R1/R2/R3: 99 run completed dan sembilan slot C/Impossible excluded. |
| Validasi dan agregasi F02 | Selesai | 990 anotasi terbaru VAL-01, PSR utama eligible pada 540 kandidat B/C S1-S9; FPR utama undefined sesuai protokol. |
| Pengembangan analisis/RAG v1-v5 | Pilot dan audit tersedia | Belum menghasilkan bukti kuat penurunan FPR. V5 r2 adalah kasus sintetis, terpisah dari formal. |
| P0, penyesuaian metode API | Sebagian | Draft amendemen tersedia. Peneliti melaporkan pembimbing setuju mencoba API; penerimaan formal amendemen belum terdokumentasi. |
| P1, adapter API | Implementasi dan pilot terbatas tersedia | Client, konfigurasi, checkpoint, parser serta wrapper tersedia. Dua celah integrasi dan perbedaan profil analisis masih menghalangi kesiapan pilot lengkap. |
| P2, kompetensi analisis API | Belum ditutup | 14/18 respons evaluable, agreement 14/14; empat unresolved. Estimasi milestone 80% hanya berlaku untuk P2. |
| P3, generasi dan pilot terpadu API | Audit offline selesai; pilot lengkap belum dijalankan | 179 tes historis lulus; 13/16 pemeriksaan audit lolos. Draft 33 run applicable lolos dry-run. Pilot S1 B/C terpisah sudah ada. |
| P4, formal API | Belum dimulai | Rencana 99 run, 990 kandidat, tiga replikasi belum dieksekusi. |
| P5/F03, pelaporan dan naskah | Belum dapat dinyatakan selesai | Data formal lokal dan bahan metode tersedia. Tidak ditemukan artefak naskah akhir Bab 3-5 dalam inventaris lokal yang ditinjau; penulisan di luar workspace belum diverifikasi. |

## 2. Hasil yang sudah dapat dilaporkan

### Formal model lokal

| Kondisi | Sukses/kandidat PSR utama | Mean PSR | SD sampel |
| --- | ---: | ---: | ---: |
| B, LLM+RAG | 75/270 | 27,78% | 0,00 poin persentase |
| C, SecLists | 202/270 | 74,81% | 1,70 poin persentase |

Pada dataset ini SecLists lebih tinggi secara deskriptif sekitar 47,04 poin
persentase. Angka ini memakai nilai presisi pada ekspor JSON, bukan selisih
angka tampilan yang sudah dibulatkan. Dokumen F02 saat ini menyebut 46,04 poin
persentase; itu salah hitung dalam narasi dan perlu dikoreksi tanpa mengubah
data atau metrik sumber.

FPR utama A/B tetap null/undefined karena S10 inconclusive pada semua
replikasi. Coverage negatif adalah 2/3 atau 66,67%; S11 dan S12 menghasilkan
FP. Rasio pada subset evaluable bukan pengganti FPR utama yang ditahan oleh
aturan studi. Data ini belum mendukung klaim bahwa RAG menurunkan FPR.

### Pengembangan dan pilot API

- P2 run-001: agreement 14/14 pada respons yang dapat dinilai, dengan coverage
  14/18 atau 77,78%. Coverage per label tidak seimbang: positive 6/6,
  negative 3/6, inconclusive 5/6. Keempat kasus unresolved harus tetap tampak
  dalam laporan. Agreement ini bukan bukti akurasi 100% untuk seluruh paket,
  dan bukan FPR/PSR formal.
- P2 run-002, run-003, run-004: setiap run berhenti pada request pertama akibat
  HTTP 503 `system_cpu_overloaded`, tanpa jawaban analisis baru. Request singkat
  `API_OK` sempat berhasil pada 21 Oktober 20:34 WIB; batch P2 20:36 WIB kembali
  ditolak. Ini bukti gangguan operasional saat itu, bukan kesalahan reasoning
  dan bukan pemeriksaan ketersediaan layanan hari ini.
- Pilot S1 Low B/C: B menghasilkan 3/10 sukses terkonfirmasi dan C 2/10.
  Review peneliti dilakukan setelah laporan terlihat. Satu skenario dan satu
  replikasi ini belum membuktikan keunggulan API dan bukan PSR formal.
- Pilot analisis lokal v5 r2: A benar 23/36, B2/B3 24/36. Kenaikan satu kasus
  disertai trial rekaan; klaim positive keliru pada referensi negative tetap
  enam per profil. Kenaikan akurasi kecil ini belum membuktikan manfaat RAG
  yang andal.

## 3. Temuan dan prioritas perbaikan

| Prioritas | Temuan | Tindakan dan kriteria selesai |
| --- | --- | --- |
| 1 | P3-02: penolakan struktural parser dapat menjadi `completed` | Periksa status parser sebelum normalisasi. Trial rekaan dan referensi lintas trial harus menghasilkan status analisis error/invalid dan tidak menjadi keputusan biner valid. Respons mentah tetap diarsipkan; verdict salah yang lolos struktur tetap dinilai sebagai kesalahan model. |
| 1 | P3-01: bukti runtime/baseline invalid masih mencapai API | Pasang gate sebelum penyusunan/pengiriman request. Tes integrasi harus menunjukkan nol panggilan API untuk kedua jenis input invalid, dengan record `runtime_invalid` tanpa keputusan model. |
| 2 | P3-03: profil analisis P2 dan pilot berbeda | Satukan builder pesan dan konfigurasi, atau validasi profil pilot secara terpisah. P2 memakai envelope berbeda dari pilot yang mengirim `enable_thinking=false`; agreement lama belum otomatis memvalidasi profil pilot. |
| 2 | Empat kasus P2 unresolved dan provider gagal melayani replikasi | Catat keputusan penutupan P2 dengan keterbatasan, atau gunakan run/addendum baru dengan ID dan budget eksplisit. Pertahankan semua run; jangan menggabungkan replikasi pada kasus sama sebagai sampel independen baru. |
| 2 | Perubahan backend belum selesai pada naskah metode | Finalkan cakupan amendemen API, identitas alias layanan, perubahan topologi dan batas reproduksibilitas. Proposal asli masih menetapkan Qwen 2.5 7B mandiri tanpa API pihak ketiga. |
| 2 | Insiden credential sudah tercatat; rotasi belum terverifikasi | Konfirmasi pencabutan dan penggantian key terdahulu sebelum request API berikutnya, sesuai catatan insiden yang sudah ada. Nilai key tidak dibaca atau dicantumkan dalam review ini. |
| 3 | Salah hitung selisih PSR pada narasi F02 | Koreksi 46,04 menjadi 47,04 poin persentase pada laporan yang mengutip selisih tersebut. Pertahankan ekspor dan anotasi sumber. |
| 3 | Beberapa instruksi roadmap masih historis | Perbarui langkah kerja aktif agar tidak kembali meminta pembuatan adapter atau diagnosis lama yang sudah tersedia. Pertahankan catatan historis dengan penanda waktunya. |

Lokasi kedua celah integrasi adalah
`development/run_qwen_api_experiments.py`, fungsi `make_analysis_callback`
mulai baris 373. Callback memanggil API di baris 382 dan meneruskan
`model_output` ke normalizer di baris 399 tanpa gate status parser.
Kode runtime tidak diubah oleh review ini.

## 4. Urutan kerja berikutnya

1. **Kerjakan offline terlebih dahulu:** perbaiki P3-01/P3-02 pada versi
   development baru, tambahkan tes integrasi yang mereproduksi kedua celah,
   lalu selaraskan atau validasi profil P3-03. Snapshot lama tetap dipertahankan.
2. **Tutup keputusan P2 dan metode:** tentukan perlakuan empat unresolved,
   finalkan amendemen serta budget pengumpulan berikutnya. Konfirmasi rotasi
   credential yang sebelumnya tercatat bermasalah.
3. **Setelah layanan siap:** smoke generasi terisolasi dan kontrol executor
   S1-S12 dengan login, level, form/token, baseline serta timing aktual.
4. **Pilot lengkap P3:** 33 run applicable, tiga slot C/Impossible excluded,
   330 kandidat dan 990 konfirmasi logis. Ukur durasi, token/kuota serta beban
   review independen sebelum menyetujui freeze formal. Rencana A/B memerlukan
   minimum 480 dan worst-case 960 request API pada attempt terencana.
5. **Jika gate siap:** bekukan versi baru dan jalankan formal API tiga
   replikasi, kemudian anotasi blind dan agregasi. Hasil formal lokal dan API
   dilaporkan terpisah.
6. **Lanjutkan penulisan sejak sekarang:** Bab 3 berdasarkan implementasi
   aktual, Bab 4 dari hasil formal lokal yang sudah tervalidasi, dan Bab 5
   mengikuti bukti. Jadikan data API tambahan hanya sejauh benar-benar selesai
   dan sesuai keputusan metode.

Roadmap yang sudah tersedia menetapkan batas kesiapan **24 Oktober malam**,
target naskah lengkap **28 Oktober**, koreksi **29 Oktober**, dan pengumpulan
**30 Oktober**. Jika versi API belum siap pada batas tersebut, gunakan jalur
penyelesaian naskah dari formal lokal dan laporkan percobaan API sebagai studi
pendamping sesuai cakupan yang selesai. Hasil negatif tetap hasil penelitian
yang sah; keunggulan LLM/RAG bukan syarat menyelesaikan TA.

## 5. Verifikasi review ini dan batasnya

- Working tree bersih sebelum review; commit terakhir lokal `bb0008a`,
  21 Oktober 2026 21:00 WIB. Review ini tidak melakukan commit atau push.
- Seluruh 31 file pada `source_sha256` audit P3 masih cocok. Ini mendukung
  bahwa temuan audit berlaku pada source saat ditinjau.
- Empat hash berkas publik formal cocok dengan provenance; CSV anotasi terbaru
  memiliki 990 baris. Mean PSR dan status FPR dibaca langsung dari JSON resmi.
- Dua belas hash artefak pada receipt P2 run-002/003/004 cocok dengan berkas
  lokal. Ketiganya tetap `halted`, satu request mulai dan nol keputusan model.
- Angka 179 tes serta preservasi 1.080 file adalah hasil audit 21 Oktober,
  bukan suite yang dijalankan ulang hari ini. Review ini memeriksa hash source
  audit, bukan menghitung ulang seluruh inventory preservasi 1.080 file.
- Tidak ada persentase penyelesaian seluruh TA yang dibuat karena bobot
  implementasi, eksperimen, validasi dan penulisan belum didefinisikan.

## Acuan

- [Progres 21 Oktober](progress-2026-10-21.md)
- [Hasil formal dan anotasi VAL-01](f02-hasil-val01-2026-10-19.md)
- [Ekspor metrik formal](../results/processed/formal-sqli-v1-20261017/metrics.reviewed.json)
- [Audit offline P3](audit-p3-offline-2026-10-21.md)
- [Evidence audit P3](evidence/p3-offline-audit-2026-10-21.json)
- [Replikasi P2](p2-replikasi-2026-10-21.md)
- [Pilot pembanding S1 B/C](evidence/qwen-api-vs-seclists-s1-pilot-2026-10-21.md)
- [Pilot analisis v5 r2](hasil-pilot-analisis-v5-r2-2026-10-20.md)
- [Roadmap API dan tenggat](rancangan-lanjutan-qwen-api-2026-10-20.md)
- [Catatan insiden credential](evidence/qwen-api-b-pilot-attempt-incident-2026-10-21.md)
- Proposal asli: `sources/103062300037_I GUSTI AGUNG JELANTIK ADITYA BASKARA.pdf`,
  halaman PDF 9, Bab 1.4 butir 4.
