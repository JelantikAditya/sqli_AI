# Kontrak data normalisasi ZAP

- Versi schema: `1.0.0` untuk alert lama; `1.1.0` untuk alert dan inventaris HAR.
- Schema machine-readable: [`schemas/zap-normalized-run.schema.json`](../schemas/zap-normalized-run.schema.json)
- Parser: [`dvwa/parse_zap_report.py`](../dvwa/parse_zap_report.py)

## Tujuan

Kontrak ini menormalisasi alert instance dari report JSON OWASP ZAP agar bisa
dipakai pipeline eksperimen. Data discovery dipisahkan dari hasil deteksi SQLi
dan dari label ground truth. Alert ZAP, terutama hasil passive scan, tidak
dihitung sebagai TP, FP, TN, atau FN.

## Bentuk data

- `run_metadata`: identitas report, versi scanner, target, level, mode scan, dan
  status autentikasi.
- `summary`: jumlah grup alert, instance alert, URI yang muncul pada instance,
  kandidat input, dan grup alert dengan nama yang memuat `SQL Injection`.
- `observations`: satu record untuk setiap instance alert. Query string,
  fragment, payload, evidence, dan `otherinfo` mentah tidak disalin.
- `candidate_injection_points`: koordinat method/path/parameter yang berasal
  dari instance alert pada endpoint SQLi DVWA yang dikenal dan cocok dengan
  level serta method di ground truth. Setiap kandidat mencantumkan `scenario_ids`
  yang mungkin sesuai, tetapi tetap berstatus `unverified`.
- `out_of_level_sqli_input_observation_count`: input `id` pada endpoint SQLi
  yang terlihat dalam alert tetapi method/path-nya tidak cocok dengan peta level.
- `interpretation`: selalu menyatakan `sql_injection_detection: not_assessed`.

Jika sebuah alert tidak memiliki instance, parser tetap menyimpan satu
observation dengan `instance: null`; jumlah ini masuk ke `alert_group_count`,
bukan `alert_instance_count`.

## Aturan pengisian metadata

Parser tidak menebak level keamanan, mode scan, atau autentikasi dari HTTP 200,
jumlah URL, atau alert. Ketiganya berasal dari bukti run yang terpisah. Nilai
bawaan adalah `unknown`; masukkan `verified` hanya jika plan/run yang sama lulus
pemeriksaan level dan autentikasi.

Contoh untuk report Low yang catatan run-nya menyatakan autentikasi dan mode
passive terverifikasi:

```powershell
python dvwa/parse_zap_report.py `
  results/zap/zap-discovery-low-20261001-221156.json `
  --security-level low `
  --scan-mode passive `
  --authentication-status verified
```

Output default berada di samping report sebagai `*.normalized.json`. Output
tersebut mengikuti aturan ignore lokal di `results/zap/`.

## Batas interpretasi

`candidate_injection_points` hanyalah koordinat input yang terlihat dalam
instance alert dan cocok dengan endpoint, method, serta level pada peta SQLi.
Plan ZAP saat ini men-seed helper High pada setiap level, sehingga helper yang
muncul pada level lain tetap ada di `observations` dan dihitung sebagai input
out-of-level, bukan kandidat untuk skenario level tersebut. Kandidat tidak
membuktikan ZAP menguji payload SQLi, tidak membuktikan kerentanan, dan tidak
mewakili seluruh URL hasil crawl. Untuk evaluasi, gabungkan dengan ground truth
dan hasil validation loop yang mencatat replikasi serta keputusan validator
manusia.

## Inventaris request/form pada jalur lokal

Plan terbaru mengekspor HAR dengan job `export`, `source: all`, setelah discovery.
Sumber `all` mencakup pesan yang dihasilkan ZAP, termasuk spider; `history` saja
tidak cukup untuk jalur ini. Acuan: [ZAP Import/Export Automation](https://www.zaproxy.org/docs/desktop/addons/import-export/automation/).

`dvwa/export_zap_inputs.py` membaca HAR secara offline. Field yang dipublikasikan
hanya koordinat, nama field terpilih, status HTTP, dan referensi observation.
Nilai parameter, cookie, token, teks halaman, dan body request tidak disalin.
Schema inventaris ada di `schemas/zap-input-inventory.schema.json`.

Koordinat menjadi `verified` jika respons terlindungi dan bukti level pada
`security.php` berasal dari sesi PHP serta state cookie keamanan yang sama.
Helper popup High tidak memiliki navigasi Logout; bukti login/level-nya berasal
dari halaman security pada sesi yang sama, ditambah respons helper/form yang
sesuai dan tidak berupa form login. Status verified hanya memverifikasi
koordinat input, bukan SQLi.

`discovery_inventory` menyimpan `covered_scenario_ids` dan
`missing_scenario_ids`. Dua injection point per level mencakup tiga skenario
karena endpoint blind digunakan untuk boolean dan timing. Cakupan ini tidak
berarti seluruh aplikasi telah dijelajahi.

Runner PowerShell menghasilkan alert JSON, HAR, log, dan report normalized
dengan run stem yang sama. Ia gagal bila autentikasi/level atau cakupan input
tidak lengkap. Seluruh artefak runtime tersebut diabaikan Git.

```powershell
.\.venv\Scripts\python.exe dvwa/parse_zap_report.py `
  results/zap/zap-discovery-low-<timestamp>.json `
  --har-report results/zap/zap-discovery-low-<timestamp>.har `
  --security-level low --scan-mode passive --require-complete-inputs
```

Untuk generator lokal, tambahkan `--zap-report <normalized-report>` dan
`--require-verified-discovery`. Mode ini menolak fallback katalog dan kandidat
alert yang belum terverifikasi. Jalur lama tetap tersedia untuk smoke/riwayat;
jangan pakai fallback tersebut sebagai input discovery formal.
