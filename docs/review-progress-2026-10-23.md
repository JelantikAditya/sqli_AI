# Review progres proyek TA, 23 Oktober 2026

## Pembaruan setelah snapshot review

Setelah review awal di bawah ini, Q3 v4 dijalankan dan gagal gate kelengkapan:
20/24 unit mencapai kuota penuh. Q4 v5 kemudian dijalankan live dan lulus
qualification: 24/24 unit selesai dengan sepuluh kandidat valid per unit.
Q4 memakai 506 dari batas 960 panggilan API. Semua respons HTTP 200 dan
berakhir `stop`; tercatat 610.910 prompt token dan 70.092 completion token,
atau 5,70% dari plafon completion. Ada 26 percobaan generasi yang ditolak,
namun retry melengkapi semua unit. Bukti ini tidak mendukung dugaan bahwa
kegagalan kuota Q3 disebabkan kekurangan completion token; masalah Q3
konsisten dengan keragaman struktur kandidat. Q4 tetap qualification, dengan
`formal_eligible: false`, dan batas biaya akun Poolside belum diverifikasi.
Rincian ada di [catatan Q4 v5](poolside-laguna-q4-v5-preparation-2026-10-23.md)
dan [audit live](evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json).

**Posisi proyek:** pipeline dan eksperimen formal model lokal sudah selesai
sampai validasi serta agregasi. Hasil tersebut siap digunakan untuk
pembahasan TA, dengan FPR utama tetap undefined. Jalur Laguna telah lulus
qualification v5, tetapi P4 formal tiga replikasi belum dimulai. Sebelum P4,
amendemen metode/API, batas belanja, serta kesiapan DVWA dan protokol formal
masih perlu ditutup. Bagian di bawah mempertahankan snapshot dan roadmap
sebelum Q3 dijalankan.

Review ini memeriksa dokumentasi terbaru sampai handoff 22 Oktober, source
generator aktif, hasil terolah formal, assessment qualification lokal, dan
percakapan proyek yang relevan. Status implementasi dibedakan dari kesiapan
layanan saat akan menjalankan eksperimen baru.

## 1. Bagian yang sudah siap

| Bagian | Status | Bukti dan batas |
| --- | --- | --- |
| Lab dan discovery | Implementasi serta bukti pengujian tersedia | DVWA Low, Medium, High, Impossible; discovery ZAP dan katalog S1-S12. Kondisi sesi, autentikasi, baseline, dan timing perlu diperiksa kembali sebelum run baru. |
| Pipeline DAST SQLi | Sudah dipakai dalam formal lokal | Generasi kandidat, eksekusi error-based/boolean-based blind/time-based blind, tiga konfirmasi, analisis respons, deduplikasi, ledger, checkpoint, serta resume tersedia. |
| RAG dan pembanding | Sudah dipakai dalam formal lokal | Korpus terstruktur, embedding Nomic, Chroma, orkestrasi LangChain, serta batch SecLists dengan provenance tersedia. |
| Formal lokal F01 | Selesai | R1/R2/R3 menghasilkan 99 run completed dan sembilan slot C/Impossible excluded sesuai desain. |
| Validasi dan agregasi F02 | Selesai dengan batas metrik | 990 anotasi VAL-01 tersedia. PSR utama eligible; FPR utama tidak eligible karena abstention S10. |
| Integrasi API | Implementasi dan pengujian tersedia | Gate invalid sebelum API, propagasi penolakan parser, dan kesetaraan profil analisis telah diperbaiki. Temuan pada snapshot awal 22 Oktober tidak lagi menjadi daftar bug aktif. |
| P2 Qwen API | Ditutup dengan keterbatasan | Run-005 menghasilkan 17/18 respons evaluable, agreement 17/17, satu unresolved. Penutupan peneliti tercatat. Tidak perlu membuka kembali P2 untuk melanjutkan jalur Laguna. |
| P2 dan preflight Laguna | Selesai sebagai pengembangan | Agreement 18/18 pada paket yang sudah diketahui; preflight 6/6 kandidat lolos format/kebijakan. Ini belum membuktikan akurasi pada holdout independen. |
| Pilot terpadu Laguna r1 | Selesai sebagai pilot parsial | 27 dari 36 slot lengkap; enam unit A/B gagal kuota dan tiga C/Impossible excluded oleh desain. Sebanyak 270 anotasi buta telah diimpor. |
| Qualification Q1 dan Q2 | Eksekusi serta audit selesai, gate gagal | Q1 lengkap 19/24; Q2 lengkap 21/24. Qualification yang selesai dijalankan belum berarti profil lulus kelayakan formal. |
| Qualification Q4 v5 | Lulus sebagai qualification | 24/24 unit mencapai 10 kandidat; 506 panggilan API. Gate ini tidak menjadikan hasil formal atau eligible. |

