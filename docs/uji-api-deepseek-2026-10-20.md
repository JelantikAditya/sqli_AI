# Uji koneksi API DeepSeek melalui HCNSEC

Tanggal: 20 Oktober 2026. Pengguna mengonfirmasi endpoint HCNSEC dan meminta
satu uji singkat DeepSeek sebelum pilot. Pemeriksaan daftar model sebelumnya
berhasil dengan HTTP 200 dan mengembalikan 19 ID; kontrol tanpa Authorization
mendapat HTTP 401. Daftar itu belum membuktikan ketersediaan inferensi semua
model atau identitas upstream-nya.

## Hasil satu panggilan chat

| Pengaturan atau hasil | Nilai |
| --- | --- |
| Endpoint | https://api.hcnsec.cn/v1/chat/completions |
| Model pada request | DeepSeek-V4-Pro |
| Model pada response.model | self-dploy/DeepSeek-V4-Flash-Vision-Exp |
| Prompt | Balas persis API_OK tanpa teks lain. |
| Batas output | 256 token |
| Temperature | 0 |
| Stream | false |
| HTTP status | 200 |
| Isi respons | API_OK |
| Finish reason | stop |
| Waktu tunggu | 9,003 detik |
| Usage yang dilaporkan gateway | 15 prompt token + 3 completion token = 18 token |
| Jumlah permintaan chat | 1 |
| Retry | 0 |

Koneksi, autentikasi untuk permintaan ini, dan pembacaan respons berhasil.
Pengujian ini tidak mengirim bukti SQLi, menguji RAG, menilai akurasi model,
atau menghasilkan FPR/PSR. API key dibaca melalui input tersembunyi, tidak
disimpan dalam berkas request, respons, atau hasil. Request disimpan tanpa
header Authorization sebelum panggilan dilakukan.

## Ketidakcocokan identitas model

ID yang diminta berbeda dengan nama model yang dilaporkan gateway. Ini
merupakan pengamatan atas metadata respons. Kita belum dapat menentukan
apakah penyebabnya alias, pemetaan kanal, fallback, atau metadata upstream
yang tidak konsisten, dan belum memverifikasi identitas model yang benar-benar
menjalankan inferensi. Hasil tidak boleh disebut sebagai pengujian kemampuan
DeepSeek-V4-Pro yang identitas upstream-nya telah terverifikasi.

Untuk perbandingan penelitian berikutnya, pemetaan ID, backend, dan versi
perlu diperjelas serta dicatat sebelum pilot. Respons model yang menyatakan
nama dirinya tidak menjadi bukti identitas yang memadai. Parameter dan
provider yang sama diperlukan pada kondisi tanpa/dengan RAG; hasil tetap
menjadi eksperimen development baru yang terpisah dari R1/R2/R3.

## Artefak lokal

- [Request tanpa kredensial](../results/raw/development/hcnsec-deepseek-smoke-20261020T082841843535Z/request.json).
- [Respons tersimpan](../results/raw/development/hcnsec-deepseek-smoke-20261020T082841843535Z/response.json).
- [Ringkasan](../results/raw/development/hcnsec-deepseek-smoke-20261020T082841843535Z/summary.json).
- [Manifest sebelum panggilan](../results/raw/development/hcnsec-deepseek-smoke-20261020T082841843535Z/manifest.json).

Berkas mentah berada di results/raw yang dikecualikan dari Git. Model lokal,
kode frozen, korpus, dan hasil formal tidak diubah pada uji koneksi ini.
