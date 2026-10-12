# Tugas persiapan eksperimen formal TA

Tanggal rancangan: 12 Oktober 2026.
Dasar: review progres 12 Oktober dan protokol local-sqli-v1-pilot.
Dokumen ini adalah backlog dan kriteria kesiapan, bukan bukti tugas telah selesai.

## Sasaran dan tiga titik kesiapan

Pengujian pengembangan sudah dapat dimulai pada DVWA lokal. Tidak perlu
menunggu semua fitur selesai untuk menguji satu perubahan.

1. **Siap test komponen:** satu perubahan memiliki kontrak input/output,
   konfigurasi lab valid, dan pemeriksaan terarah. Hasilnya data pengembangan.
2. **Siap pilot lengkap:** runner, kontrol respons, pembanding, serta pencatatan
   sudah terhubung. Pilot menilai kelayakan protokol dan masalah operasional.
3. **Siap eksperimen formal:** pilot selesai, prosedur evaluator/validator siap,
   versi dan protokol dibekukan, serta seluruh gerbang memiliki bukti.

Scope tetap DAST/black-box pada DVWA milik peneliti: Low, Medium, High,
Impossible; error-based, boolean blind, time blind. Tidak perlu menambah XSS,
SAST, target eksternal, atau memperbesar korpus tanpa kebutuhan dari pilot.

## T01. Finalisasi definisi evaluasi dan metodologi lokal

Status awal: protokol pilot tersedia, belum frozen.
Penanggung jawab: peneliti bersama pendamping teknis; identitas validator
dipersiapkan oleh peneliti.

- Catat perubahan lingkungan dari Colab/tunnel menjadi laptop lokal pada
  naskah metodologi baru, tanpa mengubah PDF sumber.
- Putuskan peran LangChain dan buktikan implementasinya jika dipertahankan.
- Tetapkan keberhasilan tiap teknik. Usulan pilot error-based adalah diagnostik
  SQL baru yang konsisten, bukan otomatis ekstraksi data.
- Selaraskan definisi FP berbasis ground truth dengan checklist validator.
  Simpan klaim sistem sebelum review; jangan menghilangkan FP dengan menyaring
  hanya temuan yang disetujui validator.
- Tetapkan cara memperoleh satu keputusan akhir per scenario-condition-run
  dari sejumlah kandidat. Definisikan penanganan bukti tidak cukup dan run
  tidak valid sebelum melihat hasil formal.
- Tetapkan budget kandidat valid, retry generasi/runtime, duplikasi, timeout,
  aturan konfirmasi, serta pelaporan run yang budgetnya tidak lengkap.
- Tentukan urutan kondisi sebelum formal, misalnya A/B bergantian antar
  replikasi, untuk mengendalikan efek urutan dan beban laptop.
- Review korpus bersama peneliti dan catat keputusan. Perubahan isi mengharuskan
  rebuild index sebelum freeze.

Keluaran: protokol pilot yang jelas, catatan keputusan peneliti, dan draft
metodologi lokal. Nilai budget/ambang masih boleh disesuaikan berdasarkan
kelayakan operasional pilot, kemudian dibekukan sebelum formal.

Selesai jika definisi dapat dipakai evaluator dan validator tanpa penafsiran
berbeda. Tidak perlu memilih setting berdasarkan kondisi mana yang unggul.

## T02. Implementasi analisis respons Qwen dan loop adaptif

Status 12 Oktober: analisis Qwen dan runner adaptif tersedia. Pilot model nyata
RAG-off dan RAG-on sudah berjalan berpasangan pada S1 Low, dua kandidat per
kondisi dengan tiga konfirmasi per kandidat. Keduanya masih incomplete pada
2/10 kandidat dan bukan eksperimen formal. Bukti tersanitasi:
[adaptive-s1-pilot-2026-10-12.json](evidence/adaptive-s1-pilot-2026-10-12.json).
Dependensi: kontrak evaluasi awal T01.

- Susun evidence respons yang disanitasi: baseline, diagnostik SQL, marker
  boolean, timing, dan status sesi. Buang data sensitif serta label evaluator.
- Buat output analisis terstruktur: klaim sistem, indikator yang dirujuk,
  alasan, dan feedback untuk langkah berikutnya.
- Hubungkan hasil eksekusi dengan Qwen; ketika gagal, feedback benar-benar
  masuk ke generasi kandidat berikutnya.
- Terapkan budget, deduplikasi, retry terbatas, dan pencatatan histori iterasi.
- Terapkan alur sama pada A/B. Jika retrieval dipakai saat analisis/feedback,
  tentukan kebijakannya dan pastikan RAG-off tidak membaca vector store.
