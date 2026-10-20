"""Reproduce all token counts, probe checks and immutable artifact checks without services."""

from __future__ import annotations

import json
from pathlib import Path

from tokenizers import Tokenizer
import preflight_analysis_v5_context as context


def verify():
    context.previous.verify_primary()
    manifest=context.read(context.OUT/"preflight-manifest.json")
    for directory,key in ((context.RAW,"raw_sha256"),(context.OUT,"processed_sha256"),(context.ROOT,"source_sha256")):
        for name,expected in manifest[key].items():
            if context.digest(directory/name)!=expected:raise ValueError(f"Preflight artifact changed: {name}")
    tokenizer=Tokenizer.from_file(str(context.RAW/"tokenizer.json"))
    receipt=context.read(context.RAW/"tokenizer-receipt.json")
    for name,row in receipt["files"].items():
        if context.digest(context.RAW/name)!=row["sha256"]:raise ValueError("Tokenizer snapshot changed.")
    official=context.read(context.RAW/"tokenizer.json")
    info=context.read(context.RAW/"model-show.json")["model_info"]
    for word,index in official["model"]["vocab"].items():
        if info["tokenizer.ggml.tokens"][index]!=word:raise ValueError("Installed vocabulary differs.")
    for token in official["added_tokens"]:
        if info["tokenizer.ggml.tokens"][token["id"]]!=token["content"]:raise ValueError("Installed special token differs.")
    merges=[' '.join(x) if isinstance(x,list) else x for x in official['model']['merges']]
    if merges!=info['tokenizer.ggml.merges']:raise ValueError("Installed merge table differs.")
    counts=context.read(context.OUT/"offline-token-counts.json")
    indexed={(r["profile"],r["case_id"],r["condition"]):r for r in counts}
    for profile,name in (("top2","prepared-requests.json"),("top3","secondary-top3-requests.json")):
        for row in context.read(context.previous.RAW/name):
            request=row["prepared"]["request"]
            count=len(tokenizer.encode(context.serialized_chat(request),add_special_tokens=False).ids)
            expected=indexed[(profile,row["case_id"],row["condition"])]
            if count!=expected["prompt_tokens"] or context.previous.rag.sha(request)!=expected["request_sha256"]:
                raise ValueError("Offline request count or content differs.")
    plans={r["probe_id"]:r for r in context.read(context.RAW/"planned-context-probes.json")}
    rows=[json.loads(line) for line in (context.RAW/"context-probes.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows)!=len(plans):raise ValueError("Incomplete context probes.")
    verified=[]
    for row in rows:
        plan=plans[row["probe_id"]]
        original=context.read(context.ROOT/plan["original_request_path"])
        request=json.loads(json.dumps(plan["request"]))
        if request["options"].pop("stop")!=["{"] or request!=original:
            raise ValueError("Probe changed more than the declared stop sequence.")
        if context.previous.rag.sha(plan["request"])!=row["request_sha256"]:raise ValueError("Recorded runtime request differs.")
        verified.append({"probe_id":row["probe_id"],**context.runtime_check(row["response"],plan["offline_prompt_tokens"],plan["request"]["options"])})
    summary=context.read(context.OUT/"runtime-context-summary.json")
    if verified!=summary["rows"]:raise ValueError("Summary differs from recorded API responses.")
    for name in ("runtime-before.json","runtime-after.json"):
        if context.read(context.RAW/name)["model"]["digest"]!=context.EXPECTED_DIGEST:raise ValueError("Model digest differs.")
    protected=context.check_protected()
    report={"status":"offline-verification-passed","request_counts_reproduced":len(counts),"runtime_probes_verified":len(rows),
            "protected_files_unchanged":protected,"no_model_calls_in_this_verification":True,
            "maximum_prompt_tokens":summary["maximum_prompt_tokens"],"minimum_reserved_headroom":summary["minimum_reserved_headroom"]}
    print(json.dumps(report))
    return report


if __name__=="__main__":
    verify()
