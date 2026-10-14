# Kontrak analisis respons Qwen dan ringkasan per run

Tanggal: 12 Oktober 2026.
Status: kontrak, schema, normalizer, runner adaptif S1, pengujian offline, dan
pilot model nyata A/B tersedia. Pilot ini belum merupakan eksperimen formal.

## Tiga keluaran berbeda

1. **Observasi HTTP:** fakta dari executor, dengan ID netral, role, nomor trial,
   status HTTP, waktu, hash respons, diagnostik eksplisit, serta marker konten.
2. **Analisis kandidat:** klaim Qwen beserta ID evidence, alasan singkat,
   reason_code, dan usulan tindakan berikutnya.
3. **Ringkasan run:** kelengkapan budget, jumlah kandidat, keputusan sistem
   per skenario-kondisi-replikasi, serta link hash ke record kandidat.

Qwen tidak menghitung FPR/PSR atau memilih ground truth. Evaluator menggabungkan
record setelahnya. Tiga konfirmasi HTTP dalam satu kandidat berbeda dari tiga
run independen yang dirata-ratakan menurut keputusan per-run averaging.

## Input yang boleh diterima model

Schema: schemas/qwen-analysis-input.schema.json.

Input memuat teknik, metode/path/parameter, runtime_status, baseline_valid,
ambang timing, dan observations. Setiap trial memiliki satu baseline serta:

| Teknik | Observasi lain per trial |
| --- | --- |
| Error-based | candidate |
| Boolean blind | true_condition dan false_condition |
| Time blind | candidate dan no_delay_control |

ID observasi berbentuk obs-001, obs-002, dan seterusnya. Hash respons tetap
dicatat untuk traceability. Tidak ada raw HTML, nilai cookie/token, record
pengguna, SQL di sekitar pesan error, atau header autentikasi pada prompt.

Input tidak menerima scenario_id, level keamanan, condition_id, sumber
kandidat, mode RAG, ground_truth atau expected outcome. Metadata itu dimasukkan
oleh wrapper ke ledger internal, bukan oleh model.

Allowlist diagnostik v1 mencakup mysql_syntax_error, mysql_xpath_error, dan
mysql_unknown_column. Nama mysqli_sql_exception atau PDOException saja tidak
menjadi indikator. Ini matcher terbatas; kecukupan signature lain perlu
ditinjau dalam pilot, lalu dibekukan sebelum formal.

## Output model

Schema: schemas/qwen-analysis-output.schema.json.

Contoh bentuk output yang diharapkan untuk evidence diagnostik baru:

```json
{
  "decision": "positive",
  "reason_code": "new_database_diagnostic",
  "reason": "Kandidat menampilkan diagnostik sintaks SQL yang tidak ada pada baseline.",
  "evidence_refs": ["obs-001", "obs-002"],
  "feedback_action": "none"
}
```

Contoh ini menjelaskan kontrak, bukan hasil formal.

| Field | Makna |
| --- | --- |
| decision | positive: indikator kandidat muncul; negative: indikator tidak terpenuhi pada evidence valid; inconclusive: evidence/kontrol belum memadai. |
| reason_code | Kode alasan yang sesuai teknik, misalnya new_database_diagnostic atau no_new_database_diagnostic. |
| reason | Penjelasan singkat yang bisa diaudit, bukan skor atau bukti tersendiri. |
| evidence_refs | ID observasi yang benar-benar disediakan executor. Positive/negative memerlukan setidaknya satu ID; audit dukungan positif memeriksa pasangan pembandingnya. |
| feedback_action | none, revise_candidate, atau collect_more_evidence. Ini usulan, belum mengeksekusi regenerasi atau request baru. |

HTTP 200 dapat membawa pesan SQL error di body. HTTP 500 tanpa diagnostik
tidak cukup. Kandidat tanpa diagnostik baru pada pasangan error-based yang
valid diberi negative; ini tidak menyatakan aplikasi secara keseluruhan aman.

Prompt aktif sejak 14 Oktober adalah sqli-response-analysis-v4. Instruksi dan pilihan reason_code
dibatasi ke teknik yang sedang dianalisis agar model tidak memakai indikator
boolean/timing untuk menilai error-based.

## Ledger kandidat dan integritas

