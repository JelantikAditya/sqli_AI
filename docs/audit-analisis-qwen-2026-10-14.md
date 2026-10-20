# Audit analisis Qwen pada evidence S1

Tanggal: 14 Oktober 2026, Asia/Jakarta.
Scope: audit pengembangan atas evidence yang sudah tersimpan dan replay fixture
lokal; bukan hasil FPR/PSR formal.

## Temuan akar masalah

Pada pilot LangChain S1 A/B, tujuh kandidat kondisi B memenuhi indikator
diagnostik executor pada ketiga konfirmasi. Untuk tiap kandidat yang diperiksa,
evidence analisis memiliki tiga pasangan baseline/kandidat. Daftar diagnostics
baseline kosong; kandidat memuat `mysql_syntax_error`. Output Qwen menyebut
perbedaan ini dengan benar, tetapi menetapkan `negative` dan
`no_new_database_diagnostic`. Record berhasil dinormalisasi ulang dari evidence
dan output tersimpan dengan hasil yang identik. Karena itu ketidaksesuaian ada
pada klasifikasi model, bukan ekstraksi diagnostik, bukti yang hilang, atau
normalizer.

Input lama mengirim enam observasi datar dengan response hash, elapsed time,
dan content marker yang tidak relevan untuk indikator error-based. Prompt
sebelumnya memberi aturan per trial, tetapi tetap meminta Qwen meringkas banyak
observasi tanpa struktur pasangan. Ini menjelaskan kondisi yang memicu kesalahan,
belum membuktikan sebab internal model secara umum.

## Replay fixture tetap

Replay v5 dan v6 memakai tujuh fixture tersanitasi dari evidence kandidat
tersimpan: diagnostik 3/3 dan 0/3, mixed 1/3 dan 2/3, HTTP 500 generik,
konfirmasi hanya dua trial, serta sesi invalid. Hanya fixture 3/3 positif
terklasifikasi benar oleh v6. Empat fixture yang runtime valid tetapi harus
negatif, mixed, atau inconclusive tetap salah. Sesi invalid benar dihentikan
sebelum inferensi. Ketidaksesuaian keputusan tetap menjadi output Qwen yang
disimpan; sinyal evidence dan klaim model adalah field terpisah.

Pada replay parser terbaru, tujuh output model v6 yang tersimpan dinormalisasi
ulang tanpa inferensi baru: hasilnya 2/7 cocok. Setelah layanan Ollama aktif,
inferensi segar pada tujuh fixture menghasilkan hasil yang sama. Dari enam
fixture dengan evidence valid, hanya satu klaim Qwen yang cocok; fixture sesi
invalid ditolak tanpa inferensi dan dihitung sebagai satu kecocokan tambahan
pada agregat 2/7. Parser kini menambahkan
`model_claim_evidence_mismatch` pada tujuh record sumber yang klaim negatifnya
berlawanan dengan konfirmasi executor positif 3/3. Ini mengubah kelengkapan
peringatan audit, bukan klaim model atau evidence. Percobaan inferensi segar
v9 memakai `qwen2.5:7b` yang terpasang lokal dan memverifikasi perilaku inferensi
terbaru. Hasil ini tetap merupakan replay pengembangan, bukan hasil formal.

Review alasan dan referensi output v9 memperjelas pola yang gagal:

- Pada bukti diagnostik 3/3, Qwen memberi klaim `positive` yang benar, tetapi
  hanya merujuk tiga observasi kandidat dan tidak menyertakan observasi baseline.
  Karena bukti indikator error harus membandingkan keduanya, ledger menandai
  `claim_supported=false`.
- Pada evidence lengkap 0/3, Qwen memberi `inconclusive`, padahal aturan tetap
  mengharuskan `negative`.
- Pada evidence mixed 1/3 dan 2/3, Qwen memberi `negative`, padahal keduanya
  harus `inconclusive`.
- HTTP 500 tanpa diagnostik diberi `inconclusive`, bukan `negative`.
- Pada input hanya dua trial yang keduanya positif, Qwen memberi `positive`
  walau trial ketiga wajib ada; ledger menandai klaim itu tidak didukung.
- Sesi invalid dihentikan dengan benar tanpa inferensi.

Pola ini konsisten dengan kegagalan menerapkan aturan keputusan per-trial dan
melengkapi sitasi evidence. Hasil observasi tidak cukup untuk menyimpulkan
mekanisme internal model. Detail per fixture ditambahkan ke evidence U01; klaim
Qwen tetap dipertahankan terpisah dari sinyal executor.
Rancangan perbaikannya, termasuk batas metodologi dan gate penerimaan, ada di
[rencana perbaikan U01](rencana-perbaikan-u01-qwen.md).

