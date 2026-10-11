# Kelanjutan lokal: protokol pilot dan discovery ZAP, 11 Oktober 2026

## Hasil

Protokol pilot lokal tersedia sebagai konfigurasi dan dokumentasi. Discovery
ZAP kini memiliki delapan injection point terverifikasi, dua per level,
mencakup koordinat seluruh skenario S1-S12. Pasangan Qwen RAG-off/on S1 sudah
dibuat dari report ZAP Low terverifikasi dan dieksekusi satu replikasi pada
DVWA Low. Jalur discovery ke generator tidak lagi memakai katalog smoke pada
pasangan ini.

Ini kemajuan tahap protokol/discovery serta integrasi awal. Belum merupakan
loop adaptif lengkap, eksperimen tiga pengulangan, atau hasil final FPR/PSR.

## Perubahan implementasi

- `local_experiment_protocol.json`: matriks 99 run, seed berpasangan, budget,
  unit FPR/PSR, kriteria konfirmasi, dan gerbang eksperimen formal.
- `experiment_protocol.py`: pemeriksaan konfigurasi dan snapshot hash/versi.
  Status tetap pilot; researcher review korpus dan validator masih pending.
- Plan ZAP mengekspor HAR dengan `source: all` agar request spider dan form
  tidak bergantung pada alert. HAR dan log mentah diabaikan Git.
- `export_zap_inputs.py`: parser offline yang mencatat koordinat dan field
  terpilih, tanpa menyalin cookie, token, nilai input, atau body halaman.
- Normalizer 1.1.0 mempertahankan alert dan menambahkan inventaris HAR, cakupan,
  serta koordinat terverifikasi. Schema 1.0.0 lama tetap dapat dibaca.
- `--require-complete-inputs` membuat discovery gagal bila input belum lengkap.
  `--require-verified-discovery` menolak fallback katalog pada generator.
- Prompt generator v3 membuang scenario ID serta level keamanan. Label
  ground truth tetap hanya berada pada evaluator.
- Guard smoke memeriksa audit, hash prompt, isi kandidat, kesamaan context
  size/options, basis prompt, report discovery, dan isolasi RAG-off sebelum HTTP.

## Verifikasi discovery nyata

ZAP 2.17.0 dijalankan melalui image lokal yang sudah tersedia. Mode tetap
discovery pasif; tidak ada Active Scan. Session PHP dan state cookie keamanan
dipakai hanya di memori untuk mencocokkan bukti security.php dengan input.

| Level | Injection point verified | Skenario tercakup | Skenario hilang |
| --- | ---: | --- | --- |
| Low | 2 | S1, S2, S3 | Tidak ada |
| Medium | 2 | S4, S5, S6 | Tidak ada |
| High | 2 | S7, S8, S9 | Tidak ada |
| Impossible | 2 | S10, S11, S12 | Tidak ada |

Low/Impossible memakai GET, Medium memakai POST, dan High memakai helper POST
session-input.php serta cookie-input.php. Field user_token ditemukan pada kedua
form Impossible. Dua teknik blind memakai injection point yang sama.

Run Low pertama menyelesaikan ZAP tetapi guard normalisasi awal gagal karena
parser mengharapkan login.php?logout, sedangkan DVWA memakai logout.php.
Parser diperbaiki dan HAR dari run yang sama diproses ulang secara offline.
Tidak ada run yang dilabeli berhasil hanya berdasarkan exit code ZAP.
Helper High tidak memuat tautan Logout: verifikasi memakai halaman security
pada sesi yang sama, form helper, dan pemeriksaan bahwa respons bukan login.

Ekstraksi ulang memakai kode akhir identik dengan inventaris tersimpan untuk
keempat run. Schema report lulus dan gate generator menerima koordinat untuk
masing-masing S1-S12. Verified di sini berarti koordinat input terverifikasi,
bukan kerentanan terkonfirmasi atau seluruh aplikasi telah tercakup.

## Smoke S1 dengan input ZAP

Comparison ID: `s1-zap-inputs-pilot-20261011`.
Model tetap Qwen 2.5 7B Q4_K_M, seed 42, temperatur 0, context 4096, output
maksimum 768 token. RAG-on mengambil dua entri dari index terstruktur aktif.

| Pengamatan | RAG-off | RAG-on |
| --- | --- | --- |
| Payload | `1' OR '1'='1` | `1'` |
| Input/output token | 175 / 28 | 818 / 22 |
| SQL error baru | Tidak | Ya |
| Sinyal sistem error-based | false | true |
| Human validation | pending | pending |

Kedua baseline menampilkan record normal tanpa SQL error. Respons kandidat off
menampilkan record tanpa diagnostik SQL baru; kandidat tersebut tidak memenuhi
kriteria smoke error-based. Pengamatan ini tidak menentukan keberhasilan teknik
lain dari payload tersebut. Kandidat on menampilkan frasa tetap SQL syntax dan
mysqli_sql_exception, tanpa menyimpan data akun atau SQL di sekitarnya.

Satu pasangan ini belum membuktikan peningkatan FPR/PSR. Tidak ada penghitungan
metrik formal. Durasi generasi tidak dibandingkan karena load model berbeda.
Prompt v3 berbeda dari smoke terdahulu sehingga hasil tidak digabungkan.

## Bukti dan pemeriksaan

Ringkasan yang disanitasi ada di `evidence/local-discovery-2026-10-11.json`.
HAR, alert JSON, normalized report, audit model, serta log validation ada di
direktori hasil lokal yang diabaikan Git. Paket validator yang menyembunyikan
kondisi belum dibuat pada tahap ini.

32 unit test lulus, mencakup sanitasi, provenance ZAP, sumber non-ZAP yang
ditolak, pemisahan sesi/level, popup High, form tanpa alert, kompatibilitas
schema lama, gate discovery, bias label prompt, serta guard audit pasangan.
Parsing sintaks 25 file Python lulus. Empat report normalized lulus schema.

Container web dibuat ulang untuk discovery setiap level; volume database
tidak dihapus atau di-reset. Sesi smoke S1 disetel Low secara eksplisit setelah
discovery Impossible. Default container pada akhir discovery adalah Impossible.
Layanan tunnel lama yang sudah berjalan tidak digunakan untuk pengujian ini.
Tidak ada file sources/ yang diubah.

## Pekerjaan berikutnya

Bangun analisis respons Qwen dan regenerasi dengan budget tetap. Sinyal aturan
yang ada menjadi evidence untuk penalaran LLM; keputusan LLM harus dicatat
terpisah agar evaluator tetap dapat mengukur klaim sistem. Terapkan tiga
konfirmasi, matched timing control, dan penanganan invalid session sesuai
protokol, kemudian siapkan SecLists serta paket review manusia sebelum run
formal. Nilai formal harus tetap memakai keputusan manusia yang terdokumentasi.
