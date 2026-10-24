# Status dan checklist uji formal API Laguna

- **Pembaruan:** 23 Oktober 2026
- **Status P4 formal:** belum siap. Keputusan arah amendemen telah dicatat,
  tetapi budget akun, kontinuitas provider, runner formal, dan validasi
  lingkungan belum ditutup.
- **Cakupan:** DAST black-box SQL injection pada DVWA untuk error-based,
  boolean-based blind, dan time-based blind. Metrik utama tetap FPR untuk
  ablasi RAG A/B dan PSR LLM terhadap SecLists.

## Pembaruan terbaru, 23 Oktober

- Q3 v4 hanya menyelesaikan 20/24 unit. Q4 v5 berikutnya lulus qualification
  dengan 24/24 unit A/B dan 10 kandidat valid pada setiap unit. Q4 menggunakan
  506 dari batas 960 panggilan; seluruh respons HTTP 200 dan `finish_reason`
  `stop`. Hasilnya tetap bukan data formal. Lihat [audit kesiapan P4](p4-readiness-audit-2026-10-23.md)
  dan [evidence live Q4](evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json).
- Proposal saat ini masih menuliskan Qwen 2.5 7B mandiri. Peneliti memutuskan
  Laguna P4 menjadi cohort formal utama untuk analisis revisi, sementara semua
  hasil formal Qwen lokal harus tetap disimpan dan dilaporkan terpisah.
  Persetujuan pembimbing dilaporkan oleh peneliti; receipt langsung belum
  tersedia. Teks proposal akan diperbarui di akhir penelitian sesuai arahan
  peneliti. Keputusan metode ini belum merupakan freeze protokol atau izin
  eksekusi. Lihat amendemen dan
  [receipt keputusan metode](evidence/poolside-laguna-p4-method-decision-2026-10-23.json).
- Halaman resmi Poolside memberi notis penghentian inference pada 31 Oktober
  2026. Pastikan endpoint project dan account memiliki jaminan ketersediaan
  sampai run serta recovery selesai. Harga tepat dan limit belanja akun belum
  diverifikasi.
- Pemeriksaan lokal read-only menemukan container DVWA dan MariaDB running,
  ping MariaDB hidup, dan endpoint `login.php` merespons HTTP 200. Sesi,
  security level, baseline, dan timing belum diperiksa ulang.
- Ada 12 normalized discovery ZAP tertanggal 18 Oktober, tiga per level.
  Seluruhnya berstatus authentication verified dan mencatat dua verified
  injection point. Bukti tersebut perlu dipetakan ke replikasi P4 dan
  dicocokkan dengan kondisi target terkini.

## Riwayat qualification sampai 22 Oktober

- Koneksi dan smoke kontrak Poolside berhasil. Model yang dilaporkan API
  adalah `poolside/laguna-s-2.1` pada endpoint Poolside.
- Evaluasi pengembangan P2 Poolside memperoleh agreement 18/18 pada paket
  kasus yang sudah diketahui. Preflight generasi menghasilkan 6/6 kandidat
  yang lolos parser dan kebijakan. Keduanya belum merupakan evaluasi formal.
- Cohort P3 pilot `poolside-s21-p3-r1-20261022` menggunakan satu replikasi.
  Semua 524 request API mendapat HTTP 200, tetapi enam dari 24 unit LLM A/B
  tidak mencapai kuota 10 kandidat valid. Unit parsial adalah A/S1, B/S2,
  B/S4, A/S6, A/S7, dan B/S11. Sembilan slot lain dikecualikan atau selesai
  sesuai desain; total 27 slot lengkap dan 9 excluded dari 36 slot.
- Paket review buta pilot telah menerima dan mengimpor 270 anotasi VAL-01:
  146 `failure` dan 124 `success`. Data sumber dan justifikasi tersimpan lokal
  di bawah `results/raw/`.
- Agregasi pilot bersifat diagnostik. PSR C r1 adalah 66/90 atau 73,33%; PSR
  B r1 belum eligible karena S2 dan S4 tidak lengkap. FPR A r1 tercatat 0/3,
  tetapi FPR keseluruhan belum eligible karena hanya satu replikasi dan B/S11
  tidak lengkap. Angka pilot tidak digabung dengan Qwen atau eksperimen formal
  lokal.
