# Penyesuaian RAG terhadap proposal — 7 Oktober 2026

> Snapshot metodologi dan status per 7 Oktober. Review korpus disetujui pada
> 12 Oktober; status aktif ada di [README](../README.md) dan [rencana penyelesaian](rencana-penyelesaian-2026-10-16.md).

## Status dan koreksi korpus sebelumnya

Jalur utama RAG kini membaca entri JSON terstruktur dari dua sumber yang
ditetapkan proposal. Index PDF `sqli-kb-a7b087430b0276aa` dan review sebelumnya
merupakan uji diagnostik, bukan knowledge base final penelitian. Generator
default menolak manifest PDF dan memakai pointer index JSON yang aktif.
PDF pada `sources/` tetap read-only; hash seluruh 15 berkas tidak berubah.

Implementasi serta integrasi Ollama/Chroma sudah diverifikasi lokal. Notebook
Colab memakai korpus/helper yang sama dan sudah diperbarui, tetapi belum
dieksekusi di Colab. Lingkungan formal yang ditulis proposal tetap Colab;
pengujian laptop ini membuktikan jalur lokal, bukan penyelesaian eksperimen TA.

## Sumber dan struktur sesuai proposal

| Sumber | Versi terkunci | Peran |
| --- | --- | --- |
| [OWASP WSTG](https://github.com/OWASP/wstg/tree/v4.2), WSTG-INPV-05 | v4.2, commit `dd33419e10edb22b78d89325a6c2aad9f184e3a2` | Metodologi SQLi dan interpretasi respons |
| [PayloadsAllTheThings SQL Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/tree/3ac27901c711bdf3f5b65a7b1d1820a1f65bd09a/SQL%20Injection) | Commit `3ac27901c711bdf3f5b65a7b1d1820a1f65bd09a` | Pola teknik dan contoh payload, termasuk bagian MySQL |

`knowledge/sources.lock.json` mencatat commit, path upstream, hash sumber,
hash snapshot, dan URL. `dvwa/fetch_knowledge_sources.py` memulihkan snapshot
sesuai lock; script tidak memperbarui commit ke versi terbaru secara otomatis.
Snapshot berada di `data/raw/knowledge-sources/`, terpisah dari `sources/`.

Windows memblokir salinan berkas MySQL lengkap sebagai konten berpotensi
berbahaya. Snapshot yang dipakai hanya memuat tiga bagian yang diperlukan:
error-based, blind, dan time-based. Commit/hash dokumen penuh diverifikasi
sebelum cuplikan dibuat; nomor baris asli dipertahankan. Sistem keamanan Windows
tidak diubah. Snapshot mentah tidak dimasukkan sebagai dokumen embedding.

Korpus `knowledge/sqli-entries.json` berisi sembilan pola, tiga per teknik.
Schema `schemas/sqli-knowledge-corpus.schema.json` mewajibkan enam komponen
proposal: `vulnerability_type`, `functional_semantics`, `root_cause`,
`detection_method`, `payload_examples`, dan `mitigation`. Setiap entri juga
memiliki ID, judul, DBMS, batas interpretasi, serta rujukan bagian/baris sumber.

Entri disusun secara editorial oleh Codex, bukan diekstrak sebagai jendela kata.
Contoh langsung dan adaptasi dibedakan. Kontrol baseline, pengulangan timing,
catatan kompatibilitas, dan rekomendasi mitigasi merupakan sintesis editorial
yang ditandai; bukan kutipan aturan sumber atau hasil DVWA yang terverifikasi.
`researcher_review` masih `pending`. Lisensi/atribusi ada di `knowledge/NOTICE.md`.
Proposal, label ground truth, SecLists evaluasi, dan hasil benchmark paper tidak
menjadi sumber korpus generator.

## Index dan retrieval

| Konfigurasi | Nilai |
| --- | --- |
| Knowledge base ID aktif | `sqli-knowledge-ec9d1b2feda12dd3` |
| Manifest | `data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3/manifest.json` |
| Unit embedding | Satu entri JSON utuh per vector; sembilan entri |
| Embedding | Nomic lokal, prefix document/query, `truncate: false` |
| Vector store | Chroma persisten, cosine |
| Query | `sqli-injection-point-query-v3`; koordinat input dan bukti spesifik teknik |
| Seleksi | Kemiripan semantik atas seluruh korpus, top-k awal 2 |
| Corpus SHA-256 | `8e2aaf363b384eb686594b8968c38ae00fd078cfc9581d6a91d6617ba0ef4348` |
| Source lock SHA-256 | `2c23da42f9db73c3241ca78e68da496b83ecdeb257bc46171e55fd69f3f6278b` |

Tidak ada filter teknik, ekspansi leksikal, atau reranking kata kunci pada jalur
proposal. Top-k 2 dipilih pada pengembangan awal agar konteks ringkas; perubahan
k dapat mengambil teknik lain dan wajib ditinjau sebelum eksperimen. Query
memuat metode, path input, parameter, dan jenis probe; label ground truth serta
level DVWA tidak dimasukkan ke query. Metadata level hanya dipakai untuk
memeriksa kecocokan report ZAP dan skenario.

Jika `--zap-report` diberikan, koordinat harus cocok dengan kandidat pada report
normalized. Jika tidak diberikan, sumber query dicatat `scenario-catalog-smoke`.
Report Low saat ini belum memiliki kandidat yang cocok untuk S1–S3; kode tidak
berpura-pura bahwa koordinat katalog berasal dari ZAP. Report High memiliki
kandidat untuk S8/S9, tetapi status discovery-nya tetap `unverified`, bukan
konfirmasi SQLi.

## Hasil verifikasi akhir

Empat belas unit test lulus, termasuk penolakan label/sumber evaluasi dalam
schema, hash snapshot berubah, rujukan salah, ID duplikat, query tanpa label,
isolasi manifest PDF, deteksi perubahan teks index, serta kontrol generator
RAG-off/on menggunakan model tiruan. Enam test lama tetap menguji jalur
diagnostik PDF; delapan test baru menguji korpus/jalur proposal.

Semua sembilan dokumen dan metadata Chroma cocok dengan entri tervalidasi.
Dengan top-k 2 semantik atas seluruh korpus, hasil akhir:

| Skenario | Asal injection point | Dua entri terambil |
| --- | --- | --- |
| S1 | Katalog smoke | `sqli-error-quote`, `sqli-error-message` |
| S2 | Katalog smoke | `sqli-boolean-numeric`, `sqli-boolean-template` |
| S3 | Katalog smoke | `sqli-time-repeated`, `sqli-time-conditional` |
| S8 | Report ZAP High | `sqli-boolean-numeric`, `sqli-boolean-template` |
| S9 | Report ZAP High | `sqli-time-repeated`, `sqli-time-conditional` |

Semua hasil pada lima query ini sesuai teknik yang diminta tanpa filter teknik.
Ini pemeriksaan pengembangan, bukan benchmark retrieval atau bukti penurunan
FPR. Ringkasan beserta path record aktual tersimpan di
`outputs/proposal-rag/verification-2026-10-07.json`.

Generator lokal menggunakan index proposal secara default, konteks entri utuh,
dan mencatat query, asal injection point, sumber, hash kebijakan, serta korpus
dalam audit. Prompt versi `sqli-candidate-v2` memakai context 4.096 dan batas
output 768 token; parameter harus sama pada pasangan RAG-off/on. Pengujian
kontrol generator menggunakan mock, belum menjalankan generasi Qwen dengan
konteks RAG ini. Kecukupan budget token aktual tetap diperiksa saat smoke
generasi. Tidak ada kandidat nyata atau request DVWA baru pada tahap ini.

## Menjalankan ulang dan Colab

```powershell
.\.venv\Scripts\python.exe dvwa/fetch_knowledge_sources.py
.\.venv\Scripts\python.exe dvwa/build_knowledge_base.py --batch-size 3
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S1
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S8 --zap-report results/zap/zap-discovery-high-20261001-220810.normalized.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pointer `knowledge/active-index.local.json` dibuat hanya setelah build selesai.
Hash korpus/lock/snapshot diperiksa sebelum build/retrieval; perubahan korpus
memerlukan build dengan identitas baru. Snapshot sumber yang baru tidak boleh
ditandai sebagai versi lama. Mode PDF tersedia hanya dengan
`build_knowledge_base.py --experimental-pdf` serta mode retrieval diagnostik
`focused` atau `legacy` dan manifest eksplisit.

Notebook `notebooks/colab_langchain_setup.ipynb` kini memvalidasi JSON, memakai
helper prefix Nomic/query yang sama, menjalankan pencarian semantik global
melalui LangChain, dan menyimpan ZIP Chroma di Drive. Seluruh cell kode lulus
compile statis; ini tidak membuktikan dependensi atau eksekusi Colab berhasil.
Bundle kode/korpus yang diperlukan tersedia di
`outputs/proposal-rag/colab-proposal-rag.zip`. Ekstrak folder `dvwa/`, `schemas/`,
dan `knowledge/` ke `MyDrive/TA-SQLi/project-code/`, lalu buka notebook dari
bundle. Bundle tidak memuat `.env`, token, PDF, vector store, atau report ZAP.
ZIP merupakan artefak lokal. Setelah clone repository, bangun ulang dengan
`python dvwa/package_colab_rag.py`; seluruh input paket tersedia dalam Git.
Ringkasan verifikasi yang disanitasi ada di
[`evidence/progress-2026-10-07.json`](evidence/progress-2026-10-07.json).

Langkah berikutnya: review peneliti atas sembilan entri, smoke generasi Qwen
dengan konteks aktual, dan verifikasi runtime Colab. Setelah konfigurasi
dibekukan, lanjutkan pasangan kandidat dan evaluasi DVWA. FPR/PSR belum diukur.