- Simpan sinyal aturan, keputusan LLM, dan keputusan manusia sebagai field
  berbeda. Ground truth hanya dipakai evaluator.
- Jika kandidat berhasil, tetap penuhi budget PSR sesuai protokol; jangan
  mengakhiri run hanya karena sukses pertama.

Keluaran yang diusulkan: analyze_response.py dan adaptive_validation_loop.py,
atau modul setara yang terintegrasi dengan kode saat ini.

Kriteria implementasi T02 terpenuhi untuk S1 error-based: pilot nyata
membuktikan alur discovery -> generasi -> eksekusi -> analisis pada kedua mode.
Di RAG-off, kandidat gagal dianalisis negative dan evidence-nya masuk ke prompt
generasi kandidat berikutnya, yang kemudian memperoleh diagnostik baru pada
3/3 konfirmasi. Di RAG-on, kandidat awal positive tetap diikuti kandidat kedua
sesuai fixed budget. Semua 51 unit test lulus.

T02 belum memberi data metrik formal: tiap kondisi baru menjalankan 2 dari 10
kandidat dan summary berstatus incomplete. Review manusia masih pending.
Konfirmasi sesi dan level sudah diperiksa, tetapi reset database sebelum tiap
condition-run, pemulihan runtime, serta alur semua teknik/level masih menjadi
pekerjaan T03 dan T07.

## T03. Lengkapi konfirmasi dan kontrol eksekusi

Status 12 Oktober: kontrol runtime, baseline, dan kontrol timing sudah diterapkan
pada runner lokal; seluruh 59 unit test lulus. Smoke run nyata S1 Low tanpa reset
memverifikasi sesi, baseline, tiga konfirmasi, dan analisis Qwen. Satu kandidat
tereksekusi dari budget 10, sehingga run incomplete dan bukan hasil formal.
Ringkasan tersanitasi ada di
[evidence T03](evidence/t03-runtime-smoke-2026-10-12.json). Reset database
tersedia sebagai opsi eksplisit dan tidak dijalankan karena endpoint tersebut
menghapus isi database sampel. Pengujian reset menggunakan mock HTTP lokal
dalam unit test, bukan POST ke DVWA.
Dependensi: dapat dibangun setelah kontrak T01, lalu diintegrasikan dengan T02.

- Error: baseline normal dan tiga konfirmasi diagnostik baru.
- Boolean: pasangan true/false pada koordinat dan struktur request yang sama,
  dengan hasil konsisten pada tiga konfirmasi.
- Timing: pasangan delay/no-delay, tiga konfirmasi, eksekusi serial, serta
  ambang awal 1500 ms yang ditinjau melalui pilot.
- Pisahkan inferensi model dari pengukuran HTTP timing agar beban model tidak
  mengganggu pengukuran; catat kondisi beban laptop yang relevan.
- Login baru, verifikasi level, penanganan token Impossible/helper High,
  baseline, dan reset data melalui setup HTTP sebelum tiap condition-run.
- Perlakukan kehilangan sesi/koneksi sebagai masalah runtime. Request valid
  yang ditolak aplikasi tetap dapat dinilai sebagai kandidat gagal.
- Tentukan batas pemulihan. Jika state tidak dapat dijamin, invalidasi attempt
  dan ulangi condition-run dari reset, dengan log attempt lama tetap tersimpan.

Implementasi saat ini memverifikasi sesi dan level sebelum replikasi, memeriksa
baseline benign sebelum kandidat, dan memakai kontrol benign `id=1` yang cocok
untuk mengukur kandidat time-based. Login, jaringan, form, level, dan baseline
memiliki kode kegagalan runtime terstruktur. Kegagalan menghentikan attempt,
ditandai `attack_failure: false`, dan tidak memicu retry otomatis. Attempt
berikutnya perlu lingkungan diperbaiki, login baru, serta reset database.
Reset hanya dapat diminta dengan `--reset-before-run`; setelah reset, runner
menggunakan akun DVWA bawaan `admin` / `password`. Opsi ini menghapus data
database sampel.

Yang masih perlu: validasi kontrol reset secara end-to-end pada database DVWA
yang memang boleh diinisialisasi ulang, validasi High/Impossible dan token/helper,
serta integrasi pemulihan attempt pada orchestrator T05. Implementasi sekarang
siap untuk smoke pengembangan S1 Low, tetapi belum menjadi gate formal seluruh
matriks.

Keluaran: executor terintegrasi dan aturan invalid/retry eksplisit.

Selesai jika seluruh bentuk input dapat dijalankan, kontrol timing tercatat,
dan kegagalan sesi tidak diam-diam menjadi FN atau payload gagal.

