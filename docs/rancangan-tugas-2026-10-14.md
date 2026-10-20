# Rancangan tugas lanjutan TA

Tanggal: 14 Oktober 2026, Asia/Jakarta.
Status: backlog kerja aktif. U00 selesai; U01 lulus gate implementasi,
sedangkan kinerja Qwen masih memiliki mismatch; U02 selesai pada subset enam
condition-run pilot; smoke wiring U03 lintas A/B selesai. Pilot terpadu U06 dan
gate berikutnya masih pending.
Dokumen ini bukan evidence implementasi atau hasil formal.
Dasar: review progres 14 Oktober, evidence pilot T03/T04/T05, dan protokol
aktif `local-sqli-v5-pilot`.
Untuk status aktif per 16 Oktober, gunakan [rencana penyelesaian](rencana-penyelesaian-2026-10-16.md).

## Sasaran

Menutup masalah operasional dan menyiapkan evaluasi yang dapat diaudit sebelum
eksperimen formal. T01 selesai pada kontrak metode. Persiapan teknis T06 sudah
tersedia, sedangkan anotasi formal, pilot terpadu U06/T07, dan freeze T08 belum
selesai.

Ruang lingkup tetap DAST/black-box pada DVWA Low, Medium, High, Impossible,
dengan SQLi error-based, boolean-based blind, dan time-based blind.
FPR membandingkan A/B, sedangkan PSR utama membandingkan B/C.

- A: Qwen RAG-off.
- B: Qwen RAG-on.
- C: SecLists, hanya skenario positif S1-S9.
- Retrieval B digunakan pada generasi/regenerasi; analisis A/B tidak memakai
  retrieval. A tidak mengakses vector store.
- Tiga konfirmasi satu kandidat berbeda dari tiga replikasi pipeline.
- Pilot dan formal menggunakan dataset terpisah; artefak lama dipertahankan.

## Daftar tugas dan dependensi

ID U digunakan untuk tugas lanjutan agar tidak mengubah identitas milestone T01-T08.
Status U00/U01 diperbarui setelah audit 14 Oktober; task table adalah status
kerja aktif, sedangkan rincian gate formal tetap mengikuti T01-T08.

| ID | Prioritas | Tugas | Milestone terkait | Dependensi |
| --- | --- | --- | --- | --- |
| U00 | Selesai | Selaraskan status dokumentasi dan daftar gate | T01/T08 | Review terbaru |
| U01 | Gate implementasi lulus: kontrak dan 145 tes; replay v8 4/6 valid dan validasi tertutup satu kali 11/18 valid, seluruh mismatch dicatat. | Laporkan keterbatasan model; jangan tuning pada set yang sudah dibuka | T02/T06 | Artefak pilot tersedia |
| U02 | Selesai pada subset pilot 6/6; pilot terpadu lintas matriks menunggu U06 | Stabilkan keragaman kandidat dan budget A/B | T02/T05 | Temuan U01 untuk jalur feedback |
| U03 | Implementasi dan smoke wiring A/B S2-S12 selesai; satu kandidat per smoke. Budget penuh lintas matriks menunggu U06 | Perluas loop adaptif ke seluruh teknik dan level | T02/T03/T05 | U01-U02 |
| U04 | Exporter/importer, form, dan prosedur tersedia; VAL-01 serta kualifikasi/independensi dikonfirmasi; 3 anotasi prosedural selesai dan 1 label awal success direvisi menjadi insufficient_evidence | Tinjau paket U06 dan anotasi data formal | T06 | Kontrak T01, artefak pilot, dan data eligible |
| U05 | Agregator FPR/PSR, ekspor, audit confusion class, dan fixture hasil diketahui selesai; belum ada metrik formal | Audit impor dan eligibility anotasi/run U06 | T06 | Format anotasi U04 dan data eligible |
| U06 | P1 | Jalankan pilot terpadu dan baseline ZAP aktif | T07 | U01-U05 selesai pada cakupan yang diperlukan |
| U07 | P1 | Freeze dan pemeriksaan kesiapan formal | T08 | U00-U06 dan evidence seluruh gate |

## U00. Selaraskan status dokumentasi

Langkah:

- Bedakan catatan historis, status implementasi saat ini, dan kesiapan formal.
- Tinjau bagian yang masih menyatakan adapter LangChain belum diimplementasikan,
  meskipun evidence integrasi S1 sudah tersedia.
