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

## Perbaikan plan discovery — 1 Oktober 2026

Template Automation Framework memakai Browser Based Authentication untuk
menjalankan form login DVWA beserta CSRF-nya. Field CSRF `user_token` juga
didaftarkan untuk form DVWA. Runner membuat ulang container web dengan level
yang diminta sebagai default (container database dan volumenya tetap), lalu
requestor memeriksa HTML `security.php` pada sesi autentikasi ZAP. Tes statistik
`stats.auth.success` dan
`stats.auth.state.loggedin` membuat plan gagal jika spider tidak membuktikan
sesi login. Kedua helper High di-seed secara eksplisit dan Client Spider tetap
dibatasi pada dua modul SQLi.

Jalankan dengan `powershell -ExecutionPolicy Bypass -File
dvwa/run_zap_discovery.ps1 -SecurityLevel high` (atau `low`, `medium`,
`impossible`). Report JSON per run masuk ke `results/zap/`. Plan hanya memakai
spider dan passive scan; tidak ada Active Scan atau payload SQLi.

Run Low, Medium, High, dan Impossible berhasil pada 1 Oktober 2026. Keempatnya
lulus pemeriksaan level, `stats.auth.success`, dan indikator `loggedin`. Spider
utama menemukan 49 URL pada Low, Medium, dan Impossible serta 45 pada High;
spider pendamping mengunjungi kedua helper High secara eksplisit. Passive report
memuat 14 kategori alert pada Low/Medium/High, 15 pada Impossible, dan tidak
memuat kategori SQL Injection. Ini adalah hasil discovery dan passive scan,
bukan bukti bahwa target aman atau pengukuran FPR/PSR. JSON report dan plan
bertimestamp tersimpan lokal di `results/zap/` dan diabaikan Git. Laporan awal
dan koreksi interpretasi di atas tetap dibatasi pada bukti yang tersedia saat
itu; hasil tervalidasi ini adalah run baru yang terpisah.

## Observasi ZAP Desktop — SQL Injection biasa, High

Catatan ini ditambahkan 1 Oktober 2026 dari ringkasan CSV History `sqlbiasa.csv` dan screenshot tab Alerts yang diberikan peneliti. File mentah tidak disalin ke repositori karena riwayat request dapat memuat payload atau data sesi. Konfigurasi dan status selesai Active Scan tidak dapat diverifikasi secara independen dari artefak yang dibagikan.

| Ukuran pada CSV History | Hasil |
| --- | ---: |
| Semua baris | 536 |
| Request ke `/vulnerabilities/sqli/session-input.php` | 430 (422 POST, 8 GET) |
| Status pada endpoint tersebut | 427 HTTP 200, 3 HTTP 302 |
| RTT endpoint tersebut | 0–11 ms |
| Respons HTTP 404 pada seluruh history | 100 |

Screenshot Alerts memperlihatkan 17 kategori alert, termasuk Reflected XSS dan beberapa temuan header/cookie. Tidak ada kategori SQL Injection yang terlihat. Karena CSV merupakan riwayat request dan screenshot tidak menampilkan filter atau konteks seluruh alert, kesimpulan terbatas pada: **tidak terlihat alert SQL Injection pada hasil yang dibagikan**. Respons 200/404 dan waktu singkat sendiri tidak membuktikan SQLi atau ketiadaannya.

Pada uji manual High yang terpisah, peneliti melaporkan keluaran beberapa akun dan hash setelah payload UNION. Ini merupakan bukti manual indikasi UNION-based SQLi pada instance DVWA tersebut. Nilai akun/hash tidak dicatat di sini. Temuan UNION-based ini bersifat eksploratif dan di luar tiga kelas yang dihitung dalam proposal (error-based, boolean-based blind, time-based blind); jangan masukkan ke PSR/FPR skenario proposal.

**Ringkasan interpretasi:** request ke endpoint SQLi biasa tercatat di ZAP; pada screenshot yang diberikan tidak tampak alert SQLi, sementara uji manual terpisah menghasilkan keluaran data. Catat hasil ZAP sebagai *SQLi tidak terdeteksi pada alert yang dibagikan*, bukan sebagai bukti bahwa High aman. Simpan bukti mentah secara lokal dengan data akun, hash, cookie, dan token disamarkan.

