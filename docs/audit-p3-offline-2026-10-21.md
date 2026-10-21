# Audit offline P3, 21 Oktober 2026

**Status:** audit selesai; pilot live dan eksperimen formal belum siap.
Ada dua celah integrasi yang perlu diperbaiki dan satu ketidaksamaan
konfigurasi analisis yang perlu diselaraskan atau divalidasi terpisah.
Audit tidak mengubah kode runtime, prompt, parser, label, atau hasil eksperimen.

## Cakupan dan bukti

- Tidak ada panggilan API, request DVWA, inferensi Ollama, atau query Chroma.
  Koneksi socket diblokir selama audit; tidak ada percobaan koneksi yang terdeteksi.
- Sebanyak **179 tes regresi lulus**, tanpa failure, error, atau skip.
- Ada 16 pemeriksaan audit: 13 lolos dan tiga menghasilkan temuan.
- Seluruh **1.080 file** kode, korpus/index, dan artefak historis yang dipin
  tetap cocok dengan hash sebelum audit.
- Draft pilot mencakup 36 slot: **33 run berlaku**, terdiri dari A=12, B=12,
  C=9; tiga slot C/Impossible dikecualikan. Draft lolos validasi tanpa eksekusi.

[Evidence terstruktur](evidence/p3-offline-audit-2026-10-21.json) memuat hash
source, hasil pemeriksaan dan ringkasan tes. Log tes serta inventory preservasi
ada di `results/raw/development/p3-offline-audit-20261021-r3/`.

## Temuan yang perlu ditindaklanjuti

### P3-01: gate bukti invalid belum diterapkan sebelum analisis API

Lokasi: `development/run_qwen_api_experiments.py`, fungsi
`make_analysis_callback`, mulai baris 373.

Callback langsung membangun pesan dan memanggil `api.chat`. Ketika input
berstatus `runtime_status=invalid` atau `baseline_valid=false`, API palsu
tetap terpanggil satu kali. Baru setelah itu normalizer melempar `ValueError`
karena keputusan model dilekatkan pada bukti runtime invalid.

**Dampak:** bukti yang semestinya berhenti pada gate lokal dikirim untuk
inferensi; request terpakai dan masalah runtime dapat tampil sebagai error
orkestrasi. Reproduksi ini tidak menghasilkan false positive yang diterima,
karena normalizer akhirnya menolak input tersebut.

**Perbaikan yang diperlukan:** periksa kelayakan runtime/baseline sebelum
menyusun atau mengirim request. Hasilkan record `runtime_invalid` tanpa
keputusan model dan tanpa inferensi. Tambahkan tes callback dengan ekspektasi
jumlah panggilan API nol untuk kedua jenis input invalid.

### P3-02: penolakan struktural parser tidak selalu menghentikan analisis

Lokasi: `development/run_qwen_api_experiments.py`, baris 396-399.

Parser mengembalikan `model_output` mentah pada beberapa penolakan untuk
keperluan audit. Callback mengambil objek itu tanpa memeriksa status parser,
lalu meneruskannya ke normalizer lama. Normalizer dapat memberi status
`completed` bila ID observasi masih dikenal, meskipun struktur trial/referensi
telah ditolak oleh parser API.

| Respons palsu yang diuji | Penolakan parser | Status akhir callback |
| --- | --- | --- |
| Trial kedua diubah menjadi trial 4 | `trial-set-mismatch` | `completed`, klaim positive |
| Referensi trial pertama memakai referensi trial kedua | `missing-trial-evidence` | `completed`, klaim positive |

**Dampak:** trial rekaan atau pemetaan bukti yang salah dapat diperlakukan
sebagai analisis selesai dan masuk ke agregasi keputusan run. Warning dan
provenance saja belum menegakkan gate struktural yang dimaksud.

**Perbaikan yang diperlukan:** propagasikan penolakan struktural parser sebagai
status analisis error/invalid. Simpan respons serta klaim mentah pada artefak
audit, tanpa mengubahnya menjadi keputusan biner yang valid. Ini berbeda
dengan mengoreksi verdict yang secara semantik salah: klaim model yang lolos
struktur tetap harus dipertahankan untuk evaluasi, termasuk bila salah.

### P3-03: request analisis pilot belum identik dengan request evaluasi P2

Lokasi: `development/run_qwen_api_experiments.py`, `make_analysis_callback`;
`development/qwen_api_runtime.py`, baris 56; serta
`development/qwen_api_p2_analysis.py`.

Keduanya menggunakan kontrak dasar v2, tetapi susunan pesan tambahan schema
berbeda. Runtime pilot juga mengirim `chat_template_kwargs` dengan
`enable_thinking=false`; envelope P2 tidak mengirim opsi tersebut.

