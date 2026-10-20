# U06: pilot terpadu dan baseline ZAP aktif

Tanggal eksekusi: 14 Oktober 2026. Dataset berstatus pilot dan memakai satu
replikasi, seed 42. Protokol tetap berstatus `pilot`; pekerjaan ini bukan
eksekusi formal.

## Pilot terpadu

Plan `u06-integrated-pilot-20261014` menjadwalkan A/B pada S1-S12 dan C pada
S1-S9, sesuai urutan protokol. Ledger memuat 36 slot: 33 applicable dan tiga
slot C/S10-S12 yang memang tidak berlaku. Semua 33 attempt applicable berakhir
normal dari sisi runner. Tidak ada attempt invalid.

| Kondisi | Run dicoba | Budget penuh 10/10 | Kandidat valid | Slot kandidat tidak terpenuhi | Request HTTP | Durasi attempt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A, RAG off | 12 | 3 | 64 | 56 | 1.395 | 42,3 menit |
| B, RAG on | 12 | 3 | 52 | 68 | 1.029 | 32,3 menit |
| C, SecLists | 9 | 9 | 90 | 0 | 2.004 | 4,4 menit |
| Total | 33 | 15 | 206 dari 330 | 124 | 4.428 | 79,1 menit |

Kandidat yang masuk ke batch akhir tidak duplikat. Namun selama generasi A/B,
audit mencatat 65 keluaran duplikat dan 5 kandidat invalid; setelah retry,
masih ada 124 slot kandidat yang tidak terpenuhi. Delapan belas attempt A/B
berakhir dengan budget kurang, sembilan per kondisi. Run incomplete tetap
dicatat dan dikeluarkan dari metrik. Kondisi C menyelesaikan 9/9 run. Durasi
attempt median 94,6 detik, minimum 5,2 detik, maksimum 439,1 detik. Direktori
pilot memakai 11.507.977 byte. Durasi ini menghitung rentang ledger attempt,
bukan waktu persiapan atau analisis lanjutan.

Loader memvalidasi 36 record dari ledger, snapshot plan/protokol, serta hash
artefak. Audit U05 tanpa anotasi U06 disimpan di
`results/raw/u06-integrated-pilot-audit-20261014/eligibility.json` dan `.csv`.
PSR dan FPR berstatus tidak eligible. PSR menunggu anotasi lengkap VAL-01 pada
run positif; FPR belum memiliki coverage lengkap atas seluruh run Impossible.
Tidak ada hasil pilot yang dilaporkan sebagai angka metrik final.

## Recovery attempt

Rehearsal pertama (`u06-recovery-interrupt-20261014`) selesai normal dengan
9/10 kandidat dan tidak menjadi uji interupsi. Rehearsal kedua memakai
`u06-recovery-r2-20261014`, kondisi A/S7. Proses dihentikan ketika attempt
pertama masih berjalan. Ledger mencatat `attempt_invalid` dengan kode
`orchestrator_interrupted`, `attack_failure=false`, dan `state_reused=false`.

Retry membuat `attempt-2-ee3230bd50` yang merujuk ke attempt pertama, meminta
login baru, dan mencatat `database_reset_performed=true`. Retry hanya
menghasilkan 1/10 kandidat, sehingga run berstatus excluded karena
`incomplete_candidate_budget`. Pemanggilan resume berikutnya tidak menambah
event. Ledger tetap delapan baris dengan SHA-256
`5fcfbb9aabf35607cbfe1e0d6a284f5a98e268939175c44b25dd8a91d2b8ff78`.

Uji recovery membuktikan pemisahan gangguan runtime dari hasil serangan,
provenance attempt baru, reset, dan perilaku resume no-op. Uji ini tidak
membuktikan bahwa retry mampu menyelesaikan budget kandidat.

## Baseline ZAP aktif

