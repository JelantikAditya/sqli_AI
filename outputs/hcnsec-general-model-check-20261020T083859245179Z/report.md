# Uji singkat model API HCNSEC, 20 Oktober 2026

Uji umum terpisah dari eksperimen TA. Tujuannya memeriksa akses ke tiga alias model, kepatuhan format JSON, jawaban untuk tiga soal sederhana, dan waktu respons yang teramati.

## Pengaturan

- Endpoint: `https://api.hcnsec.cn/v1/chat/completions`.
- Tiga soal per alias: ekstraksi data yang tidak lengkap, aritmetika, dan membaca kode Python.
- Prompt dan kunci jawaban identik antaralias, dibekukan dalam `plan.json` sebelum permintaan pertama.
- `temperature=0`, `max_tokens=1024`, `stream=false`; urutan alias dirotasi untuk setiap soal.
- Satu percobaan per pasangan alias dan soal, timeout socket 90 detik, tanpa retry otomatis.
- Lulus jika isi respons berupa JSON tanpa teks tambahan, kunci/nilai/tipe tepat, dan `finish_reason=stop`.
- API key diberikan ke proses melalui input tersembunyi dan tidak disimpan dalam artefak.

## Ringkasan observasi

| Alias yang diminta | Percobaan / rencana | Respons diterima | Lulus / 3 soal | Rerata waktu respons diterima (detik) | Token dilaporkan |
|---|---:|---:|---:|---:|---:|
| `Qwen3.8-27B` | 3 / 3 | 3 | 3 / 3 | 20.88 | 1015 |
| `glm-5.3-flash` | 3 / 3 | 2 | 2 / 3 | 40.18 | 562 |
| `MiMo-V2.6-Flash` | 3 / 3 | 3 | 3 / 3 | 9.99 | 622 |

Rerata di atas hanya menghitung respons yang diterima. Kegagalan koneksi dicatat pada tabel per permintaan, sehingga tidak menghilang dari penilaian kelengkapan pengujian. Waktu meliputi jaringan, antrean gateway, dan pemrosesan; bukan kecepatan token model.

Pada percobaan ini, Qwen dan MiMo lulus ketiga soal. MiMo memiliki rerata waktu respons terendah di antara tiga alias yang diuji. GLM memberikan dua jawaban benar, sedangkan satu permintaan timeout. Tidak ada jawaban salah pada delapan respons yang diterima. Jumlah token hanya berasal dari delapan respons tersebut; penggunaan untuk permintaan timeout tidak diketahui.

| Urutan | Alias | Soal | HTTP | Hasil | Waktu (detik) |
|---:|---|---|---:|---|---:|
| 1 | `Qwen3.8-27B` | extract_json | 200 | pass | 42.69 |
| 2 | `glm-5.3-flash` | extract_json | tidak diterima | connection-or-response-error | 90.37 |
| 3 | `MiMo-V2.6-Flash` | extract_json | 200 | pass | 4.42 |
| 4 | `glm-5.3-flash` | arithmetic | 200 | pass | 71.62 |
| 5 | `MiMo-V2.6-Flash` | arithmetic | 200 | pass | 8.01 |
| 6 | `Qwen3.8-27B` | arithmetic | 200 | pass | 9.34 |
| 7 | `MiMo-V2.6-Flash` | python_trace | 200 | pass | 17.54 |
| 8 | `Qwen3.8-27B` | python_trace | 200 | pass | 10.61 |
| 9 | `glm-5.3-flash` | python_trace | 200 | pass | 8.74 |

## Metadata model

| Alias yang diminta | Nama model dalam respons |
|---|---|
| `Qwen3.8-27B` | `self-dploy/Qwen3.8-27B` |
| `glm-5.3-flash` | `self-dploy/GLM-5.3-Flash`, `z-ai/glm-5.3-flash` |
| `MiMo-V2.6-Flash` | `self-dploy/MiMo-V2.6-Flash` |

Nama tersebut berasal dari metadata gateway. Uji ini tidak memverifikasi bobot model atau identitas upstream secara independen. Timeout tidak membuktikan model salah menjawab atau modelnya tidak tersedia; respons tidak diterima pada batas waktu klien.

## Jawaban yang diterima

### 1. Qwen3.8-27B, extract_json

```text
{"nama":"Rani","jumlah":3,"kota":null}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 2. glm-5.3-flash, extract_json

Tidak ada jawaban akhir. Detail: The read operation timed out

Putusan: `connection-or-response-error`; `finish_reason`: `None`.

### 3. MiMo-V2.6-Flash, extract_json

```text
{"nama": "Rani", "jumlah": 3, "kota": null}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 4. glm-5.3-flash, arithmetic

```text
{"pensil": 1045}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 5. MiMo-V2.6-Flash, arithmetic

```text
{"pensil": 1045}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 6. Qwen3.8-27B, arithmetic

```text
{"pensil":1045}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 7. MiMo-V2.6-Flash, python_trace

```text
{"out": [2, 6, 0, 10, 1]}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 8. Qwen3.8-27B, python_trace

```text
{"out":[2,6,0,10,1]}
```

Putusan: `pass`; `finish_reason`: `stop`.

### 9. glm-5.3-flash, python_trace

```text
{"out":[2,6,0,10,1]}
```

Putusan: `pass`; `finish_reason`: `stop`.

## Batas kesimpulan

- Tiga soal sederhana dengan satu sampel per alias hanya mendukung kesimpulan tentang fungsi API pada percobaan ini. Hasil ini belum menjadi peringkat kemampuan model secara umum.
- Belum ada pengulangan untuk mengukur variasi latensi atau konsistensi jawaban.
- Anggaran token yang sama dapat berdampak berbeda pada model yang menggunakan token reasoning.
- Nilai token dan field biaya mentah berasal dari gateway. Mata uang, tarif akun, saldo, dan tagihan aktual tidak diverifikasi.
- Prompt hanya memuat contoh sintetis. Tidak ada data pribadi nyata, dokumen TA, atau kredensial di dalam prompt pengujian.

## Artefak

- `plan.json`: semua prompt, jawaban referensi, payload, dan SHA-256 setiap permintaan.
- `manifest.json`: batas pengujian dan aturan penilaian yang ditetapkan sebelum pengiriman.
- `summary.json`: hasil lengkap dan agregat.
- Folder `01-*` sampai `09-*`: permintaan, jawaban mentah, dan putusan per percobaan yang dijalankan.
- `run_check.py`: salinan skrip yang digunakan, tanpa API key. Untuk menjalankan ulang dari workspace, gunakan Python dan masukkan key saat prompt input tersembunyi muncul.
