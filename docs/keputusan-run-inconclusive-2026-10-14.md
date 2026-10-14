# Keputusan T01: keputusan akhir run dan INCONCLUSIVE

Tanggal: 14 Oktober 2026.
Dasar otorisasi: peneliti meminta melanjutkan penetapan aturan keputusan run
ketika Qwen menghasilkan INCONCLUSIVE. Aturan operasional berikut ditetapkan
dan diimplementasikan sebagai kelanjutan keputusan konfirmasi 3/3.
Protokol aktif: local-sqli-v3-pilot, status tetap pilot.
Dokumen ini mencatat tahap v3. Kelanjutan finalisasi metodologi pada hari yang
sama memakai local-sqli-v4-pilot; policy keputusan run tetap berlaku.

## Unit dan urutan keputusan

Satu run adalah satu scenario-condition-pipeline-replicate dengan budget
kandidat yang tetap. Aturan kandidat 3/3 tetap berlaku; tidak ada voting
antar tiga pengulangan pipeline.

Evaluasi run memisahkan kelengkapan eksekusi dari kelengkapan analisis model.
Keputusan biner memerlukan semua slot budget berisi kandidat unik yang valid,
tiga konfirmasi valid per kandidat, dan analisis model lengkap.

| Kondisi run | system_decision | Implikasi |
| --- | --- | --- |
| Ada runtime invalid | not_evaluable | Invalidasi attempt; pertahankan seluruh log dan klaim yang sempat muncul. |
| Budget/konfirmasi belum lengkap | not_evaluable | Tidak masuk hasil utama; laporkan incomplete. |
| Eksekusi lengkap tetapi analisis model error/referensi invalid | not_evaluable | Tidak menjadi keputusan negatif; simpan masalah analisis terpisah. |
| Eksekusi dan analisis lengkap; sedikitnya satu klaim positive | positive | Positive tetap disimpan meskipun kandidat lain negative/inconclusive atau bukti tidak mendukung klaim. |
| Eksekusi dan analisis lengkap; tanpa positive, tetapi ada inconclusive | inconclusive | Abstention final, bukan negative dan bukan runtime invalid. |
| Eksekusi dan analisis lengkap; semua klaim negative | negative | Keputusan biner negatif untuk unit tersebut. |

Prioritas pada run yang lengkap: positive, kemudian inconclusive, kemudian
negative. Pada run yang belum evaluable, klaim positif tetap terlihat dalam
record kandidat dan system_positive_count untuk audit, tetapi tidak mengganti
status not_evaluable menjadi hasil eksperimen yang lengkap.

Contoh sintetis pada budget 10:

- Satu positive, dua inconclusive, tujuh negative: keputusan positive.
- Tanpa positive, dua inconclusive, delapan negative: keputusan inconclusive.
- Sepuluh negative: keputusan negative.
- Satu positive lalu sesi gagal: not_evaluable; klaim positive tidak dihapus.

## INCONCLUSIVE tidak memicu pengulangan otomatis

Saat masih ada slot budget, loop meneruskan feedback untuk kandidat baru
yang unik. Tidak ada tambahan konfirmasi kandidat lama. Setelah budget
terpenuhi, run inconclusive selesai dengan hasil tersebut.

Tidak ada pengulangan run sampai memperoleh keputusan biner, penggantian
seed, atau permintaan validator untuk mengubah klaim model menjadi negative.
Replikasi berikutnya adalah pengulangan pipeline yang sudah direncanakan,
bukan pengganti run inconclusive. Semua hasil dipertahankan.

Runtime invalid tetap mengikuti kebijakan pemulihan attempt yang berbeda:
perbaiki lingkungan, login baru, reset database, lalu attempt baru. Retry
runtime otomatis tetap nol. Attempt lama tidak dihapus.

## FPR: abstention terpisah dan coverage wajib

FPR utama tetap FP/(FP+TN), pada kondisi A/B dan ground truth negatif
S10-S12. Positive pada kontrol negatif adalah FP; negative adalah TN.
Run inconclusive tidak menjadi FP, TN, TP, atau FN. Pada target positif,
inconclusive juga tidak boleh otomatis menjadi FN.

Setiap kelompok FPR pada satu replikasi harus menyimpan:

- Jumlah unit negatif yang direncanakan.
- FP dan TN yang benar-benar memiliki keputusan biner evaluable.
- Jumlah run inconclusive, not_evaluable, dan unit yang belum tersedia.
- Decision coverage = jumlah keputusan biner evaluable / unit negatif direncanakan.

FPR utama hanya tersedia jika seluruh unit negatif yang direncanakan pada
kelompok tersebut memiliki keputusan biner evaluable. Pada ringkasan
keseluruhan satu replikasi, ini berarti ketiga S10-S12. Kelompok per teknik
memakai kontrol Impossible teknik yang sesuai dan ukuran sampelnya dicantumkan.
Kelompok tanpa skenario negatif, misalnya Low saja, memiliki FPR undefined.

