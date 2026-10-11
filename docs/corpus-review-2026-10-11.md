# Review teknis korpus SQLi, 11 Oktober 2026

## Hasil

Sembilan entri diperiksa terhadap snapshot OWASP WSTG v4.2 dan PayloadsAllTheThings pada commit yang dikunci di `knowledge/sources.lock.json`. Schema, hash snapshot, ketersediaan rujukan baris, heading sumber, dan tiga kelompok teknik lulus validasi. Enam komponen pengetahuan proposal tersedia pada seluruh entri. Tidak ditemukan koreksi isi yang wajib untuk smoke integrasi S1.

Review ini dilakukan oleh Codex. Status `researcher_review` tetap `pending`: pemeriksaan teknis ini bukan persetujuan peneliti atau validasi eksperimen. Isi korpus dan identitas index dipertahankan untuk smoke awal yang dapat dibandingkan dengan bukti 7 Oktober.

## Pemeriksaan setiap entri

| ID | Pemeriksaan terhadap sumber | Hasil dan batas pemakaian |
| --- | --- | --- |
| sqli-error-quote | WSTG Detection Techniques baris 46-74 dan PATT Entry Point Detection 46-79 memang membahas quote probe, pemeriksaan SQL error, dan satu input yang divariasikan. | Sesuai sebagai probe diagnostik. HTTP 500 umum tidak cukup; sinyal SQL error tidak membuktikan ekstraksi data. |
| sqli-error-message | WSTG Errors Returned by the Application 174-216 dan PATT DBMS Identification Error Based 112-126 mendukung interpretasi pesan parser database. | Sesuai. Prefiks `1` ditandai sebagai adaptasi; wording error bergantung engine dan penanganan aplikasi. |
| sqli-error-xml | WSTG Error Based Exploitation 313-333 menjelaskan pemaksaan error pembawa informasi; PATT MYSQL Error Based 221-281 memuat EXTRACTVALUE/UPDATEXML. | Sesuai sebagai template marker konstan. Fungsi bisa tidak tersedia; konteks angka/quote harus diadaptasi. Jangan menyamakan missing-function error dengan marker yang diharapkan. |
| sqli-boolean-numeric | WSTG SELECT Statement 132-152 dan PATT Entry Point Detection 46-79 mendukung pasangan AND true/false pada input numerik. | Sesuai. Kedua request harus memakai koordinat dan struktur sama; sintaks numerik tidak langsung berlaku untuk setiap konteks quoted. |
| sqli-boolean-quoted | WSTG Boolean Exploitation 261-311 memuat quote balancing dan false predicate; PATT Boolean Based Injection 256-289 mendukung kontrol pasangan. | Sesuai. Contoh true/false dibedakan dan diberi label adaptasi. Tanda kutip akhir mengandalkan remainder SQL yang kompatibel; ini asumsi template, bukan pengetahuan kode DVWA. |
| sqli-boolean-template | WSTG Boolean Exploitation 261-311 membahas ASCII/SUBSTRING dan pemfilteran bagian respons dinamis; PATT MYSQL Blind With Substring Equivalent 284-300 mendukung fungsi karakter. | Sesuai. Konstanta menggantikan data target secara eksplisit. Perbedaan ukuran halaman saja tidak cukup tanpa kontrol konsistensi. |
| sqli-time-conditional | WSTG Time Delay Exploitation 361-377 dan PATT Using Conditional Statements 414-420 mendukung IF/SLEEP. | Sesuai. Kontrol tanpa delay adalah adaptasi editorial. IF false memilih nol; SLEEP tidak selalu dievaluasi, bergantung konteks ekspresi. |
| sqli-time-repeated | Sumber time-based yang sama mendukung conditional delay; pengukuran berulang dinyatakan sebagai sintesis editorial. | Sesuai. Jitter jaringan harus dibedakan dari delay SQL. Runner saat ini belum menerapkan pasangan kontrol timing ini secara penuh. |
| sqli-time-subselect | PATT Using SLEEP in a Subselect 375-412 memuat SELECT SLEEP FROM DUAL dengan kondisi; WSTG mendukung konsep timing. | Sesuai. Predikat konstanta dan delay tiga detik adalah adaptasi. Kontrol false subselect dapat menghasilkan NULL, sehingga perbandingan fokus pada timing, bukan kesamaan konten. |

## Catatan lintas entri

- `root_cause` adalah pola kerentanan umum dari referensi, bukan hasil membaca kode sumber target. Pengujian tetap DAST/black-box.
- Mitigasi parameterized queries, least privilege, dan pembatasan pesan error ditandai sebagai sintesis editorial berdasarkan pointer Remediation WSTG. Dua langkah terakhir tidak menggantikan pemisahan data dari sintaks SQL.
- Dua entri error pertama memakai definisi diagnostik yang lebih luas daripada eksploitasi error-based pembawa data. Definisi keberhasilan S1 harus dicatat sebagai sinyal SQL error pada smoke ini. PSR formal membutuhkan definisi operasional yang disetujui.
- Retrieval adalah global semantic top-k; belum merupakan review relevansi otomatis seluruh input penelitian. Kemiripan vector tidak otomatis membuktikan teknik atau kerentanan target.
- Korpus tidak memuat label skenario, SecLists pembanding, atau hasil benchmark. Jumlah sembilan pola cukup untuk memulai smoke; kecukupan untuk eksperimen formal perlu ditinjau peneliti.

## Penggunaan berikutnya

Korpus dapat digunakan untuk smoke pengembangan S1 dengan status review pending yang dinyatakan secara eksplisit. Setelah peneliti menyetujui atau meminta perubahan, catat keputusan; perubahan isi memerlukan rebuild index dan manifest baru sebelum konfigurasi eksperimen dibekukan.