- Jelaskan `implementation_readiness.local_langchain=pending`: apakah mengacu
  pada cakupan seluruh matriks atau status yang belum diperbarui.
- Kaitkan setiap gate dengan artefak bukti dan batas cakupannya. Catat jumlah
  tes bersama tanggal/verifikasi, bukan mengganti angka historis tanpa konteks.

Keluaran: ringkasan status aktif dan daftar gate beserta evidence/celah.
Selesai jika tidak ada klaim kesiapan yang bertentangan antara README, protokol,
dan review aktif. Evidence S1 tidak menutup gate seluruh matriks secara otomatis.

## U01. Audit klaim Qwen pada evidence diagnostik

Masalah awal: pilot `t02-s1-lc-r3-20261014` memiliki tujuh kandidat B dengan
evidence executor positif 3/3, tetapi semua klaim Qwen negatif. Penyebab belum
ditetapkan; jangan menganggap prompt sebagai satu-satunya penyebab.

Langkah:

1. Telusuri record dari respons tersimpan, ekstraksi diagnostik, input analisis,
   prompt, opsi model/schema decoding, output mentah, hingga normalizer/ledger.
2. Periksa apakah baseline/kandidat dan nomor trial benar, diagnostik mencapai
   model, konteks terpotong, atau output berubah saat normalisasi.
3. Bandingkan versi/hash prompt dan input aktual dengan pilot terdahulu yang
   menghasilkan klaim sesuai evidence. Gunakan replay tanpa probe DVWA baru.
4. Tetapkan fixture diagnostik 3/3, 0/3, mixed 1/3 dan 2/3, generic HTTP error,
   serta sesi/konfirmasi invalid sebelum menilai perubahan.
5. Perbaiki komponen yang terbukti bermasalah dan lakukan replay model lokal
   pada set fixture tetap. Catat semua hasil, termasuk ketidaksesuaian yang tersisa.

Keluaran yang direncanakan:

- `docs/audit-analisis-qwen-2026-10-14.md` atau laporan bertanggal pelaksanaan.
- Evidence replay tersanitasi, versi/hash input-prompt-output, dan perubahan
  kode/prompt bila diperlukan.
- Tes regresi pada transformasi evidence, normalisasi, dan policy yang terdampak.

Selesai jika jalur evidence terbukti utuh dan akar masalah atau keterbatasan model
terdokumentasi, perubahan terverifikasi, serta perbedaan klaim/evidence dapat
diaudit. Ketidaksempurnaan model dilaporkan; klaim Qwen tidak diganti otomatis
dengan sinyal executor. Hasil replay bukan FPR/PSR formal.

## U02. Stabilkan keragaman kandidat

Masalah awal: B pada `t05-s1-abc2-20261014` berhenti di empat dari sepuluh
kandidat setelah batas regenerasi duplikat habis.

Langkah:

- Audit histori kandidat, cara mendeteksi duplikasi, input feedback, konteks
  retrieval, dan instruksi regenerasi pada slot yang gagal.
- Terapkan aturan keragaman dan feedback yang sama pada A/B; perbedaan
  perlakuan tetap hanya konteks RAG pada generasi/regenerasi.
- Pertahankan budget sepuluh kandidat, batas retry per slot, dan exclusion
  incomplete budget selama diagnosis. Perubahan protokol harus dicatat terpisah.
- Jangan mengisi kandidat LLM yang kurang dengan payload SecLists/manual atau
  mengulang run excluded sampai diperoleh hasil yang diinginkan.
- Setelah perubahan dibekukan untuk pemeriksaan ini, jalankan subset S1 A/B
  pada seed 42/43/44, enam condition-run pilot yang ditentukan di awal.

Keluaran: perbaikan generator/feedback, tes duplikasi dan penghentian, serta
evidence budget/kandidat/duplikasi/retry/durasi untuk setiap run.
Kriteria target: enam run lengkap 10/10 kandidat logis menurut aturan duplikasi
yang ditetapkan, dengan tiga konfirmasi per kandidat dan histori utuh.
Jika incomplete berulang, catat gate belum terpenuhi dan evaluasi kelayakan
budget/model secara terbuka sebelum pilot terpadu. Jangan menghapus run gagal.
Keberhasilan serangan bukan kriteria penyelesaian tugas ini.

## U03. Perluas loop adaptif

