"""Small, auditable HCNSEC chat transport for the Qwen API development path.

The client makes one request per call. It never reads a .env file, retries,
follows redirects, or falls back to a different model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = "https://api.hcnsec.cn/v1/chat/completions"
MODEL = "Qwen3.8-27B"
REPORTED_MODELS = frozenset({MODEL, "self-dploy/Qwen3.8-27B"})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ChatSettings:
    model: str = MODEL
    endpoint: str = ENDPOINT
    temperature: float = 0
    max_tokens: int = 1024
    timeout_seconds: int = 90
    chat_template_kwargs: dict | None = None

    def __post_init__(self):
        # Credentials may only go to the endpoint already verified in this task.
        if self.endpoint != ENDPOINT or self.model != MODEL:
            raise ValueError("Only the verified HCNSEC endpoint and Qwen alias are supported")
        if not 1 <= self.max_tokens <= 4096 or not 1 <= self.timeout_seconds <= 180:
            raise ValueError("Invalid output limit or timeout")
        if not 0 <= self.temperature <= 2:
            raise ValueError("Invalid temperature")
        if self.chat_template_kwargs is not None:
            if (not isinstance(self.chat_template_kwargs, dict)
                    or set(self.chat_template_kwargs) != {"enable_thinking"}
                    or self.chat_template_kwargs["enable_thinking"] is not False):
                raise ValueError("Only the explicit Qwen non-thinking template probe is supported")


def redact(value: str, key: str = "") -> str:
    if key:
        value = value.replace(key, "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)


def request_payload(messages: list[dict], settings: ChatSettings) -> dict:
    if not isinstance(messages, list) or not messages:
        raise ValueError("A nonempty message list is required")
    for message in messages:
        if (not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant"}
                or not isinstance(message.get("content"), str)):
            raise ValueError("Invalid chat message")
    payload = {"model": settings.model, "messages": messages, "temperature": settings.temperature,
               "max_tokens": settings.max_tokens, "stream": False}
    if settings.chat_template_kwargs is not None:
        # Qwen documents this for vLLM serving; generic OpenAI-compatible gateways may reject or ignore it.
        payload["chat_template_kwargs"] = settings.chat_template_kwargs
    return payload


def encoded_payload(payload: dict) -> bytes:
    # Canonical order makes the hash stable after a checkpoint JSON round trip.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode("utf-8")


class QwenAPIClient:
    def __init__(self, api_key: str, *, settings: ChatSettings | None = None, opener=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Missing API key")
        self._key = api_key.strip()
        self.settings = settings or ChatSettings()
        self._opener = opener or build_opener(_NoRedirect())

    def chat(self, messages: list[dict]) -> dict:
        payload = request_payload(messages, self.settings)
        encoded = encoded_payload(payload)
        if self._key.encode("utf-8") in encoded:
            raise ValueError("API key must not appear in model messages")
        result = {"requested_model": self.settings.model,
                  "request_sha256": hashlib.sha256(encoded).hexdigest(),
                  "http_status": None, "reported_model": None, "response_id": None,
                  "finish_reason": None, "content": None, "usage": None,
                  "status": "transport-error", "halt": False}
        request = Request(self.settings.endpoint, data=encoded,
                          headers={"Authorization": "Bearer " + self._key,
                                   "Content-Type": "application/json", "Accept": "application/json"})
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=self.settings.timeout_seconds) as response:
                result["http_status"] = response.status
                body = response.read(1_000_001)
            if len(body) > 1_000_000:
                result.update(status="oversized-response", halt=True)
                return result
            wire = json.loads(body.decode("utf-8", errors="replace"))
            if not isinstance(wire, dict):
                result.update(status="invalid-response-envelope")
                return result
            result["response"] = wire
            result["reported_model"] = wire.get("model")
            result["response_id"] = wire.get("id")
            result["usage"] = wire.get("usage")
            choices = wire.get("choices") or []
            choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            message = choice.get("message") or {}
            result["content"] = message.get("content") if isinstance(message, dict) else None
            result["finish_reason"] = choice.get("finish_reason")
            if result["reported_model"] not in REPORTED_MODELS:
                result.update(status="model-metadata-mismatch", halt=True)
            elif result["finish_reason"] == "length":
                result["status"] = "truncated"
            elif result["finish_reason"] != "stop":
                result["status"] = "unfinished"
            elif not isinstance(result["content"], str) or not result["content"].strip():
                result["status"] = "empty-content"
            else:
                result["status"] = "ok"
        except HTTPError as exc:
            result.update(http_status=exc.code, status="http-error",
                          error_detail=redact(exc.read(8000).decode("utf-8", errors="replace"), self._key)[:1200],
                          halt=300 <= exc.code < 400 or exc.code in (401, 402, 429))
        except (URLError, OSError, TimeoutError, ValueError) as exc:
            result.update(status="transport-error", error_detail=redact(str(exc), self._key)[:800])
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
