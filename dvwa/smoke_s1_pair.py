"""Verify the S1 web form and execute one local smoke replicate per LLM condition."""

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
from rag_pipeline import injection_point_context

from validation_loop import (
    ROOT, DvwaClient, execute_candidate, load_json, load_local_env_file,
    require_local_target, selected_security_level, validate_candidates,
)


class InputForms(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self.current = {
                "method": attributes.get("method", "GET").upper(),
                "action": attributes.get("action", ""), "fields": [],
            }
            self.forms.append(self.current)
        elif tag in {"input", "select", "textarea"} and self.current is not None:
            if attributes.get("name"):
                self.current["fields"].append(attributes["name"])

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class EvidenceClient(DvwaClient):
    def __init__(self, origin, timeout):
        super().__init__(origin, timeout)
        self.receipts = []
        self.condition = None

    def submit_probe(self, scenario, payload):
        response = super().submit_probe(scenario, payload)
        role = "candidate" if any(
            item["rag_mode"] == self.condition for item in self.receipts
        ) else "baseline"
        benign_record = "first name:" in response["body"].lower()
        if role == "baseline" and (response["status"] != 200 or not benign_record):
            raise RuntimeError("S1 benign baseline did not return the expected record.")
        # Keep only fixed diagnostic phrases, never surrounding SQL or user records.
        phrases = re.findall(
            r"You have an error in your SQL syntax|mysqli_sql_exception|PDOException|"
            r"mysql_fetch_(?:array|assoc|row)", response["body"], re.IGNORECASE,
        )
        self.receipts.append({
            "rag_mode": self.condition,
            "role": role,
            "http_status": response["status"],
            "response_time_ms": response["elapsed_ms"],
            "response_sha256": response["body_sha256"],
            "sql_error_excerpts": sorted(set(phrases)),
            "benign_record_visible": benign_record,
        })
        return response


def verify_generation_audits(pair, audit_paths, scenario, zap_report=None):
    """Cross-check payloads, controls, provenance and RAG isolation before HTTP."""
    audits = {mode: load_json(path) for mode, path in audit_paths.items()}
    points = []
    for mode, audit in audits.items():
        candidate = pair[mode]
        if (audit.get("rag_mode") != mode or audit.get("scenario_id") != "S1"
                or audit.get("provenance") != candidate["provenance"]):
            raise ValueError("Generation audit does not match its candidate batch.")
        messages = audit["messages"]
        prompt_hash = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if prompt_hash != candidate["provenance"].get("prompt_sha256"):
            raise ValueError("Generation prompt hash mismatch.")
        generated = json.loads(audit["response_content"])["candidates"]
        if len(generated) != 1 or generated[0].get("payload") != candidate["payload"]:
            raise ValueError("Batch payload differs from the actual model output.")
        points.append(audit["injection_point"])
    if audits["off"]["generation_options"] != audits["on"]["generation_options"] or points[0] != points[1]:
        raise ValueError("Unequal generation options or injection-point context.")
    off_messages, on_messages = audits["off"]["messages"], audits["on"]["messages"]
    if off_messages[0] != on_messages[0] or not on_messages[1]["content"].startswith(off_messages[1]["content"] + "\n\nUse the following retrieved excerpts"):
        raise ValueError("RAG conditions do not share the same base prompt.")
    if audits["off"].get("retrieval") is not None or not audits["on"].get("retrieval", {}).get("chunks"):
        raise ValueError("RAG context isolation failed.")
    if zap_report is not None:
        actual = injection_point_context(scenario, zap_report, require_verified=True)
        if points[0] != actual:
            raise ValueError("Audit discovery context differs from the verified report.")
    return {"generation_input_source": points[0]["source"], "injection_point": points[0],
            "audit_sha256": {mode: hashlib.sha256(path.read_bytes()).hexdigest() for mode, path in audit_paths.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-batch", type=Path, required=True)
    parser.add_argument("--on-batch", type=Path, required=True)
    parser.add_argument("--off-audit", type=Path)
    parser.add_argument("--on-audit", type=Path)
    parser.add_argument("--zap-report", type=Path)
    parser.add_argument("--confirm-local-dvwa", action="store_true")
    args = parser.parse_args()
    if not args.confirm_local_dvwa:
        raise SystemExit("Confirm the researcher's local DVWA with --confirm-local-dvwa.")
    catalog = load_json(ROOT / "dvwa/experiment_scenarios.json")
    scenario = next(item for item in catalog["scenarios"] if item["scenario_id"] == "S1")
    pair = {}
    for mode, path in (("off", args.off_batch), ("on", args.on_batch)):
        candidates = validate_candidates(load_json(path), scenario, 1)
        if len(candidates) != 1 or candidates[0]["source"] != "LLM" or candidates[0]["rag_mode"] != mode:
            raise ValueError("Use exactly one S1 LLM candidate for each expected condition.")
        pair[mode] = candidates[0]
    controls = ("comparison_id", "model", "prompt_version", "temperature", "seed")
    for key in controls:
        if pair["off"]["provenance"].get(key) is None or (
            pair["off"]["provenance"][key] != pair["on"]["provenance"].get(key)
        ):
            raise ValueError(f"Missing or unequal generation control: {key}")

    generation_evidence = {"generation_input_source": "not-recorded-in-batch"}
    if args.off_audit or args.on_audit or args.zap_report:
        if not args.off_audit or not args.on_audit:
            raise ValueError("Supply both generation audits to verify discovery provenance.")
        generation_evidence = verify_generation_audits(pair, {"off": args.off_audit, "on": args.on_audit}, scenario, args.zap_report)

    credentials = load_local_env_file()
    client = EvidenceClient(catalog["target"]["default_origin"], 15)
    client.login_and_set_level(
        os.environ.get("DVWA_USERNAME") or credentials.get("DVWA_USERNAME") or "admin",
        os.environ.get("DVWA_PASSWORD") or credentials.get("DVWA_PASSWORD") or "password", "low",
    )
    security = client.get_form("/security.php")
    page = client.get_form(scenario["input_path"])
    if selected_security_level(security["body"]) != "low" or "logout" not in page["body"].lower():
        raise RuntimeError("Authenticated Low session was not confirmed.")
    forms = InputForms()
    forms.feed(page["body"])
    matching = []
    for form in forms.forms:
        destination = urljoin(client.origin + scenario["input_path"], form["action"])
        require_local_target(destination)
        if (form["method"] == scenario["method"] and "id" in form["fields"]
                and urlsplit(destination).path == scenario["input_path"]):
            matching.append({"method": form["method"], "path": urlsplit(destination).path,
                             "parameter": "id", "fields": form["fields"]})
    if page["status"] != 200 or not matching:
        raise RuntimeError("The S1 injection form did not match the scenario coordinates.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    directory = ROOT / "results/raw"
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"validation-s1-pair-{run_id}.jsonl"
    evidence_path = directory / f"evidence-s1-pair-{run_id}.json"
    signals = {}
    with log_path.open("x", encoding="utf-8", newline="\n") as output:
        for mode in ("off", "on"):
            client.condition = mode
            signals[mode] = execute_candidate(
                client, output, run_id, scenario, pair[mode], 1,
                catalog["protocol"]["time_signal_threshold_ms"],
            )
    evidence = {
        "schema_version": "1.0.0", "scope": "local integration smoke, not formal FPR/PSR",
        "comparison_id": pair["off"]["provenance"]["comparison_id"], "run_id": run_id,
        "observed_form": matching[0], "observation_source": "authenticated-http-form-smoke",
        "authentication_verified": True, "security_level_verified": "low",
        "replicates_per_condition": 1, "system_signals": signals,
        "response_receipts": client.receipts, "human_validation": "pending",
        "validation_log": log_path.relative_to(ROOT).as_posix(),
        **generation_evidence,
    }
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"log": str(log_path), "evidence": str(evidence_path),
                      "system_signals": signals, "human_validation": "pending"}, indent=2))


if __name__ == "__main__":
    main()
