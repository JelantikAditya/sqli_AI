"""Exercise frozen diagnostic functions offline, with no client, model or index access."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/processed/analysis-corpus-v5-rev1-20261020/contract-semantics.json"


def isolated_symbols(path, names, namespace):
    """Compile the actual pinned definitions; do not import module startup or services."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    nodes = []
    for node in tree.body:
        declared = ([node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else
                    [t.id for t in node.targets if isinstance(t, ast.Name)] if isinstance(node, ast.Assign) else [])
        if set(declared) & set(names):
            nodes.append(node)
    if len(nodes) != len(names):
        raise ValueError("Pinned function/constant locator does not resolve.")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    isolated = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(isolated, str(path), "exec"), namespace)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    class BaselineFailure(Exception):
        pass

    def unexpected(*args, **kwargs):
        raise AssertionError("Execution advanced beyond the expected baseline gate.")

    env = {"re": re, "LocalRuntimeFailure": BaselineFailure,
           "require_active_session_response": lambda response: None,
           "emit_payload_record": unexpected}
    executor_hash = isolated_symbols(ROOT / "dvwa/validation_loop.py",
                                    ("ERROR_PATTERNS", "sql_error_markers", "execute_candidate"), env)
    rule_env = {}
    analysis_hash = isolated_symbols(ROOT / "dvwa/analyze_response.py", ("positive_evidence_groups",), rule_env)
    matcher = env["sql_error_markers"]
    syntax = "mysql_syntax_error"
    xpath = "mysql_xpath_error"
    markers = matcher("you have an error in your SQL syntax; XPATH syntax error")
    assert markers == sorted([syntax, xpath])
    assert matcher("Application failure, HTTP 500") == []

    def document(baseline, candidate, valid=True):
        return {"technique": "error-based", "runtime_status": "valid" if valid else "invalid",
                "baseline_valid": valid, "observations": [
                    {"observation_id": "obs-001", "trial": 1, "role": "baseline", "diagnostics": baseline},
                    {"observation_id": "obs-002", "trial": 1, "role": "candidate", "diagnostics": candidate}]}

    # These are isolated rule probes, not complete three-trial model cases or live runs.
    rule = rule_env["positive_evidence_groups"]
    checks = []
    for name, doc, expected in [
        ("empty-baseline-new-identifier", document([], [syntax]), True),
        ("same-identifier-not-new", document([syntax], [syntax]), False),
        ("additional-identifier-at-rule-layer-only", document([syntax], [syntax, xpath]), True),
        ("invalid-baseline-gates-additional-identifier", document([syntax], [syntax, xpath], False), False),
    ]:
        actual = bool(rule(doc))
        assert actual is expected, name
        checks.append({"case": name, "observed_indicator_group": actual, "expected": expected})

    class OfflineClient:
        def __init__(self):
            self.submissions = []

        def verify_session_level(self, level):
            return None

        def submit_probe(self, scenario, payload):
            self.submissions.append(payload)
            return {"body": "First name: placeholder; you have an error in your SQL syntax", "status": 200}

    client = OfflineClient()
    try:
        env["execute_candidate"](client, None, "offline", {"probe_kind": "single_error", "security_level": "low"},
                                 {"payload": "unused"}, 1, 1500)
    except BaselineFailure as failure:
        assert str(failure) == "baseline_invalid"
        assert client.submissions == ["1"]
    else:
        raise AssertionError("Executor accepted a diagnostic-bearing baseline.")

    return {
        "verification_id": "analysis-v5-rev1-diagnostic-semantics",
        "executor_sha256": executor_hash, "frozen_analysis_sha256": analysis_hash,
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "method": "isolated-actual-function-definitions-with-offline-stubs; no module imports or network",
        "matcher_returns_identifier_array": True, "generic_http_error_is_not_diagnostic": True,
        "new_diagnostic_rule": "bool(set(candidate.diagnostics) - set(baseline.diagnostics))",
        "rule_probes": checks, "live_executor_rejects_diagnostic_baseline": True,
        "offline_candidate_submissions_after_invalid_baseline": 0,
        "scope_limit": "Rule-layer probe with nonempty baseline and valid flag is artificial; live executor rejects that baseline first.",
        "does_not_measure": ["model accuracy", "FPR", "PSR", "retrieval quality"],
        "dvwa_requests": 0, "model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = verify()
    if args.write:
        with OUT.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    else:
        assert report == json.loads(OUT.read_text(encoding="utf-8")), "Recorded verification changed."
    print(json.dumps({"rule_probes_passed": len(report["rule_probes"]),
                      "executor_baseline_gate_verified": True, "model_calls": 0, "dvwa_requests": 0}))


if __name__ == "__main__":
    main()
