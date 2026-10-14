"""Run bounded SQLi validation candidates against the local DVWA lab only."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from confirmation_policy import classify_confirmations

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = Path(__file__).with_name("experiment_scenarios.json")
PAYLOAD_SCHEMA_VERSION = "1.0.0"
ERROR_PATTERNS = {
    "mysql_syntax_error": re.compile(r"you have an error in your sql syntax", re.IGNORECASE),
    "mysql_xpath_error": re.compile(r"xpath syntax error", re.IGNORECASE),
    "mysql_unknown_column": re.compile(r"unknown column", re.IGNORECASE),
}
EXISTS_MARKER = "user id exists"
MISSING_MARKER = "user id is missing"


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inputs: dict[str, str] = {}
        self.selected_options: list[str] = []
        self._current_option: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "input":
            name = attributes.get("name")
            value = attributes.get("value") or ""
            if name:
                self.inputs[name] = value
        elif tag.lower() == "option":
            self._current_option = attributes.get("value") or ""
            if "selected" in attributes:
                self.selected_options.append(self._current_option)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "option":
            self._current_option = None


class SetupFormParser(HTMLParser):
    """Collect only form controls needed for DVWA's local setup action."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.current: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "form":
            self.current = {"method": (attributes.get("method") or "GET").upper(),
                            "action": attributes.get("action") or "", "controls": {}}
            self.forms.append(self.current)
        elif tag.lower() == "input" and self.current is not None:
            name = attributes.get("name")
            if name:
                self.current["controls"][name] = {"type": (attributes.get("type") or "text").lower(),
                                                  "value": attributes.get("value") or ""}

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form":
            self.current = None


class LocalRuntimeFailure(RuntimeError):
    """A lab/session/control failure that must not be scored as a payload miss."""

    CODES = {"network_error", "database_reset_failed", "setup_form_invalid", "login_failed",
             "session_invalid", "security_level_mismatch", "probe_form_invalid", "baseline_invalid"}

    def __init__(self, code: str) -> None:
        if code not in self.CODES:
            raise ValueError("Unknown local runtime failure code.")
        self.code = code
        super().__init__(code)


