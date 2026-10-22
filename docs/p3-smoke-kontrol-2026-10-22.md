# P3: kontrol aktual, smoke generator dan pilot, 22 Oktober 2026

**Kontrol executor S1-S12 valid dan smoke A/B menghasilkan enam kandidat
valid dari enam request API. Pilot kemudian berhenti pada S1-A akibat bug
status generasi.** Bug diperbaiki offline pada v3; 200 tes lulus. Tidak ada
attempt pengganti yang dijalankan otomatis. Seluruh pengujian ini adalah
pilot pengembangan, bukan metrik FPR/PSR formal.

## Kontrol executor aktual

DVWA lokal aktif di `http://127.0.0.1:4280`; model embedding Nomic tersedia
pada Ollama lokal. Kontrol manual tetap dijalankan melalui executor yang
sama dengan penelitian. Setiap skenario memakai reset database sampel,
login baru, verifikasi level/form/token/helper dan tiga konfirmasi.

| Level | Error-based | Boolean blind | Time blind |
| --- | --- | --- | --- |
| Low | S1: 3/3 | S2: 3/3 | S3: 3/3 |
| Medium | S4: 3/3 | S5: 3/3 | S6: 3/3 |
| High | S7: 3/3 | S8: 3/3 | S9: 3/3 |
| Impossible | S10: 0/3 | S11: 0/3 | S12: 0/3 |

Seluruh 12 attempt runtime valid. Ada 12 kandidat kontrol manual, 36
konfirmasi, 96 logical probe submissions dan 324 request HTTP. Unit ini
berbeda: baseline/pasangan boolean/kontrol timing menambah jumlah probe,
sedangkan form, login dan verifikasi menambah request HTTP fisik.

Selisih waktu pada S3/S6/S9 adalah 1999,88-2013,45 ms, semuanya melewati
ambang 1500 ms dengan pasangan kontrol yang valid. S12 Impossible memberi
selisih -5,07 sampai 11,57 ms. Kontrol timing mempertahankan payload dan
hanya mengganti argumen `SLEEP` menjadi nol. Tidak ada inferensi LLM yang
berjalan bersamaan dengan rangkaian kontrol ini.

Ini kontrol operasional dengan kandidat manual, bukan hasil payload LLM
atau SecLists. Human validation tetap pending dan tidak digantikan oleh
ringkasan sinyal executor ini.

## Smoke generator aktif

Smoke memakai callback generator P3 aktif, prompt
`qwen38-api-blackbox-generation-v1`, output maksimum 1024 token,
temperature 0, timeout 90 detik dan `enable_thinking=false`. Baseline
diambil dari kontrol aktual; koordinat dikaitkan ke laporan discovery ZAP
terverifikasi. B memakai dua chunk retrieval dari salinan indeks yang
diverifikasi, sedangkan indeks sumber tetap sama.

Urutan adalah S1-A, S1-B, S2-B, S2-A, S3-A, S3-B. Masing-masing meminta
satu kandidat awal, satu kali, tanpa retry.

| Teknik | A | B |
| --- | --- | --- |
| Error-based | Kandidat valid | Kandidat valid |
| Boolean blind | Kandidat valid | Kandidat valid |
| Time blind | Kandidat valid | Kandidat valid |

Keenam respons HTTP 200, model yang dilaporkan
`self-dploy/Qwen3.8-27B`. Total enam request API, 4871 token yang dilaporkan
gateway, dengan rerata waktu generasi 3,04 detik. Identitas bobot model
tidak diverifikasi independen. Kandidat smoke tidak dikirim ke DVWA.

Lolos schema/kebijakan kandidat awal tidak membuktikan payload berhasil atau
sepuluh kandidat unik dapat dicapai pada setiap run. Kedua hal tersebut
dinilai pada pilot berikutnya. Tidak ada SQL source query atau label level
keamanan yang diberikan kepada generator.

## Insiden helper dan pemulihan lokal

Helper awal mengalami assertion hash sesudah respons S1-A tersimpan.
Penyebabnya adalah plan disimpan dengan pengurutan key JSON, lalu pesan
dirender kembali dari dictionary yang urutannya berubah. Teks user message
berbeda pada urutan key, sedangkan nilai JSON, system instruction dan opsi
API sama.

Plan, helper dan request/respons asli dipertahankan. Hasil S1-A dipulihkan
dari checkpoint tanpa pengiriman ulang. Plan lanjutan mengunci payload yang
dirender dari representasi tersimpan sebelum lima request sisanya dikirim.
Seluruh enam hash request aktual cocok dengan plan lanjutan. Total tetap
enam request dan nol retry. Deviasi helper ini dicatat dan tidak dinyatakan
sebagai kepatuhan byte identik terhadap plan awal.

