# Persiapan uji formal P4 Poolside Laguna

Protokol P4 sudah dibekukan berdasarkan persetujuan peneliti dan hash-bound
freeze receipt. Belum ada cohort formal yang dijalankan. Runner tetap menolak
eksekusi sampai release manifest dan persetujuan eksekusi terpisah yang
terikat hash tersedia.

## Desain dan batas eksekusi

P4 memakai 99 unit applicable pada tiga replikasi, 990 kandidat, dan 2.970
konfirmasi logis. Matriks mencakup 72 unit A/B dengan API Poolside langsung dan
27 unit C dengan SecLists. Protokol beku membatasi API pada 2.880 request dan 3.686.400
completion token, tanpa retry transport, penggantian unit, atau fallback model.
Kebijakan biaya adalah USD 0. Runner harus berhenti jika katalog atau status
provider tidak gratis, quota atau rate limit tercapai, atau ada perubahan hash.

Q4 v5 tetap qualification saja: 24/24 unit A/B lengkap, tetapi receipt tetap
`formal_eligible=false`. Hasil formal Qwen lokal tetap berada pada path aslinya
dan akan dilaporkan sebagai cohort terpisah. Teks proposal belum diubah sesuai
keputusan peneliti untuk mengubahnya pada akhir penelitian.

## Gate saat ini

| Gate | Status | Bukti |
| --- | --- | --- |
| Desain, hitungan, dan qualification Q4 | Lulus | 99 unit, 990 kandidat, 2.970 konfirmasi; Q4 24/24 dan tetap bukan hasil formal. |
| Runner P4 dan input terpin | Lulus | Runner khusus memvalidasi plan, budget, protocol, metode, source hash, release, serta receipt sebelum eksekusi. Dry-run tidak membaca credential. |
| Isolasi snapshot korpus | Lulus | Keenam hash arsip cocok; retrieval mengembalikan dua chunk dari salinan Chroma sementara dan arsip tidak berubah. Indeks aktif tetap tidak sama dengan arsip dan tidak dipakai oleh P4. |
| Discovery ZAP segar dan review teknis | Lulus | Dua belas scan passive, terautentikasi, tiga replikasi kali empat level. Setiap report memverifikasi dua injection point. Review memetakan report ke formal plan. |
| Preflight DVWA lokal | Lulus | Satu reset database sukses, sesi dan level Low/Medium/High/Impossible terverifikasi, 20 baseline benign tercatat, maksimum 23,75 ms terhadap ambang 1.500 ms. Tidak ada payload SQLi atau request API. |
| Smoke provider gratis saat ini | Lulus terbatas | Smoke terbaru dari key akun baru mengirim dua request langsung, keduanya HTTP 200, model tepat `poolside/laguna-s-2.1`, katalog `is_free=true`, dan semua harga tercatat nol. Ini memverifikasi koneksi dan harga katalog saat ini. |
| Kuota akun, rate limit, dan kontinuitas provider | Lulus dengan konfirmasi peneliti | Peneliti menyatakan akun/key baru aman untuk rate limit dan run formal Laguna. Batas akun tidak dibaca langsung dari console. Poolside mengumumkan inference dihentikan pada 31 Oktober 2026, jadi run harus dilakukan selagi endpoint tersedia. Jika terputus, cohort tidak lengkap dan tidak boleh pindah provider. OpenRouter tidak masuk P4. |
| Freeze protokol | Lulus | Receipt peneliti mengikat formal plan, budget, dan protocol candidate. Persetujuan eksekusi tetap terpisah. |
| Release manifest | Lulus | Paket dilepas setelah 21 gate teknis lulus dan terikat ke hash plan, budget, protocol, serta bukti gate. |
| Persetujuan eksekusi formal | Terbuka | Receipt hash-bound belum dibuat; cohort formal tetap terkunci sampai peneliti menyetujuinya secara terpisah. |
| VAL-01 blind | Ditunda sesuai desain | Packet dan blind mapping baru dibuat setelah candidate ID P4 terkunci. |

### Hash yang dikunci oleh freeze

Hash berikut mengikat kandidat final yang disetujui. `protocol_candidate_sha256`
menormalkan status draft/frozen, sehingga receipt freeze tetap mengikat isi
protokol yang sama saat statusnya berubah menjadi frozen.

| Artefak | SHA-256 |
| --- | --- |
| Formal runner plan | `4b4d5bb3a8a23801ad31bf5ba6e27cca4e9c47c4fc579c08079d39461277267e` |
| Budget, dengan batas biaya USD 0 | `61a987f2d44b7e70822f90f02853fe33fb65bf5876471d6386cd494557e8a377` |
| Protocol candidate | `12b2d704c07248bedff35e9459cb074c1ffa94b3c66a09cb80b67cecb969e3ee` |

