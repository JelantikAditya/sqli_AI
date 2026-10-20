"""Bounded general API check: three aliases, three identical tasks, no retries."""

from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


MODELS = ["Qwen3.8-27B", "glm-5.3-flash", "MiMo-V2.6-Flash"]
TASKS = [
    {
        "id": "extract_json",
        "prompt": (
            'Ekstrak catatan berikut. Balas hanya satu objek JSON valid tanpa Markdown '
            'dengan tepat tiga kunci: nama (string), jumlah (integer), kota (string atau null). '
            'Jangan menebak informasi yang tidak tercantum. '
            'Catatan: Nama pelanggan Rani. Pesanan 3 buku. Kota tidak dicantumkan.'
        ),
        "expected": {"nama": "Rani", "jumlah": 3, "kota": None},
    },
    {
        "id": "arithmetic",
        "prompt": (
            'Sebuah toko memiliki 48 kotak, setiap kotak berisi 24 pensil. '
            'Toko menjual 275 pensil lalu menerima tambahan 7 kotak dengan isi yang sama. '
            'Berapa pensil yang tersedia sekarang? Balas hanya objek JSON valid '
            'dengan tepat satu kunci "pensil" bernilai integer, tanpa penjelasan atau Markdown.'
        ),
        "expected": {"pensil": 1045},
    },
    {
        "id": "python_trace",
        "prompt": (
            'Tentukan isi akhir variabel out setelah kode Python berikut dijalankan. '
            'Balas hanya objek JSON valid dengan tepat satu kunci "out" berisi array integer, '
            'tanpa penjelasan atau Markdown.\n\n'
            'values = [2, 5, 2, 7, 5]\n'
            'seen = set()\n'
            'out = []\n'
            'for i, x in enumerate(values):\n'
            '    if x in seen:\n'
            '        out.append(x - i)\n'
            '    else:\n'
            '        seen.add(x)\n'
            '        out.append(x + i)\n'
        ),
        "expected": {"out": [2, 6, 0, 10, 1]},
    },
]
URL = "https://api.hcnsec.cn/v1/chat/completions"
LIMIT = 1024
TIMEOUT = 90


def strict_equal(actual, expected):
    # Reject bools and floats where the task requires an integer.
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            strict_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            strict_equal(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


def score(content, finish_reason):
    if not isinstance(content, str) or not content.strip():
        return {"valid_json": False, "passed": False, "verdict": "empty-content"}
    try:
        parsed = json.loads(content)
    except ValueError:
        return {"valid_json": False, "passed": False, "verdict": "invalid-json"}
    return {"valid_json": True, "parsed": parsed, "truncated": finish_reason == "length"}


secret = (getpass.getpass("API key: ") if sys.stdin.isatty() else sys.stdin.readline()).strip()
if not secret:
    print(json.dumps({"status": "missing-api-key"}), flush=True)
    raise SystemExit(2)


def redact(value):
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value.replace(secret, "[REDACTED]"))


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(redact(json.dumps(value, ensure_ascii=False, indent=2)) + "\n")


root = next(parent for parent in Path(__file__).resolve().parents if (parent / "AGENTS.md").is_file())
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
out = root / "outputs" / ("hcnsec-general-model-check-" + stamp)
out.mkdir(parents=True, exist_ok=False)
# Freeze every prompt, reference answer, and request before the first inference.
plan = []
for task_index, task in enumerate(TASKS):
    for model in MODELS[task_index:] + MODELS[:task_index]:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": task["prompt"]}],
            "temperature": 0,
            "max_tokens": LIMIT,
            "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        plan.append({
            "sequence": len(plan) + 1,
            "task_id": task["id"],
            "requested_model": model,
            "payload": payload,
            "expected": task["expected"],
            "request_sha256": hashlib.sha256(data).hexdigest(),
        })
