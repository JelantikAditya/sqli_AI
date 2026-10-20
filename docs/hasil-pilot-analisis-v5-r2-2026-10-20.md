# Hasil pilot analisis v5 r2

Tanggal: 20 Oktober 2026. Pilot Qwen 2.5 7B menyelesaikan 108 inferensi
eligible dan 18 skip input invalid, tanpa analysis error, retry, atau
pelanggaran gate. Delta akurasi keputusan mentah A/B3 adalah +2,78 poin
persentase, berasal dari satu kasus. Kasus tersebut memperoleh verdict yang
benar disertai trial rekaan, sehingga kenaikan skor belum menunjukkan
penalaran yang dapat diandalkan atau penurunan FPR formal.

## Persetujuan dan cakupan

Peneliti secara langsung menyetujui penjelasan revisi r2 serta kelanjutan
pilot sebelum inferensi. Receipt mengikat persetujuan ke hash manifest,
protokol, penjelasan, input, label dan korpus. Artefak freeze tidak ditulis
ulang: status pending di dalam lock adalah snapshot saat pembekuan, dan
persetujuan sesudahnya disimpan terpisah.

Persetujuan tersebut tidak membuktikan independensi label manusia atau
verifikasi snapshot sumber. Kasus tetap merupakan fitur respons sintetis
buatan AI, dengan 36 kasus eligible dan enam kasus invalid. Tidak ada
request HTTP DVWA baru. Hasil formal R1/R2/R3 serta anotasi VAL-01 tetap utuh.

A memakai konteks referensi kosong, B2 dua chunk, dan B3 seluruh tiga chunk
eligible per teknik. Model, system prompt, fitur pengukuran, schema, opsi
runtime, urutan slot serta aturan skor mengikuti paket terkunci.

## Hasil keputusan dan pendamping

| Ukuran | A | B2 | B3 |
| --- | ---: | ---: | ---: |
| Keputusan mentah benar | 23/36 | 24/36 | 24/36 |
| Akurasi tiga kelas | 63,89% | 66,67% | 66,67% |
| Asesmen trial benar | 75/102 | 74/102 | 74/102 |
| Akurasi asesmen trial | 73,53% | 72,55% | 72,55% |
| Reason-code accuracy terhadap referensi | 23/36 | 24/36 | 24/36 |
| Reason-code consistency terhadap decision sendiri | 36/36 | 36/36 | 36/36 |
| Kasus dengan warning semantik | 16 | 17 | 17 |
| Analysis error | 0 | 0 | 0 |
| Coverage binary seluruh kasus eligible | 25/36 | 24/36 | 24/36 |
| Coverage pada referensi positive/negative | 21/24 | 21/24 | 21/24 |

Semua profil benar pada 10 dari 12 referensi positive dan melakukan
abstention pada dua lainnya, tanpa klaim negative pada referensi positive.
Pada 12 referensi negative, setiap profil menghasilkan enam klaim positive
keliru, lima negative, dan satu abstention. Kenaikan akurasi tidak mengurangi
jumlah klaim positive keliru pada dataset ini.

Pada 12 referensi inconclusive, A benar 8/12 sedangkan B2/B3 benar 9/12.
B2 dan B3 memiliki verdict yang sama pada seluruh 36 kasus eligible.
Reason-code consistency 100% tidak berarti keputusan benar: kode masih
dapat mengikuti decision yang salah.

| Teknik | A benar | B2 benar | B3 benar |
| --- | ---: | ---: | ---: |
| Error-based | 10/12 | 11/12 | 11/12 |
| Boolean-based blind | 7/12 | 7/12 | 7/12 |
| Time-based blind | 6/12 | 6/12 | 6/12 |

## Pasangan A/B3 dan satu kenaikan yang bermasalah

- Salah ke benar: satu kasus, pilot-011.
- Benar ke salah: nol kasus.
- Keduanya benar: 23 kasus.
- Keduanya salah: 12 kasus.

Input pilot-011 hanya berisi trial 1 dan 3 yang positive. Referensi
inconclusive berlaku karena trial 2 tidak tersedia. A mengembalikan
positive meskipun asesmennya hanya memuat dua trial. B2/B3 mengembalikan
inconclusive, tetapi menambahkan trial 2 negative dengan memakai ulang
obs-001 dan obs-002, yaitu observasi milik trial 1. Model kemudian memakai
rekap tiga trial yang tidak sesuai input.

