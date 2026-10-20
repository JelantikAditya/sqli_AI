# Penilaian kelayakan Qwen untuk U01

Tanggal: 14 Oktober 2026.
Status: evaluasi pengembangan, bukan hasil formal.

## Bukti yang tersedia

Proposal menetapkan Qwen 2.5 7B sebagai model yang digunakan (halaman 8),
membatasi penelitian pada DAST/black-box, DVWA, serta error-based,
boolean-based blind, dan time-based blind (halaman 8-9). Evaluasi utama adalah
FPR dan PSR (halaman 22-23). Proposal juga menetapkan penilaian temuan oleh
validator independen yang memahami SQLi (halaman 34-35).

Pada fixture pengembangan U01 yang sama, inferensi segar menghasilkan:

| Versi | Cocok keseluruhan | Cocok dari input valid | Catatan |
| --- | ---: | ---: | --- |
| v6 | 2/7 | 1/6 | Referensi pembanding untuk klaim positif belum lengkap. |
| v7 | 3/7 | 2/6 | Sitasi positif 3/3 dan HTTP 500 generik membaik. |
| v8 | 5/7 | 4/6 | Mixed 1/3 dan input dua trial membaik; 0/3 dan mixed 2/3 masih salah. |

Semua replay memakai tujuh fixture pengembangan yang sama, tanpa request ke
DVWA. Angka ini bukan FPR, PSR, atau estimasi akurasi populasi. v8 menunjukkan
model masih dapat melewatkan diagnostik pada asesmen trial dan salah
menggabungkan asesmen yang sebenarnya sudah benar.

Setelah prompt v8 dibekukan, validasi tertutup sintetis satu kali pada tiga
teknik cocok 14/21 kasus keseluruhan dan 11/18 kasus runtime-valid. Per teknik,
hasil valid adalah 4/6 error-based, 4/6 boolean-based, dan 3/6 time-based.
Semua kasus positive 3/3 dan incomplete dua trial cocok. Tiga runtime-invalid
benar dihentikan. Pada time-based, model memberi positive pada 0/3, mixed 1/3,
dan kontrol dengan selisih 90 ms, meski ambang yang diminta 1500 ms.

## Penilaian

Qwen 2.5 7B tetap sesuai dengan batasan model dalam proposal. Hasil 11/18 pada
validasi sintetis memperlihatkan bahwa model belum konsisten, terutama pada
kasus negatif lengkap dan time-based. Bukti ini tidak cukup untuk menyimpulkan
model harus diganti atau mengestimasi performa populasi. Prompt v8 dibekukan
sebagai konfigurasi yang akan dievaluasi; kinerja yang lemah harus tetap
dilaporkan. Pilot/formal tetap menunggu dependensi metodologi dan validator
independen.

Kontrak output, parser, warning semantik, dan suite unit lulus. Kesalahan yang
tersisa pada v8 berada di klaim/asemen model dan tertangkap oleh audit. Dengan
mempertahankan klaim Qwen serta warning, kesalahan tersebut dapat diamati dalam
evaluasi sesuai tujuan proposal, alih-alih disamarkan menjadi keluaran validator.

## Perubahan gate yang disetujui

Peneliti menyetujui pemisahan gate implementasi dari kinerja model. Syarat
internal “semua tujuh fixture harus cocok sebelum pilot” ditetapkan dalam
rencana perbaikan setelah hasil fixture yang sama diperiksa. Proposal tidak
mensyaratkan akurasi 7/7 sebelum eksperimen. Terus mengubah prompt hingga
fixture lama cocok dapat membuat prompt terlalu sesuai dan menyaring kegagalan
model yang justru perlu diukur oleh FPR/PSR. Gate kini dibagi menjadi:

1. **Gate implementasi:** schema dan kontrak output valid, klaim model tidak
   diubah oleh parser, referensi tidak dikenal ditandai, serta tes semantik dan
   integritas lulus.
2. **Gate kinerja model:** semua hasil replay pengembangan tetap dilaporkan,
   tetapi kecocokan 7/7 bukan prasyarat untuk mengukur kinerja model. Prompt
   v8 dibekukan sebelum set validasi tertutup atau pilot berikutnya. Hasil
   formal tetap menunggu protokol, cakupan eksperimen, dan validator independen
   sesuai proposal.

Pemisahan ini tidak mengubah definisi FPR/PSR atau klaim model. Validasi
tertutup satu kali telah dijalankan pada prompt v8 yang dibekukan. Hasilnya
tidak digunakan untuk tuning.
