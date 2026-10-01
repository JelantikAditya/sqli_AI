# Catatan baseline OWASP ZAP — 1 Oktober 2026

## Cakupan dan batas interpretasi

- Target tunggal: DVWA lokal melalui `http://dvwa` pada jaringan Docker `dvwa_default`.
- Image: `ghcr.io/zaproxy/zaproxy:stable`.
- Mode: ZAP Baseline Scan, spider satu menit dan passive scan; tidak mengirim payload serangan aktif.
- Crawl tidak diautentikasi. ZAP hanya menjangkau 10 URL di sekitar halaman login.
- Karena halaman SQLi memerlukan login, hasil ini **bukan** pemeriksaan SQLi dan ketiadaan alert SQLi bukan bukti bahwa titik uji aman.

## Hasil awal

| Ukuran | Hasil |
| --- | ---: |
| URL terjangkau | 10 |
| PASS | 54 |
| WARN | 13 |
| FAIL | 0 |
| Alert SQL Injection | 0 |

Peringatan yang muncul terutama terkait header keamanan, atribut cookie, informasi server, dan konfigurasi lintas origin. ZAP melaporkan temuan sebagai peringatan baseline; semuanya perlu triase terhadap tujuan eksperimen sebelum dihitung sebagai kerentanan SQLi. Laporan HTML dan JSON lengkap berada lokal di `results/zap/` dan dikecualikan dari commit.

## Matriks ground truth proposal

Matriks ini mengikuti 12 skenario di proposal (Bab 3, Tabel 3.2). Validasi black-box tiga replikasi per skenario mengonfirmasi label untuk instance DVWA yang diuji; rincian metode dan batas interpretasi ada di [laporan ground truth](ground-truth-2026-10-01.md).

| ID | Level DVWA | Kelas | Modul DVWA untuk dipetakan | Ground truth proposal | Replikasi |
| --- | --- | --- | --- | --- | ---: |
| S1 | Low | Error-based | SQL Injection (`/vulnerabilities/sqli/`) | Positif | 3 |
| S2 | Low | Boolean-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S3 | Low | Time-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S4 | Medium | Error-based | SQL Injection (`/vulnerabilities/sqli/`) | Positif | 3 |
| S5 | Medium | Boolean-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S6 | Medium | Time-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S7 | High | Error-based | SQL Injection (`/vulnerabilities/sqli/`) | Positif | 3 |
| S8 | High | Boolean-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S9 | High | Time-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Positif | 3 |
| S10 | Impossible | Error-based | SQL Injection (`/vulnerabilities/sqli/`) | Negatif / kontrol | 3 |
| S11 | Impossible | Boolean-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Negatif / kontrol | 3 |
| S12 | Impossible | Time-based blind | SQL Injection blind (`/vulnerabilities/sqli_blind/`) | Negatif / kontrol | 3 |

## Crawl terautentikasi dan peta injection point

Database sampel diinisialisasi ulang melalui halaman setup DVWA karena login
awal gagal; smoke test proyek setelahnya mengonfirmasi login serta level Low,
Medium, High, dan Impossible. ZAP menggunakan form authentication dengan
CSRF field DVWA (`user_token`) dan akun lokal default. Templat tanpa kredensial
ada di [`dvwa/zap-auth.template.yaml`](../dvwa/zap-auth.template.yaml); nilai
kredensial diberikan melalui environment saat runtime. Spider menemukan 41 URL
dalam konteks yang dibatasi; laporan passive scan berisi 12 alert umum pada
halaman login dan dua modul SQLi. Tidak ada alert SQLi, sesuai batas scan pasif;
tidak dijalankan active scan atau payload SQLi.

Validasi form pada level Low dan Impossible mengonfirmasi request dasar berikut:

| Modul | Path | Method | Parameter input | Tombol submit |
| --- | --- | --- | --- | --- |
| SQL Injection | `/vulnerabilities/sqli/` | GET | `id` | `Submit` |
| SQL Injection blind | `/vulnerabilities/sqli_blind/` | GET | `id` | `Submit` |

Pada Medium, modul memakai POST dengan field `id` berupa select. Pada High,
halaman SQLi membuka helper `session-input.php` (POST `id`), sedangkan halaman
blind membuka `cookie-input.php` (POST `id` yang disimpan sebagai cookie).
Untuk mengatasi popup JavaScript yang luput dari spider tradisional, kedua URL
helper kini dimasukkan sebagai seed eksplisit dalam template ZAP; Client Spider
juga dijalankan pada dua modul untuk mencoba menelusuri interaksi berbasis DOM.
Catatan koreksi verifikasi (1 Oktober 2026): respons HTTP 200 dari request
pengaturan level sebelumnya tidak membuktikan bahwa sesi ZAP berhasil login
atau bahwa level High tersimpan. Pemeriksaan terbaru pada halaman `security.php`
tidak menemukan indikator login `Logout` maupun teks level aktif High.
Penyebab yang teridentifikasi: DVWA memakai CSRF token `user_token`, yang belum
ditangani dengan benar pada autentikasi ZAP. Percobaan browser authentication
headless juga belum lolos pemeriksaan tersebut. Karena itu angka URL dan alert
dari crawl sebelumnya hanya bukti URL terjangkau dan passive alerts; hasil itu
tidak boleh dilabeli crawl terautentikasi atau bukti bahwa sesi High telah
digunakan. Crawl khusus Impossible belum dijalankan. Perlu autentikasi ZAP yang
terverifikasi sebelum crawl per level diulang.

## Langkah validasi sebelum eksperimen

1. Login ke DVWA dan pastikan database telah diinisialisasi.
2. Set level keamanan, logout/login atau pastikan sesi menerima level yang sama, lalu catat level yang terlihat di DVWA.
3. Dari ZAP, jelajahi kedua modul SQLi setelah autentikasi untuk memperoleh request aktual, method, parameter, dan cookie sesi. Simpan hanya cookie yang sudah disamarkan.
4. Uji pembanding benign dan input uji yang disetujui pada endpoint yang sama. Untuk boolean/time-based blind, ulangi pengukuran baseline agar variasi jaringan tidak disalahartikan sebagai sinyal.
5. Validator manusia menetapkan apakah respons benar-benar menunjukkan injeksi. Jangan menjadikan alert ZAP tunggal sebagai ground truth.
6. Untuk pengujian utama, jalankan kembali 12 skenario × 3 replikasi dan simpan level, endpoint, parameter, kelas SQLi, mode RAG, sumber payload, outcome, dan alasan validasi.

## Rujukan implementasi ZAP

ZAP Baseline Scan melakukan spider dan passive scan, tanpa serangan aktif. Dokumentasi resmi: [ZAP Docker User Guide](https://www.zaproxy.org/docs/docker/about/) dan [ZAP Baseline Scan](https://www.zaproxy.org/docs/docker/baseline-scan/). Konfigurasi auth/spider mengikuti [Automation Framework — Environment](https://www.zaproxy.org/docs/desktop/addons/automation-framework/environment/), [Form-Based Authentication](https://www.zaproxy.org/docs/desktop/start/features/authmethods/), [requestor job](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-requestor/), [Spider job](https://www.zaproxy.org/docs/desktop/addons/spider/automation/), serta [Client Spider job](https://www.zaproxy.org/docs/desktop/addons/client-side-integration/automation/).
