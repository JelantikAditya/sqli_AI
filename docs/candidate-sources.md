# Menyiapkan kandidat LLM dan SecLists

## Tujuan

`dvwa/prepare_candidate_batch.py` memeriksa satu batch untuk satu skenario dan
satu kondisi sumber/RAG, lalu mengubahnya ke format yang diterima runner.
Kandidat dan provenance disimpan di `results/raw/`, sehingga file tersebut
tidak masuk Git. Normalizer ini tidak mengunduh SecLists. Pipeline RAG dan
generator LLM ada di `dvwa/build_knowledge_base.py`,
`dvwa/retrieve_knowledge.py`, dan `dvwa/generate_candidate_batch.py`.

Skrip lokal memakai API Ollama dan Chroma untuk memverifikasi RAG proposal.
Notebook [`colab_langchain_setup.ipynb`](../notebooks/colab_langchain_setup.ipynb)
memakai LangChain dengan korpus JSON, validator, prefix Nomic, dan query yang
sama. Kode/korpus ditempatkan di `MyDrive/TA-SQLi/project-code/`; sumber resmi
terkunci dipulihkan ke disk runtime. Drive menyimpan ZIP Chroma pada
`chroma-archives/` dan manifest di `knowledge-base-manifests/`. Database
berjalan dari `/content`, tidak langsung dari mount Drive. Notebook belum
dijalankan di Colab. Lihat [penyesuaian proposal](proposal-rag-2026-10-07.md).

Kontrak batch ada di [`../schemas/candidate-batch.schema.json`](../schemas/candidate-batch.schema.json).
Validasi tambahan memastikan pasangan payload sesuai jenis skenario, jumlah
kandidat maksimal 10, sumber metadata lengkap, dan mode RAG tercatat konsisten.

## Menyiapkan knowledge base dan retrieval

Instal dependensi pada virtual environment dan siapkan model lokal sesuai proposal:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-rag.txt
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
```

Pastikan Ollama berjalan, pulihkan snapshot resmi sesuai commit/hash yang
terkunci, lalu bangun korpus JSON proposal:

```powershell
.\.venv\Scripts\python.exe dvwa/fetch_knowledge_sources.py
.\.venv\Scripts\python.exe dvwa/build_knowledge_base.py --batch-size 3
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S1 --top-k 2
```

Sumber terbatas pada OWASP WSTG v4.2 dan PayloadsAllTheThings bagian SQL
Injection. Entri ada di `knowledge/sqli-entries.json`, schema di
`schemas/sqli-knowledge-corpus.schema.json`, dan versi sumber di
`knowledge/sources.lock.json`. Setiap pola memuat enam komponen proposal,
rujukan bagian/baris, dan penandaan adaptasi. Researcher review masih pending.
Proposal, PDF paper, dan SecLists evaluasi tidak menjadi korpus generator.

Satu entri JSON utuh menjadi satu vector Nomic (`search_document:`), dengan
query memakai `search_query:` dan API `truncate: false`. Chroma memakai cosine
similarity atas seluruh entri; default top-k 2, tanpa filter teknik atau
reranking leksikal. Query memuat injection point dan bukti spesifik teknik,
serta tidak memuat label ground truth/level. Manifest menyimpan hash korpus
serta lock; pointer `knowledge/active-index.local.json` memilih index utama.
Vector store disimpan di `data/vectorstore/` dan diabaikan Git.

Tanpa `--zap-report`, koordinat berasal dari katalog dan dicatat sebagai
`scenario-catalog-smoke`. Untuk report ZAP normalized yang memiliki kandidat
cocok, misalnya S8 pada report High yang tersedia:

```powershell
.\.venv\Scripts\python.exe dvwa/retrieve_knowledge.py --scenario S8 --zap-report results/zap/zap-discovery-high-20261001-220810.normalized.json
```

Jika kandidat tidak ada atau level/koordinat tidak cocok, script menolak
report tersebut. Status kandidat ZAP tidak otomatis menjadi konfirmasi SQLi.
Hasil dan provenance disimpan di `results/raw/`. Jika memakai port Ollama lain,
set `OLLAMA_BASE_URL` pada alamat loopback.

Index PDF sebelumnya hanya diagnostik. Build PDF memerlukan
`--experimental-pdf`; retrieval-nya memerlukan manifest eksplisit dan mode
`focused`/`legacy`. Generator proposal menolak manifest PDF. Rincian sumber,
verifikasi, serta instruksi Colab ada di
[catatan penyesuaian](proposal-rag-2026-10-07.md).

## Menghasilkan pasangan kandidat LLM RAG-off/RAG-on

Gunakan `comparison_id` dan `seed` yang sama untuk kedua kondisi. Contoh
berikut menghasilkan batch berbeda untuk S1:

```powershell
python dvwa/generate_candidate_batch.py `
  --scenario S1 `
  --rag-mode off `
  --comparison-id s1-low-error-pair01 `
  --seed 42 `
  --candidate-count 1

python dvwa/generate_candidate_batch.py `
  --scenario S1 `
  --rag-mode on `
  --comparison-id s1-low-error-pair01 `
  --seed 42 `
  --candidate-count 1 `
  --top-k 2
```

