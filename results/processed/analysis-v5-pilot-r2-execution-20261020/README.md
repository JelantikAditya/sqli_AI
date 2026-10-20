# Hasil pilot analisis v5 r2

Peneliti menyetujui penjelasan r2 dan kelanjutan pilot melalui pesan langsung sebelum inferensi.
Receipt adopsi disimpan terpisah; metadata pending pada paket lock adalah snapshot saat freeze.
Kasus sintetis buatan AI; persetujuan bukan gold manusia independen atau bukti manfaat RAG formal.

| Profil | Benar / dicoba | Akurasi | Error | Trial benar / tersedia | Reason accuracy | Reason consistency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 23/36 | 63.89% | 0 | 75/102 | 63.89% | 100.00% |
| B2 | 24/36 | 66.67% | 0 | 74/102 | 66.67% | 100.00% |
| B3 | 24/36 | 66.67% | 0 | 74/102 | 66.67% | 100.00% |

Status sesi: completed. Kesimpulan prespecified: improvement-on-this-synthetic-dataset.
Delta akurasi A/B3 (B3 dikurangi A), poin persentase: 2.7777777777777777.

Transisi pasangan A/B3:

- wrong_to_correct: 1; ID: pilot-011.
- correct_to_wrong: 0; ID: tidak ada.
- both_correct: 23; ID: pilot-001, pilot-002, pilot-003, pilot-004, pilot-005, pilot-006, pilot-007, pilot-008, pilot-009, pilot-010, pilot-013, pilot-014, pilot-018, pilot-021, pilot-022, pilot-023, pilot-024, pilot-025, pilot-026, pilot-027, pilot-028, pilot-034, pilot-036.
- both_wrong: 12; ID: pilot-012, pilot-015, pilot-016, pilot-017, pilot-019, pilot-020, pilot-029, pilot-030, pilot-031, pilot-032, pilot-033, pilot-035.

B2 pembanding deskriptif; B3 memuat seluruh tiga chunk eligible per teknik.
Hasil A/B3 tidak mengisolasi manfaat selektivitas ranking retrieval.
Tidak ada perubahan hasil formal R1/R2/R3 atau FPR/PSR formal.

Reproduksi audit tanpa model atau DVWA:

```powershell
.\.venv\Scripts\python.exe maintenance/audit_analysis_v5_pilot_rev2.py
```
