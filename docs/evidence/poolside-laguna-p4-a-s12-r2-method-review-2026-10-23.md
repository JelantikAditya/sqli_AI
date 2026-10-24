# Telaah metodologis amandemen FPR A/S12/R2

**Status:** bahan telaah untuk peneliti dan pembimbing. Ini rekomendasi metodologis, bukan bukti persetujuan.

**Paket yang ditelaah:** `p4-a-s12-r2-amend1`, SHA-256 `cd789af2359cf1dd498d49520b6d1fb76ef842a8b365b409f3f315973d9392ba`.

## Temuan

Run asli A/S12/R2 menyelesaikan anggaran sepuluh kandidat dan seluruh analisis, tetapi satu klaim `inconclusive` membuat keputusan run ikut `inconclusive`. Ini bukan run yang terputus atau invalid. Kebijakan beku `any-positive-else-abstain-v1` menetapkan `inconclusive_retry: none`; kontrak U05 menahan FPR replikasi bila salah satu skenario negatif unresolved. Pada VAL-01, A/R2 memiliki dua keputusan negatif dari tiga skenario, coverage keputusan 2/3, dan S12 unresolved. FPR A/R2 karena itu `null` dan FPR A utama belum eligible.

Kontrak FPR memakai satu keputusan run untuk masing-masing skenario S10-S12 pada tiap replikasi. Sepuluh kandidat dalam unit adalah anggaran untuk menghasilkan keputusan unit, bukan sepuluh observasi FPR independen. Bila keputusan pengganti S12/R2 negatif, FPR replikasi tersebut menjadi 0/3. Bila positif, menjadi 1/3. Karena R1 dan R3 saat ini masing-masing 0%, mean tiga replikasi pada tabel sensitivitas menjadi 0% atau 11,11%. Bila unit baru abstain atau invalid, FPR A sensitivitas tetap unresolved.

## Risiko dan rekomendasi

Mengganti unit lengkap setelah hasil `inconclusive` diketahui adalah keputusan pascahasil. Jika hanya unit ini yang diganti, analisis memilih ulang observasi yang tidak mendukung kelengkapan metrik. Itu dapat menaikkan coverage, dan hasil pengganti negatif dapat memberi angka FPR yang tampak lebih baik. Menghitung abstention sebagai negatif juga tidak dibenarkan oleh kontrak metrik.

Rekomendasi saya adalah **tidak mengubah hasil primer U05**. Amandemen ini dapat dipertimbangkan hanya sebagai analisis sensitivitas eksploratif yang dilabeli pascahasil, dengan matriks primer dan sensitivitas ditampilkan berdampingan. Laporan sensitivitas harus mencatat unit asli yang tetap inconclusive, unit pengganti, aturan inklusi, coverage, serta semua hasil, termasuk hasil positif atau inconclusive. Jangan menggabungkan kandidat lama dan baru atau menyebut hasil sensitivitas sebagai koreksi hasil primer.

Pilihan paling konservatif tetap mempertahankan FPR A sebagai tertahan dan melaporkan coverage 2/3 untuk R2. Diagnostic decided-only FPR 0% boleh ditampilkan hanya sebagai deskriptif, bukan sebagai FPR utama. Amandemen yang diusulkan tidak mengubah PSR atau FPR B.

## Syarat keputusan sebelum freeze

Peneliti dan pembimbing perlu menyetujui secara eksplisit bahwa:

1. Run pengganti hanya dipakai dalam matriks sensitivitas pascahasil, sementara hasil primer tetap sama dan tetap menahan FPR A.
2. Keputusan negatif, positif, inconclusive, atau invalid akan dilaporkan sesuai hasil. Tidak ada retry otomatis atau penggantian kedua.
3. Hasil sensitivitas tidak akan dipakai untuk mengklaim peningkatan performa primer atau menyembunyikan abstention pada unit asli.
4. Persetujuan freeze dan persetujuan eksekusi formal dibuat terpisah dan mengikat paket yang sama. Batasnya tetap USD 0, maksimum 40 request API, 51.200 completion token, satu reset DVWA lokal, tanpa fallback dan tanpa OpenRouter.

**Keputusan peneliti:** disetujui untuk analisis sensitivitas pascahasil, dengan hasil primer tetap dipertahankan. Receipt hash-bound tersimpan di `docs/evidence/poolside-laguna-p4-a-s12-r2-researcher-method-decision-2026-10-23.json`.

**Keputusan pembimbing:** disetujui menurut konfirmasi peneliti, "pembimbing sudah setuju lanjutkan". Receipt metodologis mencatat bahwa bukti langsung dari pembimbing belum diserahkan.

**Tanggal dan catatan:** pending

## Teks untuk dokumentasi pembimbing

Jika diperlukan catatan langsung dari pembimbing, teks berikut dapat dikonfirmasi atau diubah olehnya:

> Saya menyetujui penggunaan unit pengganti A/S12/R2 hanya pada analisis sensitivitas pascahasil. Hasil primer U05 tetap dipertahankan dengan FPR A tertahan. Hasil pengganti, termasuk hasil positif, inconclusive, atau invalid, dilaporkan sesuai hasil tanpa retry atau penggantian kedua. Persetujuan ini tidak dengan sendirinya mengizinkan freeze amandemen atau eksekusi formal.

Nama pembimbing: pending

Tanggal: pending

Catatan atau perubahan syarat: pending

## Bukti yang ditelaah

- Kontrak metrik: `docs/u05-agregasi-metrik-2026-10-14.md`.
- Kebijakan keputusan run: `dvwa/run_decision_policy.py`.
- Metrik VAL-01 beku: `results/raw/formal-review/poolside-laguna-p4-20261023-val01-batch01/metrics-P4-VAL01.json`.
- Diagnostik abstention A/S12/R2: `docs/evidence/poolside-p4-a-r2-s12-fpr-abstention-diagnostic-2026-10-23.json`.
- Usulan amandemen dan batas operasional: `docs/usulan-amendemen-fpr-p4-a-s12-r2-2026-10-23.md`.
- Readiness dry-run: `docs/evidence/poolside-laguna-p4-a-s12-r2-amendment-readiness-2026-10-23.json`.

Dry-run hanya memverifikasi kesiapan teknis. Ia tidak membaca API key, menghubungi API atau DVWA, mereset database, atau menggantikan persetujuan metodologis.