Salinan kedua helper disimpan bersama artefak lokal agar pemulihan dapat
ditelusuri. Tidak ada perubahan source generator atau parser produksi.

## Preservasi

Semua **1.147 file historis** dan **32 source runtime** yang dipin sebelum
kegiatan ini tetap cocok sesudah kontrol serta smoke. Retrieval memakai
salinan kerja; korpus/index sumber, hasil formal, seluruh artefak P2 dan
berkas referensi tetap utuh.

[Receipt kontrol dan smoke](evidence/p3-live-readiness-2026-10-22.json)
memuat hash 46 artefak lokal, rincian kontrol, metadata request dan insiden
helper. Artefak mentah berada di:

- `results/raw/pilot/p3-executor-controls-20261022-v2/`
- `results/raw/development/p3-readiness-20261022-r1/`

## Budget dan eksekusi pilot

Pilot memakai plan `development/qwen_api_p3_v2_pilot_plan.template.json`,
experiment ID `qwen38-api-p3-v2-pilot-20261022`, satu replikasi, serta
rotasi kondisi protokol v2. Ada 33 run applicable: A=12, B=12 dan C=9;
tiga slot C/Impossible excluded. Budget tetap sepuluh kandidat valid per
run dan tiga konfirmasi per kandidat.

Budget khusus ada di `development/qwen_api_p3_budget_20261022.json`:

- **Maksimum 960 request API** untuk pilot. Enam request smoke berada di
  luar budget ini. Batas diturunkan pada instance runtime pilot dari ceiling
  umum, sehingga request berikutnya ditolak saat cap tercapai.
- Maksimum tiga panggilan generasi per slot dan satu analisis per kandidat;
  tidak ada retry transport atau attempt pengganti otomatis.
- Gate waktu enam jam: pemeriksaan sebelum setiap unit dan request API.
  Request baru tidak dimulai bila timeout bakunya tidak lagi muat; pekerjaan
  lokal yang sedang berlangsung diperbolehkan selesai.
- Budget adalah batas request, bukan kepastian biaya atau jam selesai.
  Mata uang dan penagihan final provider belum diverifikasi independen.
- Error layanan, perubahan identitas model, runtime invalid atau kegagalan
  checkpoint menghentikan batch sesuai runner. Attempt gagal dipertahankan.

Launcher `development/run_bounded_qwen_p3_pilot.py` menggunakan ledger dan
executor yang sudah ada tanpa mengubah profil analisis P2. Source launcher
serta budget dipin pada snapshot eksperimen. Tiga tes guard budget lulus.

Perintah untuk dataset baru ini:

```powershell
.\.venv\Scripts\python.exe development/run_bounded_qwen_p3_pilot.py `
  --plan development/qwen_api_p3_v2_pilot_plan.template.json `
  --budget development/qwen_api_p3_budget_20261022.json `
  --execute --confirm-local-dvwa --confirm-database-reset --confirm-api-spending
