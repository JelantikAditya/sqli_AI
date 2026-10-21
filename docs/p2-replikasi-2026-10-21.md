# Replikasi teknis P2, 21 Oktober 2026

## Rencana yang dibekukan

Peneliti menyetujui satu replikasi penuh pada 18 kasus P2 yang sama. Paket
`qwen38-api-p2-eval-20261021-run-002` memakai urutan, bukti, request, model,
prompt, parser, label VAL-01, batas output 2048 token dan timeout 90 detik
yang sama. RAG tetap nonaktif. Perubahan loader credential hanya memberi
opsi membaca key lokal; payload request tidak berubah.

Alasannya adalah melengkapi pengamatan setelah tiga request run pertama
terputus secara lokal dan satu timeout transport, serta memeriksa konsistensi
keputusan pada kasus yang dapat dinilai di kedua run. Batasnya 18 request,
satu percobaan per kasus, tanpa retry. Timeout tanpa respons dapat dicatat
sebagai unresolved dan dilanjutkan ke kasus berikutnya; error HTTP atau
metadata model yang tidak sesuai menghentikan batch.

Set ini sudah diketahui peneliti. Replikasi bukan holdout baru; kedua run
dilaporkan terpisah dan tidak dihitung sebagai 36 kasus independen. Enam kasus
input invalid tetap berada di luar API sesuai gate paket awal. Hash request
tetap `71ccaa86eb9a563dd56815991fecd828828d2a637709c08657158997efd2dfb6`.

Rencana dibekukan sebelum eksekusi pada
[plan run-002](evidence/qwen-api-p2-run002-plan-2026-10-21.json).

## Hasil eksekusi

Pada **21 Oktober 2026, 19:13 WIB**, gateway menolak request pertama dengan
HTTP 503 setelah 2,383 detik. Respons menyebut `system_cpu_overloaded` dan
`system cpu overloaded (current: 99.6%, threshold: 98%)`. Ini laporan beban
dari layanan API; bukan hasil pengukuran CPU laptop peneliti. Detail tersebut
tidak menetapkan komponen internal provider yang bermasalah.

| Bagian | Hasil |
| --- | --- |
| Status run | `halted` |
| Request terencana | 18 |
| Request mulai/terkirim | 1 |
| Kasus yang belum mulai | 17 |
| Respons analisis Qwen yang dapat dinilai | 0 |
| Retry atau run pengganti | 0 |
| Agreement | Tidak tersedia |

Kasus pertama adalah `rv-797b4070416e`. Tidak ada keputusan model, metadata
model respons, atau token usage yang diterima. Status penagihan tidak diketahui.
Karena batch tidak lengkap, assessor 18 kasus tidak dijalankan dan skor
kompetensi tidak dibuat. Coverage respons yang bisa dinilai adalah 0/18;
angka ini tidak berarti 18 kesalahan reasoning model.

## Preservasi dan interpretasi

Sebelum eksekusi, 49 file dari run-001 dan paket persiapan serta sepuluh file
source dipin. Seluruh hash tetap cocok setelah run-002 berhenti. Enam tes
runner termasuk pengunci lintas proses lulus sebelum request dikirim.

Run-001 tetap memiliki 14/18 kasus yang dapat dinilai dengan agreement 14/14.
Run-002 memberi observasi kegagalan operasional provider dan belum menambah
bukti kemampuan analisis. Hasil keduanya tidak digabung menjadi satu skor.
Tidak ada perubahan prompt, label, parser, ataupun retry setelah error terlihat.
Penutupan milestone P2 belum diputuskan dan tidak dinaikkan menjadi selesai.

[Receipt eksekusi](evidence/qwen-api-p2-run002-receipt-2026-10-21.json)
menyimpan hash plan, manifest dan hasil tersanitasi. Artefak mentah tetap pada
`results/raw/development/qwen38-api-p2-eval-20261021-run-002/`, yang diabaikan Git.

