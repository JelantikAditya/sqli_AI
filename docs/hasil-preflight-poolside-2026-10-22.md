# Hasil preflight Poolside, 22 Oktober 2026

**Status:** koneksi, smoke kontrak output, dan evaluasi pengembangan P2 telah
selesai. Seluruh 18 verdict P2 cocok dengan label referensi terkunci pada
seluruh 18 kasus yang evaluable. P3 Poolside dan eksperimen formal belum
dijalankan. Hasil ini tidak menutup milestone melalui penerimaan peneliti
secara otomatis.

## Backend yang benar-benar diakses

- Provider langsung: `https://inference.poolside.ai/v1`.
- Requested/reported model: `poolside/laguna-s-2.1`.
- Katalog pada smoke akun mencatat context length 262.144 token, quantization
  `fp4`, `is_free=true`, serta nilai pricing nol pada saat request.
- Metadata layanan ini tidak memverifikasi bobot secara independen dan tidak
  menjamin bahwa kapasitas, harga, atau route tetap sama pada pengujian berikutnya.
- Key dimuat dari konfigurasi lokal tanpa ditampilkan. File key tidak termasuk
  plan, prompt, arsip source, atau receipt.

## Tiga tahap pengujian

| Tahap | Request | Hasil | Token dilaporkan |
| --- | ---: | --- | ---: |
| Koneksi oleh peneliti | 2 | GET model dan chat sama-sama HTTP 200; `API_OK` | 54 |
| Smoke kontrak | 2 | Generasi S1 `generated`; analisis satu bukti P2 `ok` | 1.635 |
| Evaluasi P2 Poolside | 18 | 18 HTTP 200, 18 output valid, 18 agreement | 25.684 |

Jumlah keseluruhan adalah 22 request dan 27.373 token yang dilaporkan pada
tiga tahap terpisah. Dua puluh request dilakukan setelah peneliti menyampaikan
hasil koneksi awal. Tidak ada retry, fallback, request DVWA, atau reset database.
Jumlah ini adalah pencatatan pemakaian, bukan penggabungan sampel evaluasi.

Smoke kontrak menggunakan satu kandidat S1 berdasarkan koordinat black-box,
tanpa menyisipkan source-code SQL target. Kandidat hanya diperiksa parser,
tidak dieksekusi. Request generasi memerlukan 1,479 detik dan analisis 4,505
detik. Tidak ada warning parser. Label referensi tidak dibaca oleh smoke.

## Profil dan hasil P2

Run ID: `poolside-p2-20261022T094120890211Z`.

Profil `poolside-laguna-s-2.1-p2-evidence-v1-no-thinking` mempertahankan semua
18 dokumen bukti, pesan, schema dan urutan paket P2 Qwen. Hash paket asal:
`71ccaa86eb9a563dd56815991fecd828828d2a637709c08657158997efd2dfb6`.
Request Poolside memiliki hash payload baru yang dicatat per kasus.

- Temperature 0, maksimum output 2048 token per kasus, RAG nonaktif.
- Thinking dimatikan secara eksplisit; timeout transport 60 detik.
- Maksimum 18 request, satu attempt per kasus, tanpa pengiriman ulang.
- Plan disimpan sebelum inferensi. Runner tidak membaca anotasi referensi.
- Sesudah batch selesai, assessor P2 yang sudah ada membandingkan hasil
  dengan anotasi VAL-01 terkunci; hash anotasi dan konfirmasi peneliti lolos
  pemeriksaan assessor.

| Ukuran | Hasil |
| --- | ---: |
| Request terencana/terkirim | 18/18 |
| Output valid/evaluable | 18/18 |
| Coverage | 100% |
| Agreement pada output evaluable | 18/18, 100% |
| Unresolved | 0 |
| HTTP error / timeout / warning parser | 0 / 0 / 0 |
| Total durasi API tercatat | 128,418 detik |
| Prompt / completion / total token | 20.981 / 4.703 / 25.684 |

| Teknik | Evaluable | Agreement |
| --- | ---: | ---: |
| Error-based | 6/6 | 6/6 |
| Boolean-based blind | 6/6 | 6/6 |
| Time-based blind | 6/6 | 6/6 |

Setiap label positive, negative dan inconclusive memiliki enam kasus dan
agreement 6/6. Kasus `rv-e6f30675d8d4` yang unresolved pada P2 Qwen run-005
kini menghasilkan respons valid, dengan verdict negative yang cocok dengan
referensi. Hasil historis Qwen tetap dipertahankan.

## Verifikasi dan batas interpretasi

- Sepuluh tes transport/credential dan tiga tes integrasi P2 lulus offline.
- Ketujuh hash source/input masing-masing tahap kontrak dan P2 cocok dengan
  plan. Enam source P2 diarsipkan sebagai salinan pada direktori run.
- Kedua parse smoke dan seluruh 18 parse P2 direproduksi offline dari respons
  tersimpan. Hash payload yang benar-benar dikirim cocok pada seluruh 18 kasus.
- Replay offline memblokir koneksi socket; tidak mengirim request API baru.
- Semua kasus P2 berasal dari paket lama yang telah diketahui, bukan holdout
  baru. Satu kasus juga digunakan pada smoke kontrak; kasus tersebut tetap
  dihitung hanya sekali dalam 18 sampel P2.
- Profil Qwen lama menggunakan timeout 90 detik dan tidak mengatur thinking
  secara eksplisit. Perubahan provider, model, serta profil membuat perbedaan
  hasil tidak dapat diatribusikan hanya kepada provider atau kemampuan model.
- Ini adalah agreement/coverage pengembangan analisis bukti, bukan FPR/PSR
  formal, bukan evaluasi ablasi RAG, dan bukan bukti PSR kandidat generasi.
- Belum diuji kestabilan ratusan request, generasi semua teknik/level,
  keragaman sepuluh kandidat per unit, ataupun integrasi P3 A/B/C.

Tindak lanjut: preflight generasi tiga teknik dengan konteks black-box dan
jalur RAG, lalu siapkan adapter, profil, budget serta experiment ID baru untuk
P3 Poolside. Jangan memakai hasil ini untuk resume cohort Qwen lama.

## Artefak

- Koneksi: `results/raw/poolside-smoke/20261022T093612947929Z.json`.
- Kontrak: `results/raw/poolside-contract-smoke/20261022T093837654979Z/`.
- P2: `results/raw/poolside-p2/20261022T094120890211Z/`.
- Assessment: `evaluation-assessment.json` dalam direktori P2.
- Receipt: `docs/evidence/poolside-api-preflight-2026-10-22.json`.
- Penggunaan skrip: `docs/poolside-api-smoke.md`.