save(out / "plan.json", plan)
save(out / "manifest.json", {
    "purpose": "small-general-api-check-independent-of-TA",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "endpoint": URL,
    "maximum_requests": len(plan),
    "maximum_completion_tokens_per_request": LIMIT,
    "timeout_seconds": TIMEOUT,
    "retries": 0,
    "credentials_saved": False,
    "scoring": "Exact JSON keys, values and types; no surrounding Markdown; nonempty final content; finish_reason stop required.",
    "order": "Task blocks with rotated model order; sequential calls.",
    "limitations": [
        "Three easy synthetic tasks per alias, one sample each; not a general capability ranking.",
        "Elapsed time includes network and gateway queue; this is not tokens per second.",
        "Reported model metadata does not independently verify upstream weights.",
        "Same token budget can affect models with different reasoning behavior.",
    ],
})
with (out / "run_check.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(Path(__file__).read_text(encoding="utf-8"))

results = []
stop_reason = None
opener = build_opener(NoRedirect())
print(json.dumps({"status": "plan-frozen", "requests": len(plan), "output_dir": str(out)}), flush=True)
for item in plan:
    case_dir = out / (str(item["sequence"]).zfill(2) + "-" + item["task_id"])
    case_dir.mkdir()
    save(case_dir / "request.json", item["payload"])
    report = {
        "sequence": item["sequence"],
        "task_id": item["task_id"],
        "requested_model": item["requested_model"],
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "reported_model": None,
        "valid_json": False,
        "passed": False,
    }
    save(case_dir / "attempt-started.json", report)
    print(json.dumps({"status": "request-started", "sequence": item["sequence"],
                      "model": item["requested_model"], "task": item["task_id"]}), flush=True)
    started = time.monotonic()
    request = Request(URL, data=json.dumps(item["payload"], ensure_ascii=False).encode("utf-8"),
                      headers={"Authorization": "Bearer " + secret,
                               "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            report["http_status"] = response.status
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError("response exceeded one megabyte")
        decoded = body.decode("utf-8", errors="replace")
        with (case_dir / "response.txt").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(redact(decoded))
        result = json.loads(decoded)
        save(case_dir / "response.json", result)
        if not isinstance(result, dict):
            raise ValueError("response is not an object")
        choices = result.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        finish = choice.get("finish_reason")
        grade = score(content, finish)
        if grade["valid_json"]:
            correct = strict_equal(grade["parsed"], item["expected"])
            grade.update(answer_correct=correct, passed=correct and finish == "stop",
                         verdict="pass" if correct and finish == "stop" else
                         "unfinished-response" if correct else "wrong-answer-or-schema")
        report.update(status="response-received", reported_model=result.get("model"),
                      response_id=result.get("id"), content=content,
                      finish_reason=finish, usage=result.get("usage"), **grade)
    except HTTPError as exc:
        error_body = redact(exc.read(8000).decode("utf-8", errors="replace"))
        save(case_dir / "error.json", {"http_status": exc.code, "response": error_body})
        report.update(status="http-error", http_status=exc.code,
                      verdict="http-error", detail=error_body[:1200])
        if exc.code in (401, 402, 429):
            stop_reason = "Stopped without retry after HTTP " + str(exc.code)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        report.update(status="connection-or-response-error", verdict="connection-or-response-error",
                      detail=redact(str(exc)[:800]))
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    save(case_dir / "summary.json", report)
    results.append(report)
    print(redact(json.dumps({key: report.get(key) for key in
          ("sequence", "requested_model", "reported_model", "task_id", "http_status",
           "verdict", "elapsed_seconds", "finish_reason", "content")}, ensure_ascii=True)), flush=True)
    if stop_reason:
        break

models = []
for model in MODELS:
    rows = [r for r in results if r["requested_model"] == model]
    received = [r for r in rows if r["status"] == "response-received"]
    models.append({
        "requested_model": model,
        "tasks_planned": len(TASKS),
        "requests_attempted": len(rows),
        "responses_received": len(received),
        "tasks_passed": sum(r["passed"] for r in rows),
        "valid_json": sum(r["valid_json"] for r in rows),
        "reported_models": sorted({r["reported_model"] for r in rows if isinstance(r["reported_model"], str)}),
        "mean_elapsed_seconds_received": round(statistics.mean(r["elapsed_seconds"] for r in received), 3) if received else None,
        "median_elapsed_seconds_received": round(statistics.median(r["elapsed_seconds"] for r in received), 3) if received else None,
        "tokens_reported": sum(r["usage"].get("total_tokens", 0) for r in received if isinstance(r.get("usage"), dict)),
    })
summary = {"scope": "small-general-api-check-independent-of-TA",
           "upstream_weights_independently_verified": False,
           "stop_reason": stop_reason, "requests_attempted": len(results),
           "requests_not_attempted": len(plan) - len(results),
           "models": models, "results": results}
save(out / "summary.json", summary)
print(redact(json.dumps({"status": "complete", "models": models,
                         "stop_reason": stop_reason, "summary_path": str(out / "summary.json")}, ensure_ascii=True)), flush=True)
