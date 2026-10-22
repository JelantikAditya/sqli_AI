# Replikasi teknis P2 run-005, 22 Oktober 2026

**Hasil:** Qwen API berhasil melayani 17 dari 18 request P2. Seluruh 17
verdict yang dapat dinilai cocok dengan label VAL-01 terkunci. Satu kasus
time-based blind mengalami timeout transport 90 detik tanpa respons HTTP dan
tetap unresolved. Tidak ada retry atau request pengganti.

## Pemeriksaan akses sebelum batch

Pada **22 Oktober 2026, 10:36:08 WIB**, satu request singkat menerima HTTP
200 dengan isi `API_OK` dalam **1,552 detik**. Alias yang diminta adalah
`Qwen3.8-27B`; metadata respons melaporkan `self-dploy/Qwen3.8-27B`.
Identitas bobot model tidak diverifikasi independen.

Pemeriksaan ini memakai batas keluaran 128 token, timeout 30 detik dan
`enable_thinking=false`. Ini berbeda dari profil analisis P2 dan hanya
menjadi pemeriksaan akses. Hasil batch berikutnya memberi bukti tersendiri
tentang ketersediaan request P2 yang lebih panjang.

[Receipt pemeriksaan akses](evidence/qwen-api-access-check-2026-10-22.json)
memuat hash tiga artefak lokal. Tidak ada credential dalam receipt.

## Rencana yang dikunci

Peneliti meminta pemeriksaan akses dan pengulangan P2 sebelum melanjutkan P3.
Setelah pemeriksaan berhasil, run baru
`qwen38-api-p2-eval-20261022-run-005` disiapkan dan lolos dry-run sebelum
eksekusi. Run-001 sampai run-004 dipertahankan.

- Menggunakan 18 kasus, urutan, bukti, label VAL-01, prompt dan parser yang
  sama. Set telah diketahui peneliti; ini bukan holdout independen baru.
- Hash prepared requests tetap
  `71ccaa86eb9a563dd56815991fecd828828d2a637709c08657158997efd2dfb6`.
- Kontrak `qwen38-api-p2-explicit-evidence-v1`, RAG nonaktif,
  `temperature=0`, maksimum 2048 token keluaran dan timeout 90 detik.
- Maksimum 18 request P2, satu percobaan per kasus tanpa retry. Pemeriksaan
  akses terpisah memakai satu request, sehingga total maksimum 19 request.
- Timeout tanpa respons dipertahankan sebagai unresolved dan kasus berikutnya
  yang belum dimulai dapat dilanjutkan. HTTP error atau metadata model tidak
  sesuai menghentikan batch. Tidak ada fallback backend.
- Enam kasus gate invalid pada paket terdahulu tidak dikirim ke API. Run ini
  mengulang 18 kasus eligible, bukan mengulang pengujian gate invalid.

[Plan run-005](evidence/qwen-api-p2-run005-plan-2026-10-22.json) dibekukan
sebelum request P2 pertama. Runner tidak membaca anotasi validator selama
inferensi; assessor membacanya setelah eksekusi.

## Hasil eksekusi dan assessment

Batch dimulai **10:37:04 WIB** dan berakhir **10:49:29 WIB**, sekitar
12 menit 25 detik. Jumlah durasi API yang tercatat adalah 744,694 detik.
Tidak ada request DVWA, reset database atau pengujian payload baru.

| Bagian | Hasil |
| --- | ---: |
| Status run | `completed_with_ambiguity` |
| Request P2 terencana/terkirim | 18/18 |
| Respons API valid dan evaluable | 17 |
| Timeout tanpa respons HTTP | 1 |
| HTTP error pada batch | 0 |
| Analysis error pada respons yang diterima | 0 |
| Warning parser pada respons yang diterima | 0 |
| Agreement terhadap label terkunci | 17/17, 100% pada kasus evaluable |
| Coverage seluruh paket | 17/18, 94,44% |
| Retry | 0 |
| Total request termasuk pemeriksaan akses | 19 |

| Teknik | Kasus terencana | Evaluable | Cocok dengan referensi | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| Error-based | 6 | 6 | 6 | 0 |
| Boolean-based blind | 6 | 6 | 6 | 0 |
| Time-based blind | 6 | 5 | 5 | 1 |

