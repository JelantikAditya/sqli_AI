# Review isi konteks retrieval RAG — 7 Oktober 2026

## Kesimpulan

Konteks retrieval lokal belum siap dipakai untuk generasi kandidat formal.
Pencarian dan filtering sudah berjalan, tetapi skor teknis tinggi belum menjamin
bahwa potongan membahas teknik yang diminta secara utuh.

Dari 13 hasil retrieval (11 chunk unik), tiga berpotensi menjadi konteks inti
setelah dirapikan, satu merupakan pendukung interpretasi bukti, enam lebih tepat
untuk latar belakang/kajian paper, dan tiga perlu dikeluarkan sebagai chunk
tersendiri dari konteks generator. Kategori tersebut adalah penilaian kualitatif
Codex terhadap isi, bukan label final eksperimen atau metrik precision/FPR/PSR.

## Lingkup dan bukti review

Review menggunakan hasil yang sudah tersimpan; tidak menjalankan ulang embedding,
retrieval, generasi kandidat, atau request SQLi ke DVWA:

- S1: `results/raw/retrieval-S1-20261007T094806Z-a1ebe7.json` — error-based.
- S2: `results/raw/retrieval-S2-20261007T094808Z-f01159.json` — boolean-based blind.
- S3: `results/raw/retrieval-S3-20261007T094809Z-3186c6.json` — time-based blind.

Seluruh 13 potongan dibaca dan dicocokkan dengan teks serta tampilan delapan
halaman PDF lengkap dari tiga sumber:

- `sources/SQLi.pdf`: halaman PDF 4, 6, 9, 15, dan 20; nomor cetak 228, 230,
  233, 239, dan 244. Halaman 4 memiliki subbagian Boolean-based blind
  exploitation, Error-based exploitation, dan Time-based blind exploitation.
  Halaman lain memuat model simulasi, hasil, atau lampiran paper RL.
- `sources/gptsqli.pdf`: halaman PDF 11–12; bagian 6.1 Evaluation Settings,
  6.2 Effectiveness Evaluation (RQ1), Table 2, dan awal 6.3 Efficiency Evaluation
  (RQ2). Paragraf keterbatasan database error melintasi kedua halaman.
- `sources/[4] ijsse_14.06_27.pdf`: halaman PDF 2, nomor cetak 1934;
  bagian 2 Background dan 2.1 SQL injection vulnerability. Halaman juga memuat
  bagian XSS/CSRF, tetapi keduanya bukan fokus review atau konteks TA.

Protokol lokal di `docs/validation-loop.md` dibaca untuk menilai kesesuaian:
DAST/black-box, baseline benign, pasangan respons boolean, pengukuran waktu,
dan keputusan yang masih perlu review. Label skenario tidak dipakai untuk
menilai kebenaran payload karena tidak ada payload baru yang diuji.

Ringkasan terstruktur, ID chunk lengkap, hash sumber/teks, hash record retrieval,
dan keputusan per hasil ada di
`outputs/rag-retrieval-review/content-review-2026-10-07.json`.
Policy tetap
`6c6423c65b030ba711740ad5fa9b922bb7befb24d0a006f2bdc035ec73dfe0af`.
Hash ketiga sumber cocok dengan metadata chunk; PDF, index, selector, dan
aturan retrieval tidak diubah pada tahap review ini.

## Rubrik penilaian

1. **Kesesuaian teknik:** pembahasan utama sesuai query, bukan sekadar menyebut
   teknik itu sebagai perbandingan.
2. **Kelengkapan:** paragraf/keterangan cukup utuh; tidak kehilangan awal/akhir
   penting atau bercampur dengan tabel dan subbagian lain.
3. **Kegunaan untuk generator:** menjelaskan mekanisme atau bukti yang dapat
   diamati, bukan hanya angka keberhasilan dan teori RL.
4. **Kesesuaian TA:** tidak menganggap asumsi CTF/simulasi sebagai perilaku DVWA
   atau mengubah kriteria ground truth penelitian.

Kategori: **inti setelah dirapikan**, **pendukung setelah dirapikan**,
**kajian pustaka**, dan **keluarkan dari generator**. Tidak ada kategori
"siap tanpa perubahan" pada hasil yang ditinjau ini.

## S1 — error-based

