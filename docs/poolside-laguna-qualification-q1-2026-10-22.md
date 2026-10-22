# Qualification Poolside Laguna Q1, 22 Oktober 2026

## Keputusan

Qualification terpisah `poolside-s21-p3-q1-20261022` telah mengeksekusi semua
24 unit A/B. Hasilnya **gagal gate kelengkapan**: 19 unit mencapai 10 kandidat
valid, sedangkan 5 unit dikecualikan setelah anggaran generasi tidak terpenuhi.
Karena syaratnya setiap unit harus mencapai 10 kandidat, `qualification_passed`
dan `formal_eligible` bernilai `false`. Cohort ini tidak menghasilkan metrik
formal FPR atau PSR.

## Cakupan dan kelengkapan

| Kondisi | Unit lengkap | Unit excluded | Kandidat valid | Target kandidat |
| --- | ---: | ---: | ---: | ---: |
| A, tanpa RAG | 12/12 | 0 | 120 | 120 |
| B, dengan RAG | 7/12 | 5 | 109 | 120 |
| Total | 19/24 | 5 | 229 | 240 |

Unit yang tidak mencapai kuota adalah B/S4 (9/10), B/S7 (9/10), serta B/S8,
B/S11, dan B/S12 (masing-masing 7/10). Semua 12 unit kondisi A lengkap.
Kegagalan terkonsentrasi di kondisi B, tetapi hasil ini sendiri belum
membuktikan bahwa RAG menyebabkan masalah; hubungan antara konteks retrieval,
format keluaran, dan duplikasi kandidat perlu ditinjau.

Audit generasi menunjukkan respons pertama slot yang gagal pada B/S4 dan B/S7
tidak memenuhi format kandidat, lalu dua percobaan fallback tidak menghasilkan
kandidat valid yang berbeda. Pada B/S8, B/S11, dan B/S12, slot akhir kehabisan
hingga tiga percobaan tanpa kandidat valid yang unik. Retry untuk generasi
memang terjadi sesuai protokol. Penyebabnya bukan error transport.

## Audit awal efek retrieval pada generasi kondisi B

Audit deskriptif atas event generasi menunjukkan pola yang perlu ditindaklanjuti:

| Indikator generasi | A, tanpa RAG | B, dengan RAG |
| --- | ---: | ---: |
| Unit lengkap | 12/12 | 7/12 |
| Percobaan generasi | 133 | 141 |
| Kandidat yang diterima | 120 | 109 |
| Respons berformat kandidat tidak valid | 5 | 3 |
| Percobaan berstatus `no_valid_distinct_candidate` | 8 | 29 |
| Rata-rata token prompt per request generasi, termasuk retry | 782,9 | 1.565,5 |
| Median token prompt per request generasi | 818 | 1.627 |

Dengan demikian, sinyal utama di B bukan kenaikan respons berformat salah, tetapi
lebih banyak percobaan yang ditolak karena tidak menghasilkan kandidat baru
yang lolos kebijakan keunikan. Satu slot dapat menghasilkan lebih dari satu
percobaan tersebut selama retry. Prompt generasi B juga memakai kira-kira dua
kali token prompt A per request. Itu adalah biaya konteks yang teramati, bukan
bukti bahwa latensi atau akurasi model memburuk.

Pada 12 pasangan skenario, terdapat lima pasangan A lengkap/B gagal dan nol
pasangan A gagal/B lengkap. Uji eksak berpasangan dua sisi menghasilkan
`p = 0,0625`. Jumlah pasangan kecil dan ini hanya satu replikasi, sehingga
hasilnya bersifat eksploratif dan belum cukup untuk menyatakan efek kausal.

Setiap unit B menerima dua chunk retrieval. Metadata `vulnerability_type`
sesuai dengan teknik skenario pada 24 dari 24 penempatan chunk. Namun, pasangan
dua chunk yang sama dipakai ulang pada keempat level DVWA untuk masing-masing
teknik, dan seluruh 24 teks chunk menyertakan `payload_examples`. Belum ada
review manusia yang menilai relevansi semantik tiap chunk terhadap skenario
dan level. Karena itu, kemungkinan contoh payload mengarahkan generasi ke pola
yang sama dan mengurangi keragaman adalah hipotesis yang masuk akal, bukan
temuan kausal atau bukti bahwa chunk tersebut tidak relevan.

