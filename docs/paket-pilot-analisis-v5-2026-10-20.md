# Paket pilot analisis v5 sebelum inferensi

Paket ini mengoperasionalkan enam prasyarat eksekusi untuk A/B2/B3. Ini adalah
pilot development dengan fitur respons sintetis buatan AI, bukan rekaman
HTTP DVWA baru atau holdout independen. Label dan korpus masih memiliki review
peneliti pending. Pembuatan paket dan tes offline tidak menjalankan evaluasi
keputusan Qwen. Data serta protokol formal R1/R2/R3 tetap dipertahankan.

## Kasus, komposisi, dan label

Ada 42 ID tetap, pilot-001 sampai pilot-042. Sebanyak 36 kasus eligible terdiri
dari 12 per teknik SQLi: empat referensi positive, empat negative, dan empat
inconclusive. Enam kasus lainnya menguji gate, masing-masing satu runtime
invalid dan satu baseline invalid per teknik. Gate tersebut mencakup baseline
yang memuat diagnostik meskipun pasangan kandidat tampak positif.

Inconclusive mencakup satu trial positif, dua trial positif, pasangan trial
1 dan 3 yang positif, serta pasangan 1 dan 2 yang negatif. Kasus teknik
menguji identifier diagnostik dan HTTP error tanpa diagnostik; arah marker,
status, serta diagnostik pada pasangan boolean; kontrol timing yang lambat,
marker tidak cocok, diagnostik kontrol, delta negatif, ambang tepat 1500 ms,
dan delta 1499,8 ms tanpa pembulatan.

Label berada pada labels.ai.lock.json dan tabel review terpisah. Prompt,
query retrieval, dan request hanya menerima fitur terukur. Label dibangun
menurut kontrak yang telah ada dan diperiksa terhadap fungsi kontrak pada
paket ini. Kesepakatan ini menguji implementasi, bukan validasi manusia.
Kesamaan tujuan dengan kasus development lama tetap ada. Perbedaan ID atau
angka tidak membuktikan kebaruan ilmiah atau independensi.

## Jadwal dan batas perbandingan

Setiap kasus mempunyai tiga slot profil. Keenam permutasi A/B2/B3 digunakan
dua kali per teknik eligible, dengan seed 20261020, lalu urutan kasus diacak
secara deterministik. Tiap profil menempati posisi 1, 2, dan 3 masing-masing
12 kali pada kasus eligible, serta dua kali pada gate cases. Total 126 slot:
108 panggilan model yang direncanakan dan 18 skip sebelum model.

A tidak menerima referensi. B2 menggunakan dua chunk pertama dari ranking
Nomic yang dibekukan. B3 menggunakan ketiga chunk eligible. Query lama boleh
dipakai ulang karena technique dan injection point persis sama, dan query
tidak melihat respons ataupun label. B3 merupakan konteks teknik lengkap;
hasil A/B3 tidak membuktikan bahwa selektivitas ranking meningkatkan kinerja.

## Kesamaan request dan pemeriksaan konteks

Seluruh 126 request aktual disimpan sebelum inferensi. Audit memeriksa
model, options, schema, system prompt, serta seluruh measured_evidence
identik untuk ketiga profil pada setiap kasus. Hanya reference_context yang
berbeda. Hash komponen, request lengkap, urutan, serta hash versi renderer
dan dependensinya diikat dalam manifest.lock.json.

Tokenizer Qwen yang sudah diverifikasi terhadap model terpasang menghitung
ulang seluruh request aktual, termasuk template ChatML dan awalan assistant.
Cadangan output tetap 768 token pada num_ctx 4096. Kelebihan satu request
membatalkan seluruh pengiriman sebelum panggilan pertama. Bukti dan chunk
tidak dipotong. Nilai margin baru berada pada readiness-summary.json dan
request-audit.lock.json; margin probe lama tidak dipakai sebagai jaminan.

Pada eksekusi eksplisit, runner memeriksa ulang hash, input, request, token,
versi library, digest Qwen, template, konfigurasi model, dan versi Ollama.
Setiap respons harus melaporkan prompt_eval_count yang persis sama dengan
hitungan lengkap offline. Ketidakcocokan dicatat sebagai analysis error,
lalu sesi dihentikan. Pemeriksaan ini tetap diperlukan karena hitungan
offline bukan pengamatan runtime pada kasus pilot yang belum dijalankan.
Opsi stop awal dari probe konteks tidak disalin ke pilot.

## Gate, error, dan retry

Input harus lolos schema. Tepat sebelum panggilan model, runner mensyaratkan
runtime_status valid dan baseline_valid true. Input invalid dicatat sebagai
skip dan tidak masuk penyebut akurasi model. Ini berbeda dari input valid
dengan pasangan kandidat yang gagal indikator, yang tetap dinilai model.

Timeout per panggilan adalah 240 detik. Tidak ada retry isi atau transport.
Respons tanpa content, JSON/schema rusak, referensi observasi tidak dikenal,
generation belum selesai, atau output menyentuh batas 768 token merupakan
analysis error. Kasus itu tetap masuk penyebut, dan runner melanjutkan slot
berikutnya untuk error isi. Error transport dicatat satu kali dan menghentikan
sesi; slot berikutnya berstatus belum dicoba, sehingga kesimpulan tidak lengkap.