## T04. Siapkan pembanding SecLists

Status awal: adapter provenance tersedia, belum ada run nyata.
Dependensi: definisi T01 dan executor T03.

- Tentukan versi/commit, file wordlist, hash, nomor baris, aturan seleksi, dan
  urutan sebelum hasil formal diketahui.
- Bentuk kandidat sesuai teknik; satu pasangan boolean dihitung satu kandidat.
  Dokumentasikan transformasi deterministik jika diperlukan agar request valid.
- Hindari seleksi hanya payload yang sebelumnya diketahui berhasil pada DVWA.
- Gunakan executor, jumlah konfirmasi, aturan runtime, dan budget kandidat sama
  dengan LLM. Catat jumlah request karena kandidat antar teknik tidak identik.
- Jalankan pilot SecLists nyata untuk tiga teknik, lalu level positif lainnya.

Keluaran: manifest SecLists, batch per skenario, dan log pilot.

Selesai jika S1-S9 dapat dijalankan dengan provenance dapat ditelusuri serta
budget sebanding. SecLists tidak masuk PSR Impossible pada rancangan ini.

## T05. Bangun orchestrator dan ledger eksperimen

Status awal: matriks konfigurasi tersedia; runner penuh belum ada.
Dependensi: T02-T04.

- Jalankan kondisi, skenario, seed, reset, discovery, dan executor dari satu
  konfigurasi. A/B menggunakan inventaris discovery sama per replikasi.
- Satu pengulangan menjalankan pipeline baru. Tiga konfirmasi satu kandidat
  berbeda dari tiga pengulangan pipeline.
- Gunakan ID run/attempt/kandidat unik, checkpoint dan resume, serta ledger
  planned/completed/invalid/retried/excluded.
- Resume tidak boleh menganggap state sesi/database lama masih valid. Catat
  titik reset dan keputusan pengulangan run.
- Pisahkan direktori/dataset pilot dan formal. Simpan hash artefak dan versi.
- Catat kandidat valid dieksekusi, kandidat gagal dibuat, duplikat, request,
  konfirmasi, dan kelengkapan budget.

Keluaran yang diusulkan: run_local_experiments.py dan ledger kelengkapan.

Selesai jika satu subset matriks berjalan otomatis dan gangguan/resume tidak
menimbulkan data ganda, state tidak jelas, atau record hilang.

## T06. Siapkan human validation dan agregasi metrik

Status awal: keputusan manusia masih pending; paket/evaluator final belum ada.
Dependensi: kontrak T01 dan log T02-T05.

- Tentukan validator yang memahami SQLi dan tidak terlibat pengembangan sistem.
- Buat paket dengan ID acak, koordinat, kandidat, baseline, bukti dan timing;
  sembunyikan kondisi RAG, sumber kandidat, dan label ground truth evaluator.
- Buat form keputusan, justifikasi, reproduktibilitas, dan aturan perbedaan
  pendapat. Mapping kondisi disimpan internal.
- Uji prosedur pada paket pilot sebelum mengumpulkan data formal.
- Bangun agregator dari ledger, klaim sistem tersimpan, ground truth evaluator,
  dan keputusan validator. FPR A/B; PSR utama B/C sesuai protokol pilot.
- Periksa kasus FP, TN, FN, kandidat gagal, run invalid, budget tidak lengkap,
  dan penyebut nol memakai fixture buatan dengan hasil perhitungan diketahui.
- Pastikan FPR dihitung per keputusan scenario-condition-replicate, sedangkan
  PSR per kandidat logis. Konfirmasi tidak menjadi tambahan kandidat.

Keluaran: paket review, template anotasi, identitas/prosedur validator, dan
aggregate_metrics.py atau fungsi setara.

Selesai jika paket pilot dapat direview tanpa mengetahui kondisi dan agregator
menghasilkan hitungan yang dapat diverifikasi. Seluruh anotasi data formal
baru diselesaikan setelah run formal, bukan syarat sebelum pengambilan data.

## T07. Pilot terpadu seluruh teknik dan level

Dependensi: T02-T06; penetapan protokol T01 ditinjau kembali sebelum freeze.

Urutan pengujian: S1 -> S2/S3 -> S4-S9 -> S10-S12. Jalankan A/B untuk seluruh
12 skenario dan C untuk sembilan skenario positif. Sebagai pilot cakupan awal,
satu pengulangan per kombinasi memberi 33 run, terpisah dari dataset formal.
Uji mekanisme replikasi/seed dan pemulihan secara terarah; tambah pilot hanya
jika masalah operasional atau perubahan kode memerlukannya.

