"""Record post-ranking AI content judgments separately from the predeclared rubric."""

from __future__ import annotations

import json
from pathlib import Path

import preflight_analysis_v5_context as context

ROOT,RAW,OUT=context.ROOT,context.RAW,context.OUT
READY=context.previous.OUT


def assess():
    context.previous.verify_primary()
    context.check_protected()
    projection=context.read(context.previous.RAW/"projection.json")
    chunks={c["chunk_id"]:c for c in projection["chunks"]}
    queries=context.read(context.previous.RAW/"queries.json")
    request_summary=context.read(READY/"retrieval-summary.json")
    rows=[]
    for q in queries:
        technique=json.loads(q["query"])["technique"]
        for chunk in chunks.values():
            if technique not in chunk["techniques"]:continue
            topic=chunk["topic"]
            if topic in q["required_topics"]:
                grade=3
                rationale="Directly addresses the explicitly requested analysis topic; applies to supplied features rather than raw HTML."
            elif q["purpose"]=="request-query":
                grade=2
                rationale="Useful claim-scope guidance, but does not supply the omitted technique-specific comparison or confounder topic."
            elif topic=="conclusion-scope":
                grade=1
                rationale="Contextual limit on claims; not the specific comparator, direction, stability or timing issue asked by this query."
            elif q["required_topics"]==["conclusion-scope"]:
                grade=2
                rationale="Technique-specific conditions help bound a claim, while the dedicated scope chunk answers the general question directly."
            elif q["required_topics"]==["boolean-pair-direction"] and topic=="marker-stability":
                grade=1
                rationale="Repeatability is supporting context; it does not itself establish correct true/false orientation."
            elif q["required_topics"]==["matched-timing-control"] and topic=="timing-confounders":
                grade=1
                rationale="Noise cautions are supporting context; they do not identify the matching no-delay comparator."
            else:
                grade=2
                rationale="Complementary technique guidance needed to interpret the requested comparison; less direct than the topic-specific chunk."
            if topic=="marker-stability":
                rationale+=" Template discussion is upstream background only; the model compares supplied markers."
            if topic=="timing-confounders":
                rationale+=" A potential noise source is not an observed cause without independent telemetry."
            rows.append({"query_id":q["query_id"],"query":q["query"],"chunk_id":chunk["chunk_id"],
                         "rendered_text_sha256":chunk["text_sha256"],"ai_grade":grade,"rationale":rationale,
                         "human_grade":None,"researcher_adoption":"not-recorded"})
    report={"review_type":"post-ranking-AI-editorial-content-review-not-independent-semantic-gold",
        "reviewer":"Codex AI","researcher_adoption":"not-recorded","human_review":"pending",
        "ranking_and_query_tuning_performed":False,"previous_rubric_replaced":False,
        "grade_definitions":{"0":"irrelevant or incompatible","1":"contextual only","2":"useful complementary guidance","3":"directly addresses the query topic"},
        "rows":rows,"observed_selection":request_summary["request_queries"],
        "interpretation":[
            "Selected conclusion-scope chunks are relevant complementary knowledge, not irrelevant retrieval.",
            "Top-2 still omits one explicitly requested technique topic in each general query.",
            "Top-3 covers both technique topics by including all eligible chunks; semantic selection within that pool no longer changes content membership.",
            "These content judgments do not establish improved Qwen decisions or formal FPR/PSR."]}
    context.write_new(OUT/"relevance-review.ai.json",report)
    token_summary=context.read(OUT/"runtime-context-summary.json")
    if not token_summary["all_full_input_counts_match_runtime"]:raise ValueError("Context preflight has not passed.")
    corpus=context.read(ROOT/"knowledge/analysis-v5/corpus.rev2.json")
    profile={
        "profile_id":"analysis-v5-rev2-development-pilot-candidate-20261020",
        "status":"concrete-development-profile-not-formal-release",
        "scope":"SQLi response-feature interpretation; no payload generation or PSR experiment",
        "corpus_path":"knowledge/analysis-v5/corpus.rev2.json","corpus_sha256":context.digest(ROOT/"knowledge/analysis-v5/corpus.rev2.json"),
        "source_lock_sha256":corpus["source_lock_sha256"],"model":context.MODEL,"model_digest":context.EXPECTED_DIGEST,
        "options":{"temperature":0,"seed":42,"num_ctx":4096,"num_predict":768},
        "stop_override_from_preflight_in_pilot":False,
        "profiles":{
            "A":{"reference_context":"empty","role":"reference-free comparison"},
            "B2":{"top_k":2,"role":"ranked semantic retrieval comparison retained for diagnosis"},
            "B3":{"top_k":3,"role":"preferred complete eligible technique-context candidate"}},
        "preferred_development_profile":"A versus B3; retain B2 as secondary development comparison",
        "basis":["post-ranking AI content review identifies missing technical topic under top-2",
                 "predeclared top-3 covers both technique topics",
                 "9 runtime context probes match offline counts with full 768-token output reserve"],
        "method_limit":"B3 includes all three eligible chunks; compare knowledge context, without claiming semantic ranking caused a model improvement.",
        "common_contract":"same system prompt, schema, measurements and options across profiles; only reference_context differs",
        "model_outputs":"raw claim retained; deterministic verification remains separately reported",
        "evaluation_data_policy":{
            "renderer_fixtures":"wiring/preflight only, excluded from model-performance denominators",
            "previous_v1_v4_cases":"development history, not new holdout",
            "next_cases":"new prespecified response evidence, with evaluator labels outside model input and retrieval",
            "holdout_independence":"not established merely by changing numbers or hashes"},
        "planned_model_evaluation_executed":False,"pilot_execution_started":False,
        "researcher_review":"pending","researcher_adoption":"not-recorded",
        "context_evidence_path":str((OUT/"runtime-context-summary.json").relative_to(ROOT)),
        "context_evidence_sha256":context.digest(OUT/"runtime-context-summary.json"),
        "relevance_review_sha256":context.digest(OUT/"relevance-review.ai.json"),
        "required_next_checks":["freeze new evaluation cases and schedule before first performance call",
                                "check full output completion, not just input fit, on the future pilot",
                                "record analysis error, false positive/negative, abstention, coverage and runtime separately"],
        "formal_data_or_protocol_modified":False,
    }
    context.write_new(OUT/"pilot-profile.candidate.json",profile)
    print(json.dumps({"AI_content_judgments":len(rows),"human_judgments":0,
                      "preferred_profile":"A vs B3; B2 retained","pilot_execution_started":False}))


if __name__=="__main__":
    assess()
