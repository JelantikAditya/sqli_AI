# Preflight generasi payload SQLi dengan alias API Qwen3.8-27B

Tanggal 20 Oktober 2026. Dokumen ini merekam batch generasi awal v1/v2 untuk S1-S3 DVWA Low, sebelum kandidat dieksekusi. Tidak ada FPR atau PSR yang dihitung. Pembaruan setelah kandidat ringkas diuji di DVWA tercatat di [hasil pilot generasi API](hasil-pilot-generasi-qwen-api-2026-10-20.md). API key tidak disimpan pada artefak.

## Kontrak dan prosedur

Adapter `development/qwen_api_generation.py` memakai prompt versi `qwen38-api-sqli-generation-v1-no-nonce`. Slot kandidat adalah metadata sehingga nilai numerik 101-110 tidak dipaksakan ke parameter DVWA. Respons diperiksa terhadap JSON Schema lokal, aturan payload error-based, dan kesamaan struktur kandidat. Panggilan dijalankan serial, tanpa retry tersembunyi. Keluaran penyedia, request hash, penggunaan token, dan kegagalan disimpan pada checkpoint lokal yang dikecualikan dari Git.

Preflight pertama meminta satu kandidat per teknik dengan `temperature=0`, `max_tokens=2048`, dan timeout 90 detik. Setelah S2 terpotong dan S3 timeout, preflight kedua mengirim **request baru** untuk S2/S3 dengan `max_tokens=4096` serta timeout 150 detik. Plan kedua mem-pin hash semua hasil pertama. Keduanya merupakan diagnosis parameter layanan, bukan satu konfigurasi eksperimen yang homogen.

| Skenario | Teknik | Batas output / timeout | Hasil API | Hasil generasi | Waktu |
| --- | --- | --- | --- | --- | ---: |
| S1 | Error-based | 2.048 token / 90 dtk | `ok` | `1'` lolos parser | 7,621 dtk |
| S2 | Boolean-based blind | 2.048 token / 90 dtk | `truncated` | Tidak ada kandidat | 60,031 dtk |
| S3 | Time-based blind | 2.048 token / 90 dtk | `transport-error` | Tidak ada kandidat | 90,134 dtk |
| S2, request baru | Boolean-based blind | 4.096 token / 150 dtk | `transport-error` | Tidak ada kandidat | 150,476 dtk |
| S3, request baru | Time-based blind | 4.096 token / 150 dtk | `truncated` | Tidak ada kandidat | 138,490 dtk |

Pada S2 pertama, seluruh 2.048 completion token dilaporkan sebagai reasoning token dan tidak ada kandidat akhir. Pada S3 kedua, seluruh 4.096 completion token juga dilaporkan sebagai reasoning token. Dua timeout tidak memiliki envelope respons sehingga tidak memberi usage atau metadata model. Tiga respons yang memiliki envelope melaporkan `self-dploy/Qwen3.8-27B`, yaitu identitas yang dilaporkan gateway dan belum memverifikasi bobot model secara independen.

[Audit replay offline](../results/processed/qwen38-api-generation-smoke-20261020/audit.json) memeriksa kedua plan dan receipt, sumber skenario, hash request, lima attempt, hasil mentah, serta keluaran parser. Audit menghasilkan 1 `ok`, 2 `truncated`, 2 `transport-error`, tanpa panggilan model atau DVWA saat audit. Arsip raw lokal di `results/raw/development/qwen38-api-generation-smoke-20261020` dan `...-v2` diperlukan untuk mereproduksi pemeriksaan penuh.

## Keputusan setelah batch v1/v2

Generasi API saat ini **belum lulus gate lintas teknik**. S1 hanya membuktikan keluaran dapat diparse, bukan keberhasilan SQLi. S2/S3 belum menghasilkan kandidat sehingga pilot A/B pada DVWA dan freeze formal versi API belum sah dimulai. Menaikkan batas output saja tidak menyelesaikan masalah ini.

Langkah pengembangan berikutnya adalah versi prompt baru yang lebih ringkas untuk satu kandidat boolean dan time, dengan batas panggilan yang ditetapkan sebelum percobaan. Perubahan prompt harus diberi versi dan diuji pada S1-S3 sebelum pilot DVWA. Jangan mencampur hasil preflight ini dengan metrik formal Qwen lokal terdahulu atau menukar model tanpa versi eksperimen baru. Validator independen sudah dinyatakan siap oleh peneliti, tetapi paket blind baru dibuat dari bukti DVWA yang benar-benar dihasilkan.
