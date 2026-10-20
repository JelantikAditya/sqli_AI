# Lingkungan DVWA untuk TA

Target lokal untuk eksperimen DAST SQL injection pada DVWA. Port web hanya
diikat ke `127.0.0.1:4280`; jangan arahkan pemindaian ke target lain.

## Dependency LangChain lokal

Pada 14 Oktober, langchain-core 1.6.10 dipasang dan diperiksa pada `.venv`
proyek. Jalankan dari root proyek untuk memasang ulang dan memeriksa library:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-orchestration.txt
.\.venv\Scripts\python.exe -B dvwa/smoke_langchain.py
```

Smoke memeriksa dua tahap RunnableSequence serial, tanpa inferensi model,
request DVWA atau tracing eksternal. Pilot ledger S1 A/B pada 14 Oktober juga
menjalankan chain LangChain pada generasi dan analisis Qwen serta executor DVWA.
Bukti instalasi ada di
[catatan pemasangan](../docs/evidence/langchain-core-install-2026-10-14.json),
sedangkan bukti runtime ada di
[pilot T02/T05](../docs/evidence/t05-ab-s1-langchain-live-pilot-2026-10-14.json).
Integrasi yang terbukti saat ini terbatas pada S1 Low, belum seluruh teknik
dan level.

## Menjalankan

Urutan condition-run mengikuti protokol v5: blok replikasi 1/2/3 dan S1-S12
numerik, dengan ABC/BCA/CAB pada skenario ganjil serta CBA/ACB/BAC pada genap.
Daftar subset pada plan hanya memilih unit; urutan array tidak menimpa jadwal.
C Impossible excluded. Resume memakai jadwal tersimpan, bukan rotasi baru.
Lihat [keputusan urutan](../docs/keputusan-urutan-kondisi-2026-10-14.md).

Kontrak analisis respons Qwen dan CLI replay evidence tersedia pada
[panduan analisis](../docs/qwen-response-analysis-contract.md).
`analyze_response.py` menganalisis evidence tersimpan tanpa request baru
ke DVWA. Runner adaptif S1 menghubungkan executor, analisis Qwen, dan feedback
regenerasi untuk pilot pengembangan.

```powershell
docker compose -f dvwa/compose.yaml up -d
docker compose -f dvwa/compose.yaml ps
```

Buka `http://127.0.0.1:4280/setup.php`, lalu klik **Create / Reset Database**.
Masuk melalui `http://127.0.0.1:4280/login.php` dengan kredensial bawaan
`admin` / `password`. Kredensial itu hanya boleh dipakai pada instance lokal.

Pada menu **DVWA Security**, pilih `Low`, `Medium`, `High`, atau `Impossible`
sebelum setiap rangkaian pengujian. Catat level, waktu, endpoint, parameter,
jenis SQLi, dan ID percobaan pada log eksperimen; jangan simpan cookie mentah.
Perubahan level berlaku pada
sesi yang digunakan; pastikan sesi scanner dan validator memakai level yang sama.

Runner lokal menyediakan `--reset-before-run` untuk mengirim form reset setup
DVWA sebelum login. Reset menghapus isi database sampel dan memulihkan akun
`admin` / `password`, jadi gunakan flag hanya bila memang ingin menginisialisasi
ulang lab. Kegagalan jaringan, sesi, level, form, atau baseline menghentikan
attempt sebagai invalid dan tidak dihitung sebagai FN. Aturan lengkap ada di
[panduan validation loop](../docs/validation-loop.md).

## Cek cepat

Pilot kontrol executor pada 14 Oktober mencakup S1-S12, termasuk token
Impossible dan helper High. Pilot ledger C mencakup S1-S9, 10 kandidat dan
tiga konfirmasi per skenario. Bukti serta perbaikan kontrol timing/HTTP 404
ada di [laporan T03/T04](../docs/t03-t04-controls-2026-10-14.md).

