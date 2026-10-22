"""Bounded AISUBS Luna connectivity check, separate from SQLi experiments.

Use --dry-run without credentials, or --run for one model-list request and at
most one chat request. Credentials stay in the environment or ignored local
file. There are no retries, redirects, model substitutions, or DVWA requests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import warnings


ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / ".env.aisubs.local"
ENV_NAME = "AISUBS_API_KEY"
BASE_URL = "https://api.aisubs.id/v1"
MODEL = "gpt-6-luna"
MAX_BODY_BYTES = 1_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An Authorization header must never follow a gateway redirect.
        return None


def load_key(prompt: bool = False) -> str:
    value = os.environ.get(ENV_NAME, "").strip()
    if not value and KEY_PATH.exists():
        lines = [line.strip() for line in KEY_PATH.read_text(encoding="utf-8-sig").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        if len(lines) != 1 or not lines[0].startswith(ENV_NAME + "="):
            raise ValueError("Invalid credential file; expected one AISUBS_API_KEY entry.")
        value = lines[0].partition("=")[2].strip()
    if not value and prompt:
        with warnings.catch_warnings():
            # Abort if the terminal cannot provide hidden input.
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(ENV_NAME + " (hidden): ").strip()
    if value and (not value.isascii() or any(c.isspace() or not c.isprintable() for c in value)):
        raise ValueError("Invalid credential format.")
    return value


def chat_payload() -> dict:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Balas tepat API_OK tanpa teks tambahan."}],
        "reasoning_effort": "none",
        "max_completion_tokens": 128,
        "stream": False,
    }


def redact(value: object, key: str) -> object:
    # Sanitize success bodies as well as errors in case the gateway echoes a key.
    encoded = json.dumps(value, ensure_ascii=True)
    if key:
        encoded = encoded.replace(json.dumps(key)[1:-1], "[REDACTED]")
    encoded = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", encoded)
    return json.loads(encoded)


def request_once(opener, key: str, resource: str, payload: dict | None = None) -> dict:
    if resource not in {"/models", "/chat/completions"}:
        raise ValueError("Unsupported resource.")
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
               if payload is not None else None)
    request = Request(BASE_URL + resource, data=encoded, headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json", "Content-Type": "application/json",
    })
    result = {"resource": resource, "method": request.get_method(), "status": "transport-error",
              "http_status": None, "body": None}
    if encoded is not None:
        result["request_sha256"] = hashlib.sha256(encoded).hexdigest()
    started = time.monotonic()
    try:
        with opener.open(request, timeout=20 if payload is None else 60) as response:
            result["http_status"] = response.status
            body = response.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            result["status"] = "oversized-response"
        else:
            try:
                result["body"] = json.loads(body)
                result["status"] = "ok" if result["http_status"] == 200 else "http-error"
            except (ValueError, UnicodeError):
                result["status"] = "invalid-json"
    except HTTPError as exc:
        result.update(status="http-error", http_status=exc.code,
                      error_detail=exc.read(4000).decode("utf-8", errors="replace"))
        exc.close()
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        # The exception class suffices for transport diagnosis without dumping headers.
        result["error_type"] = type(exc).__name__
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return redact(result, key)


def run_smoke(key: str, opener=None) -> dict:
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "connectivity-only; not SQLi, FPR, or PSR evaluation",
              "base_url": BASE_URL, "requested_model": MODEL,
              "automatic_retries": 0, "model_fallback": False,
              "request_payload": chat_payload(), "requests": [], "status": "missing-api-key"}
    if not key:
        return report
    opener = opener if opener is not None else build_opener(NoRedirect())
    models = request_once(opener, key, "/models")
    report["requests"].append(models)
    if models["status"] != "ok":
        report["status"] = "model-list-request-failed"
        return report
    body = models["body"]
    entries = body.get("data") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        report["status"] = "invalid-model-list"
        return report
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    report["luna_listed"] = MODEL in ids
    if not report["luna_listed"]:
        report["status"] = "luna-not-listed"
        return report
    # The only generative call is this short smoke prompt, with a fixed budget.
    chat = request_once(opener, key, "/chat/completions", chat_payload())
    report["requests"].append(chat)
    if chat["status"] != "ok" or not isinstance(chat["body"], dict):
        report["status"] = "chat-request-failed"
        return report
    wire = chat["body"]
    choices = wire.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    report.update(reported_model=wire.get("model"), content=content,
                  usage=wire.get("usage"), finish_reason=choice.get("finish_reason"))
    if report["reported_model"] != MODEL:
        report["status"] = "model-metadata-mismatch"
    elif report["finish_reason"] != "stop":
        report["status"] = "unfinished-response"
    elif not isinstance(content, str) or content.strip() != "API_OK":
        report["status"] = "unexpected-content"
    else:
        report["status"] = "ok"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print plan without reading keys or using network")
    mode.add_argument("--check-key", action="store_true", help="Check credentials without printing them or using network")
    mode.add_argument("--run", action="store_true", help="Execute at most two API requests")
    parser.add_argument("--prompt-key", action="store_true", help="Ask for a key using hidden terminal input")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"status": "ready-dry-run", "base_url": BASE_URL,
                          "payload": chat_payload(), "max_http_requests": 2,
                          "max_chat_requests": 1, "automatic_retries": 0,
                          "model_fallback": False, "execution_started": False}, indent=2))
        return 0
    try:
        key = load_key(prompt=args.prompt_key)
    except (OSError, UnicodeError, ValueError, EOFError, getpass.GetPassWarning):
        print(json.dumps({"status": "credential-input-error", "requests_sent": 0}))
        return 2
    if args.check_key or not key:
        print(json.dumps({"status": "key-configured" if key else "missing-api-key", "requests_sent": 0}))
        return 0 if key else 2
    report = run_smoke(key)
    destination = ROOT / "results" / "raw" / "aisubs-luna-smoke"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(redact(report, key), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "requests_sent": len(report["requests"]),
                      "reported_model": report.get("reported_model"),
                      "usage": report.get("usage"), "report_path": str(path)}, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