Template `dvwa/zap-active-sqli.template.yaml` dan runner
`dvwa/run_zap_active_baseline.ps1` membuat sesi ZAP baru per level. Scope
dibatasi ke halaman SQLi DVWA dan helper High. Semua rule aktif dimatikan secara
default; kebijakan hanya mengaktifkan rule 40018 dan 40019 pada strength Low,
threshold Low, satu thread per host, jeda 100 ms, serta batas waktu per rule dan
scan. Rule 40018 adalah scanner SQLi generik untuk teknik error-based,
boolean-based, Union, dan stacked. Rule 40019 menguji time-based SQLi khusus
MySQL. Karena 40019 sensitif terhadap waktu, jumlah thread dijaga minimum sesuai
[dokumentasi rule aktif ZAP](https://www.zaproxy.org/docs/desktop/addons/active-scan-rules/).

Tes Automation Framework memeriksa level DVWA, autentikasi, dan statistik
request per rule. Autocheck lulus untuk konfigurasi empat level. Uji berjalan
menunjukkan:

| Level | Level dan autentikasi | Request rule 40018 / 40019 | Alert SQLi | Coverage koordinat terverifikasi | Status |
| --- | --- | ---: | ---: | ---: | --- |
| Low | Lulus | 26 / 17 pada run final | 1 | 1 dari 2, GET `/vulnerabilities/sqli/` | Parsial |
| Medium | Lulus | 32 / 20 | 0 | 0 dari 2 bertag | Rule berjalan; atribusi rute belum terbukti |
| High | Lulus | 34 / 18 | 0 | 0 dari 2 bertag | Rule berjalan; atribusi rute belum terbukti |
| Impossible | Lulus | 28 / 24 | 0 | 0 dari 2 | Request ada, lokasi spesifik belum terverifikasi |

Run Low sebelumnya yang tidak memiliki request scanner disimpan sebagai
iterasi gagal dan tidak dipakai sebagai hasil akhir. Pada run final, summary
menemukan satu alert rule 40018 pada koordinat SQLi GET, sementara titik blind
tidak mendapat bukti coverage per-koordinat. Impossible tidak menghasilkan
alert, tetapi cakupan tiap koordinat belum terverifikasi. Karena itu, ketiadaan
alert di Impossible belum boleh disimpulkan sebagai bukti aman.

Pemindaian Medium/High pertama pada URL endpoint selesai tanpa request rule.
Dokumentasi ZAP menyebut job `activeScan` memilih subtree URL, sedangkan
`requestor` mengirim request dengan method dan body khusus. Saya mengubah job
agar memilih seluruh URL dalam context yang sudah dibatasi rute DVWA. Uji
ulang menghasilkan 32/20 URL-rule pada Medium dan 34/18 pada High, lalu
berhenti pada batas lima menit sesuai konfigurasi. HAR berisi request POST
dengan parameter input yang diharapkan: masing-masing 5 pada dua rute Medium,
serta 5 dan 3 pada helper High. Namun HAR follow-up itu tidak memiliki header
`X-ZAP-Scan-ID`; request tersebut bisa berasal dari seed atau spider. Karena
itu, status scanner-tagged coverage tetap 0/2 untuk kedua level dan hasil
alert kosong belum ditafsirkan sebagai bukti aman. Lihat [job activeScan ZAP](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-ascan/)
dan [job requestor ZAP](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-requestor/).

HAR dan report final ada di `results/zap/` dan diabaikan Git karena HAR memuat
session traffic. Ringkasan yang disanitasi ada di
`results/raw/u06-zap-active-baseline-20261014/`; detail hash dan status ada di
evidence U06.

## Paket review dan kesimpulan gate

Paket blind U06 berisi empat kandidat contoh di
`results/raw/u06-validator-review-sample-20261014/validator/`. Public packet
tidak memuat label kondisi, sumber, atau klaim sistem. Mapping privat disimpan
terpisah. Belum ada anotasi U06 dari VAL-01, sehingga paket ini menunggu review
dan tidak dipakai untuk agregasi.

## Preflight perbaikan generator

Audit kode menunjukkan guidance keragaman sebelumnya hanya diterapkan pada
S1. Prompt diperluas ke profil per probe kind dan prompt version dinaikkan ke
`sqli-adaptive-candidate-v11-technique-aware-loop`. Suite offline lulus 158
tes. Preflight lokal memanggil Qwen dan RAG, tetapi tidak mengirim request ke
DVWA dan tidak mengubah pilot U06.

Preflight kondisi A/B pada S2-S4 mencapai budget 10/10 untuk lima dari enam
kombinasi. A/B S2 Boolean dan S4 error-based lengkap, begitu juga A/S3
time-based. B/S3 hanya menghasilkan 6/10 kandidat unik setelah 11 panggilan
generasi. Perluasan profil time-based dari 8 menjadi 16 tidak mengubah hasil
B/S3 pada pengulangan terfokus: tetap 6/10 dengan lima duplikasi. Rincian tanpa
payload ada di `results/raw/u06-generation-preflight-20261014/`.

Jadi guidance teknik sudah membantu cakupan prompt, tetapi belum menutup
duplikasi time-based dengan RAG. Preflight ini bukan dataset eksperimen dan
tidak boleh digabungkan ke pilot. U06 tetap parsial; generator memerlukan
perbaikan lanjutan dan pengulangan pilot dengan snapshot serta experiment ID
baru.

### Diagnosis terkontrol B/S3, 14 Oktober 2026

Diagnosis lanjutan memakai `qwen2.5:7b`, temperature 0, opsi protokol yang sama,
dan dua chunk retrieval B/S3 yang sama. Tidak ada request ke DVWA. Hasil hanya
disimpan sebagai hash kandidat/prompt dan metadata di
`results/raw/u06-generation-diagnostic-20261014/matched-rag-on-off-summary.json`;
teks model dan nilai kandidat tidak disalin ke ringkasan ini.

Pada rekonstruksi prefix v11, RAG menghasilkan lima kandidat unik dalam delapan
panggilan lalu mencapai batas retry untuk slot berikutnya. Tiga pasangan
counterfactual memakai attempted list, slot, seed, dan opsi model yang sama;
pasangan hanya berbeda pada ada/tidaknya retrieved context. Pada pasangan
pertama, kedua kondisi mengulang kandidat lama. Pada dua pasangan berikutnya,
RAG-on mengulang kandidat lama, sedangkan RAG-off menghasilkan kandidat unik
baru yang sama pada kedua pasangan. Ini sinyal kuat untuk memeriksa efek
retrieval terhadap anchoring, tetapi enam panggilan counterfactual ini belum
merupakan bukti kausal atau hasil eksperimen formal.

Isi kedua chunk menjelaskan teknik yang relevan, tetapi juga memberi empat
contoh payload yang semuanya memakai pola IF/SLEEP dan delay 3 detik. Batas
generator saat ini mengizinkan maksimal 2 detik. Contoh yang seragam dapat
mendorong model mengulang keluarga bentuk yang sama, sedangkan delay contoh
melampaui batas prompt. Perluasan profil sintaks v11 sendiri belum cukup
mengatasi konflik konteks ini. Pilot B/S3 yang tercatat sebelumnya memakai
prompt v10 dan berhenti pada 2 kandidat unik; angka pilot tersebut tetap
terpisah dari diagnosis v11 ini.

Langkah koreksi berikutnya adalah menyiapkan snapshot knowledge base kandidat
yang mempertahankan penjelasan mekanisme dan kontrol pengukuran, tetapi tidak
menyuntikkan contoh payload di luar batas eksperimen. Tinjau ulang snapshot
tersebut, jalankan preflight generation-only A/B untuk S3, lalu bekukan versi
prompt dan corpus sebelum attempt pilot baru. Jangan menimpa ledger atau hasil
pilot lama.

Snapshot kandidat review sudah disiapkan terpisah di
`results/raw/u06-generation-diagnostic-20261014/candidate-sqli-entries-s3-review.json`.
Semua contoh timing dibatasi ke satu detik, dan entry pengukuran berulang memakai
bentuk CASE yang berbeda dari entry IF. Snapshot disimpan sebagai salinan
terpisah dari corpus aktif. Saat preflight seed 42, status review-nya masih
`pending`. Setelah peneliti
menyetujui snapshot untuk preflight generation-only, statusnya dicatat sebagai
`reviewed` dengan batas penggunaan yang sama. Keputusan tersanitasi ada di
`results/raw/u06-generation-diagnostic-20261014/candidate-corpus-review-decision.json`.
Persetujuan ini bukan izin penggunaan pada eksperimen formal. Indeks aktif dan
pointer lokal tidak berubah.

Preflight generation-only S3 dengan seed 42 menghasilkan:

| Lengan | Kandidat unik | Panggilan generasi | Lengkap 10/10 |
| --- | ---: | ---: | --- |
| A, RAG off | 10/10 | 16 | Ya |
| B, corpus aktif | 6/10 | 12 | Tidak |
| B, corpus kandidat review | 10/10 | 14 | Ya |

Corpus kandidat menurunkan duplikasi B dari enam menjadi empat dan mencapai
budget 10/10 pada preflight ini. Hasil tersebut mendukung hipotesis bahwa contoh
RAG aktif yang seragam dan melebihi batas durasi ikut mengganggu keragaman
generasi. Namun, ini satu preflight lokal, bukan bukti formal atau jaminan
replikasi. Satu keluaran A juga ditolak oleh validasi kandidat; tidak ada
kandidat atau teks model yang disimpan dalam ringkasan. Tidak ada request ke
DVWA. Hash corpus, model, prompt, seed, chunk retrieval, dan event tersanitasi
tersedia di `results/raw/u06-generation-diagnostic-20261014/`.

Pengulangan dengan seed preflight baru 45 memberi hasil yang sama: A mencapai
10/10 dengan 16 panggilan, B dengan corpus aktif berhenti di 6/10 setelah 12
panggilan, dan B dengan corpus kandidat mencapai 10/10 setelah 14 panggilan.
Corpus kandidat menghasilkan empat duplikasi; corpus aktif menghasilkan enam.
Satu kandidat A kembali ditolak oleh validasi. Ringkasan seed 45 dan hash
keputusan review tersimpan di `candidate-corpus-preflight-seed-45-summary.json`.
Seed 45 dipilih di luar seed replikasi protokol 42, 43, dan 44 agar preflight
tetap terpisah dari replikasi pilot.

Keragaman penuh 10/10 kini terulang pada dua seed preflight. Sebelum kandidat
corpus dipakai pada pilot baru, bekukan snapshot, prompt, dan manifest sebagai
versi eksperimen baru, lalu buat experiment ID dan ledger baru. Jangan mengubah
data U06 lama atau mengalihkan pointer indeks aktif sebelum persiapan versi baru
direkam.

### Rencana pilot S3 dengan corpus kandidat

Experiment ID baru adalah `u06-s3-candpilot-20261014`, dengan dua unit
`A/S3/r1` dan `B/S3/r1`, seed 42, dan budget 10 kandidat. Run plan ada di
`dvwa/local_run_plan.u06-s3-candidate-pilot-20261014.json`. Discovery memakai
report Low terverifikasi dari 14 Oktober yang dinormalisasi offline dari HAR dan
report ZAP yang sama; inventaris memverifikasi koordinat GET `id` S3 dalam sesi
terautentikasi. Ini bukti koordinat input, bukan temuan atau ground truth SQLi.

Plan mengunci hash manifest, corpus, dan keputusan review. Runner kini mengirim
manifest tersebut hanya untuk kondisi B, mempertahankan A tanpa akses vector
store, dan menolak eksekusi jika hash berubah. Tes juga memastikan persetujuan
preflight saja tidak membuat ledger atau memulai run pilot.

Plan lolos validasi schema dan menghasilkan dua unit dengan discovery SHA yang
sama. Peneliti menyetujui penggunaan snapshot untuk pilot U06 S3 ini; keputusan
review dan hash yang dipatok pada plan telah diperbarui. Persetujuan ini khusus
pilot dan bukan persetujuan eksperimen formal. Docker/DVWA lokal serta Ollama
kemudian terkonfirmasi aktif, dan runner mereset database sampel sebelum setiap
condition-run.

### Hasil pilot S3 dengan corpus kandidat

Pilot `u06-s3-candpilot-20261014` dijalankan berurutan pada 14 Oktober 2026.
Ledger baru mencatat kedua unit sebagai `excluded` karena budget kandidat tidak
terpenuhi. Setiap kandidat yang dihasilkan tetap menjalani tiga konfirmasi
sesuai protokol; data parsial dipertahankan untuk audit, tetapi tidak masuk
perhitungan metrik.

| Kondisi | Kandidat unik dari 10 | Event generasi | Duplikat | Kandidat invalid | Logical probe submissions | HTTP request | Durasi | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A, RAG off | 3 | 9 | 5 | 1 | 27 | 70 | 4 menit 02 detik | Excluded, incomplete budget |
| B, corpus kandidat | 4 | 11 | 7 | 0 | 36 | 91 | 3 menit 23 detik | Excluded, incomplete budget |

Kedua unit mencatat nol `confirmed_success`, tetapi hasil itu tidak boleh
dibaca sebagai bukti bahwa injection point aman. Angka A/B tidak eligible untuk
PSR atau FPR, dan tidak ada metrik formal yang dihitung. Pilot ini menunjukkan
bahwa hasil generation-only 10/10 pada seed 42 dan 45 belum menjamin budget
10/10 ketika loop adaptif menjalankan generasi, analisis, dan validasi live.
Durasi gabungan 7 menit 25 detik terutama terjadi saat inferensi dan retry
generasi berjalan sinkron. Qwen tersedia dan tidak ada kegagalan layanan model;
run berhenti karena `generation_exhausted` setelah duplikasi dan penolakan
kandidat menghabiskan kesempatan pengisian slot. Setiap reset dan login lokal
berhasil, sehingga penyebab eksklusi bukan target yang tidak tersedia.
Ledger berisi sembilan event dan SHA-256
`e2275f14f00901fb77474532974d9e2700eae2898b209ec33edf3f94cb371bc4`.
Loader memverifikasi urutan event dan hash batch, validation log, serta artefak
analisis. Detail mentah tetap berada di direktori hasil lokal yang diabaikan
Git.

U06 mencakup pilot terpadu, audit metrik, sampel review, serta bukti recovery.
Baseline ZAP aktif masih parsial dan masalah budget generator A/B belum
tertutup. U06 belum memenuhi syarat selesai penuh dan U07 belum boleh
menyiapkan freeze formal. Perlu perbaikan generator untuk menyelesaikan 10
kandidat per run, serta atribusi scanner per koordinat input POST, session, dan
cookie pada ZAP. Perubahan tersebut harus memakai snapshot serta experiment ID
baru; jangan mengubah ledger U06 yang sudah ada.

### Follow-up 16 Oktober 2026

Perubahan berikut memakai prompt, plan, dan evidence terpisah. Ledger pilot
14 Oktober tidak diubah. Semua pilot S3 tetap memakai protokol v5, seed 42,
budget 10, maksimum dua retry generasi per slot, tiga konfirmasi, reset
database per condition-run, serta corpus kandidat yang sama dengan hash
`d38499f68f5a6530cd87e35d54c83242aa09f650d7c666dc2e686300d36659e2`.
Decision receipt masing-masing run hanya mengizinkan pilot, bukan penggunaan
formal.

| Experiment ID | Prompt | A unik | B unik | Duplicate generation attempts A/B | Confirmed success A/B | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `u06-s3-candpilot-v12-20261016` | v12 hard slot diversity | 2/10 | 2/10 | 3 / 3 | 1 / 0 | Keduanya excluded |
| `u06-s3-candpilot-v13-20261016` | v13 duplicate retry novelty | 3/10 | 2/10 | 4 / 3 | 2 / 0 | Keduanya excluded |

Tidak ada run yang mencapai budget. Bukti positif kandidat pada A tetap
observasi pilot, bukan hasil eligible untuk FPR/PSR. B menggunakan retrieval
dan memuat dua chunk pada kedua iterasi. Artefak lengkap, termasuk ledger,
audit generasi, hasil adaptif, hash plan, dan approval pilot, disimpan di
`results/raw/pilot/u06-s3-candpilot-v12-20261016/` dan
`results/raw/pilot/u06-s3-candpilot-v13-20261016/`. Instruksi retry v13
meningkatkan A satu kandidat pada pilot ini, tetapi tidak memperbaiki B dan
belum cukup untuk menyatakan budget generator stabil. Temperature protokol v5
tetap 0; perubahan temperatur memerlukan versi protokol dan snapshot baru.

### Baseline ZAP aktif v2 dan pemeriksaan terarah v3

Plan ZAP diperbarui untuk memasukkan attribution `X-ZAP-Scan-ID` dan
mengaktifkan input vector query, POST, dan cookie. Empat plan v2 lolos
autocheck dan active scan hanya memakai dua rule SQLi pada DVWA lokal. Hasil
coverage dari report, HAR, log, dan plan yang di-hash:

| Level | Koordinat teratribusi | Request ber-header scan ID | Statistik rule 40018 / 40019 | Interpretasi |
| --- | ---: | ---: | ---: | --- |
| Low | 1/2 | 1 | 86 / 27 | Hanya GET `id` pada endpoint SQLi utama terverifikasi |
| Medium | 0/2 | 0 | 46 / 32 | POST `id` seed terlihat; coverage scanner belum terbukti |
| High | 0/2 | 0 | 48 / 30 | Helper session dan cookie belum teratribusi |
| Impossible | 0/2 | 0 | 88 / 66 | Dua koordinat GET belum teratribusi |

Ringkasan yang tersanitasi dan artefak lokal ada di
`results/raw/u06-zap-active-baseline-v2-20261016/`. Active Scan job v3
kemudian diuji dengan URL endpoint Medium yang eksplisit. Request rule turun
menjadi 14 dan 12 URL, tetapi attribution tetap 0/2. Percobaan pertama dengan
subtree `/vulnerabilities/` gagal karena URL itu tidak ada pada Sites Tree;
log kegagalan dipertahankan. Plan High dengan dua helper endpoint lolos
autocheck, tetapi belum dijalankan dalam v3.

ZAP Automation Framework menerima `url` subtree pada activeScan job, sedangkan
API active scan menyediakan parameter `method` dan `postData`. Karena request
POST saat ini belum teratribusi, tindak lanjut yang terukur adalah menjalankan
API tersebut secara eksplisit untuk request POST, merekam scan ID per
koordinat, kemudian mengulang matrix empat level sebelum menafsirkan alert.
Lihat [dokumentasi activeScan job](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-ascan/)
dan [API ZAP](https://www.zaproxy.org/docs/api/).

### U06 API eksplisit untuk GET dan POST, 16 Oktober 2026

Runner baru memanggil Automation Framework untuk autentikasi dan setup level,
lalu menjalankan `ascan.scanAsUser` dengan method dan input eksplisit. Untuk
Medium/High, request memakai `method=POST` dan `postData=id=1&Submit=Submit`;
jalur GET Low/Impossible membawa `id=1&Submit=Submit` pada URL. API
`optionInjectPluginIdInHeader` diaktifkan dan diverifikasi sebelum active scan.
HAR lokal menjadi sumber pemeriksaan
header `X-ZAP-Scan-ID`; ringkasan juga mencocokkan koordinat, metode, parameter,
dan rule ID. API key dibuat sementara di proses runner, diwariskan ke container,
dan tidak ditulis ke evidence. API tidak mempublikasikan port ke host.

| Level | Koordinat bertanda rule 40018/40019 | URL pada statistik ZAP, rule 40018 / 40019 | Request HAR bertanda, rule 40018 / 40019 | Alert SQLi | Status coverage |
| --- | ---: | ---: | ---: | --- | --- |
| Low | 2/2 GET `id` | 40 / 29 | 41 / 29 | Satu instance rule 40018 pada `/vulnerabilities/sqli/` | Terverifikasi |
| Medium | 2/2 POST `id` | 47 / 34 | 96 / 68 | Satu instance rule 40018 pada `/vulnerabilities/sqli/` | Terverifikasi |
| High | 2/2 POST `id` | 42 / 36 | 42 / 36 | Tidak ada | Terverifikasi untuk dua helper target |
| Impossible | 2/2 GET `id` | 49 / 42 | 49 / 42 | Tidak ada | Terverifikasi |

Low dan Impossible menguji `/vulnerabilities/sqli/` serta
`/vulnerabilities/sqli_blind/` dengan GET. Medium menguji dua endpoint yang
sama dengan POST. High menguji `/vulnerabilities/sqli/session-input.php` dan
`/vulnerabilities/sqli_blind/cookie-input.php` dengan POST. Semua setup plan
memverifikasi auth dan level, seluruh active scan selesai dengan status 100%,
dan coverage 2/2 tercatat pada tiap level. Alert kosong pada High dan Impossible
hanya merupakan hasil negatif untuk koordinat yang dicakup dalam sesi dan
policy pilot ini, bukan bukti keamanan umum.

Artefak plan, report, dan HAR bertimestamp ada di `results/zap/`: Low
`low-20261016-161236`, Medium `medium-20261016-153313`, High
`high-20261016-155022`, dan Impossible `impossible-20261016-161855`. API evidence
dan ringkasan tersanitasi ada di `results/raw/u06-zap-api-explicit-20261016/`.
HAR disimpan lokal karena berisi lalu lintas sesi DVWA. Runner dan summarizer
baru menambahkan hash source ke snapshot eksperimen berikutnya; snapshot lama
tidak diubah.

U06.2 selesai untuk matrix empat level dan koordinat katalog yang diuji. Pada
snapshot follow-up API ini, U06.1 masih menunggu pilot baru.

### Follow-up U06.1, 16 Oktober 2026

Investigasi audit v13 menemukan bahwa beberapa retry tetap mengembalikan
kandidat yang sama. Perubahan v14 meminta tiga opsi per panggilan dan memilih
satu opsi unik untuk tiap slot. Hasil `u06-s3-candpilot-v14-20261016` adalah
A 10/10 dan B 8/10; B tetap incomplete dan excluded.

Prompt v15 kemudian meminta sepuluh opsi per panggilan untuk skenario selain
S1, memvalidasi seluruh opsi, lalu hanya memilih opsi valid pertama yang belum
pernah dicoba. Kandidat yang dipilih tetap satu per slot sehingga budget
eksekusi tetap 10. Batas retry tetap 2 dan temperature tetap 0. Experiment ID
`u06-s3-candpilot-v15-20261016` memakai S3 replicate 1 dan hash corpus kandidat
yang sama dengan v14, `d38499f68f5a6530cd87e35d54c83242aa09f650d7c666dc2e686300d36659e2`.

| Arm | Kandidat unik | Analisis selesai | Duplikat generasi | Kandidat invalid runtime | Retrieved chunks | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A, RAG off | 10/10 | 10/10 | 2 | 0 | 0 | Budget lengkap |
| B, RAG on | 10/10 | 10/10 | 3 | 0 | 2 | Budget lengkap |

Semua event generasi meminta 10 opsi. Audit mencatat prompt versi
`sqli-adaptive-candidate-v15-batch-option-dedup`, seluruh regenerasi, dan profil
struktur identik pada urutan A/B. Kedua run menyelesaikan budget dalam batas
retry dan dapat dipakai sebagai keputusan pilot; hasilnya bukan metrik formal.
Run v12, v13, serta B/v14 tetap excluded. Artefak v14 dan v15, termasuk ledger,
plan snapshot, audit generasi, validation log, serta ringkasan run, disimpan di
`results/raw/pilot/u06-s3-candpilot-v14-20261016/` dan
`results/raw/pilot/u06-s3-candpilot-v15-20261016/`. Receipt v15 mencatat
otorisasi pilot lokal dan secara eksplisit tidak menyetujui eksperimen formal.

Dengan hasil ini, U06.1 selesai untuk pasangan S3 replicate 1 yang direncanakan.
U06.3 kemudian dijalankan kembali pada 16 Oktober dengan plan dan snapshot baru
`u06-v15-integrated-20261016`, 33 run applicable A/B/C, budget 10, serta tiga
slot C/S10-S12 yang tidak berlaku.

### Hasil pilot terpadu v15, 16 Oktober

Ledger final memiliki 36 slot: 28 completed, lima excluded karena incomplete
candidate budget, tiga slot C/S10-S12 yang tidak berlaku, dan nol invalid.
Semua 33 run applicable memiliki attempt serta provenance yang lolos loader.
Matriks budget:

| Kondisi | Applicable | Completed | Excluded budget | Rincian incomplete |
| --- | ---: | ---: | ---: | --- |
| A, LLM tanpa RAG | 12 | 10 | 2 | S1 8/10; S10 9/10 |
| B, LLM dengan RAG | 12 | 9 | 3 | S3, S6, S9 masing-masing 8/10 |
| C, SecLists | 9 | 9 | 0 | Tidak ada |

Sebanyak 19/24 run LLM mencapai 10/10. Seluruh 231 kandidat LLM yang sempat
dijalankan memiliki analisis selesai; tidak ada runtime-invalid. Audit generasi
mencatat 255 panggilan model, 24 langkah retry, 465 opsi duplikat, 1.640 opsi
unik yang tidak dipilih karena setiap slot hanya memakai satu opsi, dan 16
opsi invalid yang ditolak sebelum dieksekusi. Kontrol SecLists menyelesaikan 90
kandidat pada C/S1-S9. Loader memverifikasi 321 kandidat dan 2.568 observasi,
termasuk record dari run incomplete yang tetap dikecualikan dari metrik.
Rentang eksekusi berurutan 3 jam 54 menit.

Pada skenario negatif S10-S12, keputusan sistem A berurutan tidak evaluable,
positif, positif; B inconclusive, positif, positif. Hasil ini hanya observasi
pilot. Setelah paket dikembalikan VAL-01, dua baris CSV diperbaiki dalam salinan
tanpa mengubah file asli. Keempat anotasi lolos validasi dan berhasil diimpor:
dua `failure`, satu `insufficient_evidence`, dan satu `success`. Keputusan
selaras dengan bukti paket, tetapi sampel ini hanya menguji alur review.

Agregator tetap menahan PSR dan FPR. Nol dari 18 baris run PSR memiliki
coverage anotasi penuh; nol dari enam replikasi FPR memiliki coverage formal
penuh. Tidak ada FPR atau PSR formal yang dihitung. Hasil impor dan audit pilot
tersimpan di `results/raw/u06-v15-integrated-review-sample-20261016/` dan
`results/raw/pilot/u06-v15-integrated-20261016/`. Perbaikan hash importer
menangani perbedaan CRLF pada Windows. Ringkasan dan hash run ada di
[evidence pilot v15](evidence/u06-v15-integrated-pilot-2026-10-16.json).

### Paket blind U06.4

Paket empat kandidat baru untuk eksperimen v15 siap direview VAL-01 di
`results/raw/u06-v15-integrated-review-sample-20261016/validator/`. Readiness
adalah `ready_for_pilot_review`; packet tidak memuat label kondisi, sumber,
ground truth, maupun klaim sistem. Hash packet:
`0430c09924409ce536129cd1d17c007a899d953c558df5d764cc39621e09e77e`.
Bagikan hanya folder `validator/`, bukan mapping atau metadata privat di folder
induk. Audit pra-anotasi tersedia bersama ledger di
`results/raw/pilot/u06-v15-integrated-20261016/`. Review VAL-01 kini telah
diimpor dan agregator telah diaudit. U06.4 selesai untuk validasi alur pilot;
U07 belum dimulai dan eksperimen formal belum dilakukan.
