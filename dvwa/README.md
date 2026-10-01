# Lingkungan DVWA untuk TA

Target lokal untuk eksperimen DAST SQL injection pada DVWA. Port web hanya
diikat ke `127.0.0.1:4280`; jangan arahkan pemindaian ke target lain.

## Menjalankan

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

## Cek cepat

```powershell
docker compose -f dvwa/compose.yaml ps
Invoke-WebRequest http://127.0.0.1:4280/login.php -UseBasicParsing
python dvwa/check_levels.py
```

Halaman login yang merespons belum membuktikan database sudah diinisialisasi.
Pastikan tombol **Create / Reset Database** sudah dijalankan dan login berhasil.

## Discovery ZAP terautentikasi

Plan ZAP memakai form authentication dengan cookie session DVWA. Karena field
CSRF DVWA bernama `user_token`, plan mendaftarkan nama tersebut ke ZAP, memuat
form `security.php`, mengubah level pada sesi ZAP sendiri, lalu memeriksa HTML
bahwa level yang diminta benar-benar terpilih. Uji statistik autentikasi juga
menggagalkan run jika ZAP tidak membuktikan login. Pada level High, helper
`session-input.php` dan `cookie-input.php` menjadi seed eksplisit; Client Spider
melengkapi discovery alur berbasis popup.

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

Untuk uji lengkap dari runtime Colab, buka
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