**Dampak:** agreement P2 tidak otomatis memvalidasi konfigurasi analisis pilot
secara identik. Temuan ini adalah perbedaan konfigurasi, bukan bukti bahwa salah
satu profil pasti lebih akurat.

**Tindak lanjut:** pilih satu jalur persiapan pesan dan konfigurasi untuk
digunakan konsisten pada A/B, lalu bekukan versinya. Jika perbedaan dipertahankan,
validasi profil pilot secara terpisah dan laporkan perbedaan tersebut. Hasil P2
lama tetap menjadi arsip pada konfigurasi aslinya.

## Bagian yang lolos pemeriksaan offline

- **Identitas dan deduplikasi:** generator API aktif tidak mewajibkan angka
  slot 101-110 pada payload. Varian yang hanya mengubah literal numerik
  terdeteksi sebagai struktur yang sama.
- **Isolasi A/B:** 120 pasangan pesan generasi diperiksa pada 12 skenario
  dan sepuluh posisi kandidat. Perbedaannya hanya konteks retrieval; field
  ground truth, level keamanan, dan ID skenario tidak masuk task model.
- **Discovery:** koordinat S1-S12 dapat dibaca dari report ZAP historis
  terverifikasi. Ini belum memverifikasi sesi atau token DVWA saat ini.
- **Timing dan serialisasi:** kontrol timing mempertahankan payload dan hanya
  mengganti argumen `SLEEP` menjadi nol. Trace callback bersifat serial;
  durasi API palsu yang sangat besar tidak mengubah bukti HTTP.
- **Checkpoint dan batas request:** percobaan dicatat sebelum transport,
  hitungan request dipertahankan setelah inisialisasi ulang, dan ceiling
  menahan request tambahan. Pengujian memakai transport palsu.
- **Penanganan kegagalan:** error transport dipropagasikan, sedangkan inspeksi
  AST menunjukkan handler batch mencatat attempt invalid dan berhenti.
- **Resume dan preservasi:** perubahan snapshot ditolak saat resume; dummy
  credential disunting dari artefak dan file indeks asli tetap utuh.

Lolosnya tes regresi tidak meniadakan P3-01 dan P3-02; reproduksi integrasi
tambahan di atas memperlihatkan celah yang belum dicakup tes lama.

## Draft pilot dan pekerjaan yang masih perlu live

Draft reviewable tersedia di
`development/qwen_api_p3_pilot_plan.template.json`. Validasi offline menghitung
330 kandidat logis dan 990 konfirmasi logis. Pada A/B, 240 kandidat membutuhkan
minimum 480 request API bila setiap generasi dan analisis berhasil sekali;
worst-case generasi tiga percobaan per slot ditambah satu analisis adalah
**960 request**. Angka tersebut belum termasuk attempt pemulihan yang baru.

Ceiling runtime saat ini 5.760 request per direktori eksperimen. Tetapkan
budget pilot dan pemulihan yang spesifik sebelum eksekusi; jangan menganggap
ceiling umum itu sebagai izin menghabiskan seluruhnya. Durasi dan biaya belum
dapat dipastikan dari audit offline.

Urutan tindak lanjut:

1. Perbaiki gate input invalid dan propagasi penolakan parser pada versi
   development baru, dengan tes integrasi callback.
2. Selaraskan atau validasi profil analisis pilot terhadap P2, lalu bekukan
   source/config baru. Snapshot eksperimen lama tidak ditulis ulang untuk resume.
3. Setelah layanan siap, lakukan smoke generasi terisolasi dan kontrol executor
   S1-S12 dengan verifikasi sesi, level, form/token dan baseline aktual.
4. Jalankan 33 run pilot dengan budget yang ditetapkan, lalu lakukan review
   independen, pengukuran durasi/kuota, dan pemeriksaan kesiapan formal.

P3 baru menyelesaikan bagian audit offline. Belum ada pilot API lintas level
baru, metrik PSR/FPR baru, ataupun keputusan penutupan P2 dari pekerjaan ini.

## Reproduksi audit

Gunakan output directory baru agar evidence terdahulu tetap utuh:

```powershell
.\.venv\Scripts\python.exe maintenance/audit_p3_offline.py `
  --output-dir results/raw/development/p3-offline-audit-recheck
```

Skrip membutuhkan artefak lokal historis yang memang diabaikan Git. Ia memakai
API/transport palsu dan memblokir koneksi jaringan, termasuk loopback. Source
runtime tidak diperbaiki atau diganti oleh skrip ini.
