"""Small local-only helpers for serial LangChain Core pipelines."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from importlib.metadata import version
from typing import Any

from langchain_core.runnables import RunnableLambda, RunnableSequence
from langsmith import tracing_context


def orchestration_metadata() -> dict:
    return {"framework": "langchain-core", "version": version("langchain-core"),
            "chain_type": "RunnableSequence", "max_concurrency": 1,
            "external_tracing": False}


def invoke_serial(stages: Sequence[Callable[[Any], Any]], value: Any) -> Any:
    """Run explicit pipeline stages serially with tracing disabled."""
    if len(stages) < 2 or any(not callable(stage) for stage in stages):
        raise ValueError("A local LLM pipeline needs at least two callable stages.")
    chain = RunnableSequence(*(RunnableLambda(stage) for stage in stages))
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    with tracing_context(enabled=False):
        return chain.invoke(value, config={"max_concurrency": 1})
