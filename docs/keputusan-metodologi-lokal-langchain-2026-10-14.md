# Keputusan T01: metodologi laptop lokal dan peran LangChain

Tanggal: 14 Oktober 2026.
Dasar otorisasi: peneliti meminta melanjutkan finalisasi metodologi lokal dan
peran LangChain. Keputusan operasional di bawah ditetapkan dalam lingkup itu.
Protokol tahap keputusan metode: local-sqli-v4-pilot, status pilot.
Kelanjutan penutupan T01 memakai local-sqli-v5-pilot; keputusan metode tetap berlaku.
Status bagian T01 ini: keputusan metode selesai; implementasi framework lokal
dan pembuktiannya tetap T02/T05/T07, kemudian freeze T08.

## Dasar penyesuaian proposal

Proposal asli Bab 3 bagian 3.3, halaman tercetak 28-30 (halaman PDF 29-31),
menempatkan Ollama, RAG dan LangChain pada Colab, dengan DVWA pada laptop
melalui tunnel. LangChain disebut sebagai penghubung hasil ZAP dan penalaran
LLM. Arahan peneliti pada 11 Oktober memindahkan jalur aktif ke laptop lokal.

Dokumen sumber tetap read-only. Penyesuaian ditulis dalam naskah baru:
[metodologi lokal](metodologi-lokal-2026-10-14.md). Bagian proposal yang perlu
diselaraskan adalah rencana implementasi halaman 9, lokasi embedding/vector
store halaman 27, tabel/topologi lingkungan halaman 28-30, serta uraian
kontrol reset dan evaluasi halaman 33-35.

Scope tetap DAST/black-box pada DVWA Low/Medium/High/Impossible, error-based,
boolean-based blind dan time-based blind. FPR ablasi A/B dan PSR B/C tetap
pertanyaan evaluasi utama. Perubahan lokasi runtime tidak menjadi variabel
tambahan yang dibandingkan dan hasil lama Colab tidak digabung ke data formal.

## Keputusan lingkungan

Seluruh proses eksperimen aktif berlangsung pada satu laptop: DVWA/MariaDB
dan ZAP dalam Docker, serta Python, Ollama dan Chroma pada host lokal.
Host mengakses DVWA melalui http://127.0.0.1:4280; ZAP container dapat
mengakses service DVWA melalui jaringan Docker terisolasi. Hasil disimpan di
disk lokal dalam direktori pilot/formal yang terpisah. Colab, tunnel, dan
penyimpanan Drive merupakan jalur terdahulu yang ditunda.

Konfigurasi model awal tetap Qwen 2.5 7B melalui Ollama, temperature 0,
num_ctx 4096, num_predict 768, seed 42/43/44. Pilot lokal menggunakan
quantization Q4_K_M menurut catatan 7 Oktober; digest model, versi Ollama,
penempatan CPU/GPU, serta manifest runtime aktual dibekukan pada T08.
Keberhasilan smoke/pilot lokal membuktikan kelayakan komponen/subset,
bukan bahwa seluruh matriks formal sudah selesai atau sepenuhnya muat di GPU.

Baseline perangkat untuk revisi Tabel 3.1:

| Komponen | Nilai | Status sumber |
| --- | --- | --- |
| CPU | Intel Core i5-11400H | Proposal dan pemeriksaan proyek 7 Oktober; belum diukur ulang pada sesi ini. |
| RAM | Terpasang 16 GB; sekitar 15,7 GiB terdeteksi | Catatan 7 Oktober; belum diukur ulang pada sesi ini. |
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU | Dibaca ulang melalui nvidia-smi pada 14 Oktober. |
| VRAM | 4096 MiB | Dibaca ulang pada 14 Oktober. |
| Sistem operasi | Windows 11 | Proposal/catatan lingkungan; build aktual perlu dicatat saat T08. |
| Penyimpanan hasil | Disk laptop lokal | Metode yang ditetapkan; kapasitas tersedia dan lokasi backup dicatat saat T08. |

Pemeriksaan CIM CPU/RAM/OS tidak tersedia dalam sesi ini. Nilai null atau
nol turunan dari kegagalan pembacaan tidak dipakai sebagai spesifikasi.
Metadata model Ollama saat ini belum bisa diakses dari sesi review (URLError);
ini tidak menetapkan bahwa model tidak terpasang atau tidak dapat dijalankan.
Tidak dilakukan startup layanan, inferensi, scan, atau reset untuk keputusan ini.

