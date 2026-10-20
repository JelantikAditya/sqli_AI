# Arsip pilot pengembangan analisis respons v1

Tanggal: 19 Oktober 2026. Model: Qwen 2.5 7B.

Pilot sintetis sepuluh kasus ini membandingkan frozen-v8 dan measured-pairs-v1.
Sembilan kasus valid menghasilkan 18 inferensi; satu kasus baseline invalid
diblokir pada kedua profil. Ini bukti pengembangan, bukan holdout independen,
hasil pengujian DVWA, atau perhitungan FPR/PSR formal.

## Isi arsip

| Berkas | Isi dan asal |
| --- | --- |
| [summary.json](summary.json) | Salinan byte identik ringkasan asli, mencakup seluruh keputusan per kasus, warning dan runtime. |
| [manifest.json](manifest.json) | Salinan byte identik manifest sebelum inferensi, termasuk hash kode dan input. |
| [runtime.json](runtime.json) | Salinan byte identik identitas model aktual dan digest. |
| [trial-summary.json](trial-summary.json) | Ringkasan audit trial dan pemeriksaan preservasi; tidak memuat detail private per trial. |
| [provenance.json](provenance.json) | SHA-256 berkas publik dan sumber audit lokal. |

Sumber lokal berada di results/raw/development/response-analysis-v1-20261019/.
Input, label evaluator, request dan output mentah tetap di sana. Kode pembuat
kasus sintetis dan pelaksana pilot tersedia di
[development](../../../development/README.md). Arsip publik tidak cukup untuk
merekonstruksi seluruh teks keluaran model; hash dipakai untuk memeriksa arsip
lokal yang dipertahankan.

## Hasil dan keterbatasan

- Asesmen trial cocok: frozen 15/26; prototipe 26/26.
- Keputusan akhir cocok pada kasus valid: kedua profil 6/9.
- Prototipe salah pada mixed 1/3, mixed 2/3 dan trial tidak lengkap.
- Enam record prototipe mempunyai warning ketidakcocokan reason_code.
- Prototipe belum diintegrasikan ke runner formal. R1/R2/R3 dan anotasi VAL-01
  tetap dipertahankan; tidak ada perhitungan ulang metrik formal.

Semua kasus dan regresi dipertahankan. Penilaian trial berasal dari indikator
protokol pada data sintetis, bukan anotasi validator manusia. Satu pass, satu
seed dan sedikit kasus belum mendukung klaim generalisasi atau manfaat RAG.
Retrieval analisis dinonaktifkan pada kedua profil.

Lihat [laporan lengkap](../../../docs/pilot-perbaikan-analisis-v1-2026-10-19.md)
untuk desain, hasil per kasus, runtime dan prioritas revisi berikutnya.
