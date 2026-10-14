# Keputusan akhir T01: urutan kondisi formal

Tanggal: 14 Oktober 2026.
Dasar otorisasi: peneliti meminta melanjutkan penetapan urutan kondisi dan
menutup sisa T01. Pola berikut ditetapkan sebelum eksperimen formal.
Protokol aktif: local-sqli-v5-pilot, status pilot.
Status T01: keputusan evaluasi dan metodologi selesai; freeze tetap T08.

## Urutan yang ditetapkan

A adalah Qwen RAG-off, B adalah Qwen RAG-on, dan C adalah SecLists.
Satu replikasi menjadi satu blok. Urutan blok adalah replikasi 1, 2, kemudian
3; seed masing-masing 42, 43, dan 44. Dalam setiap blok, skenario mengikuti
urutan numerik S1 sampai S12.

| Replikasi | Seed | Nomor skenario ganjil | Nomor skenario genap |
| --- | ---: | --- | --- |
| 1 | 42 | A, B, C | C, B, A |
| 2 | 43 | B, C, A | A, C, B |
| 3 | 44 | C, A, B | B, A, C |

Skenario ganjil adalah S1/S3/S5/S7/S9/S11. Skenario genap adalah
S2/S4/S6/S8/S10/S12. Identitas ini berasal dari katalog evaluator, tidak
diteruskan ke prompt model dan tidak dipilih berdasarkan hasil pilot.

Pada S1-S9, tiap kondisi memperoleh posisi pertama, kedua dan ketiga tepat
satu kali dalam tiga replikasi skenario tersebut. A/B tetap memakai discovery
yang sama pada replikasi yang sama, meskipun C kadang berada di antara A/B.
Setiap condition-run memiliki reset database dan login baru; sesi tidak dibagi.

Pada S10-S12, C tidak dijalankan. Slot C tetap dicatat sebagai excluded di
ledger, lalu dikeluarkan dari urutan eksekusi:

| Skenario Impossible | Replikasi 1 | Replikasi 2 | Replikasi 3 |
| --- | --- | --- | --- |
| S10 | B, A | A, B | B, A |
| S11 | A, B | B, A | A, B |
| S12 | B, A | A, B | B, A |

Matriks tetap 99 run: A=36, B=36, C=27. Tiap blok replikasi berisi 33 run.
Ada 36 pasangan A/B; 18 A-dulu dan 18 B-dulu. Pada sembilan pasangan negatif
Impossible, pembagiannya A-dulu=4 dan B-dulu=5. Jumlah pasangan negatif
ganjil tidak memungkinkan pembagian tepat sama.

## Alasan pemilihan dan batas interpretasi

