# Automation Penetration Testing SQL Injection dengan LLM dan RAG

Repositori implementasi tugas akhir untuk pengujian **DAST/black-box** pada
**DVWA**. Ruang lingkup penelitian adalah SQL injection error-based,
boolean-based blind, dan time-based blind pada level Low, Medium, High, serta
Impossible. Evaluasi utama membandingkan **FPR** sistem dengan/tanpa RAG dan
**PSR** payload LLM terhadap SecLists.

## Status audit terakhir per 20 Oktober 2026

Diagnosis SQLi API pada 36 kasus sintetis selesai dan diaudit: 26 verdict benar,
sembilan analysis error, dan satu verdict valid keliru pada marker time-based.
Preflight ringkas `/no_think` menghasilkan kandidat berformat valid pada S1-S3.
Pilot lokal DVWA Low menunjukkan sinyal executor konsisten untuk S1, tetapi
kandidat S2/S3 tidak membedakan respons boolean atau menghasilkan delay.
Regenerasi berbasis feedback kembali terpotong atau timeout. Ini masih pilot
pengembangan, bukan evaluasi PSR/FPR; run API formal belum dimulai. Lihat
[hasil pilot generasi API](docs/hasil-pilot-generasi-qwen-api-2026-10-20.md),
[preflight generasi](docs/hasil-preflight-generasi-qwen-api-2026-10-20.md),
[diagnosis analisis](docs/hasil-diagnosis-qwen-api-2026-10-20.md),
[protokol review blind API](docs/protokol-review-blind-qwen-api-2026-10-20.md),
dan [draft amendemen metode](docs/usulan-amendemen-metode-qwen-api-2026-10-20.md).

Uji prompt khusus S1 dan S3 kemudian selesai dengan satu request per skenario
dan tanpa retry. Keduanya menghasilkan kandidat yang lolos schema serta
kebijakan lokal. Ketika diuji pada DVWA Low, S1 memberi sinyal error 3/3 dan
S3 memberi selisih waktu 2001,18-2017,12 ms terhadap kontrol `SLEEP(0)` pada
3/3 konfirmasi. Ini pilot pengembangan, bukan skor PSR/FPR. VAL-01 kemudian
menilai kedua packet pilot dengan keputusan `success`; anotasi manusia telah
diimpor secara terpisah. Lihat
[hasil uji prompt S1/S3](docs/hasil-uji-prompt-khusus-s1-s3-2026-10-20.md).

**Tahap saat ini:** pilot API S1/S3 dan review VAL-01 selesai; persiapan
eksperimen formal API masih berlangsung dan belum ada run formal. Sebelum
memulai, catat pemicu peralihan bersyarat dari model lokal, finalkan cakupan
provider/model, dan bekukan metode serta gate pipeline API.

Peneliti memilih alias API Qwen3.8-27B untuk pengujian lanjutan. Uji umum
selesai: 3/3 soal tunggal serta 9/9 giliran pada tiga percakapan pendek lulus.
Metadata respons Qwen konsisten melaporkan self-dploy/Qwen3.8-27B; identitas
upstream belum diverifikasi independen. Ini belum merupakan pengujian SQLi.
Lihat [hasil uji percakapan API](outputs/hcnsec-qwen38-multiturn-20261020T085758633152Z/report.md).

Rancangan lanjutan menuju tenggat 30 Oktober tersedia sebagai usulan, dengan
target hasil/naskah pada 28 Oktober. Rancangan mencakup perubahan batasan
proposal yang masih mewajibkan Qwen2.5 7B mandiri tanpa API pihak ketiga,
adapter versi baru, pilot domain, formal A/B/C, serta validasi independen.
Eksperimen formal API belum dijalankan. Lihat
[rancangan kerja Qwen API](docs/rancangan-lanjutan-qwen-api-2026-10-20.md).

Uji koneksi API HCNSEC/DeepSeek selesai dengan satu permintaan: HTTP 200,
respons API_OK, sekitar 9 detik, dan 18 token menurut usage gateway. Request
memakai DeepSeek-V4-Pro, tetapi response.model melaporkan
self-dploy/DeepSeek-V4-Flash-Vision-Exp. Identitas backend belum terverifikasi;
uji ini belum menjadi evaluasi SQLi atau pilot RAG. API key tidak disimpan
dalam berkas. Lihat [hasil dan batas uji API](docs/uji-api-deepseek-2026-10-20.md).

