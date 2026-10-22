"""Save a local Poolside key or run a bounded hosted-API connectivity check.

Uses only the Python standard library. --dry-run and --check-key do not use
the network. --run makes one model-list request and at most one chat request.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import warnings


ROOT = Path(__file__).resolve().parents[1]
ENV_NAME = "POOLSIDE_API_KEY"
KEY_PATH = ROOT / ".env.poolside.local"
BASE_URL = "https://inference.poolside.ai/v1"
MODEL = "poolside/laguna-s-2.1"
MAX_BODY_BYTES = 1_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected endpoint.
        return None


def validate_key(value: str) -> str:
    key = value.strip()
    if not key or not key.isascii() or any(c.isspace() or not c.isprintable() for c in key):
        raise ValueError("Invalid credential format.")
    return key


def load_key(path: Path = KEY_PATH) -> str:
    value = os.environ.get(ENV_NAME, "").strip()
    if value:
        return validate_key(value)
    if not path.exists():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1 or not lines[0].startswith(ENV_NAME + "="):
        raise ValueError("Invalid credential file; use --save-key again.")
    return validate_key(lines[0].partition("=")[2])


def save_key(path: Path = KEY_PATH) -> None:
    with warnings.catch_warnings():
        # Abort if the terminal cannot hide input instead of echoing a secret.
        warnings.simplefilter("error", getpass.GetPassWarning)
        key = validate_key(getpass.getpass(ENV_NAME + " (hidden input): "))
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.poolside.local.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(ENV_NAME + "=" + key + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def chat_payload() -> dict:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly API_OK and nothing else."}],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def redact(value: object, key: str) -> object:
    # Sanitize both success and failure bodies if the server echoes the key.
    encoded = json.dumps(value, ensure_ascii=True)
    return json.loads(encoded.replace(json.dumps(key)[1:-1], "[REDACTED]")) if key else value


def request_once(opener, key: str, resource: str, payload: dict | None = None) -> dict:
    if resource not in {"/models", "/chat/completions"}:
        raise ValueError("Unsupported resource.")
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8") if payload is not None else None
    request = Request(BASE_URL + resource, data=encoded, headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json", "Content-Type": "application/json",
    })
    result = {"resource": resource, "status": "transport-error", "http_status": None}
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
            result["body"] = json.loads(body)
            result["status"] = "ok" if result["http_status"] == 200 else "http-error"
    except HTTPError as exc:
        result.update(status="http-error", http_status=exc.code,
                      error_detail=exc.read(4000).decode("utf-8", errors="replace"))
        exc.close()
    except (URLError, OSError, TimeoutError) as exc:
        result["error_type"] = type(exc).__name__
    except (ValueError, UnicodeError):
        result["status"] = "invalid-response"
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return redact(result, key)


def run_smoke(key: str, opener=None) -> dict:
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "connectivity-only; not P2, P3, FPR, or PSR evaluation",
              "base_url": BASE_URL, "requested_model": MODEL,
              "request_payload": chat_payload(), "requests": [],
              "automatic_retries": 0, "model_fallback": False, "status": "missing-api-key"}
    if not key:
        return report
    key = validate_key(key)
    opener = opener if opener is not None else build_opener(NoRedirect())
    models = request_once(opener, key, "/models")
    report["requests"].append(models)
    if models["status"] != "ok":
        report["status"] = "model-list-request-failed"
        return report
    body = models.get("body")
    entries = body.get("data") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        report["status"] = "invalid-model-list"
        return report
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    report["model_listed"] = MODEL in ids
    if not report["model_listed"]:
        report["status"] = "model-not-listed"
        return report
    chat = request_once(opener, key, "/chat/completions", chat_payload())
    report["requests"].append(chat)
    wire = chat.get("body")
    if chat["status"] != "ok" or not isinstance(wire, dict):
        report["status"] = "chat-request-failed"
        return report
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
    mode.add_argument("--save-key", action="store_true", help="Save key locally using hidden terminal input")
    mode.add_argument("--check-key", action="store_true", help="Check key availability without network access")
    mode.add_argument("--dry-run", action="store_true", help="Inspect plan without reading keys or using network")
    mode.add_argument("--run", action="store_true", help="Send at most two requests to the direct Poolside API")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"status": "ready-dry-run", "base_url": BASE_URL,
                          "payload": chat_payload(), "max_http_requests": 2,
                          "max_chat_requests": 1, "automatic_retries": 0,
                          "model_fallback": False, "execution_started": False}, indent=2))
        return 0
    try:
        if args.save_key:
            save_key()
            print("API key saved locally. No API request was sent.")
            if os.environ.get(ENV_NAME, "").strip():
                print("The environment value takes precedence over the saved key.")
            return 0
        key = load_key()
    except (OSError, UnicodeError, ValueError, EOFError, getpass.GetPassWarning):
        print(json.dumps({"status": "credential-input-error", "requests_sent": 0}))
        return 2
    if args.check_key or not key:
        print(json.dumps({"status": "key-configured" if key else "missing-api-key", "requests_sent": 0}))
        return 0 if key else 2
    report = redact(run_smoke(key), key)
    destination = ROOT / "results" / "raw" / "poolside-smoke"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"status": report["status"], "requests_sent": len(report["requests"]),
                      "http_statuses": [item["http_status"] for item in report["requests"]],
                      "latencies_seconds": [item["elapsed_seconds"] for item in report["requests"]],
                      "reported_model": report.get("reported_model"), "content": report.get("content"),
                      "usage": report.get("usage"), "report_path": str(path)}, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