```powershell
docker compose -f dvwa/compose.yaml ps
Invoke-WebRequest http://127.0.0.1:4280/login.php -UseBasicParsing
python dvwa/check_levels.py
```

Halaman login yang merespons belum membuktikan database sudah diinisialisasi.
Pastikan tombol **Create / Reset Database** sudah dijalankan dan login berhasil.

## Discovery ZAP terautentikasi

Plan ZAP memakai browser authentication agar browser mengisi form login DVWA
beserta token CSRF-nya. Runner menyiapkan level yang diminta sebagai default,
membuat sesi ZAP baru, lalu memeriksa halaman `security.php` untuk memastikan
level tersebut aktif pada sesi scanner. Runner membuat ulang container web
DVWA saja; container database dan volumenya tetap berjalan. Uji statistik
autentikasi juga menggagalkan run jika ZAP tidak membuktikan login. Pada level
High, helper `session-input.php` dan `cookie-input.php` menjadi seed eksplisit;
Client Spider melengkapi discovery alur berbasis popup.

Jalankan discovery terautentikasi dan pasif terhadap instance lokal:

```powershell
.\dvwa\run_zap_discovery.ps1 -SecurityLevel high
```

Gunakan `low`, `medium`, atau `impossible` untuk level lainnya. Report JSON
bertimestamp disimpan di `results/zap/`. Skrip memakai kredensial default DVWA
(`admin` / `password`); jika diubah, isi `DVWA_USERNAME` dan `DVWA_PASSWORD` di
`dvwa/.env` lokal. Jangan commit file tersebut. ZAP berjalan pada jaringan
Compose `dvwa_default` dan hanya memindai service `dvwa` di lab ini.

Plan ini hanya melakukan spidering dan passive scan, tanpa Active Scan atau
payload SQLi. Bukti keberhasilan adalah exit code 0, pemeriksaan level lulus,
dan tes statistik autentikasi ZAP lulus. Jumlah URL atau alert bukan ground
truth SQLi; evaluasi tetap memakai validasi black-box di
[`../docs/ground-truth-2026-10-01.md`](../docs/ground-truth-2026-10-01.md).

## Baseline ZAP active scan API eksplisit

Runner API eksplisit menjalankan dua rule SQLi 40018/40019 pada koordinat dari
katalog skenario, memverifikasi `X-ZAP-Scan-ID`, lalu mengekspor report dan
HAR. Sudah terbukti untuk POST pada Medium dan High. Jalur GET untuk Low dan
Impossible tersedia agar matrix yang sama bisa ditutup. Jalankan dari root:

```powershell
.\dvwa\run_zap_api_explicit.ps1 -SecurityLevel low
.\dvwa\run_zap_api_explicit.ps1 -SecurityLevel medium
.\dvwa\run_zap_api_explicit.ps1 -SecurityLevel high
.\dvwa\run_zap_api_explicit.ps1 -SecurityLevel impossible
```

Runner hanya menargetkan DVWA lokal, memakai API ZAP pada jaringan Docker tanpa
port host yang dipublikasikan, dan menghentikan container API setelah ekspor. HAR dapat berisi cookie dan
nilai request, jadi simpan di `results/zap/` lokal dan jangan dibagikan sebelum
disanitasi. Ringkasan coverage tersanitasi disimpan di `results/raw/`.
Status cakupan terbaru dan batas interpretasi ada di
[laporan U06](../docs/u06-pilot-zap-baseline-2026-10-14.md).

## Validation loop SQLi terkontrol

