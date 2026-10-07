# Automation Penetration Testing SQL Injection dengan LLM dan RAG

Repositori implementasi tugas akhir untuk pengujian **DAST/black-box** pada
**DVWA**. Ruang lingkup penelitian adalah SQL injection error-based,
boolean-based blind, dan time-based blind pada level Low, Medium, High, serta
Impossible. Evaluasi utama membandingkan **FPR** sistem dengan/tanpa RAG dan
**PSR** payload LLM terhadap SecLists.

## Status

- Lingkungan DVWA dan MariaDB berjalan melalui Docker Compose.
- Empat level keamanan DVWA telah diuji melalui antarmuka web.
- Akses dari runtime Colab ke DVWA melalui tunnel bertoken sudah diverifikasi
  pada 28 September 2026; [catatan uji](docs/progress-2026-09-28.md).
- Plan ZAP untuk discovery SQLi terautentikasi kini menangani `user_token`,
  memverifikasi level sesi, dan mewajibkan bukti login sebelum melaporkan hasil.
  Run terautentikasi berhasil pada 1 Oktober 2026 untuk keempat level; detail
  dan batas interpretasi ada di
  [catatan ZAP](docs/zap-baseline-2026-10-01.md)
  dan [petunjuk run](dvwa/README.md#discovery-zap-terautentikasi).
- Parser ZAP, validation loop DVWA, batch builder, indexing/retrieval Chroma,
  dan generator kandidat Qwen lokal sudah memiliki implementasi awal.
  Pengujian formal dan pengukuran FPR/PSR belum dimulai; rincian progres ada di
  [catatan progres rinci per 2 Oktober](docs/progress-2026-10-02.md).
- Pada 7 Oktober, Qwen 2.5 7B dan embedding Nomic berhasil diuji di laptop
  lokal. Index 15 PDF merupakan uji diagnostik awal. Jalur utama kini memakai
  sembilan entri JSON terstruktur dari OWASP WSTG v4.2 dan PayloadsAllTheThings
  SQL Injection, sesuai proposal. Index aktif dan retrieval semantik sudah
  diverifikasi lokal, termasuk koordinat report ZAP High. Notebook Colab
  diperbarui tetapi belum dijalankan; review peneliti dan eksperimen formal
  masih diperlukan. Lihat [penyesuaian RAG terhadap proposal](docs/proposal-rag-2026-10-07.md)
  dan [laporan progres harian 7 Oktober](docs/progress-2026-10-07.md).

Petunjuk menjalankan lab ada di [dvwa/README.md](dvwa/README.md).
Notebook untuk memverifikasi koneksi dari runtime Google Colab ada di
[notebooks/colab_dvwa_smoke.ipynb](notebooks/colab_dvwa_smoke.ipynb).
Rincian milestone awal juga tersedia di
[catatan progres 28 September](docs/progress-2026-09-28.md).

## Prinsip reproduksibilitas

- Gunakan hanya target DVWA milik sendiri pada lingkungan terkontrol.
- Catat image Docker, level keamanan, endpoint, jenis SQLi, konfigurasi
  RAG, sumber payload, seed, dan nomor pengulangan pada setiap percobaan.
- Simpan hasil agregat dan contoh log yang telah disanitasi dalam repositori.
  Simpan token, cookie, dump database, artefak mentah, model besar, serta PDF
  referensi di luar Git.
- Proposal dan artikel referensi dicantumkan sebagai sitasi bibliografis dalam
  paper, bukan disalin sebagai PDF ke repositori ini.