## 2. Hasil formal lokal yang sudah dapat ditulis

Sumber utama adalah [ekspor hasil formal](../results/processed/formal-sqli-v1-20261017/README.md)
dan [laporan VAL-01](f02-hasil-val01-2026-10-19.md).

| Kondisi | Success / kandidat PSR utama | Mean PSR | SD sampel | Replikasi |
| --- | ---: | ---: | ---: | ---: |
| B, LLM + RAG | 75/270 | 27,78% | 0,00 poin persentase | 3 |
| C, SecLists | 202/270 | 74,81% | 1,70 poin persentase | 3 |

Selisih mean berdasarkan nilai presisi JSON adalah **47,04 poin persentase**,
dengan SecLists lebih tinggi pada dataset ini. Ini perbandingan deskriptif
pada DVWA, bukan bukti generalisasi ke aplikasi lain.

FPR utama A/B tetap **null/undefined**. Pada setiap replikasi S10
inconclusive, sedangkan S11/S12 menghasilkan dua FP dan nol TN. Coverage
keputusan pada skenario negatif adalah 2/3 atau 66,67%. Abstention tidak boleh
diubah menjadi TN untuk melengkapi skor. Hasil ini belum mendukung klaim
bahwa RAG menurunkan FPR.

Seluruh 990 anotasi berisi 349 success dan 641 failure. Pembilang PSR utama
tetap memakai 540 kandidat B/C S1-S9; 349 success seluruh paket bukan
pembilang PSR utama. Hasil formal lokal tetap terpisah dari pilot API dan
qualification.

## 3. Hambatan jalur Laguna pada snapshot sebelum Q3

[Assessment Q2](evidence/poolside-laguna-qualification-q2-2026-10-22.json)
dan assessment raw lokal cocok mengenai status terakhir:

| Indikator Q2 | Hasil |
| --- | ---: |
| Unit yang menjalani eksekusi | 24/24 |
| Unit mencapai kuota lengkap | 21/24 |
| Kandidat valid | 235/240 |
| Kondisi A tanpa RAG | 12/12 unit, 120/120 kandidat |
| Kondisi B dengan RAG tanpa contoh payload | 9/12 unit, 115/120 kandidat |
| Request API | 504; seluruhnya HTTP 200 menurut audit Q2 |
| Qualification passed / formal eligible | false / false |

Unit belum lengkap adalah B/S7 dan B/S10, masing-masing 9/10 kandidat,
serta B/S11 sebanyak 7/10. Pada S7/S10, JSON tidak valid pada slot terakhir
diikuti dua fallback yang mengulang struktur dari slot 1 dan 9. Pada S11,
duplikasi lintas-slot menghabiskan kesempatan generasi.

Source aktif mendukung diagnosis ini: profil v3 masih memanggil generator
v2, dan `_request_family` memilih dua fallback hanya dari `retry_index`.
Pemilihan family belum memperhitungkan seluruh struktur yang sudah diterima
dalam unit. Parser dengan benar menolak kandidat duplikat; prioritas revisi
adalah generator serta pemilihan fallback.

