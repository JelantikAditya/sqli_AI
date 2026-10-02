# Menyiapkan kandidat LLM dan SecLists

## Tujuan

`dvwa/prepare_candidate_batch.py` memeriksa satu batch untuk satu skenario dan
satu kondisi sumber/RAG, lalu mengubahnya ke format yang diterima runner.
Kandidat dan provenance disimpan di `results/raw/`, sehingga file tersebut
tidak masuk Git. Normalizer ini tidak mengunduh SecLists. Pipeline RAG dan
generator LLM ada di `dvwa/build_knowledge_base.py`,
`dvwa/retrieve_knowledge.py`, dan `dvwa/generate_candidate_batch.py`.

Skrip lokal pipeline memakai API Ollama dan Chroma langsung. Notebook Colab
[`colab_langchain_setup.ipynb`](../notebooks/colab_langchain_setup.ipynb)
menggunakan integrasi LangChain untuk Ollama dan Chroma. Notebook menerima
salinan PDF yang diunggah ke `MyDrive/TA-SQLi/references/`, menghitung hash
sumber, mengindeks per halaman, dan menyimpan snapshot Chroma sebagai ZIP di
`MyDrive/TA-SQLi/chroma-archives/`. Manifest build disimpan terpisah di
`MyDrive/TA-SQLi/knowledge-base-manifests/`. Saat runtime baru, notebook
memulihkan snapshot ke `/content` sebelum retrieval; jangan membuka database
SQLite Chroma secara langsung dari mount Drive. Implementasi notebook belum
dijalankan di Colab.

Kontrak batch ada di [`../schemas/candidate-batch.schema.json`](../schemas/candidate-batch.schema.json).
Validasi tambahan memastikan pasangan payload sesuai jenis skenario, jumlah
kandidat maksimal 10, sumber metadata lengkap, dan mode RAG tercatat konsisten.

## Menyiapkan knowledge base dan retrieval

Instal dependensi dan siapkan model lokal sesuai proposal:

```powershell
python -m pip install -r requirements-rag.txt
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
```

Pastikan Ollama berjalan lokal, lalu indeks semua PDF referensi tanpa mengubah
`sources/`:

```powershell
python dvwa/build_knowledge_base.py --embedding-model nomic-embed-text
```

Script mengekstrak teks per halaman, memecahnya menjadi chunk dengan overlap,
membuat embedding lewat `POST /api/embed`, dan menyimpannya ke ChromaDB lokal.
Manifest berisi hash sumber, jumlah halaman/chunk, konfigurasi chunking, model
embedding, ID knowledge base, dan nama koleksi. Vector store berada di
`data/vectorstore/` dan diabaikan Git. Jika Ollama berjalan di port lokal lain,
atur `OLLAMA_BASE_URL` (tetap loopback).

Uji retrieval untuk satu skenario dengan manifest yang dicetak saat indexing:

```powershell
python dvwa/retrieve_knowledge.py `
  --scenario S1 `
  --manifest data/vectorstore/sqli-kb-<id>/manifest.json `
  --top-k 5
```

Hasil retrieval, termasuk ID chunk dan jarak, disimpan lokal di `results/raw/`.

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
  --manifest data/vectorstore/sqli-kb-<id>/manifest.json `
  --top-k 5
```

Generator memakai `qwen2.5:7b` secara default (ubah dengan `--model` atau
`OLLAMA_LLM_MODEL`), temperatur 0, dan output JSON terstruktur. File kandidat
siap-runner beserta prompt, output model, dan konteks retrieval untuk audit
ditulis ke `results/raw/`. Tinjau batch sebelum mengirimnya ke validator.

Implementasi generator lokal saat ini memanggil API Ollama dan Chroma langsung.
Notebook Colab sudah memakai wrapper LangChain untuk pembentukan knowledge
base serta retrieval, tetapi generator kandidat dan pencatatan batch formal
sekarang juga tersedia sebagai cell LangChain. Cell tersebut membuat pasangan
RAG-off/RAG-on untuk satu skenario dengan model, prompt dasar, temperatur, seed,
dan `comparison_id` yang sama. Kondisi RAG-on menambahkan konteks retrieval;
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
berbeda. Simpan snapshot prompt/konteks
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
