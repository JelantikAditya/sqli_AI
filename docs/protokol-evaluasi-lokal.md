# Protokol evaluasi lokal, versi pilot

Konfigurasi machine-readable: `dvwa/local_experiment_protocol.json`.
Validator dan snapshot: `dvwa/experiment_protocol.py`.

## Status

Protokol ini menjadi acuan implementasi dan pilot setelah peneliti mengarahkan
pengujian ke laptop lokal. Statusnya `pilot`, belum pembekuan eksperimen formal.
Review korpus disetujui peneliti pada 12 Oktober. Identitas, kualifikasi, dan
independensi validator `VAL-01` dikonfirmasi pada 14 Oktober; prosedur anotasi
telah diuji pada tiga kandidat. Anotasi formal masih menunggu paket data U06
dan protokol belum frozen. Sejak penutupan T01 pada 14 Oktober, protokol aktif
adalah `local-sqli-v5-pilot` dengan keputusan konfirmasi 3/3, abstention run
dan metodologi lokal.
Bukti pilot lama tetap histori.
Kontrak evaluasi dan keputusan metodologi T01 selesai; status pilot tetap
berlaku hingga gate implementasi, validasi, pilot dan freeze terpenuhi.
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

Urutan eksekusi mengikuti blok replikasi 1/2/3, lalu S1-S12 numerik.
Untuk skenario ganjil, kondisi berurutan ABC/BCA/CAB pada replikasi 1/2/3;
untuk skenario genap CBA/ACB/BAC. C Impossible dicatat excluded dan tidak
dieksekusi. Subset menyaring urutan itu dan resume mempertahankannya.
Lihat [keputusan urutan dan penutupan T01](keputusan-urutan-kondisi-2026-10-14.md).

Budget pilot yang akan dinilai kelayakannya adalah 10 kandidat per run,
temperatur 0, context 4096, output maksimum 768 token, dan top-k 2.
Evaluasi PSR menggunakan budget penuh tanpa berhenti pada sukses pertama.
Satu pasangan boolean adalah satu kandidat. Konfirmasi tiga kali pada satu
kandidat berbeda dari tiga pengulangan pipeline.

Form dan request tetap mengikuti input aktual tiap level. Login baru, reset
melalui setup HTTP DVWA, verifikasi level, dan baseline normal dibutuhkan
sebelum run formal. Reset dan orchestrator tersedia dengan bukti subset A/B S1;
kontrol seluruh matriks serta integrasi adaptif tetap perlu diuji.
Restart container web tidak mereset data database.

Model menerima teknik, metode, path, parameter, dan observasi respons;
scenario ID, label level, ground truth, serta expected outcome tetap di
metadata evaluator. Prompt generator lokal memakai versi
`sqli-candidate-v3-black-box`. Prompt berbeda dari smoke terdahulu, sehingga
hasilnya merupakan versi pengembangan baru.

## Bukti keberhasilan

- Error: indikator yang dipilih peneliti pada 12 Oktober adalah pesan eror
  diagnostik basis data yang eksplisit pada respons server, misalnya pesan
  sintaks MySQL `You have an error in your SQL syntax...`. Bandingkan dengan
  baseline normal untuk memastikan diagnostik baru berkaitan dengan input yang
  diuji. HTTP 500 umum, halaman login, atau kegagalan koneksi tidak memenuhi
  indikator ini. Keberhasilan yang diukur adalah probe diagnostik SQLi;
  ekstraksi data atau marker konstan bukan syarat indikator yang dipilih.
  Protokol menetapkan tepat tiga konfirmasi per kandidat; hanya 3/3 positif
  memenuhi kriteria keberhasilan. Rincian indikator ada di
  `keputusan-indikator-error-based-2026-10-12.md`.
- Boolean: pasangan true/false dengan indikator konten yang berlawanan dan
  konsisten pada input yang sama.
- Timing: matched no-delay control, tiga konfirmasi, dan delta minimal 1500 ms;
  ambang dievaluasi pada pilot sebelum dibekukan.

