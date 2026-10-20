# Keputusan indikator keberhasilan error-based

Tanggal: 12 Oktober 2026.
Dipilih oleh: peneliti melalui chat proyek.
Scope: indikator error-based untuk eksperimen SQLi DAST pada DVWA lokal.

> Bagian dampak implementasi di bawah merekam status pada tanggal keputusan.
> Untuk bukti kontrol executor yang lebih baru, lihat [pilot T03/T04](t03-t04-controls-2026-10-14.md)
> dan [review progres 14 Oktober](review-progress-2026-10-14.md); status kerja
> aktif ada di [rencana penyelesaian](rencana-penyelesaian-2026-10-16.md).

## Definisi yang dipilih

Eksekusi kandidat memenuhi indikator keberhasilan ketika respons server
memuat pesan eror diagnostik basis data secara eksplisit. Contoh yang
diberikan peneliti adalah pesan sintaks MySQL:

`You have an error in your SQL syntax...`

Dalam penelitian ini pesan tersebut dipakai sebagai sinyal diagnostik
pemrosesan SQL yang dipengaruhi input. Interpretasinya harus didukung
baseline normal, keterkaitan dengan kandidat yang diuji, dan konfirmasi
respons. Munculnya nama database atau exception tanpa diagnostik yang jelas
tidak boleh otomatis dianggap bukti perubahan ekspresi kueri SQL.

Ekstraksi data dan marker konstan bukan syarat keberhasilan indikator yang
dipilih. Istilah pada pelaporan PSR error-based perlu menyebut keberhasilan
probe diagnostik sesuai definisi operasional penelitian ini.

## Operasionalisasi dalam protokol pilot

- Gunakan sesi autentikasi dan level yang terverifikasi.
- Catat baseline normal sebelum kandidat pada injection point yang sama.
- Cari diagnostik basis data eksplisit yang baru terhadap baseline.
- HTTP 500 umum, halaman kosong, halaman login, atau koneksi gagal tidak
  memenuhi indikator diagnostik SQL.
- Jumlah konfirmasi tetap tiga per kandidat sesuai protokol pilot yang ada.
  Jumlah ini berbeda dari tiga pengulangan pipeline.
- Aturan penentuan hasil akhir dari konfirmasi bercampur, misalnya satu atau
  dua dari tiga respons positif di dalam satu run, masih perlu ditetapkan
  sebelum freeze. Ini berbeda dari agregasi antar-run: peneliti telah memilih
  per-run averaging, sehingga hasil Run 1/2/3 dipertahankan dan tidak diberi
  verdict tunggal berdasarkan 3/3. Lihat keputusan-agregasi-per-run-2026-10-12.md.
- Simpan evidence, sinyal aturan, klaim Qwen, dan keputusan validator terpisah.
  Klaim sistem disimpan sebelum human review untuk menjaga audit FPR.
- Terapkan definisi yang sama pada RAG-off, RAG-on, dan SecLists untuk teknik
  error-based. PSR tetap hanya pada skenario positif S1-S9.

## Dampak implementasi

Field `validation.error_success_indicator` pada konfigurasi pilot diberi nilai
`explicit-database-diagnostic`. Identitas definisi lama
`new-sql-diagnostic-reproduced` dipertahankan karena masih sesuai dengan arah
indikator dan kontrol baseline/reproduktibilitas.

Penambahan field mencatat keputusan; executor belum membaca field tersebut
sebagai kebijakan baru. Matcher lama pada validation_loop.py masih menerima
sejumlah nama exception atau warning yang luas. Pada T02/T03 perlu ditinjau
agar indikasi awal itu dibedakan dari diagnostik SQL eksplisit yang memenuhi
definisi ini. Pengujian konfirmasi, analisis Qwen, serta agregasi keputusan
belum dianggap selesai oleh pembaruan dokumentasi.

## Sitasi dan keputusan lain

Peneliti menyertakan nomor sitasi [1][2] pada pernyataan indikator. Identitas
referensi untuk kedua nomor belum diberikan pada pesan tersebut. Nomor ini
tidak dipetakan ke sumber tertentu tanpa memeriksa daftar pustaka yang dimaksud.

Keputusan ini hanya menetapkan indikator error-based. Status review korpus,
validator independen, protokol formal, dan gate lain tetap pending/pilot.
Artefak smoke dan manifest lama tidak diubah; bukti berikutnya harus mengacu
pada versi konfigurasi yang diperbarui.
