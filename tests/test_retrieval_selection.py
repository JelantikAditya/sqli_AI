"""Check selection boundaries and batch audit consistency without network calls."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dvwa"))
from prepare_candidate_batch import validate_batch
from rag_pipeline import load_catalog, scenario_query
from retrieval_selection import load_policy, lexical_candidates, select_chunks, technical_cues


class RetrievalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.policy, _ = load_policy()

    def chunk(self, identifier, text, source="sources/example.pdf", distance=0.2):
        return {"chunk_id": identifier, "text": text, "distance": distance,
                "metadata": {"source_path": source, "page_number": 1}}

    def test_exclusions_override_high_technical_relevance(self):
        text = "Error-based SQL injection uses SQL engine error messages returned in HTTP responses."
        candidates = [self.chunk("refs", text, distance=0.01),
                      self.chunk("proposal", text, self.policy["excluded_source_paths"][0], 0.02),
                      self.chunk("body", text, distance=0.3)]
        curation = {"annotation_sha256": "fixture", "chunks": {
            "refs": {"section": "references"}, "proposal": {"section": "excluded_source"},
            "body": {"section": "body"}}}
        selected, rejected = select_chunks(candidates, "error-based", 5, self.policy, curation)
        self.assertEqual([item["chunk_id"] for item in selected], ["body"])
        self.assertEqual({item["reason"] for item in rejected}, {"references", "excluded_source"})

    def test_duplicates_and_irrelevant_text_do_not_fill_top_k(self):
        text = "Error-based SQL injection parses database error messages from the server HTTP response."
        candidates = [self.chunk("first", text), self.chunk("overlap", text + " Compare a benign baseline."),
                      self.chunk("unrelated", "Astronomy describes stars and planetary orbits."),
                      self.chunk("taxonomy", "Error-based SQL injection is one of several attack categories.")]
        curation = {"annotation_sha256": "fixture", "chunks": {
            item["chunk_id"]: {"section": "body"} for item in candidates}}
        selected, rejected = select_chunks(candidates, "error-based", 5, self.policy, curation)
        self.assertEqual(len(selected), 1)
        self.assertEqual({item["reason"] for item in rejected}, {
            "duplicate_context", "no_technique_evidence", "insufficient_technical_evidence"})

    def test_queries_do_not_encode_level_or_ground_truth_answers(self):
        scenarios = load_catalog()["scenarios"]
        for technique in ("error-based", "boolean-based blind", "time-based blind"):
            queries = {scenario_query(item, mode="focused") for item in scenarios if item["sqli_type"] == technique}
            self.assertEqual(len(queries), 1)

    def test_error_evidence_requires_database_error_phrase(self):
        self.assertFalse(technical_cues("SQL Injections [21]. Error-based attacks are one category.",
                                       "error-based")["primary_evidence"])
        for text in ("Observe the SQL engine’s error messages.", "Parse a database syntax error.",
                     "Error messages returned from the database appear in the response."):
            self.assertTrue(technical_cues(text, "error-based")["primary_evidence"])

    def test_lexical_recovery_finds_technical_text_missing_from_dense_pool(self):
        technical = self.chunk("missed", "Error-based SQL injection observes SQL engine error messages.")
        class Collection:
            def get(self, ids=None, include=None):
                result = {"ids": ["missed"], "documents": [technical["text"]], "metadatas": [technical["metadata"]]}
                if ids is not None:
                    result["embeddings"] = [[1.0, 0.0]]
                return result
        curation = {"annotation_sha256": "fixture", "chunks": {"missed": {"section": "body"}}}
        additions = lexical_candidates(Collection(), [], [1.0, 0.0], "error-based", self.policy, curation)
        self.assertEqual(additions[0]["chunk_id"], "missed")
        self.assertAlmostEqual(additions[0]["distance"], 0.0)
        self.assertEqual(lexical_candidates(Collection(), [technical], [1.0, 0.0], "error-based", self.policy, curation), [])

    def batch(self, mode):
        return {"schema_version": "1.0.0", "scenario_id": "S1", "source": "LLM", "rag_mode": mode,
                "provenance": {"comparison_id": "smoke-pair", "model": "qwen2.5:7b",
                    "prompt_version": "sqli-candidate-v1", "temperature": 0, "seed": 42,
                    "knowledge_base_id": "fixture-kb" if mode == "on" else None,
                    "retrieved_chunk_ids": ["fixture-chunk"] if mode == "on" else [],
                    "retrieval_top_k": 5 if mode == "on" else None,
                    "retrieval_query_version": "sqli-technique-query-v2" if mode == "on" else None,
                    "retrieval_policy_sha256": "a" * 64 if mode == "on" else None,
                    "retrieval_curation_sha256": "b" * 64 if mode == "on" else None},
                "candidates": [{"candidate_id": "fixture", "payload": "benign-test-value"}]}

    def test_batch_preserves_audit_and_rejects_retrieval_state_for_rag_off(self):
        for mode in ("on", "off"):
            batch = self.batch(mode)
            normalized = validate_batch(batch, None)
            self.assertEqual(normalized["candidates"][0]["provenance"], batch["provenance"])
        bad = self.batch("off")
        bad["provenance"]["retrieval_policy_sha256"] = "a" * 64
        with self.assertRaises(ValueError):
            validate_batch(bad, None)
        legacy = copy.deepcopy(self.batch("on"))
        for key in list(legacy["provenance"]):
            if key in ("retrieval_query_version", "retrieval_policy_sha256", "retrieval_curation_sha256"):
                del legacy["provenance"][key]
        validate_batch(legacy, None)


if __name__ == "__main__":
    unittest.main()
