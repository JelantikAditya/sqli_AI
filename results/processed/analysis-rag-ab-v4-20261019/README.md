# Hasil pilot RAG pada analisis respons v4

Tanggal: 19 Oktober 2026. Model qwen2.5:7b, seed 42, satu pass.
Klaim mentah Qwen merupakan keluaran utama. Ini pilot sintetis pengembangan,
bukan holdout independen atau metrik formal.

| Ukuran pada 18 kasus valid baru | A tanpa retrieval | B dengan retrieval |
| --- | ---: | ---: |
| Verdict sesuai evaluator | 12/18 | 12/18 |
| Asesmen trial sesuai indikator | 37/51 | 37/51 |
| Kode sesuai decision | 18/18 | 18/18 |
| Kontrol positif terdeteksi | 2/3 | 2/3 |
| Klaim positif pada enam fixture negatif | 3 | 3 |
| Coverage biner fixture negatif | 6/6 | 6/6 |

Semua 18 pasangan valid mempunyai verdict dan asesmen trial yang sama.
Tambahan retrieval pada konfigurasi ini belum menunjukkan peningkatan.
Kriteria peningkatan verdict dan pengurangan klaim positif keliru tidak
tercapai. Varian belum dipromosikan ke runner formal.

Gate v3 tetap sekunder: kedua kondisi menjadi 14/18 tepat dan nol klaim
positif pada fixture negatif, dengan coverage negatif turun ke 3/6. Efek
abstention gate tidak diatribusikan sebagai manfaat RAG.

Ada 36 inferensi dan dua skip baseline invalid. Dua belas uji offline lulus.
Audit mereproduksi 38 record, memeriksa 19 pasangan request, serta memastikan
959 sumber formal dan 26 artefak v1/v2/v3 tetap utuh. Semua inferensi selesai
dengan stop. Tidak ada request DVWA atau perhitungan ulang FPR/PSR formal.

## Berkas dan sumber

| Berkas | Isi |
| --- | --- |
| summary.json | Hasil utama mentah A/B, gate sekunder, pasangan kasus dan kriteria. |
| design-manifest.json | Desain dan source/input hash sebelum embedding. |
| manifest.json | Retrieval, vektor dan request dipin sebelum inferensi. |
| runtime.json | Digest model/embedding, versi Chroma dan waktu retrieval. |
| audit.json | Reproduksi record, kesamaan A/B dan pemeriksaan cosine/sumber. |
| retrieval.json | Query, candidate pool, jarak dan dua referensi terpilih per teknik. |
| analysis-corpus.json | Proyeksi sembilan pola pengetahuan tanpa payload contoh. |
| provenance.json | Hash salinan di sini dan artefak lokal. |

Tujuh berkas pertama disalin byte-for-byte dari
results/raw/development/analysis-rag-ab-v4-20261019/. Input, label evaluator,
vektor embedding, request, output mentah dan QA konteks tersedia pada arsip
lokal tersebut.

Proyeksi korpus merupakan adaptasi editorial dari OWASP WSTG v4.2 dan
PayloadsAllTheThings melalui korpus proyek yang dipin. Lisensi CC BY-SA 4.0;
lihat [atribusi dan lisensi](../../../knowledge/NOTICE.md). Payload contoh,
root cause dan mitigation dihilangkan; dua frasa nama target dianonimkan.
Source_refs mewarisi referensi entri asal dan bukan review independen per kalimat.

Filter teknik dan integritas sumber/ranking lulus. Kesesuaian teknik berasal
dari filter metadata, bukan gold relevansi semantik independen. Hasil sama
pada set kecil ini tidak menetapkan ekuivalensi metode secara umum.

Lihat [laporan lengkap dan batas interpretasi](../../../docs/pilot-rag-analisis-v4-2026-10-19.md).