Loop adaptif kini digunakan untuk kondisi A/B pada seluruh S1-S12. Smoke live
satu kandidat sudah memverifikasi wiring lintas teknik dan level; rincian
terbaru tercatat pada evidence U03. Pilot budget penuh tetap pekerjaan U06.

Langkah:

- Pisahkan controller adaptif umum dari struktur kandidat/probe tiap teknik.
- Dukung kandidat tunggal error, pasangan boolean sebagai satu kandidat, dan
  timing dengan matched control payload yang sama memakai `SLEEP(0)`.
- Hubungkan executor Medium select, High helper, serta token baru Impossible
  ke alur generasi, observasi, analisis, feedback, dan ledger.
- Pertahankan baseline, tiga konfirmasi tetap, serialisasi inferensi/probe,
  label evaluator di luar prompt, serta kebijakan abstention/invalid/excluded.
- Verifikasi secara bertahap S2/S3, S4-S9, lalu S10-S12 dengan unit pilot baru.

Keluaran: controller/adaptor lintas teknik, integrasi runner, kontrak yang
diselaraskan, tes perilaku penting, dan smoke evidence per bentuk input.
Selesai jika semua skenario A/B memakai alur adaptif yang sesuai dan tidak ada
kegagalan pipeline tersembunyi. Hasil negatif/abstention tetap sah dicatat,
termasuk klaim positif pada Impossible untuk audit FP.

## U04. Siapkan validasi independen

Langkah:

- Peneliti menetapkan validator yang memahami SQLi dan tidak terlibat pengembangan.
- Buat exporter paket review dengan ID acak, koordinat, kandidat, baseline,
  tiga konfirmasi, dan evidence tersanitasi.
- Sembunyikan kondisi A/B/C, sumber kandidat, label ground truth, dan klaim
  Qwen/sinyal verdict executor dari paket penilaian awal. Mapping disimpan internal;
  periksa apakah nama file/ID atau metadata membocorkan kondisi.
- Buat form keputusan, alasan, kecukupan bukti, prosedur klarifikasi, dan aturan
  penanganan perbedaan pendapat jika ada lebih dari satu validator.
- Uji ekspor-impor dan prosedur review pada paket pilot, termasuk mixed evidence
  dan kandidat yang ditolak target dalam sesi valid.

Keluaran: exporter, template/form anotasi, mapping internal, dan prosedur validator.
Selesai jika paket pilot dapat direview tanpa label kondisi, hasil anotasi dapat
ditautkan ke kandidat asal, serta identitas dan prosedur validator tercatat.
Anotasi seluruh data formal dilakukan sesudah pengumpulan data formal.

## U05. Bangun agregator FPR/PSR

Langkah:

- Implementasikan `dvwa/aggregate_metrics.py` atau modul setara yang membaca
  ledger, klaim sistem sebelum review, ground truth evaluator, dan anotasi manusia.
- FPR A/B memakai keputusan per scenario-condition-replicate. Validator tidak
  boleh menghapus klaim positif pada skenario negatif dari hitungan FP.
- PSR utama B/C memakai kandidat logis pada S1-S9. Pembilang mensyaratkan
  evidence 3/3 dan validasi independen; mixed evidence tetap dalam penyebut
  kandidat valid pada run lengkap. Pasangan boolean tetap satu kandidat.
- Hitung per replikasi/kelompok sesuai kontrak per-run averaging, lalu mean dan
  SD sampel `ddof=1`. Tulis unit dan penyebut tiap tabel agar tidak terjadi pooling
  konfirmasi atau voting lintas run.
- Tahan FPR utama bila unit negatif terencana belum seluruhnya evaluable/biner;
  tampilkan coverage dan alasan exclusion. Penyebut nol menghasilkan undefined.
- Uji fixture hasil diketahui untuk TP/FP/TN/FN, abstention, invalid, incomplete
  budget, mixed evidence, anotasi pending, dan tiga replikasi.

Keluaran: agregator, fixture dan tes perhitungan, keluaran JSON/CSV, serta
definisi kolom dan eligibility. Keluaran fixture/pilot diberi label scope yang jelas.
Selesai jika hasil manual fixture cocok dengan agregator, input belum tervalidasi
tidak menghasilkan PSR final, dan setiap angka dapat ditelusuri ke record sumber.

## U06. Pilot terpadu dan baseline ZAP aktif

Langkah:

