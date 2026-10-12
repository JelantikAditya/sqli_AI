# Lingkungan DVWA untuk TA

Target lokal untuk eksperimen DAST SQL injection pada DVWA. Port web hanya
diikat ke `127.0.0.1:4280`; jangan arahkan pemindaian ke target lain.

## Menjalankan

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

### Pilot loop adaptif Qwen S1

Runner pengembangan `adaptive_s1_loop.py` menghubungkan generasi kandidat,
validasi tiga kali dengan baseline, analisis Qwen, dan feedback ke generasi
berikutnya. Jalur hanya menerima S1 Low pada DVWA lokal, menyimpan hash
respons serta diagnostik allowlist, dan membatasi pilot di dua kandidat secara
default. Setiap run berhenti sebagai incomplete terhadap budget protokol 10;
ringkasan tersebut tidak boleh dihitung sebagai FPR/PSR formal. Reset database
opt-in tersedia melalui `--reset-before-run`; pilot yang sudah tersanitasi
dijalankan tanpa reset langsung dan hanya untuk pengembangan.

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

## Akses Colab melalui tunnel bertoken

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