```

Launcher menolak overwrite/resume direktori yang sudah ada. Jangan memakai
perintah tersebut sebagai retry setelah batch ini telah dimulai. Dataset
dan ledger tersimpan di `results/raw/pilot/qwen38-api-p3-v2-pilot-20261022/`.

## Hasil pilot v2 dan perbaikan lanjutan

Pilot v2 berhenti pada **22 Oktober, 11:28:44 WIB**, saat S1-A menjalankan
slot kandidat kesembilan. Total pemakaian adalah **17 request API**:
sembilan generasi dan delapan analisis. Seluruh respons API berhasil; ini
bukan kejadian HTTP 503 atau timeout provider.

| Status matriks | Jumlah |
| --- | ---: |
| Run completed | 0 |
| Run invalid | 1, S1-A |
| Run applicable belum dimulai | 32 |
| Slot C/Impossible excluded | 3 |

Parser menolak respons generasi kesembilan sebagai `duplicate_structure`.
Callback mengembalikan `rejection_code` tanpa field `status` yang diwajibkan
`adaptive_s1_loop`, sehingga terjadi `KeyError: 'status'` sebelum jalur
regenerasi berbatas budget dapat berjalan. Batch berhenti sesuai kebijakan;
tidak ada retry transport atau attempt pengganti.

Attempt sudah melakukan reset database, 49 logical probe submissions dan
129 request HTTP. Delapan checkpoint analisis sebelumnya tetap tersedia.
Field agregat kandidat pada event invalid berisi nilai default nol karena
exception terjadi sebelum penyusunan artefak akhir. Angka default tersebut
tidak berarti tidak pernah ada probe kandidat. Ledger tidak diedit, dan
checkpoint parsial tidak dijadikan run eligible atau skor PSR.

Receipt pilot ada di
[hasil pilot yang berhenti](evidence/p3-pilot-halted-2026-10-22.json).
Dengan enam request smoke, total request API pada rangkaian kegiatan ini
adalah **23**. Kontrol dan pilot memakai total 453 request HTTP DVWA.

### Perbaikan v3 yang sudah diverifikasi offline

Callback kini selalu membawa `status` dari parser dalam audit generasi,
termasuk kandidat invalid dan duplikat. Jika penolakan berulang, loop memakai
budget regenerasi yang sudah ditetapkan, lalu menghasilkan run tidak lengkap
tanpa crash. Definisi sukses, deduplikasi, prompt generasi dan profil analisis
P2 tidak diubah.

Protokol baru adalah `qwen38-api-sqli-v3-pilot`. Lima regresi generasi baru
ditambahkan. **200 tes lulus**, nol failure/error/skip. Replay seluruh sembilan
checkpoint generasi mereproduksi payload request aktual secara persis;
delapan kandidat diterima dan penolakan duplikat terakhir tertangani tanpa
exception. Tidak ada inferensi baru pada replay.

Seluruh 109 file attempt gagal/smoke yang dipin tetap sama. Sebanyak 32
source sebelum perbaikan diarsipkan; hanya file runner yang sengaja berubah
pada inventory runtime. Audit pertama sempat gagal pada discovery path tes,
bukan pada runtime; log dan versi helper awal tetap dipertahankan. Audit
ulang dengan path diperbaiki menghasilkan 200 tes lulus.

Evidence: [audit perbaikan status generasi](evidence/p3-generation-status-repair-2026-10-22.json).

### Pemulihan yang siap ditinjau

Plan baru `development/qwen_api_p3_v3_pilot_plan.template.json` dan budget
`development/qwen_api_p3_v3_budget_20261022.json` lolos dry-run: 33 run
applicable, maksimum 960 request API baru dan gate waktu enam jam. ID
eksperimen adalah `qwen38-api-p3-v3-pilot-20261022`. Peneliti kemudian
menyetujui satu eksekusi; receipt persetujuan disimpan terpisah dari draft
budget.

## Hasil pilot pemulihan v3

Pilot v3 mulai pukul **11:45 WIB** dan berhenti pukul **12:00:45 WIB** setelah
45 request API. Perbaikan generasi berfungsi: A/S1 menganalisis delapan
kandidat, lalu tiga duplikat berturut-turut mengakhiri run sebagai incomplete
tanpa crash. B/S1 menghasilkan sepuluh kandidat. Dua run SecLists, C/S1 dan
C/S2, juga selesai.

Pada unit B/S2, 5 dari enam respons API kembali berhasil. Request keenam,
analisis, berakhir dengan transport timeout setelah 90,114 detik tanpa status
HTTP. Tidak ada retry. Batch berhenti sesuai protokol.

| Status akhir | Jumlah |
| --- | ---: |
| Run LLM lengkap dan eligible | 1, B/S1 |
| Run SecLists lengkap dan eligible | 2, C/S1 dan C/S2 |
| Run A/S1 incomplete dan excluded | 1, delapan dari sepuluh kandidat |
| Run invalid akibat timeout API | 1, B/S2 |
| Applicable belum dimulai | 28 |
| Slot C/Impossible dikecualikan desain | 3 |

Semua 44 respons API yang kembali menerima HTTP 200. Total request terdiri
dari 24 generasi dan 21 analisis. Executor membuat 732 request HTTP DVWA;
258 logical probe submissions tercatat dari run yang agregatnya lengkap,
sedangkan jumlah pada B/S2 tidak diketahui. Tidak ada FPR/PSR formal dari
pilot ini dan bukti baru belum divalidasi manusia.

Audit memastikan ledger dan checkpoint cocok, tidak ada retry, serta 1.301
file historis dan 32 source runtime sebelum eksekusi tetap utuh. Rincian ada
di [hasil pilot v3](p3-pilot-v3-2026-10-22.md),
[receipt persetujuan](evidence/p3-v3-execution-approval-2026-10-22.json), dan
[audit akhir](evidence/p3-v3-execution-audit-r2-2026-10-22.json). P3 live
belum selesai. Pengumpulan berikutnya memerlukan keputusan baru setelah
kestabilan endpoint analisis diperiksa; budget ini tidak mengizinkan
replacement otomatis.
