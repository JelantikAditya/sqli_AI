# Hasil pilot generasi Qwen API pada DVWA

Tanggal 20 Oktober 2026. Ini pilot pengembangan untuk menguji alur generasi API pada DVWA Low, bukan bagian dari 99 run formal. Cakupan hanya SQLi error-based, boolean-based blind, dan time-based blind. Tidak ada metrik PSR atau FPR yang dihitung.

## Hasil utama

| Skenario | Teknik | Kandidat dari API | Hasil executor DVWA | Interpretasi pilot |
| --- | --- | --- | --- | --- |
| S1 | Error-based | Satu kandidat lolos schema dan policy lokal | 3 sinyal diagnostik dari 3 konfirmasi; satu kandidat tercatat `CONSISTENT_POSITIVE` | Sinyal error-based konsisten pada pilot ini |
| S2 | Boolean-based blind | Pasangan true/false lolos schema | 0 sinyal konfirmasi; true dan false memberi marker `user_id_exists` pada ketiga pasangan | Belum ada diferensiasi boolean |
| S3 | Time-based blind | Satu kandidat lolos schema dan policy lokal | 0 sinyal konfirmasi; selisih kandidat terhadap kontrol tanpa delay adalah -10,52 ms, 0,10 ms, dan -3,18 ms | Delay yang diminta tidak tampak pada respons |

Kandidat diproses satu per skenario dengan reset database sebelum run dan tiga konfirmasi. Batch diberi ID `qwen38-api-pilot-20261020`, sumber `LLM`, dan `rag_mode=off`. Executor mengirim request hanya ke DVWA lokal. Hasil ini tidak memvalidasi efektivitas pada level Medium, High, atau Impossible.

## Pemeriksaan tambahan S2

Probe batas kutip yang terpisah membandingkan input baseline `1` dengan input bertanda kutip pada injection point yang sama, masing-masing tiga kali. Seluruh respons berstatus HTTP 200. Signature yang tercatat berubah dari `[true, false]` pada baseline menjadi `[false, false]` pada kandidat, tanpa diagnostik SQL baru. Perubahan signature ini belum cukup untuk menyimpulkan SQL injection karena tidak ada error SQL dan hasilnya perlu ditafsirkan sesuai kontrak bukti blind.

## Kestabilan generasi dan feedback

Prompt ringkas versi `qwen38-api-sqli-generation-v2-compact-no-think` memakai satu kandidat per skenario, `temperature=0`, batas 1.024 token, timeout 120 detik, dan penanda `/no_think`. Tiga response awal berhasil diparse dan memenuhi pemeriksaan format lokal. Gateway melaporkan model `self-dploy/Qwen3.8-27B`; label tersebut belum memverifikasi identitas upstream secara independen.

Ketika kandidat S2/S3 diuji di DVWA lalu feedback executor diberikan untuk regenerasi, layanan kembali gagal menyelesaikan kandidat. Regenerasi dilakukan sebagai request baru dengan plan dan hash tersendiri, tanpa retry otomatis.

| Batch | Skenario | Status API | Waktu | Rincian |
| --- | --- | --- | ---: | --- |
| Feedback lengkap | S2 | `transport-error` | 120,545 dtk | Tidak ada envelope respons |
| Feedback lengkap | S3 | `truncated` | 71,361 dtk | 1.024 completion token, seluruhnya dilaporkan sebagai reasoning |
| Feedback diringkas | S2 | `truncated` | 54,518 dtk | 1.024 completion token, seluruhnya dilaporkan sebagai reasoning |
| Feedback diringkas | S3 | `truncated` | 42,196 dtk | 1.024 completion token, seluruhnya dilaporkan sebagai reasoning |

Pemendekan feedback belum mengatasi hambatan. Temuan ini menunjukkan konfigurasi gateway/prompt saat ini belum stabil untuk menghasilkan kandidat blind ketika diberi feedback, sementara preflight tanpa feedback berhasil. Belum cukup bukti untuk menyatakan apakah penyebabnya perilaku model, pengaturan reasoning gateway, atau batas layanan.

## Perbaikan S2 Low setelah pilot awal

Probe terpisah berikutnya mengisolasi masalah payload S2. Pada request awal dengan `chat_template_kwargs: {"enable_thinking": false}`, Qwen mengembalikan kandidat dalam 6,325 detik, 25 completion token, dan 0 reasoning token. Kandidat `1 OR 1=1` / `1 OR 1=2` lolos schema tetapi menghasilkan respons identik di DVWA pada 3 dari 3 konfirmasi.

