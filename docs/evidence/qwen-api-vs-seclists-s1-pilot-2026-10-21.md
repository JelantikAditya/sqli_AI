# Hasil pilot pembanding Qwen API dan SecLists, S1 Low

## Ringkasan

Run pembanding condition C selesai pada 21 Oktober 2026. Kedua run menguji sepuluh kandidat unik untuk DVWA S1 Low, SQLi error-based, dengan tiga konfirmasi per kandidat. Executor memberi sinyal sukses terkonfirmasi pada 3 dari 10 kandidat Qwen B dan 2 dari 10 kandidat SecLists C. Peneliti mengonfirmasi label pada kedua run setelah melihat laporan. Angka ini tetap hitungan pilot dan bukan PSR formal.

Run SecLists memakai plan dan ID eksperimen baru. Run C S1 yang lebih lama dari 14 Oktober tetap tidak diubah. Tidak ada API yang dipanggil untuk condition C.

| Kondisi | Sumber kandidat | Run dan attempt | Kandidat valid | Sinyal sukses 3/3 | Status review |
|---|---|---|---:|---:|---|
| B | Qwen 3.8 API dengan RAG aktif | `qwen38-api-b-s1-r1-20261021`, `attempt-1-b581ee7c3b` | 10 | 3 | Label 3 positif dan 7 negatif dikonfirmasi peneliti |
| C | SecLists terkunci | `qwen38-c-s1-pilot-20261021`, `attempt-1-bc2cdec5a1` | 10 | 2 | Label 2 sukses dan 8 gagal dikonfirmasi peneliti |

Kedua run mencatat reset database DVWA dan 60 logical probe submissions. Run C mencatat 156 request HTTP. Recovery run B mencatat 159 request HTTP dan 20 request API. Satu request API tambahan berasal dari attempt B sebelumnya yang invalid sebelum payload kandidat dieksekusi; attempt itu tidak termasuk dalam perbandingan 10 kandidat.

## Review kandidat SecLists

Pada 21 Oktober 2026, peneliti menyatakan hasil S1 C sudah sesuai. Konfirmasi ini berlaku untuk seluruh sepuluh label di bawah, setelah melihat ringkasan laporan, dan bukan anotasi blind VAL-01. Untuk audit bukti, log tetap menyediakan tiga respons `single` dan tiga baseline per kandidat, dikelompokkan menurut `candidate_id` dan confirmation index. `HTTP 200` sendiri bukan bukti sukses.

| Candidate ID | Baris SecLists | Sinyal executor | Bukti ringkas | Anotasi reviewer | Catatan |
|---|---:|---|---|---|---|
| `run-e4f6c7cf2297411b-c001` | 1 | Positif, 3/3 | `mysql_syntax_error` pada seluruh respons kandidat; baseline tanpa diagnostik | success | |
| `run-e4f6c7cf2297411b-c002` | 2 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c003` | 3 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c004` | 4 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c005` | 5 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c006` | 6 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c007` | 7 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c008` | 8 | Positif, 3/3 | `mysql_xpath_error` pada seluruh respons kandidat; baseline tanpa diagnostik | success | |
| `run-e4f6c7cf2297411b-c009` | 9 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |
| `run-e4f6c7cf2297411b-c010` | 13 | Negatif, 0/3 | Tidak ada diagnostik pada respons kandidat; baseline memiliki marker `benign_record` | failure | |

## Batas interpretasi

Run ini berstatus dataset pilot, satu kondisi per sumber, satu skenario, dan satu replikasi. Hasil 3/10 pada B dan 2/10 pada C belum membuktikan keunggulan salah satu sumber. Perbandingan PSR penelitian tetap memerlukan run formal lengkap dan validasi sesuai protokol.

Receipt dan log run mentah menyimpan status saat eksekusi, termasuk `human_validation: pending`. Dokumen ini adalah ringkasan pasca-run dan lembar review C, bukan perubahan pada receipt eksekusi.

## Artefak

- Hasil terstruktur JSON: [qwen-api-vs-seclists-s1-pilot-2026-10-21.json](qwen-api-vs-seclists-s1-pilot-2026-10-21.json)
- Receipt dan review condition B: [receipt pilot B](qwen-api-b-pilot-run-receipt-2026-10-21.md) dan [review manusia B](qwen-api-b-pilot-human-review-2026-10-21.md)
- Snapshot plan C: [plan.snapshot.json](../../results/raw/pilot/qwen38-c-s1-pilot-20261021/plan.snapshot.json)
- Checkpoint C: [checkpoint.json](../../results/raw/pilot/qwen38-c-s1-pilot-20261021/checkpoint.json)
- Input batch kandidat dan provenance SecLists: [runner-input.json](../../results/raw/pilot/qwen38-c-s1-pilot-20261021/attempts/qwen38-c-s1-pilot-20261021-c-s1-r1/attempt-1-bc2cdec5a1/runner-input.json)
- Bukti respons, baseline, diagnostik, dan anotasi executor: [validation.jsonl](../../results/raw/pilot/qwen38-c-s1-pilot-20261021/attempts/qwen38-c-s1-pilot-20261021-c-s1-r1/attempt-1-bc2cdec5a1/validation.jsonl)
- Pemetaan ID kandidat: [candidate-id-map.json](../../results/raw/pilot/qwen38-c-s1-pilot-20261021/attempts/qwen38-c-s1-pilot-20261021-c-s1-r1/attempt-1-bc2cdec5a1/candidate-id-map.json)