Pilot v5 r2 selesai setelah persetujuan peneliti: 108 inferensi, 18 skip
invalid, dan nol analysis error. Akurasi mentah A=23/36 (63,89%), B2/B3=24/36
(66,67%). Selisih satu kasus pada pilot-011 disertai trial 2 rekaan pada B2/B3;
asesmen trial turun dari 75/102 ke 74/102 dan klaim positive keliru pada
referensi negative tetap enam per profil. Seluruh 108 parse/skor direproduksi
dan 1.183 file historis tetap utuh. Hasil sintetis ini belum membuktikan
penurunan FPR atau penalaran yang lebih andal. Receipt persetujuan disimpan
terpisah dari metadata pending saat freeze. Lihat
[hasil dan batas pilot r2](docs/hasil-pilot-analisis-v5-r2-2026-10-20.md).

Paragraf persiapan berikut mencatat status sebelum persetujuan dan inferensi.

Revisi r2 paket pilot menindaklanjuti review yang diteruskan pengguna tanpa
mengubah 42 label, korpus rev2, input, jadwal atau request. Batas output tetap
konservatif: stop pada 768 token dikategorikan output-budget-rejection,
terpisah dari length stop dan kegagalan JSON. Struktur/citation tidak dikenal
dibedakan dari warning semantik; reason-code accuracy dan consistency serta
transisi salah/benar A/B3 dilaporkan terpisah. Review peneliti tetap pending;
evaluasi pilot belum dijalankan. Paket asli tetap menjadi arsip reproduksi.
Lihat [protokol dan batas r2](docs/paket-pilot-analisis-v5-r2-2026-10-20.md).

Paket persiapan pilot v5 sudah dikunci: 36 kasus eligible sintetis dan enam
kasus invalid, dengan label terpisah, jadwal A/B2/B3 seimbang, kebijakan tanpa
retry otomatis, metrik akurasi keputusan mentah A versus B3, serta gate input
invalid sebelum model. Seluruh 126 request aktual sudah diaudit dan hanya
reference_context berbeda antarprofil. Prompt terbesar 1694 token dengan
reserve output 768 pada context 4096 menyisakan minimum 1634 token. Sebanyak
24 tes offline lulus dan 1.144 file sebelumnya tetap utuh. Evaluasi keputusan
pilot belum dijalankan; label AI masih pending review peneliti dan belum
menjadi holdout independen. Lihat
[paket pilot dan aturan kesimpulan](docs/paket-pilot-analisis-v5-2026-10-20.md)
serta [tabel review kasus](outputs/analysis-v5-pilot-review/cases.review.md).

Preflight konteks v5 selesai: 36 request dihitung offline dan sembilan probe
Qwen dengan stop awal cocok persis dengan hitungan tokenizer. Prompt terbesar
1684 token; context 4096 dengan reserve output 768 menyisakan minimum 1644.
Penilaian relevansi AI atas 36 pasangan query/chunk selesai, tanpa menjadi gold
manusia. Kandidat pengembangan A/B3 disiapkan, B2 tetap pembanding sekunder.
Belum ada evaluasi verdict pilot. Lihat
[preflight konteks dan profil v5](docs/preflight-konteks-dan-profil-v5-2026-10-20.md).

Korpus rev2 memperjelas batas marker/template dan mengoreksi atribusi review:
masukan sebelumnya berbantuan AI; pemeriksaan/adopsi peneliti belum tercatat.
Renderer dan inspeksi retrieval selesai dengan Nomic lokal tanpa Qwen chat.
Seluruh sembilan pasangan request menjaga kontrak serta paired evidence.
Pada top-2, ketiga query utama masih kehilangan satu topik teknik; top-3
sekunder menutup coverage dengan konteks lebih panjang. Profil pilot belum
dipilih. Lihat [hasil renderer dan retrieval](docs/renderer-retrieval-v5-2026-10-20.md).