| Rank / ID awal | Sumber / halaman PDF | Keputusan | Temuan dan tindakan |
| --- | --- | --- | --- |
| 1 / `350cf2380b7b` | SQLi / 4 | Inti setelah dirapikan | Penjelasan error mesin SQL relevan. Awal berupa sisa paragraf sebelumnya dan akhir terpotong. Ambil subbagian Error-based exploitation secara utuh. |
| 2 / `ab5b6658c20c` | gptsqli / 12 | Pendukung setelah dirapikan | Keterbatasan database error relevan untuk interpretasi. Awal paragraf berasal dari halaman 11 dan akhir masuk Table 2. Gabungkan hanya paragraf lengkap, tanpa tabel benchmark. |
| 3 / `8dd5d4588a1c` | gptsqli / 11 | Keluarkan dari generator | Didominasi hasil scanner; kalimat relevan terputus sebelum penjelasan utama. Jangan dipakai sebagai konteks tambahan tersendiri; gabungkan paragrafnya dengan rank 2. |

S1 memiliki materi teknik yang cukup menjanjikan. Namun, pembahasan gptsqli
berlaku pada SqliMicroBenchmark: database error tidak memenuhi kriteria
keberhasilan injeksi yang dipakai penulis pada target tersebut. Ini bukan aturan
bahwa setiap SQL error pasti false positive pada DVWA. Tetap gunakan kriteria
proposal dan validasi black-box proyek, termasuk pembanding baseline.

## S2 — boolean-based blind

| Rank / ID awal | Sumber / halaman PDF | Keputusan | Temuan dan tindakan |
| --- | --- | --- | --- |
| 1 / `be37eb9039da` | [4] ijsse / 2 | Kajian pustaka | Taksonomi banyak teknik; boolean hanya dijelaskan singkat. Input validation pada bagian pencegahan ikut menaikkan skor validasi. Jangan menjadi konteks inti. |
| 2 / `ed3b0407dc37` | SQLi / 4 | Keluarkan dari generator | Dominan time-based: latency, traffic, pengulangan request. Boolean hanya sebagai pembanding; akhir masuk RL. Bagian time-based dapat digunakan untuk S3 setelah dirapikan. |
| 3 / `20e4a1a822bc` | SQLi / 4 | Inti setelah dirapikan | Penjelasan respons biner/truth-value relevan. Awal berisi UNION di luar fokus dan akhir kalimat terpotong. Ambil subbagian Boolean-based blind exploitation secara utuh. |
| 4 / `6f933db0663f` | SQLi / 6 | Kajian pustaka | Respons biner relevan secara konsep, tetapi konteksnya CTF/simulasi RL. Chunk berhenti sebelum asumsi simulasi lengkap. Jangan menganggap flag/escape simulasi sebagai protokol DVWA. |
| 5 / `b1ee8213742d` | SQLi / 4 | Keluarkan dari generator | Dominan error-based dan time-based; boolean disebut sebagai perbandingan. Tidak menjelaskan perbandingan pasangan boolean secara langsung. |

Dua dari lima hasil dominan membahas teknik lain. Penjelasan inti yang lebih
sesuai ada di rank 3, bukan rank 1. Subbagian lengkap halaman 4 juga berisi
penjelasan bahwa contoh probing awal belum merupakan eksploit yang selesai;
kalimat pembatas seperti ini sebaiknya tidak hilang karena chunking.

Untuk konteks TA, prioritaskan mekanisme pasangan kondisi true/false dan
perbedaan respons yang dapat diamati. Pengetahuan tentang panjang/isi respons
perlu dibedakan dari asumsi panjang respons pada simulator paper.

## S3 — time-based blind

| Rank / ID awal | Sumber / halaman PDF | Keputusan | Temuan dan tindakan |
| --- | --- | --- | --- |
| 1 / `be37eb9039da` | [4] ijsse / 2 | Kajian pustaka | Hanya taksonomi dan kalimat umum tentang waktu; pencegahan ikut menyumbang skor validasi. Bukan konteks inti pengukuran latency. |
| 2 / `13bebc6a74fc` | SQLi / 15 | Kajian pustaka | Fragmen Table 7 dan pembahasan hasil agent3t, termasuk time-based 95,83% dalam simulasi. Angka ini bukan PSR TA atau jaminan keberhasilan di DVWA. |
| 3 / `ed3b0407dc37` | SQLi / 4 | Inti setelah dirapikan | Membahas latency, traffic, dan pengulangan request. Awal kalimat hilang dan akhir masuk RL. Ambil seluruh subbagian Time-based blind exploitation. |
| 4 / `b4a50e77696d` | SQLi / 9 | Kajian pustaka | Bagian 3.7 Simulation3: threshold arbitrer dan traffic stokastik. Ada pengetahuan tentang ketidakpastian, tetapi model itu bukan protokol DVWA. |
| 5 / `8a0e256b239a` | SQLi / 20 | Kajian pustaka | Lampiran C.2/C.3 menjelaskan kegagalan/salah klasifikasi agent. Berguna untuk keterbatasan penelitian, kurang langsung membantu pembentukan kandidat. |

