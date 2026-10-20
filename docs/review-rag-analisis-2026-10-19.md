# Review kurasi RAG untuk analisis respons

Tanggal: 19 Oktober 2026. Status: review teknis Codex selesai terhadap sembilan
entri dan 45 field proyeksi v4. Review dilakukan setelah hasil pilot terbuka;
ini bukan penilaian buta, review manusia independen, atau eksperimen baru.

## Hasil utama

Mekanisme SQLi dalam proyeksi mempunyai dukungan pada snapshot OWASP WSTG v4.2
dan PayloadsAllTheThings yang dikunci. Kontrol baseline, pengulangan, sebagian
peringatan kompatibilitas dan batas klaim merupakan sintesis editorial.
Kecukupan sumber konsep tidak otomatis membuktikan kecukupan untuk klasifikasi
bukti HTTP berdasarkan kontrak proyek.

Ada satu ambiguitas scope: limitations pada sqli-boolean-quoted menyebut
respons identik sebagai inconclusive. Kalimat itu tidak membedakan ketidakpastian
tentang kerentanan target dari hasil negatif suatu kandidat. Kontrak proyek
menetapkan bukti lengkap 0/3 sebagai negative untuk kandidat, tanpa menyimpulkan
target bebas SQLi. Prompt bersama A/B v4 sudah menetapkan prioritas kontrak
tersebut. Review ini tidak membuktikan ambiguitas itu menyebabkan hasil v4.

Seluruh sembilan entri juga mewarisi pointer Remediation yang tidak digunakan
untuk mendukung field proyeksi analisis. Pointer tersebut berasal dari korpus
lengkap yang masih memuat mitigasi; keberadaannya bukan bukti dukungan per field.

## Koreksi status persetujuan

Korpus asal sudah disetujui peneliti pada 12 Oktober untuk pilot dan pada
17 Oktober untuk penggunaan formal. Hash snapshot pada receipt cocok dengan
file saat ini. Nilai researcher_review=pending dipertahankan pada metadata
beku agar korpus/index tidak berganti identitas. Nilai tersebut tidak berarti
persetujuan korpus asal belum pernah diberikan.

Lihat [review peneliti 12 Oktober](evidence/review-peneliti-2026-10-12.md) dan
[keputusan penggunaan formal](keputusan-korpus-formal-u07-2026-10-17.md).
Persetujuan korpus asal tidak otomatis menjadi review independen atas proyeksi
analisis baru. Review teknis ini belum mempunyai persetujuan manusia tersendiri.

## Pemeriksaan per entri

Seluruh rentang rujukan diperiksa pada snapshot lokal yang hash-nya cocok
dengan knowledge/sources.lock.json. Metadata commit, path dan koordinat baris
tersedia per field dalam [matriks review](../results/processed/analysis-rag-corpus-review-20261019/review.json).

| Entri | Dipilih v4 | Temuan |
| --- | --- | --- |
| sqli-error-quote | Ya | Quote probe, satu variabel dan inspeksi HTML didukung sumber; syarat baru terhadap baseline merupakan kontrol proyek. |
| sqli-error-message | Ya | Diagnostik lintas DBMS didukung sumber; batas fingerprinting dan pembandingan baseline merupakan penegasan editorial. |
| sqli-error-xml | Tidak | Mekanisme error pembawa informasi dan fungsi XML didukung; marker konstan serta pembedaan missing-function merupakan adaptasi. Kompatibilitas versi tidak diuji ulang. |
| sqli-boolean-numeric | Ya | Pasangan true/false numerik didukung; repeatability dan pengendalian delivery diperjelas secara editorial. |
| sqli-boolean-quoted | Ya | Quote balancing dan kelas respons didukung; scope kata inconclusive perlu diperjelas pada versi baru. |
| sqli-boolean-template | Tidak | WSTG baris 297 mendukung template konten dinamis dan filtering konsisten. Entri ini tersedia tetapi tidak terpilih oleh query boolean v4. |
| sqli-time-conditional | Ya | Conditional delay didukung; matched no-delay control merupakan prosedur editorial. |
| sqli-time-repeated | Ya | Conditional delay didukung; prosedur pengukuran berulang memang sudah diberi label editorial adaptation. |
| sqli-time-subselect | Tidak | Subselect bersyarat didukung; kontrol matched dan penggantian informasi target dengan konstanta merupakan adaptasi. |

