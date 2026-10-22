# Preflight generasi dan persiapan P3 Poolside

**Hasil 22 Oktober 2026:** enam request generasi pada tiga teknik dan kondisi
A/B mendapat HTTP 200. Seluruh enam kandidat lolos parser serta kebijakan
teknik. Adapter P3 Poolside dan rencana cohort baru telah lolos pemeriksaan
offline. P3 belum dieksekusi dan tidak ada request DVWA pada tahap ini.

## Profil preflight

- Model `poolside/laguna-s-2.1`, endpoint langsung Poolside, temperature 0.
- Maksimum output 1024 token, thinking nonaktif, timeout 60 detik.
- Enam request maksimum, satu kandidat logis per kasus, tanpa retry/fallback.
- S1 error-based, S2 boolean-based blind, S3 time-based blind, semuanya Low.
- Urutan A/B mengikuti rotasi: S1 A-B, S2 B-A, S3 A-B.
- Prompt memakai builder black-box aktif yang juga digunakan adapter P3.
  Tidak ada source-code SQL target atau label ground truth dalam prompt.
- Tidak ada pengukuran baseline baru. Prompt diberi objek baseline kosong
  yang sama pada A/B, tanpa merekayasa pengukuran HTTP.

## Retrieval dan isolasi A/B

Korpus proposal, source lock dan indeks yang sebelumnya disetujui untuk pilot
digunakan kembali dengan hash yang sama. Tiga query embedding lokal memakai
`nomic-embed-text`, lalu Chroma mengambil top-2 semantic entries untuk setiap
teknik. Tidak ada technique filter, reranking, atau lexical expansion.

Kondisi A dirender sebelum indeks dibuka dan tidak menerima konteks RAG.
Kondisi B memakai salinan indeks, dengan proyeksi maksimum 1800 karakter per
chunk sesuai adapter aktif. Kedua prompt dalam setiap pasangan hanya berbeda
pada `retrieved_reference_chunks`. Seluruh hash indeks sumber cocok setelah
retrieval; indeks aktif tidak diubah.

## Hasil live

| Skenario | Kondisi | HTTP | Parser/policy | Latency API | Token |
| --- | --- | ---: | --- | ---: | ---: |
| S1 error-based | A | 200 | Lolos | 3,382 detik | 358 |
| S1 error-based | B | 200 | Lolos | 1,261 detik | 1.023 |
| S2 boolean blind | B | 200 | Lolos | 1,852 detik | 1.203 |
| S2 boolean blind | A | 200 | Lolos | 1,122 detik | 413 |
| S3 time blind | A | 200 | Lolos | 2,388 detik | 379 |
| S3 time blind | B | 200 | Lolos | 2,696 detik | 1.199 |

Total: **6 request, 6 kandidat valid, 4.575 token, dan 12,701 detik durasi API**.
Tidak ada transport error, metadata mismatch, output terpotong, atau retry.
Enam parse direproduksi offline dan hash seluruh payload cocok dengan plan.

S1 A/B menghasilkan kandidat yang sama. S2 A menghasilkan pasangan quoted,
sementara B menghasilkan pasangan numerik. Kedua kandidat S3 menggunakan
satu literal `SLEEP(2)`; kontrolnya berhasil diturunkan dengan mengganti hanya
nilai delay menjadi `SLEEP(0)`. Kesesuaian kandidat terhadap konteks target
aktual belum dibuktikan. Kandidat numerik pada S2/S3 tetap harus dinilai lewat
respons HTTP, bukan dianggap sukses karena lolos parser.

Hasil ini menguji format, batas kandidat, dan integrasi RAG. Ini bukan PSR,
FPR, bukti manfaat RAG, atau uji keragaman sepuluh kandidat per unit. Medium,
High dan Impossible belum mendapat generasi Poolside pada preflight ini.

## Adapter P3 yang disiapkan