- Jalankan satu replikasi pilot terpadu: A/B S1-S12 dan C S1-S9, total 33 run,
  budget sepuluh kandidat, tiga konfirmasi, reset per run, dan urutan protokol.
- Gunakan snapshot konsisten untuk seluruh pilot ini dan catat durasi, jumlah
  request, kelengkapan budget/analisis, serta excluded/invalid/abstention.
- Uji satu gangguan proses nyata yang ditentukan sebelumnya pada eksperimen
  terpisah: recovery mencatat attempt invalid, login/reset baru, dan provenance;
  resume selesai tetap no-op.
- Siapkan baseline deteksi SQLi aktif ZAP terpisah dari passive discovery dan
  kondisi A/B/C. Verifikasi autentikasi, level, form/injection point, payload policy,
  laporan, dan cakupan scan sebelum menafsirkan ketiadaan alert.
- Gunakan paket U04 dan agregator U05 untuk audit pilot. Perbaikan memerlukan
  snapshot/experiment ID baru; ulangi hanya bagian terdampak dengan alasan tercatat.

Keluaran: plan dan evidence 33 run, laporan cakupan baseline ZAP, bukti recovery,
contoh review pilot, serta estimasi waktu/penyimpanan berdasarkan pengukuran.
Selesai jika semua bentuk alur berjalan, masalah operasional utama ditutup,
kontrol dan pencatatan dapat diverifikasi, serta gate tersisa dijelaskan.
Payload tidak wajib berhasil dan model tidak wajib menghasilkan klaim positif.
Run incomplete berulang tetap masalah kesiapan budget, bukan hasil serangan negatif.

## U07. Freeze kesiapan formal

Langkah:

- Catat commit kode, dependency/runtime, digest model/embedding/image Docker,
  prompt, korpus/index, retrieval policy/top-k, SecLists, dan protokol.
- Periksa context/truncation, layanan lokal, ruang disk/backup, schema, serta
  tes yang relevan. Tutup atau dokumentasikan masalah interpreter yang pernah tercatat.
- Hubungkan seluruh gate dengan evidence cakupan yang sesuai; jangan hanya
  mengganti status konfigurasi menjadi frozen.
- Siapkan plan formal 99 run: A 36, B 36, C 27, seed 42/43/44. Jika budget
  sepuluh dipertahankan, ada 990 slot kandidat terencana, bukan 990 request HTTP.
- Buat dataset formal baru yang terpisah, kemudian lakukan pemeriksaan akhir.

Keluaran: manifest freeze, checklist gate, plan formal, dan jadwal berbasis durasi U06.
Selesai jika seluruh gate punya bukti, prosedur validator/agregator siap, dan
snapshot formal dapat direproduksi. Pengumpulan formal merupakan tahap berikutnya.

## Pembagian tanggung jawab dan urutan terdekat

Pendamping teknis menyiapkan audit, kode, tes, paket, dan evidence.
Peneliti menetapkan validator, mereview perubahan metode bila diperlukan, dan
mengawasi pemisahan data pilot/formal. Validator memberi penilaian independen.

Urutan sesi terdekat:

1. U00 ditutup dengan menyelaraskan status LangChain S1 di README/protokol.
2. U01 kontrak implementasi dan validasi tertutup satu kali selesai; pertahankan mismatch sebagai bukti kinerja Qwen.
3. U02 dilanjutkan dengan status evidence yang eksplisit dalam feedback; persiapkan U04 sejak awal.
4. Kerjakan U03 dan U05, lalu U06 dan U07 setelah dependensinya tersedia.

Tidak menetapkan tanggal selesai sebelum durasi inferensi/pilot diukur.
Replay U01 hanya memakai evidence tersimpan dan tidak mengirim probe ke DVWA.
Perubahan analisis dan feedback adalah implementasi pengembangan; protokol
formal tetap pilot.
Pelaporan temuan/CVSS, anotasi formal, dan Bab Hasil/Pembahasan dilanjutkan setelah
dataset formal tersedia. File referensi tersinkron pada `sources/` tetap read-only.

## Status pelaksanaan U02, U04, dan U05, 14 Oktober

