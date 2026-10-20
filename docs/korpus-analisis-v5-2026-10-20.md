# Draft korpus analisis respons v5

Tanggal: 20 Oktober 2026. Status: draft siap direview peneliti. Penyusunan dan
pemeriksaan mekanis selesai; penelitian belum mempunyai hasil inferensi atau
retrieval v5. Dokumen ini melanjutkan rekomendasi
[review kurasi v4](review-rag-analisis-2026-10-19.md).

## Hasil yang tersedia

- [Korpus JSON](../knowledge/analysis-v5/corpus.json): tujuh chunk, 35 field
  substantif dan 38 pernyataan. Bahasanya Inggris, mengikuti prompt analisis
  yang sudah digunakan proyek.
- [Source lock](../knowledge/analysis-v5/sources.lock.json): empat dokumen dan
  sembilan rentang rujukan dengan hash snapshot serta koordinat lokal.
- [Schema khusus v5](../schemas/analysis-knowledge-v5.schema.json) dan
  [checker](../development/validate_analysis_corpus_v5.py): memeriksa struktur,
  rujukan, kontrak proyek dan preservasi artefak.
- [Audit akhir](../results/processed/analysis-corpus-v5-20261020/audit.final.json)
  serta [form review peneliti](../results/processed/analysis-corpus-v5-20261020/researcher-review.final.template.json).
  Form ini belum diisi dan bukan receipt persetujuan.

## Peta tujuh topik

| ID chunk, awalan analysis-v5- | Topik | Teknik yang berlaku | Dasar utama |
| --- | --- | --- | --- |
| sql-diagnostics | Diagnostik database versus error aplikasi | Error-based | WSTG Detection; Academy Error-based |
| baseline-comparison | Diagnostik baru terhadap baseline | Error-based | WSTG satu variabel; adaptasi kontrak error proyek |
| boolean-direction | Arah pasangan true dan false | Boolean-based blind | Academy Conditional responses; lab marker |
| marker-stability | Marker dan konten halaman dinamis | Boolean-based blind | WSTG Boolean exploitation |
| timing-control | Kandidat dan matched no-delay control | Time-based blind | Academy Time delays; adaptasi kontrak timing proyek |
| timing-confounders | Signal, jitter dan server noise | Time-based blind | PortSwigger Research bagian timing noise |
| conclusion-scope | Batas kesimpulan kandidat dan target | Semua tiga teknik | Academy definisi blind; kontrak kandidat proyek |

Setiap chunk mempunyai concept, evidence_to_compare, supporting_conditions,
confounders dan conclusion_limits. Baseline benign pada topik kedua berlaku
untuk diagnostik error; pembanding boolean tetap true/false dan pembanding
timing tetap candidate/no_delay_control. Ini mencegah perluasan aturan baseline
ke pembanding yang tidak sesuai teknik.

## Sumber dan peran masing-masing

