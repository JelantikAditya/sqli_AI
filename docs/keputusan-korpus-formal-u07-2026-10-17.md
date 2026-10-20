# Keputusan penggunaan korpus formal U07

Tanggal persiapan: 17 Oktober 2026.
**Status: disetujui peneliti pada 17 Oktober 2026.**
Persetujuan eksplisit dalam percakapan ini: "iya saya setuju", sebagai jawaban
atas permintaan penggunaan snapshot sembilan entri yang sama untuk eksperimen
formal. Receipt terikat hash tersedia di
[evidence keputusan](evidence/u07-formal-corpus-decision-2026-10-17.json).

## Snapshot yang disetujui

- File: `knowledge/sqli-entries.json`, sembilan entri dari OWASP WSTG v4.2
  dan PayloadsAllTheThings SQL Injection yang telah direview pada tahap pilot.
- SHA-256 korpus:
  `8e2aaf363b384eb686594b8968c38ae00fd078cfc9581d6a91d6617ba0ef4348`.
- SHA-256 source lock:
  `2c23da42f9db73c3241ca78e68da496b83ecdeb257bc46171e55fd69f3f6278b`.
- Knowledge base: `sqli-knowledge-ec9d1b2feda12dd3`.
- Sembilan dokumen pada index lokal cocok dengan serialisasi korpus utama;
  top-k 2, embedding Nomic, retrieval semantik global sebelum tiap run B.
- Context retrieval dipakai pada generasi/regenerasi. Analisis A/B tidak
  memakai retrieval, dan A tidak mengakses vector store.

Isi korpus/index tidak diubah selama U07. Penanda `researcher_review=pending`
di metadata lama tetap dipertahankan agar hash korpus yang sudah diindeks
tidak berubah; keputusan review dicatat terpisah dan ditautkan melalui hash.

## Dasar keputusan

Catatan [review peneliti 12 Oktober](evidence/review-peneliti-2026-10-12.md)
dan [review korpus](corpus-review-2026-10-11.md) tersedia. Dokumen review
korpus sebelumnya menyatakan penggunaan tahap pilot. Pada 17 Oktober peneliti
menyetujui snapshot identik ini untuk eksperimen formal DVWA dengan tiga
teknik dan empat level sesuai proposal, setelah gate U07 lainnya terpenuhi.

Korpus kandidat S3 pada pilot terpisah tidak termasuk usulan ini. Keputusan
ini tidak menyatakan semua payload efektif, dan tidak mengubah klaim model,
ground truth, keputusan validator, maupun hasil FPR/PSR.

## Rekaman keputusan

- Keputusan: **approved-for-formal-use**.
- Pemberi keputusan: peneliti.
- Tanggal keputusan: 17 Oktober 2026, Asia/Jakarta.
- Dasar: persetujuan eksplisit peneliti dalam percakapan, "iya saya setuju".
- Ruang lingkup yang disetujui: penggunaan hash korpus/index utama di atas
  untuk eksperimen formal dengan plan baru setelah seluruh gate U07 lulus.
- Status gate lain: budget lima run A/B dan release manifest tetap terbuka.
- Catatan: perubahan isi setelah keputusan memerlukan hash, review dan index
  baru serta pemeriksaan ulang gate yang terdampak.
