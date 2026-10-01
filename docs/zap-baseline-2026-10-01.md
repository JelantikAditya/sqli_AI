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

## Matriks ground truth sementara

Matriks ini mengikuti 12 skenario di proposal (Bab 3, Tabel 3.2). Label positif/negatif berasal dari level proteksi DVWA yang ditetapkan proposal; status per percobaan harus tetap dikonfirmasi melalui validasi manual sebelum masuk hitungan TP/FP/TN/FN.

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

Validasi halaman melalui sesi login mengonfirmasi request form dasar berikut:

| Modul | Path | Method | Parameter input | Tombol submit |
| --- | --- | --- | --- | --- |
| SQL Injection | `/vulnerabilities/sqli/` | GET | `id` | `Submit` |
| SQL Injection blind | `/vulnerabilities/sqli_blind/` | GET | `id` | `Submit` |

Ini memetakan injection point pada level sesi yang diperiksa. Perlu diperiksa
lagi pada tiap level keamanan karena DVWA dapat mengubah lokasi/sumber input;
matriks ground truth di atas masih merupakan label rancangan proposal, belum
hasil konfirmasi eksploitabilitas.

## Langkah validasi sebelum eksperimen

1. Login ke DVWA dan pastikan database telah diinisialisasi.
2. Set level keamanan, logout/login atau pastikan sesi menerima level yang sama, lalu catat level yang terlihat di DVWA.
3. Dari ZAP, jelajahi kedua modul SQLi setelah autentikasi untuk memperoleh request aktual, method, parameter, dan cookie sesi. Simpan hanya cookie yang sudah disamarkan.
4. Uji pembanding benign dan input uji yang disetujui pada endpoint yang sama. Untuk boolean/time-based blind, ulangi pengukuran baseline agar variasi jaringan tidak disalahartikan sebagai sinyal.
5. Validator manusia menetapkan apakah respons benar-benar menunjukkan injeksi. Jangan menjadikan alert ZAP tunggal sebagai ground truth.
6. Jalankan 12 skenario × 3 replikasi sesuai proposal dan simpan level, endpoint, parameter, kelas SQLi, mode RAG, sumber payload, outcome, dan alasan validasi.

## Rujukan implementasi ZAP

ZAP Baseline Scan melakukan spider dan passive scan, tanpa serangan aktif. Dokumentasi resmi: [ZAP Docker User Guide](https://www.zaproxy.org/docs/docker/about/) dan [ZAP Baseline Scan](https://www.zaproxy.org/docs/docker/baseline-scan/). Konfigurasi auth/spider mengikuti [Automation Framework — Environment](https://www.zaproxy.org/docs/desktop/addons/automation-framework/environment/), [Form-Based Authentication](https://www.zaproxy.org/docs/desktop/start/features/authmethods/), dan [Spider job](https://www.zaproxy.org/docs/desktop/addons/spider/automation/).