1. **OWASP WSTG v4.2, Testing for SQL Injection.** Snapshot Markdown lama pada
   commit dd33419e10edb22b78d89325a6c2aad9f184e3a2 dipakai ulang secara baca saja.
   Rujukan terpilih adalah Detection Techniques dan Boolean Exploitation.
   [Sumber commit](https://github.com/OWASP/wstg/blob/dd33419e10edb22b78d89325a6c2aad9f184e3a2/document/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05-Testing_for_SQL_Injection.md).
2. **PortSwigger Academy, Blind SQL injection.** Dipilih bagian definisi blind,
   conditional responses, error-based dan time delays.
   [Halaman sumber](https://portswigger.net/web-security/sql-injection/blind).
3. **PortSwigger Academy, Conditional responses lab.** Dipilih deskripsi
   pemetaan marker dan pemeriksaan dua kondisi, tanpa memasukkan jawaban lab
   atau prosedur ekstraksi ke teks korpus.
   [Halaman sumber](https://portswigger.net/web-security/sql-injection/blind/lab-conditional-responses).
4. **PortSwigger Research, Listen to the whispers.** Dipilih Noise vs signal
   dan penjelasan server noise. Prosedur HTTP/2, amplifikasi beban dan teknik
   serangan di luar SQLi tidak masuk korpus.
   [Halaman sumber](https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work).

Halaman PortSwigger dicapture pada 20 Oktober 2026 sekitar 09:44 WIB. Identitas
versinya adalah snapshot bertanggal dengan hash HTML dan teks normalisasi,
bukan commit upstream. Nomor baris pada lock mengacu pada snapshot lokal,
sehingga tidak boleh disamakan dengan nomor baris situs yang sedang tampil.
Aturan normalisasi tersedia pada PageText dalam prepare_analysis_sources_v5.py.

PayloadsAllTheThings tetap tersedia pada korpus generasi terdahulu. Draft
analisis ini memprioritaskan materi interpretasi respons OWASP/PortSwigger.

## Provenance dan perubahan terhadap v4

Ada **14 pernyataan source_paraphrase** dan **24 researcher_adaptation**.
Istilah researcher_adaptation menandai usulan editorial Codex yang masih harus
direview peneliti, bukan klaim bahwa peneliti sudah menulis atau menyetujuinya.

- Setiap parafrasa mempunyai source_reference_ids menuju rentang sumber
  spesifik. Tidak ada pointer mitigasi yang diwariskan ke field analisis.
- Setiap adaptasi mempunyai adaptation_basis menuju kontrak proyek atau
  research-design. Field itu tidak diklaim sebagai persyaratan upstream.
- Kalimat tentang kegagalan indikator kandidat dipisahkan secara eksplisit
  dari kesimpulan keamanan target. Pernyataan ini menyelesaikan scope pada
  draft baru; hasil v4 tidak diinterpretasikan ulang.
- Pengetahuan umum tidak menetapkan angka ambang, jumlah trial, atau enum
  keluaran. Ketentuan itu ditaruh dalam metadata prompt_contract.
- Draft tidak memuat contoh sintetis. Penandanya dicadangkan untuk versi
  eksperimen lanjutan agar tambahan manfaat contoh bisa diuji terpisah.

Bagian prompt_contract **bukan bagian teks yang akan diretrieve**. Isinya
mendokumentasikan kontrak wajib di prompt kedua kondisi: validitas runtime
dan baseline, status HTTP dan pemetaan marker, matched control, delta tanpa
pembulatan sebelum perbandingan, ambang 1500 ms, identitas trial 1/2/3, serta
pemetaan 3/3, 0/3, mixed dan incomplete. Hash file dan locator fungsi/JSON
dicatat agar asal setiap aturan dapat diperiksa.

Belum ada renderer request v5. Saat implementasi berikutnya dibuat, hanya
field pengetahuan yang masuk reference_context; metadata review, kontrak,
label evaluator dan hasil eksperimen tidak menjadi teks retrieval.

## Pemeriksaan isi dan batas pemeriksaan

Review editorial Codex membaca rentang sumber dan mencocokkannya dengan 14
parafrasa, memisahkan 24 adaptasi, serta memeriksa scope tujuh topik. Review
ini dilakukan setelah hasil v4 diketahui, sehingga bukan review independen,
review blind atau penilaian relevansi retrieval yang mempunyai gold label.

Checker akhir memastikan:

- Tujuh topik unik dan lima field substantif pada setiap chunk.
- Seluruh sembilan rentang sumber dapat ditemukan dan hash-nya cocok.
- Semua snapshot dan file kontrak cocok dengan hash serta locator-nya.
- Status review tetap pending pada korpus dan setiap pernyataan.
- Semua **1.053 file** pada baseline awal tetap sama, termasuk **959 file**
  inventory formal. Enam file indeks aktif diperiksa sebagai byte tanpa
  membuka Chroma; perbandingannya memakai keadaan awal tugas ini.

Pemeriksaan mekanis membuktikan keterlacakan, bukan kebenaran semantik setiap
kalimat atau manfaat retrieval. Reviewer tetap perlu menilai kecukupan sumber
dan apakah batas klaimnya benar. Tidak ada embedding, inferensi model,
request DVWA, perubahan metrik formal atau integrasi ke runner.

Audit awal audit.json tersimpan sebagai riwayat penyusunan. Pemeriksaan
editorial berikutnya memperbaiki label locator fungsi menjadi build_messages
dan menambahkan resolusi AST pada checker. **Acuan draft saat ini adalah
audit.final.json dan researcher-review.final.template.json**, yang mengikat
hash korpus sesudah koreksi. Form awal tidak dipakai untuk review draft kini.

## Cara review dan pekerjaan berikutnya

1. Buka corpus.json dan periksa teks tujuh chunk. Gunakan source_reference_ids
   untuk menemukan section, snapshot dan rentang pada sources.lock.json.
2. Nilai dukungan setiap parafrasa, kecukupan setiap adaptasi, dan batas klaim.
   Form akhir menyediakan satu baris per pernyataan untuk komentar reviewer.
3. Catat nama reviewer, tanggal, keputusan dan hash yang direview. Form yang
   masih pending tidak memberikan persetujuan pilot atau penggunaan formal.
4. Revisi draft bila diperlukan, lalu buat rekaman audit/review baru yang
   mengikat versi tersebut. Persetujuan korpus lama tidak otomatis berlaku.
5. Sesudah isi layak, siapkan renderer dan penilaian relevansi retrieval sebelum
   pilot model. Kebijakan query, jumlah chunk, panjang konteks dan urutan
   kondisi ditetapkan sebelum hasil baru dilihat.

Untuk evaluasi berikutnya, perbandingan utama memakai prompt/model/input yang
sama pada retrieval off dan retrieval on. Perbandingan tambahan dapat menguji
referensi umum versus referensi dengan contoh sintetis. Perubahan struktur
chunk dan sumber pada v5 adalah satu paket pengembangan; peningkatan nantinya
tidak boleh diatribusikan hanya kepada PortSwigger tanpa perbandingan khusus.

Siapkan bukti evaluasi baru yang terpisah dari contoh dan kasus v4 yang sudah
dibuka. Laporkan keputusan, asesmen trial, kesalahan positif/negatif,
abstention, coverage dan biaya konteks. Belum ada klaim perbaikan FPR atau PSR
berdasarkan draft ini.

Pemeriksaan ulang lokal:

```powershell
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5.py
```

Perintah tersebut hanya membaca file dan membandingkan audit akhir. Snapshot
sumber dan beberapa inventory lama berada pada data/raw dan results/raw yang
dikecualikan dari Git. Arsip lokal tersebut diperlukan untuk mereproduksi
pemeriksaan lengkap; source lock tidak menjamin halaman hidup tetap identik.
