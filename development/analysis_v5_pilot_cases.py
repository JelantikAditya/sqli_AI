"""AI-authored synthetic contract cases, not captured HTTP traffic or independent gold."""

from __future__ import annotations

import hashlib
import itertools
import random
from decimal import Decimal

import analysis_rag_v5 as rag

SEED = 20261020
PROFILES = ("A", "B2", "B3")


def eligible(document):
    rag.base.frozen.validate_input(document)
    return document["runtime_status"] == "valid" and document["baseline_valid"]


def expected_trials(document):
    """Independent specification using the exact displayed decimal delta, outside prompts."""
    if not eligible(document):
        return []
    result = []
    for trial in sorted({o["trial"] for o in document["observations"]}):
        group = {o["role"]: o for o in document["observations"] if o["trial"] == trial}
        def valid(row):
            return not row["diagnostics"] and (row["http_status"] == 200 or (
                row["http_status"] == 404 and row["content_markers"] == ["user_id_missing"]))
        if document["technique"] == "error-based":
            rows = [group[r] for r in ("baseline", "candidate")]
            positive = bool(set(rows[1]["diagnostics"]) - set(rows[0]["diagnostics"]))
        elif document["technique"] == "boolean-based blind":
            rows = [group[r] for r in ("true_condition", "false_condition")]
            positive = (all(valid(r) for r in rows) and rows[0]["content_markers"] == ["user_id_exists"]
                        and rows[1]["content_markers"] == ["user_id_missing"])
        else:
            rows = [group[r] for r in ("candidate", "no_delay_control")]
            markers = rows[0]["content_markers"]
            positive = (all(valid(r) for r in rows) and markers == rows[1]["content_markers"]
                        and markers in (["user_id_exists"], ["user_id_missing"])
                        and Decimal(str(rows[0]["elapsed_ms"])) - Decimal(str(rows[1]["elapsed_ms"]))
                        >= Decimal(str(document["time_threshold_ms"])))
        result.append({"trial": trial, "outcome": "positive" if positive else "negative",
                       "evidence_refs": [r["observation_id"] for r in rows]})
    return result


def reference(document):
    trials = expected_trials(document)
    if not eligible(document):
        return {"decision": None, "trial_assessments": [], "gate": "input_invalid"}
    decision = "inconclusive"
    if [r["trial"] for r in trials] == [1, 2, 3]:
        decision = {0: "negative", 3: "positive"}.get(sum(r["outcome"] == "positive" for r in trials), "inconclusive")
    return {"decision": decision, "trial_assessments": trials, "gate": "eligible"}


