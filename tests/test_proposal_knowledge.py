"""Exercise corpus integrity, source boundaries, safe queries and index isolation."""

import copy
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "development"))
sys.path.insert(0, str(ROOT_DIR / "dvwa"))
from test_prerequisites import require_local_snapshots
from generate_candidate_batch import build_messages as build_generation_messages
from jsonschema.exceptions import ValidationError
from knowledge_corpus import ROOT, CORPUS_KIND, prepare_documents, validate_corpus
from rag_pipeline import injection_point_context, load_catalog, scenario_query
from retrieve_structured_knowledge import retrieve


class ProposalKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_snapshots("knowledge/sources.lock.json")

    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="proposal-tests-", dir=ROOT / "tmp")
        assert Path(self.temp.name).resolve().is_relative_to((ROOT / "tmp").resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        corpus, lock = validate_corpus()
        for relative in ["knowledge/sqli-entries.json", "knowledge/sources.lock.json",
                         "schemas/sqli-knowledge-corpus.schema.json"] + [
                item["snapshot_path"] for source in lock["sources"] for item in source["files"]]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.path = self.root / "knowledge/sqli-entries.json"
        self.corpus, self.lock = corpus, lock
        self.scenario = load_catalog()["scenarios"][0]

    def test_unexpected_corpus_fields_and_evaluation_source_are_rejected(self):
        for mutate in (lambda d: d["entries"][0].update(ground_truth="positive"),
                       lambda d: d["entries"][0]["source_refs"][0].update(source_id="SecLists")):
            data = copy.deepcopy(self.corpus)
            mutate(data)
            self.path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValidationError):
                validate_corpus(self.path, self.root)

    def test_generation_prompt_contains_rules_only_for_selected_probe_technique(self):
        error = "\n".join(item["content"] for item in build_generation_messages(self.scenario, 1))
        self.assertIn("single error-based diagnostic probe", error)
        self.assertIn("Never use delays, timing functions", error)
        self.assertNotIn("For timing probes use a bounded delay", error)
        timing = next(item for item in load_catalog()["scenarios"] if item["scenario_id"] == "S3")
        time_prompt = "\n".join(item["content"] for item in build_generation_messages(timing, 1))
        self.assertIn("time-based blind probe", time_prompt)
        self.assertIn("at most two seconds", time_prompt)
        self.assertNotIn("single error-based diagnostic probe", time_prompt)

    def test_source_snapshot_tampering_is_rejected(self):
        snapshot = self.root / self.lock["sources"][0]["files"][0]["snapshot_path"]
        snapshot.write_text("different source", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            validate_corpus(self.path, self.root)

    def test_invalid_source_coordinates_and_duplicate_entry_ids_are_rejected(self):
        for mutate in (lambda d: d["entries"][0]["source_refs"][0].update(line_start=999999, line_end=999999),
                       lambda d: d["entries"][1].update(entry_id=d["entries"][0]["entry_id"])):
            data = copy.deepcopy(self.corpus)
            mutate(data)
            self.path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_corpus(self.path, self.root)

    def test_query_uses_coordinates_without_ground_truth_or_level(self):
        query = scenario_query(self.scenario)
        changed = {**self.scenario, "security_level": "impossible", "ground_truth": "negative"}
        self.assertEqual(query, scenario_query(changed))
        self.assertNotEqual(query, scenario_query({**changed, "method": "POST"}))
        self.assertIn("parameter id", query)

    def test_normalized_zap_context_drops_secret_and_label_fields(self):
        report = self.root / "zap.json"
        data = {"run_metadata": {"security_level": "low"}, "candidate_injection_points": [{
            "path": self.scenario["input_path"], "method": "GET", "parameter": "id",
            "source_observation_id": "zapobs-fixture", "cookie": "secret", "ground_truth": "positive"}]}
        report.write_text(json.dumps(data), encoding="utf-8")
        point = injection_point_context(self.scenario, report)
        self.assertEqual(point["source"], "normalized-zap")
        self.assertNotIn("secret", json.dumps(point))
        self.assertNotIn("ground_truth", point)
        data["run_metadata"]["security_level"] = "high"
        report.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            injection_point_context(self.scenario, report)

    def test_proposal_retrieval_rejects_the_pdf_index(self):
        with self.assertRaisesRegex(ValueError, "PDF indexes are diagnostic"):
            retrieve("error-based", {"purpose": "experimental-pdf-smoke"}, 5, "error-based")

    def test_retrieval_uses_global_top_k_and_detects_tampered_text(self):
        documents = prepare_documents(self.corpus, self.lock)
        item = next(d for d in documents if d["metadata"]["vulnerability_type"] == "error-based")
        class Collection:
            def count(self): return len(documents)
            def query(self, **kwargs):
                self.kwargs = kwargs
                return {"ids": [[item["id"]]], "documents": [[item["text"]]],
                        "metadatas": [[item["metadata"]]], "distances": [[0.1]]}
        collection = Collection()
        manifest = {"corpus_kind": CORPUS_KIND, "purpose": "proposal-rag", "corpus_path": "knowledge/sqli-entries.json",
                    "corpus_sha256": __import__('hashlib').sha256((ROOT / "knowledge/sqli-entries.json").read_bytes()).hexdigest(),
                    "source_lock_sha256": self.corpus["source_lock_sha256"], "embedding_model": "nomic-embed-text",
                    "embedding_input_format": "nomic-search-prefix-v1", "resolved_store_path": str(self.root),
                    "collection_name": "fixture", "knowledge_base_id": "fixture"}
        with patch("chromadb.PersistentClient") as client, patch("rag_pipeline.embed_texts", return_value=[[1., 0.]]):
            client.return_value.get_collection.return_value = collection
            result = retrieve("error-based", manifest, 2, "error-based")
            self.assertNotIn("where", collection.kwargs)
            self.assertEqual(collection.kwargs["n_results"], 2)
            self.assertEqual(result["chunks"][0]["text"], item["text"])
            item["text"] += " tampered"
            with self.assertRaisesRegex(ValueError, "differs"):
                retrieve("error-based", manifest, 2, "error-based")

    def test_generator_pair_keeps_controls_and_isolates_rag_off(self):
        import generate_candidate_batch as generator
        document = prepare_documents(self.corpus, self.lock)[0]
        retrieval = {"knowledge_base_id": "fixture", "selection_policy_sha256": "a" * 64,
                     "curation_annotation_sha256": "b" * 64, "chunks": [
                         {"chunk_id": document["id"], "text": document["text"], "metadata": document["metadata"]}]}
        response = {"model": "qwen2.5:7b", "message": {"content": '{"candidates":[{"payload":"benign-fixture-value"}]}'}}
        calls = []
        for mode in ("off", "on"):
            argv = ["generate_candidate_batch.py", "--scenario", "S1", "--rag-mode", mode,
                    "--comparison-id", "fixture-pair", "--seed", "42"]
            with patch.object(sys, "argv", argv), patch.object(generator, "ROOT", self.root), \
                 patch.object(generator, "retrieve_chunks", return_value=retrieval) as retrieve_mock, \
                 patch.object(generator, "post_ollama", return_value=response) as chat, \
                 contextlib.redirect_stdout(io.StringIO()):
                generator.main()
                calls.append(chat.call_args.args[1])
                self.assertEqual(retrieve_mock.call_count, 1 if mode == "on" else 0)
        self.assertEqual(calls[0]["options"], calls[1]["options"])
        self.assertEqual(calls[0]["format"], calls[1]["format"])
        self.assertNotIn(document["id"], json.dumps(calls[0]["messages"]))
        self.assertIn(document["id"], json.dumps(calls[1]["messages"]))


if __name__ == "__main__":
    unittest.main()