## Implementasi kontrak v7 dan regression replay

Kontrak v7 menambahkan `trial_assessments` per konfirmasi, pemeriksaan semantik
terhadap sinyal executor, kelengkapan referensi per pasangan, serta warning saat
klaim akhir bertentangan dengan ringkasan asesmen model. Klaim Qwen tetap utuh;
record historis tanpa asesmen per-trial tetap dapat dibaca. Tes semantik mencakup
0/1/2/3 konfirmasi, trial hilang, referensi pasangan, serta pasangan khusus
error-based, boolean-based, dan time-based.

Suite penuh lulus 145 tes dan semua schema JSON valid. Regression replay v7 pada
tujuh fixture lama cocok pada 3/7 kasus secara keseluruhan, termasuk sesi
invalid yang dihentikan tanpa inferensi. Pada enam kasus valid, 2/6 klaim cocok.
Perbaikan terlihat pada sitasi penuh untuk bukti positif 3/3 dan klasifikasi
HTTP 500 tanpa diagnostik sebagai negatif. Kasus 0/3 masih menjadi
`inconclusive`, mixed 1/3 dan 2/3 masih dinilai negatif, dan dua trial positif
masih dinilai positif walau trial ketiga tidak ada. Warning baru menangkap
ketidaksesuaian asesmen per-trial atau klaim akhir. Pada saat catatan v7 dibuat,
gate internal lama masih mensyaratkan kecocokan semua fixture.

## Revisi prompt v8 dan replay diagnostik

Pemeriksaan output v7 menunjukkan tiga pola: pada 0/3, asesmen per-trial sudah
negative tetapi verdict akhir menjadi inconclusive; pada mixed 1/3 dan 2/3,
model kadang melewatkan indikator di trial positif; pada dua trial positif,
model memilih positive walau trial ketiga tidak tersedia. Prompt v8 memperjelas
urutan klasifikasi per trial, penghitungan hasil 0/3 sampai 3/3, dan aturan
bahwa trial yang hilang menghasilkan inconclusive.

Replay v8 pada tujuh fixture tetap cocok pada 5/7 kasus keseluruhan dan 4/6
kasus dengan runtime valid. Dibanding v7, mixed 1/3 dan dua trial positif kini
menghasilkan klaim akhir inconclusive. Pada mixed 1/3, asesmen trial tetap
bertentangan dengan diagnostik executor. Kasus 0/3 masih inconclusive walau
semua asesmen trial negative; mixed 2/3 masih negative dengan asesmen trial
yang mengabaikan dua indikator positif. Tidak ada request ke DVWA pada replay
ini. Peneliti kemudian menyetujui pemisahan gate implementasi dari kinerja
model; replay ini tetap menjadi observasi pengembangan, bukan gate pass/fail,
FPR, atau PSR.

Artefak v8 berada di `results/raw/u01-replay-v11-v8-count-trials-20261014/`.
Hash summary `32f701835166916c7f51cec5022634fbe8c927eefd1e901e3d9d0ca3d91d20c3`,
hash replay `58c798312a68cb4bac1d00a270701f5b63d8b12fe6e7d5c4033e094638a0d7af`,
dan hash prompt `0cc06b64fbb3cf8fc1f47a7f118cc5baf4cb98b62ffed58275c6abb4b8544209`.
Suite penuh kembali lulus 145 tes; semua 11 schema JSON valid.

## Validasi tertutup satu kali pada tiga teknik

Setelah prompt v8 dibekukan, satu set 21 fixture dijalankan: tujuh per teknik,
dengan positif 3/3, negatif 0/3, mixed 1/3, mixed 2/3, dua trial positif,
kontrol teknik, dan runtime-invalid. Label expected dibangun dan diverifikasi
terhadap aturan executor sebelum inferensi, lalu tidak dimasukkan ke input
Qwen. Ini validasi kontrak pengembangan sintetis, bukan anotasi manusia atau
eksperimen DVWA.

Qwen cocok pada 14/21 fixture keseluruhan dan 11/18 yang runtime-valid. Hasil
per teknik adalah error-based 5/7 (4/6 valid), boolean-based 5/7 (4/6 valid),
dan time-based 4/7 (3/6 valid). Ketiga kasus positif 3/3, ketiga kasus dua
trial positif, serta ketiga runtime-invalid ditangani sesuai expected. Pada
time-based, model memberi positive untuk 0/3, mixed 1/3, dan kontrol teknik.
Ketiganya memiliki selisih kandidat dan kontrol 90 ms, jauh di bawah ambang
1500 ms; asesmen trial model menyatakan positive dan audit menandai mismatch.