def require_active_session_response(response: dict) -> None:
    """Classify auth expiry as a runtime failure before scoring candidate evidence."""
    body = response.get("body", "").lower()
    if (response.get("status") in {401, 403} or 'name="password"' in body
            or "csrf token is incorrect" in body):
        raise LocalRuntimeFailure("session_invalid")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def require_local_target(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Target URL has an invalid port.") from exc

    if (
        parsed.scheme != "http"
        or host not in allowed_hosts
        or port != 4280
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            "Only the local DVWA instance at http://127.0.0.1:4280 is allowed."
        )


class LocalRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_local_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def form_data(html: str) -> dict[str, str]:
    parser = FormParser()
    parser.feed(html)
    return parser.inputs


def selected_security_level(html: str) -> str | None:
    parser = FormParser()
    parser.feed(html)
    return parser.selected_options[0].lower() if parser.selected_options else None


def load_local_env_file() -> dict[str, str]:
    """Read only DVWA credential keys; never print or log their values."""
    env_path = Path(__file__).with_name(".env")
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in {"DVWA_USERNAME", "DVWA_PASSWORD"}:
            values[key] = value
    return values


class DvwaClient:
    def __init__(self, origin: str, timeout: int) -> None:
        require_local_target(origin)
        self.origin = origin.rstrip("/")
        self.timeout = timeout
        self.database_reset_done = False
        self.http_request_calls = 0
        self.logical_probe_submissions = 0
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(cookie_jar),
            LocalRedirectHandler(),
        )
        self.opener.addheaders = [("User-Agent", "DVWA-TA-validation-loop/1.0")]

    def request(
        self, method: str, path: str, values: dict[str, str] | None = None
    ) -> dict:
        url = self.origin + path
        require_local_target(url)
        data = None
        if values is not None:
            encoded = urllib.parse.urlencode(values).encode("utf-8")
            if method.upper() == "GET":
                separator = "&" if "?" in url else "?"
                url = url + separator + encoded.decode("ascii")
                data = None
            else:
                data = encoded

        request = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers=(
                {"Content-Type": "application/x-www-form-urlencoded"}
                if data is not None
                else {}
            ),
        )
        self.http_request_calls += 1
        started = time.perf_counter()
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            status = error.code
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise LocalRuntimeFailure("network_error") from error

        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "status": status,
            "body": body,
            "elapsed_ms": round(elapsed_ms, 2),
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    def get_form(self, path: str) -> dict:
        return self.request("GET", path)

    def login_and_set_level(
        self, username: str, password: str, security_level: str
    ) -> None:
        login_page = self.get_form("/login.php")
        token = form_data(login_page["body"]).get("user_token")
        if login_page["status"] != 200 or not token:
            raise LocalRuntimeFailure("login_failed")

        login = self.request(
            "POST",
            "/login.php",
            {
                "username": username,
                "password": password,
                "Login": "Login",
                "user_token": token,
            },
        )
        if login["status"] != 200 or "logout" not in login["body"].lower():
            raise LocalRuntimeFailure("login_failed")

        security_page = self.get_form("/security.php")
        token = form_data(security_page["body"]).get("user_token")
        if security_page["status"] != 200 or "logout" not in security_page["body"].lower() or not token:
            raise LocalRuntimeFailure("session_invalid")

        updated = self.request(
            "POST",
            "/security.php",
            {
                "security": security_level,
                "seclev_submit": "Submit",
                "user_token": token,
            },
        )
        selected = selected_security_level(updated["body"])
        if updated["status"] != 200 or "logout" not in updated["body"].lower():
            raise LocalRuntimeFailure("session_invalid")
        if selected != security_level:
            raise LocalRuntimeFailure("security_level_mismatch")

    def reset_database(self) -> dict:
        """Reset the DVWA sample database through its own CSRF-protected form."""
        if self.database_reset_done:
            raise LocalRuntimeFailure("database_reset_failed")
        page = self.get_form("/setup.php")
        if page["status"] != 200:
            raise LocalRuntimeFailure("setup_form_invalid")
        parser = SetupFormParser()
        parser.feed(page["body"])
        matches = []
        for form in parser.forms:
            submit = form["controls"].get("create_db")
            token = form["controls"].get("user_token")
            action_url = urllib.parse.urljoin(self.origin + "/setup.php", form["action"])
            try:
                require_local_target(action_url)
            except ValueError as exc:
                raise LocalRuntimeFailure("setup_form_invalid") from exc
            parsed = urllib.parse.urlsplit(action_url)
            if (form["method"] == "POST" and parsed.path == "/setup.php" and not parsed.query
                    and submit and submit["type"] == "submit"
                    and submit["value"].strip().lower() == "create / reset database"
                    and token and token["value"]):
                matches.append((submit["value"], token["value"]))
        if len(matches) != 1:
            raise LocalRuntimeFailure("setup_form_invalid")
        button_value, token_value = matches[0]
        response = self.request("POST", "/setup.php", {"create_db": button_value,
                                                         "user_token": token_value})
        body = response["body"]
        if (response["status"] != 200 or not re.search(r"database has been created\.", body, re.I)
                or not re.search(r"setup successful", body, re.I)):
            raise LocalRuntimeFailure("database_reset_failed")
        self.database_reset_done = True
        return {"status": response["status"], "response_sha256": response["body_sha256"],
                "success_markers_verified": True, "endpoint": "/setup.php"}

    def verify_session_level(self, expected_level: str) -> dict:
        response = self.get_form("/security.php")
        body = response["body"].lower()
        if (response["status"] in {401, 403} or response["status"] != 200
                or "logout" not in body or re.search(r"\bname\s*=\s*['\"]password['\"]", body)):
            raise LocalRuntimeFailure("session_invalid")
        actual_level = selected_security_level(response["body"])
        if actual_level != expected_level:
            raise LocalRuntimeFailure("security_level_mismatch")
        return {"security_level": actual_level, "response_sha256": response["body_sha256"]}

    def submit_probe(self, scenario: dict, payload: str) -> dict:
        """Submit one logical payload and return only the final response metadata."""
        self.logical_probe_submissions += 1
        method = scenario["method"]
        input_path = scenario["input_path"]
        result_path = scenario["result_path"]

        # Fetch a fresh form token outside the measured injection request.
        form = self.get_form(input_path)
        if form["status"] in {401, 403} or re.search(r"\bname\s*=\s*['\"]password['\"]", form["body"], re.I):
            raise LocalRuntimeFailure("session_invalid")
        if form["status"] != 200:
            raise LocalRuntimeFailure("probe_form_invalid")
        token = form_data(form["body"]).get("user_token")
        if scenario["security_level"] == "impossible" and not token:
            raise LocalRuntimeFailure("probe_form_invalid")

        values = {scenario["parameter"]: payload}
        if token:
            values["user_token"] = token
        if input_path == result_path:
            values["Submit"] = "Submit"

        started = time.perf_counter()
        submitted = self.request(method, input_path, values)
        statuses = [submitted["status"]]
        final = submitted
        if input_path != result_path:
            final = self.request("GET", result_path)
            statuses.append(final["status"])

        if (any(status in {401, 403} for status in statuses)
                or re.search(r"\bname\s*=\s*['\"]password['\"]", final["body"], re.I)):
            raise LocalRuntimeFailure("session_invalid")

        final["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        final["http_statuses"] = statuses
        return final


def sql_error_markers(body: str) -> list[str]:
    return sorted(name for name, pattern in ERROR_PATTERNS.items() if pattern.search(body))


def decide_class(ground_truth: str, detected: bool) -> str:
    if ground_truth == "positive":
        return "TP" if detected else "FN"
    return "FP" if detected else "TN"


def validate_candidates(
    payload_document: dict, scenario: dict, max_candidates: int
) -> list[dict]:
    if payload_document.get("schema_version") != PAYLOAD_SCHEMA_VERSION:
        raise ValueError(f"Payload file must use schema_version {PAYLOAD_SCHEMA_VERSION}.")
    candidates = payload_document.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Payload file must contain a non-empty candidates array.")
    if len(candidates) > max_candidates:
        raise ValueError(
            f"Run has {len(candidates)} candidates; maximum is {max_candidates}."
        )

    candidate_ids: set[str] = set()
    selected: list[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Every candidate must be a JSON object.")
        required = ("candidate_id", "scenario_id", "source", "rag_mode")
        if any(not isinstance(candidate.get(key), str) or not candidate[key] for key in required):
            raise ValueError("Each candidate needs candidate_id, scenario_id, source, and rag_mode.")
        if candidate["candidate_id"] in candidate_ids:
            raise ValueError(f"Duplicate candidate_id: {candidate['candidate_id']}.")
        candidate_ids.add(candidate["candidate_id"])
        if candidate["scenario_id"] != scenario["scenario_id"]:
            raise ValueError("All candidates must match the selected scenario.")
        if candidate["source"] not in {"LLM", "SecLists", "manual"}:
            raise ValueError("source must be LLM, SecLists, or manual.")
        if candidate["source"] == "LLM" and candidate["rag_mode"] not in {"on", "off"}:
            raise ValueError("LLM candidates must specify rag_mode on or off.")
        if candidate["source"] in {"SecLists", "manual"} and candidate["rag_mode"] != "not_applicable":
            raise ValueError("SecLists and manual candidates must use rag_mode not_applicable.")

        if scenario["probe_kind"] == "boolean_pair":
            payloads = (candidate.get("true_payload"), candidate.get("false_payload"))
            if any(not isinstance(value, str) or not value.strip() for value in payloads):
                raise ValueError("Boolean candidates require true_payload and false_payload.")
            if candidate.get("payload") is not None:
                raise ValueError("Boolean candidates must not also define payload.")
        else:
            payload = candidate.get("payload")
            if not isinstance(payload, str) or not payload.strip():
                raise ValueError("Error/time candidates require a non-empty payload.")
            if candidate.get("true_payload") is not None or candidate.get("false_payload") is not None:
                raise ValueError("Only boolean candidates may define true_payload/false_payload.")

        all_payloads = [
            candidate.get("payload"),
            candidate.get("true_payload"),
            candidate.get("false_payload"),
        ]
        if any(isinstance(value, str) and "REPLACE_WITH_" in value for value in all_payloads):
            raise ValueError("Replace the template placeholder before running candidates.")
        selected.append(candidate)

    conditions = {(item["source"], item["rag_mode"]) for item in selected}
    if len(conditions) != 1:
        raise ValueError("Use one payload source and one RAG condition per run.")
    return selected


def emit_payload_record(
    output,
    run_id: str,
    scenario: dict,
    candidate: dict,
    replicate: int,
    role: str,
    payload: str,
    response: dict,
    baseline: dict,
    indicators: list[str],
    confirmation_index: int = 1,
    attempt_id: str = "attempt-1",
    experiment_id: str | None = None,
    condition_id: str | None = None,
) -> None:
    output.write(
        json.dumps(
            {
                "record_type": "payload",
                "run_id": run_id,
                "attempt_id": attempt_id,
                "experiment_id": experiment_id,
                "condition_id": condition_id,
                "candidate_id": candidate["candidate_id"],
                "payload_id": f"{candidate['candidate_id']}-r{replicate}-c{confirmation_index}-{role}",
                "scenario_id": scenario["scenario_id"],
                "replicate": replicate,
                "confirmation_index": confirmation_index,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "security_level": scenario["security_level"],
                "sqli_type": scenario["sqli_type"],
                "endpoint": scenario["input_path"],
                "method": scenario["method"],
                "parameter": scenario["parameter"],
                "payload_source": candidate["source"],
                "rag_mode": candidate["rag_mode"],
                "provenance": candidate.get("provenance", {}),
                "payload_role": role,
                "payload": payload,
                "http_status": response["status"],
                "http_statuses": response.get("http_statuses", [response["status"]]),
                "response_time_ms": response["elapsed_ms"],
                "baseline_time_ms": baseline["elapsed_ms"],
                "delta_time_ms": round(response["elapsed_ms"] - baseline["elapsed_ms"], 2),
                "response_sha256": response["body_sha256"],
                "response_indicators": indicators,
                "human_validation": "pending",
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    output.flush()


def execute_candidate(
    client: DvwaClient,
    output,
    run_id: str,
    scenario: dict,
    candidate: dict,
    replicate: int,
    threshold_ms: float,
    confirmation_index: int = 1,
    attempt_id: str = "attempt-1",
    experiment_id: str | None = None,
    condition_id: str | None = None,
    observation_sink=None,
) -> bool:
    client.verify_session_level(scenario["security_level"])
    baseline = client.submit_probe(scenario, "1")
    require_active_session_response(baseline)
    baseline_body = baseline["body"].lower()
    if (baseline["status"] != 200 or sql_error_markers(baseline["body"])
            or (scenario["probe_kind"] == "single_error" and "first name:" not in baseline_body)
            or (scenario["probe_kind"] != "single_error"
                and EXISTS_MARKER not in baseline_body and MISSING_MARKER not in baseline_body)):
        raise LocalRuntimeFailure("baseline_invalid")
    if observation_sink:
        observation_sink("baseline", baseline, [])
    probe_kind = scenario["probe_kind"]
    evidence: dict = {"probe_kind": probe_kind}
    control = None
    comparison_baseline = baseline

    if probe_kind in {"single_error", "single_time"}:
        response = client.submit_probe(scenario, candidate["payload"])
        require_active_session_response(response)
        if probe_kind == "single_error":
            baseline_errors = set(sql_error_markers(baseline["body"]))
            response_errors = set(sql_error_markers(response["body"]))
            indicators = sorted(response_errors - baseline_errors)
            detected = bool(indicators)
            evidence["new_sql_error_markers"] = indicators
            if observation_sink:
                observation_sink("candidate", response, indicators)
        else:
            control = client.submit_probe(scenario, "1")
            require_active_session_response(control)
            control_body = control["body"].lower()
            if (control["status"] != 200 or sql_error_markers(control["body"])
                    or (EXISTS_MARKER not in control_body and MISSING_MARKER not in control_body)):
                raise LocalRuntimeFailure("baseline_invalid")
            delta = response["elapsed_ms"] - control["elapsed_ms"]
            comparison_baseline = control
            detected = delta >= threshold_ms
            indicators = ["time_delta_over_threshold"] if detected else []
            if observation_sink:
                observation_sink("candidate", response, indicators)
                observation_sink("control", control, [])
            evidence.update(
                {
                    "time_delta_ms": round(delta, 2),
                    "threshold_ms": threshold_ms,
                    "matched_control_time_ms": control["elapsed_ms"],
                }
            )

        if control is not None:
            emit_payload_record(
                output,
                run_id,
                scenario,
                candidate,
                replicate,
                "baseline",
                "1",
                baseline,
                baseline,
                [],
                confirmation_index,
                attempt_id,
                experiment_id,
                condition_id,
            )
        emit_payload_record(
            output,
            run_id,
            scenario,
            candidate,
            replicate,
            "single",
            candidate["payload"],
            response,
            comparison_baseline,
            indicators,
            confirmation_index,
            attempt_id,
            experiment_id,
            condition_id,
        )
        if control is not None:
            emit_payload_record(
                output,
                run_id,
                scenario,
                candidate,
                replicate,
                "no_delay_control",
                "1",
                control,
                baseline,
                [],
                confirmation_index,
                attempt_id,
                experiment_id,
                condition_id,
            )
    else:
        true_response = client.submit_probe(scenario, candidate["true_payload"])
        require_active_session_response(true_response)
        false_response = client.submit_probe(scenario, candidate["false_payload"])
        require_active_session_response(false_response)
        true_body = true_response["body"].lower()
        false_body = false_response["body"].lower()
        true_exists = EXISTS_MARKER in true_body
        true_missing = MISSING_MARKER in true_body
        false_exists = EXISTS_MARKER in false_body
        false_missing = MISSING_MARKER in false_body
        detected = true_exists and false_missing and not true_missing and not false_exists
        if observation_sink:
            observation_sink("true_condition", true_response,
                             ["user_id_exists"] if true_exists else [])
            observation_sink("false_condition", false_response,
                             ["user_id_missing"] if false_missing else [])

        emit_payload_record(
            output,
            run_id,
            scenario,
            candidate,
            replicate,
            "true_condition",
            candidate["true_payload"],
            true_response,
            baseline,
            ["user_id_exists"] if true_exists else [],
            confirmation_index,
            attempt_id,
            experiment_id,
            condition_id,
        )
        emit_payload_record(
            output,
            run_id,
            scenario,
            candidate,
            replicate,
            "false_condition",
            candidate["false_payload"],
            false_response,
            baseline,
            ["user_id_missing"] if false_missing else [],
            confirmation_index,
            attempt_id,
            experiment_id,
            condition_id,
        )
        indicators = []
        if true_exists:
            indicators.append("true_response_exists")
        if false_missing:
            indicators.append("false_response_missing")
        evidence.update(
            {
                "true_response_has_exists": true_exists,
                "true_response_has_missing": true_missing,
                "false_response_has_exists": false_exists,
                "false_response_has_missing": false_missing,
            }
        )

    decision = {
        "record_type": "decision",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "experiment_id": experiment_id,
        "condition_id": condition_id,
        "candidate_id": candidate["candidate_id"],
        "scenario_id": scenario["scenario_id"],
        "replicate": replicate,
        "confirmation_index": confirmation_index,
        "security_level": scenario["security_level"],
        "sqli_type": scenario["sqli_type"],
        "ground_truth": scenario["ground_truth"],
        "payload_source": candidate["source"],
        "rag_mode": candidate["rag_mode"],
        "provenance": candidate.get("provenance", {}),
        "system_signal": detected,
        "decision_scope": "single-confirmation-rule-signal",
        "system_decision": "vulnerable" if detected else "not_vulnerable",
        "confusion_class": decide_class(scenario["ground_truth"], detected),
        "evidence": evidence,
        "human_validation": "pending",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.write(json.dumps(decision, ensure_ascii=False) + "\n")
    output.flush()
    return detected


def emit_candidate_evidence(output, run_id, scenario, candidate, replicate, signals,
                            attempt_id="attempt-1", experiment_id=None, condition_id=None,
                            *, runtime_valid=True):
    """Keep confirmation evidence separate from an absent model claim."""
    record = {
        "schema_version": "1.0.0", "record_type": "candidate_evidence",
        "run_id": run_id, "attempt_id": attempt_id, "experiment_id": experiment_id,
        "condition_id": condition_id, "candidate_id": candidate["candidate_id"],
        "scenario_id": scenario["scenario_id"], "replicate": replicate,
        "payload_source": candidate["source"], "rag_mode": candidate["rag_mode"],
        "confirmation_signals": [signals[index] for index in sorted(signals)],
        **classify_confirmations(signals, runtime_valid=runtime_valid),
        # The executor does not infer what Qwen would have claimed.
        "qwen_claim": None, "human_validation": "pending",
    }
    output.write(json.dumps(record, ensure_ascii=False) + "\n")
    output.flush()
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="One scenario ID, S1 through S12")
    parser.add_argument("--payload-file", required=True, type=Path)
    parser.add_argument("--confirmations", "--repetitions", dest="confirmations", type=int, default=3,
                        help="Response confirmations per candidate. --repetitions remains a compatibility alias.")
    parser.add_argument("--replicate", type=int, choices=(1, 2, 3), default=1,
                        help="Independent pipeline replicate, distinct from response confirmations.")
    parser.add_argument("--run-id", help="Orchestrator-assigned unique pipeline run ID.")
    parser.add_argument("--attempt-id", default="attempt-1", help="Unique attempt ID within the pipeline run.")
    parser.add_argument("--experiment-id", help="Orchestrator-assigned experiment ID.")
    parser.add_argument("--condition-id", choices=("A", "B", "C"), help="Planned comparison condition.")
    parser.add_argument("--reset-before-run", action="store_true",
                        help="Reset the local DVWA sample database before login; this clears its data.")
    parser.add_argument("--output", type=Path, help="Optional JSONL path under results/raw")
    parser.add_argument(
        "--confirm-local-dvwa",
        action="store_true",
        help="Confirm DVWA is your local lab at http://127.0.0.1:4280",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_json(SCENARIOS_PATH)
    scenarios = {item["scenario_id"]: item for item in catalog["scenarios"]}
    if args.scenario not in scenarios:
        raise SystemExit("Unknown scenario. Choose S1 through S12.")
    scenario = scenarios[args.scenario]
    protocol = catalog["protocol"]

    if not args.confirm_local_dvwa:
        raise SystemExit("Pass --confirm-local-dvwa to run against the local lab.")
    if not 1 <= args.confirmations <= protocol["max_repetitions"]:
        raise SystemExit(
            f"--confirmations must be between 1 and {protocol['max_repetitions']}."
        )
    if args.run_id is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.run_id):
        raise SystemExit("--run-id contains unsupported characters.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.attempt_id):
        raise SystemExit("--attempt-id contains unsupported characters.")
    if args.experiment_id is not None and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", args.experiment_id):
        raise SystemExit("--experiment-id must be a lowercase project slug.")

    payload_document = load_json(args.payload_file)
    candidates = validate_candidates(
        payload_document,
        scenario,
        protocol["max_candidates_per_run"],
    )
    source_mode = (candidates[0]["source"], candidates[0]["rag_mode"])
    inferred_condition = {("LLM", "off"): "A", ("LLM", "on"): "B",
                          ("SecLists", "not_applicable"): "C"}.get(source_mode)
    if inferred_condition is None and candidates[0]["source"] != "manual":
        raise SystemExit("Candidate source cannot be mapped to a comparison condition.")
    if args.condition_id and args.condition_id != inferred_condition:
        raise SystemExit("--condition-id does not match the candidate source and RAG mode.")
    condition_id = args.condition_id or inferred_condition
    experiment_id = args.experiment_id or payload_document.get("experiment_id")
    if experiment_id is not None and (not isinstance(experiment_id, str)
                                      or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", experiment_id)):
        raise SystemExit("experiment_id in candidate batch must be a lowercase project slug.")

    username = os.environ.get("DVWA_USERNAME")
    password = os.environ.get("DVWA_PASSWORD")
    local_env = load_local_env_file()
    username = username or local_env.get("DVWA_USERNAME") or "admin"
    password = password or local_env.get("DVWA_PASSWORD") or "password"

    run_id = args.run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    raw_directory = ROOT / "results" / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    output_path = args.output or raw_directory / f"validation-{run_id}.jsonl"
    output_path = output_path.resolve()
    if not output_path.is_relative_to(raw_directory.resolve()):
        raise SystemExit("Output must stay inside results/raw/.")

    client = DvwaClient(
        catalog["target"]["default_origin"],
        int(protocol["request_timeout_seconds"]),
    )
    total_decisions = 0
    positive_signals = 0
    confirmed_success_count = 0
    mixed_evidence_count = 0
    with output_path.open("x", encoding="utf-8", newline="\n") as output:
        reset_receipt = None
        runtime_failure_logged = False
        output.write(json.dumps({"record_type": "run_start", "run_id": run_id,
                                 "attempt_id": args.attempt_id,
                                 "experiment_id": experiment_id,
                                 "condition_id": condition_id,
                                 "scenario_id": scenario["scenario_id"],
                                 "candidate_count": len(candidates),
                                 "pipeline_replicate": args.replicate,
                                 "confirmations_per_candidate": args.confirmations,
                                 "database_reset_requested": args.reset_before_run,
                                 "attempt_status": "started",
                                 "recorded_at_utc": datetime.now(timezone.utc).isoformat()},
                                ensure_ascii=False) + "\n")
        output.flush()
        try:
            if args.reset_before_run:
                reset_receipt = client.reset_database()
                # DVWA restores its documented sample credentials after setup.
                username, password = "admin", "password"
            client.login_and_set_level(username, password, scenario["security_level"])
            output.write(json.dumps({"record_type": "runtime_setup", "run_id": run_id,
                                     "attempt_id": args.attempt_id,
                                     "experiment_id": experiment_id,
                                     "condition_id": condition_id,
                                     "security_level_verified": scenario["security_level"],
                                     "database_reset": reset_receipt}, ensure_ascii=False) + "\n")
            output.flush()
            for candidate in candidates:
                signals = {}
                for confirmation_index in range(1, args.confirmations + 1):
                    try:
                        detected = execute_candidate(
                            client,
                            output,
                            run_id,
                            scenario,
                            candidate,
                            args.replicate,
                            float(protocol["time_signal_threshold_ms"]),
                            confirmation_index,
                            args.attempt_id,
                            experiment_id,
                            condition_id,
                        )
                        signals[confirmation_index] = detected
                        positive_signals += detected
                    except LocalRuntimeFailure as failure:
                        emit_candidate_evidence(output, run_id, scenario, candidate, args.replicate,
                                                signals, args.attempt_id, experiment_id, condition_id,
                                                runtime_valid=False)
                        output.write(json.dumps({
                            "record_type": "runtime_failure", "run_id": run_id,
                            "attempt_id": args.attempt_id,
                            "experiment_id": experiment_id,
                            "condition_id": condition_id,
                            "scenario_id": scenario["scenario_id"], "candidate_id": candidate["candidate_id"],
                            "replicate": args.replicate, "confirmation_index": confirmation_index,
                            "runtime_failure_code": failure.code,
                            "http_request_calls": client.http_request_calls,
                            "logical_probe_submissions": client.logical_probe_submissions,
                            "attack_failure": False, "attempt_status": "invalid",
                            "recovery_action": "repair_environment_then_start_new_attempt_after_database_reset",
                            "database_reset_performed": bool(reset_receipt),
                            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                        }, ensure_ascii=False) + "\n")
                        output.flush()
                        runtime_failure_logged = True
                        raise
                    total_decisions += 1
                    time.sleep(0.1)
                candidate_summary = emit_candidate_evidence(
                    output, run_id, scenario, candidate, args.replicate, signals,
                    args.attempt_id, experiment_id, condition_id)
                confirmed_success_count += candidate_summary["confirmed_success"] is True
                mixed_evidence_count += candidate_summary["evidence_status"] == "MIXED_EVIDENCE"
            output.write(json.dumps({"record_type": "run_end", "run_id": run_id,
                                     "attempt_id": args.attempt_id,
                                     "experiment_id": experiment_id,
                                     "condition_id": condition_id,
                                     "attempt_status": "complete",
                                     "decision_count": total_decisions,
                                     "positive_signals": positive_signals,
                                     "confirmed_success_count": confirmed_success_count,
                                     "mixed_evidence_count": mixed_evidence_count,
                                     "pipeline_replicate": args.replicate,
                                     "confirmations_per_candidate": args.confirmations,
                                     "database_reset_performed": bool(reset_receipt),
                                     "http_request_calls": client.http_request_calls,
                                     "logical_probe_submissions": client.logical_probe_submissions,
                                     "recorded_at_utc": datetime.now(timezone.utc).isoformat()},
                                    ensure_ascii=False) + "\n")
            output.flush()
        except LocalRuntimeFailure as failure:
            if not runtime_failure_logged:
                output.write(json.dumps({
                    "record_type": "runtime_failure", "run_id": run_id,
                    "attempt_id": args.attempt_id,
                    "experiment_id": experiment_id,
                    "condition_id": condition_id,
                    "scenario_id": scenario["scenario_id"], "runtime_failure_code": failure.code,
                    "http_request_calls": client.http_request_calls,
                    "logical_probe_submissions": client.logical_probe_submissions,
                    "attack_failure": False, "attempt_status": "invalid",
                    "recovery_action": "repair_environment_then_start_new_attempt_after_database_reset",
                    "database_reset_performed": bool(reset_receipt),
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
                output.flush()
                runtime_failure_logged = True
            print(json.dumps({"run_id": run_id, "scenario_id": scenario["scenario_id"],
                              "attempt_id": args.attempt_id,
                              "decision_count": total_decisions, "attempt_status": "invalid",
                              "runtime_failure_code": failure.code, "attack_failure": False,
                              "database_reset_performed": bool(reset_receipt)}), flush=True)
            return

    print(f"Validation log: {output_path}")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": args.attempt_id,
                "experiment_id": experiment_id,
                "condition_id": condition_id,
                "scenario_id": scenario["scenario_id"],
                "candidate_count": len(candidates),
                "pipeline_replicate": args.replicate,
                "confirmations_per_candidate": args.confirmations,
                "decision_count": total_decisions,
                "positive_signals": positive_signals,
                "confirmed_success_count": confirmed_success_count,
                "mixed_evidence_count": mixed_evidence_count,
                "http_request_calls": client.http_request_calls,
                "logical_probe_submissions": client.logical_probe_submissions,
                "database_reset_performed": bool(reset_receipt),
                "human_validation": "pending",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