def make_document(technique, variants, trial_numbers=(1, 2, 3)):
    path = "/vulnerabilities/sqli/" if technique == "error-based" else "/vulnerabilities/sqli_blind/"
    document = {"schema_version": "1.0.0", "technique": technique,
        "injection_point": {"method": "GET", "input_path": path, "result_path": path, "parameter": "id"},
        "runtime_status": "valid", "baseline_valid": True, "time_threshold_ms": 1500, "observations": []}
    for trial, variant in zip(trial_numbers, variants):
        roles = ("baseline", "candidate") if technique == "error-based" else (
            ("baseline", "true_condition", "false_condition") if technique == "boolean-based blind" else
            ("baseline", "candidate", "no_delay_control"))
        for role in roles:
            oid = f"obs-{len(document['observations']) + 1:03d}"
            row = {"observation_id": oid, "trial": trial, "role": role, "http_status": 200,
                "elapsed_ms": 40 + trial, "response_sha256": hashlib.sha256(f"synthetic:{trial}:{role}:{variant}".encode()).hexdigest(),
                "diagnostics": [], "content_markers": ["benign_record"] if technique == "error-based" else ["user_id_exists"]}
            if role != "baseline":
                if technique == "error-based":
                    if variant in ("syntax", "xpath", "column", "multi"):
                        codes = {"syntax": ["mysql_syntax_error"], "xpath": ["mysql_xpath_error"],
                                 "column": ["mysql_unknown_column"], "multi": ["mysql_syntax_error", "mysql_xpath_error"]}
                        row.update(diagnostics=codes[variant], http_status=500 if trial != 2 else 200)
                    else:
                        row.update(http_status={"generic500": 500, "notfound": 404, "benign": 200,
                                                "redirect": 302}[variant], content_markers=[])
                elif technique == "boolean-based blind":
                    marker = "user_id_exists" if role == "true_condition" else "user_id_missing"
                    if variant == "reversed":
                        marker = "user_id_missing" if role == "true_condition" else "user_id_exists"
                    if variant == "same":
                        marker = "user_id_exists"
                    row["content_markers"] = [marker]
                    if marker == "user_id_missing" and variant != "positive200":
                        row["http_status"] = 404
                    if variant == "diagnostic" and role == "false_condition":
                        row["diagnostics"] = ["mysql_unknown_column"]
                    if variant == "badstatus" and role == "true_condition":
                        row["http_status"] = 500
                else:
                    control_ms = 82 + trial * 23
                    delta = {"boundary": 1500, "above": 1800, "missing": 1600,
                             "far-above": 2700, "just-below": 1499.8, "slow-control": 120,
                             "unmatched": 1900, "diagnostic": 1800, "negative-delta": -20}[variant]
                    if variant == "slow-control":
                        control_ms = 2400 + trial
                    row["elapsed_ms"] = float(Decimal(str(control_ms)) + Decimal(str(delta))) if role == "candidate" else control_ms
                    if variant == "missing":
                        row.update(content_markers=["user_id_missing"], http_status=404)
                    if variant == "unmatched" and role == "no_delay_control":
                        row.update(content_markers=["user_id_missing"], http_status=404)
                    if variant == "diagnostic" and role == "no_delay_control":
                        row["diagnostics"] = ["mysql_syntax_error"]
            document["observations"].append(row)
    rag.base.frozen.validate_input(document)
    return document


