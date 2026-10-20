"""Verify saved requests and build the predeclared top-3 secondary preview, without inference."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import prepare_analysis_rag_v5 as preparation

rag=preparation.rag
ROOT,RAW,OUT=preparation.ROOT,preparation.RAW,preparation.OUT
PREVIEW=ROOT/"outputs/analysis-v5-renderer-review"


def verify_primary():
    design=preparation.read(RAW/"design.json")
    preparation.assert_pins(design)
    manifest=preparation.read(OUT/"readiness-manifest.json")
    for folder,values in ((RAW,manifest["artifact_sha256"]),(OUT,manifest["processed_sha256"])):
        for name,expected in values.items():
            if preparation.digest(folder/name)!=expected:raise ValueError(f"Saved readiness artifact differs: {name}")
    return design


def secondary_requests():
    design=verify_primary()
    if design["predeclared_secondary_top_k"]!=3:raise ValueError("Top-3 comparison was not predeclared.")
    projection=preparation.read(RAW/"projection.json")
    receipts=preparation.read(RAW/"retrieval.json")
    chunks={c["chunk_id"]:c for c in projection["chunks"]}
    primary={(r["case_id"],r["condition"]):r["prepared"] for r in preparation.read(RAW/"prepared-requests.json")}
    result=[];integrity=[]
    for case in preparation.read(RAW/"view-fixtures.json"):
        doc=case["input"];key=hashlib.sha256(rag.query_for(doc).encode()).hexdigest()
        receipt=receipts[key]
        # Reproduce and validate primary requests before extending only the reference context.
        for condition in ("A","B"):
            actual=rag.prepared_request(doc,condition,receipt if condition=="B" else None,projection=projection)
            if actual!=primary[(case["case_id"],condition)]:raise ValueError("Saved primary request differs.")
        a=copy.deepcopy(primary[(case["case_id"],"A")]);b=copy.deepcopy(primary[(case["case_id"],"B")])
        bv=json.loads(b["request"]["messages"][1]["content"])
        references=[{"chunk_id":row["chunk_id"],"reference_text":chunks[row["chunk_id"]]["text"]}
                    for row in receipt["candidate_pool"][:3]]
        if len(references)!=3:raise ValueError("Secondary preview needs three eligible ranked chunks.")
        bv["reference_context"]=references
        b["request"]["messages"][1]["content"]=json.dumps(bv,ensure_ascii=False,allow_nan=False)
        av=json.loads(a["request"]["messages"][1]["content"])
        evidence_ok=av["measured_evidence"]==bv["measured_evidence"]==rag.base.v1.paired_view(doc)
        common_ok=a["request"]["messages"][0]==b["request"]["messages"][0] and all(
            a["request"][field]==b["request"][field] for field in ("model","options","format","stream"))
        ref_bytes=len(json.dumps(references,ensure_ascii=False).encode())
        message_bytes=sum(len(m["content"].encode()) for m in b["request"]["messages"])
        if not evidence_ok or not common_ok:raise ValueError("Secondary preview changes evidence or contract.")
        if ref_bytes>rag.MAX_REFERENCE_BYTES or message_bytes>rag.MAX_MESSAGE_BYTES:
            raise ValueError("Secondary preview exceeds a guard; do not trim evidence.")
        for condition,prepared in (("A",a),("B",b)):
            prepared["provenance"]["secondary_preview"]={"top_k":3,"profile_predeclared_before_embeddings":True,
                  "preview_implementation_after_retrieval":True,"pilot_selected":False}
            if condition=="B":
                prepared["provenance"].update({"prompt_sha256":rag.sha(prepared["request"]["messages"]),
                    "retrieved_chunk_ids":[r["chunk_id"] for r in references],"message_content_utf8_bytes":message_bytes,
                    "reference_utf8_bytes":ref_bytes,
                    "retrieval_receipt_sha256":None,
                    "primary_rank_receipt_sha256":rag.sha(receipt)})
            result.append({"case_id":case["case_id"],"condition":condition,"prepared":prepared})
        integrity.append({"case_id":case["case_id"],"same_contract":common_ok,"same_complete_paired_evidence":evidence_ok,
                          "primary_B_bytes":primary[(case["case_id"],"B")]["provenance"]["message_content_utf8_bytes"],
                          "secondary_B_bytes":message_bytes,"renderer_truncation":False})
    return result,integrity


def build_preview():
    if PREVIEW.exists() or (RAW/"secondary-top3-requests.json").exists():
        raise ValueError("Preview already exists; retain it rather than overwrite.")
    rows,integrity=secondary_requests()
    preparation.write_new(RAW/"secondary-top3-requests.json",rows)
    preparation.write_new(OUT/"secondary-top3-integrity.json",integrity)
    PREVIEW.mkdir(parents=True)
    fixtures=preparation.read(RAW/"view-fixtures.json")
    primary={(r["case_id"],r["condition"]):r["prepared"] for r in preparation.read(RAW/"prepared-requests.json")}
    secondary={(r["case_id"],r["condition"]):r["prepared"] for r in rows}
    summary=preparation.read(OUT/"retrieval-summary.json")
    lines=["# Pratinjau request Qwen v5 rev2", "", "Ini payload yang disiapkan, belum dikirim ke Qwen. Review isi sebelumnya berbantuan AI; adopsi peneliti belum tercatat.", "",
           "A dan B memakai system prompt, schema, opsi dan paired evidence yang sama. B menerima referensi tambahan. Top-3 adalah pratinjau sekunder yang sudah direncanakan, belum pilihan pilot.", "",
           "| Teknik | Payload A | Payload B top-2 | Payload B top-3 | Topik inti tertinggal pada top-2 |", "| --- | --- | --- | --- | --- |"]
    for case in fixtures:
        if case["shape"]!="complete":continue
        cid=case["case_id"]
        names=[]
        for label,payload in (("A",primary[(cid,"A")]),("B-top2",primary[(cid,"B")]),("B-top3",secondary[(cid,"B")])):
            name=f"{cid}.{label}.request.json";preparation.write_new(PREVIEW/name,payload["request"]);names.append(name)
        query=next(q for q in summary["request_queries"] if json.loads(q["query"])["technique"]==case["input"]["technique"])
        lines.append(f"| {case['input']['technique']} | [A]({names[0]}) | [B top-2]({names[1]}) | [B top-3]({names[2]}) | {', '.join(query['missing_topics_at_2'])} |")
    lines += ["", "Periksa messages[0].content, messages[1].content, format dan options pada file JSON. Isi user message adalah JSON dengan measured_evidence terlebih dahulu, lalu reference_context.", "",
              "Semua sembilan pasangan probe mempertahankan paired evidence lengkap pada kedua profil. Probe hanya memeriksa bentuk input, bukan holdout atau evaluasi keputusan model.", "",
              "Top-2 mencakup satu dari dua topik teknik yang diwajibkan rubrik sementara pada setiap query utama. Top-3 mencakup keduanya, tetapi berisi seluruh tiga chunk yang eligible untuk teknik itu. Angka ini bukan precision retrieval independen.", "",
              "Guard byte tidak memotong bukti atau chunk. Jumlah token tepat dan truncation di runtime Qwen belum diperiksa; keduanya merupakan preflight sebelum pilot chat.", ""]
    with (PREVIEW/"request-preview.md").open("x",encoding="utf-8",newline="\n") as stream:stream.write("\n".join(lines))
    manifest={"scope":"secondary-profile-preview-not-pilot-selection","source_sha256":preparation.digest(Path(__file__)),
        "primary_readiness_manifest_sha256":preparation.digest(OUT/"readiness-manifest.json"),
        "secondary_requests_sha256":preparation.digest(RAW/"secondary-top3-requests.json"),
        "secondary_integrity_sha256":preparation.digest(OUT/"secondary-top3-integrity.json"),
        "preview_sha256":{p.name:preparation.digest(p) for p in PREVIEW.iterdir() if p.is_file()},"chat_calls":0}
    preparation.write_new(OUT/"preview-manifest.json",manifest)
    print(json.dumps({"preview_files":len(manifest["preview_sha256"]),"secondary_request_pairs":len(integrity),
                      "all_evidence_preserved":all(r["same_complete_paired_evidence"] for r in integrity),"chat_calls":0}))


def verify():
    rows,integrity=secondary_requests()
    if rows!=preparation.read(RAW/"secondary-top3-requests.json") or integrity!=preparation.read(OUT/"secondary-top3-integrity.json"):
        raise ValueError("Saved secondary preview differs.")
    manifest=preparation.read(OUT/"preview-manifest.json")
    if manifest["source_sha256"]!=preparation.digest(Path(__file__)):raise ValueError("Preview inspector changed.")
    for name,expected in manifest["preview_sha256"].items():
        if preparation.digest(PREVIEW/name)!=expected:raise ValueError("Public request preview changed.")
    print(json.dumps({"status":"saved-primary-and-secondary-requests-reproduced","pairs_per_profile":len(integrity),"chat_calls":0}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--write",action="store_true")
    args=parser.parse_args()
    build_preview() if args.write else verify()