Discovery lokal terbaru juga mengekspor HAR seluruh pesan ZAP. Runner langsung
menormalisasi request/form dan gagal bila cakupan input per level belum lengkap.
Report normalized memakai schema 1.1.0; token/cookie/nilai input HAR tetap lokal.
Lihat [kontrak inventaris HAR](../docs/zap-normalized-data-contract.md#inventaris-requestform-pada-jalur-lokal)
dan [protokol pilot lokal](../docs/protokol-evaluasi-lokal.md).

MVP validator menguji satu skenario ground truth per run terhadap DVWA lokal,
menggunakan kandidat payload dari file JSON dan mencatat tiap request serta
keputusan awal ke `results/raw/`. Parser ZAP dan validator membaca katalog
bersama di [`experiment_scenarios.json`](experiment_scenarios.json), sehingga
mapping level, endpoint, metode, dan ID skenario tidak diduplikasi.

Ikuti [panduan validation loop](../docs/validation-loop.md) untuk membuat file
kandidat lokal dan menjalankan satu skenario. File kandidat lokal dan hasil
mentah diabaikan Git. Kandidat LLM/RAG tidak diambil otomatis. Batch SecLists
S1-S9 kini dapat dibangun dari sumber yang sudah diunduh secara lokal dengan
`build_seclists_batches.py`; panduan dan hash sumbernya ada di
[`../docs/candidate-sources.md`](../docs/candidate-sources.md). Label
TP/FP/TN/FN yang dicatat masih provisional dan perlu validasi manusia.

### Loop pilot adaptif Qwen lintas skenario

Runner pengembangan `adaptive_s1_loop.py` menghubungkan generasi kandidat,
baseline dan tiga konfirmasi, analisis Qwen, serta feedback untuk S1-S12 pada
kondisi A/B. Adapter memilih schema kandidat tunggal error/time atau pasangan
boolean, lalu menyimpan evidence dengan role dan hash respons yang tervalidasi.
Runner ledger memakai budget 10 dan me-reset database setiap condition-run;
eksekusi meminta konfirmasi target DVWA lokal dan reset database. Smoke U03
mencakup satu kandidat untuk semua skenario S2-S12 pada A dan S2 pada B. Artifact
awal S5/S8 menyimpan error parsing evidence references berulang; normalizer kini
mempertahankan teks mentah, menghapus hanya ID duplikat dari record terstruktur,
dan menandai warning audit. Replay S5 tetap menunjukkan mismatch antara klaim
model dan sinyal executor. Pilot terpadu U06 mencoba 33 run applicable, tetapi
hanya 15/33 menyelesaikan 10 kandidat; 124 slot kandidat belum terpenuhi.
Follow-up API eksplisit membuktikan coverage 2/2 koordinat pada keempat level.
Low dan Medium masing-masing menghasilkan satu alert rule 40018; High dan
Impossible tidak menghasilkan alert pada target yang dicakup. Coverage U06.2
selesai, tetapi stabilitas generasi U06.1 masih pending. Lihat
[laporan pilot U06](../docs/u06-pilot-zap-baseline-2026-10-14.md) dan
[rencana penyelesaian](../docs/rencana-penyelesaian-2026-10-16.md).

Perintah berikut mereproduksi pasangan pilot 12 Oktober jika artefak seed
lokal yang berada di `results/raw/` masih tersedia. Jalankan terpisah untuk
kedua kondisi:

```powershell
\.venv\Scripts\python.exe dvwa/adaptive_s1_loop.py --rag-mode off --zap-report results/zap/zap-discovery-low-20261011-180846.normalized.json --comparison-id adaptive-s1-feedback-20261012 --replicate 1 --pilot-slots 2 --initial-batch results/raw/candidates-S1-llm-off-20261011T111501Z-12fed9.json --initial-generation-audit results/raw/generation-audit-20261011T111501Z-12fed9.json --confirm-local-dvwa

\.venv\Scripts\python.exe dvwa/adaptive_s1_loop.py --rag-mode on --zap-report results/zap/zap-discovery-low-20261011-180846.normalized.json --comparison-id adaptive-s1-feedback-20261012 --replicate 1 --pilot-slots 2 --initial-batch results/raw/candidates-S1-llm-on-20261011T111622Z-fe13f4.json --initial-generation-audit results/raw/generation-audit-20261011T111622Z-fe13f4.json --confirm-local-dvwa
```

Output penuh tersimpan di `results/raw/` yang diabaikan Git. Ringkasan
tersanitasi dan batas pilot ada di
[`../docs/qwen-response-analysis-contract.md`](../docs/qwen-response-analysis-contract.md#pilot-loop-adaptif-lokal-s1-pada-12-oktober).

Untuk menyiapkan batch kandidat dengan provenance yang dapat diaudit, gunakan
[`../docs/candidate-sources.md`](../docs/candidate-sources.md) dan
`dvwa/prepare_candidate_batch.py`. Langkah ini memvalidasi metadata LLM/RAG
atau kecocokan payload SecLists dengan file dan nomor baris sumber sebelum
batch diberikan ke runner. Panduan yang sama menjelaskan indexing JSON ke Chroma,
retrieval, serta generasi kandidat Qwen lokal. Runtime Qwen, indexing diagnostik PDF,
embedding, dan retrieval lokal sudah terverifikasi pada 7 Oktober; generator
batch kandidat sudah memiliki smoke nyata S1 pada 11 Oktober. Bukti serta batas kualitas retrieval ada di
[`../docs/progress-2026-10-07.md`](../docs/progress-2026-10-07.md).
Jalur utama RAG kini memakai entri JSON dari OWASP WSTG v4.2 dan
PayloadsAllTheThings SQL Injection; index PDF hanya uji diagnostik. Lihat
[penyesuaian proposal](../docs/proposal-rag-2026-10-07.md)
untuk sumber terkunci, build, retrieval injection point, dan batas verifikasi.

### Orchestrator eksperimen lokal T05

`run_local_experiments.py` mengelola kondisi, skenario, seed replikasi,
discovery, generasi Qwen atau batch SecLists, reset database, executor, serta
ledger. Mulai dari subset pilot dan salin template ke berkas lokal yang tidak
masuk Git:

```powershell
Copy-Item dvwa/local_run_plan.template.json dvwa/local_run_plan.local.json
```

Isi path report ZAP normalized yang sudah diverifikasi. A dan B memakai report
yang sama untuk skenario dan replikasi yang sama. Untuk memilih C, isi
`seclists_source_root` dengan folder lokal dari commit yang dikunci di rencana
T04. Rencana pilot saja yang dapat dijalankan saat protokol masih berstatus
`pilot`.

Tinjau rencana tanpa mengirim request:

```powershell
\.venv\Scripts\python.exe dvwa/run_local_experiments.py --plan dvwa/local_run_plan.local.json
```

Eksekusi meminta dua konfirmasi eksplisit. Setiap condition-run memulai login
baru dan mereset database sampel DVWA melalui setup HTTP:

```powershell
\.venv\Scripts\python.exe dvwa/run_local_experiments.py `
  --plan dvwa/local_run_plan.local.json `
  --execute --confirm-local-dvwa --confirm-database-reset
```

Ledger JSONL bersifat append-only dan checkpoint diperbarui atomik di
`results/raw/pilot/<experiment_id>/`. Resume memakai rencana dan hash protokol
yang sama. Attempt yang terputus ditandai invalid dan tidak otomatis diulang;
setelah memperbaiki runtime, gunakan `--resume --retry-invalid` agar attempt
baru mendapat ID baru, login baru, dan reset baru. Status budget yang tidak
lengkap dikecualikan dari metrik. Artefak formal tertahan sampai protokol
berstatus frozen. Candidate guard menolak operasi mutasi, file, stacked
statement, dan delay timing di atas dua detik sebelum satu request kandidat
dikirim.

### Freeze protokol dan otorisasi dataset formal

Freeze U07 dan eksekusi F01 adalah dua keputusan berbeda. Setelah paket
kesiapan baru memiliki 10 gate selain `runtime-manifest-frozen` berstatus
passed, audit bukti dan working tree, lalu periksa kelayakan release tanpa
mengubah protokol:

```powershell
& .\.venv\Scripts\python.exe dvwa/release_formal_freeze.py `
  --candidate-dir results/raw/u07-formal-readiness-20261018-v18 --check
```

Jika audit berhasil, tool dapat membuat receipt freeze berstatus `pending`.
Peneliti meninjau ulang hash kandidat, plan, protokol, dan receipt korpus, lalu
merekam keputusan freeze secara eksplisit pada file tersebut. Perintah release
menolak receipt pending atau hash yang tidak cocok. Release membekukan protokol
dan menghasilkan `formal-release-manifest.json`; status release itu sendiri
belum memberi izin menjalankan dataset formal.

```powershell
& .\.venv\Scripts\python.exe dvwa/release_formal_freeze.py `
  --candidate-dir results/raw/u07-formal-readiness-20261018-v18 `
  --write-approval-template

# Setelah peneliti meninjau dan merekam keputusan pada receipt:
& .\.venv\Scripts\python.exe dvwa/release_formal_freeze.py `
  --candidate-dir results/raw/u07-formal-readiness-20261018-v18 `
  --release `
  --approval results/raw/u07-formal-readiness-20261018-v18/formal-freeze-approval.json
```

Sebelum F01, peneliti membuat receipt `formal-dataset-execution` yang
mencantumkan `experiment_id`, path dan SHA-256 plan formal, path dan SHA-256
`formal-release-manifest.json`, serta otoritas dan waktu persetujuan. Schema
receipt ada di `schemas/formal-execution-approval.schema.json`. Runner memeriksa
receipt terhadap protokol aktif, snapshot sumber release, plan persis yang
dipakai, dan release manifest sebelum membuat atau melanjutkan attempt.
Eksekusi formal dan resume formal harus menyertakan receipt yang sama:

```powershell
& .\.venv\Scripts\python.exe dvwa/run_local_experiments.py `
  --plan dvwa/local_run_plan.formal-20261017-approved-index.json `
  --formal-execution-approval results/raw/formal-execution-approval.json `
  --execute --confirm-local-dvwa --confirm-database-reset
```

Untuk mengurangi beban laptop, F01 dapat dijalankan satu blok replikasi per
sesi. Tambahkan `--one-replicate-per-session` pada eksekusi pertama dan setiap
resume. Runner memilih replikasi paling awal yang belum selesai, menuntaskan
blok itu, mencatat event `execution_paused` pada ledger, lalu kembali tanpa
memulai replikasi berikutnya. Gunakan plan, ledger, receipt formal, dan
konfigurasi yang sama pada semua sesi. Contoh invocation lanjutan:

```powershell
& .\.venv\Scripts\python.exe dvwa/run_local_experiments.py `
  --plan dvwa/local_run_plan.formal-20261017-approved-index.json `
  --formal-execution-approval results/raw/formal-execution-approval.json `
  --resume --execute --one-replicate-per-session `
  --confirm-local-dvwa --confirm-database-reset
```

Invocation pertama memakai perintah formal di atas dengan tambahan
`--one-replicate-per-session` dan tanpa `--resume`. Jangan menghentikan proses
secara manual di tengah condition-run. Jika attempt terputus, perilaku invalid
dan recovery tetap mengikuti prosedur resume/retry yang dijelaskan sebelumnya.
Pertahankan model, parameter, index, image Docker, dan konfigurasi daya yang
sama; ledger menyimpan waktu mulai dan selesai setiap attempt serta waktu jeda
antarblok.

Receipt keputusan korpus `approved-for-formal-use` hanya menyetujui snapshot
korpus untuk protokol formal. Receipt itu tidak menggantikan persetujuan freeze
atau persetujuan menjalankan F01. Untuk condition B pada pilot v18, runner
memerlukan receipt korpus terpisah berstatus `approved-for-pilot-use` yang
terikat ke corpus dan index Chroma yang sama; jangan mengubah receipt formal
agar dapat dipakai untuk pilot. Jika metadata korpus yang sudah dipin masih
menyebut `researcher_review: pending`, receipt pilot harus mencatat attestation
review peneliti dan `approved_snapshot` yang cocok persis dengan corpus, source
lock, dan seluruh file index. Runner memvalidasi attestation itu tanpa mengubah
corpus atau manifest bersama, sehingga persetujuan formal yang sudah ada tetap
terikat ke hash semula. Persetujuan penggunaan korpus ini tetap tidak
menggantikan kesiapan pilot lokal atau otorisasi eksekusi eksperimen.

## Referensi historis: akses Colab melalui tunnel bertoken (ditunda)

Jalur Colab/tunnel tidak digunakan untuk eksperimen aktif; metode saat ini
berjalan lokal sesuai [metodologi lokal](../docs/metodologi-lokal-2026-10-14.md).
Bagian berikut dipertahankan untuk catatan pengembangan terdahulu. Jangan
gunakan sebagai prosedur pilot aktif. Lihat [rencana penyelesaian](../docs/rencana-penyelesaian-2026-10-16.md)
untuk status dan langkah kerja terbaru.

Tunnel sementara Cloudflare menuju gateway. Gateway mewajibkan header
`X-Lab-Token` pada **setiap** request sebelum meneruskannya ke DVWA. Token
acak disimpan hanya di `dvwa/.env` dan tidak boleh diunggah ke repositori atau
ditaruh dalam notebook yang dibagikan. Perintah awal:

```powershell
python dvwa/create_token.py
docker compose -f dvwa/compose.yaml --profile tunnel up -d
docker compose -f dvwa/compose.yaml --profile tunnel logs tunnel | Select-String trycloudflare
Get-Content dvwa/.env
```

`create_token.py` cukup dijalankan satu kali setelah clone. Jika token lokal
sudah ada, skrip sengaja tidak menimpanya agar sesi eksperimen tidak putus.

Masukkan URL `https://...trycloudflare.com` dan nilai `LAB_TOKEN` secara privat
ke Colab. Contoh cek koneksi di sel Colab:

```python
from getpass import getpass
from urllib.request import Request, urlopen

base_url = input("Tunnel URL: ").rstrip("/")
lab_token = getpass("LAB_TOKEN: ")
request = Request(base_url + "/login.php", headers={"X-Lab-Token": lab_token})
with urlopen(request, timeout=20) as response:
    print(response.status, "DVWA" in response.read().decode("utf-8", "replace"))
```

Hasil yang diharapkan adalah `200 True`. Setiap request Colab berikutnya wajib
menyertakan header yang sama; gunakan satu cookie jar untuk login dan request
eksperimen. URL tunnel berubah jika layanan tunnel dibuat ulang. Cek dari
komputer lokal dengan:

```powershell
python dvwa/check_tunnel.py https://ALAMAT-TUNNEL.trycloudflare.com
```

Untuk menyiapkan Ollama/LangChain/Chroma dan membangun knowledge base RAG di runtime Colab, buka
[`notebooks/colab_langchain_setup.ipynb`](../notebooks/colab_langchain_setup.ipynb)
di Colab melalui tombol **Upload notebook**. Notebook ini melakukan smoke check
model/embedding, membaca entri JSON dan sumber terkunci dari kode yang diunggah ke
`MyDrive/TA-SQLi/project-code/`, membangun Chroma dengan LangChain, dan menyimpan
arsip ZIP serta manifest provenance ke Google Drive. Chroma dipulihkan ke disk
runtime `/content` saat sesi berjalan. Notebook juga membuat pasangan batch
kandidat LLM RAG-off/RAG-on beserta audit prompt dan ID chunk retrieval.
Pembuatan batch belum menjalankan payload; review manusia diperlukan sebelum
batch diberikan ke runner. Bagian akhir notebook menyediakan runner tunnel
bertoken yang membaca batch dari folder tersebut, meminta frasa konfirmasi
sebelum request, dan menyimpan log JSONL ke `validation-logs/` tanpa URL,
token, password, cookie, atau response body. Runner memulai dari satu
replikasi dan membatasi maksimum tiga. Jalankan notebook smoke tunnel di bawah
lebih dahulu.

Untuk memeriksa tunnel, login, dan level DVWA, buka
[`notebooks/colab_dvwa_smoke.ipynb`](../notebooks/colab_dvwa_smoke.ipynb)
di Colab melalui tombol **Upload notebook**, lalu jalankan semua sel. Repository
GitHub bersifat private, jadi tautan GitHub langsung ke Colab memerlukan
otorisasi GitHub tambahan; unggah berkas lokal untuk menghindari izin tersebut.
Notebook meminta URL tunnel, token, dan
password DVWA saat dijalankan. **Jangan simpan salinan notebook dengan output
atau rahasia yang masih terisi.** Hasil yang diharapkan adalah penolakan 403
tanpa token, login berhasil, dan empat level bertanda `OK`.

Login browser lokal dapat tetap memakai `127.0.0.1:4280`. Sesi Colab terpisah,
jadi level keamanan perlu disetel dan diverifikasi lagi pada sesi Colab.
Tunnel ini hanya untuk eksperimen singkat; hentikan setelah dipakai:

```powershell
docker compose -f dvwa/compose.yaml --profile tunnel stop tunnel gateway
```

Cloudflare menyatakan Quick Tunnel ditujukan untuk pengujian, memakai URL
sementara, dan tidak memberi jaminan uptime. Karena DVWA sengaja rentan,
jangan membagikan token maupun URL beserta tokennya.

## Menghentikan

```powershell
docker compose -f dvwa/compose.yaml down
```

Perintah ini mempertahankan volume database agar eksperimen berikutnya dapat
dilanjutkan. Reset data eksperimen melalui tombol setup DVWA jika diperlukan.

## U07: manifest kandidat dan gate formal

Status 17 Oktober: audit tersedia, protokol masih pilot. Baca
[laporan U07](../docs/u07-freeze-kesiapan-formal-2026-10-17.md) untuk gate yang
masih terbuka. Tool persiapan membaca metadata dan evidence; tool tidak
menjalankan eksperimen atau mengganti status protokol menjadi frozen.

```powershell
& .\.venv\Scripts\python.exe dvwa/prepare_formal_freeze.py `
  --capture-runtime results/raw/u07-formal-readiness-20261017/runtime.json

& .\.venv\Scripts\python.exe dvwa/prepare_formal_freeze.py `
  --runtime results/raw/u07-formal-readiness-20261017/runtime.json `
  --plan dvwa/local_run_plan.formal-20261017.json `
  --output-dir results/raw/u07-formal-readiness-20261017
```

Mode capture memerlukan Docker/Ollama lokal. Satu GET halaman login memeriksa
reachability DVWA; container ZAP sementara memakai `--network none` untuk
mendaftar file versi/add-on. Mode persiapan memverifikasi ledger pilot,
hash sumber dan artefak, index SQLite read-only, budget context, hasil tes,
schedule, serta salinan backup. `tests.log` di direktori output harus memuat
hasil suite offline terbaru agar gate kontrak lulus.

Plan formal memuat 99 run applicable dan 990 slot kandidat. Dua belas path
discovery adalah reservasi baru untuk tiga replikasi; report masih perlu
dibuat pada persiapan F01. Root `results/raw/formal/` disiapkan tanpa membuat
subfolder experiment ID atau ledger. Runner menolak plan formal sampai
protokol benar-benar frozen. Archive dan mapping validator tetap privat lokal.
