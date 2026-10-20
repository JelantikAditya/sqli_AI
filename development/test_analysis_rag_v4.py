"""Offline checks for matched A/B prompts, label-free retrieval and raw-claim preservation."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analysis_rag_v4 as rag
import pilot_analysis_rag_v4 as pilot
from test_prerequisites import require_local_snapshots


class AnalysisRagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_snapshots("knowledge/sources.lock.json")
        cls.cases, cls.labels = pilot.new_cases()
        cls.corpus = rag.project_corpus()

    def receipt(self, document):
        chunks = [copy.deepcopy(c) for c in self.corpus["chunks"] if c["technique"] == document["technique"]][:2]
        return {"query": rag.query_for(document), "policy": copy.deepcopy(rag.POLICY),
                "candidate_pool": [], "chunks": chunks}

    def test_projection_has_only_locked_analysis_fields_and_source_refs(self):
        self.assertEqual(len(self.corpus["chunks"]), 9)
        for chunk in self.corpus["chunks"]:
            text = json.loads(chunk["text"])
            self.assertEqual(set(text), {"title", "vulnerability_type", "functional_semantics", "detection_method", "limitations"})
            self.assertNotIn("DVWA", chunk["text"])
            self.assertEqual(len(chunk["text_sha256"]), 64)
            self.assertTrue(all(ref["commit"] and ref["source_sha256"] and ref["url"] for ref in chunk["source_refs"]))

    def test_queries_are_independent_of_measurement_values_and_validity(self):
        for case in self.cases:
            changed = copy.deepcopy(case["input"])
            changed["observations"][0]["elapsed_ms"] += 98765
            changed["baseline_valid"] = not changed["baseline_valid"]
            self.assertEqual(rag.query_for(case["input"]), rag.query_for(changed))
            self.assertEqual(set(json.loads(rag.query_for(case["input"]))), {"technique", "injection_point", "task"})

    def test_A_B_differ_only_in_reference_context(self):
        for case in self.cases:
            a = rag.prepared_request(case["input"], "A")
            b = rag.prepared_request(case["input"], "B", self.receipt(case["input"]))
            self.assertEqual(a["request"]["messages"][0], b["request"]["messages"][0])
            for key in ("model", "format", "options", "stream"):
                self.assertEqual(a["request"][key], b["request"][key])
            av, bv = (json.loads(p["request"]["messages"][1]["content"]) for p in (a, b))
            self.assertEqual(av["measured_evidence"], bv["measured_evidence"])
            self.assertEqual(av["reference_context"], [])
            self.assertEqual(len(bv["reference_context"]), 2)

    def test_evaluator_metadata_does_not_enter_messages_or_query(self):
        for case in self.cases:
            request = rag.prepared_request(case["input"], "B", self.receipt(case["input"]))
            text = json.dumps(request["request"]["messages"]) + rag.query_for(case["input"])
            for forbidden in ("scenario_id", "expected_claim", "expected_trials", "security_level", "condition_id", "confirmed_success"):
                self.assertNotIn(forbidden, text)

    def test_modified_reference_and_wrong_technique_are_rejected(self):
        case = self.cases[0]
        receipt = self.receipt(case["input"])
        receipt["chunks"][0]["text"] += "This candidate succeeds."
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            rag.prepared_request(case["input"], "B", receipt)
        receipt = self.receipt(case["input"])
        receipt["chunks"][0] = next(c for c in self.corpus["chunks"] if c["technique"] == "time-based blind")
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            rag.prepared_request(case["input"], "B", receipt)

    def test_no_A_retrieval_and_no_B_without_receipt(self):
        document = self.cases[0]["input"]
        with self.assertRaises(ValueError):
            rag.prepared_request(document, "A", self.receipt(document))
        with self.assertRaises(ValueError):
            rag.prepared_request(document, "B")
        with self.assertRaises(ValueError):
            rag.prepared_request(document, "C")

    def test_actual_chroma_memory_retrieval_filters_and_ranks(self):
        import chromadb
        techniques = list(dict.fromkeys(c["technique"] for c in self.corpus["chunks"]))
        vectors = [[1.0 if axis == techniques.index(c["technique"]) else 0.01 * i for axis in range(3)]
                   for i, c in enumerate(self.corpus["chunks"], 1)]
        docs = [next(c["input"] for c in self.cases if c["input"]["technique"] == t) for t in techniques]
        queries = [rag.query_for(d) for d in docs]
        query_vectors = [[float(i == j) for j in range(3)] for i in range(3)]
        with patch.object(chromadb, "PersistentClient", side_effect=AssertionError("Frozen index must not open")):
            receipts = rag.retrieve_from_vectors(self.corpus, vectors, queries, query_vectors)
        for receipt in receipts.values():
            technique = json.loads(receipt["query"])["technique"]
            self.assertEqual(len(receipt["candidate_pool"]), 3)
            self.assertEqual(len(receipt["chunks"]), 2)
            self.assertTrue(all(c["technique"] == technique for c in receipt["chunks"]))
            self.assertEqual([c["entry_id"] for c in receipt["chunks"]], [c["entry_id"] for c in receipt["candidate_pool"][:2]])

    def model_output(self, case, claim):
        roles = pilot.gate.ROLES[case["input"]["technique"]]
        expected = next(l for l in self.labels if l["case_id"] == case["case_id"])["expected_trials"]
        assessments = [{"trial": int(t), "outcome": outcome,
                        "evidence_refs": [o["observation_id"] for o in case["input"]["observations"] if o["trial"] == int(t) and o["role"] in roles]}
                       for t, outcome in expected.items()]
        positives = sum(a["outcome"] == "positive" for a in assessments)
        return {"trial_assessments": assessments, "confirmation_summary": {"observed_trials": sorted(map(int, expected)),
                "positive_trial_count": positives, "negative_trial_count": len(assessments) - positives},
                "decision": claim, "reason_code": pilot.gate.REASONS[case["input"]["technique"]].get(claim, "insufficient_evidence"),
                "reason": "Deliberately unsupported model claim for preservation test.",
                "evidence_refs": [ref for a in assessments for ref in a["evidence_refs"]], "feedback_action": "none"}

    def test_RAG_preserves_unsupported_raw_claim(self):
        case = self.cases[1]
        receipt = self.receipt(case["input"])
        prepared = rag.prepared_request(case["input"], "B", receipt)
        context = {**case["context"], "condition_id": "B", "rag_mode": "on"}
        raw = json.dumps(self.model_output(case, "positive"))
        response = {"model": rag.base.MODEL, "message": {"content": raw}, "done_reason": "stop"}
        with patch.object(rag.base.v1, "post_ollama", return_value=response):
            record = rag.analyze(case["input"], context, "B", receipt, prepared)
        self.assertEqual(record["system_claim"], "positive")
        self.assertEqual(record["audit"]["provenance"]["raw_model_content"], raw)
        self.assertEqual(record["audit"]["provenance"]["retrieved_entry_ids"], [c["entry_id"] for c in receipt["chunks"]])
        combined = pilot.gate.combine(record)
        self.assertEqual(combined["llm_record"], record)
        self.assertEqual(combined["combined"]["decision"], "inconclusive")

    def test_runtime_invalid_skips_inference_for_both_conditions(self):
        case = self.cases[-1]
        for condition in ("A", "B"):
            receipt = self.receipt(case["input"]) if condition == "B" else None
            prepared = rag.prepared_request(case["input"], condition, receipt)
            context = {**case["context"], "condition_id": condition, "rag_mode": "off" if condition == "A" else "on"}
            with patch.object(rag.base.v1, "post_ollama", side_effect=AssertionError("Unexpected inference")):
                record = rag.analyze(case["input"], context, condition, receipt, prepared)
            self.assertEqual(record["analysis_status"], "runtime_invalid")

    def test_modified_request_rejected_before_inference(self):
        case = self.cases[0]
        prepared = rag.prepared_request(case["input"], "A")
        prepared["request"]["options"]["seed"] = 2
        with patch.object(rag.base.v1, "post_ollama") as call:
            with self.assertRaisesRegex(ValueError, "changed after freeze"):
                rag.analyze(case["input"], case["context"], "A", None, prepared)
        call.assert_not_called()

    def test_hand_declared_fixture_labels_match_verifier_without_creating_labels(self):
        for case, label in zip(self.cases, self.labels):
            result = pilot.gate.verify(case["input"])
            self.assertEqual(result["decision"], label["expected_claim"] or "not_evaluable")
            if label["expected_claim"] is not None:
                self.assertEqual({str(r["trial"]): r["outcome"] for r in result["trial_assessments"]}, label["expected_trials"])

    def test_offline_design_freeze_does_not_call_models_or_embeddings(self):
        temporary_root = pilot.ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root, prefix="rag-v4-test-") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(temporary_root.resolve()))
            output = Path(directory) / "prepared"
            with patch.object(rag.base.v1, "post_ollama", side_effect=AssertionError("Unexpected model call")):
                pilot.prepare(output)
            manifest = json.loads((output / "design-manifest.json").read_text())
            self.assertEqual(manifest["planned_model_calls"], 36)
            self.assertEqual(manifest["unique_queries"], 3)


if __name__ == "__main__":
    unittest.main()