- Qualification `poolside-s21-p3-q1-20261022` telah menjalankan 24/24 unit A/B.
  Hasilnya 19 unit lengkap dan 5 excluded, dengan 229/240 kandidat valid.
  Semua 503 request API berhasil pada HTTP 200, tetapi kelengkapan unit tidak
  mencapai gate 24/24. Kondisi A lengkap 12/12; B hanya 7/12.
- Qualification gate gagal, sehingga P4 formal belum eligible. Tidak ada
  FPR/PSR formal dari cohort ini. Rincian unit, penggunaan token, serta sebab
  eksklusi ada di [laporan qualification Q1](poolside-laguna-qualification-q1-2026-10-22.md)
  dan [evidence mesin](evidence/poolside-laguna-qualification-q1-2026-10-22.json).
- Audit retrieval Q1 menemukan sinyal awal bahwa B lebih sering menerima
  percobaan berstatus `no_valid_distinct_candidate` (29 kali dibanding 8 di A) dan memakai kira-kira dua kali token
  prompt generasi per request. Chunk cocok secara metadata teknik, tetapi
  pasangan yang sama digunakan pada empat level per teknik dan seluruh chunk
  memuat contoh payload. Ini belum membuktikan sebab-akibat atau perubahan
  akurasi, karena Q1 tidak melakukan validasi buta dan tidak menghasilkan
  PSR/FPR. Lihat bagian [audit efek retrieval](poolside-laguna-qualification-q1-2026-10-22.md#audit-awal-efek-retrieval-pada-generasi-kondisi-b).
- Qualification Q2 `poolside-s21-p3-q2-20261022` mempertahankan retrieval B,
  tetapi menghapus `payload_examples` dari teks prompt. Seluruh 138 request
  generasi B lulus pemeriksaan ini. Hasilnya 21/24 unit lengkap, 235/240
  kandidat valid, dan tiga unit B excluded: S7, S10, S11. Gate tetap gagal,
  tanpa FPR/PSR; rinciannya ada di [laporan Q2](poolside-laguna-qualification-q2-2026-10-22.md)
  dan [evidence Q2](evidence/poolside-laguna-qualification-q2-2026-10-22.json).
- Audit offline Q2 menemukan S7/S10 gagal setelah JSON tidak valid di slot 10
  dan dua fallback duplikat terhadap slot 1 dan 9. S11 memiliki enam duplikasi
  lintas-slot; slot 8 kehabisan tiga percobaan. Ini menunjuk ke family fallback
  statis dan jumlah bentuk struktural yang terbatas. Detail dan batas
  interpretasi ada di [audit retry Q2](poolside-laguna-qualification-q2-2026-10-22.md#audit-offline-pola-retry-dan-duplikasi).

Rujukan: [hasil Poolside P2 dan preflight](hasil-preflight-poolside-2026-10-22.md),
[hasil P3](poolside-p3-run-2026-10-22.md),
[paket validasi buta](poolside-p3-blind-review-2026-10-22.md), dan
[progres harian](progress-2026-10-22.md). Data mentah, CSV VAL-01, mapping
blind, hasil agregasi terperinci, serta key API tetap lokal dan diabaikan Git.

## Pekerjaan sebelum P4 formal

### 1. Tetapkan perubahan metode

- [x] Catat keputusan peneliti bahwa provider/model pengujian API berubah ke Poolside
  Laguna S 2.1, termasuk endpoint, model yang dilaporkan, tanggal, profil,
  serta batas reprodusibilitas layanan ter-host. Keputusan tertulis di
  [receipt metode](evidence/poolside-laguna-p4-method-decision-2026-10-23.json).
- [x] Catat keputusan peneliti atas perubahan dari model lokal di proposal:
  Laguna menjadi model formal utama untuk analisis revisi dan hasil formal
  Qwen lokal tetap dipertahankan sebagai cohort terpisah. Persetujuan
  pembimbing dilaporkan peneliti, tanpa receipt langsung. Pembaruan teks
  proposal ditunda sampai akhir penelitian sesuai arahan peneliti.
- [x] Tegaskan pelaporan Laguna terpisah dari Qwen lokal dan percobaan Qwen.
  Perubahan provider, model, profil, dan topologi harus dilaporkan bersama;
  selisih hasil tidak boleh diatribusikan hanya pada provider.
- [ ] Bekukan protokol P4 dan catat persetujuan eksekusi formal setelah seluruh
  gate teknis, provider, budget, dan validasi target lulus.

### 2. Bekukan protokol, matriks, dan aturan kelengkapan

- [ ] Tetapkan ID protokol formal dan ID cohort P4 baru. Jangan melanjutkan
  atau menimpa ID pilot.
- [ ] Bekukan kondisi A tanpa RAG, B dengan RAG, dan C SecLists; prompt,
  parameter sampling, batas token, thinking, parser, kebijakan duplikasi,
  jumlah konfirmasi, urutan run, serta aturan penghentian.
- [ ] Bekukan perlakuan untuk output tidak valid, duplikat, error transport,
  unit parsial, abort, dan cohort yang tidak lengkap. Jangan mengganti unit
  gagal secara diam-diam atau menggabungkan pilot ke replikasi formal.
- [ ] Matriks tiga replikasi berisi 99 unit yang berlaku: 72 unit A/B dan
  27 unit C. Targetnya 990 kandidat: 720 A/B dan 270 C. Sembilan slot C pada
  S10-S12 dikecualikan oleh desain, setara dengan 90 kandidat logis.
- [ ] Buat budget baru dari hasil pilot aktual dan limit akun terbaru. Ceiling
  960 request pada berkas pilot hanya berlaku untuk P3 r1, bukan persetujuan
  atau estimasi biaya P4. Tetapkan batas biaya, token, request, waktu, dan
  kriteria abort sebelum eksekusi.

### 3. Tuntaskan risiko kelengkapan generasi

- [x] Audit enam unit parsial dan klasifikasikan penyebab per slot. Semua
  request provider berhasil, sehingga temuan utama pilot adalah kelengkapan
  format dan keragaman kandidat, bukan kegagalan transport API. Lihat
  [audit generasi](poolside-p3-generation-audit-2026-10-22.md).
- [x] Perbaikan offline diberi prompt version dan retry policy baru. Parser,
  kebijakan kandidat, jumlah retry, serta batas payload tetap dipertahankan.
- [x] Plan qualification terpisah mencakup semua level DVWA dan tiga teknik,
  dengan 24 unit A/B serta kriteria kelulusan 10 kandidat per unit. Dry-run
  memvalidasi hash dan estimasi budget.
- [x] Jalankan qualification cohort terpisah dan evaluasi gate kelengkapan.
  Q1 selesai tetapi gagal gate: 19/24 unit lengkap. Hasil tetap terpisah dari
  pilot r1 dan dataset formal.
- [x] Uji profil B retrieval tanpa `payload_examples` pada cohort Q2 dengan ID
  baru. Hasilnya 21/24 unit lengkap, tetapi tiga unit B masih gagal kuota.
- [x] Audit keragaman kandidat dan fallback setelah Q2. S7/S10 menunjukkan
  fallback mengulang bentuk yang telah diterima; S11 menunjukkan duplikasi
  lintas-slot sampai tiga retry habis. Temuan tidak membuktikan efek kausal RAG.
- [x] Revisi dan bekukan family/fallback dengan protocol/cohort ID baru.
  Replay offline dan qualification Q4 v5 selesai; 24/24 unit mencapai kuota
  kandidat valid. Gate ini menutup kelengkapan generator, bukan gate P4 formal.

Qualification terbaru dicatat pada [catatan Q4 v5](poolside-laguna-q4-v5-preparation-2026-10-23.md).
Titik lanjut untuk gate P4 sekarang ada pada [audit kesiapan P4](p4-readiness-audit-2026-10-23.md).

### Persiapan P4 langsung Poolside, 23 Oktober

- P4 memiliki runner fail-closed, plan, budget nol dolar, protocol terpisah,
  tes offline, dan dry-run. Status masih `blocked-not-execution-ready` karena
  kuota serta kontinuitas provider langsung belum terverifikasi, protocol belum
  dibekukan dengan receipt peneliti, dan belum ada release serta persetujuan
  eksekusi hash-bound.
- Snapshot korpus resmi 17 Oktober cocok pada keenam hash. Retrieval B diuji
  pada salinan Chroma sementara dan mengembalikan dua chunk; store aktif tetap
  tidak berubah dan tidak dipakai P4.
- Dua belas discovery P4 yang baru lulus autentikasi, empat level, dan dua
  injection point per report. Review memetakan semua report ke plan formal.
  Observasi out-of-level berasal dari helper cookie input yang sengaja di-seed
  oleh scan passive; semua report melaporkan nol grup alert SQL injection.
- Preflight DVWA P4 lulus dengan satu reset database, empat level terverifikasi,
  serta 20 baseline benign. Direct Poolside smoke berstatus HTTP 200 dan katalog
  saat ini melaporkan Laguna gratis dengan harga nol. Smoke tidak membuktikan
  kuota 2.880 request atau kontinuitas endpoint sampai recovery.
- Laguna ditetapkan sebagai cohort utama dalam analisis revisi; seluruh hasil
  formal Qwen lokal tetap disimpan dan dilaporkan terpisah. Proposal akan
  diperbarui pada akhir penelitian. OpenRouter tidak digunakan untuk P4.
  Rincian gate dan bukti ada di [paket persiapan P4](poolside-laguna-p4-preparation-2026-10-23.md),
  [runner readiness](evidence/poolside-laguna-p4-runner-readiness-2026-10-23.json),
  dan [dry-run](evidence/poolside-laguna-p4-dry-run-2026-10-23.json).

### 4. Verifikasi layanan dan lingkungan eksperimen

- [ ] Sebelum run, verifikasi key hanya dari penyimpanan lokal, endpoint,
  model yang dilaporkan, batas konteks, rate limit, kuota, dan harga saat itu.
  Jangan masukkan key ke Git, log, receipt publik, atau prompt.
- [ ] Bekukan source hash, dependency lock, adapter, prompt, konfigurasi,
  korpus, indeks Chroma, embedding lokal, sumber SecLists, dan skema ledger.
- [ ] Periksa DVWA dan MariaDB lokal, versi, autentikasi, level keamanan,
  reset database, baseline, timeout, serta urutan kontrol S1-S12.
- [ ] Siapkan bukti discovery ZAP segar dan cocokkan cakupan empat level DVWA
  pada tiga replikasi. Rencana awal memerlukan 12 paket discovery, yaitu
  empat level dikali tiga replikasi.
- [ ] Pastikan semua request target tetap menuju DVWA lokal. Penelitian tetap
  dibatasi pada DAST black-box SQLi, bukan XSS atau SAST.

### 5. Jalankan cohort formal dan validasi buta

- [ ] Simpan plan, budget, persetujuan eksekusi, dan hash seluruh input
  sebelum request pertama. Gunakan ID baru dan aturan retry yang telah
  dipreregistrasi.
- [ ] Jalankan tiga replikasi terpisah. Catat setiap request, respons,
  penggunaan token, latency, reset DVWA, status unit, dan alasan eksklusi.
- [ ] Setelah kandidat terkunci, buat paket VAL-01 baru dengan randomisasi
  dan blind mapping baru. Jangan memakai kembali anotasi pilot.
- [ ] Bekukan cakupan anotasi sebelum membuka mapping. Kandidat B/C untuk PSR
  mencakup 540 kandidat pada matriks lengkap; importer harus memvalidasi
  seluruh ID yang memang disertakan dalam paket. Keputusan negatif A/B untuk
  FPR harus tercakup lengkap pada S10-S12 di ketiga replikasi.
- [ ] Impor dan audit anotasi, lalu agregasikan PSR/FPR hanya saat seluruh
  gate cakupan, kelengkapan, dan replikasi terpenuhi.

### 6. Laporkan hasil dan batas interpretasi

- [ ] Laporkan coverage, unit/kandidat yang dikecualikan, error API, latency,
  token, dan hasil setiap replikasi bersama PSR/FPR.
- [ ] Pertahankan hasil lokal, Qwen, pilot Laguna, qualification, dan P4
  sebagai dataset terpisah. Jangan menyebut satu pilot sebagai hasil formal.
- [ ] Nyatakan bahwa endpoint ter-host dapat berubah, termasuk routing,
  model alias, metadata, kuota, dan harga. Simpan respons metadata tanggal
  pengujian tanpa credential.
- [ ] Tulis metode serta hasil TA berdasarkan implementasi dan data yang
  benar-benar tervalidasi. Jika gate API belum tercapai, laporkan P4 belum
  selesai dan gunakan hasil formal lokal sesuai batas proposal.

## Gerbang mulai P4

P4 siap dimulai setelah amendemen metode terdokumentasi, profil generasi dan
aturan kegagalan dibekukan, kualifikasi kelengkapan lulus, budget/limit akun
disetujui, lingkungan DVWA lolos pemeriksaan, dan plan tiga replikasi beserta
paket review VAL-01 dapat direproduksi dari hash yang dipin.