Semua request Q2 berhasil pada lapisan transport. Bukti ini mengarahkan
perbaikan ke format dan keragaman kandidat, tetapi belum membuktikan RAG
menyebabkan kegagalan atau menurunkan kualitas deteksi. Perbandingan Q1/Q2
masih eksploratif, satu replikasi per profil, tanpa validasi buta baru untuk
menghasilkan PSR/FPR.

## 4. Bagian yang belum siap pada snapshot sebelum Q3

- **Profil v4 dan qualification baru:** belum dibuat atau dijalankan setelah Q2.
- **Amendemen metode formal API:** checklist belum mencatat finalisasi
  perpindahan dari model lokal ke Poolside Laguna beserta batas
  reproduksibilitasnya. Persetujuan mencoba API tidak otomatis menjadi
  persetujuan perubahan metode formal.
- **Freeze P4:** protokol, cohort ID, prompt, retry, parser, batas
  kelengkapan, budget, dependency, korpus/index, dan sumber runtime perlu
  dibekukan untuk versi formal baru.
- **Formal API tiga replikasi:** belum dimulai. Matriks yang direncanakan
  mencakup 99 unit applicable dan 990 kandidat, dengan sembilan slot
  C/Impossible excluded oleh desain.
- **Validasi dan metrik API formal:** memerlukan packet/mapping buta baru,
  anotasi sesuai cakupan, audit, dan agregasi. Anotasi pilot tidak menjadi
  pengganti anotasi formal.
- **Naskah akhir:** bahan Bab 3 dan hasil formal lokal tersedia, tetapi
  naskah final Bab 3-5 tidak ditemukan pada inventaris lokal yang ditinjau.
  Chat "Susun Bab 3" baru memuat usulan kerangka. Kemajuan penulisan di luar
  workspace belum diverifikasi.

## 5. Roadmap pada snapshot sebelum Q3

1. **Revisi generator secara offline pada profil v4 baru.** Pertahankan RAG
   B tanpa `payload_examples`. Perluas family yang relevan dan pilih fallback
   dengan mempertimbangkan structural key kandidat yang sudah diterima.
   Pertahankan batas retry yang ditetapkan atau dokumentasikan perubahan
   kebijakannya sebelum eksekusi. Tambahkan replay yang mereproduksi JSON
   rusak dan duplikasi lintas-slot Q2.
2. **Bekukan plan qualification baru.** Tetapkan ID protokol/cohort, hash,
   budget request/token/biaya/waktu, dan aturan penghentian; lakukan dry-run.
   Jalankan kembali seluruh 24 unit A/B, dengan target masing-masing sepuluh
   kandidat valid. Tiga unit gagal Q2 tidak diisi secara retroaktif.
3. **Tutup kesiapan metode dan lingkungan sebelum P4.** Dokumentasikan
   amendemen model/API, periksa DVWA/autentikasi/level/baseline/timing,
   siapkan discovery ZAP serta sumber terpin, dan tetapkan budget formal
   berdasarkan pengukuran pilot. Gate minimum qualification adalah 24/24;
   kelulusan itu tetap harus disertai gate metode dan lingkungan.
4. **Jika semua gate terpenuhi, jalankan P4 tiga replikasi.** Gunakan dataset
   baru, kemudian validasi buta dan agregasi sesuai protokol. Pertahankan
   hasil lokal, Qwen, pilot Laguna, qualification, dan formal API sebagai
   dataset terpisah.
5. **Mulai penyelesaian naskah dari data yang tersedia sekarang.** Susun Bab
   3 dari implementasi aktual, Bab 4 dari hasil formal lokal, dan Bab 5 dari
   bukti beserta keterbatasannya. Formal API menjadi tambahan hanya apabila
   benar-benar selesai dan perubahan metodenya terdokumentasi.