Table 7 merupakan hasil simulasi agent3t; bagian 4.2.3 menyebut pengujian
agent3/agent3t pada 10.000 kasus. Traffic 5% adalah probabilitas pada model
simulasi paper, bukan kondisi jaringan laptop. Simulation3 halaman 9 memakai
threshold arbitrer dan Eq. (2) untuk probabilitas traffic episode. Jangan
membawa threshold/probabilitas itu menjadi konfigurasi TA.

Halaman 4 mendukung prinsip bahwa respons lambat dapat disebabkan traffic
dan perlu pengulangan. Namun, konteks yang terambil belum menjelaskan secara
utuh pembentukan delay SQL yang terkontrol dan kontrol pembandingnya.
Karena itu, membaiknya konteks pengukuran waktu belum berarti pengetahuan
untuk generasi kandidat time-based sudah lengkap.

## Akar masalah selector

- **Skor dihitung untuk seluruh chunk.** Penyebutan boolean di paragraf
  time-based mendapat skor teknik dan respons true/false sekaligus, walau
  pembahasan utama bukan boolean.
- **Cue validasi terlalu luas.** `validat` juga cocok dengan input validation
  pencegahan. Itu berbeda dari validasi bukti DAST/baseline.
- **Chunk berbasis jendela kata/karakter.** Potongan dapat dimulai di tengah
  kata, berhenti sebelum kalimat selesai, atau memuat beberapa subbagian.
- **Semua body diperlakukan setara.** Hasil benchmark, simulasi, lampiran,
  uraian teknik, dan pembahasan keterbatasan bersaing dengan bobot yang sama.
- **Dedup teks tidak menyelesaikan fragmen paragraf.** Halaman 11/12 dapat
  menjadi potongan terpisah dari satu pembahasan tanpa overlap shingle besar.

## Prioritas perbaikan berikutnya

1. **Rapikan chunk menurut subbagian/paragraf.** Pisahkan tiga bagian teknik
   halaman 4; pertahankan awal/akhir kalimat dan provenance. Gabungkan paragraf
   gptsqli halaman 11–12 sebelum Table 2. Implementasi harus berupa aturan
   umum, bukan hardcode ID/halaman yang unggul pada S1.
2. **Pisahkan peran pengetahuan.** Bedakan teknik, interpretasi/validasi,
   latar belakang, simulasi, hasil, dan lampiran. Prioritaskan teknik serta
   interpretasi; jangan mengecualikan seluruh paper RL karena bagian tekniknya
   tetap berguna.
3. **Perbaiki relevansi berdasarkan konteks lokal.** Hitung cue dalam paragraf
   atau subbagian yang sesuai; penyebutan teknik lain dan input validation
   tidak boleh mengalahkan penjelasan langsung mekanisme target.
4. **Review ulang coverage sebelum generasi.** Error: bukti respons dan
   batas interpretasi. Boolean: kondisi berpasangan dan beda respons. Time:
   delay terkontrol, baseline, pengulangan, dan ketidakpastian waktu. Jika
   cakupan tetap kurang setelah perbaikan, baru tambahkan referensi teknis
   pelengkap yang terkurasi.

Protokol pengujian seperti baseline, budget, dan format pasangan harus
konsisten pada prompt dasar RAG-off/on; label ground truth tetap di evaluasi.
Pengetahuan baru bukan pengganti pemeriksaan budget token: konteks aktual
harus utuh dan muat sebelum generasi Qwen.

Tidak perlu menambah banyak PDF sekarang. Penjelasan inti sudah ditemukan
pada sumber yang ada, tetapi pemilihan/pemotongannya belum layak. Catatan ini
menutup tahap review; perbaikan selector/chunking dan eksperimen kandidat
merupakan langkah berikutnya. Tidak ada hasil FPR/PSR baru dari review ini.