Pola rotasi dan pembalikan dipakai untuk menyebarkan posisi kondisi, menjaga
jadwal dapat direproduksi, serta mencegah seluruh A selalu dijalankan sebelum
B. Prinsip penggunaan blok/posisi untuk nuisance factors dibahas dalam
[NIST/SEMATECH tentang Latin square](https://itl.nist.gov/div898/handbook/pri/section3/pri3321.htm).

Jadwal ini adalah keputusan operasional penelitian dengan keseimbangan posisi,
bukan penerapan seluruh model statistik Latin square atau pembuktian bahwa
carryover, thermal throttling dan perubahan beban laptop telah hilang.
Tidak ada klaim randomisasi: urutan deterministik dicatat apa adanya.
Model/cache, load laptop dan durasi perlu dicatat pada pilot T07. Inferensi
tetap tidak overlap dengan probe HTTP dan kondisi menggunakan kontrol yang sama.

Perubahan jadwal setelah melihat hasil formal tidak dibenarkan untuk memilih
hasil yang lebih baik. Jika pilot menemukan kendala operasional yang memerlukan
perubahan, buat keputusan/protokol versi baru sebelum freeze/pengambilan data.

## Subset, resume dan pemulihan

Daftar condition_ids/scenario_ids/replicates pada plan merupakan selector,
bukan override urutan. Subset menyaring jadwal kanonik, tanpa re-rotasi dan
tanpa menggunakan urutan array input sebagai urutan eksekusi.
Jika subset hanya A/B, urutan keduanya mengikuti proyeksi pola tabel di atas.

Ledger menyimpan policy ID, posisi kondisi pada pola nominal tiga kondisi,
nomor slot subset, serta nomor eksekusi subset. planned_slot_index dapat
mencakup slot excluded; planned_execution_index bernilai null untuk slot itu.
Pada plan lengkap ada 108 slot ledger, yang terdiri dari 99 run terencana
dan sembilan slot C Impossible excluded. Ini tidak menambah run penelitian.

Resume mempertahankan jadwal awal. Run completed/excluded dilewati; attempt
invalid diulang pada slot awalnya setelah perbaikan lingkungan, login baru
dan reset sesuai protokol. Setelah itu runner meneruskan slot berikutnya.
Tidak ada shuffle, pergantian seed, atau penjadwalan ulang berdasarkan hasil
positive/negative/inconclusive. Run inconclusive bukan alasan mengulang unit.

Penjagaan resume memeriksa hash plan/protokol/kode/schema serta kecocokan
event perencanaan dengan rotasi. Eksperimen v1-v4 tidak dilanjutkan dengan
kode v5; gunakan ID eksperimen baru dan pertahankan artefak historis.

## Implementasi dan bukti yang diperlukan

- execution_order_policy.py menjadi sumber urutan untuk experiment_matrix
  dan planned_units, sehingga snapshot dan runner menghasilkan jadwal sama.
- Pemeriksa protokol menolak perubahan urutan, kebijakan subset atau resume
  yang tidak sesuai dengan keputusan ini.
- Runner mengeksekusi unit berdasarkan planned_slot_index dan memeriksa
  event perencanaan saat resume. Skema ledger mencatat metadata urutan.
- Tes memeriksa jumlah/seed/posisi pada seluruh matriks, C Impossible,
  selector dengan urutan terbalik, eksekusi subset dengan executor tiruan,
  resume no-op, recovery parsial dan perubahan metadata yang tidak sah.

Verifikasi offline bukan pilot DVWA/model nyata. Tidak dilakukan reset,
inferensi, scan, atau request probe pada penutupan T01 ini.

Hasil akhir: **104 test lulus**, 43 file Python lulus parsing, 11 definisi
schema valid dan pemeriksa protokol menerima v5 dengan 99 run terencana.
Jadwal penuh, hitungan keseimbangan, serta hash implementasi tersimpan pada
[evidence penutupan T01](evidence/t01-order-and-closure-2026-10-14.json).

## Penutupan T01

| Keputusan T01 | Status | Bukti |
| --- | --- | --- |
| Indikator tiap teknik dan konfirmasi kandidat | Selesai | protokol-evaluasi-lokal.md dan keputusan-konfirmasi-kandidat-2026-10-14.md |
| FP/TN, unit FPR/PSR, tiga replikasi, mean/SD | Selesai | keputusan-agregasi-per-run-2026-10-12.md dan protokol aktif |
| Mixed evidence, abstention dan keputusan akhir run | Selesai | keputusan-run-inconclusive-2026-10-14.md |
| Budget, deduplikasi, retry, runtime invalid | Selesai pada kontrak | konfigurasi v5; implementasi dan perluasan runtime tetap diuji pada T02/T03/T05/T07 |
| Metodologi laptop dan peran LangChain | Selesai pada keputusan | keputusan-metodologi-lokal-langchain-2026-10-14.md dan narasi Bab 3 |
| Keputusan review korpus peneliti | Selesai | evidence/review-peneliti-2026-10-12.md |
| Urutan kondisi formal, subset dan resume | Selesai | keputusan ini dan policy urutan bersama |

**T01 selesai pada tingkat kontrak evaluasi dan penetapan metodologi.** Ini
tidak mengubah status protokol menjadi frozen, tidak menyatakan validator
independen siap, dan tidak menyatakan pipeline LangChain/pilot seluruh matriks
selesai. Implementasi T02/T03/T05, persiapan validator/agregator T06, pilot T07
dan freeze T08 tetap memiliki gerbang sendiri.
