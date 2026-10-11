# Protokol evaluasi lokal, versi pilot

Konfigurasi machine-readable: `dvwa/local_experiment_protocol.json`.
Validator dan snapshot: `dvwa/experiment_protocol.py`.

## Status

Protokol ini menjadi acuan implementasi dan pilot setelah peneliti mengarahkan
pengujian ke laptop lokal. Statusnya `pilot`, belum pembekuan eksperimen formal.
Review korpus oleh peneliti dan identitas validator independen masih pending.
Kriteria gerbang formal dicatat dalam konfigurasi dan snapshot, tidak diklaim
selesai oleh pemeriksaan sintaks atau smoke S1.

## Matriks

- A: LLM RAG-off, S1-S12, tiga pengulangan.
- B: LLM RAG-on, S1-S12, tiga pengulangan.
- C: SecLists, S1-S9, tiga pengulangan.
- Total: 99 run; seed LLM 42/43/44, berpasangan sama pada A/B.
- Setiap pengulangan LLM menjalankan pipeline baru. Inventaris discovery yang
  sama dipakai pasangan A/B, dan diperbarui tiap pengulangan.

## Kontrol

Budget pilot yang akan dinilai kelayakannya adalah 10 kandidat per run,
temperatur 0, context 4096, output maksimum 768 token, dan top-k 2.
Evaluasi PSR menggunakan budget penuh tanpa berhenti pada sukses pertama.
Satu pasangan boolean adalah satu kandidat. Konfirmasi tiga kali pada satu
kandidat berbeda dari tiga pengulangan pipeline.

Form dan request tetap mengikuti input aktual tiap level. Login baru, reset
melalui setup HTTP DVWA, verifikasi level, dan baseline normal dibutuhkan
sebelum run formal. Reset otomatis dan orchestrator matriks masih perlu dibuat.
Restart container web tidak mereset data database.

Model menerima teknik, metode, path, parameter, dan observasi respons;
scenario ID, label level, ground truth, serta expected outcome tetap di
metadata evaluator. Prompt generator lokal memakai versi
`sqli-candidate-v3-black-box`. Prompt berbeda dari smoke terdahulu, sehingga
hasilnya merupakan versi pengembangan baru.

## Bukti keberhasilan

- Error: diagnostik SQL baru dan dapat direproduksi terhadap baseline. Definisi
  ini adalah keberhasilan probe diagnostik; jangan menyimpulkan ekstraksi data.
- Boolean: pasangan true/false dengan indikator konten yang berlawanan dan
  konsisten pada input yang sama.
- Timing: matched no-delay control, tiga konfirmasi, dan delta minimal 1500 ms;
  ambang dievaluasi pada pilot sebelum dibekukan.

Executor saat ini belum menjalankan seluruh kriteria konfirmasi dan matched
timing pada protokol ini. Implementasi itu merupakan pekerjaan tahap loop
adaptif; smoke S1 satu replikasi tidak memenuhi protokol formal.

## Metrik dan review

FPR memakai satu keputusan sistem per skenario-kondisi-pengulangan.
Simpan prediksi sebelum review. Klaim kerentanan pada ground truth negatif
dicatat FP meskipun validator menolak klaimnya; penolakan validator tidak boleh
menyaring FP hingga menghilang. Ada sembilan unit negatif per kondisi pada
matriks ini, semuanya berasal dari aplikasi DVWA yang sama.

PSR memakai kandidat berhasil dibagi kandidat valid yang benar-benar
dieksekusi, untuk S1-S9. Request dengan sesi valid tetapi payload ditolak target
dihitung gagal. Masalah login, baseline, atau koneksi adalah masalah runtime;
catat, pulihkan/ulang sesuai protokol, dan jangan otomatis menjadikannya FN
atau payload gagal. Run dengan budget tidak lengkap dikeluarkan dari analisis
utama dan tetap dilaporkan dalam ledger kelengkapan.

Penyebut nol dilaporkan tidak terdefinisi. Hasil manual dan smoke pengembangan
tidak dimasukkan ke dataset formal. Validator independen menerima ID acak,
koordinat, payload, baseline dan bukti yang disanitasi tanpa kondisi/sumber
kandidat atau label hasil yang diharapkan. PSR final menggunakan keputusan
validator; FPR tetap mempertahankan klaim sistem yang diaudit.

## Pemeriksaan konfigurasi

```powershell
.\.venv\Scripts\python.exe dvwa/experiment_protocol.py --write-manifest
```

Perintah ini tidak melakukan scan atau mengirim payload. Snapshot pada
`results/raw/` mencatat konfigurasi, matriks, revision Git, versi paket, serta
hash file. Snapshot ini belum menggantikan pembekuan runtime lengkap dengan
digest model/image, sumber SecLists, dan seluruh gerbang formal.
