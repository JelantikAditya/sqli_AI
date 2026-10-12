"""Verify real input coverage boundaries, session isolation and evidence sanitization."""

import base64
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from export_zap_inputs import extract_inventory
from parse_zap_report import normalize_report
from rag_pipeline import injection_point_context, load_catalog
from experiment_protocol import load_protocol, experiment_matrix
from generate_candidate_batch import build_messages

LOGOUT = '<a href="../../login.php?logout">Logout</a>'


def entry(path, body, *, session="private-session", method="GET", post=None):
    request = {"url": "http://dvwa" + path, "method": method,
               "headers": [{"name": "Cookie", "value": f"PHPSESSID={session}; secret=private-cookie"}]}
    if post is not None:
        request["postData"] = {"mimeType": "application/x-www-form-urlencoded", "text": post}
    return {"request": request, "response": {"status": 200, "content": {"text": body}}}


def har_for(level):
    security = LOGOUT + f'<option value="{level}" selected="selected">{level}</option>'
    paths = ["/vulnerabilities/sqli/", "/vulnerabilities/sqli_blind/"]
    method = "POST" if level in {"medium", "high"} else "GET"
    if level == "high":
        paths = ["/vulnerabilities/sqli/session-input.php", "/vulnerabilities/sqli_blind/cookie-input.php"]
    fields = '<input name="id" value="private-value"><input name="Submit" value="Submit">'
    if level == "impossible":
        fields += '<input name="user_token" value="private-token">'
    return {"log": {"creator": {"name": "ZAP", "version": "fixture"}, "entries": [entry("/security.php", security)] +
            [entry(path, (LOGOUT if level != "high" else "") + f'<form method="{method}" action="">{fields}</form>private-record') for path in paths]}}


