"""Check recorded local LangChain readiness and its formal freeze gate."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from experiment_protocol import experiment_matrix, load_protocol, snapshot


class LocalMethodologyTests(unittest.TestCase):
    def check_rejected(self, protocol, pattern):
        with tempfile.TemporaryDirectory(dir=ROOT / "results/raw") as temporary:
            path = Path(temporary) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, pattern):
                load_protocol(path)

    def test_formal_protocol_records_verified_local_langchain_integration(self):
        protocol = load_protocol()
        self.assertEqual(protocol["implementation_readiness"]["local_langchain"], "verified")
        self.assertEqual(len(experiment_matrix(protocol)), 99)
        self.assertIn("local-langchain-integration-verified", protocol["formal_gate"])

    def test_retrieval_and_timing_policy_drift_is_rejected(self):
        changes = {"rag_off_vectorstore_access": "allowed",
                   "analysis_retrieval": "enabled-in-rag-on",
                   "inference_http_timing": "parallel",
                   "llm_pipeline_framework": "colab-only",
                   "external_tracing": "enabled"}
        for key, value in changes.items():
            with self.subTest(key=key):
                protocol = load_protocol()
                protocol["methodology"][key] = value
                self.check_rejected(protocol, "recorded local methodology")

    def test_formal_freeze_rejects_pending_framework_even_if_reviews_are_approved(self):
        protocol = load_protocol()
        protocol["status"] = "frozen"
        protocol["review"]["independent_validator"] = "approved"
        protocol["implementation_readiness"]["local_langchain"] = "pending"
        self.check_rejected(protocol, "verified local LangChain integration")

    def test_gate_cannot_be_removed_and_snapshot_tracks_framework_packages(self):
        protocol = load_protocol()
        protocol["formal_gate"].remove("local-langchain-integration-verified")
        self.check_rejected(protocol, "formal integration gate")
        from experiment_protocol import DEFAULT_PROTOCOL
        manifest = snapshot(load_protocol(), DEFAULT_PROTOCOL)
        for package in ("langchain-core", "langchain-ollama", "langchain-chroma"):
            self.assertIn(package, manifest["packages"])


if __name__ == "__main__":
    unittest.main()
