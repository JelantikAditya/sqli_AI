# Hasil validasi kontrak analisis respons v2

Tanggal: 19 Oktober 2026. Model: qwen2.5:7b, digest sama dengan pilot v1.
Ini validasi sintetis pengembangan, bukan holdout independen atau metrik formal.

| Ukuran pada kasus baru | V1 | V2 |
| --- | ---: | ---: |
| Verdict sesuai evaluator | 10/16 | 11/16 |
| Asesmen trial sesuai indikator | 33/44 | 32/44 |
| Mismatch decision/reason_code | 7 | 0 |
| Klaim positif pada enam fixture negatif | 3 | 3 |
| Analysis error | 0 | 0 |

Regresi v2 pada kasus pilot v1 yang sudah dibuka menghasilkan verdict tepat
7/9, asesmen trial tepat 24/26, serta nol mismatch reason_code. Hasil regresi
dipisahkan dari penyebut validasi baru. Total 41 inferensi dan tiga skip
runtime invalid menghasilkan 44 record. Semua inferensi selesai dengan stop.

Reason_code yang konsisten berarti cocok dengan keputusan model, bukan bahwa
keputusannya benar. V2 belum memenuhi kriteria yang dibekukan dan belum
dipromosikan ke runner formal. RAG analisis tetap nonaktif pada kedua profil.

## Isi arsip

| Berkas | Isi |
| --- | --- |
| summary.json | Hasil per profil dan per kasus, termasuk kegagalan serta warning. |
| manifest.json | Desain, kriteria, request/input/source hash yang dibekukan sebelum inferensi. |
| runtime.json | Identitas dan digest Qwen aktual. |
| audit.json | Reproduksi 44 record, preservasi 41 klaim, dan pemeriksaan sumber. |
| provenance.json | SHA-256 salinan publik dan arsip lokal. |

Empat berkas pertama disalin byte-for-byte dari arsip lokal
results/raw/development/response-analysis-v2-20261019/. Input, label evaluator,
prepared request dan output mentah tetap tersedia di arsip lokal tersebut.

Audit mengonfirmasi 959 sumber formal dan delapan artefak pilot v1 tetap utuh.
Tidak ada request DVWA, pengulangan R1/R2/R3, penggantian klaim mentah dengan
label executor, atau perhitungan ulang FPR/PSR formal.

Lihat [laporan lengkap](../../../docs/validasi-kontrak-analisis-v2-2026-10-19.md).
