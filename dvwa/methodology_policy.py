"""T01 design contract; implementing the LangChain adapter belongs to T02/T05."""

LOCAL_METHODOLOGY = {
    "decision_id": "local-laptop-langchain-v1",
    "execution_topology": "single-laptop-local-services-and-docker",
    "experiment_controller": "custom-python",
    "llm_pipeline_framework": "langchain-core-serial-runnables",
    "model_transport": "local-ollama-http",
    "knowledge_store": "persistent-local-chroma",
    "retrieval_adapter": "existing-proposal-structured-retrieval",
    "retrieval_frequency": "once-before-each-rag-on-condition-run",
    "rag_usage": "generation-and-feedback-conditioned-regeneration-only",
    "analysis_retrieval": "disabled-in-both-llm-conditions",
    "rag_off_vectorstore_access": "forbidden",
    "executor": "custom-dvwa-http",
    "inference_http_timing": "serial-nonoverlapping",
    "evidence_storage": "local-disk-separated-pilot-and-formal",
    "external_tracing": "disabled",
    "colab_and_tunnel": "deferred-outside-active-experiments",
}
