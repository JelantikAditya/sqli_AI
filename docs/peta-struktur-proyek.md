# Peta struktur proyek dan lokasi data

Dokumen ini menjelaskan letak kode, konfigurasi, korpus RAG, data lokal, dan
bukti evaluasi. Path ditulis relatif dari root repository.

## RAG dan korpus pengetahuan

| Isi | Lokasi | Status di Git |
| --- | --- | --- |
| Korpus SQLi terstruktur untuk RAG proposal | `knowledge/sqli-entries.json` | Dilacak |
| Lock sumber, commit, dan hash provenance | `knowledge/sources.lock.json` | Dilacak |
| Schema korpus | `schemas/sqli-knowledge-corpus.schema.json` | Dilacak |
| Validator, pemecah dokumen, dan identitas knowledge base | `dvwa/knowledge_corpus.py` | Dilacak |
| Builder index Chroma utama | `dvwa/build_structured_knowledge.py` | Dilacak |
| Retriever, koneksi Ollama lokal, dan pointer manifest aktif | `dvwa/rag_pipeline.py` | Dilacak |
| Kebijakan seleksi konteks retrieval | `dvwa/retrieval_selection.py`, `dvwa/retrieval_policy.json` | Dilacak |
| Folder vector store Chroma persisten | `data/vectorstore/<knowledge_base_id>/` | Lokal, diabaikan Git |
| Pointer index aktif | `knowledge/active-index.local.json` | Lokal, diabaikan Git |
| Manifest tiap index | `data/vectorstore/<knowledge_base_id>/manifest.json` | Lokal bersama index, diabaikan Git |

Index proposal yang dipakai eksperimen dibangun dari korpus JSON, bukan dari
PDF proposal. Index PDF yang ada di `data/vectorstore/` hanya untuk diagnostik.
Bangun ulang index proposal dengan:

```powershell
.\.venv\Scripts\python.exe dvwa/build_structured_knowledge.py
```

Ollama berjalan lokal, default pada `http://127.0.0.1:11434`. Model bahasa
default adalah `qwen2.5:7b`; model embedding default adalah `nomic-embed-text`.
Nama model, identitas index, provenance, dan chunk retrieval dicatat pada
manifest serta artefak generasi.

## DVWA, protokol, dan eksperimen

| Isi | Lokasi | Status di Git |
| --- | --- | --- |
| Docker Compose DVWA dan database | `dvwa/compose.yaml` | Dilacak |
| Katalog S1-S12, endpoint, teknik, level, label skenario | `dvwa/experiment_scenarios.json` | Dilacak |
| Protokol evaluasi aktif, budget, konfirmasi, reset, dan kondisi | `dvwa/local_experiment_protocol.json` | Dilacak |
| Plan template | `dvwa/local_run_plan.template.json` | Dilacak |
| Plan pilot LangChain S1 A/B yang berhasil | `dvwa/local_run_plan.langchain-pilot-20261014-r3.json` | Dilacak |
| Runner plan, ledger append-only, checkpoint, resume | `dvwa/run_local_experiments.py` | Dilacak |
| Executor HTTP, login, verifikasi sesi/level, baseline, probe | `dvwa/validation_loop.py` | Dilacak |
| Loop adaptif S1, generasi, feedback, analisis, regenerasi | `dvwa/adaptive_s1_loop.py` | Dilacak |
| Chain LangChain serial lokal | `dvwa/langchain_runtime.py` | Dilacak |
| Analisis respons dan klaim Qwen | `dvwa/analyze_response.py` | Dilacak |
| Fungsi policy konfirmasi, keputusan run, dan urutan eksperimen | `dvwa/confirmation_policy.py`, `dvwa/run_decision_policy.py`, `dvwa/execution_order_policy.py` | Dilacak |

Hasil run mentah, payload, respons tersanitasi, ledger, checkpoint, dan log
per-run ditulis ke `results/raw/<dataset>/<experiment_id>/`. Folder
`results/raw/` diabaikan Git karena berisi artefak eksperimen lengkap. Plan
pilot yang perlu reproduksi dan evidence ringkasan tersanitasi disimpan di
Git pada lokasi di atas dan `docs/evidence/`.

Discovery ZAP disimpan lokal di `results/zap/`. File report mentah/normalized
diabaikan Git oleh `results/zap/.gitignore`; evidence menyimpan nama report dan
hash agar provenance bisa diperiksa. Runner menolak report jika hash berubah.

## SecLists

| Isi | Lokasi | Status di Git |
| --- | --- | --- |
| Versi, file sumber, baris, seleksi, dan transformasi yang disetujui | `docs/evidence/seclists-selection-plan-2026-10-12.json` | Dilacak |
| Batch builder dan provenance validator | `dvwa/build_seclists_batches.py`, `dvwa/prepare_candidate_batch.py` | Dilacak |
| Checkout SecLists yang dipin | `results/raw/seclists/<commit>/` | Lokal, diabaikan Git |
| Batch per skenario dan hasil pilot | `results/raw/seclists-batches/`, `results/raw/pilot/` | Lokal, diabaikan Git |

Isi SecLists mentah tidak disalin ke repository. Rencana seleksi dan evidence
pilot yang tersanitasi disimpan pada `docs/evidence/`.

## Ground truth, evidence, dan skema

| Isi | Lokasi | Catatan |
| --- | --- | --- |
| Ground truth skenario DVWA | `docs/ground-truth-2026-10-01.md` | Label eksperimen, bukan label prediksi model |
| Bukti pilot yang disanitasi | `docs/evidence/` | Dapat dilacak Git, tidak berisi cookie atau respons mentah |
| Status T01-T08 terkini | `docs/review-progress-2026-10-14.md` | Ringkasan milestone dan celah |
| Schema plan, ledger, batch, dan evidence | `schemas/` | Kontrak JSON yang dipakai validator |
| Template payload lokal dan konfigurasi autentikasi ZAP | `dvwa/validation_payloads.template.json`, `dvwa/zap-auth.template.yaml` | Template saja, tanpa rahasia |
| Kredensial lokal | `dvwa/.env` | Lokal, jangan commit |

## Dependency dan batas penyimpanan

- Dependency Python tercatat pada `requirements-rag.txt` dan
  `requirements-orchestration.txt`; virtual environment `.venv/` lokal dan
  diabaikan Git.
- Tes unit dan fixture ada di `tests/`; schema kontrak ada di `schemas/`.
- `sources/` adalah material referensi tersinkron dari proyek ChatGPT, bersifat
  read-only dan tidak menjadi bagian perubahan repository.
- Jangan commit `.env`, cookie, database DVWA, model Ollama, Chroma store,
  report ZAP mentah, atau hasil `results/raw/`.

Untuk alur build corpus, retrieval, dan generasi kandidat lihat
[`candidate-sources.md`](candidate-sources.md). Untuk runner dan lingkungan
DVWA lihat [`../dvwa/README.md`](../dvwa/README.md).
