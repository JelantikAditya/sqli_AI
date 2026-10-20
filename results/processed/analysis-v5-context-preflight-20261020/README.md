# Preflight konteks dan penilaian relevansi v5

Preflight selesai pada 20 Oktober 2026. Ada 36 hitungan request offline dan
sembilan probe Qwen runtime, dengan keluaran sengaja dihentikan setelah satu
token. Tidak ada verdict yang dievaluasi atau request DVWA.

- design.json: rencana probe sebelum eksekusi, context 4096/output reserve 768.
- offline-token-counts.json: semua request top-2/top-3 yang sudah dipersiapkan.
- runtime-context-summary.json: sembilan prompt_eval_count cocok persis dengan
  hitungan lengkap. Maksimum 1684 token; minimum headroom setelah reserve 1644.
- preservation-baseline.json: 1126 file terdahulu tetap utuh.
- relevance-review.ai.json: 36 penilaian isi oleh AI sesudah ranking, dengan
  human_grade tetap kosong. Tidak mengganti rubrik awal atau menjadi gold manusia.
- pilot-profile.candidate.json: A versus B3 sebagai kandidat, B2 pembanding
  sekunder. Stop khusus preflight tidak masuk pilot. Belum ada pilot performa.

Verifikasi tanpa model atau jaringan:

```powershell
.\.venv\Scripts\python.exe development/verify_analysis_v5_context.py
```

Membutuhkan tokenizer, metadata dan respons lokal di results/raw. Lihat
[laporan dan batas klaim](../../../docs/preflight-konteks-dan-profil-v5-2026-10-20.md).
