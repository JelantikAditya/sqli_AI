# Catatan insiden attempt pilot B, 21 Oktober 2026

Attempt pertama untuk S1 Low menerima satu respons generation API, lalu berstatus invalid dengan `ValueError: An adaptive candidate must be an object.` Adapter generation mengembalikan payload S1 sebagai string, sementara `observe_candidate` memerlukan objek `{"payload": ...}`. Exception terjadi sebelum `execute_candidate`, sehingga tidak ada payload kandidat yang dikirim sebagai probe SQLi ke DVWA.

Ledger tetap append-only dan tidak diubah. Baris `attempt_invalid` menyimpan `database_reset_performed: false` dan `http_request_calls: null` karena jalur exception generik mengisi nilai default. Kode mengeksekusi reset database, login, verifikasi level, dan baseline sebelum membuat request generation API. Karena artefak respons generation tersimpan, penyelesaian tahapan tersebut tersirat, tetapi reset receipt dan jumlah request DVWA tidak tercatat di ledger.

Perbaikan membungkus string S1 menjadi objek kandidat sebelum observasi dan mempertahankan fakta reset serta jumlah request bila exception orkestrasi terjadi. Pemeriksaan offline ada di `development/test_qwen_api_experiment_adapter.py`. Plan pemulihan memakai ID eksperimen baru dan snapshot knowledge yang sama, lalu akan divalidasi dengan dry-run.

Saat memeriksa helper untuk input key, ditemukan credential literal tersimpan pada teks prompt helper dan nilainya muncul dalam keluaran tool. Helper telah ditulis ulang dengan prompt input tersembunyi generik. Key tersebut harus dicabut dan diganti sebelum request API berikutnya. Nilai credential tidak dicantumkan dalam catatan ini.

Plan pemulihan `development/qwen_api_b_pilot_recovery_20261021.template.json` lolos dry-run dengan estimasi maksimum 40 request tambahan. Attempt pertama memakai satu request, jadi maksimum total untuk dua attempt adalah 41. Delapan belas tes offline lulus; dry-run tidak memulai eksekusi. Helper pemulihan yang sudah dibersihkan ada di `tmp/qwen_api_b_secure_recovery.ps1` dan menunggu key pengganti.

Recovery selesai dengan 20 request API, sepuluh kandidat valid, dan status run lengkap. Rincian hasil, batas penggunaan, serta hash bukti tercantum di `docs/evidence/qwen-api-b-pilot-run-receipt-2026-10-21.json`. Rotasi key belum dapat diverifikasi dari runner karena nilai credential tidak disimpan.