Adapter baru mempertahankan executor, urutan kondisi, ledger, parser bukti,
dan memory duplikat per slot dari P3 v5. Ia memakai key Poolside dan endpoint
langsung, dengan checkpoint sebelum setiap request. Error layanan menahan
unit; tidak ada retry transport, fallback, resume, atau replacement otomatis.

Profil analisis sama persis dengan P2 Poolside: temperature 0, output maksimum
2048 token, thinking nonaktif, timeout 60 detik, dan tanpa RAG pada analisis
kondisi A maupun B. Seluruh 18 payload cocok dengan P2. Replay callback pada
A/B menghasilkan 36 analisis yang cocok dengan verdict P2 tersimpan.

Input runtime/baseline invalid tertahan sebelum API. Output dengan referensi
atau trial rekaan tidak menjadi klaim biner valid. Verdict salah secara
semantik tetap dipertahankan untuk evaluasi. Sepuluh tes adapter dan lima
tes preflight baru lulus offline dengan socket diblokir pada pemeriksaan
adapter. Binding callback dipulihkan setelah eksekusi atau exception.

## Rencana cohort baru yang dapat ditinjau

| Properti | Nilai |
| --- | --- |
| Experiment ID | `poolside-s21-p3-r1-20261022` |
| Protocol ID | `poolside-laguna-s21-sqli-v1-pilot` |
| Cakupan | S1-S12, empat level DVWA, A/B/C, satu replikasi |
| Slot / unit applicable | 36 / 33 |
| Unit LLM A/B | 24 |
| Kandidat target | 330 |
| Konfirmasi logis | 990 |
| Maksimum request generasi per slot | 3 |
| Ceiling request API | 960 |
| Ceiling waktu | 21.600 detik, enam jam |
| Timeout generasi / analisis | 60 / 60 detik |
| Retry transport / replacement | 0 / 0 |
| Status eksekusi | Belum dimulai |

Tiga slot C pada Impossible excluded sesuai desain. Ceiling API berasal dari
24 unit LLM x 10 kandidat x (maksimum tiga generasi + satu analisis).
Enam jam adalah batas waktu, bukan perkiraan durasi selesai. Runner memeriksa
deadline sebelum unit/request; request atau unit yang sedang berjalan tidak
diputus paksa oleh timer terpisah. Konfirmasi logis bukan jumlah request HTTP.

Dry-run memvalidasi plan, korpus, indeks, sumber SecLists dan 45 pin source/input
tanpa membaca key atau menghubungi API/DVWA. Preview protokol dan salinan
source tersedia di direktori persiapan. Hasil Qwen dan formal lokal dipertahankan.

Pelaksanaan P3 berikutnya akan memakai DVWA lokal, melakukan reset database
sebelum kondisi sesuai protokol, dan mengonsumsi API sampai batas yang
ditetapkan. Scope tersebut terpisah dari enam request preflight ini.

## Pemeriksaan dan pelaksanaan

Periksa paket tanpa mengirim request:

```powershell
.\.venv\Scripts\python.exe development\run_bounded_poolside_p3.py
```

Setelah keputusan pelaksanaan P3 dibuat:

```powershell
.\.venv\Scripts\python.exe development\run_bounded_poolside_p3.py `
  --execute --confirm-local-dvwa --confirm-database-reset --confirm-api-spending
```

Runner menolak experiment ID yang sudah memiliki direktori hasil. Setiap
cohort berikutnya memerlukan identitas baru dan paket tersendiri. Kelengkapan
P3, review peneliti, dan validasi independen tetap diperlukan sebelum formal.

## Artefak

- Preflight: `results/raw/poolside-generation-preflight/20261022T095049537491Z/`.
- Persiapan P3: `results/raw/development/poolside-s21-p3-r1-20261022-preparation-r2/`.
- Plan: `development/poolside_p3_plan.template.json`.
- Budget: `development/poolside_p3_budget_20261022.json`.
- Launcher: `development/run_bounded_poolside_p3.py`.
- Transport: `development/poolside_p3_runtime.py`.
- Receipt: `docs/evidence/poolside-generation-preflight-2026-10-22.json`.
