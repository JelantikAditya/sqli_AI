# Hasil terolah eksperimen formal SQLi

Eksperimen: formal-sqli-v1-20261017. Penerimaan anotasi: 19 Oktober 2026.

Direktori ini menyimpan salinan anotasi serta keluaran agregator untuk arsip
GitHub. Byte berkas CSV/JSON disalin dari artefak lokal yang sudah diperiksa;
keputusan validator dan metrik tidak dihitung ulang pada tahap publikasi ini.

## Berkas

| Berkas | Isi |
| --- | --- |
| annotations.val01.latest.csv | Penilaian terbaru VAL-01: 990 baris, 349 success dan 641 failure. |
| annotations.val01.initial.csv | Format normalisasi penilaian awal: 990 baris, 362 success dan 628 failure; dipertahankan sebagai riwayat, bukan input metrik terbaru. |
| metrics.reviewed.json | Keluaran agregator dengan hasil per run, skenario, replikasi dan mean/SD. |
| metrics.reviewed.csv | Ekspor tabular yang sama, 94 baris data. |
| provenance.json | Hash berkas, identitas paket dan ledger sumber, serta ringkasan penerimaan. |

Tiga belas keputusan time-based berubah dari success menjadi failure pada
versi terbaru. Penilaian awal dan terbaru disimpan terpisah. Tidak ada anotasi
manusia yang diganti otomatis atau diambil dari keluaran model.

## Ringkasan utama

| Kondisi | Success / kandidat valid | Mean PSR (%) | SD sampel (poin persentase) | n replikasi |
| --- | ---: | ---: | ---: | ---: |
| B, LLM+RAG | 75 / 270 | 27,78 | 0,00 | 3 |
| C, SecLists | 202 / 270 | 74,81 | 1,70 | 3 |

PSR utama memakai 540 kandidat B/C S1-S9. Jumlah 349 success dari seluruh
990 anotasi tidak menjadi pembilang PSR utama. Keberhasilan memerlukan bukti
3/3 dan keputusan validator sesuai protokol.

FPR utama A/B tetap null/undefined karena S10 inconclusive pada ketiga
replikasi, dengan coverage keputusan negatif 2/3 atau 66,67%. Angka 66,67%
untuk FPR hanya berlaku pada analisis sensitivitas jika S10 diasumsikan TN;
asumsi itu tidak diterapkan pada ekspor metrik resmi ini.

## Jejak sumber dan batas arsip

Paket lokal yang digunakan adalah
results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2, dengan penerimaan
terbaru di subdirektori returned-VAL-01-20261019-rev2. Eksperimen sumber berada
di results/raw/formal/formal-sqli-v1-20261017.

Log HTTP, mapping private, body/artefak runtime, file indeks, dan sumber proyek
tersinkron tetap disimpan terpisah sesuai .gitignore. Salinan di direktori ini
tidak menggantikan arsip mentah lokal yang diperlukan untuk memuat ulang
seluruh bukti dan memverifikasi pemilihan attempt. Seluruh 959 hash sumber
F02 cocok sebelum dan sesudah penerimaan anotasi; R1/R2/R3 tidak diulang.

Rincian metode, preservasi dan hasil ada di
[laporan VAL-01](../../../docs/f02-hasil-val01-2026-10-19.md).
Panduan penilaian ada di
[panduan VAL-01](../../../docs/panduan-penilaian-val01-formal.md).