Receipt freeze tersimpan pada
`docs/evidence/poolside-laguna-p4-freeze-approval-2026-10-23.json` dengan SHA-256
`0ca77139d50990d2af270ba3ba4106cfada73d8f30396a6b752a2868136eda7c`.
Protokol berstatus `frozen`; freeze tidak memberi persetujuan untuk menjalankan
cohort. Receipt persetujuan eksekusi belum ada dan harus mengikat release
manifest secara terpisah.

### Temuan discovery yang ditinjau

Jumlah observasi input di luar peta level adalah 1 pada Low, 1 pada Medium,
0 pada High, dan 3 pada Impossible di setiap replikasi. Semuanya berasal dari
POST helper `/vulnerabilities/sqli_blind/cookie-input.php` yang memang di-seed
oleh template passive discovery pada setiap level. Observasi ini adalah
koordinat helper dan cookie, bukan deteksi SQLi atau tambahan skenario formal.
Seluruh 12 report mencatat nol grup alert SQL injection. Hasil discovery tidak
masuk hitungan FPR atau PSR.

## Artefak bukti

- [Plan P4](../development/poolside_laguna_p4_plan_20261023.json), [formal runner plan](../development/poolside_laguna_p4_formal_plan_20261023.json), [budget](../development/poolside_laguna_p4_budget_20261023.json), dan [protocol beku](../development/poolside_laguna_p4_protocol_20261023.json).
- [Runner P4](../development/run_poolside_laguna_p4.py), [snapshot check](evidence/poolside-laguna-p4-snapshot-check-2026-10-23.json), [runner dry-run](evidence/poolside-laguna-p4-runner-readiness-2026-10-23.json), dan [dry-run persiapan](evidence/poolside-laguna-p4-dry-run-2026-10-23.json).
- [Preflight DVWA](evidence/poolside-laguna-p4-dvwa-preflight-2026-10-23.json) dan [review discovery](evidence/poolside-laguna-p4-discovery-review-2026-10-23.json).
- Paket mentah 12 discovery berada pada `results/raw/formal-discovery/poolside-laguna-p4-20261023/` dan setiap report memiliki capture receipt serta hash.
- Smoke Poolside terbaru tersimpan pada `results/raw/poolside-smoke/20261023T081457883186Z.json`; key tidak dimasukkan ke receipt.
- [Konfirmasi peneliti tentang akun baru dan kesiapan provider](evidence/poolside-laguna-p4-provider-confirmation-2026-10-23.json) terikat ke smoke terbaru, formal runner plan, dan protocol candidate.
- [Receipt freeze protokol](evidence/poolside-laguna-p4-freeze-approval-2026-10-23.json) mengikat plan, budget, dan candidate hash; receipt ini menyatakan `formal_execution_approval=false`.
- [Release manifest](evidence/poolside-laguna-p4-release-manifest-2026-10-23.json) berstatus `released`, mengikat 21 gate teknis, dan menyatakan `formal_execution_authorized=false`. SHA-256: `1365dff78ffcdfaf29503007580f23dfbf63f4e0736f37c74c015a889c9c0a63`.
- [Keputusan metode](evidence/poolside-laguna-p4-method-decision-2026-10-23.json) mencatat bahwa Laguna P4 menjadi cohort utama dalam analisis revisi dan Qwen lokal tetap dipisahkan.

## Langkah sebelum request formal pertama

1. Konfirmasi peneliti dan smoke terbaru menutup gate akun untuk persiapan. Saat run, pertahankan batas biaya USD 0 dan hentikan jika provider melaporkan pembatasan, biaya, atau status non-free. Selesaikan run selagi endpoint langsung tersedia. Jangan kirim API key.
2. Freeze protokol dan release manifest selesai. Langkah berikutnya adalah memperoleh receipt persetujuan eksekusi terpisah yang mengikat hash release, plan, budget, protocol, dan batas biaya USD 0.
3. Jalankan P4 hanya setelah persetujuan eksekusi tersedia dan gate formal execution tertutup. Jika quota atau layanan berhenti, hentikan cohort dan pertahankan checkpoint; jangan pindah provider di tengah P4.
4. Setelah kandidat terkunci, buat packet VAL-01 baru. Hitung FPR dan PSR hanya bila cakupan serta tiga replikasi lengkap.

Status mesin terakhir: `blocked-not-execution-ready` karena persetujuan eksekusi
formal belum tersedia. Release manifest berstatus `released`. Uji unit runner
lulus 7/7. Bukti dry-run
melaporkan nol request Poolside atau DVWA, `execution_started=false`,
`credentials_read=false`, dan `openrouter_used=false`.

Pengumuman layanan resmi: [Poolside Platform](https://platform.poolside.ai/).
Keterangan akses gratis sementara: [Poolside Models](https://poolside.ai/models).
