"""Checkpointed, single-request Qwen API calls for the development pilot runner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from qwen_api_client import ChatSettings, QwenAPIClient, request_payload


class APIRuntimeFailure(RuntimeError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _redact_tree(value, api_key: str):
    if isinstance(value, str):
        if api_key:
            value = value.replace(api_key, "[REDACTED]")
        return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    if isinstance(value, list):
        return [_redact_tree(item, api_key) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_tree(item, api_key) for key, item in value.items()}
    return value


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    with temporary.open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(payload)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)


class CheckpointedQwenAPI:
    """Make one API request per call and checkpoint before contacting the gateway."""

    def __init__(self, api_key: str, experiment_directory: Path, config: dict):
        self.api_key = api_key.strip()
        self.experiment_directory = experiment_directory.resolve()
        self.max_total_calls = config["limits"]["max_total_api_calls"]
        self.settings = {
            stage: ChatSettings(
                model=config["model"], endpoint=config["endpoint"], temperature=config["temperature"],
                max_tokens=config["token_limits"][stage], timeout_seconds=config["timeout_seconds"],
                chat_template_kwargs={"enable_thinking": False},
            )
            for stage in ("generation", "analysis")
        }
        self.client = {stage: QwenAPIClient(self.api_key, settings=settings)
                       for stage, settings in self.settings.items()}
        self.used_calls = self.count_started_calls(self.experiment_directory)
        if self.used_calls > self.max_total_calls:
            raise APIRuntimeFailure("api_call_ceiling_already_exceeded", {
                "used_calls": self.used_calls, "max_total_api_calls": self.max_total_calls})

    @staticmethod
    def count_started_calls(experiment_directory: Path) -> int:
        attempts = experiment_directory / "attempts"
        if not attempts.is_dir():
            return 0
        return sum(1 for path in attempts.rglob("request-started.json") if path.is_file())

    def chat(self, stage: str, messages: list[dict], attempt_directory: Path) -> tuple[dict, dict]:
        if stage not in self.settings:
            raise ValueError("API stage must be generation or analysis.")
        if self.used_calls >= self.max_total_calls:
            raise APIRuntimeFailure("api_call_ceiling_reached", {
                "used_calls": self.used_calls, "max_total_api_calls": self.max_total_calls})

        payload = request_payload(messages, self.settings[stage])
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                             sort_keys=True, allow_nan=False).encode("utf-8")
        if self.api_key.encode("utf-8") in encoded:
            raise ValueError("API key must not appear in model messages.")
        request_sha256 = hashlib.sha256(encoded).hexdigest()
        calls_directory = attempt_directory / "api-calls"
        calls_directory.mkdir(parents=True, exist_ok=True)
        call_id = f"{self.used_calls + 1:05d}-{stage}-{uuid4().hex[:8]}"
        call_directory = calls_directory / call_id
        call_directory.mkdir(exist_ok=False)
        relative_directory = call_directory.relative_to(self.experiment_directory).as_posix()

        safe_payload = _redact_tree(payload, self.api_key)
        _write_json(call_directory / "request.json", {
            "schema_version": "1.0.0", "call_id": call_id, "stage": stage,
            "requested_model": self.settings[stage].model,
            "request_sha256": request_sha256, "payload": safe_payload,
        })
        _write_json(call_directory / "request-started.json", {
            "schema_version": "1.0.0", "call_id": call_id, "stage": stage,
            "request_sha256": request_sha256,
        })
        self.used_calls += 1

        try:
            raw_result = self.client[stage].chat(messages)
        except Exception as failure:
            safe_failure = _redact_tree(str(failure), self.api_key)[:800]
            _write_json(call_directory / "result.json", {
                "schema_version": "1.0.0", "call_id": call_id,
                "status": "client-exception", "error": safe_failure,
            })
            raise APIRuntimeFailure("api_client_exception", {
                "call_id": call_id, "checkpoint_directory": relative_directory,
                "request_sha256": request_sha256,
            }) from failure

        result = _redact_tree(raw_result, self.api_key)
        _write_json(call_directory / "result.json", {
            "schema_version": "1.0.0", "call_id": call_id, "result": result,
        })
        receipt = {"call_id": call_id, "request_sha256": request_sha256,
                   "checkpoint_directory": relative_directory}
        if result.get("status") != "ok":
            status = str(result.get("status") or "unknown")
            raise APIRuntimeFailure("api_" + status.replace("-", "_"), {
                **receipt, "api_status": status,
                "http_status": result.get("http_status"), "halt": bool(result.get("halt")),
            })
        return result, receipt
