# Audit kesiapan U07 untuk freeze formal

Tanggal audit: 17 Oktober 2026, Asia/Jakarta.

**Status: pilot U07 v17 lulus pemeriksaan kelengkapan. Freeze formal masih
pending, dengan 8 dari 11 gate lulus pada paket kesiapan v18.** Protokol aktif tetap
`local-sqli-v5-pilot`; dataset formal belum dijalankan. Cakupan penelitian
tetap DAST black-box pada DVWA Docker untuk SQL injection error-based,
boolean-based blind, dan time-based blind.

Paket v18 adalah audit dan rencana, bukan pengujian U07 baru. Tidak ada probe
DVWA atau inferensi model yang dijalankan untuk menyiapkan paket ini.

## Hasil pilot U07 v17

Experiment `u07-v17-integrated-20261017` berjalan selama 4 jam 8 menit.
Loader memverifikasi urutan ledger, hash artefak, evidence, dan ringkasan
analisis.

| Pemeriksaan | Hasil |
| --- | ---: |
| Slot nominal | 36 |
| Run applicable selesai | 33 dari 33 |
| Slot excluded sesuai protokol | 3, yaitu C/S10, C/S11, C/S12 |
| Run invalid | 0 |
| Run selesai dengan 10 kandidat dan eligible untuk metrik | 33 dari 33 |
| Ketidaksesuaian budget kandidat | 0 |
| Cakupan skenario dan kondisi | Lengkap |

Konfirmasi kandidat pada skenario dengan ground truth positif S1-S9 bersifat
deskriptif untuk satu replikasi pilot:

| Kondisi | Run | Kandidat | Konfirmasi berhasil | Konfirmasi negatif | Rasio konfirmasi pilot |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 12 | 120 | 24 | 96 | 24/90 = 26,7% |
| B | 12 | 120 | 25 | 95 | 25/90 = 27,8% |
| C | 9 | 90 | 68 | 22 | 68/90 = 75,6% |

Penyebut rasio tersebut hanya mencakup S1-S9. Pada Impossible, S10-S12,
kondisi A dan B masing-masing mencatat 0 konfirmasi berhasil dari 30 kandidat.
Angka pilot ini bukan hasil formal PSR atau FPR dan tidak cukup untuk menarik
kesimpulan statistik. Perbedaan satu kandidat antara A dan B juga tidak
membuktikan manfaat retrieval.

Runner mencatat 241 panggilan generasi dan 240 panggilan analisis. Semua
respons tercatat berhenti dengan `done_reason=stop`. Versi prompt generasi
tercatat `sqli-adaptive-candidate-v16-slot-nonce`; prompt analisis
`sqli-response-analysis-v8-count-trials`. Bukti ini tidak menggantikan
verifikasi log server Ollama.

## Status gate U07

| Gate | Status | Dasar |
| --- | --- | --- |
| Pilot lengkap untuk teknik dan level yang berlaku | Lulus | Matriks 36 slot sesuai protokol, 33 run applicable lengkap, 3 exclusion yang direncanakan, tanpa invalid atau mismatch budget. |
| Keputusan peneliti untuk penggunaan korpus | Lulus | Snapshot Chroma lama yang disetujui telah dipulihkan; keenam hash file index cocok dengan receipt. |
| Manifest runtime frozen | Pending | Yang tersedia masih paket kandidat, bukan release formal. |
| Versi dan seleksi SecLists | Lulus | Revisi, file sumber, hash, rentang baris, dan aturan seleksi terverifikasi. |
| Prosedur validator | Lulus untuk pilot | Empat anotasi blind pilot dan identitas VAL-01 tersedia. Anotasi F01 tetap harus dilakukan pada data formal. |
| Metodologi lokal | Lulus | Pipeline serial, cakupan retrieval, dan policy evaluasi tercatat. |
| Integrasi LangChain lokal | Lulus | 24 attempt A/B memverifikasi concurrency 1, tracing eksternal nonaktif, dan isolasi retrieval A/B. |
| Snapshot index retrieval terikat | Pending | Draft formal dan rencana v18 mengunci hash, tetapi pilot v17 tidak merekam hash snapshot yang dipakainya. |
| Context dan preflight runtime | Pending | Telemetri per panggilan tersedia dan runtime mencatat hanya DVWA serta MariaDB lokal, tetapi log server Ollama yang mencakup jam awal dan akhir pilot tidak ditemukan. |
| Coverage koordinat ZAP | Lulus pada evidence tersimpan | Report, HAR, plan, API evidence, dan koordinat bertanda scanner terverifikasi untuk empat level. |
| Kontrak offline | Lulus | Suite lengkap terkini lulus 184 tes, termasuk validasi pin snapshot v18. |