Review berbantuan AI atas draft v5 meminta revisi kecil. Versi rev1 tersedia:
peran executor/model dan semantik diagnostik diperjelas, template dibatasi pada
persiapan bukti, dan lima keputusan desain menggantikan basis research-design.
Jumlah tetap 7 chunk/35 field/38 pernyataan, kini 13 parafrasa/25 adaptasi.
Pemeriksaan kode offline serta preservasi 1.072 file lulus. Rev1 masih menunggu
review ulang sebelum freeze pilot. Catatan ini merupakan tahap historis;
atribusi AI dan versi aktif mengikuti paragraf rev2 di atas. Lihat
[revisi v5 rev1](docs/revisi-korpus-analisis-v5-rev1-2026-10-20.md).

Draft korpus analisis v5 tersedia: tujuh topik, 35 field dan 38 pernyataan
dengan provenance terpisah untuk 14 parafrasa sumber serta 24 adaptasi peneliti.
Referensinya OWASP WSTG v4.2 dan tiga halaman PortSwigger. Audit mekanis serta
preservasi 1.053 file lulus; review peneliti masih pending. Belum ada retrieval,
embedding, inferensi, atau integrasi runner v5. Lihat
[draft dan panduan review v5](docs/korpus-analisis-v5-2026-10-20.md).

R1, R2, dan R3 selesai: 99 run completed dan 9 slot C/Impossible excluded.
Anotasi terbaru VAL-01 dan agregasi F02 selesai; PSR utama sudah tersedia,
sedangkan FPR utama tetap undefined akibat abstention S10. Lihat
[progres formal](docs/progress-2026-10-19.md),
[hasil VAL-01](docs/f02-hasil-val01-2026-10-19.md), dan
[rencana penyelesaian](docs/rencana-penyelesaian-2026-10-16.md).

Salinan anotasi dan ekspor metrik tersedia di
[hasil terolah formal](results/processed/formal-sqli-v1-20261017/README.md).
Lihat juga [panduan VAL-01](docs/panduan-penilaian-val01-formal.md) dan
[rencana perbaikan berikutnya](docs/rencana-perbaikan-setelah-formal-2026-10-19.md).

Pengembangan lanjutan memakai Qwen 2.5 7B: pilot v1 dan validasi kontrak v2
selesai. Pada 16 kasus baru, verdict v2 tepat 11/16 dibandingkan v1 10/16;
mismatch reason_code turun 7 ke 0, tetapi asesmen trial turun 33/44 ke 32/44.
V2 belum memenuhi kriteria dan belum diintegrasikan ke runner. Lihat
[hasil pilot v1](docs/pilot-perbaikan-analisis-v1-2026-10-19.md),
[validasi v2](docs/validasi-kontrak-analisis-v2-2026-10-19.md), dan
[arsip hasil v2](results/processed/response-analysis-dev-v2-20261019/README.md).

Shadow verifier v3 juga selesai. Pada 20 kasus valid baru, verdict gabungan
tepat 17/20 dibandingkan Qwen 15/20. Tiga klaim positif keliru ditahan menjadi
inconclusive, sehingga coverage negatif turun 7/7 ke 4/7. Varian tetap audit
sekunder dan tidak mengubah FPR/PSR formal. Lihat
[metode dan hasil v3](docs/varian-verifikasi-hibrida-v3-2026-10-19.md).

Pilot RAG analisis v4 selesai dengan 36 inferensi berpasangan. Pada 18 kasus
valid baru, A/B sama-sama tepat 12/18 verdict dan 37/51 asesmen trial, dengan
tiga klaim positif pada enam fixture negatif. Tambahan dua referensi belum
meningkatkan hasil pada konfigurasi ini. Klaim mentah tetap keluaran utama;
gate v3 tetap sekunder. Lihat
[pilot RAG analisis v4](docs/pilot-rag-analisis-v4-2026-10-19.md).

Review kurasi analisis juga selesai: sembilan entri/45 field diperiksa terhadap
snapshot sumber. Ada satu ambiguitas scope pada hasil boolean; aturan tiga
trial, ambang timing dan reason_code merupakan kontrak proyek. Korpus asal
sudah disetujui peneliti, meskipun metadata beku masih bertuliskan pending.
Korpus, indeks dan metrik formal tetap utuh selama review. Lihat
[review dan rekomendasi perbaikan korpus](docs/review-rag-analisis-2026-10-19.md).