class ZapInputInventoryTests(unittest.TestCase):
    def inventory(self, level="low", har=None):
        return extract_inventory(har or har_for(level), level, "a" * 64)

    def test_forms_without_alerts_cover_all_twelve_scenarios_and_schema(self):
        seen = set()
        inv_schema = json.loads((ROOT / "schemas/zap-input-inventory.schema.json").read_text())
        schema = json.loads((ROOT / "schemas/zap-normalized-run.schema.json").read_text())
        registry = Registry().with_resource("zap-input-inventory.schema.json", Resource.from_contents(inv_schema))
        for level in ("low", "medium", "high", "impossible"):
            with self.subTest(level=level):
                inv = self.inventory(level)
                self.assertEqual(inv["missing_scenario_ids"], [])
                self.assertEqual(len(inv["candidate_injection_points"]), 2)
                seen.update(inv["covered_scenario_ids"])
                Draft202012Validator(inv_schema).validate(inv)
                normalized = normalize_report({"site": []}, "same-run.json", level, "passive", "unknown", inv)
                Draft202012Validator(schema, registry=registry).validate(normalized)
                self.assertEqual(normalized["summary"]["alert_instance_count"], 0)
                self.assertEqual(normalized["summary"]["verified_injection_point_count"], 2)
        self.assertEqual(seen, {f"S{i}" for i in range(1, 13)})

    def test_values_cookies_page_text_and_external_form_never_enter_inventory(self):
        har = har_for("low")
        har["log"]["entries"][1]["response"]["content"]["text"] += '<form method="POST" action="http://external.invalid/vulnerabilities/sqli/"><input name="id"></form>'
        serialized = json.dumps(self.inventory(har=har))
        for private in ("private-session", "private-cookie", "private-value", "private-token", "private-record", "external.invalid"):
            self.assertNotIn(private, serialized)

    def test_security_evidence_from_another_session_cannot_verify_inputs(self):
        har = har_for("low")
        har["log"]["entries"][0]["request"]["headers"][0]["value"] = "PHPSESSID=another-session"
        inv = self.inventory(har=har)
        self.assertEqual(inv["candidate_injection_points"], [])
        self.assertEqual(inv["missing_scenario_ids"], ["S1", "S2", "S3"])

    def test_changed_security_cookie_cannot_reuse_previous_level_evidence(self):
        har = har_for("low")
        for e in har["log"]["entries"][1:]:
            e["request"]["headers"][0]["value"] += "; security=high"
        self.assertEqual(self.inventory(har=har)["candidate_injection_points"], [])

    def test_missing_login_level_or_conflicting_level_rejects_coordinates(self):
        for change in ("login", "level", "conflict", "no-cookie"):
            har = har_for("low")
            if change == "login":
                for e in har["log"]["entries"]:
                    e["response"]["content"]["text"] = e["response"]["content"]["text"].replace(LOGOUT, "")
            elif change == "level":
                har["log"]["entries"][0]["response"]["content"]["text"] = LOGOUT
            elif change == "conflict":
                har["log"]["entries"].append(entry("/security.php", LOGOUT + '<option value="high" selected="selected">High</option>'))
            else:
                for e in har["log"]["entries"]:
                    e["request"]["headers"] = []
            self.assertEqual(self.inventory(har=har)["candidate_injection_points"], [], change)

    def test_request_parameter_and_base64_response_are_supported(self):
        har = har_for("medium")
        e = entry("/vulnerabilities/sqli/", LOGOUT, method="POST", post="id=private-value&user_token=private-token")
        e["response"]["content"] = {"encoding": "base64", "text": base64.b64encode(LOGOUT.encode()).decode()}
        har["log"]["entries"].append(e)
        inv = self.inventory("medium", har)
        point = next(p for p in inv["candidate_injection_points"] if p["path"] == "/vulnerabilities/sqli/")
        self.assertEqual(point["evidence_kinds"], ["request-parameter", "response-form"])
        self.assertNotIn("private-value", json.dumps(inv))

    def test_wrong_method_or_external_request_does_not_manufacture_coverage(self):
        har = har_for("low")
        for e in har["log"]["entries"][1:]:
            e["response"]["content"]["text"] = LOGOUT + '<form method="POST"><input name="id"></form>'
        self.assertEqual(self.inventory(har=har)["candidate_injection_points"], [])
        har = har_for("low")
        for e in har["log"]["entries"]:
            e["request"]["url"] = e["request"]["url"].replace("http://dvwa", "http://external.invalid")
        self.assertEqual(self.inventory(har=har)["candidate_injection_points"], [])

    def test_browser_har_cannot_claim_zap_provenance(self):
        har = har_for("low")
        har["log"]["creator"]["name"] = "Browser"
        with self.assertRaisesRegex(ValueError, "exported by ZAP"):
            self.inventory(har=har)

    def test_legacy_alert_report_is_still_supported(self):
        schema = json.loads((ROOT / "schemas/zap-normalized-run.schema.json").read_text())
        legacy = normalize_report({"site": []}, "legacy.json", "low", "passive", "verified")
        Draft202012Validator(schema).validate(legacy)
        self.assertEqual(legacy["schema_version"], "1.0.0")

    def test_actual_logout_php_link_is_recognized(self):
        har = har_for("low")
        for e in har["log"]["entries"]:
            e["response"]["content"]["text"] = e["response"]["content"]["text"].replace(LOGOUT, '<a href="logout.php">Logout</a>')
        self.assertEqual(self.inventory(har=har)["missing_scenario_ids"], [])

    def test_protocol_matrix_pairs_seeds_and_has_positive_only_seclists(self):
        matrix = experiment_matrix(load_protocol())
        self.assertEqual(len(matrix), 99)
        for row in matrix:
            if row["condition_id"] == "C":
                self.assertLessEqual(int(row["scenario_id"][1:]), 9)
        a = [(r["scenario_id"], r["replicate"], r["seed"]) for r in matrix if r["condition_id"] == "A"]
        b = [(r["scenario_id"], r["replicate"], r["seed"]) for r in matrix if r["condition_id"] == "B"]
        self.assertEqual(a, b)

    def test_protocol_rejects_biased_units_stop_policy_and_premature_freeze(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temp:
            path = Path(temp) / "protocol.json"
            for change in ("stop", "seed", "freeze", "unit", "temperature", "aggregation", "stddev", "vote", "incomplete", "runtime"):
                p = copy.deepcopy(load_protocol())
                if change == "stop":
                    p["generation"]["stop_on_success"] = True
                elif change == "seed":
                    p["replicate_seeds"] = [42, 42, 42]
                elif change == "freeze":
                    p["status"] = "frozen"
                elif change == "unit":
                    p["metrics"]["fpr_unit"] = "http-request"
                elif change == "temperature":
                    p["generation"]["temperature"] = float("inf")
                elif change == "aggregation":
                    p["metrics"]["aggregation"] = "pooled-runs"
                elif change == "stddev":
                    p["metrics"]["stddev_ddof"] = 0
                elif change == "vote":
                    p["metrics"]["cross_run_success_vote"] = "all-three"
                elif change == "runtime":
                    p["runtime_recovery"]["automatic_retries"] = 1
                else:
                    p["metrics"]["primary_summary_requires_complete_replicates"] = False
                path.write_text(json.dumps(p))
                with self.assertRaises(ValueError, msg=change):
                    load_protocol(path)

    def test_generator_prompt_does_not_change_with_evaluator_labels(self):
        scenario = load_catalog()["scenarios"][0]
        changed = {**scenario, "scenario_id": "S10", "security_level": "impossible", "ground_truth": "negative"}
        self.assertEqual(build_messages(scenario, 1), build_messages(changed, 1))
        prompt = json.dumps(build_messages(scenario, 1))
        self.assertNotIn('S1', prompt)
        self.assertNotIn('ground_truth', prompt)
        self.assertNotIn('impossible', prompt)

    def test_verified_discovery_gate_rejects_catalog_and_alert_only_evidence(self):
        scenario = load_catalog()["scenarios"][0]
        with self.assertRaises(ValueError):
            injection_point_context(scenario, require_verified=True)
        inv = self.inventory()
        normalized = normalize_report({"site": []}, "same-run.json", "low", "passive", "unknown", inv)
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temp:
            path = Path(temp) / "normalized.json"
            path.write_text(json.dumps(normalized))
            point = injection_point_context(scenario, path, require_verified=True)
            self.assertEqual(point["verification_status"], "verified")
            normalized["candidate_injection_points"][0]["verification_status"] = "unverified"
            path.write_text(json.dumps(normalized))
            with self.assertRaises(ValueError):
                injection_point_context(scenario, path, require_verified=True)


if __name__ == "__main__":
    unittest.main()