Coverage menurut label referensi adalah positive 6/6, negative 5/6 dan
inconclusive 6/6. Seluruh kasus yang terjawab cocok dengan label. Agreement
100% ini bersyarat pada respons evaluable dan bukan akurasi 18/18.

Kasus unresolved adalah **`rv-e6f30675d8d4`**, time-based blind dengan label
referensi negative. Statusnya `transport-error`, tanpa respons HTTP atau
verdict model. Provider mungkin sudah menerima request; penyelesaiannya
tidak diketahui. Kasus tidak dikirim ulang dan tidak dihitung benar atau
salah dalam denominator agreement.

Metadata seluruh 17 respons melaporkan `self-dploy/Qwen3.8-27B`. Gateway
melaporkan 39.307 token pada respons yang tersedia, terdiri dari 20.342 token
prompt dan 18.965 token completion. Tidak ada usage untuk request timeout;
angka tersebut bukan total penagihan final.

## Perbandingan dengan run-001

| Ukuran | Run-001 | Run-005 |
| --- | ---: | ---: |
| Evaluable/terencana | 14/18 | 17/18 |
| Coverage | 77,78% | 94,44% |
| Cocok dengan referensi pada kasus evaluable | 14/14 | 17/17 |
| Unresolved | 4 | 1 |

Pada **14 kasus yang evaluable di kedua run, seluruh keputusan identik**.
Tiga dari empat kasus yang dahulu unresolved kini evaluable dan cocok dengan
referensi: satu boolean negative, satu error-based negative, dan satu
time-based inconclusive. Kasus time-based negative tetap unresolved.

Kedua run menggunakan kasus yang sama. Hasil tidak digabung menjadi 31 atau
36 sampel independen, dan pengulangan ini bukan holdout baru.

## Preservasi dan keterbatasan

Seluruh **91 file historis/paket/receipt** dan **10 file source** yang dipin
sebelum run tetap cocok setelah eksekusi. Semua 17 parse direproduksi
offline dari respons tersimpan dan cocok dengan hasil runner. Tidak ada
perubahan prompt, parser, label, aturan skor atau kode P3.

Key dimuat melalui loader lokal tanpa menampilkan atau mencatat nilainya.
Status rotasi key yang disebut dalam insiden terdahulu tetap belum
diverifikasi independen; keberhasilan akses tidak membuktikan rotasi.

Ini adalah evaluasi pengembangan pembacaan bukti SQLi, **bukan FPR/PSR
formal**, bukan pengujian generasi payload dan bukan bukti bahwa RAG unggul.
Receipt eksekusi tidak menutup milestone secara otomatis. Setelah meninjau
laporan ini, peneliti menerima hasil 17/18 dengan satu unresolved dan
**menutup P2 pada 22 Oktober 2026**. Keputusan disimpan terpisah pada
[receipt penutupan P2](evidence/qwen-api-p2-closure-2026-10-22.json), tanpa
mengubah receipt atau assessment eksekusi. Tidak ada retry, pemantauan atau
run tambahan yang dijadwalkan.

Peneliti kemudian meminta perbaikan P3. Ketiga temuan telah ditangani dan
diverifikasi offline; lihat [laporan perbaikan P3](perbaikan-p3-2026-10-22.md).
Pilot live versi baru dan formal API belum dijalankan.

## Artefak

- [Receipt run-005 dan metrik](evidence/qwen-api-p2-run005-receipt-2026-10-22.json)
- [Plan sebelum eksekusi](evidence/qwen-api-p2-run005-plan-2026-10-22.json)
- [Receipt pemeriksaan akses](evidence/qwen-api-access-check-2026-10-22.json)
- [Assessment resmi](../results/raw/development/qwen38-api-p2-eval-20261022-run-005/evaluation-assessment.json)
- [Perbandingan antarrun](../results/raw/development/qwen38-api-p2-replication-run005-20261022/replication-comparison.json)
- [Hasil dan respons lokal](../results/raw/development/qwen38-api-p2-eval-20261022-run-005/evaluation-results.json)

Artefak mentah berada dalam `results/raw/` yang dikecualikan dari Git. Receipt
yang dapat dilacak memuat hash artefak tersebut; tidak ada commit atau push
pada pengujian ini.