| Area | Status |
| --- | --- |
| T01, protokol dan metodologi | Protokol v5 frozen dengan release formal v18-r2. Aturan konfirmasi 3/3, abstention, averaging, dan coverage tetap berlaku. |
| T03-T04, kontrol dan SecLists | Kondisi C formal menyelesaikan 27 run S1-S9 di tiga replikasi. Sembilan slot C/Impossible excluded sesuai desain. |
| T05 dan U02-U03, pipeline adaptif | Kondisi A dan B formal masing-masing menyelesaikan 36 run; setiap run completed memiliki 10 kandidat valid. |
| U04-U05, validasi dan agregasi | Seluruh 990 anotasi terbaru VAL-01 diterima dan diimpor. Mean PSR B=27,78% dan C=74,81% pada tiga replikasi; SD sampel masing-masing 0,00 dan 1,70 poin persentase. FPR utama undefined karena S10 inconclusive pada seluruh A/B. |
| U06, pilot terpadu | U06.1 selesai untuk S3 replicate 1 dan U06.2 membuktikan 2/2 koordinat pada empat level. U06.3 selesai: 28 run completed, 5 excluded karena budget, 3 slot tidak berlaku, 0 invalid. U06.4 selesai sebagai validasi alur pilot: empat anotasi VAL-01 berhasil diimpor dan agregator menahan metrik yang belum eligible. Pilot bukan dataset formal. |
| U07, freeze formal | Release formal v18-r2 disetujui dan digunakan. Amendment 19 Oktober hanya mengatur pemulihan index runner B pada R3; artefak R1/R2 dipertahankan. |
| Eksperimen dan metrik formal | F01 dan proses F02 selesai: 99 run completed, 9 excluded, 0 unit invalid pada checkpoint akhir. PSR utama eligible pada 540 kandidat B/C S1-S9. FPR utama undefined dengan coverage negatif 66,67%; keterbatasan dicatat untuk F03. |

Rincian evidence, cakupan, dan batas interpretasi ada di
[review progres 14 Oktober](docs/review-progress-2026-10-14.md),
[laporan U06](docs/u06-pilot-zap-baseline-2026-10-14.md), dan
[evidence U06 v15](docs/evidence/u06-v15-integrated-pilot-2026-10-16.json).

## Riwayat progres dan bukti terdahulu

Catatan di bagian ini merangkum tahap-tahap sebelumnya. Status yang masih
tertulis pending di dokumen lama adalah snapshot pada tanggal dokumen tersebut,
bukan status proyek terkini. Gunakan tabel di atas dan
[rencana penyelesaian](docs/rencana-penyelesaian-2026-10-16.md) sebagai acuan
status aktif.

- **T01 selesai** pada definisi evaluasi dan metodologi lokal. Protokol aktif
  `local-sqli-v5-pilot` menetapkan konfirmasi 3/3, abstention run, rotasi
  kondisi, reset, unit, dan batas retry. Lihat
  [keputusan T01](docs/keputusan-urutan-kondisi-2026-10-14.md).
- **Pilot integrasi T02/T05 S1 A/B berhasil pada 14 Oktober.** Kedua kondisi
  menjalankan 10 kandidat, 3 konfirmasi per kandidat, reset database, dan
  ledger. LangChain Core 1.6.10 berjalan serial dengan Ollama lokal. B mencatat
  7 bukti executor 3/3, sementara Qwen mengklaim `NOT_VULNERABLE` untuk semua
  kandidat pada A dan B. Klaim dan bukti menunggu review independen; FPR/PSR
  formal belum dihitung. Baca [evidence pilot](docs/evidence/t05-ab-s1-langchain-live-pilot-2026-10-14.json).
- **Kontrol T03 dan persiapan/eksekusi SecLists T04 terbukti pada 14 Oktober.**
  Pilot kontrol manual S1-S12 valid; C S1-S9 menyelesaikan 90 kandidat dan
  270 konfirmasi setelah reset per run. Timing kini memakai payload yang sama
  dengan `SLEEP(0)`, dan baseline tercatat pada semua teknik. Lihat
  [laporan T03/T04](docs/t03-t04-controls-2026-10-14.md).
- Pilot lifecycle T05 S1 A/B/C terdahulu memproses ketiga kondisi: A dan C
  lengkap 10 kandidat, B excluded setelah hanya menghasilkan 4 kandidat akibat
  duplikasi. C tetap berjalan setelah B, dan execute-resume tidak mengubah
  ledger. Ini merupakan histori run, bukan status U02 terbaru. Status rinci ada di
  [review progres](docs/review-progress-2026-10-14.md).