Jika ada abstention, tampilkan status inconclusive dan primary_fpr=null.
Jika ada unit missing/not_evaluable, tampilkan incomplete dan primary_fpr=null.
Jangan melaporkan mean dua replikasi sebagai hasil tiga replikasi: mean/SD
utama antar-run memerlukan semua tiga FPR replikasi yang eligible.

Rasio FP/(FP+TN) pada subset yang sudah diputuskan boleh tersedia sebagai
diagnostic_decided_only_fpr, disertai coverage dan jumlah abstention. Ini
diagnostik bersyarat dan tidak menggantikan hasil utama atau menjadi dasar
klaim bahwa RAG menurunkan FPR ketika coverage A/B berbeda.
Jika FP+TN=0, rasio diagnostik juga null/undefined, bukan 0%.

Contoh sintetis: satu FP, satu TN, satu inconclusive menghasilkan coverage
2/3, rasio diagnostik 50%, dan FPR utama belum tersedia. Tiga inconclusive
menghasilkan coverage 0%, bukan FPR 0%. Satu FP dan dua TN menghasilkan
coverage 100% dan FPR replikasi 1/3. Semua angka ini bukan hasil eksperimen.

## PSR tetap mengikuti bukti kandidat

Run inconclusive yang memiliki budget eksekusi lengkap pada S1-S9 tetap
memiliki evidence kandidat yang dapat direview untuk PSR. Keraguan Qwen
bukan alasan menghapus kandidat valid dari penyebut atau mengganti status
bukti 3/3 menjadi gagal.

- MIXED_EVIDENCE dan CONSISTENT_NEGATIVE tetap dalam penyebut, kontribusi
  keberhasilan nol.
- CONSISTENT_POSITIVE memenuhi syarat bukti 3/3. Klaim Qwen inconclusive
  tidak menghapus bukti tersebut; anotasi validator menentukan penerimaan
  bukti sesuai protokol.
- Attempt runtime invalid atau budget eksekusi incomplete dikeluarkan dari
  analisis utama, dengan pencatatan kelengkapan.
- Eksekusi lengkap tetapi analisis model gagal dapat memiliki evidence siap
  review PSR, walaupun keputusan biner sistem tidak evaluable. Human review
  dan audit ledger tetap wajib; flag readiness bukan hasil metrik final.
- Impossible tidak masuk PSR utama. Perbandingan utama tetap B/C;
  PSR A dapat dilaporkan sebagai tambahan sesuai protokol.

## Implementasi dan batas kesiapan

- run_decision_policy.py menetapkan policy any-positive-else-abstain-v1.
- analyze_response.py membuat ringkasan run versi 1.2.0, dengan
  execution_status, binary_decision_eligible, decision_exclusion_reason,
  runtime_invalid_count, dan psr_evidence_eligible. Ledger kandidat tetap 1.1.0.
- confusion_class mengembalikan null untuk inconclusive/not_evaluable dan
  memeriksa konsistensi field ringkasan terhadap counts sebelum menilai.
- run_decision_evaluator.py memeriksa satu kelompok negatif per replikasi,
  budget, identitas kondisi/eksperimen, duplikasi, coverage, dan kelengkapan.
  Pemanggil harus memilih satu attempt final menurut ledger. Helper ini
  tidak memilih attempt atau memverifikasi hash sumber sebagai pengganti
  agregator formal T06.
- Config run_decision mengunci aturan; validator protokol menolak imputasi
  negatif, retry sampai biner, atau FPR utama dengan unit negatif unresolved.
- Penjagaan hash resume mencakup policy/evaluator/analysis/schema. Protokol
  v3 harus memakai eksperimen baru; jangan resume hasil lama dengan kode baru.
- Metadata extra_observation_rounds_max diperbaiki menjadi nol, sesuai
  kode yang telah menonaktifkan konfirmasi tambahan.

Paket validator, anotasi independen, agregator dataset formal, dan pilot
seluruh matriks tetap bagian T06/T07. Perubahan ini tidak menyatakan T06
selesai dan tidak menghasilkan FPR/PSR penelitian. Tidak dilakukan probe,
inferensi model nyata, atau reset database pada pengerjaan ini.

Verifikasi akhir: **92 test lulus**, 38 file Python lulus parsing, 11 definisi
schema JSON valid, konfigurasi v3 diterima untuk 99 condition-run, dan
git diff --check lulus. Empat contoh sintetis yang dihitung langsung oleh
helper serta hash 14 artefak ada dalam
[evidence offline](evidence/t01-run-decision-offline-2026-10-14.json).

Aturan final INCONCLUSIVE pada T01 ditutup. Metodologi laptop lokal/peran
LangChain kemudian ditetapkan pada
[keputusan metode](keputusan-metodologi-lokal-langchain-2026-10-14.md).
Urutan kondisi formal kemudian ditetapkan pada
[penutupan T01](keputusan-urutan-kondisi-2026-10-14.md), protokol v5.
