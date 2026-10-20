# Usulan amendemen metode TA untuk backend Qwen API

Status: **draft amendemen metode**, disusun 20 Oktober 2026. Peneliti melaporkan telah mendapat persetujuan bersyarat pembimbing untuk mempertimbangkan API LLM berbayar apabila hasil tiga replikasi model lokal dinilai buruk. Keputusan final beralih ke API, pemicu yang dianggap terpenuhi, dan cakupan persetujuan untuk provider/model tertentu perlu dicatat sebelum run API formal. Dokumen proposal asli di `sources/` tidak diubah.

## Mengapa amendemen diperlukan

Proposal asli, halaman PDF 9, Bab 1.4 butir 4, membatasi LLM pada Qwen 2.5 7B yang dijalankan mandiri tanpa API pihak ketiga. Bab 2.2.5 halaman PDF 21 menjelaskan kemampuan serta spesifikasi model tersebut. Bab 3.1 dan 3.3 halaman PDF 25-31 menempatkan Qwen/Ollama, RAG, ZAP, dan orkestrasi pada Google Colab, dengan DVWA lokal melalui ngrok. Bab 3.2 halaman PDF 28 menyatakan embedding Nomic lokal agar data tidak dikirim ke API eksternal. Semua bagian ini perlu diselaraskan jika inferensi LLM berpindah ke layanan HCNSEC dengan alias `Qwen3.8-27B`.

Perubahan backend tidak mengubah pertanyaan penelitian, target DVWA, tiga teknik SQLi, sumber utama RAG, atau metrik FPR/PSR. Hasil formal lama Qwen 2.5 7B tetap dilaporkan sebagai versi terdahulu dan tidak digabung dengan angka versi API.

## Teks pengganti yang diusulkan

### Bab 1.3, tujuan penelitian

Pada tujuan ketiga, ganti kata "membuktikan" dengan rumusan hipotesis yang dapat dibantah:

> Mengukur dan membandingkan Payload Success Rate (PSR) kandidat SQL Injection yang dihasilkan LLM dengan dukungan Knowledge-level RAG terhadap kandidat payload statis dari SecLists, pada skenario DVWA yang sama dan dengan kriteria keberhasilan terkonfirmasi yang identik.

Ini menjaga hasil setara atau lebih buruk tetap sebagai temuan sah, bukan kegagalan pelaporan.

### Bab 1.4 butir 4, batasan model dan layanan

> Komponen generasi serta analisis respons menggunakan layanan API pihak ketiga dengan alias model `Qwen3.8-27B`. Nama model yang diminta, nama yang dilaporkan respons, endpoint, tanggal pengujian, parameter, pemakaian token, dan hash request dicatat. Identitas bobot model upstream tidak dapat diverifikasi secara independen. Model serta parameter inferensi dibuat sama pada kondisi RAG aktif dan nonaktif. Layanan API menerima fitur hasil DAST yang telah disanitasi, bukan kode sumber DVWA, cookie, token autentikasi, atau log mentah.

Tambahkan setelah butir batasan evaluasi:

> Generalisasi dibatasi pada DVWA lokal dan empat tingkat keamanannya. Perubahan model, provider, prompt, atau kebijakan payload diperlakukan sebagai perubahan versi eksperimen. Tidak ada kesimpulan lintas aplikasi produksi dari satu target DVWA.

### Bab 2.2.5, pemilihan LLM

> Penelitian versi lanjutan memakai alias layanan `Qwen3.8-27B` melalui API HCNSEC sebagai komponen inferensi. Uji koneksi umum memperlihatkan respons dengan `model` bernilai `self-dploy/Qwen3.8-27B`, tetapi metadata gateway tidak membuktikan identitas bobot, parameter, context window, atau teknik serving model. Oleh karena itu, klaim spesifikasi Qwen 2.5 7B dalam proposal awal tidak dipindahkan ke model API. Kinerja SQLi ditetapkan secara empiris melalui preflight domain dan pilot terpisah. Ketidakpastian provider, kuota, latensi, dan perubahan layanan dicatat sebagai ancaman validitas serta batas reproduksibilitas.

