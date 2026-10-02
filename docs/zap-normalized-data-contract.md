# Kontrak data normalisasi ZAP

- Versi schema: `1.0.0`
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
