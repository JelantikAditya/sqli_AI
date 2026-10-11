"""Extract safe DVWA input coordinates from a local ZAP HAR, without sending HTTP."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import defaultdict
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit

from parse_zap_report import EXPECTED_INPUTS_BY_LEVEL, SQLI_INPUT_PATHS
from validation_loop import selected_security_level


class DiscoveryHTML(HTMLParser):
    """Keep field names and actions; input values and page text never leave memory."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.current = None
        self.logged_in = False
        self.login_form = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "a":
            href = urlsplit(attrs.get("href", ""))
            if href.path.endswith("logout.php") or (href.path.endswith("login.php") and any(k == "logout" for k, _ in parse_qsl(href.query, keep_blank_values=True))):
                self.logged_in = True
        if tag == "input" and attrs.get("name") in {"username", "password"}:
            self.login_form = True
        if tag == "form":
            self.current = {"method": attrs.get("method", "GET").upper(), "action": attrs.get("action", ""), "fields": []}
            self.forms.append(self.current)
        elif tag in {"input", "select", "textarea", "button"} and self.current is not None:
            # Only names meaningful to this experiment are published.
            name = attrs.get("name")
            if name in {"id", "Submit", "user_token"} and name not in self.current["fields"]:
                self.current["fields"].append(name)

    def handle_endtag(self, tag):
        if tag.lower() == "form":
            self.current = None


def local_origin(url):
    try:
        parts = urlsplit(url)
        port = parts.port or 80
    except (ValueError, TypeError):
        return None
    if parts.scheme != "http" or parts.username is not None or parts.password is not None:
        return None
    if parts.hostname == "dvwa" and port == 80:
        return ("http", "dvwa", 80)
    if parts.hostname in {"localhost", "127.0.0.1", "::1"} and port == 4280:
        return ("http", parts.hostname, 4280)
    return None


def session_key(request):
    """Use the session only to correlate evidence; never serialize it or its digest."""
    cookies = SimpleCookie()
    try:
        for header in request.get("headers", []):
            if header.get("name", "").lower() == "cookie":
                cookies.load(header.get("value", ""))
        for cookie in request.get("cookies", []):
            if cookie.get("name") in {"PHPSESSID", "security"}:
                cookies[cookie["name"]] = cookie.get("value", "")
    except Exception:
        return None
    session = cookies.get("PHPSESSID")
    origin = local_origin(request.get("url", ""))
    security = cookies.get("security")
    # DVWA's security cookie can change while PHPSESSID remains the same.
    # Keep those request states separate so one level cannot verify another.
    return (origin, session.value, security.value if security else None) if origin and session and session.value else None


def response_body(entry):
    content = entry.get("response", {}).get("content", {})
    body = content.get("text", "")
    if not isinstance(body, str):
        return ""
    if content.get("encoding") == "base64":
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8", "replace")
        except (ValueError, UnicodeError):
            return ""
    return body


