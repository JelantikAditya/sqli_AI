# Hasil eksekusi cohort pemulihan P3, 22 Oktober 2026

Pilot pengembangan `qwen38-api-r2-20261022` dimulai setelah peneliti menyetujui
cohort baru. Protokol yang dipakai tetap `qwen38-api-sqli-v3-pilot`, dengan 33
unit applicable pada kondisi A/B/C dan tiga slot C/Impossible yang dikecualikan
sesuai desain. Batasnya 960 request API dan enam jam, tanpa retry transport
otomatis maupun attempt pengganti otomatis.

## Hasil eksekusi

Eksekusi aktif berlangsung **437,8 detik atau sekitar 7 menit 18 detik**, lalu
berhenti karena read timeout API 90,153 detik saat analisis S1-B. Batas enam
jam adalah ceiling penghentian, bukan estimasi bahwa pengujian pasti berjalan
selama enam jam. Run ini berhenti lebih awal setelah kegagalan transport.

Sebanyak **25 request API** dimulai: 24 sukses dan satu `transport-error`.
Komposisinya 14 request generasi dan 11 request analisis. Tidak ada retry.
Ledger mencatat 183 HTTP request ke DVWA.

| Unit | Status | API | Request DVWA | Submisi probe logis |
| --- | --- | ---: | ---: | ---: |
| S1-A, RAG off | Excluded: `incomplete_candidate_budget` | 19 | 129 | 48 |
| S1-B, RAG on | Invalid: `api_transport_error` | 6 | 54 | Tidak diketahui |

S1-A menghasilkan dan mengeksekusi 8 kandidat valid dari target 10. Untuk slot
berikutnya, Qwen mengembalikan struktur kandidat duplikat tiga kali
(`duplicate_structure`); loop lalu berhenti dengan `generation_exhausted`.
Unit tidak memenuhi budget sehingga tidak eligible untuk metrik. S1-B berakhir
pada request analisis ke-25 dengan pesan `The read operation timed out`; request
itu tidak memiliki HTTP status. Kelima request API sebelumnya pada S1-B sukses.

Checkpoint akhir berisi 31 unit planned, nol running, nol retried, nol
completed, satu invalid, dan empat excluded. Empat excluded terdiri atas tiga
slot desain C/Impossible dan S1-A yang tidak memenuhi budget kandidat. Dengan
begitu, **belum ada unit eligible yang completed** dan tidak ada hasil PSR atau
FPR API yang dapat dihitung.

## Audit dan interpretasi

Audit rekonsiliasi lulus: urutan serta hash request konsisten, ledger cocok
dengan checkpoint, batas budget sesuai approval, tidak ada retry, 1.504 file
historis tidak berubah, dan 32 source runtime tetap cocok dengan baseline.
Audit tidak mengubah data eksperimen.

Ini merupakan pilot pengembangan yang berhenti, bukan validasi kestabilan API
atau evaluasi formal. Pemeriksaan `API_OK` singkat sebelumnya hanya membuktikan
akses dasar; hasil ini menunjukkan timeout masih dapat terjadi pada analisis
yang berjalan lebih lama. Angka enam jam adalah batas maksimum operasional,
bukan perkiraan durasi normal dan bukan jumlah waktu yang sudah dipakai.

## Tindak lanjut

Simpan cohort ini sebagai eksekusi parsial yang tidak eligible. Sebelum
pengumpulan baru, tinjau alasan generator hanya menghasilkan delapan kandidat
di S1-A dan timeout analisis pada S1-B. Eksekusi baru memerlukan ID, plan,
budget, dan keputusan terpisah; jangan melanjutkan atau menggabungkan cohort ini.

Bukti utama: [approval eksekusi](evidence/p3-recovery-002-execution-approval-2026-10-22.json),
[audit rekonsiliasi](evidence/p3-recovery-002-execution-audit-2026-10-22.json),
dan ledger/checkpoint di `results/raw/pilot/qwen38-api-r2-20261022/`.