Artefak validasi tersimpan di `results/raw/u01-closed-v1-20261014/`. Hash file
fixture `ae7ea1b345cf786f6c38888d6ee40daf49783298aa62c58d9b6fb4f6a31f3c16`,
hash replay `fdc3071f0172aa80c6289d98adc348bed604c40671777b2ff624661dfde0ad45`,
hash summary `270d5bdf1312efeea51d3974b5f72eb4c84980cd657520b9cba7015b413bcb99`,
hash prompt `0cc06b64fbb3cf8fc1f47a7f118cc5baf4cb98b62ffed58275c6abb4b8544209`,
dan hash schema `1d3d9b3e673e65b1810a8a94fbce0293403eec992ac056d2f54c8e8d8da58c37`.
Set validasi kini terbuka; prompt tidak akan dituning menggunakan hasilnya.
Validasi ini tidak menghasilkan FPR/PSR dan tidak menggantikan validator
independen yang belum ditetapkan.

Prompt v6 menyajikan observasi berkelompok menurut trial dan memberi aturan
langsung per teknik. Replay tidak cukup untuk memakai v6 pada pilot. Saya tidak
melanjutkan penyetelan prompt berulang berdasarkan hasil fixture yang sama.
Langkah yang dicatat adalah menambahkan warning `model_claim_evidence_mismatch`
ketika klaim biner Qwen berlawanan dengan status konfirmasi deterministik, tanpa
mengubah klaim atau system decision. Warning membantu audit dan feedback; ia
tidak menggantikan peran model dan tidak menyamarkan kesalahan sebagai keputusan
validator.

Ringkasan, hash sumber, hash prompt, dan hasil per fixture ada di
[evidence replay U01](evidence/u01-qwen-replay-2026-10-14.json). Replay lengkap
dan output model tersimpan lokal di `results/raw/u01-replay-v5-20261014/` dan
`results/raw/u01-replay-v6-20261014/`; normalisasi tersimpan ada di
`results/raw/u01-replay-v8-20261014/`, dan inferensi segar di
`results/raw/u01-replay-v9-20261014/`. Tidak ada request yang dikirim ke DVWA.

## Dampak pada feedback generator

Feedback kandidat sekarang menerangkan bahwa `evidence_status` adalah hasil
pengukuran terstruktur, sedangkan keputusan Qwen merupakan interpretasi
terpisah. Untuk status positif 3/3, generator diminta tetap memenuhi budget
kandidat berikutnya dengan ekspresi berbeda, bukan mengulangi variasi kandidat
karena klaim Qwen yang bertentangan. Prompt mengarahkan keragaman sintaks per
slot dan seed generation dibedakan secara deterministik per slot; A/B menerima
profil dan urutan seed yang sama.

Perubahan keragaman masih memerlukan hasil pilot A/B. Lihat plan dan ledger
`u02-s1-ab-diversity-20261014`; perubahan belum dianggap berhasil sampai
kondisi A/B selesai 10/10 kandidat dengan tiga konfirmasi setiap kandidat.

Pilot tersebut juga mengungkap lemahnya guard khusus adaptive S1: kandidat A
pertama berisi `WAITFOR DELAY`, yaitu teknik waktu di luar S1 error-based.
Kandidat sempat dieksekusi sebelum run dikecualikan karena budget tidak lengkap.
Kondisi B hanya mencoba generasi yang berisi `SLEEP(5)` dan berhenti setelah
batas retry; tidak ada kandidat B dieksekusi. Ledger mempertahankan kedua run
sebagai `metric_eligible=false`. Guard adaptive S1 kini menolak delay dari
berbagai DBMS serta statement bertumpuk sebelum eksekusi. Ini gate operasional
yang harus lulus fixture sebelum pilot live berikutnya.

## Batas interpretasi

- Qwen tetap dapat keliru pada input valid; angka replay ini tidak mengukur FPR
  atau PSR.
- Validasi manusia independen belum tersedia. Identitas validator masih harus
  ditetapkan sebelum anotasi final.
- Warning hasil perubahan pengembangan harus diuji pada ledger baru. Artefak
  pilot lama tetap bukti historis dan tidak diubah.