Pilot diagnostik kedua memakai `u02-s1-ab-diversity-r2-20261014`, prompt
`sqli-adaptive-candidate-v4-technique-scoped`, serta kondisi A/B pada S1,
seed 42, satu replikasi. Run A lengkap 10/10 kandidat unik, 30 keputusan,
60 observasi payload, tiga konfirmasi per kandidat, dan keputusan sistem
positif. Run B menghasilkan nol kandidat valid dari sepuluh slot: seluruh
sepuluh upaya generasi ditolak karena payload masuk ke teknik timing, walaupun
skenario meminta error-based. Contoh output mentah yang tercatat adalah
`1' AND SLEEP(5)--`. Guard menghentikan payload tersebut sebelum probe, lalu
ledger mengecualikan B dengan `incomplete_candidate_budget`.

Perbaikan guard berhasil menahan teknik di luar cakupan sebelum eksekusi,
tetapi instruksi prompt dan batas retry belum membuat generasi B lengkap.
Pilot pertama U02 juga dikecualikan setelah kandidat timing lolos ke jalur
eksekusi sebelum guard diperketat; hasil itu tidak dipakai untuk metrik dan
tetap dipertahankan sebagai histori. Kedua percobaan U02 bersifat diagnostik,
bukan enam condition-run yang menjadi kriteria penyelesaian. Akar masalah yang
tersisa ada pada kepatuhan generasi saat retrieval aktif; perbaikan harus menjaga
kesetaraan perlakuan selain konteks retrieval dan ditetapkan pada snapshot baru.

Pada snapshot rancangan 14 Oktober, exporter paket blind dan importer anotasi
U04 sudah tersedia dan lolos pengujian offline. Paket uji dari artefak pilot
memuat 24 kandidat dengan ID acak dan mapping privat yang terpisah. Pembaruan
setelah snapshot: peneliti mengonfirmasi identitas, kualifikasi, dan
independensi `VAL-01`; tiga anotasi prosedural selesai. Satu label awal
`success` kemudian dikoreksi menjadi `insufficient_evidence` atas persetujuan
validator tanpa mengubah alasannya.
Anotasi formal U06 masih belum dilakukan. U05 memiliki agregator dan fixture
sintetis untuk PSR, FPR, abstention, mixed evidence, anotasi pending, duplikasi
run, dan orphan annotation. Data anotasi yang tersedia belum cukup untuk
menghasilkan metrik formal.

Suite lengkap memakai interpreter `.venv` proyek menghasilkan 128 tes lulus
pada 14 Oktober 2026 sebelum perbaikan U02 final. Python global tidak memiliki
dependensi `jsonschema`, jadi hasil pemanggilan dari interpreter global tidak
dianggap hasil verifikasi.

### Penutupan U02 pada subset pilot, 14 Oktober

Prompt v9 `sqli-adaptive-candidate-v9-expanded-retry-families` diuji dahulu
dengan konteks retrieval B yang disimpan dari pilot sebelumnya. Preflight
generator-only menghasilkan 10/10 nilai unik yang lolos guard kebijakan; dua
nilai duplikat diatasi dalam batas retry. Tidak ada request ke DVWA pada tahap
ini. Audit lengkap tersimpan di
`results/raw/u02-generation-preflight-v9-20261014/generation-only-audit.json`.

Enam condition-run dijalankan pada snapshot baru
`u02-s1-ab-diversity-v9b-20261014` untuk A/B, S1, seed 42/43/44. Seluruh enam
run selesai, masing-masing dengan 10 kandidat unik, tiga konfirmasi per
kandidat, nol generation failure, reset database terverifikasi, dan 158 HTTP
request tercatat per run. Semua payload lolos guard error-based syntax-only
sebelum eksekusi. Retry generasi yang terjadi hanya menangani nilai duplikat;
tidak ada attempt invalid atau run excluded. Durasi attempt A adalah 122.1,
115.0, dan 123.3 detik; B adalah 143.2, 142.0, dan 144.5 detik. Ledger dan
hash artifact telah diperiksa ulang lewat loader dataset.

Seluruh keputusan sistem pada S1 adalah positive, dengan jumlah kandidat
3/3 positif per run sebesar 3, 3, 3, 8, 3, dan 2. Angka pilot ini hanya
dicatat sebagai evidence U02, bukan FPR/PSR formal dan belum divalidasi manusia.
Plan pertama `u02-s1-ab-diversity-v9-20261014` tidak memiliki mapping discovery
untuk replikasi 2/3; runner berhenti sebelum attempt/probe pertama. Kesalahan
plan dipertahankan, lalu pelaksanaan dilakukan dengan plan baru lengkap
`u02-s1-ab-diversity-v9b-20261014`.