- Gunakan model, retrieval dan DVWA nyata, dengan budget yang akan dipakai
  formal untuk memastikan laptop mampu menyelesaikannya.
- Catat durasi aktual agar estimasi waktu formal berdasarkan hasil pilot.
- Siapkan baseline deteksi SQLi ZAP tersendiri sebagai acuan tambahan proposal,
  dengan prosedur terpisah dari passive discovery dan kondisi A/B/C.
- Review kontrol timing, konfirmasi, input High/Impossible, evidence, budget,
  paket validator, dan ledger. Perbaiki masalah lalu ulangi bagian terdampak.

Selesai jika pipeline dan pencatatan berfungsi untuk semua kombinasi yang
direncanakan serta masalah operasional utama terselesaikan. Kandidat tidak
harus berhasil menyerang. Pada Impossible, deteksi positif tetap disimpan
untuk audit FP; jangan mengubah sistem hanya agar hasil pilot tampak bagus.

## T08. Freeze dan pemeriksaan kesiapan formal

Dependensi: T01-T07.

- Bekukan commit kode, dependency/runtime, digest model/embedding/image,
  prompt, korpus/index, top-k, sumber SecLists, dan protokol final.
- Pastikan prompt RAG masuk context tanpa truncation yang tidak tercatat.
- Selesaikan pesan startup interpreter .venv yang tercatat pada review atau
  dokumentasikan penyebab dan runtime bersih yang dipakai formal.
- Catat evidence lulus untuk setiap formal_gate. Mengubah status JSON menjadi
  frozen saja tidak membuktikan semua gate sudah terpenuhi.
- Pilih urutan run, penamaan output, ruang penyimpanan dan backup lokal;
  buat manifest formal serta dataset kosong yang terpisah dari pilot.
- Jalankan pemeriksaan akhir konfigurasi, kontrak schema, dan test yang relevan.

Selesai jika checklist berikut seluruhnya memiliki bukti:

- [ ] Definisi sukses, FP/TN, unit keputusan, invalid/retry dan budget final jelas.
- [ ] Metodologi laptop lokal serta peran LangChain terdokumentasi.
- [ ] Keputusan review korpus oleh peneliti dicatat.
- [ ] Analisis Qwen dan feedback adaptif berfungsi; A/B memiliki kontrol sama.
- [ ] Konfirmasi, timing control, login/level/token/helper dan reset teruji.
- [ ] SecLists versi/seleksi tetap dan executor sebanding tersedia.
- [ ] Orchestrator, resume, ledger dan evidence lengkap teruji.
- [ ] Pilot seluruh teknik/level selesai dan terpisah dari dataset formal.
- [ ] Baseline ZAP tambahan memiliki prosedur yang jelas sesuai naskah.
- [ ] Validator independen, paket blind dan prosedur anotasi siap.
- [ ] Agregator metrik teruji; prediksi sistem sebelum review dipertahankan.
- [ ] Versi/runtime/protokol dan manifest formal dibekukan.

## Matriks formal setelah seluruh gate terpenuhi

| Kondisi | Cakupan | Pengulangan | Run |
| --- | --- | ---: | ---: |
| A: Qwen RAG-off | S1-S12 | 3 | 36 |
| B: Qwen RAG-on | S1-S12 | 3 | 36 |
| C: SecLists | S1-S9 | 3 | 27 |
| Total | | | 99 |

Budget awal 10 kandidat per run berarti 990 slot kandidat yang direncanakan
jika angka itu dipertahankan. Ini bukan jumlah request HTTP: pasangan boolean,
kontrol timing, baseline, dan konfirmasi menambah request. Sembilan unit negatif
per kondisi A/B berasal dari DVWA yang sama, bukan aplikasi independen.

## Pelaporan yang dikerjakan setelah pengumpulan data

Anotasi formal, agregasi final, interpretasi FPR/PSR, skor CVSS temuan yang
dikonfirmasi, dan penulisan hasil/pembahasan memerlukan dataset formal.
Modul CVSS/laporan dapat disiapkan selama persiapan, tetapi skor final dan
naskah hasil tidak menjadi syarat memulai pengumpulan data. Keduanya tetap
wajib diselesaikan sebelum mengklaim keseluruhan sistem end-to-end sesuai
proposal selesai.

Mulai dari T01 untuk mengunci kontrak awal, lalu T02/T03 untuk mencapai pilot
adaptif S1. Setup lab, discovery dan index yang sudah terbukti tidak perlu
dibangun ulang; gunakan sebagai fondasi dan verifikasi saat runner diintegrasikan.