## Temuan retrieval dan runtime yang perlu ditutup

Receipt keputusan korpus terikat pada hash korpus, source lock, knowledge base,
dan hash byte enam file index. Sebelum pemulihan, tiga file aktif berbeda dari
receipt. Salinan kondisi aktif dibuat terlebih dahulu di
`results/raw/backups/chroma-active-before-approved-restore-u07-20261017/`.
Kemudian enam file dari archive yang disetujui dipulihkan dan diverifikasi
ulang. Hash aktif sekarang cocok dengan receipt, isi dokumen dan metadata tetap
cocok dengan korpus sembilan entri, dan backup kondisi sebelum pemulihan masih
tersimpan.

Hash adalah sidik jari isi file. Jika satu byte berubah, hash file itu berubah.
Hash berbeda tidak otomatis berarti isi pengetahuan berubah atau index rusak,
tetapi berarti kita tidak bisa membuktikan bahwa byte index yang dipakai sama
dengan snapshot yang disetujui. Karena plan v17 tidak menyimpan hash index,
hasil pilot v17 tetap sah sebagai catatan pilot, tetapi tidak dapat dipastikan
menggunakan snapshot yang mana. Oleh sebab itu, sebelum evaluasi formal perlu
pilot revalidasi dengan index yang dipin oleh hash.

Rencana `u07-v18-index-pinned-20261017` sudah disiapkan dengan snapshot lama
yang disetujui dan backup kondisi aktif tetap dijaga. Rencana tersebut belum
dijalankan. Gate retrieval tetap pending sampai pilot yang dipin itu selesai
dan hasilnya lolos pemeriksaan. Uji unit offline tidak mengirim permintaan ke
DVWA.

Runtime tersimpan mencatat container DVWA dan MariaDB lokal tanpa tunnel atau
gateway. Namun, log server Ollama yang mencakup jam mulai dan selesai U07 v17
tetap tidak ditemukan. Capture metadata runtime tidak dapat menggantikan log
tersebut, sehingga gate context masih pending.

## Plan formal kandidat

Draft yang dipin berada di `dvwa/local_run_plan.formal-20261017-approved-index.json`.
Isinya 99 run applicable: A=36, B=36, C=27, dengan 990 slot kandidat dan 12
report discovery baru. Jadwal berisi 108 slot nominal; sembilan slot
C/Impossible tidak applicable. Runner menolak plan karena protokol aktif masih
berstatus pilot.

Rencana revalidasi pilot v18 ada di
`dvwa/local_run_plan.u07-v18-index-pinned-20261017.json`. Rencana ini memuat
hash keenam file index yang sama dengan receipt. Belum ada run yang dibuat
darinya.

Perkalian linear durasi pilot memberi acuan sekitar 12,42 jam untuk tiga
replikasi. Ini bukan jaminan durasi: discovery baru, reset basis data,
pemulihan, beban laptop, dan anotasi manusia belum tercakup.

## Artefak dan batas audit

Ringkasan hasil pilot: `docs/evidence/u07-v17-pilot-summary-2026-10-17.json`.
Paket kesiapan kandidat disimpan pada
`results/raw/u07-formal-readiness-20261017-v17/`, dengan manifest, runtime,
hash sumber, jadwal, log tes, dan archive bukti. Salinan backup berada di
`results/raw/backups/formal-sqli-v1-20261017-u07-formal-readiness-20261017-v17/`.
Semua artefak ini bersifat lokal dan privat.

File `docs/evidence/u07-formal-readiness-2026-10-17.json` menyimpan checkpoint
audit sebelum pilot v17 selesai. Status terbaru ada pada laporan ini dan
manifest paket kesiapan v18 di
`results/raw/u07-formal-readiness-20261017-v18-index-pinned/`. Paket mencatat
184 tes offline lulus. Tiga gate masih pending: manifest runtime formal,
revalidasi pilot dengan hash index terpin, dan log Ollama untuk rentang U07 v17.

Bukti pemulihan index disimpan di
`docs/evidence/u07-index-restoration-2026-10-17.json`. Snapshot aktif sebelum
pemulihan beserta inventory hash-nya disimpan di
`results/raw/backups/chroma-active-before-approved-restore-u07-20261017/`.

U07 v17 tidak menjalankan evaluasi formal, tidak menghitung PSR/FPR, dan tidak
mengubah protokol menjadi frozen. Sesudah pilot v18 disetujui dan selesai,
hasilnya perlu ditinjau sebelum F01. Persetujuan penggunaan korpus tidak
menjadi persetujuan untuk menjalankan evaluasi formal.