Penelitian primer menunjukkan efek RAG bergantung pada mutu dan penggunaan
konteks. Konteks yang relevan dan bermutu tinggi dapat membantu generasi kode,
sementara studi pada retrieval QA mendapati konteks yang tidak relevan dapat
menurunkan akurasi. Studi lain juga melaporkan bahwa menambah dokumen tidak
memberi efek yang selalu monoton, sehingga lebih banyak konteks tidak otomatis
lebih baik. Temuan posisi informasi pada konteks panjang juga relevan sebagai
mekanisme umum, tetapi tidak boleh langsung dipakai untuk menjelaskan Q1:
prompt B rata-rata sekitar 1.566 token dan tugas eksperimennya berbeda.

- Wang et al., [CodeRAG-Bench: Can Retrieval Augment Code Generation?](https://aclanthology.org/2025.findings-naacl.176/), Findings of NAACL 2025.
- Yoran et al., [Making Retrieval-Augmented Language Models Robust to Irrelevant Context](https://arxiv.org/abs/2310.01558), studi primer pada lima benchmark open-domain QA.
- Cuconasu et al., [The Power of Noise: Redefining Retrieval for RAG Systems](https://arxiv.org/abs/2401.14887), studi primer tentang relevansi, posisi, dan jumlah passage.
- Liu et al., [Lost in the Middle: How Language Models Use Long Contexts](https://aclanthology.org/2024.tacl-1.9/), TACL 2024; studi konteks panjang, bukan replika kondisi Q1.

Kesimpulan untuk Q1: penambahan retrieval berkorelasi dengan penurunan
kelengkapan generasi dan kenaikan token prompt, terutama pada kegagalan
keragaman kandidat. Q1 belum mengukur PSR atau FPR, sehingga belum diketahui
apakah kualitas deteksi SQLi membaik atau memburuk. Sebelum qualification baru,
profil B dan perlakuan terhadap contoh payload perlu ditinjau, dibekukan dengan
versi dan ID cohort baru, lalu diuji ulang pada seluruh 24 unit. Jangan
mengubah profil atau mengisi unit Q1 secara retroaktif.

## Layanan dan target lokal

- Laguna S 2.1 melaporkan model `poolside/laguna-s-2.1` pada semua 503 request.
- Seluruh 503 request menerima HTTP 200 dan status transport `ok`: 274 request
  generasi dan 229 request analisis. Tidak ada transport failure yang tercatat.
- Pemakaian tercatat 596.433 prompt token dan 68.038 completion token, total
  664.471 token. Latensi kumulatif respons API 2.539,545 detik; median 4,43
  detik per request.
- Runner melakukan 24 reset database DVWA lokal dan 5.010 request HTTP ke
  target. Ini adalah hasil qualification generasi, bukan pengukuran FPR/PSR.

## Batas interpretasi dan tindak lanjut

Qualification ini hanya menguji kelengkapan generasi pada 12 skenario A/B
dengan satu replikasi. Hasil kandidat atau keputusan sistem pada unit lengkap
tidak divalidasi manual buta dan tidak boleh diperlakukan sebagai dataset
formal. Data Q1 juga tidak digabung dengan pilot Poolside sebelumnya, Qwen,
atau hasil model lokal.

Audit awal event generasi dan perbedaan A/B diringkas pada bagian di atas;
relevansi semantik chunk terhadap skenario dan level masih belum dinilai
manual. Jika profil prompt atau strategi fallback diubah, bekukan perubahan
dan buat ID qualification baru. Ulangi gate dengan seluruh 24 unit pada profil
yang sama sebelum menyusun budget tiga replikasi formal. Jangan mengisi slot
yang gagal secara retroaktif atau menggabungkan Q1 dengan cohort baru.

## Artefak

- Assessment mesin: `results/raw/pilot/poolside-s21-p3-q1-20261022/qualification-assessment.json`
- Ledger dan checkpoint: direktori raw yang sama, diabaikan Git.
- Ringkasan metadata yang aman untuk Git: [evidence Q1](evidence/poolside-laguna-qualification-q1-2026-10-22.json).
- Plan yang dipin: [plan qualification](../development/poolside_laguna_qualification_plan_20261022.json).

Konten kandidat, prompt, respons mentah, kredensial API, dan artefak target
tetap berada di `results/raw/` lokal dan tidak dimasukkan ke laporan ini.