Roadmap tersimpan menetapkan **24 Oktober malam** sebagai batas kesiapan,
target naskah lengkap **28 Oktober**, koreksi **29 Oktober**, dan pengumpulan
**30 Oktober**. Jika gate API belum tercapai pada batas kesiapan itu, gunakan
hasil formal lokal untuk menyelesaikan naskah dan laporkan pengujian API
sebatas cakupan yang selesai. Keunggulan LLM/RAG bukan syarat keberhasilan
penelitian.

## 6. Dokumentasi yang perlu dirapikan

- README bagian status masih menyebut qualification belum dijalankan,
  padahal Q1 dan Q2 sudah selesai dengan gate gagal. Bagian riwayat Qwen juga
  perlu penanda snapshot yang jelas agar penutupan P2 dan perbaikan integrasi
  terbaru mudah dikenali.
- Narasi F02 menyebut selisih PSR 46,04 poin persentase. Nilai yang benar
  adalah 47,04 berdasarkan ekspor JSON. Data metrik dan anotasi tidak perlu
  diubah.
- Gunakan [checklist Laguna](laguna-formal-test-checklist-2026-10-22.md)
  dan bagian terakhir [progres 22 Oktober](progress-2026-10-22.md) untuk
  melanjutkan kerja. Review awal tanggal 22 adalah snapshot historis.

## 7. Verifikasi pada review ini

- Working tree bersih sebelum review; HEAD `6b00b7b` bertanggal 22 Oktober.
- Empat hash berkas publik formal cocok dengan `provenance.json`:
  dua CSV anotasi serta ekspor metrik JSON/CSV.
- CSV terbaru memiliki 990 baris; jumlah keputusan, summary PSR/FPR, dan
  hasil per replikasi dibaca langsung dari artefak resmi.
- Ledger formal memuat 99 `attempt_completed`, masing-masing 33 pada R1,
  R2, dan R3; sepuluh attempt invalid historis beserta retry tetap tercatat.
- Assessment raw Q1/Q2 dibaca langsung: Q1 19/24 dan 229/240, Q2 21/24 dan
  235/240. Keduanya tetap tidak eligible untuk formal.
- **36 tes Poolside lulus** melalui
  `.venv/Scripts/python.exe -m unittest discover -s development -p 'test_poolside*.py' -q`.
- **12 tes agregasi metrik lulus** melalui
  `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_aggregate_metrics.py' -q`.
- Tidak ada panggilan API/model, request DVWA/ZAP, reset database, atau
  eksperimen ulang pada review ini. Kesiapan layanan langsung belum diuji.
- Review ini menambah laporan ini saja; kode, metrik, anotasi, dan seluruh
  berkas `sources/` tidak diubah. Tidak ada commit atau push.

## Tindak lanjut persiapan P4 setelah review

Bagian review di atas mencatat kondisi saat review berlangsung. Setelah itu,
peneliti meminta persiapan P4 Laguna dilanjutkan. Runner formal, snapshot check,
12 discovery passive, review teknis discovery, preflight DVWA, dan smoke
langsung Poolside sudah dijalankan terpisah. Tidak ada cohort formal yang
dimulai. Status terkini dan bukti yang mengikatnya ada pada
[paket persiapan P4](poolside-laguna-p4-preparation-2026-10-23.md). Setelah
peneliti menyetujui freeze, protocol candidate dibekukan dan release manifest
diterbitkan. Gate terakhir adalah receipt persetujuan eksekusi formal yang
terikat ke hash release; cohort tetap belum dimulai.

## Acuan utama

- [Checklist formal Laguna](laguna-formal-test-checklist-2026-10-22.md).
- [Hasil dan audit Q2](poolside-laguna-qualification-q2-2026-10-22.md).
- [Handoff dan progres terakhir](progress-2026-10-22.md).
- [Hasil formal lokal](../results/processed/formal-sqli-v1-20261017/README.md).
- [Penerimaan VAL-01 dan definisi metrik](f02-hasil-val01-2026-10-19.md).
- [Penutupan P2 Qwen](p2-replikasi-2026-10-22.md).
- [Roadmap dan batas keputusan](rancangan-lanjutan-qwen-api-2026-10-20.md).
