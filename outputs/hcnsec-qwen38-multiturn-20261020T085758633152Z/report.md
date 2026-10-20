# Uji percakapan Qwen3.8-27B, 20 Oktober 2026

Uji API umum menggunakan tiga percakapan sintetis, masing-masing tiga giliran. Setiap giliran berikutnya menyertakan jawaban asli model sebelumnya. Ini terpisah dari eksperimen TA.

Jumlah permintaan: 9/9. Respons diterima: 9. Giliran lulus: 9/9.

Rerata waktu untuk respons diterima: 11.566 detik; median: 10.063 detik. Total token yang dilaporkan: 3747.

| Percakapan | Lulus | Respons diterima |
|---|---:|---:|
| Koreksi dan perubahan pesanan | 3/3 | 3/3 |
| Ingatan, informasi kosong, dan catatan kutipan | 3/3 | 3/3 |
| Hitungan belanja setelah revisi | 3/3 | 3/3 |

## Detail giliran

| Percakapan | Giliran | Hasil | Waktu (detik) |
|---|---:|---|---:|
| order_updates | 1 | pass | 15.598 |
| order_updates | 2 | pass | 7.876 |
| order_updates | 3 | pass | 7.393 |
| facts_and_quoted_text | 1 | pass | 8.46 |
| facts_and_quoted_text | 2 | pass | 10.063 |
| facts_and_quoted_text | 3 | pass | 6.416 |
| shopping_revision | 1 | pass | 10.386 |
| shopping_revision | 2 | pass | 15.856 |
| shopping_revision | 3 | pass | 22.048 |

## Pengaturan dan batas kesimpulan

- Alias yang diminta selalu `Qwen3.8-27B`; endpoint `https://api.hcnsec.cn/v1/chat/completions`.
- `temperature=0`, `max_tokens=1024`, `stream=false`, timeout socket 90 detik, tanpa retry.
- Prompt dan jawaban referensi ditetapkan sebelum permintaan pertama. Lulus membutuhkan JSON dengan kunci, nilai, dan tipe yang tepat serta `finish_reason=stop`.
- Percakapan direset antara skenario. Jawaban referensi tidak pernah dimasukkan ke riwayat sebagai jawaban model.
- Hanya tiga percakapan pendek dengan satu percobaan setiap giliran; hasil tidak mengukur percakapan panjang atau kemampuan umum model.
- Waktu mencakup jaringan dan antrean gateway, bukan kecepatan token. Nilai token berasal dari gateway; biaya dan tagihan aktual belum diverifikasi.
- API key dimasukkan melalui input tersembunyi dan tidak disimpan. Prompt hanya memakai data sintetis.
- Nama model dalam metadata: `self-dploy/Qwen3.8-27B`. Metadata ini tidak memverifikasi identitas upstream secara independen.

## Artefak

`plan.json` memuat prompt dan jawaban referensi. `manifest.json` mencatat aturan dan batas pengujian. Setiap folder giliran memuat payload dengan riwayat aktual, hash permintaan, respons mentah, dan hasil. `summary.json` memuat agregat; `run_check.py` memuat skrip tanpa kredensial.
