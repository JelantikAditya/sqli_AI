# Draf amandemen analisis FPR P4: A/S12/R2

**Status:** draf untuk keputusan metodologis. Belum dibekukan, belum menjadi plan eksekusi, dan belum mengizinkan run formal.

## Masalah yang ditangani

Pada cohort P4, A/S12/R2 adalah run lengkap dengan sepuluh kandidat dan seluruh analisis selesai. Keputusan run menjadi `inconclusive` karena satu klaim model bertentangan dengan bukti executor. Audit turunan mengonfirmasi delta waktu ketiga trial berada di bawah ambang 1.500 ms, tetapi aturan run beku mempertahankan klaim sistem dan tidak mengizinkan retry abstention. Kontrak U05 karena itu menahan FPR A.

Rincian dan checksum sumber tercatat di [audit diagnostik FPR](evidence/poolside-p4-a-r2-s12-fpr-abstention-diagnostic-2026-10-23.json). Hasil FPR VAL-01 saat ini tetap menjadi hasil utama sesuai metode beku.

## Koreksi penting tentang status run

Run lama bukan run invalid atau terputus. Menghapusnya dari analisis utama lalu memilih run baru setelah melihat hasil `inconclusive` dapat menimbulkan bias seleksi. Karena itu penggantian langsung tidak dapat diperlakukan sebagai koreksi teknis netral. Amandemen setelah hasil diketahui harus dinyatakan sebagai analisis amendemen atau sensitivitas, dilaporkan berdampingan dengan hasil utama yang dibekukan, dan mendapat persetujuan metodologis sebelum run baru.

## Usulan terbatas

Jika peneliti dan pembimbing memilih analisis amendemen, cakupan operasionalnya dibatasi pada satu unit: kondisi A, skenario S12, replikasi 2. Jalankan satu attempt baru yang terisolasi dengan sepuluh kandidat dan metode P4 yang sama. Tidak ada unit lain yang diulang. Seluruh ledger, hasil, klaim, anotasi, dan checksum run lama tetap dipertahankan sebagai bukti historis.

Untuk tabel amendemen, aturan inklusi yang diusulkan adalah memakai seluruh run A/B/C yang sudah terkunci, mengecualikan satu unit A/S12/R2 lama dari matriks amendemen, lalu memasukkan unit pengganti hanya jika sepuluh kandidat berbeda, semua analisis dan konfirmasi selesai, serta aturan eligibility yang sama menyatakan run valid. Kandidat lama dan baru tidak boleh digabung. Hasil utama U05 tetap ditampilkan terpisah dan tetap menandai FPR A tertahan.

Klaim pengganti mengikuti kebijakan yang sama: `positive` dihitung sebagai FP, `negative` sebagai TN, dan `inconclusive` atau run tidak valid tetap unresolved. Run pengganti yang positif tetap dapat membuat FPR eligible, tetapi FPR akan mencerminkan false positive tersebut. Jika negatif, FPR A amendemen akan menjadi 0%; jika positif, FPR A2 adalah 1/3 dan rata-rata tiga replikasi A menjadi 11,11%; jika abstain atau tidak valid, FPR A amendemen tetap tertahan.

## Batas sumber daya usulan

- Satu unit formal, A/S12/R2, dengan anggaran sepuluh kandidat.
- Maksimum 40 request API: 30 request generasi dan 10 request analisis.
- Maksimum 51.200 completion token: `30 x 1.024 + 10 x 2.048`.
- Batas biaya maksimum USD 0, akses langsung Poolside dengan model `poolside/laguna-s-2.1` saja.
- Maksimum satu reset database DVWA lokal untuk attempt formal yang disetujui.
- Tanpa OpenRouter, fallback model, retry transport otomatis, retry unit otomatis, atau pengganti kedua.
- Simpan attempt baru di direktori output terpisah. Persiapan dan dry-run tidak membaca API key, mengirim request API/DVWA, atau mereset database.

Batas di atas masih berupa usulan, belum dibekukan atau dapat dieksekusi. Plan satu unit, budget, runner fail-closed, dan paket hash-bound sudah disiapkan. Dry-run offline memverifikasi binding 16 artefak, release dan runtime beku, satu slot A/S12/R2, discovery terautentikasi yang masih segar, serta batas USD 0. Bukti readiness akan disimpan di [hasil dry-run](evidence/poolside-laguna-p4-a-s12-r2-amendment-readiness-2026-10-23.json).

Dry-run tidak membaca API key, tidak mengirim request API atau DVWA, dan tidak mereset database. Persetujuan metodologis peneliti dan pembimbing, freeze amandemen ber-hash, serta persetujuan eksekusi formal terpisah masih pending. Persetujuan formal Recovery P4 sebelumnya terikat ke release lama dan tidak mengotorisasi amandemen ini.

## Validasi dan penggabungan hasil

Untuk laporan FPR saja, anotasi manusia tidak menjadi pembilang atau penyebut. Jika cohort amendemen juga akan dipakai untuk melaporkan PSR dan mempertahankan validasi 990 kandidat, paket VAL-01 perlu diperbarui dengan sepuluh kandidat pengganti. Sepuluh anotasi lama A/S12/R2 tidak boleh dipasangkan ke kandidat baru. Anotasi dan metrik lama tetap disimpan tanpa ditimpa.

Sebelum amendemen dapat dibekukan, peneliti perlu memutuskan apakah penggantian pascahasil ini layak dilaporkan sebagai analisis amendemen. Persetujuan pembimbing atas keputusan tersebut perlu dicatat. Setelah itu baru siapkan plan dan budget ber-hash, dry-run offline, persetujuan freeze amendemen, serta persetujuan eksekusi formal terpisah. Tidak ada eksekusi yang tercakup dalam draf ini.

## Dampak terhadap hasil

Amandemen ini tidak mengubah PSR A/B/C. FPR B tetap 0% dan eligible. Hasil utama FPR A tetap tertahan sesuai run lama. Hanya tabel FPR amendemen yang dapat menjadi eligible jika run pengganti valid dan memiliki keputusan biner; angka akhirnya bergantung pada hasil run tersebut.

Receipt spesifikasi mesin untuk draf ini ada di `development/poolside_laguna_p4_a_s12_r2_amendment_20261023.json`.