- **U02 selesai pada subset S1 A/B.** Enam condition-run seed 42/43/44 masing-
  masing menyelesaikan 10 kandidat unik dengan tiga konfirmasi, nol generation
  failure, nol duplikasi, dan guard error-based syntax-only aktif. Integrasi ini
  membuktikan kestabilan budget pada S1, bukan cakupan semua teknik/level atau
  hasil FPR/PSR formal. Lihat [rancangan tugas](docs/rancangan-tugas-2026-10-14.md).
- **U03 menyelesaikan smoke wiring loop adaptif lintas teknik dan level.**
  Smoke satu kandidat mencakup S2-S12 pada kondisi A dan B; sepuluh smoke B
  tambahan valid dan selesai dianalisis. Dua klaim positif pada kontrol
  Impossible tetap menjadi observasi model untuk audit. S1 memiliki pilot
  budget penuh tersendiri pada U02. Smoke ini tidak masuk FPR/PSR. Lihat
  [ringkasan awal](docs/evidence/u03-adaptive-shape-smoke-2026-10-14.json) dan
  [smoke tambahan B](docs/evidence/u03-adaptive-cross-condition-smoke-2026-10-14.json).
- Audit Qwen menunjukkan klaim yang bertentangan dengan evidence diagnostik.
  Kontrak output mengaudit asesmen per-trial dan cakupan sitasi. Prompt v8
  regression replay tujuh fixture cocok pada 5/7 kasus keseluruhan dan 4/6
  kasus valid. Validasi tertutup sintetis satu kali pada 21 fixture cocok pada 14/21
  kasus keseluruhan dan 11/18 kasus runtime-valid. Mismatch dicatat sebagai
  kinerja model; keduanya bukan FPR/PSR formal. Lihat
  [audit Qwen](docs/audit-analisis-qwen-2026-10-14.md).
- LangChain serial dengan Ollama sudah dibuktikan pada loop adaptif S1 A/B.
  Audit U07 memverifikasi integrasi serial pada seluruh 24 attempt A/B S1-S12.
  Marker pada protokol pilot tetap pending sampai release formal; gate budget
  generasi dinilai terpisah. Lihat [laporan U07](docs/u07-freeze-kesiapan-formal-2026-10-17.md).
- Rancangan tugas lanjutan U00-U07 tersedia di
  [rencana tugas](docs/rancangan-tugas-2026-10-14.md). Paket blind dan agregator
  T06 tersedia dan diuji offline. Identitas/kualifikasi validator VAL-01 serta
  independensinya telah dikonfirmasi; prosedur pilot tiga kandidat telah ditinjau.
  Anotasi formal pada paket U06 belum dilakukan, sehingga metrik formal belum ada.
- Bukti loop adaptif dua kandidat pada 12 Oktober tetap historis dan tidak
  disamakan dengan pilot budget penuh 14 Oktober. Riwayat tahap terdahulu ada
  di [kontrak analisis Qwen](docs/qwen-response-analysis-contract.md).
- Pada 12 Oktober, loop adaptif Qwen sudah menjalani pilot lokal berpasangan
  RAG-off/RAG-on pada S1 Low. Kedua kondisi menjalankan dua kandidat dengan
  tiga konfirmasi; generator menerima keputusan dan evidence kandidat
  sebelumnya. Hasil masih incomplete terhadap budget 10, sehingga belum
  menghasilkan FPR/PSR formal. 51 unit test lulus. Lihat
  [kontrak dan bukti pilot Qwen](docs/qwen-response-analysis-contract.md)
  serta [ringkasan evidence yang disanitasi](docs/evidence/adaptive-s1-pilot-2026-10-12.json).
- Arah kerja aktif per 11 Oktober: eksperimen dilakukan pada laptop lokal
  sesuai arahan peneliti. Colab dan tunneling ditunda; tahapan integrasi serta
  evaluasi ada di [rancangan kerja lokal](docs/rencana-kerja-lokal-2026-10-11.md).
