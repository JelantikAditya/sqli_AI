"""Check installed LangChain runnables locally, without model/target requests."""

import importlib.metadata
import json
import os
import platform
from unittest.mock import patch


def smoke():
    # Disable inherited external tracing settings in this smoke process only.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    from langchain_core.runnables import RunnableLambda, RunnableSequence
    from langsmith import tracing_context

    stages = []
    attempted_connections = []

    def prepare(value):
        stages.append("prepare")
        return {"value": value + 1}

    def finish(document):
        stages.append("finish")
        return document["value"] * 2

    def block_connection(*args, **kwargs):
        attempted_connections.append(True)
        raise RuntimeError("Network connections are forbidden in this dependency smoke.")

    chain = RunnableLambda(prepare) | RunnableLambda(finish)
    with tracing_context(enabled=False), patch("socket.socket.connect", block_connection), \
            patch("socket.socket.connect_ex", block_connection):
        result = chain.invoke(2, config={"callbacks": [], "max_concurrency": 1})
    if (not isinstance(chain, RunnableSequence) or result != 6
            or stages != ["prepare", "finish"] or attempted_connections):
        raise RuntimeError("Serial runnable smoke failed.")
    return {
        "schema_version": "1.0.0", "scope": "dependency-smoke-not-live-pipeline-integration",
        "python_version": platform.python_version(),
        "langchain_core_version": importlib.metadata.version("langchain-core"),
        "runnable_class": type(chain).__name__, "input": 2, "output": result,
        "stages": stages, "serial_smoke_passed": True, "external_tracing_enabled": False,
        "network_connection_attempts": len(attempted_connections),
        "model_inference_calls": 0, "dvwa_requests_sent": 0,
        "local_pipeline_integration": "pending",
    }


if __name__ == "__main__":
    print(json.dumps(smoke()))
