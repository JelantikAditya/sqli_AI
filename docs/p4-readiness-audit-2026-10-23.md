# Audit kesiapan P4 formal Laguna

Dokumen ini adalah snapshot awal sebelum keputusan metode P4 dan paket runner,
discovery, serta preflight selesai. Status terkini ada pada
[paket persiapan P4](poolside-laguna-p4-preparation-2026-10-23.md) dan
[evidence dry-run terbaru](evidence/poolside-laguna-p4-dry-run-2026-10-23.json).

Tanggal audit: 2026-10-23  
Kesimpulan: **belum siap dimulai**

Qualification v5 sudah lulus, tetapi itu hanya menutup gate kelengkapan generator.
P4 formal masih menunggu keputusan metode, anggaran yang dapat diverifikasi,
plan tiga replikasi yang dibekukan, dan validasi ulang kondisi target. Ada juga
risiko waktu karena situs resmi Poolside menyatakan inference Poolside Platform
akan ditutup pada 31 Oktober 2026. Cakupan penghentian endpoint
`inference.poolside.ai` perlu dikonfirmasi langsung pada akun sebelum P4
bergantung padanya.

## Status setiap gate

| Gate | Status | Bukti dan pekerjaan tersisa |
| --- | --- | --- |
| Qualification generasi | **Lulus** | Q4 v5 menyelesaikan 24/24 unit A/B dengan 10 kandidat per unit. `formal_eligible` tetap `false`. Lihat [assessment Q4](../results/raw/pilot/poolside-s21-p3-q4-v5-20261023/qualification-assessment.json). |
| Cakupan desain | **Terdefinisi, belum dibekukan untuk P4** | Matriks di checklist menetapkan 99 unit applicable dan 990 kandidat untuk tiga replikasi: A/B 72 unit atau 720 kandidat, C 27 unit atau 270 kandidat. Belum ada ID, plan, atau budget P4 tersendiri. |
| Amendemen metode | **Belum siap** | Proposal membatasi model ke Qwen 2.5 7B yang berjalan mandiri dan tanpa API pihak ketiga. Draft amendemen lokal hanya membahas Qwen API HCNSEC, bukan Poolside Laguna S 2.1; keputusan dan persetujuan tertulis spesifik Poolside belum tercatat. |
| Ketersediaan provider | **Risiko tinggi** | Halaman Poolside Platform mengumumkan inference ditutup 31 Oktober 2026. Halaman model hanya menyebut akses API gratis untuk waktu terbatas, tanpa tanggal akhir atau batas akun yang dapat dijadikan dasar budget. Pastikan cakupan shutdown dan kelanjutan endpoint di akun. |
| Budget dan limit akun | **Belum siap** | Budget Q4 adalah qualification P3, bukan P4. Nilai limit belanja akun `null` dan belum diverifikasi. Tidak ada estimasi biaya uang yang sah dari audit token saja. |
| Estimasi kapasitas API | **Tersedia sebagai estimasi awal** | Dengan rasio Q4, P4 A/B diperkirakan memakai sekitar 1.518 panggilan API. Ceiling linear dari Q4 adalah 2.880 panggilan dan 3.686.400 completion token. Ini bukan plafon yang disetujui; hitung ulang setelah aturan formal dibekukan. |
| DVWA dan database | **Lulus pemeriksaan dasar, perlu validasi eksperimen** | Container DVWA dan MariaDB sedang berjalan dengan image digest yang dipin; `mariadb-admin ping` hidup dan `login.php` memberi HTTP 200. Container tidak memiliki healthcheck. Sesi terautentikasi, level keamanan yang aktif, reset, baseline, dan timing belum diverifikasi dalam audit read-only ini. |
| Discovery dan injection point | **Bukti tersedia, perlu dicocokkan ke P4** | Ada 12 normalized discovery ZAP tertanggal 18 Oktober, tiga untuk tiap level. Semua mencatat autentikasi terverifikasi dan dua injection point. Plan P4 harus memetakan file ke replikasi dan memvalidasi bahwa target serta kondisi saat ini masih cocok. |
| Freeze runtime dan data | **Belum siap** | Belum ada freeze P4 untuk prompt, profil analisis, parser, retry, korpus/index, SecLists, dependency, sumber runtime, dan aturan abort. Plan pilot P3 satu replikasi serta budget qualification Q4 tidak menggantikannya. |
| Validasi buta | **Belum siap** | Proses VAL-01 sudah ada, tetapi packet dan blind mapping baru untuk dataset P4 belum ditemukan. Jangan memakai ulang anotasi pilot atau qualification. |