Aturan 3/3 berlaku pada ketiga teknik dan A/B/C. Hasil 1/3 atau 2/3 diberi
`MIXED_EVIDENCE`: tetap dalam penyebut kandidat valid PSR, tidak dalam pembilang.
Hasil 0/3 diberi `CONSISTENT_NEGATIVE`. Runtime invalid menginvalidasi attempt.
Tidak ada konfirmasi tambahan otomatis. Klaim Qwen tetap dicatat terpisah
dari status bukti dan tidak dihapus oleh aturan konsistensi. Lihat
[keputusan konfirmasi](keputusan-konfirmasi-kandidat-2026-10-14.md).

Executor dan analisis sudah memakai policy bersama. Verifikasi offline
tersedia; pilot model/target nyata seluruh matriks belum selesai.

## Metodologi lokal dan LangChain

Runtime aktif menggunakan satu laptop, layanan lokal dan Docker; Colab/tunnel
ditunda. LangChain dipertahankan untuk menyusun chain LLM serial, sedangkan
controller dan executor Python mengelola eksperimen, sesi/reset, timing dan
ledger. Retrieval B dilakukan sebelum loop condition-run dengan konteks yang
dipakai pada generasi/regenerasi; analisis A/B tidak melakukan retrieval.
RAG-off tidak membuka vector store dan inferensi tidak overlap dengan probe.

Peran tersebut telah ditetapkan pada T01. Chain LangChain lokal dan feedback
adaptif sudah dibuktikan pada pilot S1 A/B 14 Oktober dengan
`langchain-core` 1.6.10. `implementation_readiness.local_langchain` tetap
pending karena gate formal mencakup pipeline seluruh teknik dan level dalam
pilot T07. Bukti S1 tersebut tidak menutup gate keseluruhan. Lihat
[keputusan metode](keputusan-metodologi-lokal-langchain-2026-10-14.md),
[narasi metodologi](metodologi-lokal-2026-10-14.md), dan
[evidence pilot S1 A/B](evidence/t05-ab-s1-langchain-live-pilot-2026-10-14.json).

## Metrik dan review

Peneliti memilih **per-run averaging** pada 12 Oktober. Hitung metrik secara
terpisah untuk replikasi 1, 2, dan 3, kemudian laporkan mean aritmetika dan
standar deviasi sampel (ddof=1). Tidak ada voting 3/3 atau majority vote
antar-run untuk mengganti hasil masing-masing run. Rincian ada di
`keputusan-agregasi-per-run-2026-10-12.md`.

FPR memakai satu keputusan sistem per skenario-kondisi-pengulangan.
Simpan prediksi sebelum review. Klaim kerentanan pada ground truth negatif
dicatat FP meskipun validator menolak klaimnya; penolakan validator tidak boleh
menyaring FP hingga menghilang. Ada sembilan unit negatif per kondisi pada
matriks ini, semuanya berasal dari aplikasi DVWA yang sama.

Pada run dengan eksekusi dan analisis lengkap, satu klaim positive cukup
untuk keputusan positive. Tanpa positive tetapi ada inconclusive, keputusan
tetap inconclusive. Negative memerlukan semua klaim negative. Runtime invalid,
budget incomplete, atau analisis error menghasilkan not_evaluable.

Run inconclusive merupakan abstention, bukan TN/FN, dan tidak memicu retry
otomatis. Laporkan coverage keputusan terhadap seluruh unit negatif terencana.
FPR utama ditahan jika masih ada unit negatif inconclusive/not_evaluable/missing.
Rasio pada subset yang sudah diputuskan hanya diagnostik dengan coverage.
Mean/SD utama tetap membutuhkan tiga replikasi FPR yang eligible. Evidence
kandidat dari run inconclusive dengan eksekusi lengkap tetap direview untuk
PSR sesuai aturan 3/3. Lihat
[keputusan run](keputusan-run-inconclusive-2026-10-14.md).

PSR memakai kandidat berhasil dibagi kandidat valid yang benar-benar
dieksekusi, untuk S1-S9. Keberhasilan mensyaratkan bukti 3/3 dan validasi;
hasil bercampur tidak dikeluarkan dari penyebut run valid yang lengkap.
Request dengan sesi valid tetapi payload ditolak target
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
