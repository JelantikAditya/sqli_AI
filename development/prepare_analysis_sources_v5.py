"""Capture new analysis references and a preservation baseline, without opening indexes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/analysis-knowledge-v5-20261020"
OUT = ROOT / "results/processed/analysis-corpus-v5-20261020"
LOCK = ROOT / "knowledge/analysis-v5/sources.lock.json"
FORMAL = ROOT / "results/raw/formal-review/formal-sqli-v1-20261017-20261019-v2/source-inventory.private.json"
PAGES = [
    ("portswigger-blind", "Blind SQL injection", "https://portswigger.net/web-security/sql-injection/blind"),
    ("portswigger-conditional-lab", "Lab: Blind SQL injection with conditional responses",
     "https://portswigger.net/web-security/sql-injection/blind/lab-conditional-responses"),
    ("portswigger-timing", "Listen to the whispers: web timing attacks that actually work",
     "https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work"),
]


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return sha_bytes(path.read_bytes())


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


class PageText(HTMLParser):
    """Deterministic readable text for local source coordinates; no JavaScript execution."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag in ("p", "div", "section", "article", "main", "li", "br", "pre", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li", "pre", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return "\n".join(line for raw in "".join(self.parts).splitlines()
                         if (line := " ".join(raw.split()))) + "\n"


def prepare():
    if LOCK.exists() or RAW.exists():
        raise ValueError("Preparation requires new source paths; existing evidence is never overwritten.")
    protected = read(FORMAL)
    for name, expected in protected.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Formal source differs from its inventory: {name}")
    # Preserve current bytes, independently of historical index byte identity.
    folders = ["knowledge", "data/raw/knowledge-sources", "results/raw/development", "results/processed"]
    paths = [ROOT / "dvwa/local_experiment_protocol.json", FORMAL]
    for folder in folders:
        paths.extend(path for path in (ROOT / folder).rglob("*") if path.is_file())
    approval = read(ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json")
    paths.extend(ROOT / name for name in approval["approved_snapshot"]["index_file_sha256"])
    for path in paths:
        protected[path.relative_to(ROOT).as_posix()] = sha(path)
    baseline_path = OUT / "preservation-baseline.json"
    if baseline_path.exists():
        # A failed network capture may resume only while the original baseline still matches.
        for name, expected in read(baseline_path)["files"].items():
            if sha(ROOT / name) != expected:
                raise ValueError(f"Preserved source changed after initial preparation: {name}")
    else:
        write_new(baseline_path, {
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "formal_inventory_count": len(read(FORMAL)),
            "files": dict(sorted(protected.items())), "basis": "current-bytes-before-v5-authoring",
        })

    old = read(ROOT / "knowledge/sources.lock.json")["sources"][0]
    record = old["files"][0]
    snapshot = ROOT / record["snapshot_path"]
    if sha(snapshot) != record["snapshot_sha256"]:
        raise ValueError("Pinned OWASP snapshot differs from its original lock.")
    sources = [{
        "source_id": "owasp-wstg42", "title": "Testing for SQL Injection, WSTG v4.2",
        "publisher": "OWASP WSTG contributors", "canonical_url": record["url"],
        "public_reading_url": "https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05-Testing_for_SQL_Injection/",
        "version_kind": "git-commit", "version": old["commit"],
        "retrieved_at_utc": read(ROOT / "knowledge/sources.lock.json")["retrieved_at_utc"],
        "verified_for_v5_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": record["snapshot_path"], "snapshot_sha256": sha(snapshot),
        "snapshot_format": "utf-8-markdown", "line_coordinate_basis": "splitlines-one-based-inclusive",
        "attribution": "OWASP WSTG v4.2, CC BY-SA 4.0; short editorial paraphrases with section attribution.",
    }]
    for source_id, title, url in PAGES:
        request = Request(url, headers={"User-Agent": "TA-SQLi-Analysis-Corpus-Review/5"})
        with urlopen(request, timeout=30) as response:
            final_url = response.geturl()
            if final_url != url:
                raise ValueError(f"Unexpected source redirect: {final_url}")
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset() or "utf-8"
        parser = PageText()
        parser.feed(raw.decode(charset))
        text = parser.text().encode("utf-8")
        if title not in text.decode("utf-8") or "text/html" not in content_type:
            raise ValueError("Unexpected page content/title.")
        RAW.mkdir(parents=True, exist_ok=True)
        html_path, text_path = RAW / f"{source_id}.html", RAW / f"{source_id}.txt"
        html_path.write_bytes(raw)
        text_path.write_bytes(text)
        sources.append({
            "source_id": source_id, "title": title, "publisher": "PortSwigger",
            "canonical_url": url, "version_kind": "dated-content-snapshot-not-upstream-release",
            "version": sha_bytes(raw), "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_path": text_path.relative_to(ROOT).as_posix(), "snapshot_sha256": sha_bytes(text),
            "raw_html_path": html_path.relative_to(ROOT).as_posix(), "raw_html_sha256": sha_bytes(raw),
            "snapshot_format": "normalized-visible-text-v1", "line_coordinate_basis": "splitlines-one-based-inclusive",
            "attribution": "PortSwigger; concise original paraphrases only. No upstream license grant asserted.",
        })
    write_new(LOCK, {"schema_version": "1.0.0", "lock_id": "analysis-v5-sources-20261020",
                     "sources": sources, "reference_segments": [],
                     "scope": "analysis-only-draft-general-knowledge; no payload-generation corpus replacement"})
    print(json.dumps({"sources": len(sources), "protected_files": len(read(baseline_path)["files"]), "lock": LOCK.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
