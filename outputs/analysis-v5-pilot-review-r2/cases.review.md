# Review paket pilot v5

Seluruh kasus dan label adalah sintetis buatan AI. Review peneliti masih pending.

Periksa label pada tabel ini, kebijakan metrik/error pada protocol.lock.json, dan request aktual. Jangan masukkan label ini ke prompt/retrieval.

| ID | Teknik | Referensi kontrak | Asesmen trial | Alasan |
| --- | --- | --- | --- | --- |
| pilot-001 | error-based | positive | 1:positive, 2:positive, 3:positive | One newly supplied syntax identifier in every trial |
| pilot-002 | error-based | positive | 1:positive, 2:positive, 3:positive | New XPath diagnostic with status variation |
| pilot-003 | error-based | positive | 1:positive, 2:positive, 3:positive | New unknown-column diagnostic |
| pilot-004 | error-based | positive | 1:positive, 2:positive, 3:positive | Different nonempty new diagnostic sets |
| pilot-005 | error-based | negative | 1:negative, 2:negative, 3:negative | HTTP 500 alone has no database diagnostic |
| pilot-006 | error-based | negative | 1:negative, 2:negative, 3:negative | Status differences alone |
| pilot-007 | error-based | negative | 1:negative, 2:negative, 3:negative | Redirect without diagnostic |
| pilot-008 | error-based | negative | 1:negative, 2:negative, 3:negative | Candidate response change without diagnostic |
| pilot-009 | error-based | inconclusive | 1:positive, 2:negative, 3:negative | One positive trial |
| pilot-010 | error-based | inconclusive | 1:positive, 2:negative, 3:positive | Two positive trials |
| pilot-011 | error-based | inconclusive | 1:positive, 3:positive | Only trials 1 and 3 |
| pilot-012 | error-based | inconclusive | 1:negative, 2:negative | Only trials 1 and 2, both negative |
| pilot-013 | boolean-based blind | positive | 1:positive, 2:positive, 3:positive | Opposed markers, HTTP 200 on both sides |
| pilot-014 | boolean-based blind | positive | 1:positive, 2:positive, 3:positive | Missing marker with HTTP 404 |
| pilot-015 | boolean-based blind | positive | 1:positive, 2:positive, 3:positive | Stable direction despite status variation |
| pilot-016 | boolean-based blind | positive | 1:positive, 2:positive, 3:positive | Stable markers across alternate status pattern |
| pilot-017 | boolean-based blind | negative | 1:negative, 2:negative, 3:negative | Opposed markers in the wrong direction |
| pilot-018 | boolean-based blind | negative | 1:negative, 2:negative, 3:negative | Both sides have the same marker |
| pilot-019 | boolean-based blind | negative | 1:negative, 2:negative, 3:negative | Database diagnostic invalidates opposed-marker indicator |
| pilot-020 | boolean-based blind | negative | 1:negative, 2:negative, 3:negative | Candidate comparison status invalid, baseline remains valid |
| pilot-021 | boolean-based blind | inconclusive | 1:positive, 2:negative, 3:negative | One valid opposed pair |
| pilot-022 | boolean-based blind | inconclusive | 1:positive, 2:negative, 3:positive | Two valid opposed pairs |
| pilot-023 | boolean-based blind | inconclusive | 1:positive, 3:positive | Only trials 1 and 3 |
| pilot-024 | boolean-based blind | inconclusive | 1:negative, 2:negative | Incomplete negative pairs |
| pilot-025 | time-based blind | positive | 1:positive, 2:positive, 3:positive | Exact inclusive threshold with matched controls |
| pilot-026 | time-based blind | positive | 1:positive, 2:positive, 3:positive | Above-threshold matched exists markers |
| pilot-027 | time-based blind | positive | 1:positive, 2:positive, 3:positive | Matched missing markers with valid HTTP 404 |
| pilot-028 | time-based blind | positive | 1:positive, 2:positive, 3:positive | Each trial independently reaches threshold |
| pilot-029 | time-based blind | negative | 1:negative, 2:negative, 3:negative | 1499.8 ms is below 1500 ms without rounding |
| pilot-030 | time-based blind | negative | 1:negative, 2:negative, 3:negative | Slow absolute responses with small matched deltas |
| pilot-031 | time-based blind | negative | 1:negative, 2:negative, 3:negative | Large delay with mismatched control marker |
| pilot-032 | time-based blind | negative | 1:negative, 2:negative, 3:negative | Diagnostic controls and negative signed delta |
| pilot-033 | time-based blind | inconclusive | 1:positive, 2:negative, 3:negative | One qualifying matched delay |
| pilot-034 | time-based blind | inconclusive | 1:positive, 2:negative, 3:positive | Two qualifying delays |
| pilot-035 | time-based blind | inconclusive | 1:positive, 3:positive | Only trials 1 and 3 |
| pilot-036 | time-based blind | inconclusive | 1:negative, 2:negative | Incomplete negative timings |
| pilot-037 | error-based | input_invalid |  | runtime-invalid |
| pilot-038 | error-based | input_invalid |  | baseline-invalid |
| pilot-039 | boolean-based blind | input_invalid |  | runtime-invalid |
| pilot-040 | boolean-based blind | input_invalid |  | baseline-invalid |
| pilot-041 | time-based blind | input_invalid |  | runtime-invalid |
| pilot-042 | time-based blind | input_invalid |  | baseline-invalid |

Perubahan setelah freeze memerlukan versi paket baru dan hash baru sebelum inferensi.
