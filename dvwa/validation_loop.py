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


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = Path(__file__).with_name("experiment_scenarios.json")
PAYLOAD_SCHEMA_VERSION = "1.0.0"
ERROR_PATTERNS = {
    "sql_syntax": re.compile(
        r"you have an error in your sql syntax|sql syntax.*(mysql|maria)|"
        r"syntax error.*sql|mysqli_sql_exception|mysql_fetch_(array|assoc|row)",
        re.IGNORECASE,
    ),
    "database_exception": re.compile(
        r"uncaught (mysqli_sql_exception|pdoexception)|"
        r"warning:\s*(mysqli|mysql|pdo)_",
        re.IGNORECASE,
    ),
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
        started = time.perf_counter()
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            status = error.code
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Local DVWA request failed: {reason}") from error

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
        if not token:
            raise RuntimeError("DVWA login CSRF token was not found.")

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
        if "logout" not in login["body"].lower():
            raise RuntimeError("DVWA login was not confirmed in the same session.")

        security_page = self.get_form("/security.php")
        token = form_data(security_page["body"]).get("user_token")
        if not token:
            raise RuntimeError("DVWA security form CSRF token was not found.")

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
        if selected != security_level:
            raise RuntimeError(
                f"DVWA did not confirm security level {security_level}."
            )

    def submit_probe(self, scenario: dict, payload: str) -> dict:
        """Submit one logical payload and return only the final response metadata."""
        method = scenario["method"]
        input_path = scenario["input_path"]
        result_path = scenario["result_path"]

        # Fetch a fresh form token outside the measured injection request.
        form = self.get_form(input_path)
        token = form_data(form["body"]).get("user_token")
        if scenario["security_level"] == "impossible" and not token:
            raise RuntimeError(
                "DVWA Impossible form did not expose the expected user_token."
            )

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
) -> None:
    output.write(
        json.dumps(
            {
                "record_type": "payload",
                "run_id": run_id,
                "candidate_id": candidate["candidate_id"],
                "payload_id": f"{candidate['candidate_id']}-r{replicate}-{role}",
                "scenario_id": scenario["scenario_id"],
                "replicate": replicate,
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
) -> bool:
    baseline = client.submit_probe(scenario, "1")
    probe_kind = scenario["probe_kind"]
    evidence: dict = {"probe_kind": probe_kind}

    if probe_kind in {"single_error", "single_time"}:
        response = client.submit_probe(scenario, candidate["payload"])
        if probe_kind == "single_error":
            baseline_errors = set(sql_error_markers(baseline["body"]))
            response_errors = set(sql_error_markers(response["body"]))
            indicators = sorted(response_errors - baseline_errors)
            detected = bool(indicators)
            evidence["new_sql_error_markers"] = indicators
        else:
            delta = response["elapsed_ms"] - baseline["elapsed_ms"]
            detected = delta >= threshold_ms
            indicators = ["time_delta_over_threshold"] if detected else []
            evidence.update(
                {
                    "time_delta_ms": round(delta, 2),
                    "threshold_ms": threshold_ms,
                }
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
            baseline,
            indicators,
        )
    else:
        true_response = client.submit_probe(scenario, candidate["true_payload"])
        false_response = client.submit_probe(scenario, candidate["false_payload"])
        true_body = true_response["body"].lower()
        false_body = false_response["body"].lower()
        true_exists = EXISTS_MARKER in true_body
        true_missing = MISSING_MARKER in true_body
        false_exists = EXISTS_MARKER in false_body
        false_missing = MISSING_MARKER in false_body
        detected = true_exists and false_missing and not true_missing and not false_exists

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
        "candidate_id": candidate["candidate_id"],
        "scenario_id": scenario["scenario_id"],
        "replicate": replicate,
        "security_level": scenario["security_level"],
        "sqli_type": scenario["sqli_type"],
        "ground_truth": scenario["ground_truth"],
        "payload_source": candidate["source"],
        "rag_mode": candidate["rag_mode"],
        "provenance": candidate.get("provenance", {}),
        "system_signal": detected,
        "system_decision": "vulnerable" if detected else "not_vulnerable",
        "confusion_class": decide_class(scenario["ground_truth"], detected),
        "evidence": evidence,
        "human_validation": "pending",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.write(json.dumps(decision, ensure_ascii=False) + "\n")
    output.flush()
    return detected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="One scenario ID, S1 through S12")
    parser.add_argument("--payload-file", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
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
    if not 1 <= args.repetitions <= protocol["max_repetitions"]:
        raise SystemExit(
            f"--repetitions must be between 1 and {protocol['max_repetitions']}."
        )

    payload_document = load_json(args.payload_file)
    candidates = validate_candidates(
        payload_document,
        scenario,
        protocol["max_candidates_per_run"],
    )

    username = os.environ.get("DVWA_USERNAME")
    password = os.environ.get("DVWA_PASSWORD")
    local_env = load_local_env_file()
    username = username or local_env.get("DVWA_USERNAME") or "admin"
    password = password or local_env.get("DVWA_PASSWORD") or "password"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
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
    client.login_and_set_level(username, password, scenario["security_level"])

    total_decisions = 0
    positive_signals = 0
    with output_path.open("x", encoding="utf-8", newline="\n") as output:
        for candidate in candidates:
            for replicate in range(1, args.repetitions + 1):
                positive_signals += execute_candidate(
                    client,
                    output,
                    run_id,
                    scenario,
                    candidate,
                    replicate,
                    float(protocol["time_signal_threshold_ms"]),
                )
                total_decisions += 1
                time.sleep(0.1)

    print(f"Validation log: {output_path}")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "scenario_id": scenario["scenario_id"],
                "candidate_count": len(candidates),
                "replicates_per_candidate": args.repetitions,
                "decision_count": total_decisions,
                "positive_signals": positive_signals,
                "human_validation": "pending",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