Langkah berikutnya adalah memeriksa ketersediaan provider sebelum menetapkan
run tambahan dengan ID dan budget baru, atau menerima keterbatasan data P2
yang sudah tersedia. Run-002 tidak ditimpa atau dikirim ulang secara otomatis.

## Pemeriksaan ulang dan run-003

Peneliti kemudian meminta menjalankan ulang P2 untuk memeriksa apakah Qwen
sudah dapat diakses. Run-003 disiapkan dengan ID baru, parameter serta request
yang sama dan batas maksimum 18 request tanpa retry. Request pertama P2 juga
menjadi pemeriksaan ketersediaan, sehingga tidak ada panggilan preflight tambahan.
[Plan run-003](evidence/qwen-api-p2-run003-plan-2026-10-21.json) dibekukan
sebelum API dipanggil.

Pada **21 Oktober 2026, 19:56 WIB**, request pertama kembali menerima HTTP
503 setelah 1,611 detik. Kode error tetap `system_cpu_overloaded`; kali ini
gateway melaporkan CPU 99,5% terhadap ambang 98%. Gateway terjangkau, tetapi
belum melayani analisis P2 pada percobaan ini. Beban yang disebut berasal dari
laporan layanan, bukan pengukuran laptop peneliti.

Status run-003 adalah `halted`: satu request dikirim, 17 belum dimulai, nol
jawaban analisis yang bisa dinilai dan nol retry. Assessor tidak dijalankan
karena batch belum lengkap. Agreement tidak tersedia. Tidak ada metadata model
respons atau token usage; status penagihan tidak diketahui.

Seluruh 61 file historis/paket/receipt yang dipin dan sepuluh source tetap
cocok dengan hash sebelum eksekusi. Run-001 dan run-002 dipertahankan. P2 belum
ditutup dan belum memperoleh bukti kemampuan tambahan dari run-003.
[Receipt run-003](evidence/qwen-api-p2-run003-receipt-2026-10-21.json)
mencatat hasil serta hash artefak. Tidak ada polling, retry, atau run pengganti
yang dijadwalkan otomatis.

## Run-004 setelah uji akses singkat berhasil

Setelah uji akses terpisah pada 20:34 WIB menghasilkan HTTP 200 dan `API_OK`,
peneliti meminta P2 dijalankan kembali. Run-004 dibekukan dengan 18 request
P2 yang sama, satu percobaan per kasus dan parameter yang tetap. Tidak ada
uji akses tambahan sebelum batch. Lihat
[plan run-004](evidence/qwen-api-p2-run004-plan-2026-10-21.json).

Pada **21 Oktober 2026, 20:36 WIB**, request pertama menerima HTTP 503 setelah
2,567 detik. Gateway kembali melaporkan `system_cpu_overloaded`, CPU 99,5%
terhadap ambang 98%. Status `halted`: satu request dikirim, 17 belum dimulai,
nol respons analisis yang bisa dinilai, dan nol retry. Assessor tidak
dijalankan karena batch belum lengkap. Metadata model respons dan token usage
tidak tersedia; status penagihan tidak diketahui.

Uji singkat dan request P2 berbeda pada pesan, budget keluaran dan opsi
template. Pengamatan ini belum menetapkan penyebab perbedaan ketersediaan
antarrequest. Keberhasilan uji akses sebelumnya tidak menjamin layanan mampu
melayani batch P2 berikutnya; error yang teramati pada batch tetap HTTP 503.

Seluruh 76 file historis/paket/receipt dan sepuluh source yang dipin tetap
utuh. Run-001 tetap memiliki 14/18 respons yang bisa dinilai dengan agreement
14/14. Run-002, run-003 dan run-004 dipertahankan sebagai batch yang berhenti
pada request pertama, tanpa mengubah hasil kompetensi atau menutup milestone P2.
[Receipt run-004](evidence/qwen-api-p2-run004-receipt-2026-10-21.json)
mengikat hasil dan hash artefak. Langkah berikutnya adalah memeriksa kesiapan
layanan provider sebelum pengumpulan tambahan; audit offline P3 dapat
dikerjakan tanpa mengirim request API.
