# Draf usulan amendemen metode P4 Poolside Laguna

Status dokumen: **keputusan metode peneliti sudah dicatat; persetujuan
pembimbing dilaporkan oleh peneliti**. Ini belum merupakan freeze protokol
atau izin menjalankan eksperimen formal.

## Keputusan yang sudah dicatat

Proposal saat ini menetapkan model Qwen 2.5 7B yang dijalankan mandiri. P4
mengusulkan Laguna S 2.1 melalui API Poolside langsung. Perubahan ini mengubah
model, transport inference, topologi, kendali atas versi layanan, dan kondisi
reproduksibilitas. Peneliti memutuskan Laguna P4 menjadi **cohort formal utama
untuk analisis yang direvisi**. Hasil formal Qwen lokal yang sudah ada harus
tetap disimpan sebagai cohort terpisah, dilaporkan secara terpisah, dan tidak
ditimpa, dibuang, atau digabung dengan data Laguna. Proposal akan diperbarui
di akhir penelitian agar peneliti dapat berfokus menyelesaikan serta menulis
hasil terlebih dahulu.

Peneliti menyatakan bahwa pembimbing telah menyetujui arah tersebut. Persetujuan
pembimbing dicatat sebagai laporan peneliti, bukan sebagai receipt langsung
atau tanda tangan pembimbing. Keputusan ini hanya menetapkan arah amendemen
metode dan peran cohort. Protokol P4 belum dibekukan dan eksekusi formal belum
diizinkan.

> “saya setuju dengan laguna sebagai cohort formal tambahan, setuju juga laguna
> menggantikan model formal utama, yang terpenting hasil pengujian formal
> menggunakan qwen lokal tetap disimpan”

Keputusan peneliti dicatat pada 23 Oktober 2026 di
`docs/evidence/poolside-laguna-p4-method-decision-2026-10-23.json`.

## Bagian desain yang tetap

- Metode tetap DAST black-box pada DVWA lokal.
- Cakupan serangan tetap SQL Injection: error-based, boolean-based blind, dan
  time-based blind pada level Low, Medium, High, serta Impossible.
- Kondisi A tetap LLM tanpa RAG, B tetap LLM dengan RAG, dan C tetap SecLists.
- Metrik utama tetap FPR untuk ablasi RAG A/B dan PSR untuk LLM terhadap
  SecLists.
- Matriks yang diusulkan mencakup 99 unit applicable pada tiga replikasi:
  72 unit A/B dan 27 unit C, 990 kandidat, serta 2.970 konfirmasi logis.
- Qualification Q4 v5 hanya menutup gate kelengkapan generasi. Q4 tidak
  menghasilkan FPR atau PSR formal dan tidak diperlakukan sebagai data P4.

## Perubahan yang harus dibekukan

- Provider inference: endpoint langsung Poolside, base URL
  https://inference.poolside.ai/v1, model yang diminta
  poolside/laguna-s-2.1.
- Profil kandidat A/B: prompt generasi v5, retry policy v5, konteks retrieval
  yang tidak memuat payload_examples, temperature 0, thinking nonaktif,
  batas 1.024 token untuk generasi dan 2.048 token untuk analisis.
- Adapter harus memeriksa model yang dilaporkan di setiap respons. Tidak ada
  fallback model dan tidak ada retry transport otomatis.
- Adapter Poolside tidak mengirim seed. Replikasi adalah pengulangan unit,
  reset target, login baru, dan jadwal yang dipin. Replikasi tidak menjamin
  keluaran identik dari layanan hosted.
- Retrieval B memakai snapshot korpus yang persis disetujui pada 17 Oktober.
  Runner P4 harus membaca snapshot secara terisolasi dan hanya-baca. Indeks
  aktif yang sekarang berbeda dari snapshot tersebut dan tidak boleh ditimpa.
- Endpoint, metadata model, hash prompt, profil, request ID, token, latency,
  finish reason, dan status transport dicatat tanpa credential.

## Budget dan aturan berhenti

Ekstrapolasi Q4 v5 memberi estimasi awal 1.518 panggilan API untuk 72 unit A/B.
Ceiling draft adalah 2.880 panggilan dan 3.686.400 completion token. Estimasi
token dan panggilan tidak menetapkan biaya uang. Harga, batas belanja, quota,
rate limit akun, dan ketersediaan endpoint untuk seluruh run belum diverifikasi.

Sebelum eksekusi, peneliti harus menetapkan batas biaya atau quota gratis yang
dapat dibuktikan pada akun langsung Poolside. Cohort dihentikan bila model,
endpoint, quota, batas biaya, hash input, atau kondisi target tidak sesuai
freeze. Unit gagal tidak boleh diganti diam-diam. Tidak ada penggunaan
OpenRouter dalam amendemen ini.

Halaman model Poolside saat ini menampilkan API kompatibel OpenAI, endpoint
tersebut, serta akses gratis untuk waktu terbatas. Notis Poolside Platform
menyebut penghentian inference pada 31 Oktober 2026. Dampak notis tersebut
terhadap endpoint API langsung dan akun penelitian masih perlu dikonfirmasi.

## Persetujuan dan batas klaim

Persetujuan pembimbing: **dilaporkan telah diberikan oleh peneliti; receipt
langsung belum tersedia**  
Keputusan peneliti: **Laguna P4 menjadi cohort formal utama untuk analisis
revisi; hasil formal Qwen lokal dipertahankan dan dilaporkan terpisah**  
Tanggal keputusan: **23 Oktober 2026**  
Pembaruan teks proposal: **ditunda sampai akhir penelitian sesuai arahan
peneliti**  
Freeze protokol dan persetujuan eksekusi: **belum diberikan**

Hasil Laguna dilaporkan sebagai hasil dari model hosted dengan topologi serta
batas reproduksibilitas tersendiri. Hasil formal Qwen lokal tetap tersedia dan
dibahas sebagai cohort terpisah. Selisih hasil tidak boleh diatribusikan hanya
pada provider karena model dan jalur inference ikut berubah. Jika gate
ketersediaan, biaya, protokol, atau eksekusi tidak dapat ditutup, hasil P4
tetap qualification/pilot dan tidak digunakan sebagai FPR/PSR formal.
