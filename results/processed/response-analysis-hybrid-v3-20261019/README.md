# Hasil shadow verifier dan agreement gate v3

Tanggal: 19 Oktober 2026. Model tetap qwen2.5:7b dengan prompt v2 yang sama.
Ini evaluasi sintetis pengembangan, bukan holdout independen atau metrik formal.

| Ukuran pada 20 kasus valid baru | Qwen mentah | Gabungan |
| --- | ---: | ---: |
| Verdict sesuai label | 15/20 | 17/20 |
| Kontrol positif terdeteksi | 4/4 | 4/4 |
| Klaim positif pada 7 fixture negatif | 3 | 0 |
| Abstention pada 7 fixture negatif | 0 | 3 |
| Coverage biner fixture negatif | 7/7 | 4/7 |
| Coverage biner seluruh kasus valid | 13/20 | 8/20 |

Ketiga klaim positif keliru menjadi inconclusive. Jumlah true negative tetap
4/7. Angka nol klaim positif keliru ini tidak berarti FPR utama 0%.

Verifier-only cocok dengan 20/20 label verdict dan 56/56 label trial yang
ditetapkan dari rancangan kasus. Ini kesesuaian implementasi terhadap aturan
pada fixture yang dibangun, bukan bukti akurasi independen. Asesmen trial Qwen
tetap 47/56. Penjelasan dan klaim mentah Qwen tidak diganti.

Replay lama dipisahkan: verdict tepat 11/16 menjadi 13/16 pada set v2, dan
7/9 menjadi 8/9 pada regresi v1. Replay tidak memerlukan inferensi ulang.

Ada 20 inferensi baru dan satu skip baseline invalid. Enam belas uji offline
lulus. Audit mereproduksi 48 record hibrida, memastikan seluruh 959 sumber
formal dan 16 artefak v1/v2 tetap utuh. Kriteria coverage yang dibekukan belum
tercapai; varian tetap shadow dan belum dipromosikan ke runner formal.

## Berkas

| Berkas | Isi |
| --- | --- |
| summary.json | Metrik mentah, verifier-only, dan gabungan pada set baru serta replay lama. |
| manifest.json | Aturan, kriteria empiris, input/request/source hash sebelum inferensi. |
| runtime.json | Digest Qwen aktual. |
| audit.json | Reproduksi record, kesesuaian fixture, preservasi sumber dan batas desimal. |
| provenance.json | Hash salinan di sini dan artefak arsip lokal. |

Empat berkas pertama disalin byte-for-byte dari
results/raw/development/response-analysis-hybrid-v3-20261019/. Arsip lokal
memuat input, label evaluator terpisah, prepared request, record lengkap,
replay lama dan QA independensi metadata.

Tidak ada request DVWA, perubahan protokol formal, pengulangan R1/R2/R3 atau
perhitungan ulang FPR/PSR. Gate tidak memakai label evaluator atau sinyal
executor sebagai jawaban dan hasilnya tidak dimasukkan ke prompt Qwen.

Lihat [laporan metode dan hasil](../../../docs/varian-verifikasi-hibrida-v3-2026-10-19.md).