RAG-on memakai index JSON aktif; `--manifest` dapat menunjuk manifest JSON
secara eksplisit. `--zap-report` diterima untuk mencatat injection point yang
sama pada kedua kondisi. Gunakan `--num-ctx 4096` dan top-k 2 sebagai
konfigurasi pengembangan awal; pastikan prompt aktual muat sebelum eksperimen.

Generator memakai `qwen2.5:7b` secara default (ubah dengan `--model` atau
`OLLAMA_LLM_MODEL`), temperatur 0, dan output JSON terstruktur. File kandidat
siap-runner beserta prompt, output model, dan konteks retrieval untuk audit
ditulis ke `results/raw/`. Tinjau batch sebelum mengirimnya ke validator.

Implementasi generator lokal saat ini memanggil API Ollama dan Chroma langsung.
Notebook Colab sudah memakai wrapper LangChain untuk pembentukan knowledge
base serta retrieval, tetapi generator kandidat dan pencatatan batch formal
sekarang juga tersedia sebagai cell LangChain. Cell tersebut membuat pasangan
RAG-off/RAG-on untuk satu skenario dengan model, prompt dasar, temperatur, seed,
context size, dan `comparison_id` yang sama. Kondisi RAG-on menambahkan konteks retrieval;
keduanya mencatat `prompt_sha256`, provenance model, serta ID chunk. Batch sumber
dan audit prompt/konteks disimpan terpisah di Drive pada `candidate-batches/`
dan `generation-audits/`. Notebook belum dijalankan di Colab, sehingga hasilnya
belum diverifikasi terhadap model aktual.

Pilih `SCENARIO_ID`, `COMPARISON_ID`, `SEED`, dan `CANDIDATE_COUNT` di cell
generator. Jalankan sekali untuk membuat kedua kondisi sebagai pasangan.
Periksa payload boolean sebagai pasangan true/false dan tinjau semua keluaran
model sebelum menyerahkannya ke validation loop. Batch tersebut belum otomatis
menjalankan request ke DVWA.

## Batch SecLists

Ambil payload dari satu file SecLists yang sudah tersedia secara lokal. Catat
repository dan commit SHA, path relatif file, SHA-256 file, serta nomor
baris untuk setiap payload terpilih. Salin payload persis dari baris tersebut
ke batch. Script memeriksa format commit SHA, lalu memverifikasi hash file dan
kecocokan isi baris; ia tidak menafsirkan otomatis apakah payload cocok dengan
teknik atau level tertentu.
Penetapan kandidat tetap harus direview peneliti.

Contoh struktur batch:

