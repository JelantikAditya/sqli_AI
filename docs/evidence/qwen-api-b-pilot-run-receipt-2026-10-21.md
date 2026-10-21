# Receipt eksekusi pilot B, 21 Oktober 2026

## Ruang lingkup

Eksekusi terbatas pada kondisi B, skenario S1 Low, satu replikasi, dan dataset pilot. Receipt keputusan snapshot yang menjadi acuan adalah `docs/evidence/qwen-api-b-pilot-decision-2026-10-21.json`. Hash korpus, source lock, manifest, dan keenam file indeks tercantum lengkap di JSON receipt.

## Hasil

Runner menyelesaikan seluruh anggaran sepuluh kandidat. Sepuluh analisis selesai, sepuluh kandidat dijalankan, tiga kandidat mendapat sinyal positif yang terkonfirmasi, tujuh negatif, dan tidak ada bukti campuran. Attempt memakai 20 request API. Attempt pertama yang invalid memakai satu request, sehingga total aktual lintas kedua attempt adalah 21. Maksimum gabungan yang direncanakan adalah 41 request.

DVWA database reset dilakukan. Ledger mencatat 159 request HTTP dan 60 logical probe submissions. Status run `metric_eligible` hanya menyatakan anggaran pilot lengkap dan bukti teknis lengkap. Nilai PSR masih kosong, validasi manusia masih pending, dan hasil satu kondisi B pada satu skenario serta satu replikasi tidak menghasilkan estimasi FPR atau perbandingan PSR untuk proposal.

## Integritas indeks dan batas penggunaan

Retrieval memakai salinan kerja yang diverifikasi terhadap snapshot receipt. Hash store sumber tetap sama dengan keenam hash yang disetujui setelah query, sementara salinan retrieval menunjukkan penulisan Chroma. Store aktif sudah dipulihkan sebelum recovery dan kondisi post-attempt pertama disimpan sebagai backup dalam catatan insiden.

Eksekusi ini adalah bukti pilot pengembangan, bukan formal execution dan bukan hasil final penelitian. Catatan insiden memuat kegagalan attempt pertama, koreksi adapter, pemulihan indeks, dan temuan credential helper. Receipt JSON mengikat hash plan, ledger, checkpoint, runtime snapshot, adaptive result, log validasi, generation audit, dan batch kandidat.