Schema: schemas/analysis-ledger.schema.json, kandidat versi 1.1.0 dan ringkasan run 1.2.0.
Implementasi: dvwa/analyze_response.py.

- context dipasang wrapper: experiment/run/attempt/candidate ID, scenario,
  replicate, condition, source dan rag_mode. Tidak ada label ground truth di
  record yang diberikan ke model.
- evidence menyimpan input yang disanitasi, bukan hanya kesimpulan model.
- model_output, system_claim, dan qwen_claim mempertahankan hasil Qwen,
  termasuk INCONCLUSIVE/null ketika keputusan biner belum tersedia.
- rule_signal dan evidence_status mencatat CONSISTENT_POSITIVE hanya pada
  3/3 konfirmasi, MIXED_EVIDENCE pada 1/3 atau 2/3, dan CONSISTENT_NEGATIVE
  pada 0/3. Runtime invalid dan konfirmasi tidak lengkap memiliki status terpisah.
- confirmed_success, valid_confirmation_count, dan positive_confirmation_count
  merekam hasil policy. Mixed evidence tetap kandidat valid pada penyebut PSR.
- claim_supported mensyaratkan 3/3 dan referensi ketiga pasangan pembanding.
  Ini flag audit, bukan filter klaim.
- analysis_warnings menandai reason_code yang bertentangan dengan decision
  atau teknik. Klaim positive tetap dipertahankan.
- audit mencatat hash input/output, versi/hash prompt, schema decoding, opsi
  model, sumber evidence dan token/durasi jika tersedia.
- human_validation tetap pending. Model tidak dapat mengisi label manusia.

Sejak keputusan T01 pada 14 Oktober, runner tidak menjalankan putaran
konfirmasi tambahan meskipun model meminta collect_more_evidence. Hasil dan
permintaan asli disimpan, kemudian evidence dipakai untuk kandidat baru.
Lihat [keputusan konfirmasi](keputusan-konfirmasi-kandidat-2026-10-14.md).
Pilot dan angka pengujian bertanggal 12 Oktober di bawah tetap catatan historis.

Keputusan run kini mengikuti any-positive-else-abstain-v1. Positive mendahului
inconclusive pada run lengkap; negative mensyaratkan semua klaim negative.
Ringkasan memisahkan execution_status dari binary_decision_eligible dan
psr_evidence_eligible. Inconclusive tidak menjadi TN/FN atau memicu run baru.
FPR utama membutuhkan seluruh unit negatif terencana yang evaluable/biner;
helper evaluator melaporkan coverage dan diagnostik subset secara terpisah.
Lihat [keputusan run](keputusan-run-inconclusive-2026-10-14.md).

Ringkasan memeriksa ulang schema, hash, konteks, dan semantik record sehingga
perubahan system_claim atau evidence sesudah normalisasi terdeteksi.

JSON/schema model tidak valid menghasilkan analysis_error, bukan negative.
Teks model asli disimpan pada audit lokal, termasuk jika JSON/schema tidak
valid, agar klaim yang tidak dapat dinormalisasi tetap dapat diperiksa.
ID evidence yang tidak dikenal menghasilkan invalid_evidence_reference;
output dan klaim tetap tercatat, tetapi run belum dapat digunakan sebagai
hasil lengkap sampai masalahnya diselesaikan. Jumlah kegagalan analisis harus
dilaporkan agar data yang tidak lengkap tidak tersamarkan.

Klaim positive dengan ID valid tetapi tanpa sinyal pendukung tetap dihitung
sebagai klaim positive sistem. Bila evaluator memberi ground truth negatif,
kejadian tersebut menjadi FP. Menghapusnya karena validator menolak bukti
akan mengubah FPR secara tidak sah.

## Keputusan per run dan kaitannya dengan metrik

Usulan operasional v1 untuk menggabungkan kandidat di dalam satu run:

- Ada setidaknya satu klaim positive: keputusan run positive.
- Tidak ada positive, tetapi ada inconclusive: keputusan run inconclusive.
- Semua kandidat negative: keputusan run negative.
- Budget eksekusi/analisis belum lengkap atau ada error analisis/runtime:
  ringkasan not_evaluable dengan status incomplete; semua klaim kandidat tetap
  tersimpan. Perbaiki/ulang sesuai ledger, jangan ubah menjadi negative.

