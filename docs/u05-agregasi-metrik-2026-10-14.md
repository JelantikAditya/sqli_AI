# U05: agregasi FPR dan PSR

## Kontrak perhitungan

Agregator membaca run hasil `experiment_dataset.load_runs`, keputusan sistem
yang disimpan sebelum review, ground truth dari
`dvwa/experiment_scenarios.json`, serta anotasi hasil impor blind review.
Katalog harus tetap menyatakan S1-S9 positif dan S10-S12 negatif; perubahan
label ditolak sampai ruang lingkup metrik ditinjau ulang.

PSR dihitung untuk B/C pada S1-S9. Kandidat masuk penyebut hanya dari run valid
dan selesai. Pembilang memerlukan keputusan validator `success` dan bukti
executor `confirmed_success=true`. Keputusan `failure` dan
`insufficient_evidence`, termasuk mixed evidence, tidak masuk pembilang tetapi
tetap di penyebut kandidat pada run lengkap. Setiap run harus memiliki anotasi
untuk seluruh kandidat. Satu anotasi hilang menahan PSR run tersebut dan
agregasi utamanya.

FPR A/B menghitung klaim sistem `positive` pada S10-S12 sebagai FP dan
`negative` sebagai TN. Anotasi validator tidak menyaring klaim sistem tersebut.
Run terencana yang hilang, invalid, tidak evaluable, atau abstain ditampilkan
sebagai unresolved dan menahan FPR replikasi. Penyebut nol menghasilkan nilai
null, bukan nol.

Mean dan standar deviasi sampel dihitung dari tiga replikasi eligible setelah
metrik dihitung per replikasi. Agregator juga menyimpan hitungan TP/FP/TN/FN
per replikasi A/B sebagai audit klasifikasi; hitungan itu tidak menggantikan
metrik primer FPR/PSR. JSON berisi detail run, skenario, replikasi, dan
ringkasan. CSV meratakan baris yang sama, mempertahankan unit ID, pembilang,
penyebut, TP/FP/TN/FN, coverage, kelayakan, dan alasan exclusion.

## Pemakaian

Impor anotasi dilakukan melalui `dvwa/blind_review.py import`. Setelah itu
jalankan agregator dengan dua tujuan keluaran baru di bawah `results/raw`:

```powershell
.\.venv\Scripts\python.exe dvwa/aggregate_metrics.py `
  --experiment-dir results/raw/<experiment> `
  --annotations results/raw/<imported-annotations.json> `
  --output results/raw/<report.json> `
  --csv-output results/raw/<report.csv>
```

Kedua file dibuat baru, tidak menimpa hasil sebelumnya. `scope` keluaran
menandai dataset dan tidak dengan sendirinya menyatakan bahwa data formal telah
terkumpul.

## Validasi U05

Fixture sintetis menguji hasil diketahui TP/FN/FP/TN, FPR dan PSR per run,
mean/SD tiga replikasi, anotasi pending, mixed evidence, penyebut nol,
abstention, run invalid/incomplete, duplicate run, orphan annotation, serta
ekspor CSV. Uji pilot atas ledger SecLists U04 dengan tiga anotasi prosedural
VAL-01 menahan semua PSR run karena tiap run memuat lebih dari satu kandidat
yang belum dianotasi. FPR juga tidak eligible karena pilot hanya kondisi C dan
tidak memiliki S10-S12. Pilot ini membuktikan agregator menahan metrik yang
belum lengkap; ia bukan hasil formal. Output CLI tersimpan di
`results/raw/u05-validator-pilot-check-20261014-v2/`.