```json
{
  "schema_version": "1.0.0",
  "scenario_id": "S1",
  "source": "SecLists",
  "rag_mode": "not_applicable",
  "provenance": {
    "repository": "SecLists",
    "revision": "<commit-sha>",
    "list_path": "Fuzzing/SQLi/<list-name>.txt",
    "list_sha256": "<64-hex-character-sha256>"
  },
  "candidates": [
    {
      "candidate_id": "seclists-s1-001",
      "source_line_number": 12,
      "payload": "<exact text from line 12>"
    }
  ]
}
```

Simpan batch kerja di `dvwa/candidate_batch.local.json` (sudah diabaikan
Git), lalu jalankan dari root repositori:

```powershell
python dvwa/prepare_candidate_batch.py `
  --input dvwa/candidate_batch.local.json `
  --source-list C:\path\to\the\exact\SecLists-file.txt
```

Untuk boolean-based, manifest SecLists memuat pasangan kondisi
`true_payload`/`false_payload` dan dua nomor baris dalam
`source_line_numbers`. Script memverifikasi kedua isi baris, tetapi tidak
membuktikan semantik true/false; peneliti tetap harus mereview pasangan itu.

## Batch LLM dengan RAG aktif/nonaktif

Simpan keluaran model beserta konfigurasi generasi. Buat file batch terpisah
untuk setiap kondisi. Gunakan model, prompt, skenario, batas kandidat, dan
parameter generasi yang sama pada pasangan RAG-off/RAG-on; gunakan
`comparison_id` yang sama untuk menghubungkan kedua batch dan isi hanya konteks
retrieval yang berbeda. Simpan ID knowledge base dan ID chunk yang benar-benar
dimasukkan ke prompt untuk kondisi RAG-on. Kondisi RAG-off harus mencatat
`knowledge_base_id: null` dan `retrieved_chunk_ids: []`.

Contoh provenance RAG-off:

```json
{
  "schema_version": "1.0.0",
  "scenario_id": "S1",
  "source": "LLM",
  "rag_mode": "off",
  "provenance": {
    "comparison_id": "s1-error-seed42-pair01",
    "model": "<model-id-and-version>",
    "prompt_version": "sqli-candidate-v1",
    "temperature": 0,
    "seed": 42,
    "prompt_sha256": "<64-hex-character-sha256>",
    "knowledge_base_id": null,
    "retrieved_chunk_ids": [],
    "retrieval_top_k": null
  },
  "candidates": [
    { "candidate_id": "llm-s1-off-001", "payload": "<generated payload>" }
  ]
}
```

Untuk RAG-on, gunakan `rag_mode: "on"`, ID knowledge base yang tetap, dan
daftar `retrieved_chunk_ids` yang tidak kosong serta nilai `retrieval_top_k`.
`comparison_id`, model, versi prompt, temperatur, dan seed harus sama antara
batch RAG-off/on; `prompt_sha256` boleh berbeda karena konteks retrieval memang
berbeda. Versi query, hash kebijakan retrieval, dan hash korpus dicatat oleh
generator baru; untuk RAG-off nilainya `null`. Simpan snapshot prompt/konteks
dan respons model secara lokal sebagai bahan audit; jangan masukkan credential
atau cookie DVWA. Keluaran runner akan membawa metadata provenance ke setiap
baris log.

## Menjalankan batch

Persiapkan file kandidat terlebih dahulu:

```powershell
python dvwa/prepare_candidate_batch.py --input dvwa/candidate_batch.local.json
```

Script menulis file kompatibel-runner di `results/raw/`. Jalankan runner dengan
path output itu, satu skenario dan satu kondisi per run:

```powershell
python dvwa/validation_loop.py `
  --scenario S1 `
  --payload-file results/raw/candidates-S1-llm-off-<timestamp>.json `
  --repetitions 3 `
  --confirm-local-dvwa
```

Gunakan nama output aktual yang dicetak script. Ulangi terpisah untuk
SecLists, LLM RAG-off, dan LLM RAG-on. Smoke run manual sebelumnya bukan bagian
dari perbandingan. Jangan menghitung metrik sampai seluruh kondisi memiliki
jumlah run dan skenario yang sebanding serta keputusan mendapat review manusia.