Runner menyimpan attempt_started ke disk sebelum memanggil API, menyimpan
respons asli sebelum parsing, dan melakukan flush serta fsync setiap event.
Interupsi setelah attempt_started dihitung sebagai interrupted analysis error.
Runner menolak direktori run yang sudah ada, tanpa resume otomatis. Penyebut
yang direncanakan, dicoba, belum dicoba, dan attempt yang belum selesai
ditampilkan terpisah. Keluaran JSONL tetap dipertahankan untuk audit.

Keputusan yang valid secara schema tetap dipakai mentah meskipun hitungan
trial, reason_code, atau citation bertentangan. Ketidaksesuaian tersebut
dicatat sebagai warning. Tidak ada koreksi verdict oleh verifier.

## Metrik dan aturan kesimpulan yang ditetapkan sebelumnya

Metrik utama adalah ketepatan keputusan mentah tiga kelas, A versus B3.
Pembilang adalah jumlah keputusan yang sama dengan referensi kontrak;
penyebut adalah seluruh kasus eligible yang dicoba, termasuk analysis error.
Pada sesi lengkap penyebut setiap profil adalah 36. Inconclusive yang tepat
pada referensi inconclusive mendapat kredit pada akurasi tiga kelas, sehingga
coverage pada referensi binary tetap wajib ditampilkan sebagai pendamping.

Matriks hasil mempunyai tiga baris referensi dan empat kolom: positive,
negative, inconclusive, analysis_error. Pada referensi positive, negative
adalah klaim negatif keliru, sedangkan inconclusive adalah abstention. Pada
referensi negative, positive adalah klaim positif keliru, dan inconclusive
tetap abstention. Analysis error tidak diubah menjadi salah satu keputusan.

Coverage binary adalah proporsi keluaran positive/negative non-error terhadap
semua kasus eligible yang dicoba. Coverage pada subset referensi positive
atau negative juga dilaporkan dengan penyebutnya sendiri. Akurasi trial
menggunakan semua trial yang tersedia pada kasus yang dicoba; error kasus,
trial hilang, atau assessment ganda mendapat nol, tanpa mengurangi penyebut.
Pada sesi lengkap tersedia 102 trial yang dinilai per profil.
Reason-code accuracy, semantic warnings, waktu, token, dan completion
disediakan sebagai pendamping. B2 merupakan perbandingan deskriptif sekunder.

Kesimpulan memerlukan seluruh 108 slot eligible dicoba dan difinalisasi,
tanpa pelanggaran gate. Delta utama adalah accuracy B3 dikurangi A dalam
poin persentase pada 36 pasangan yang sama. Peningkatan deskriptif pada
dataset ini memerlukan delta positif, jumlah positive yang benar tidak
turun, jumlah false positive pada referensi negative tidak naik, coverage
referensi binary tidak turun, serta jumlah analysis error tidak naik.
Delta positif dengan guard yang memburuk diberi hasil tradeoff. Delta nol
atau negatif diberi hasil tidak ada peningkatan akurasi mentah. Sesi yang
tidak lengkap hanya menampilkan statistik percobaan dengan kesimpulan incomplete.
Tidak ada ambang yang disesuaikan setelah hasil terlihat.

Rancangan ini belum mendukung inferensi signifikansi, generalisasi, klaim
manfaat RAG, atau hasil FPR/PSR formal. Metrik proposal tetap FPR untuk ablasi
RAG dan PSR untuk LLM versus SecLists pada eksperimen yang sesuai.

## Artefak review dan penggunaan

- [Tabel 42 kasus dan alasan label](../outputs/analysis-v5-pilot-review/cases.review.md).
- [Ringkasan kesiapan](../results/processed/analysis-v5-pilot-20261020/readiness-summary.json).
- [Protokol terkunci](../results/processed/analysis-v5-pilot-20261020/protocol.lock.json).
- [Manifest path dan SHA-256](../results/processed/analysis-v5-pilot-20261020/manifest.lock.json).
- [Input kasus](../results/processed/analysis-v5-pilot-20261020/inputs.lock.json).
- [Label AI terpisah](../results/processed/analysis-v5-pilot-20261020/labels.ai.lock.json).
- [Seluruh request](../results/processed/analysis-v5-pilot-20261020/prepared-requests.lock.json).
- [Audit token dan kesamaan request](../results/processed/analysis-v5-pilot-20261020/request-audit.lock.json).
- [Jadwal](../results/processed/analysis-v5-pilot-20261020/schedule.lock.json).

Tabel label dan batas kesimpulan menjadi prioritas review peneliti. Jika ada
revisi, buat versi paket baru beserta hash baru sebelum inferensi, tanpa
menulis ulang paket terkunci atau mengganti pending menjadi approved otomatis.

Verifikasi offline, tanpa model atau DVWA:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s development -p test_analysis_v5_pilot.py -v
.\.venv\Scripts\python.exe development/analysis_v5_pilot.py
```

Runner mempunyai opsi --execute yang eksplisit untuk sesi model berikutnya;
pembuatan paket ini tidak menjalankannya. Hasil sesi akan berada di
results/raw/development/analysis-v5-pilot-20261020 dan tidak menimpa manifest.
Opsi --score-saved menghitung ulang event yang sudah tersimpan, termasuk
attempt terinterupsi, tanpa memanggil model.