Nomor versi model pada judul/subbab/tabel yang masih menyebut Qwen 2.5 7B harus diperbarui atau diberi penjelasan bahwa itu hanya milik eksperimen terdahulu. Jangan menyebut alias HCNSEC sebagai rilis resmi Qwen tanpa bukti terpisah.

### Bab 3.1, alur sistem

> OWASP ZAP dan executor HTTP lokal menemukan serta menguji injection point secara black-box pada DVWA. Controller menyusun permintaan inferensi berisi teknik SQLi, koordinat input yang diperlukan, ringkasan baseline, dan bukti respons tersanitasi. Pada kondisi B, retrieval ChromaDB lokal menambahkan chunk Knowledge-level RAG untuk generasi dan regenerasi payload; pada kondisi A retrieval tersebut nonaktif. Keduanya menggunakan endpoint, alias model, prompt dasar, output budget, dan aturan validasi yang sama. Payload dijalankan oleh executor lokal, bukan oleh penyedia API. Pengukuran waktu SQLi dihitung hanya dari request HTTP ke DVWA; latensi API dicatat terpisah. Model mengembalikan kandidat atau klaim mentah, sementara parser memeriksa struktur, ID observasi, dan kelengkapan bukti tanpa mengubah klaim. Keputusan penelitian akhir memakai bukti executor serta anotasi validator manusia sesuai protokol.

Gambar 3.1 perlu menggambarkan hubungan controller lokal, ZAP, DVWA, RAG lokal, dan endpoint inferensi eksternal. Panah ke API menunjukkan hanya prompt tersanitasi dan konteks retrieval yang relevan, tanpa sesi DVWA.

### Bab 3.2, basis pengetahuan

> Sumber utama RAG tetap OWASP Web Security Testing Guide dan PayloadsAllTheThings sesuai batasan proposal. Entri terstruktur, embedding `nomic-embed-text`, dan vector store ChromaDB tetap diproses lokal. Hanya chunk terpilih yang sudah diperiksa dan diperlukan untuk kondisi B dikirim sebagai bagian prompt generasi ke API. Hash snapshot korpus, versi embedding, index, query, top-k, urutan chunk, dan sumber tiap chunk dibekukan untuk eksperimen utama.

Korpus pengembangan analisis v5 rev2 yang memuat rujukan PortSwigger tidak otomatis menjadi korpus utama. Bila akan digunakan pada hasil formal, Bab 1.4 dan Bab 3.2 perlu amendemen tambahan sebelum freeze.

### Bab 3.3, lingkungan dan sanitasi

> DVWA berjalan di Docker lokal pada tingkat Low, Medium, High, dan Impossible. ZAP, executor, controller, serta ChromaDB berada di lingkungan pengujian yang dikendalikan peneliti. Hanya layanan inferensi LLM yang berada di luar lingkungan lokal. Desain ini tidak membutuhkan tunnel publik menuju DVWA untuk inferensi API. Jika implementasi aktual memakai mesin atau tunnel lain, tabel spesifikasi dan diagram harus mengikuti lingkungan yang benar-benar dipakai, bukan tabel Google Colab/ngrok dari proposal awal.

> Sebelum mengirim prompt, controller menghapus cookie, CSRF token, Authorization header, kredensial, identitas pribadi, dan body HTTP mentah yang tidak diperlukan. Input model berisi identifier pengukuran, marker terpilih, diagnostik, status HTTP, dan waktu respons. API key diberikan melalui input tersembunyi atau environment sementara, tidak ditulis ke Git, manifest, atau artefak request. Output provider dan metadata disimpan di ruang hasil lokal dengan redaksi defensif; kebijakan retensi provider perlu dicatat dari ketentuan layanan yang berlaku saat pengujian.

