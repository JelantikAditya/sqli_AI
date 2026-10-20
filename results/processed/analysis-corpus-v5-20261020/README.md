# Audit draft korpus analisis v5

Hasil authoring dan pemeriksaan pada 20 Oktober 2026. Acuan terkini adalah
audit.final.json serta researcher-review.final.template.json. Draft memuat
tujuh chunk/35 field/38 pernyataan, dengan empat dokumen sumber dan sembilan
rentang rujukan. Review peneliti masih pending.

preservation-baseline.json mencatat keadaan sebelum penyusunan draft. Audit
akhir memeriksa 1.053 file tetap sama, termasuk 959 file inventory formal.
Audit awal audit.json dan researcher-review.template.json dipertahankan sebagai
riwayat sebelum koreksi locator fungsi lokal. Keduanya sudah digantikan oleh
artefak berakhiran final untuk review draft yang sekarang.

Pemeriksaan ulang tanpa model, embedding, jaringan atau target:

```powershell
.\.venv\Scripts\python.exe development/validate_analysis_corpus_v5.py
```

Pemeriksaan memerlukan snapshot lokal dan inventory yang dikecualikan dari Git.
Hasilnya bukan akurasi model, nilai FPR/PSR, atau bukti peningkatan RAG.
Lihat [laporan lengkap](../../../docs/korpus-analisis-v5-2026-10-20.md).