Aturan ini hanya menggabungkan kandidat dalam satu run. Tidak ada voting
antar Run 1/2/3. Keputusan penggabungan ini perlu dinilai pada pilot sebelum
freeze formal.

Run summary memakai candidate_id __run__ sebagai penanda record agregat.
valid_executed_count menghitung kandidat logis: pasangan boolean tetap satu.
budget_complete berbeda dari kesiapan analisis dan kesiapan validasi manusia.

| Keluaran untuk evaluator | Penggunaan |
| --- | --- |
| system_decision per run lengkap | Dibandingkan dengan ground truth evaluator untuk TP/FP/TN/FN. |
| valid_executed_count | Bahan audit penyebut PSR, setelah ledger/formal eligibility ditetapkan. |
| Keputusan validator per kandidat | Pembilang PSR final; belum tersedia pada kontrak pengembangan ini. |
| Run/replicate/condition ID | Mengelompokkan metrik tiap run lalu mean dan SD sampel dari tiga replikasi. |

psr_success_count dan psr sengaja null selama human_validation pending.
Jumlah positive Qwen tidak disamakan dengan jumlah payload berhasil yang
disetujui validator. FPR per kelompok tanpa kontrol negatif tetap undefined.

Scope semua record tahap ini development-analysis-contract. Status complete
di ledger hanya berarti budget dan analisis lengkap menurut kontrak ini;
bukan bukti seluruh formal_gate, konfirmasi atau human validation selesai.

## Kebijakan RAG pada analisis

Analisis respons v1 menggunakan prompt dasar, schema, model, seed dan opsi
yang sama pada A/B. Analisis tidak mengambil konteks Chroma di kedua kondisi.
Perlakuan RAG tetap berada pada generator kandidat yang sudah tersedia.
Perbedaan observasi akibat kandidat berbeda dapat menghasilkan keputusan
analisis berbeda.

Jika RAG juga akan digunakan pada tahap analisis/feedback, tetapkan sebagai
perubahan versi protokol dan tambahkan audit retrieval. Jangan mencampur
hasil kedua kebijakan ke satu dataset formal tanpa definisi eksperimen baru.

## Replay evidence S1 yang sudah tersedia

```powershell
.\.venv\Scripts\python.exe dvwa/analyze_response.py --smoke-evidence results/raw/evidence-s1-pair-20261011T112013Z-6d6994fc.json --rag-mode off
```

Perintah tersebut hanya mengekspor input yang disanitasi. Tambahkan
--call-model untuk melakukan inferensi Ollama lokal; ganti off dengan on
untuk evidence kondisi lain. Output lokal disimpan pada results/raw/ yang
diabaikan Git. Tidak ada request HTTP ke DVWA pada CLI ini.

Adapter hanya mendukung dua receipt S1 yang tersimpan: satu baseline dan satu
kandidat. Adapter tidak mengarang konfirmasi, matched control, atau replikasi
baru. Ia tidak merekonstruksi validitas sesi setiap respons dari body mentah.
Karena itu replay ini merupakan smoke kontrak, bukan pilot formal lengkap.
Expected budget tetap 10; replay satu kandidat menghasilkan status incomplete.

## Pekerjaan selanjutnya

1. Selesaikan reset database, pemulihan runtime, dan kontrol lengkap T03 sebelum
   memperluas pemakaian runner.
2. Siapkan batch dan pilot pembanding SecLists untuk T04.
3. Perluas orchestrator serta ledger attempt, checkpoint dan resume pada T05.
4. Tambahkan paket human validation dan agregator PSR/FPR mean/SD pada T06.
5. Jalankan pilot semua teknik/level, tinjau hasil, lalu penuhi gerbang freeze
   formal pada T07-T08.

Rancangan ini tidak menetapkan corpus_researcher_review atau validator selesai,
tidak mengubah hasil/manifest lama, dan tidak membuat klaim kinerja penelitian.

## Bukti replay lokal 12 Oktober

Ringkasan yang disanitasi ada di evidence/qwen-analysis-2026-10-12.json.
Evidence HTTP berasal dari pasangan S1 pada 11 Oktober, bukan eksekusi baru.
Prompt analisis final v3 memakai seed 42, temperatur 0, context 4096, output
maksimum 768 token, dan Qwen 2.5 7B yang sama pada kedua kondisi.

