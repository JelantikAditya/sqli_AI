# Persiapan cohort P3 v5

Status: **siap untuk ditinjau dan dijalankan**, belum dieksekusi. Paket ini
menyiapkan cohort baru `qwen38-api-r4-20261022` dengan protokol
`qwen38-api-sqli-v5-pilot`.

Pada cohort sebelumnya, r3 berhenti di S7-B setelah 234 request API: 233
berhasil dan satu menghasilkan HTTP 500. Sembilan unit LLM juga tidak
mencapai 10 kandidat valid; audit menemukan 31 saran `duplicate_structure`.
Retry r3 tidak mengingat saran duplikat yang ditolak. Di v5, saran tersebut
dimasukkan ke konteks prompt dan daftar pengecualian parser untuk slot yang
sama. Kandidat yang ditolak tidak dihitung sebagai kandidat valid, tidak
memajukan slot, dan tidak menambah batas retry.

Cakupan tetap sama: 12 skenario SQL injection pada DVWA Low, Medium, High, dan
Impossible; satu replikasi; 33 unit applicable. Tiga slot kondisi C pada
Impossible tetap excluded sesuai desain. Cohort ini dimulai dari slot pertama
dengan ID baru, dan tidak menggabungkan hasil dari r3.

Batas pelaksanaan tetap 960 request API dan enam jam. Generasi memakai timeout
90 detik, analisis 180 detik, 10 kandidat per unit LLM, paling banyak tiga
permintaan generasi per slot, tiga konfirmasi per kandidat, dan tanpa retry
transport atau replacement otomatis. Enam jam merupakan batas maksimum, bukan
perkiraan pasti durasi selesai. Cohort tetap berstatus pengembangan dan tidak
menghasilkan metrik formal FPR/PSR.

Validasi persiapan lulus: dry-run menghasilkan 36 slot, 33 unit applicable,
24 unit LLM, dan batas worst-case 960 request. Dua tes baru memeriksa bahwa
saran duplikat muncul dalam konteks retry, ditolak lagi oleh parser, dan tidak
bocor ke cache slot berikutnya. Bersama tes timeout, budget, dan gate P3,
sebanyak 21 tes lulus. Tidak ada API request, request DVWA, atau reset database
selama persiapan ini. Folder hasil untuk ID baru belum dibuat.

Pemeriksaan endpoint sebelumnya ke `https://api.hcnsec.cn/v1/chat/completions`
menghasilkan HTTP 200 dalam 2,876 detik dengan respons yang diharapkan. Itu
mengonfirmasi key dan route berfungsi pada saat pemeriksaan, tetapi tidak
menjamin kestabilan provider selama cohort.

Untuk memeriksa paket tanpa menjalankan cohort:

```powershell
.\.venv\Scripts\python.exe development\run_bounded_qwen_api_p3_v5.py `
  --plan development\qwen_api_p3_v5_plan.template.json `
  --budget development\qwen_api_p3_v5_budget_20261022.json
```

Untuk memulai cohort, launcher mensyaratkan konfirmasi eksplisit terhadap
DVWA lokal, reset database, dan penggunaan API:

```powershell
.\.venv\Scripts\python.exe development\run_bounded_qwen_api_p3_v5.py `
  --plan development\qwen_api_p3_v5_plan.template.json `
  --budget development\qwen_api_p3_v5_budget_20261022.json `
  --execute --confirm-local-dvwa --confirm-database-reset --confirm-api-spending
```

Runner menolak ID hasil yang sudah ada dan tidak melanjutkan cohort lama.
Receipt validasi dan hash artefak tersimpan di
`docs/evidence/p3-v5-preparation-2026-10-22.json`.
