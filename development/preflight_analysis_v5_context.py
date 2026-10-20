"""Count full ChatML inputs and run bounded context probes, without evaluating verdicts."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.request import ProxyHandler, Request, build_opener

from tokenizers import Tokenizer
import inspect_analysis_v5_readiness as previous

ROOT=previous.ROOT
RAW=ROOT/"results/raw/development/analysis-v5-context-preflight-20261020"
OUT=ROOT/"results/processed/analysis-v5-context-preflight-20261020"
EXPECTED_DIGEST="845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"
MODEL="qwen2.5:7b"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write("\n")


def serialized_chat(payload):
    """Installed Qwen template branch: one supplied system, one user, no tools/history."""
    if payload.get("tools") or [m["role"] for m in payload["messages"]]!=["system","user"]:
        raise ValueError("Only the inspected two-message, no-tool template branch is supported.")
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in payload["messages"])+"<|im_start|>assistant\n"


def runtime_check(response,expected_prompt,options):
    if response.get("done") is not True or response.get("done_reason")!="stop":
        raise ValueError("Context probe did not stop cleanly.")
    if response.get("prompt_eval_count")!=expected_prompt:
        raise ValueError("Runtime prompt count differs from complete offline-tokenized input.")
    output=response.get("eval_count")
    if type(output) is not int or not 0<=output<options["num_predict"]:
        raise ValueError("Missing or exhausted output token accounting.")
    margin=options["num_ctx"]-expected_prompt-options["num_predict"]
    if margin<0:raise ValueError("Full input plus configured output allowance exceeds context.")
    return {"exact_prompt_count_match":True,"prompt_tokens":expected_prompt,
            "generated_tokens":output,"configured_output_reserve":options["num_predict"],
            "context_tokens":options["num_ctx"],"reserved_headroom":margin,
            "no_input_token_loss_observed":True}


def api(endpoint,payload=None):
    request=Request("http://127.0.0.1:11434"+endpoint,
        data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),
        headers={} if payload is None else {"Content-Type":"application/json"})
    with build_opener(ProxyHandler({})).open(request,timeout=240) as response:return json.load(response)


def prepare():
    previous.verify_primary()
    if OUT.exists():raise ValueError("Use a fresh preflight directory.")
    OUT.mkdir(parents=True)
    protected=dict(read(previous.OUT/"preservation-baseline.json")["files"])
    for folder in [previous.OUT,previous.RAW,previous.PREVIEW,ROOT/"knowledge/analysis-v5"]:
        for path in folder.rglob("*"):
            if path.is_file():protected[path.relative_to(ROOT).as_posix()]=digest(path)
    for path in [Path(previous.__file__),Path(previous.preparation.__file__),Path(previous.rag.__file__),
                 Path(previous.rag.checker.__file__),ROOT/"schemas/analysis-knowledge-v5-rev2.schema.json"]:
        protected[path.relative_to(ROOT).as_posix()]=digest(path)
    write_new(OUT/"preservation-baseline.json",{"files":dict(sorted(protected.items())),"basis":"before-context-runtime-probes"})
    tokenizer=Tokenizer.from_file(str(RAW/"tokenizer.json"))
    receipt=read(RAW/"tokenizer-receipt.json")
    for name,record in receipt["files"].items():
        if digest(RAW/name)!=record["sha256"]:raise ValueError("Tokenizer source differs.")
    if read(RAW/"model-inventory.json")["digest"]!=EXPECTED_DIGEST:
        raise ValueError("Installed model differs from formal/v4 digest.")
    counts=[]
    for profile,name in (("top2","prepared-requests.json"),("top3","secondary-top3-requests.json")):
        for row in read(previous.RAW/name):
            payload=row["prepared"]["request"]
            n=len(tokenizer.encode(serialized_chat(payload),add_special_tokens=False).ids)
            margin=payload["options"]["num_ctx"]-payload["options"]["num_predict"]-n
            if margin<0:raise ValueError("Prepared request exceeds reserved context.")
            counts.append({"profile":profile,"case_id":row["case_id"],"condition":row["condition"],
                           "prompt_tokens":n,"reserved_headroom":margin,"request_sha256":previous.rag.sha(payload)})
    write_new(OUT/"offline-token-counts.json",counts)
    calls=[]
    for path in sorted(previous.PREVIEW.glob("*.request.json")):
        payload=read(path);probe=copy.deepcopy(payload)
        if "stop" in probe["options"]:raise ValueError("Unexpected existing stop override.")
        probe["options"]["stop"]=["{"]
        n=len(tokenizer.encode(serialized_chat(payload),add_special_tokens=False).ids)
        calls.append({"probe_id":path.name.removesuffix(".request.json"),"original_request_path":path.relative_to(ROOT).as_posix(),
                      "original_request_sha256":digest(path),"offline_prompt_tokens":n,"request":probe,
                      "only_option_delta":{"stop":["{"]},"verdict_evaluation":False})
    write_new(RAW/"planned-context-probes.json",calls)
    write_new(OUT/"design.json",{"scope":"runtime-context-preflight-not-model-performance-evaluation","planned_chat_probes":len(calls),
        "new_dvwa_requests":0,"model":MODEL,"expected_model_digest":EXPECTED_DIGEST,
        "num_ctx":4096,"num_predict":768,"early_stop":"{","preflight_outputs_are_verdicts":False,
        "tokenizer_revision":receipt["revision"],"input_count_method":"official tokenizer, installed vocabulary/merges checked; installed ChatML template branch",
        "source_sha256":{str(Path(__file__).relative_to(ROOT)):digest(Path(__file__))},
        "probe_plan_sha256":digest(RAW/"planned-context-probes.json"),
        "tokenizer_receipt_sha256":digest(RAW/"tokenizer-receipt.json"),"researcher_adoption":"not-recorded"})
    print(json.dumps({"status":"preflight-plan-pinned","requests_counted":len(counts),"planned_probes":len(calls),
                      "maximum_prompt_tokens":max(r["prompt_tokens"] for r in counts),
                      "minimum_reserved_headroom":min(r["reserved_headroom"] for r in counts)}))


def check_protected():
    inventory=read(OUT/"preservation-baseline.json")["files"]
    for name,expected in inventory.items():
        if digest(ROOT/name)!=expected:raise ValueError(f"Preserved artifact changed: {name}")
    return len(inventory)


def run():
    design=read(OUT/"design.json");check_protected()
    for name,expected in design["source_sha256"].items():
        if digest(ROOT/name)!=expected:raise ValueError("Preflight source changed.")
    if digest(RAW/"planned-context-probes.json")!=design["probe_plan_sha256"]:raise ValueError("Probe plan changed.")
    if (RAW/"context-probes.jsonl").exists():raise ValueError("Already started; retain existing probes without retry.")
    actual=next(m for m in api("/api/tags")["models"] if m["name"]==MODEL)
    if actual["digest"]!=EXPECTED_DIGEST:raise ValueError("Model digest changed before probes.")
    write_new(RAW/"runtime-before.json",{"model":actual,"version":api("/api/version"),"ps":api("/api/ps")})
    rows=[]
    with (RAW/"context-probes.jsonl").open("x",encoding="utf-8",newline="\n") as stream:
        for planned in read(RAW/"planned-context-probes.json"):
            if digest(ROOT/planned["original_request_path"])!=planned["original_request_sha256"]:
                raise ValueError("Original request changed.")
            print(json.dumps({"probe":planned["probe_id"],"status":"starting"}),flush=True)
            started=time.monotonic();response=api("/api/chat",planned["request"])
            record={"probe_id":planned["probe_id"],"recorded_at_utc":datetime.now(timezone.utc).isoformat(),
                "request_sha256":previous.rag.sha(planned["request"]),"response":response,
                "elapsed_seconds":time.monotonic()-started,"scope":"context-only-intentionally-early-stopped"}
            stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+"\n");stream.flush()
            verified=runtime_check(response,planned["offline_prompt_tokens"],planned["request"]["options"])
            rows.append({"probe_id":planned["probe_id"],**verified})
            print(json.dumps({"probe":planned["probe_id"],"status":"verified",**verified}),flush=True)
    after={"model":next(m for m in api("/api/tags")["models"] if m["name"]==MODEL),"ps":api("/api/ps")}
    if after["model"]["digest"]!=EXPECTED_DIGEST:raise ValueError("Model digest changed during preflight.")
    write_new(RAW/"runtime-after.json",after)
    summary={"status":"passed-for-recorded-context-probes","scope":design["scope"],"chat_probes":len(rows),
        "verdicts_evaluated":0,"dvwa_requests":0,"rows":rows,
        "maximum_prompt_tokens":max(r["prompt_tokens"] for r in rows),
        "minimum_reserved_headroom":min(r["reserved_headroom"] for r in rows),
        "expected_model_digest":EXPECTED_DIGEST,"digest_unchanged":True,
        "tokenizer_matched_installed_model":True,"all_full_input_counts_match_runtime":True,
        "server_log_truncation_audit":"not-used; independent full-input token counts compared with each runtime prompt count",
        "full_output_completion_tested":False,"future_prompt_fit_guaranteed":False,
        "early_stop_override_is_for_preflight_only":True,"researcher_adoption":"not-recorded",
        "protected_files_unchanged":check_protected()}
    write_new(OUT/"runtime-context-summary.json",summary)
    write_new(OUT/"preflight-manifest.json",{"source_sha256":design["source_sha256"],
        "raw_sha256":{p.name:digest(p) for p in RAW.iterdir() if p.is_file()},
        "processed_sha256":{p.name:digest(p) for p in OUT.iterdir() if p.is_file()}})
    print(json.dumps({"status":summary["status"],"chat_probes":len(rows),
                     "maximum_prompt_tokens":summary["maximum_prompt_tokens"],
                     "minimum_reserved_headroom":summary["minimum_reserved_headroom"]}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--phase",choices=("prepare","run"),default="prepare")
    args=parser.parse_args();{"prepare":prepare,"run":run}[args.phase]()