| Evidence lama | Label Qwen v3 | Reason code | Referensi | Status run |
| --- | --- | --- | --- | --- |
| RAG-off: tanpa diagnostik baru | negative | no_new_database_diagnostic | baseline dan candidate | incomplete, 1/10 kandidat |
| RAG-on: diagnostik sintaks baru | positive | new_database_diagnostic | baseline dan candidate | incomplete, 1/10 kandidat |

Kedua output memenuhi schema dan referensi evidence. Labelnya sesuai sinyal
pada receipt yang tersedia. Alasan bebas teks masih perlu human review:
jawaban negative mengaitkan HTTP 200 dengan tidak adanya error, padahal
HTTP 200 sendiri tidak membuktikan hal tersebut. Normalizer tidak menganggap
alasan model sebagai fakta tambahan atau hasil validasi manusia.

Prompt pengembangan awal menghasilkan abstention dan satu ketidaksesuaian
decision/reason. Artefak awal tetap disimpan lokal dan tidak digabungkan ke
pasangan final. Versi prompt dipisahkan agar perubahan tidak tersamar.

46 unit test dan parsing sintaks 27 file Python lulus. Pemeriksaan mencakup
sanitasi, isolasi label, kondisi/skenario, referensi, integritas, kegagalan model,
runtime invalid, kandidat duplikat, budget dan pemisahan replikasi. Dua record
final dan dua summary lolos schema serta hasil normalisasi ulang identik.
Tidak ada PSR/FPR formal yang dihitung atau request baru dikirim ke DVWA.

## Pilot loop adaptif lokal S1 pada 12 Oktober

Runner `dvwa/adaptive_s1_loop.py` memverifikasi discovery ZAP dan form S1
langsung, login baru, level Low, serta sesi sebelum dan sesudah setiap pasangan
baseline/kandidat. Ia mengirim tiga pasangan untuk setiap kandidat, menyimpan
hash respons dan marker diagnostik allowlist, lalu meminta Qwen menganalisis
evidence tanpa body HTML atau label evaluator. Pada kandidat selanjutnya,
prompt generator memuat keputusan, evidence terstruktur, dan nilai yang sudah
dicoba. RAG-on memakai retrieval hanya saat generasi; RAG-off tidak membaca
vector store.

Bukti yang disimpan dalam Git ada di
`docs/evidence/adaptive-s1-pilot-2026-10-12.json`. File run dan JSONL penuh
disimpan lokal dalam `results/raw/`, yang diabaikan Git. Hasil ringkasnya:

| Kondisi | Kandidat 1 | Kandidat 2 setelah feedback | Ringkasan run |
| --- | --- | --- | --- |
| A, RAG-off | negative, 0/3 diagnostik baru | positive, 3/3 diagnostik baru, evidence mendukung | incomplete, 2/10 |
| B, RAG-on | positive, 3/3 diagnostik baru, evidence mendukung | negative, 0/3 diagnostik baru | incomplete, 2/10 |

Keputusan kedua kandidat konsisten dengan sinyal diagnostik pada pilot ini.
RAG-off pada kandidat pertama menghasilkan `feedback_action: none`; runner
tetap melanjutkan karena protokol memakai fixed budget dan memasukkan klaim
negative beserta evidence ke prompt regenerasi. Pilot menunjukkan bahwa
keputusan per kandidat dapat dihitung dan ditelusuri, tetapi ringkasan run
tetap `not_evaluable` karena dua kandidat belum memenuhi budget sepuluh.
Karena itu belum ada angka PSR/FPR yang boleh dilaporkan dari pilot ini.

Kedua run memakai Qwen 2.5 7B, seed 42, discovery S1 Low yang sama, tiga
konfirmasi, dan 42 request HTTP termasuk pemeriksaan sesi dan login per run.
Kondisi A tidak mengambil chunk RAG; kondisi B memakai dua chunk dari
`sqli-knowledge-ec9d1b2feda12dd3`. Reset database tidak dilakukan pada runner
pengembangan ini. Human validation tetap pending. Seluruh 51 unit test lulus.
