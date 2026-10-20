# Analysis knowledge v5 draft

Draft 20 Oktober 2026 untuk interpretasi bukti HTTP SQLi. Tujuh chunk disusun
berdasarkan tugas analisis, dengan provenance per pernyataan. Status seluruh
review peneliti masih pending. Panduan utama:
[laporan dan cara review](../../docs/korpus-analisis-v5-2026-10-20.md).

- corpus.json: konten draft, 35 field/38 pernyataan dan metadata kontrak prompt.
- sources.lock.json: sumber, versi snapshot, hash dan sembilan rentang rujukan.
- [Audit akhir](../../results/processed/analysis-corpus-v5-20261020/audit.final.json).
- [Form review](../../results/processed/analysis-corpus-v5-20261020/researcher-review.final.template.json).

Teks corpus.json berupa parafrasa singkat dan adaptasi editorial. Bagian OWASP
mengatribusikan WSTG v4.2 beserta versi commit dan lisensi CC BY-SA 4.0. Parafrasa
PortSwigger mengatribusikan masing-masing halaman pada source lock; tidak ada
klaim bahwa lisensi OWASP mencakup konten PortSwigger. Snapshot lengkap hanya
disimpan sebagai referensi lokal pada data/raw yang dikecualikan dari Git.

Tidak ada contoh sintetis, payload baru, embedding atau pengukuran model dalam
draft ini. Metadata prompt_contract ditempatkan di luar teks retrieval dan
mendokumentasikan aturan proyek yang perlu tersedia pada prompt kedua kondisi.