Ganti tabel 3.1 dan Gambar 3.2 dengan topologi aktual yang diukur. Hapus klaim GPU T4, Ollama di Colab, Google Drive sebagai tempat hasil, dan ngrok sebagai kebutuhan arsitektur bila komponen itu tidak digunakan pada eksperimen versi API. Pemindahan inferensi ke API membuat kalimat "log tidak perlu dikirim ke layanan API pihak ketiga" pada Bab 3.2 dan 3.3 tidak lagi benar untuk versi baru.

### Bab 3.4 dan bagian evaluasi

Pertahankan S1-S12: Low, Medium, High untuk tiga teknik sebagai skenario positif; Impossible untuk tiga teknik sebagai kontrol negatif. Kondisi A/B masing-masing 12 skenario per replikasi, C SecLists sembilan skenario positif per replikasi, dan tiga replikasi. Sepuluh kandidat logis per run serta tiga konfirmasi per kandidat berlaku sama untuk semua kondisi applicable.

> FPR memakai unit keputusan run pada skenario Impossible dan dihitung `FP/(FP+TN)` hanya ketika penyebut serta cakupan sesuai aturan pra-registrasi. Inconclusive, analysis error, dan run tidak lengkap dilaporkan eksplisit; tidak dikonversi menjadi TN. PSR memakai jumlah kandidat valid dengan keberhasilan 3/3 terkonfirmasi serta validasi manusia dibagi seluruh kandidat valid pada run eligible. Pasangan boolean dihitung satu kandidat logis. Satuan kandidat logis, trial konfirmasi, dan request HTTP fisik dilaporkan terpisah.

Klaim bahwa sistem harus menurunkan FPR atau meningkatkan PSR diganti menjadi pengujian komparatif netral. Dengan hanya satu aplikasi target, keterbatasan generalisasi dan resolusi FPR pada sedikit skenario negatif perlu dijelaskan.

## Matriks perlakuan dan versi data

| Kondisi | Generasi | RAG generasi | Analisis respons | Skenario |
| --- | --- | --- | --- | --- |
| A | API Qwen alias sama | Tidak aktif | API Qwen, tanpa retrieval tambahan | S1-S12 |
| B | API Qwen alias sama | Aktif, sumber dan top-k dibekukan | API Qwen, tanpa retrieval tambahan | S1-S12 |
| C | SecLists dan seleksi terpin | Tidak berlaku | Bukti executor dan validator, tanpa LLM | S1-S9 |

Versi baru diusulkan bernama `qwen38-api-sqli-v2`. Manifest, prompt, kode, index, jadwal, dan data disimpan pada namespace terpisah. Pilot sintetis v5 r2 dan diagnosis API di atas 36 kasus lama hanya mendukung pengembangan parser. Keduanya bukan holdout independen, bukan FPR DVWA, dan bukan PSR formal.

## Keputusan akademis yang masih terbuka

1. Persetujuan bersyarat pembimbing untuk opsi API telah dilaporkan peneliti. Sebelum run formal, catat bahwa hasil tiga replikasi memenuhi pemicu peralihan, pastikan persetujuan mencakup provider/model yang dipilih, lalu selaraskan naskah Bab 1-3 dengan metode aktual.
2. Peneliti memastikan topologi aktual untuk tabel 3.1 dan Gambar 3.2 sebelum naskah akhir. Pemeriksaan kode saat ini tidak cukup untuk menyatakan semua komponen sudah dipindahkan.
3. Validator independen tersedia untuk anotasi kandidat sesuai jadwal dan paket blind, tanpa mengetahui kondisi A/B/C.
4. Kebijakan retensi dan pemrosesan data layanan HCNSEC diperiksa dan dicatat oleh peneliti. Metadata respons saja tidak menjelaskan kebijakan layanan.
5. Korpus utama tetap dua sumber proposal, atau perubahan sumber disetujui dan dicatat sebelum eksperimen formal.
