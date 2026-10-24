"""Enforce the qualification cohort's reserved completion-token ceiling."""

from __future__ import annotations

import json
from pathlib import Path

from qwen_api_runtime import APIRuntimeFailure
from poolside_p3_runtime import CheckpointedPoolsideAPI


MAX_COMPLETION_TOKENS = 1_228_800
MAX_TOKENS_BY_STAGE = {"generation": 1024, "analysis": 2048}


class CompletionBudgetPoolsideAPI(CheckpointedPoolsideAPI):
    """Keep completion reservations within a pinned cap, including after resume."""

    def __init__(self, key: str, directory: Path, *, max_calls: int, max_seconds: int,
                 opener=None, clock=None, max_completion_tokens: int = MAX_COMPLETION_TOKENS):
        kwargs = {"max_calls": max_calls, "max_seconds": max_seconds,
                  "opener": opener}
        if clock is not None:
            kwargs["clock"] = clock
        super().__init__(key, directory, **kwargs)
        if type(max_completion_tokens) is not int or max_completion_tokens <= 0:
            raise ValueError("Completion-token ceiling must be a positive integer.")
        self.max_completion_tokens = max_completion_tokens
        self.completion_tokens_reserved = self._recovered_completion_reservation()
        if self.completion_tokens_reserved > self.max_completion_tokens:
            raise ValueError("Recovered completion-token reservations exceed the cohort ceiling.")

    def _recovered_completion_reservation(self) -> int:
        reserved = 0
        for started in self.directory.glob("attempts/**/request-started.json"):
            request_path = started.parent / "request.json"
            if not request_path.is_file():
                raise ValueError("A started request has no checkpointed request payload.")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            stage = request.get("stage")
            maximum = MAX_TOKENS_BY_STAGE.get(stage)
            payload = request.get("payload")
            if maximum is None or not isinstance(payload, dict) or payload.get("max_tokens") != maximum:
                raise ValueError("A checkpointed request differs from the frozen token profile.")
            usage = None
            result_path = started.parent / "result.json"
            if result_path.is_file():
                record = json.loads(result_path.read_text(encoding="utf-8"))
                usage = (record.get("result") or {}).get("usage")
            completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
            if type(completion) is int and 0 <= completion <= maximum:
                reserved += completion
            else:
                # A sent request with missing usage keeps its full maximum reserved.
                reserved += maximum
        return reserved

    def chat(self, stage: str, messages: list[dict], attempt_directory: Path) -> tuple[dict, dict]:
        maximum = MAX_TOKENS_BY_STAGE.get(stage)
        if maximum is None:
            raise ValueError("Unsupported API stage for the frozen completion budget.")
        if self.completion_tokens_reserved + maximum > self.max_completion_tokens:
            raise APIRuntimeFailure("completion_token_budget_reserved", {
                "completion_tokens_reserved": self.completion_tokens_reserved,
                "max_completion_tokens": self.max_completion_tokens,
                "next_request_reservation": maximum,
            })

        self.completion_tokens_reserved += maximum
        result, checkpoint = super().chat(stage, messages, attempt_directory)
        usage = result.get("usage") if isinstance(result, dict) else None
        completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
        if type(completion) is int and 0 <= completion <= maximum:
            self.completion_tokens_reserved -= maximum - completion
        return result, checkpoint