Pemeriksaan source Low yang sedang berjalan di container menunjukkan query `SELECT first_name, last_name FROM users WHERE user_id = '$id';`. Ada dua syarat agar pasangan boolean memberi sinyal berbeda: parameter harus keluar dari string SQL yang dikutip, dan base ID harus tidak ada. Pasangan kutip berbasis ID `1` masih gagal karena ID `1` sendiri ada di data sampel, sehingga kondisi false tetap menemukan baris. Kontrol lokal memakai `0' OR '1'='1` dan `0' OR '1'='2` berhasil memberi signature true/false yang berbeda pada 3 dari 3 konfirmasi.

Prompt versi `qwen38-api-sqli-generation-v3-s2-low-context-no-think` sekarang menyertakan konteks query Low yang sudah diperiksa, temuan bahwa ID `0` tidak ada dan ID `1` ada, serta bentuk pasangan yang sesuai. Request satu kali dengan opsi template menghasilkan `0' OR '1'='1` dan `0' OR '1'='2` dalam 3,4 detik, memakai 29 completion token dengan 0 reasoning token. Validator DVWA melaporkan `CONSISTENT_POSITIVE` pada 3 dari 3 konfirmasi. Database tidak di-reset.

Qwen mendokumentasikan `chat_template_kwargs.enable_thinking=false` untuk Qwen3 yang dilayani melalui vLLM, sekaligus menyebutkan bahwa cara pengiriman bergantung pada framework dan bukan bagian dari kompatibilitas OpenAI standar ([dokumentasi deployment vLLM Qwen3](https://github.com/QwenLM/Qwen3/blob/main/docs/source/deployment/vllm.md)). HCNSEC tidak mengembalikan metadata yang membuktikan bahwa gateway menerapkan opsi itu. Karena prompt konteks dan opsi template berubah sebelum keluaran berhasil, hasil ini membuktikan jalur generasi dapat bekerja pada request tersebut, tetapi belum membuktikan opsi template sebagai satu-satunya penyebab perbaikan.

Checkpoint mentah v6/v7 serta log DVWA disimpan lokal dan dikecualikan dari Git. Replay offline tersedia melalui `maintenance/audit_qwen_api_generation_s2_context.py`; audit tidak memanggil API atau DVWA dan menulis ringkasan ke `results/processed/qwen38-api-generation-s2-context-20261020/audit.json`.

## Batas kesimpulan dan langkah berikutnya

- Hasil S1 adalah sinyal executor dari tiga konfirmasi pada satu kandidat pengembangan. Hasil ini belum menjadi label manusia VAL-01 atau skor PSR.
- Hasil awal S2/S3 tetap gagal. Setelah prompt diperbaiki, satu kandidat S2 Low berhasil melewati tiga konfirmasi lokal; hasil satu kandidat ini hanya pilot teknis dan belum diberi anotasi manusia atau label VAL-01.
- S1 dan S3 belum diuji ulang dengan perbaikan generasi ini. Belum ada bukti lintas teknik atau level keamanan untuk menyatakan jalur API siap bagi 99 run.
- Pilot tidak menilai FPR, tidak membandingkan RAG-on dengan RAG-off, tidak menguji SecLists, dan tidak mencakup 99 run.
- Paket review blind API dibuat setelah versi kandidat dan bukti formal dibekukan. Anotasi lama VAL-01 tidak dipakai sebagai label kandidat API.
- Sebelum run formal, stabilkan generasi lintas teknik dan selaraskan perubahan penggunaan API pihak ketiga dengan amendemen metode, karena proposal awal menetapkan Qwen lokal.

Checkpoint mentah serta plan yang mem-pin request dan sumber bukti berada di `results/raw/development/qwen38-api-generation-smoke-20261020-v3`, `...-v4-feedback-canonical`, dan `...-v5-feedback-summary`. Folder tersebut dikecualikan dari Git. Ringkasan preflight awal yang memakai batas 2.048/4.096 token ada di [laporan preflight](hasil-preflight-generasi-qwen-api-2026-10-20.md), dan aturan review formal ada di [protokol blind API](protokol-review-blind-qwen-api-2026-10-20.md).