def build_cases():
    cases, labels = [], []
    specifications = {
        "error-based": [
            ("positive", ["syntax"] * 3, "One newly supplied syntax identifier in every trial"),
            ("positive", ["xpath"] * 3, "New XPath diagnostic with status variation"),
            ("positive", ["column"] * 3, "New unknown-column diagnostic"),
            ("positive", ["multi", "syntax", "xpath"], "Different nonempty new diagnostic sets"),
            ("negative", ["generic500"] * 3, "HTTP 500 alone has no database diagnostic"),
            ("negative", ["notfound", "benign", "generic500"], "Status differences alone"),
            ("negative", ["redirect", "redirect", "benign"], "Redirect without diagnostic"),
            ("negative", ["benign", "generic500", "benign"], "Candidate response change without diagnostic"),
            ("inconclusive", ["syntax", "generic500", "benign"], "One positive trial"),
            ("inconclusive", ["xpath", "generic500", "column"], "Two positive trials"),
            ("inconclusive", ["multi", "column"], "Only trials 1 and 3", (1, 3)),
            ("inconclusive", ["benign", "generic500"], "Only trials 1 and 2, both negative", (1, 2)),
        ],
        "boolean-based blind": [
            ("positive", ["positive200"] * 3, "Opposed markers, HTTP 200 on both sides"),
            ("positive", ["positive404"] * 3, "Missing marker with HTTP 404"),
            ("positive", ["positive200", "positive404", "positive200"], "Stable direction despite status variation"),
            ("positive", ["positive404", "positive200", "positive404"], "Stable markers across alternate status pattern"),
            ("negative", ["reversed"] * 3, "Opposed markers in the wrong direction"),
            ("negative", ["same"] * 3, "Both sides have the same marker"),
            ("negative", ["diagnostic"] * 3, "Database diagnostic invalidates opposed-marker indicator"),
            ("negative", ["badstatus"] * 3, "Candidate comparison status invalid, baseline remains valid"),
            ("inconclusive", ["positive404", "same", "reversed"], "One valid opposed pair"),
            ("inconclusive", ["positive200", "badstatus", "positive404"], "Two valid opposed pairs"),
            ("inconclusive", ["positive404", "positive200"], "Only trials 1 and 3", (1, 3)),
            ("inconclusive", ["same", "reversed"], "Incomplete negative pairs", (1, 2)),
        ],
        "time-based blind": [
            ("positive", ["boundary"] * 3, "Exact inclusive threshold with matched controls"),
            ("positive", ["above"] * 3, "Above-threshold matched exists markers"),
            ("positive", ["missing"] * 3, "Matched missing markers with valid HTTP 404"),
            ("positive", ["boundary", "far-above", "above"], "Each trial independently reaches threshold"),
            ("negative", ["just-below"] * 3, "1499.8 ms is below 1500 ms without rounding"),
            ("negative", ["slow-control"] * 3, "Slow absolute responses with small matched deltas"),
            ("negative", ["unmatched"] * 3, "Large delay with mismatched control marker"),
            ("negative", ["diagnostic", "negative-delta", "diagnostic"], "Diagnostic controls and negative signed delta"),
            ("inconclusive", ["above", "just-below", "unmatched"], "One qualifying matched delay"),
            ("inconclusive", ["missing", "slow-control", "boundary"], "Two qualifying delays"),
            ("inconclusive", ["above", "boundary"], "Only trials 1 and 3", (1, 3)),
            ("inconclusive", ["slow-control", "just-below"], "Incomplete negative timings", (1, 2)),
        ],
    }
    for technique, specs in specifications.items():
        for decision, variants, rationale, *trials in specs:
            doc = make_document(technique, variants, trials[0] if trials else (1, 2, 3))
            cid = f"pilot-{len(cases) + 1:03d}"
            truth = reference(doc)
            if truth["decision"] != decision:
                raise ValueError("Independent case specification and rule implementation disagree.")
            cases.append({"case_id": cid, "input": doc})
            labels.append({"case_id": cid, "technique": technique, **truth, "rationale": rationale})
    for technique in rag.TECHNIQUES:
        for gate in ("runtime-invalid", "baseline-invalid"):
            positive = {"error-based": "syntax", "boolean-based blind": "positive404", "time-based blind": "above"}[technique]
            doc = make_document(technique, [positive] * 3)
            if gate == "runtime-invalid":
                doc.update(runtime_status="invalid", runtime_failure_code="network_error", observations=[])
            else:
                doc.update(baseline_valid=False, runtime_failure_code="baseline_invalid")
                for observation in doc["observations"]:
                    if observation["role"] == "baseline":
                        observation["diagnostics"] = ["mysql_syntax_error"]
            cid = f"pilot-{len(cases) + 1:03d}"
            cases.append({"case_id": cid, "input": doc})
            labels.append({"case_id": cid, "technique": technique, **reference(doc), "rationale": gate})
    return cases, {"origin": "AI-authored synthetic contract labels", "researcher_review": "pending",
                   "researcher_adoption": "not-recorded", "independent_holdout": False, "cases": labels}


def schedule(cases):
    """All six orders twice per eligible technique, once across six gate cases."""
    orders = list(itertools.permutations(PROFILES))
    rng = random.Random(SEED)
    assignments = []
    for technique in rag.TECHNIQUES:
        group = [c for c in cases if eligible(c["input"]) and c["input"]["technique"] == technique]
        if len(group) != 12:
            raise ValueError("The balanced schedule requires twelve eligible cases per technique.")
        rng.shuffle(group)
        order_group = orders * 2
        rng.shuffle(order_group)
        assignments.extend((case, order) for case, order in zip(group, order_group))
    invalid = [c for c in cases if not eligible(c["input"])]
    if len(invalid) != 6:
        raise ValueError("Expected six invalid gate checks.")
    rng.shuffle(invalid)
    assignments.extend(zip(invalid, orders))
    rng.shuffle(assignments)
    return [{"slot_id": f"slot-{i + 1:03d}", "case_id": case["case_id"], "profile": profile,
             "position_within_case": position + 1}
            for i, (case, order, position, profile) in enumerate(
                (case, order, position, profile) for case, order in assignments
                for position, profile in enumerate(order))]