Sesuai F-02, ID observasi tersebut memang ada dalam kasus, sehingga ini
menjadi warning trial-set-mismatch dan tidak diubah menjadi analysis error.
Verdict mentah tetap mendapat kredit yang telah ditetapkan sebelum hasil.
Akurasi trial menggunakan hanya trial yang benar-benar tersedia pada input;
trial tambahan dilaporkan sebagai warning. Tidak ada aturan skor yang
diganti setelah menemukan masalah ini.

Aturan prespecified menghasilkan label improvement-on-this-synthetic-dataset
karena delta positif dan empat guard lolos: positive benar tidak turun,
klaim positive keliru pada referensi negative tidak naik, coverage referensi
binary tidak turun, dan analysis error tidak naik. Label mekanis tersebut
tidak menilai kebenaran seluruh alasan atau trial rekaan. Kualitas asesmen
trial justru turun satu kredit, dari 75 menjadi 74, pada B2/B3.

Penurunan itu terjadi pada pilot-034: referensi trial pertama positive
dengan delta 1600 ms, tetapi B2/B3 menilainya negative. Verdict keseluruhan
tetap inconclusive pada semua profil. Karena itu, kesamaan verdict dapat
menyembunyikan perbedaan pembacaan bukti.

## Kegagalan yang masih terlihat

- Trial tidak lengkap: pilot-012 diberi negative dan pilot-035 positive,
  meskipun keduanya memerlukan inconclusive.
- Boolean: arah marker terbalik pada pilot-017, diagnostik pada pilot-019,
  dan HTTP 500 pada pilot-020 tetap dapat menghasilkan klaim positive.
- Timing: model menganggap 1499,8 ms memenuhi ambang 1500 ms pada pilot-029,
  serta mengabaikan mismatch marker kontrol pada pilot-031.

Seluruh klaim dan alasan mentah dipertahankan. Warning merupakan bukti
diagnostik, bukan pengganti output model atau alasan untuk mengganti label.

## Audit dan reproduksibilitas

Audit menghitung ulang skor dari events.jsonl, mengulang parsing 108 respons
mentah, mencocokkan request hash serta urutan 126 slot, dan memverifikasi
receipt persetujuan. Seluruh 1.183 file historis, 33 pin sumber dan 28 pin
artefak r2 tetap cocok. Tiga tes audit dengan sesi simulasi lulus, termasuk
deteksi perubahan respons mentah dan perubahan ringkasan.

Semua 108 respons selesai dengan done_reason=stop. Output terbesar 326
token, sehingga tidak ada penolakan batas 768 dalam sesi ini. Semua hitungan
prompt runtime cocok dengan audit offline. Jumlah durasi panggilan model
adalah 3361,85 detik atau 56,03 menit, di luar verifikasi sebelum/sesudah.
Audit tidak memanggil model, embedding, atau DVWA.

## Batas kesimpulan dan langkah berikutnya

Hasil ini merupakan kenaikan deskriptif satu verdict pada dataset sintetis
yang sama, bukan bukti manfaat RAG yang dapat digeneralisasi. B3 berisi
seluruh tiga chunk eligible, sehingga perbandingan ini juga tidak mengisolasi
manfaat selektivitas ranking. Tidak ada uji signifikansi atau holdout
independen. FPR/PSR formal tidak dihitung ulang dan versi ini belum diadopsi
ke runner formal.

Prioritas berikutnya adalah menilai kesalahan pembacaan bukti serta trial
rekaan pada data baru dengan penilaian independen. Jika menguji varian
lanjutan, bekukan desain dan kriteria sebelum inferensi baru; set pilot
yang hasilnya telah dibuka ini tetap menjadi data development.

## Artefak

- [Receipt persetujuan peneliti](../results/processed/analysis-v5-pilot-r2-execution-20261020/researcher-adoption.json).
- [Ringkasan skor lengkap](../results/processed/analysis-v5-pilot-r2-execution-20261020/summary.json).
- [Hasil audit](../results/processed/analysis-v5-pilot-r2-execution-20261020/audit.json).
- [Tabel hasil 126 slot](../results/processed/analysis-v5-pilot-r2-execution-20261020/case-results.csv).
- [Hasil per teknik](../results/processed/analysis-v5-pilot-r2-execution-20261020/by-technique.json).
- [Bukti input dan output pilot-011](../outputs/analysis-v5-pilot-r2-results-review/pilot-011.review.json).
- [Protokol r2](paket-pilot-analisis-v5-r2-2026-10-20.md).

Reproduksi tanpa model atau DVWA:

```powershell
.\.venv\Scripts\python.exe maintenance/audit_analysis_v5_pilot_rev2.py
```
