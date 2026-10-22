# Runner Qwen API untuk pilot SQLi

Runner ini menghubungkan Qwen API ke ledger eksperimen lokal untuk pilot DAST
black-box pada DVWA. Scope-nya hanya dataset `pilot`, kondisi LLM A/B, dan
payload SQLi error-based, Boolean-based blind, atau time-based blind. Kondisi C
opsional memakai executor SecLists lokal yang sudah ada.

## Versi aktif per 22 Oktober 2026

**Pembaruan terakhir:** runtime aktif `qwen38-api-sqli-v3-pilot` lulus 200 tes
dan replay sembilan checkpoint generasi. Kontrol S1-S12 serta smoke A/B juga
selesai. Pilot v2 berhenti pada S1-A akibat bug status ketika kandidat duplikat
ditolak. Pilot v3 pertama berhenti pada analisis S2-B setelah 45 request; tiga
unit lengkap eligible, satu A/S1 incomplete, satu invalid, tiga slot desain
excluded, dan 28 planned. Cohort recovery baru `qwen38-api-r2-20261022`
kemudian dijalankan selama sekitar 7 menit 18 detik dan berhenti pada analisis
S1-B karena read timeout 90,153 detik. Dari 25 request, 24 sukses dan satu
transport-error. S1-A excluded setelah 8 dari 10 kandidat; S1-B invalid; 31
unit planned dan nol completed. Tidak ada retry. Audit memastikan 1.504 file
historis dan 32 source runtime utuh. Batas enam jam adalah ceiling, bukan
estimasi durasi. Tidak ada hasil PSR/FPR API. Lihat
`docs/p3-recovery-002-results-2026-10-22.md` dan receipt audit terkait.

Dry-run plan v3:

```powershell
.\.venv\Scripts\python.exe development/run_bounded_qwen_p3_pilot.py `
  --plan development/qwen_api_p3_v3_pilot_plan.template.json `
  --budget development/qwen_api_p3_v3_budget_20261022.json
```

Hasilnya bukan evaluasi formal. Persetujuan dan hasil rinci ada di
`docs/evidence/p3-v3-execution-approval-2026-10-22.json`,
`docs/evidence/p3-v3-execution-audit-r2-2026-10-22.json`, dan
`docs/evidence/qwen-api-access-check-post-v3-2026-10-22.json`, serta
`docs/p3-pilot-v3-2026-10-22.md`. Run berikutnya perlu keputusan baru;
budget yang telah dipakai menetapkan nol replacement otomatis.

Cohort tersebut mencakup ulang 33 unit applicable dan dry-run sebelumnya
menghitung 960 request/36 slot. Eksekusinya berhenti sebelum unit eligible
selesai. Jangan resume atau mengganti unit secara otomatis. Setiap run lanjutan
memerlukan ID, plan, budget, dan keputusan eksekusi terpisah. Lihat
`docs/p3-recovery-002-plan-2026-10-22.md` dan
`docs/p3-recovery-002-results-2026-10-22.md`.

Draft lanjutan v4 `qwen38-api-r3-20261022` menambah timeout transport analisis
menjadi 180 detik; timeout generasi tetap 90 detik dan profil P2 tetap tidak
berubah. Perubahan memakai adapter, profile, dan runtime hash tersendiri.
Tiga tes offline serta dry-run bounded lulus, dengan 36 slot dan ceiling 960
request. Belum ada panggilan API/DVWA atau izin eksekusi. Perhatikan juga
risiko loop generasi S1-A yang kehabisan kandidat unik pada recovery-002.
Lihat `docs/p3-timeout180-plan-2026-10-22.md` dan
`docs/evidence/p3-timeout180-preparation-2026-10-22.json`.

### Checkpoint sebelum pilot live v2

Protokol aktif adalah `qwen38-api-sqli-v2-pilot`. P2 sudah ditutup peneliti
dengan satu timeout sebagai keterbatasan. Dua gate analisis P3 diperbaiki dan
profil analisis memakai renderer, parser serta settings P2: 2048 token,
90 detik, temperature 0, tanpa opsi template tambahan. Generasi tetap memakai
profil sebelumnya. Ada 192 tes offline lulus; belum ada pilot live v2.

Gunakan plan dengan experiment ID baru:

