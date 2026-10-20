"""Check ablation integrity and metadata isolation before any chat execution exists."""

import copy
import json
import unittest

from test_prerequisites import require_local_snapshots
from unittest.mock import patch

import analysis_rag_v5 as rag
import prepare_analysis_rag_v5 as prepare


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_local_snapshots("knowledge/analysis-v5/sources.lock.json")
        cls.projection=rag.project_corpus()
        cls.cases=prepare.fixtures()

    def receipt(self,document):
        eligible=[c for c in self.projection["chunks"] if document["technique"] in c["techniques"]]
        pool=[{"chunk_id":c["chunk_id"],"distance":float(i)} for i,c in enumerate(eligible)]
        return {"query":rag.query_for(document),"policy":copy.deepcopy(rag.POLICY),
                "projection_sha256":rag.sha(self.projection),"candidate_pool":pool,"chunks":copy.deepcopy(eligible[:2])}

    def test_ablation_changes_only_reference_context_and_preserves_all_paired_rows(self):
        for case in self.cases:
            doc=case["input"]
            a=rag.prepared_request(doc,"A",projection=self.projection)
            b=rag.prepared_request(doc,"B",self.receipt(doc),projection=self.projection)
            self.assertEqual(a["request"]["messages"][0],b["request"]["messages"][0])
            for field in ("model","format","options","stream"):
                self.assertEqual(a["request"][field],b["request"][field])
            av,bv=[json.loads(r["request"]["messages"][1]["content"]) for r in (a,b)]
            self.assertEqual(av["measured_evidence"],bv["measured_evidence"])
            self.assertEqual(av["measured_evidence"],rag.base.v1.paired_view(doc))
            self.assertEqual(list(bv),["measured_evidence","reference_context"])
            self.assertEqual(av["reference_context"],[])
            self.assertEqual(len(bv["reference_context"]),2)
            self.assertEqual(a["provenance"]["runtime_eligible"],case["shape"]!="invalid-runtime")

    def test_review_and_evaluator_metadata_never_enter_model_messages(self):
        for case in self.cases:
            prepared=rag.prepared_request(case["input"],"B",self.receipt(case["input"]),projection=self.projection)
            messages=json.dumps(prepared["request"]["messages"])
            for value in ("PREPARATION_CANARY_NOT_FOR_MODEL","EVALUATOR_ONLY_NOT_FOR_MODEL",
                          "researcher_review","feedback_sha256","prompt_contract","approval"):
                self.assertNotIn(value,messages)

    def test_query_does_not_depend_on_observations_or_validity(self):
        for case in self.cases:
            modified=copy.deepcopy(case["input"])
            modified["runtime_status"]="invalid";modified["baseline_valid"]=False
            modified["observations"]=[]
            self.assertEqual(rag.query_for(case["input"]),rag.query_for(modified))

    def test_projection_and_reference_tampering_are_rejected(self):
        doc=self.cases[0]["input"]
        receipt=self.receipt(doc);receipt["chunks"][0]["text"]+=" Target is vulnerable."
        with self.assertRaisesRegex(ValueError,"allowlisted"):
            rag.prepared_request(doc,"B",receipt,projection=self.projection)
        projection=copy.deepcopy(self.projection);projection["chunks"][0]["text"]="modified"
        with self.assertRaisesRegex(ValueError,"current validated"):
            rag.prepared_request(doc,"A",projection=projection)

    def test_wrong_rank_or_technique_and_missing_receipt_are_rejected(self):
        doc=self.cases[0]["input"]
        receipt=self.receipt(doc);receipt["chunks"].reverse()
        with self.assertRaisesRegex(ValueError,"ranked"):
            rag.prepared_request(doc,"B",receipt,projection=self.projection)
        receipt=self.receipt(doc);receipt["candidate_pool"][0]["chunk_id"]="analysis-v5-timing-control"
        with self.assertRaisesRegex(ValueError,"candidate-pool"):
            rag.prepared_request(doc,"B",receipt,projection=self.projection)
        with self.assertRaises(ValueError):rag.prepared_request(doc,"B",projection=self.projection)
        with self.assertRaises(ValueError):rag.prepared_request(doc,"A",self.receipt(doc),projection=self.projection)

    def test_budget_guards_reject_instead_of_silently_cutting_evidence(self):
        doc=self.cases[0]["input"]
        original=copy.deepcopy(doc)
        with patch.object(rag,"MAX_REFERENCE_BYTES",1):
            with self.assertRaisesRegex(ValueError,"not be trimmed"):
                rag.prepared_request(doc,"B",self.receipt(doc),projection=self.projection)
        with patch.object(rag,"MAX_MESSAGE_BYTES",1):
            with self.assertRaisesRegex(ValueError,"no partial request"):
                rag.prepared_request(doc,"A",projection=self.projection)
        self.assertEqual(doc,original)

    def test_memory_retrieval_supports_shared_scope_without_opening_formal_index(self):
        import chromadb
        projection=self.projection
        vectors=[[float(i==j)+0.01 for j in range(7)] for i in range(7)]
        docs=[next(c["input"] for c in self.cases if c["input"]["technique"]==t) for t in rag.TECHNIQUES]
        queries=[rag.query_for(d) for d in docs]
        with patch.object(chromadb,"PersistentClient",side_effect=AssertionError("Formal index opened")):
            receipts=rag.retrieve_from_vectors(projection,vectors,queries,[vectors[0],vectors[2],vectors[4]])
        for doc,query in zip(docs,queries):
            import hashlib
            receipt=receipts[hashlib.sha256(query.encode()).hexdigest()]
            self.assertEqual(len(receipt["candidate_pool"]),3)
            self.assertIn("analysis-v5-conclusion-scope",[r["chunk_id"] for r in receipt["candidate_pool"]])
            self.assertTrue(all(doc["technique"] in c["techniques"] for c in receipt["chunks"]))
            rag.prepared_request(doc,"B",receipt,projection=projection)


if __name__=="__main__":
    unittest.main()