## Dasar estimasi budget

P4 yang tercatat pada checklist membutuhkan 72 unit A/B dan 27 unit C, dengan
10 kandidat valid per unit dan tiga konfirmasi per kandidat. Jadi targetnya 990
kandidat serta 2.970 konfirmasi logis. API hanya diproyeksikan untuk A/B karena
kondisi C menggunakan SecLists.

Q4 mencatat 506 panggilan API untuk 24 unit A/B, atau rata-rata 21,08 panggilan
per unit. Ekstrapolasi linear ke 72 unit A/B menghasilkan sekitar 1.518
panggilan. Budget Q4 mengizinkan maksimum 40 panggilan per unit, sehingga
ceiling perencanaan sementara menjadi 2.880 panggilan. Plafon completion Q4
adalah 1.228.800 token untuk 24 unit; skala linear ke 72 unit menjadi
3.686.400 token. Nilai ini hanya membantu menyusun draft budget. Tambahkan
limit belanja akun, estimasi waktu, stop condition, dan margin retry berdasarkan
plan P4 final sebelum menyetujui eksekusi.

## Tindakan sebelum P4

1. Putuskan bersama pembimbing apakah metode formal benar-benar beralih dari
   Qwen lokal ke Poolside Laguna S 2.1. Catat keputusan, alasan pemicu, cakupan
   provider/model, topologi aktual, dan perlakuan hasil lokal yang sudah ada.
2. Verifikasi apakah API Poolside yang dipakai tetap tersedia sampai seluruh
   run dan pemulihan selesai. Bila tidak ada jaminan, gunakan hasil formal lokal
   sesuai proposal atau susun amendemen baru untuk alternatif yang memang
   dapat dijalankan. Jangan mengganti provider di tengah P4.
3. Tetapkan batas belanja dan penggunaan yang terlihat pada akun/provider.
   Simpan bukti tanpa API key. Tetapkan plafon request, completion token,
   waktu, biaya, dan kondisi abort pada budget P4.
4. Buat ID P4 baru, plan tiga replikasi, budget, aturan kelengkapan dan retry,
   serta freeze hash untuk runtime, prompt A/B, analisis, parser, RAG, SecLists,
   dependency, dan skema ledger. Jalankan dry-run sebelum request pertama.
5. Verifikasi login dan level Low, Medium, High, serta Impossible. Cocokkan
   discovery ZAP 18 Oktober dengan container yang sedang dipin; ambil ulang
   baseline dan pasangan kontrol timing sebelum cohort formal.
6. Buat packet VAL-01 dan blind mapping baru dari dataset P4 setelah kandidat
   terkunci. Audit cakupan anotasi untuk PSR dan seluruh unit negatif A/B untuk
   FPR sebelum membuka mapping.

Jika keputusan metode, limit akun, atau kesinambungan endpoint belum dapat
ditutup dalam jadwal, pilihan yang paling dapat dipertanggungjawabkan adalah
menyelesaikan naskah dari hasil formal lokal dan melaporkan Laguna sebatas
qualification. Q4 tidak menyediakan metrik FPR/PSR formal.

## Referensi bukti

- [Checklist formal Laguna](laguna-formal-test-checklist-2026-10-22.md)
- [Usulan amendemen Qwen API](usulan-amendemen-metode-qwen-api-2026-10-20.md)
- [Audit live Q4 v5](evidence/poolside-laguna-q4-v5-live-audit-2026-10-23.json)
- Proposal asli, `sources/103062300037_I GUSTI AGUNG JELANTIK ADITYA BASKARA.pdf`, halaman PDF 9, 21, dan 25-32. File sumber dipertahankan read-only.
- [Poolside Platform](https://platform.poolside.ai/), notis penghentian inference 31 Oktober 2026.
- [Model Poolside](https://poolside.ai/models), akses API ditandai gratis untuk waktu terbatas; harga dan limit akun tidak ditentukan pada halaman tersebut.