```powershell
.\.venv\Scripts\python.exe development/run_qwen_api_experiments.py `
  --plan development/qwen_api_p3_v2_pilot_plan.template.json
```

Ini dry-run 33 run applicable, bukan eksekusi. Tetapkan budget khusus sebelum
memakai `--execute`; ceiling umum 5.760 bukan budget pilot yang otomatis
disetujui. Smoke generasi dan kontrol executor aktual masih perlu dijalankan.

Snapshot lama tidak boleh ditulis ulang agar bisa resume dengan source baru.
Sumber v1 sebelum perubahan diarsipkan dalam
`results/raw/development/p3-repair-20261022-v2/legacy-source/`.
Contoh S1 dan resume pada bagian berikut adalah riwayat v1; reproduksinya
memerlukan source/config v1 yang cocok, bukan runtime aktif v2.

Laporan: `docs/perbaikan-p3-2026-10-22.md`. Audit offline dapat diulang dengan
`maintenance/audit_p3_repairs.py --output-dir results/raw/development/p3-repair-audit-recheck`.

## Pemeriksaan rencana

Template awal menguji kondisi A untuk S1 Low pada satu replikasi:

```powershell
.\.venv\Scripts\python.exe development/run_qwen_api_experiments.py `
  --plan development/qwen_api_pilot_plan.template.json
```

Tanpa `--execute`, runner hanya memvalidasi plan dan menampilkan estimasi. Ia
tidak membuat ledger, memanggil API, melakukan login DVWA, atau mereset database.
Plan memakai laporan discovery ZAP yang telah tercatat.

Paket revalidasi hash dan rekonsiliasi akhir baris per 21 Oktober ada di
`docs/evidence/qwen-api-b-index-revalidation-2026-10-21.md`,
`docs/evidence/qwen-api-b-review-reconciliation-2026-10-21.md`, dan
`docs/evidence/qwen-api-b-review-verification-2026-10-21.md`. Checker aktif
cocok dengan revisi yang tercatat. Audit historis berhasil direproduksi dengan
normalisasi CRLF ke LF di memori saja; baseline dan receipt lama tidak diubah.

Pemeriksaan isi salinan indeks ada di
`docs/evidence/qwen-api-b-index-content-inspection-2026-10-21.md`. Sembilan ID,
dokumen, metadata, konfigurasi koleksi dan vektor cocok dengan arsip acuan;
sembilan query uji juga memberi ranking yang sama. Hash byte
`data_level0.bin` dan `chroma.sqlite3` tetap berbeda, dan laporan mencatat
perbedaannya. Pemeriksaan menggunakan salinan, tanpa mengubah indeks aktif.
Peneliti menyetujui snapshot aktif untuk penggunaan pilot B pada 21 Oktober.
Receipt `docs/evidence/qwen-api-b-pilot-decision-2026-10-21.json` mengikat
korpus, source lock, keenam hash aktif, dan bukti pemeriksaan. Batas byte-level
dan satu baris tambahan `acquire_write` tetap dicatat dalam receipt. Approval
ini hanya untuk pemakaian snapshot dalam pilot, bukan eksekusi langsung.

Plan B untuk S1 dan satu replikasi sudah divalidasi dengan dry-run:

```powershell
.\.venv\Scripts\python.exe development/run_qwen_api_experiments.py `
  --plan development/qwen_api_b_pilot_plan.template.json
```

Estimasi worst-case-nya 40 request API dari batas 5.760. Dry-run mengembalikan
`execution_started: false`; belum ada API atau DVWA yang dipanggil.

## Eksekusi eksplisit

Runner pilot dan P2 membaca API key dengan urutan: environment `HCNSEC_API_KEY`,
file lokal `.env.hcnsec.local` di root proyek, lalu prompt tersembunyi. Simpan
sekali agar tidak perlu mengetiknya pada setiap eksekusi:

```powershell
.\.venv\Scripts\python.exe development/qwen_api_credentials.py --save
.\.venv\Scripts\python.exe development/qwen_api_credentials.py --check
```

Perintah `--save` meminta key melalui input tersembunyi; jalankan lagi untuk
mengganti key. `--check` hanya memeriksa ketersediaan, tanpa menampilkan key
atau menghubungi API. File lokal ini berupa teks biasa, diabaikan Git oleh pola
`**/.env.*`, dan tidak masuk snapshot runtime. Hindari membagikan file tersebut.
Jangan menaruh key di source code, plan, prompt, atau konfigurasi yang dilacak Git.
Skrip smoke historis tetap memakai environment atau prompt seperti sebelumnya.
Perubahan loader dipin untuk run pilot baru; jangan mengganti snapshot lama
untuk meloloskan resume dengan source yang berubah.

```powershell
\.venv\Scripts\python.exe development/run_qwen_api_experiments.py `
  --plan development/qwen_api_b_pilot_plan.template.json `
  --execute --confirm-api-spending --confirm-local-dvwa --confirm-database-reset