### SQL Injection Blind — High

Peneliti mengidentifikasi screenshot Alerts berikutnya sebagai hasil untuk modul SQL Injection Blind pada level High. Screenshot memperlihatkan 18 kategori alert; tidak tampak kategori SQL Injection.

| Bukti yang tampak | Hasil |
| --- | --- |
| Jumlah kategori alert pada screenshot | 18 |
| Alert SQL Injection yang terlihat | Tidak ada |
| Alert lain yang tampak | Reflected XSS, GET for POST, dan beberapa alert header/cookie/session |

Interpretasi dibatasi pada screenshot yang dibagikan. Screenshot tidak memperlihatkan request target yang dipindai, filter Alerts, atau status selesai Active Scan. Peneliti kemudian mengklarifikasi bahwa saat memasukkan nilai normal `1` pada level High, tidak terlihat request POST pada run yang sedang diperiksa. Baris POST `/vulnerabilities/sqli_blind/cookie-input.php` yang pernah dibagikan sebelumnya tidak dapat dipastikan berasal dari run pemindaian ini. Karena itu belum terverifikasi bahwa Active Scan Blind High menguji injection point yang benar. Hasil ini dicatat sebagai *tidak terlihat alert SQLi pada screenshot modul blind High*, bukan sebagai bukti bahwa target aman atau bahwa seluruh titik uji telah dipindai. Alert non-SQLi berada di luar metrik SQLi proposal.

### SQL Injection biasa — Impossible

Peneliti melaporkan request normal `GET /vulnerabilities/sqli/` dengan `id=1` mendapat HTTP 200 OK. Screenshot Alerts memperlihatkan 20 kategori alert; tidak tampak kategori SQL Injection. Screenshot rincian berikutnya menunjukkan daftar alert mencakup beberapa endpoint, termasuk helper `session-input.php` dan `cookie-input.php`, selain halaman SQLi utama. Karena itu daftar tersebut merupakan agregat sesi ZAP dan tidak dapat diatribusikan seluruhnya ke pemindaian SQLi biasa pada level Impossible. Screenshot juga tidak menunjukkan status selesai Active Scan, sehingga status pemindaian injection point belum dapat dipastikan hanya dari gambar.

Satu kategori lain yang terlihat adalah `Information Disclosure - Sensitive Information in URL`. Ini bukan alert SQLi. Periksa detail alert di ZAP secara lokal untuk mengetahui URL/parameter yang ditandai; jangan membagikan nilai token atau sesi jika muncul. Catat hasil SQLi sebagai *tidak terlihat alert SQLi pada screenshot yang diberikan*, bukan bukti tunggal bahwa target aman.

### SQL Injection Blind — Impossible

Peneliti melaporkan request normal pada modul SQL Injection Blind di level Impossible mendapat HTTP 200 OK. Ini mengonfirmasi halaman merespons input normal pada sesi tersebut. Belum ada bukti request ini dipindai secara aktif; screenshot Alerts yang dibagikan merupakan agregat beberapa endpoint dan tidak dapat diatribusikan khusus ke modul Blind Impossible.

Peneliti menyatakan daftar Alerts yang terlihat untuk Blind Impossible sama dengan daftar sebelumnya (20 kategori) dan tidak menampilkan alert SQL Injection. Karena Alerts merupakan agregat sesi dengan beberapa endpoint, hasil ini belum menjadi bukti scan Blind Impossible yang terisolasi.

Screenshot terbaru setelahnya memperlihatkan `Alerts (21)`—bertambah dari screenshot sebelumnya—dan tetap tidak menunjukkan kategori SQL Injection pada bagian yang terlihat. Daftar masih memuat alert untuk helper High (`session-input.php` dan `cookie-input.php`), sehingga jumlah/isi tersebut harus diperlakukan sebagai agregat sesi yang berubah, bukan hitungan alert khusus Impossible.
