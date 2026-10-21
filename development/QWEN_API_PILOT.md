# Runner Qwen API untuk pilot SQLi

Runner ini menghubungkan Qwen API ke ledger eksperimen lokal untuk pilot DAST
black-box pada DVWA. Scope-nya hanya dataset `pilot`, kondisi LLM A/B, dan
payload SQLi error-based, Boolean-based blind, atau time-based blind. Kondisi C
opsional memakai executor SecLists lokal yang sudah ada.

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
