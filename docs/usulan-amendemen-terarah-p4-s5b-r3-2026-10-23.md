# Draf amendemen terarah P4: S5-B Replikasi 3

**Status:** paket persiapan dan dry-run siap ditinjau. Amendemen ini belum dibekukan dan belum mengizinkan eksekusi formal.

## Alasan dan cakupan

Audit P4 Replikasi 3 mencatat 32 dari 33 unit applicable selesai. Satu unit, S5 kondisi B pada Replikasi 3, menghasilkan 9 dari 10 kandidat. Tiga respons generasi untuk slot terakhir berstatus HTTP 200, tetapi struktur kandidatnya duplikat. Audit tidak menemukan HTTP 529, kegagalan runtime, atau kehabisan token. Karena aturan rilis P4 melarang penggantian otomatis, unit ini tetap dikecualikan sampai amendemen terarah disetujui.

Amendemen hanya menyiapkan satu unit pengganti, yaitu S5-B-R3. Ia tidak menjalankan ulang 32 unit selesai, tidak mengubah hasil Replikasi 1-2 yang dipakai ulang, dan tidak mengubah protokol P4, prompt, model, snapshot RAG, atau aturan validasi.

## Aturan inklusi yang diusulkan

- Jalankan satu attempt baru dalam direktori output terpisah, dengan satu reset database DVWA lokal dan login baru.
- Hasil lama 9 kandidat dan seluruh keputusan validasinya tetap tersimpan sebagai bukti audit, tetapi tidak masuk metrik.
- Masukkan hanya sepuluh kandidat dari attempt pengganti jika seluruh analisis dan konfirmasi selesai dan status eligibility sesuai aturan protokol yang sudah dibekukan.
- Jika unit pengganti kembali tidak lengkap atau invalid, biarkan sel S5-B-R3 dikecualikan. Amendemen ini tidak memberi izin untuk retry otomatis atau penggantian kedua.
- Pertahankan 66 unit applicable Replikasi 1-2 serta 32 unit applicable Replikasi 3. Jika pengganti lolos, komposit kembali memiliki 99 unit applicable dan 990 slot kandidat. Jika gagal, jumlah unit metric-eligible tetap 98.

## Batas run yang disiapkan

- Satu unit applicable: kondisi B, skenario S5, Replikasi 3.
- Maksimum 40 panggilan API: paling banyak 30 panggilan generasi dan 10 analisis.
- Maksimum 51.200 completion token: `30 x 1.024 + 10 x 2.048`.
- Batas biaya USD 0, akses langsung Poolside saja, tanpa OpenRouter, fallback model, retry transport otomatis, atau penggantian unit otomatis.
- Satu reset database hanya terjadi saat eksekusi formal yang disetujui. Dry-run ini tidak membaca credential, tidak menghubungi API, dan tidak mengirim request ke DVWA.
- Estimasi waktu API dibatasi 2.700 detik. Batas jumlah request DVWA lokal tidak dipaksakan oleh runner; jumlah aktual akan dicatat di audit setelah eksekusi.

## Artefak dan gerbang

Plan, budget, aturan amendemen, runner, dan seluruh hash sumber terikat dalam `docs/evidence/poolside-laguna-p4-s5b-amendment-package-2026-10-23.json`. Runner dry-run memverifikasi bahwa plan hanya memuat B/S5/R3, audit dan ledger sumber masih cocok, snapshot serta protokol beku tidak berubah, dan output pengganti belum ada.

Sebelum eksekusi dibuka, dibutuhkan dua persetujuan terpisah yang terikat pada SHA paket ini: persetujuan freeze amendemen dan persetujuan eksekusi formal. Persetujuan eksekusi Replicate 3 yang lama terikat ke release berbeda dan tidak membuka gerbang ini. Setelah persetujuan, runner tetap membutuhkan flag eksplisit untuk DVWA lokal, satu reset database, dan biaya USD 0.

## Perintah dry-run

```powershell
python development/run_poolside_laguna_p4_s5b_amendment.py --dry-run
```

Perintah ini hanya memvalidasi paket offline. Opsi `--execute` akan ditolak sampai kedua receipt persetujuan baru tersedia dan cocok dengan semua hash paket.
