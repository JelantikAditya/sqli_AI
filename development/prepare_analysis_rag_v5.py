"""Pin readiness design, evaluate memory retrieval, and inspect requests; never call /api/chat."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time
from urllib.request import ProxyHandler, build_opener

import analysis_rag_v5 as rag

ROOT = rag.ROOT
RAW = ROOT / "results/raw/development/analysis-v5-renderer-readiness-20261020"
OUT = ROOT / "results/processed/analysis-v5-renderer-readiness-20261020"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def fixtures():
    """Input-shape probes only, with no target traffic or model-performance labels."""
    result = []
    for technique in rag.TECHNIQUES:
        for shape in ("complete", "missing-trial", "invalid-runtime"):
            observations = []
            for trial in ((1,2,3) if shape == "complete" else (1,3) if shape == "missing-trial" else ()):
                def observe(role, markers, diagnostics=(), status=200, elapsed=30):
                    oid = f"obs-{len(observations)+1:03d}"
                    observations.append({"observation_id":oid,"trial":trial,"role":role,
                        "http_status":status,"elapsed_ms":elapsed,"response_sha256":hashlib.sha256(oid.encode()).hexdigest(),
                        "diagnostics":list(diagnostics),"content_markers":list(markers),
                        "review_excerpt":"PREPARATION_CANARY_NOT_FOR_MODEL"})
                observe("baseline",["benign_record"] if technique=="error-based" else ["user_id_exists"])
                if technique == "error-based":
                    observe("candidate",[],["mysql_syntax_error"] if trial==2 else [],500)
                elif technique == "boolean-based blind":
                    observe("true_condition",["user_id_exists"])
                    observe("false_condition",["user_id_missing"],status=404)
                else:
                    observe("candidate",["user_id_exists"],elapsed=1549.98 if trial==2 else 1550)
                    observe("no_delay_control",["user_id_exists"],elapsed=50)
            document={"schema_version":"1.0.0","technique":technique,
                      "injection_point":{"method":"GET","input_path":"/vulnerabilities/sqli/" if technique=="error-based" else "/vulnerabilities/sqli_blind/",
                                         "result_path":"/vulnerabilities/sqli/" if technique=="error-based" else "/vulnerabilities/sqli_blind/","parameter":"id"},
                      "runtime_status":"invalid" if shape=="invalid-runtime" else "valid",
                      "baseline_valid":shape!="invalid-runtime","time_threshold_ms":1500,"observations":observations}
            rag.base.frozen.validate_input(document)
            result.append({"case_id":f"view-{len(result)+1:03d}","shape":shape,"input":document,
                           "evaluation_metadata_canary":"EVALUATOR_ONLY_NOT_FOR_MODEL"})
    return result


def assert_pins(design):
    for name, expected in design["source_sha256"].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f"Pinned preparation source changed: {name}")
    for name, expected in design["artifact_sha256"].items():
        if digest(RAW/name) != expected:
            raise ValueError(f"Pinned design artifact changed: {name}")
    rag.checker.audit()


def prepare():
    if RAW.exists():
        raise ValueError("Use a fresh readiness directory; do not overwrite an existing design.")
    corpus=rag.load_corpus()
    projection=rag.project_corpus(corpus)
    cases=fixtures()
    queries=[]
    for technique in rag.TECHNIQUES:
        document=next(c["input"] for c in cases if c["input"]["technique"]==technique)
        queries.append({"query_id":f"request-{len(queries)+1:02d}","purpose":"request-query",
                        "query":rag.query_for(document),
                        "required_topics":[c["topic"] for c in corpus["chunks"] if c["techniques"]==[technique]]})
    for chunk in corpus["chunks"]:
        for technique in chunk["techniques"]:
            queries.append({"query_id":f"facet-{len(queries)-2:02d}","purpose":"diagnostic-topic-query-not-production",
                "query":json.dumps({"technique":technique,"task":chunk["question"]},sort_keys=True,ensure_ascii=False),
                "required_topics":[chunk["topic"]]})
    rubric=[]
    for q in queries:
        technique=json.loads(q["query"])["technique"]
        rubric.extend({"query_id":q["query_id"],"chunk_id":c["chunk_id"],
                       "provisional_grade":3 if c["topic"] in q["required_topics"] else 1,
                       "basis":"predeclared-task-topic-match; not independent semantic gold"}
                      for c in projection["chunks"] if technique in c["techniques"])
    RAW.mkdir(parents=True)
    for name,value in (("projection.json",projection),("view-fixtures.json",cases),("queries.json",queries),
                       ("relevance-rubric.ai.json",{"origin":"Codex AI-authored development rubric", "human_review":"pending","rows":rubric})):
        write_new(RAW/name,value)
    sources=[Path(__file__),Path(rag.__file__),Path(rag.base.__file__),Path(rag.base.v1.__file__),
             Path(rag.checker.__file__),rag.checker.CORPUS,rag.checker.SCHEMA,
             ROOT/"knowledge/analysis-v5/design-decisions.rev2.json",ROOT/"knowledge/analysis-v5/sources.lock.json",
             ROOT/"development/test_analysis_rag_v5.py",ROOT/"dvwa/analyze_response.py",ROOT/"dvwa/rag_pipeline.py",
             ROOT/"dvwa/langchain_runtime.py",ROOT/"schemas/qwen-analysis-input.schema.json"]
    design={"preparation_id":"analysis-v5-renderer-readiness-20261020","created_at_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"development-renderer-and-retrieval-readiness-not-model-evaluation-or-pilot-release",
            "researcher_review":"pending","researcher_adoption":"not-recorded","review_origin":"AI-assisted",
            "model":rag.base.MODEL,"chat_calls_planned":0,"dvwa_requests":0,"embedding_model":rag.EMBEDDING_MODEL,
            "policy":rag.POLICY,"projection_sha256":rag.sha(projection),"queries":len(queries),"shape_probes":len(cases),
            "primary_top_k":2,"predeclared_secondary_top_k":3,
            "relevance_rubric":"AI-authored-provisional-not-independent-human-gold",
            "case_performance_labels_included":False,"runtime_context_preflight":"required-before-chat-pilot-not-executed",
            "source_sha256":{p.resolve().relative_to(ROOT).as_posix():digest(p) for p in sources},
            "artifact_sha256":{p.name:digest(p) for p in RAW.iterdir() if p.is_file()}}
    write_new(RAW/"design.json",design)
    print(json.dumps({"status":"design-pinned-before-embeddings","queries":len(queries),"shape_probes":len(cases),"chat_calls":0}))


def retrieve():
    design=read(RAW/"design.json");assert_pins(design)
    if (RAW/"retrieval-start.json").exists():
        raise ValueError("Retrieval already started; retain existing evidence instead of overwriting or retrying.")
    from rag_pipeline import embed_texts,local_ollama_url
    with build_opener(ProxyHandler({})).open(local_ollama_url()+"/api/tags",timeout=5) as response:
        models=json.load(response)["models"]
    embedder=next((m for m in models if m["name"].split(":")[0]==rag.EMBEDDING_MODEL),None)
    if embedder is None:
        raise ValueError("Local Nomic embedder unavailable.")
    projection=read(RAW/"projection.json");queries=read(RAW/"queries.json")
    write_new(RAW/"retrieval-start.json",{"model":embedder["name"],"digest":embedder["digest"],
                                          "created_at_utc":datetime.now(timezone.utc).isoformat(),"chat_calls":0})
    started=time.monotonic()
    document_vectors=embed_texts(embedder["name"],[c["text"] for c in projection["chunks"]],batch_size=16,task="document")
    query_vectors=embed_texts(embedder["name"],[q["query"] for q in queries],batch_size=16,task="query")
    receipts=rag.retrieve_from_vectors(projection,document_vectors,[q["query"] for q in queries],query_vectors)
    write_new(RAW/"embedding-snapshot.json",{"model":embedder["name"],"digest":embedder["digest"],
              "document_vectors":document_vectors,"query_vectors":query_vectors})
    write_new(RAW/"retrieval.json",receipts)
    grades={(r["query_id"],r["chunk_id"]):r["provisional_grade"] for r in read(RAW/"relevance-rubric.ai.json")["rows"]}
    chunk_topics={c["chunk_id"]:c["topic"] for c in projection["chunks"]}
    relevance=[];review=[]
    for q in queries:
        r=receipts[hashlib.sha256(q["query"].encode()).hexdigest()]
        selected=[c["chunk_id"] for c in r["chunks"]]
        topics={chunk_topics[key] for key in selected}
        missing=sorted(set(q["required_topics"])-topics)
        relevance.append({"query_id":q["query_id"],"purpose":q["purpose"],"query":q["query"],
                          "selected_chunk_ids":selected,"required_topics":q["required_topics"],"missing_topics_at_2":missing,
                          "required_topic_coverage_at_2":1-len(missing)/len(q["required_topics"]),
                          "all_required_topics_at_3":set(q["required_topics"]) <= {chunk_topics[x["chunk_id"]] for x in r["candidate_pool"][:3]},
                          "provisional_selected_grades":[grades[(q["query_id"],key)] for key in selected]})
        review.extend({"query_id":q["query_id"],"query":q["query"],"rank":i,"chunk_id":item["chunk_id"],
                       "distance":item["distance"],"ai_provisional_grade":grades[(q["query_id"],item["chunk_id"])],
                       "human_grade":None,"human_comment":"","review_status":"pending"}
                      for i,item in enumerate(r["candidate_pool"],1))
    schedule=[];audits=[]
    for case in read(RAW/"view-fixtures.json"):
        document=case["input"];receipt=receipts[hashlib.sha256(rag.query_for(document).encode()).hexdigest()]
        pair={condition:rag.prepared_request(document,condition,receipt if condition=="B" else None,projection=projection)
              for condition in ("A","B")}
        a,b=pair["A"]["request"],pair["B"]["request"]
        av,bv=(json.loads(x["messages"][1]["content"]) for x in (a,b))
        common=all(a[k]==b[k] for k in ("model","format","options","stream")) and a["messages"][0]==b["messages"][0]
        evidence=av["measured_evidence"]==bv["measured_evidence"]==rag.base.v1.paired_view(document)
        if not common or not evidence or av["reference_context"]:
            raise AssertionError("A/B contract or evidence differs.")
        for condition,prepared in pair.items():
            payload=json.dumps(prepared["request"],ensure_ascii=False)
            for forbidden in ("PREPARATION_CANARY_NOT_FOR_MODEL","EVALUATOR_ONLY_NOT_FOR_MODEL","researcher_review","prompt_contract","feedback_sha256"):
                if forbidden in payload:raise AssertionError(f"Metadata leaked: {forbidden}")
            schedule.append({"case_id":case["case_id"],"condition":condition,"prepared":prepared})
        audits.append({"case_id":case["case_id"],"shape":case["shape"],"identical_common_contract":common,
                       "identical_complete_paired_evidence":evidence,"renderer_truncated":False,
                       "message_bytes":{k:pair[k]["provenance"]["message_content_utf8_bytes"] for k in pair}})
    write_new(RAW/"prepared-requests.json",schedule)
    # Verify the actual serialized artifact, not just objects before writing.
    if read(RAW/"prepared-requests.json") != schedule:raise AssertionError("Serialized requests differ.")
    assert_pins(design)
    request_rows=[r for r in relevance if r["purpose"]=="request-query"]
    summary={"scope":design["scope"],"corpus_version":projection["corpus_version"],"queries":len(queries),
             "document_embeddings":len(document_vectors),"query_embeddings":len(query_vectors),
             "chat_calls":0,"dvwa_requests":0,"prepared_requests":len(schedule),"input_shape_pairs":len(audits),
             "all_common_contracts_identical":all(x["identical_common_contract"] for x in audits),
             "all_paired_evidence_preserved":all(x["identical_complete_paired_evidence"] for x in audits),
             "metadata_canaries_absent":True,"whole_chunks_only":True,
             "exact_token_count":None,"runtime_context_truncation_preflight":"not-executed; byte guards are not token proof",
             "relevance_status":"provisional-AI-task-rubric-not-independent-human-validation",
             "request_queries_with_full_required_coverage_at_2":sum(not x["missing_topics_at_2"] for x in request_rows),
             "diagnostic_queries_with_target_at_2":sum(not x["missing_topics_at_2"] for x in relevance if x["purpose"]!="request-query"),
             "request_queries":request_rows,"query_results":relevance,"request_integrity":audits,
             "embedding_model":embedder["name"],"embedding_digest":embedder["digest"],
             "chromadb_version":version("chromadb"),"retrieval_seconds":time.monotonic()-started,
             "source_lock_sha256":projection["source_lock_sha256"],"researcher_adoption":"not-recorded",
             "formal_metrics_recomputed":False,"pilot_released":False}
    write_new(OUT/"retrieval-summary.json",summary)
    write_new(OUT/"relevance-review.template.json",{"origin":"AI-provisional rubric; human review pending","rows":review})
    write_new(OUT/"request-integrity.json",audits)
    write_new(OUT/"readiness-manifest.json",{"design_sha256":digest(RAW/"design.json"),"raw_directory":RAW.relative_to(ROOT).as_posix(),
               "artifact_sha256":{p.name:digest(p) for p in RAW.iterdir() if p.is_file()},
               "processed_sha256":{name:digest(OUT/name) for name in ("retrieval-summary.json","relevance-review.template.json","request-integrity.json")},
               "chat_calls":0,"pilot_released":False})
    print(json.dumps({"status":"retrieval-and-request-inspection-completed","requests":len(schedule),
          "request_query_coverage_at_2":summary["request_queries_with_full_required_coverage_at_2"],
          "diagnostic_target_hits_at_2":summary["diagnostic_queries_with_target_at_2"],"chat_calls":0}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("prepare","retrieve"),default="prepare")
    args=parser.parse_args()
    {"prepare":prepare,"retrieve":retrieve}[args.phase]()