def extract_inventory(har, security_level, source_sha256):
    if security_level not in EXPECTED_INPUTS_BY_LEVEL:
        raise ValueError("Choose low, medium, high or impossible.")
    if har.get("log", {}).get("creator", {}).get("name") != "ZAP":
        raise ValueError("Input must be a HAR exported by ZAP, not a browser capture.")
    entries = har.get("log", {}).get("entries")
    if not isinstance(entries, list):
        raise ValueError("Expected a HAR log.entries array.")
    session_levels = defaultdict(set)
    decoded = []
    # Correlate security-page evidence with the exact session of each input.
    for index, entry in enumerate(entries):
        request, response = entry.get("request", {}), entry.get("response", {})
        url = request.get("url", "")
        origin = local_origin(url)
        if not origin:
            continue
        path = urlsplit(url).path
        if path not in SQLI_INPUT_PATHS | {"/security.php"}:
            continue
        body = response_body(entry)
        html = DiscoveryHTML()
        html.feed(body)
        session = session_key(request)
        authenticated = response.get("status") == 200 and html.logged_in
        if path == "/security.php" and session and authenticated:
            level = selected_security_level(body)
            if level:
                session_levels[session].add(level)
        decoded.append((index, entry, html, session, authenticated))

    observations, candidates = [], {}
    rejected_sessions = 0
    expected = EXPECTED_INPUTS_BY_LEVEL[security_level]
    for index, entry, html, session, authenticated in decoded:
        request = entry["request"]
        url, method = request["url"], request.get("method", "").upper()
        path = urlsplit(url).path
        if path not in SQLI_INPUT_PATHS:
            continue
        # Popup helpers have no navigation/Logout link. Their authentication is
        # evidenced by the security page in the SAME session, not by HTTP 200.
        helper = path.endswith(("/session-input.php", "/cookie-input.php"))
        protected_response = authenticated or (helper and entry.get("response", {}).get("status") == 200 and not html.login_form and any("id" in f["fields"] for f in html.forms))
        verified = protected_response and session is not None and session_levels[session] == {security_level}
        if not verified:
            rejected_sessions += 1
        names = {k for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)}
        names.update(p.get("name") for p in request.get("queryString", []))
        post = request.get("postData", {})
        names.update(p.get("name") for p in post.get("params", []))
        if post.get("mimeType", "").split(";", 1)[0] == "application/x-www-form-urlencoded":
            names.update(k for k, _ in parse_qsl(post.get("text", ""), keep_blank_values=True))
        forms = []
        for form in html.forms:
            destination = urljoin(url, form["action"])
            if local_origin(destination) != local_origin(url):
                continue
            form_path = urlsplit(destination).path
            if form_path in SQLI_INPUT_PATHS:
                forms.append({"path": form_path, "method": form["method"], "fields": sorted(form["fields"])})
        obs_id = f"zaphar-{source_sha256[:12]}-{index}"
        observation = {"observation_id": obs_id, "entry_index": index, "path": path,
                       "method": method, "parameter_names": sorted(names & {"id", "Submit", "user_token"}),
                       "http_status": entry.get("response", {}).get("status"), "forms": forms,
                       "session_level_verified": bool(verified)}
        observations.append(observation)
        # A form identifies an input even if ZAP never submitted that form.
        coordinates = [(path, method, "request-parameter", [])] if "id" in names else []
        coordinates.extend((f["path"], f["method"], "response-form", f["fields"]) for f in forms if "id" in f["fields"])
        for input_path, input_method, kind, fields in coordinates:
            scenario_ids = expected.get((input_path, input_method))
            if not scenario_ids or not verified:
                continue
            key = (input_path, input_method, "id")
            candidate = candidates.setdefault(key, {"path": input_path, "method": input_method, "parameter": "id",
                "source_observation_id": obs_id, "scenario_ids": list(scenario_ids), "verification_status": "verified",
                "discovery_source": "zap-har", "evidence_kinds": [], "form_fields": [], "source_observation_ids": []})
            candidate["evidence_kinds"] = sorted(set(candidate["evidence_kinds"] + [kind]))
            candidate["form_fields"] = sorted(set(candidate["form_fields"] + fields))
            if obs_id not in candidate["source_observation_ids"]:
                candidate["source_observation_ids"].append(obs_id)
    covered = sorted({s for c in candidates.values() for s in c["scenario_ids"]}, key=lambda s: int(s[1:]))
    all_ids = {s for ids in expected.values() for s in ids}
    return {"schema_version": "1.0.0", "source_kind": "zap-har", "source_sha256": source_sha256,
            "security_level": security_level, "authentication_status": "verified" if any(v == {security_level} for v in session_levels.values()) else "unverified",
            "entry_count": len(entries), "rejected_session_observations": rejected_sessions,
            "observations": observations, "candidate_injection_points": list(candidates.values()),
            "covered_scenario_ids": covered, "missing_scenario_ids": sorted(all_ids - set(covered), key=lambda s: int(s[1:])),
            "sql_injection_detection": "not_assessed"}


def read_inventory(path, security_level):
    data = path.read_bytes()
    return extract_inventory(json.loads(data), security_level, hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("--security-level", required=True, choices=tuple(EXPECTED_INPUTS_BY_LEVEL))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = read_inventory(args.har, args.security_level)
    output = args.output or args.har.with_suffix(".inputs.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "covered": inventory["covered_scenario_ids"], "missing": inventory["missing_scenario_ids"]}))


if __name__ == "__main__":
    main()