Dari 45 field yang ditinjau, 18 berupa label editorial title/type. Pada 27 field
substantif, tujuh dinilai supported_paraphrase, 13 source_and_editorial, enam
editorial_guardrail, dan satu scope_ambiguity. Kategori ini adalah penilaian
teknis Codex, bukan akurasi sitasi, precision retrieval, atau metrik eksperimen.

## Kecukupan untuk verifikasi bukti

| Kebutuhan | Cakupan proyeksi v4 | Implikasi |
| --- | --- | --- |
| Diagnostik baru terhadap baseline | Sebagian | Konsep ada; matcher dan indikator operasional tetap harus dijelaskan dalam protokol proyek. |
| Arah true/false dan kelas respons | Sebagian | Marker exists/missing dan pengecualian status HTTP adalah pemetaan aplikasi, bukan aturan universal sumber. |
| Konten dinamis | Tersedia pada entri yang tidak terpilih | Perlu penilaian relevansi pada query baru; jangan mengganti retrieval v4 setelah melihat hasilnya. |
| Matched control timing | Sebagian | Referensi menyebut kontrol dan variasi latency; kontrak kesesuaian marker/status berasal dari proyek. |
| Delta dan ambang 1500 ms | Tidak ditentukan referensi | Angka ambang dan aturan perbandingan merupakan metode proyek, sudah diberikan bersama pada A/B. |
| Tiga trial, mixed dan incomplete | Tidak ditentukan referensi | Tabel keputusan v2 merupakan kontrak proyek. Pengulangan umum tidak menentukan aturan 3/3. |
| Sesi, baseline dan measurement valid | Sebagian | Bukti tidak lengkap, login redirect dan runtime invalid memerlukan precondition proyek tersendiri. |
| Decision dan reason_code | Tidak ditentukan referensi | Enum berasal dari schema/prompt. Konsistensi kode tetap harus dinilai terpisah dari ketepatan verdict. |

## Integritas dan batas pemeriksaan

Audit mereproduksi matriks sembilan entri/45 field dan memeriksa 27 pointer
rentang sumber yang diwarisi. Kelima file snapshot, termasuk lisensi, cocok
dengan source lock. Sebanyak 1.051 file yang dilindungi tetap sama terhadap
baseline review, termasuk 959 sumber formal dan enam file indeks aktif.

Empat dari enam file indeks aktif juga sama dengan receipt 17 Oktober.
data_level0.bin dan chroma.sqlite3 sudah berbeda pada awal review ini.
Riwayat pemulihan indeks sebelum run B tercatat dalam
[progres formal](progress-2026-10-19.md#perbaikan-yang-diterapkan).
Review ini hanya membaca hash file, tidak membuka Chroma atau memulihkan indeks,
dan tidak menetapkan bahwa isi dokumen/vector berubah dari perbedaan byte itu.

Checker awal keliru mensyaratkan seluruh byte indeks aktif identik dengan
receipt lama untuk melanjutkan review isi. Kegagalan tersebut diperbaiki dengan
memisahkan perbandingan historis dari preservasi selama review. Baseline awal
tetap utuh; perubahan checker dicatat pada review-checker-revision.json.

Tidak ada inferensi, embedding ulang, request DVWA, modifikasi korpus/index,
atau perhitungan ulang FPR/PSR. Pemeriksaan mekanis memastikan keterlacakan;
ketepatan interpretasi sumber tetap merupakan penilaian editorial yang dapat
direview peneliti. Temuan ini tidak menjelaskan secara kausal hasil sama A/B v4.

## Arah perbaikan berikutnya

1. Buat versi baru dengan provenance per field: parafrasa sumber, sintesis
   editorial dan aturan operasional proyek ditandai eksplisit.
2. Perjelas scope hasil kandidat pada entri boolean dan rapikan pointer yang
   mendukung field analisis. Pertahankan snapshot formal/v4 untuk audit.
3. Nilai relevansi terhadap tugas verifikasi pada query baru. Jika menggunakan
   worked examples, tandai sebagai contoh sintetis metode proyek dan pisahkan
   dari label evaluasi serta hasil formal yang sudah diketahui.
4. Bekukan perubahan dan evaluasi pada bukti HTTP baru. Klaim mentah model tetap
   keluaran utama; verifier tetap audit sekunder. Laporkan abstention dan coverage.

Langkah di atas merupakan rekomendasi pengembangan, belum perubahan korpus atau
bukti peningkatan RAG. Instruksi verifikasi arsip ada pada
[README hasil review](../results/processed/analysis-rag-corpus-review-20261019/README.md).