- Kelanjutan lokal pada 11 Oktober: protokol pilot tersedia, discovery HAR ZAP
  mencakup koordinat S1-S12 pada empat level, dan pasangan S1 dengan input ZAP
  terverifikasi sudah diuji sampai eksekusi. Loop adaptif dan evaluasi formal
  tetap merupakan pekerjaan berikutnya. Lihat
  [progres discovery lokal](docs/progress-local-discovery-2026-10-11.md)
  dan [protokol evaluasi](docs/protokol-evaluasi-lokal.md).
- Lingkungan DVWA dan MariaDB berjalan melalui Docker Compose.
- Empat level keamanan DVWA telah diuji melalui antarmuka web.
- Akses dari runtime Colab ke DVWA melalui tunnel bertoken sudah diverifikasi
  pada 28 September 2026; [catatan uji](docs/progress-2026-09-28.md).
- Plan ZAP untuk discovery SQLi terautentikasi kini menangani `user_token`,
  memverifikasi level sesi, dan mewajibkan bukti login sebelum melaporkan hasil.
  Run terautentikasi berhasil pada 1 Oktober 2026 untuk keempat level; detail
  dan batas interpretasi ada di
  [catatan ZAP](docs/zap-baseline-2026-10-01.md)
  dan [petunjuk run](dvwa/README.md#discovery-zap-terautentikasi).
- Parser ZAP, validation loop DVWA, batch builder, indexing/retrieval Chroma,
  dan generator kandidat Qwen lokal sudah memiliki implementasi awal.
  Pengujian formal dan pengukuran FPR/PSR belum dimulai; rincian progres ada di
  [catatan progres rinci per 2 Oktober](docs/progress-2026-10-02.md).
- Pada 7 Oktober, Qwen 2.5 7B dan embedding Nomic berhasil diuji di laptop
  lokal. Index 15 PDF merupakan uji diagnostik awal. Jalur utama kini memakai
  sembilan entri JSON terstruktur dari OWASP WSTG v4.2 dan PayloadsAllTheThings
  SQL Injection, sesuai proposal. Index aktif dan retrieval semantik sudah
  diverifikasi lokal, termasuk koordinat report ZAP High. Notebook Colab
  diperbarui tetapi belum dijalankan dan kini menjadi jalur historis yang ditunda.
  Review peneliti atas sembilan entri korpus disetujui pada 12 Oktober; eksperimen
  formal masih diperlukan. Lihat [penyesuaian RAG terhadap proposal](docs/proposal-rag-2026-10-07.md)
  dan [laporan progres harian 7 Oktober](docs/progress-2026-10-07.md).
- Pada 11 Oktober, review teknis sembilan entri selesai dan pasangan S1
  RAG-off/on berhasil dibuat oleh Qwen lokal serta dieksekusi satu replikasi
  pada DVWA Low. Kedua kandidat memunculkan SQL error baru terhadap baseline.
  Pada tanggal catatan tersebut, review peneliti/validator masih pending.
  Review korpus disetujui pada 12 Oktober dan VAL-01 dikonfirmasi pada 14
  Oktober; hasil smoke tetap bukan FPR/PSR. Lihat [hasil smoke S1](docs/progress-2026-10-11.md)
  dan [review korpus](docs/corpus-review-2026-10-11.md).

Petunjuk menjalankan lab ada di [dvwa/README.md](dvwa/README.md).
Untuk menemukan kode dan penyimpanan lokal RAG, SecLists, runner, ledger, serta
evidence, lihat [peta struktur proyek](docs/peta-struktur-proyek.md).
Notebook historis untuk memverifikasi koneksi dari runtime Google Colab ada di
[notebooks/colab_dvwa_smoke.ipynb](notebooks/colab_dvwa_smoke.ipynb).
Rincian milestone awal juga tersedia di
[catatan progres 28 September](docs/progress-2026-09-28.md).

## Prinsip reproduksibilitas

- Gunakan hanya target DVWA milik sendiri pada lingkungan terkontrol.
- Catat image Docker, level keamanan, endpoint, jenis SQLi, konfigurasi
  RAG, sumber payload, seed, dan nomor pengulangan pada setiap percobaan.
- Simpan hasil agregat dan contoh log yang telah disanitasi dalam repositori.
  Simpan token, cookie, dump database, artefak mentah, model besar, serta PDF
  referensi di luar Git.
- Proposal dan artikel referensi dicantumkan sebagai sitasi bibliografis dalam
  paper, bukan disalin sebagai PDF ke repositori ini.