## Peran LangChain yang ditetapkan

**LangChain tetap dipertahankan, dijalankan lokal, dan bertugas menyusun
pipeline LLM secara serial.** Lapisan yang direncanakan memakai langchain-core
dengan RunnableLambda/RunnableSequence untuk mengomposisikan fungsi yang
sudah tersedia. RunnableSequence meneruskan output suatu tahap ke tahap
berikutnya secara berurutan, sebagaimana
[referensi resmi Runnables](https://reference.langchain.com/python/langchain-core/runnables/base)
dan [kode sumber resmi](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/runnables/base.py).

| Komponen | Tanggung jawab yang ditetapkan |
| --- | --- |
| Python runner | Mengatur scenario/condition/replicate, seed, budget, attempt, deduplikasi, retry terbatas, checkpoint/resume dan ledger. |
| LangChain lokal | Menyusun tahap konteks/prompt, generasi kandidat, dan analisis respons Qwen dalam chain serial yang dipanggil controller. |
| Adapter RAG | Memanggil helper retrieval terstruktur yang sudah ada; mempertahankan serialisasi JSON, prefix Nomic, hash index, metric cosine dan top-k. |
| Ollama | Menjalankan Qwen dan embedding Nomic lewat API lokal dengan opsi yang tercatat. |
| Chroma | Menyimpan index persisten dari korpus JSON terstruktur yang telah direview. |
| HTTP executor | Mengelola login, level, token/helper, baseline, reset, pasangan boolean/timing, tiga konfirmasi dan status runtime. |
| Evaluator/validator | Mengakses ground truth, mengaudit klaim dan bukti, melakukan anotasi dan menghitung metrik. |

LangChain membungkus fungsi yang ada agar alur antar tahap dapat diperiksa.
Integrasi tidak mengganti transport Ollama atau adapter Chroma dengan default
wrapper yang dapat mengubah prompt, prefix embedding, retrieval atau token
budget. Paket langchain-ollama/langchain-chroma tidak menjadi keharusan
metode ini; jika nanti dipakai, kesetaraan adapter harus dibuktikan sebelum freeze.

Tidak ada agent yang bebas memilih tool, target, budget atau retry. Semua
request DVWA hanya dilakukan executor pada target lab. Chain dipanggil
secara serial, tanpa menjalankan batch inferensi berbarengan dengan probe.
Konfirmasi tambahan, automatic retry chain, external tracing dan unggah log
ke layanan tracing eksternal dinonaktifkan pada jalur formal.

## Kebijakan RAG dan kesepadanan A/B

- A/B menggunakan chain, model/quantization, template prompt dasar, seed,
  limit token, analisis respons, executor dan policy feedback yang sama.
- B melakukan retrieval satu kali sebelum loop kandidat tiap condition-run,
  top-k awal 2, dari injection point ZAP yang sudah diverifikasi. Konteks itu
  dipakai untuk generasi awal dan regenerasi yang menerima feedback.
- A melewati retrieval dan tidak membuka manifest/index/vector store.
- Analisis respons Qwen tidak melakukan retrieval pada kedua kondisi.
  RAG-off dan RAG-on memiliki prompt analisis yang sama.
- Scope ablasi adalah tambahan knowledge-level context pada generasi/regenerasi.
  Pengaruh pada FPR berasal dari jalur itu dan respons/klaim yang dihasilkan;
  penelitian ini tidak menguji retrieval saat analisis sebagai faktor terpisah.
- Ground truth, level keamanan dan scenario ID berada pada metadata executor/
  evaluator, bukan pada input generasi atau analisis model. Cookie/token/raw
  response disaring sesuai kontrak sanitasi.

Pembanding C memakai batch SecLists yang sudah dikunci, executor dan budget
yang sama. C tidak menggunakan model/retrieval; kesepadanannya berupa kontrol
eksekusi dan kandidat logis, bukan jumlah panggilan LLM.

## Status nyata implementasi dan kriteria pembuktian

Pemeriksaan kode sebelum pemasangan dependency pada 14 Oktober menunjukkan helper lokal memakai HTTP Ollama
dan Chroma langsung dari Python. Import LangChain hanya ditemukan pada
notebook Colab yang ditunda. Paket langchain, langchain-core, langchain-ollama
dan langchain-chroma tidak ditemukan pada interpreter proyek yang diperiksa.

Karena itu keputusan metode tidak disebut sebagai integrasi yang sudah
berjalan. implementation_readiness.local_langchain tetap pending. Daftar
formal_gate menambahkan local-langchain-integration-verified. Pemeriksa
protokol menolak freeze jika marker integrasi masih pending. Mengubah marker
menjadi verified saja bukan bukti kesiapan; T08 tetap memerlukan audit artefak.

Pembaruan setelah keputusan ini: langchain-core 1.6.10 sudah dipasang di
`.venv` proyek dan smoke RunnableSequence lokal berhasil. Pip check dan
96 test proyek lulus; tidak ada paket lama yang diganti versinya. Smoke
tersebut tidak memakai model, DVWA atau tracing eksternal. Library siap
diimpor, tetapi adapter pada jalur utama masih belum diintegrasikan. Status
implementation_readiness.local_langchain tetap pending. Lihat
[bukti pemasangan](evidence/langchain-core-install-2026-10-14.json).

T02/T05 harus menghasilkan bukti berikut:

1. Adapter chain lokal terpasang dan dipanggil pada alur utama, dengan versi
   dependency dan hash kode tercatat. Memasang paket saja tidak cukup.
2. Input/output prompt dan opsi model setara dengan helper saat ini, serta
   RAG-off terbukti tidak memanggil retrieval/vector store.
3. Satu alur S1 nyata A/B menjalankan discovery, generasi, tiga konfirmasi,
   analisis, feedback dan kandidat baru sampai budget pilot yang ditetapkan.
4. Executor mempertahankan pengukuran HTTP serial tanpa inferensi model
   bersamaan, kontrol runtime, reset dan pencatatan attempt.
5. Runner matriks memanggil chain yang sama dengan histori kandidat dan
   checkpoint/resume yang dapat diaudit; bukan hanya batch awal sekali.

Perluasan seluruh teknik/level dan paket validasi tetap T07/T06. Versi final
langchain-core dipilih setelah integrasi diuji, kemudian dibekukan pada T08;
tidak dicantumkan versi paket yang belum terpasang sebagai fakta runtime.

## Status T01 dan langkah berikutnya

Metodologi lokal dan peran LangChain telah ditetapkan serta dicatat pada
protokol v4. Bagian ini selesai pada tingkat keputusan T01. Draft narasi naskah
tersedia pada metodologi-lokal-2026-10-14.md; proposal sumber tidak diubah.

Keputusan urutan kondisi A/B/C kemudian ditutup pada
[penutupan T01](keputusan-urutan-kondisi-2026-10-14.md).
Integrasi lokal LangChain dan pipeline adaptif tetap pekerjaan implementasi,
bukan alasan menulis bahwa metode sudah terbukti end-to-end.

Pembaruan implementasi pada 14 Oktober: `dvwa/langchain_runtime.py` kini
menjalankan tahap serial dengan `RunnableSequence`, concurrency satu, dan
LangSmith tracing nonaktif. Generasi kandidat adaptif dan analisis Qwen memakai
chain tersebut. Runner S1 A/B juga diarahkan ke loop adaptif, dengan evidence
konfirmasi dan ledger klaim Qwen disimpan terpisah. Observer S1 memanggil
`execute_candidate` yang sama dengan runner validasi, dan executor kini
mengklasifikasikan respons login/401/403 sebagai kegagalan sesi. Perubahan ini
belum dijalankan pada Ollama/DVWA lokal; karena itu
`implementation_readiness` tetap `pending` dan formal gate belum terpenuhi.

Verifikasi akhir: **96 test lulus**, 40 file Python lulus parsing, 11 definisi
schema valid dan matriks tetap 99 condition-run. Ringkasan pembacaan sumber,
status paket/hardware serta hasil offline tersedia pada
[evidence T01](evidence/t01-local-methodology-2026-10-14.json). Hash pada evidence
diambil sesudah dokumen dan kode final disimpan.