Suite lengkap pada interpreter `.venv` proyek menghasilkan **134 tes lulus**
setelah perubahan U02 pada 14 Oktober 2026. `git diff --check` lulus; Git hanya
melaporkan peringatan normal konversi akhir baris LF/CRLF pada beberapa file.

## Rujukan lokal

- [Review progres](review-progress-2026-10-14.md).
- [Protokol evaluasi](protokol-evaluasi-lokal.md).
- [Kontrak analisis Qwen](qwen-response-analysis-contract.md).
- [Kontrol executor dan SecLists](t03-t04-controls-2026-10-14.md).
- [Pilot A/B LangChain](evidence/t05-ab-s1-langchain-live-pilot-2026-10-14.json).
- [Pilot lifecycle A/B/C](evidence/t05-abc-s1-lifecycle-live-2026-10-14.json).
- [Rancangan persiapan sebelumnya](persiapan-eksperimen-formal-2026-10-12.md).

### U03: implementasi lintas teknik dan level, 14 Oktober

Loop adaptif kini menerima kandidat tunggal error/time dan pasangan boolean
sebagai satu kandidat, memvalidasi bentuk kandidat terhadap `probe_kind`,
mengobservasi baseline serta tiga konfirmasi tetap, mengirim evidence ke
analisis Qwen, dan mempertahankan feedback pada ledger. Adapter runner mengubah
hasil kembali ke record payload, decision, candidate evidence, serta batch
yang sama dengan jalur eksperimen. Pemeriksaan sinyal time-based sekarang
mencocokkan status, marker respons, diagnostik, dan delay terhadap kontrol
`SLEEP(0)`.

Smoke lokal terbatas mencakup S2-S12 pada kondisi A/RAG-off dan S2 pada
kondisi B/RAG-on. Setiap smoke hanya memakai satu kandidat dari budget sepuluh
dan tiga konfirmasi. Sepuluh dari dua belas hasil asli melewati analisis Qwen.
Artifact S5 dan S8 menyimpan `analysis_error` dari parser lama. Replay offline
atas teks mentah Qwen yang persis sama kini menghasilkan record completed
setelah ID berulang dihapus dari daftar terstruktur dan warning
`duplicate_evidence_refs_removed` ditambahkan. Klaim model dan teks mentah tetap
tersedia untuk audit. S5 tetap memiliki warning `model_claim_evidence_mismatch`;
analisis baru tidak mengubah evidence executor.
Adapter runner berhasil mengubah hasil S2/S3/S4/S10 serta S2-B menjadi record
payload, decision, dan candidate evidence. Ringkasan hash ada di
[evidence U03](evidence/u03-adaptive-shape-smoke-2026-10-14.json), sedangkan
artefak rinci berada di `results/raw/u03-adaptive-smoke-20261014/`.

U03 memenuhi implementasi dan smoke wiring lintas skenario, belum memenuhi
pilot budget sepuluh kandidat untuk seluruh matriks. Replay Qwen segar pada
evidence yang sama memberi variasi klaim, sehingga hasil pengembangan tersebut
tidak membuktikan akurasi model. Kesiapan formal tetap pending; U06 masih
memerlukan pilot terpadu setelah analisis Qwen stabil.

### Smoke tambahan kondisi B, 14 Oktober

Setelah layanan lokal tersedia, kondisi B/RAG-on dijalankan satu kali pada
S3-S12 memakai report ZAP terverifikasi sesuai level. Setiap run memakai satu
kandidat dari budget sepuluh, tiga konfirmasi, dan reset database sampel DVWA
sebelum run. Kesepuluh run runtime-valid dan analisis Qwen selesai. Evidence
executor menunjukkan empat kandidat positif dan enam negatif; klaim Qwen cocok
secara biner pada lima run, inconclusive pada tiga kontrol negatif, serta
positif pada dua kontrol Impossible S11/S12. Ini observasi smoke, bukan label
ground truth manusia atau FPR/PSR. Ringkasan hash dan batas interpretasi ada di
[evidence smoke tambahan](evidence/u03-adaptive-cross-condition-smoke-2026-10-14.json).

Dengan smoke A pada S2-S12, smoke B pada S2-S12, dan pilot budget penuh S1 pada
U02, wiring adaptif kini sudah diperiksa di seluruh skenario dan kondisi A/B.
Matriks budget penuh sepuluh kandidat dan tiga replikasi masih menjadi bagian
pilot terpadu U06.
