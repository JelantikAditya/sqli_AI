"""Checkpointed Poolside transport for a new bounded P3 pilot cohort."""

from __future__ import annotations

from pathlib import Path
import time
from uuid import uuid4

from qwen_api_runtime import APIRuntimeFailure
import run_poolside_contract_smoke as contract
import run_poolside_smoke as transport
from run_poolside_generation_preflight import write_new


class CheckpointedPoolsideAPI:
    def __init__(self, key: str, directory: Path, *, max_calls: int, max_seconds: int,
                 opener=None, clock=time.monotonic):
        self._key = transport.validate_key(key)
        self.directory = directory.resolve()
        self.max_total_calls = max_calls
        self.clock = clock
        self.deadline = clock() + max_seconds
        self.opener = opener if opener is not None else transport.build_opener(transport.NoRedirect())
        self.used_calls = sum(1 for _ in self.directory.glob("attempts/**/request-started.json"))

    def require_time(self, stage=None):
        reserve = 60 if stage is not None else 0
        if self.clock() + reserve >= self.deadline:
            raise APIRuntimeFailure("pilot_time_budget_exceeded", {"used_calls": self.used_calls})

    @staticmethod
    def payload(stage: str, messages: list[dict]) -> dict:
        if stage not in {"generation", "analysis"}:
            raise ValueError("Unsupported API stage.")
        return {"model": transport.MODEL, "messages": messages, "temperature": 0,
                "max_tokens": 1024 if stage == "generation" else 2048, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}

    def chat(self, stage: str, messages: list[dict], attempt_directory: Path) -> tuple[dict, dict]:
        self.require_time(stage)
        if self.used_calls >= self.max_total_calls:
            raise APIRuntimeFailure("api_call_ceiling_reached", {"used_calls": self.used_calls})
        attempt_directory = attempt_directory.resolve()
        if not attempt_directory.is_relative_to(self.directory / "attempts"):
            raise ValueError("Checkpoint must stay under this experiment's attempts directory.")
        payload = self.payload(stage, messages)
        import json
        if self._key in json.dumps(payload):
            raise ValueError("API key must not appear in model messages.")
        request_hash = contract.request_hash(payload)
        call_id = f"{self.used_calls + 1:05d}-{stage}-{uuid4().hex[:8]}"
        destination = attempt_directory / "api-calls" / call_id
        destination.mkdir(parents=True, exist_ok=False)
        write_new(destination / "request.json", {"stage": stage, "payload": payload,
                                                 "request_sha256": request_hash})
        write_new(destination / "request-started.json", {"call_id": call_id, "request_sha256": request_hash})
        self.used_calls += 1
        receipt = {"call_id": call_id, "request_sha256": request_hash,
                   "checkpoint_directory": destination.relative_to(self.directory).as_posix()}
        try:
            response = transport.request_once(self.opener, self._key, "/chat/completions", payload)
            result = {**contract.api_result(response), "request_sha256": response.get("request_sha256")}
            if result["request_sha256"] != request_hash:
                result.update(status="request-hash-mismatch", halt=True)
            write_new(destination / "result.json", transport.redact({"result": result, "transport": response}, self._key))
        except Exception as failure:
            write_new(destination / "client-exception.json", {"exception_type": type(failure).__name__})
            raise APIRuntimeFailure("api_client_exception", receipt) from failure
        if result["status"] != "ok":
            raise APIRuntimeFailure("api_" + result["status"].replace("-", "_"), {
                **receipt, "api_status": result["status"], "http_status": result["http_status"]})
        return result, receipt
