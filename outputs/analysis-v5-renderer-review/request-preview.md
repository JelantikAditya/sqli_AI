# Pratinjau request Qwen v5 rev2

Ini payload yang disiapkan, belum dikirim ke Qwen. Review isi sebelumnya berbantuan AI; adopsi peneliti belum tercatat.

A dan B memakai system prompt, schema, opsi dan paired evidence yang sama. B menerima referensi tambahan. Top-3 adalah pratinjau sekunder yang sudah direncanakan, belum pilihan pilot.

| Teknik | Payload A | Payload B top-2 | Payload B top-3 | Topik inti tertinggal pada top-2 |
| --- | --- | --- | --- | --- |
| error-based | [A](view-001.A.request.json) | [B top-2](view-001.B-top2.request.json) | [B top-3](view-001.B-top3.request.json) | baseline-comparison |
| boolean-based blind | [A](view-004.A.request.json) | [B top-2](view-004.B-top2.request.json) | [B top-3](view-004.B-top3.request.json) | marker-stability |
| time-based blind | [A](view-007.A.request.json) | [B top-2](view-007.B-top2.request.json) | [B top-3](view-007.B-top3.request.json) | timing-confounders |

Periksa messages[0].content, messages[1].content, format dan options pada file JSON. Isi user message adalah JSON dengan measured_evidence terlebih dahulu, lalu reference_context.

Semua sembilan pasangan probe mempertahankan paired evidence lengkap pada kedua profil. Probe hanya memeriksa bentuk input, bukan holdout atau evaluasi keputusan model.

Top-2 mencakup satu dari dua topik teknik yang diwajibkan rubrik sementara pada setiap query utama. Top-3 mencakup keduanya, tetapi berisi seluruh tiga chunk yang eligible untuk teknik itu. Angka ini bukan precision retrieval independen.

Guard byte tidak memotong bukti atau chunk. Jumlah token tepat dan truncation di runtime Qwen belum diperiksa; keduanya merupakan preflight sebelum pilot chat.