```

Template ini memiliki batas worst-case 40 request API: 10 kandidat,
sampai tiga request generasi per slot, dan satu analisis per kandidat. Pemakaian
aktual biasanya lebih rendah karena kandidat yang lolos pada request pertama
tidak perlu regenerasi. Konfigurasi membatasi total 5.760 request per direktori
eksperimen, output generasi 1.024 token, output analisis 2.048 token, dan timeout
90 detik per request.

Setiap request disimpan ke direktori unik dengan `request-started.json` yang
ditulis sebelum koneksi API. Hasil dan prompt disimpan setelah respons diterima;
key API disunting sebelum artefak ditulis. Tidak ada retry transport otomatis.
Jika proses terputus, ledger menandai attempt sebagai tidak valid. Lanjutkan
dengan plan dan konfigurasi yang sama:

```powershell
\.venv\Scripts\python.exe development/run_qwen_api_experiments.py `
  --plan development/qwen_api_b_pilot_plan.template.json `
  --execute --resume --confirm-api-spending --confirm-local-dvwa --confirm-database-reset
```

Retry untuk attempt tidak valid harus dinyatakan terpisah dengan
`--retry-invalid`. Runner melakukan reset DVWA baru sebelum attempt ulang dan
tetap menghitung seluruh request yang sudah dimulai terhadap batas eksperimen.

Prompt generation hanya membawa teknik, koordinat HTTP terverifikasi, baseline
yang sudah disaring, feedback observasi terukur, kandidat terdahulu, dan untuk B
teks chunk dari snapshot retrieval. Prompt tidak membawa level keamanan, label
ground truth, SQL source query, HTML mentah, cookie, token, atau data login.
Respons analisis memakai proyeksi observasi terukur dan tidak menerima konteks
retrieval. Gateway API tidak menerima random seed, sehingga seed replikasi
hanya menjadi metadata penjadwalan dan batch API dicatat tanpa seed.

## Status attempt pertama dan pemulihan

Pada 21 Oktober, attempt pertama S1 Low menerima satu respons generation API,
lalu invalid sebelum payload kandidat dikirim ke DVWA. Adapter S1 mengirim string
ke `observe_candidate`, padahal loop adaptif memerlukan objek `{"payload": ...}`.
Perbaikannya ada di `run_qwen_api_experiments.py` dan diuji offline. Attempt
pertama juga telah mereset database DVWA dan mengambil baseline sebelum request
generation. Baris ledger `attempt_invalid` kehilangan fakta tersebut karena
exception generik memakai nilai default. Rincian dan batas bukti ada di
`docs/evidence/qwen-api-b-pilot-attempt-incident-2026-10-21.md`.

Query Chroma pada attempt pertama menulis ulang `data_level0.bin` dan
`chroma.sqlite3` pada store aktif. Salinan pra-attempt yang dipakai untuk
inspeksi masih cocok dengan keenam hash yang disetujui. Store sesudah attempt
disimpan sebagai backup, lalu store aktif dipulihkan dan diverifikasi terhadap
keenam hash receipt. Retrieval berikutnya disiapkan agar memakai salinan kerja
terverifikasi, sehingga query Chroma hanya dapat mengubah salinan itu.

Helper key sebelumnya memuat credential literal di teks prompt dan nilai itu
sempat muncul pada keluaran pemeriksaan. Helper sudah dibersihkan. Cabut key
tersebut dan gunakan key baru sebelum menjalankan plan pemulihan. Plan pemulihan
memiliki ID eksperimen baru dan harus lolos dry-run sebelum eksekusi.
