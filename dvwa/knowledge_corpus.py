"""Validate and render structured SQLi knowledge from the two proposal sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "knowledge" / "sqli-entries.json"
CORPUS_KIND = "structured-sqli-knowledge-v1"
TECHNIQUES = ("error-based", "boolean-based blind", "time-based blind")
CONTENT_FIELDS = ("title", "vulnerability_type", "dbms", "functional_semantics",
                  "root_cause", "detection_method", "payload_examples", "mitigation", "limitations")
ALLOWED_FILES = {
    "owasp-wstg": {"document/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05-Testing_for_SQL_Injection.md"},
    "payloadsallthethings": {"SQL Injection/README.md", "SQL Injection/MySQL Injection.md"},
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_entry(entry: dict) -> str:
    # One complete knowledge pattern per vector, with no word-window truncation.
    return json.dumps({field: entry[field] for field in CONTENT_FIELDS}, ensure_ascii=False, indent=2)


def validate_corpus(path: Path = DEFAULT_CORPUS, root: Path = ROOT) -> tuple[dict, dict]:
    from jsonschema import Draft202012Validator

    corpus = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((root / "schemas/sqli-knowledge-corpus.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(corpus)
    lock_path = root / corpus["source_lock_path"]
    if sha256(lock_path.read_bytes()) != corpus["source_lock_sha256"]:
        raise ValueError("Corpus source lock changed; review and update the corpus explicitly.")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    sources = {item["source_id"]: item for item in lock["sources"]}
    if len(lock["sources"]) != 2 or set(sources) != set(ALLOWED_FILES):
        raise ValueError("The proposal corpus must use exactly OWASP WSTG and PayloadsAllTheThings.")
    if (sources["owasp-wstg"]["repository"] != "https://github.com/OWASP/wstg"
        or sources["owasp-wstg"]["requested_ref"] != "v4.2"
        or sources["payloadsallthethings"]["repository"] != "https://github.com/swisskyrepo/PayloadsAllTheThings"):
        raise ValueError("Source identity does not match the proposal.")

    file_lines = {}
    for source_id, source in sources.items():
        for record in source["files"]:
            snapshot = (root / record["snapshot_path"]).resolve()
            if not snapshot.is_relative_to((root / "data/raw/knowledge-sources").resolve()):
                raise ValueError("Source snapshots must stay in data/raw/knowledge-sources/.")
            data = snapshot.read_bytes()
            if sha256(data) != record["snapshot_sha256"]:
                raise ValueError(f"Source snapshot changed: {record['snapshot_path']}")
            if record["snapshot_kind"] == "selected-sections":
                selected = json.loads(data)
                if selected["source_sha256"] != record["sha256"]:
                    raise ValueError("Section snapshot must identify the full upstream source hash.")
                lines = {}
                for section in selected["sections"]:
                    text_lines = section["text"].split("\n")
                    # A trailing blank line may disappear in splitlines; it is restored below.
                    expected = section["line_end"] - section["line_start"] + 1
                    if not 0 <= expected - len(text_lines) <= 1:
                        raise ValueError("Section line coordinates do not match its text.")
                    text_lines += [""] * (expected - len(text_lines))
                    lines.update(dict(enumerate(text_lines, section["line_start"])))
            elif record["snapshot_kind"] == "full-file":
                if sha256(data) != record["sha256"]:
                    raise ValueError("Full snapshot hash must equal upstream hash.")
                # GitHub source coordinates count LF, not Unicode separators in payload text.
                lines = dict(enumerate(data.decode("utf-8").split("\n"), 1))
            else:
                raise ValueError("Unsupported source snapshot kind.")
            file_lines[source_id, record["repository_path"]] = lines

    entries = corpus["entries"]
    if len({entry["entry_id"] for entry in entries}) != len(entries):
        raise ValueError("Knowledge entry IDs must be unique.")
    if {entry["vulnerability_type"] for entry in entries} != set(TECHNIQUES):
        raise ValueError("Corpus must cover all three proposal SQLi techniques.")
    used_sources = set()
    for entry in entries:
        if len(render_entry(entry)) > 5500:
            raise ValueError("Knowledge entry too long; split the pattern editorially, not by truncating it.")
        for ref in entry["source_refs"]:
            source_id = ref["source_id"]
            used_sources.add(source_id)
            if ref["repository_path"] not in ALLOWED_FILES[source_id]:
                raise ValueError("Knowledge references must remain in the SQLi proposal sections.")
            lines = file_lines.get((source_id, ref["repository_path"]), {})
            start, end = ref["line_start"], ref["line_end"]
            if end < start or any(number not in lines for number in range(start, end + 1)):
                raise ValueError(f"Unavailable source coordinates in {entry['entry_id']}.")
            if ref["section"].lower() not in lines[start].lower():
                raise ValueError(f"Source section heading mismatch in {entry['entry_id']}.")
    if used_sources != set(ALLOWED_FILES):
        raise ValueError("Entries must include both proposal sources.")
    return corpus, lock


def prepare_documents(corpus: dict, lock: dict) -> list[dict]:
    sources = {item["source_id"]: item for item in lock["sources"]}
    documents = []
    for entry in corpus["entries"]:
        text = render_entry(entry)
        refs = []
        for ref in entry["source_refs"]:
            source = sources[ref["source_id"]]
            record = next(item for item in source["files"] if item["repository_path"] == ref["repository_path"])
            refs.append({**ref, "commit": source["commit"], "source_sha256": record["sha256"],
                         "url": record["url"] + f"#L{ref['line_start']}-L{ref['line_end']}"})
        chunk_id = sha256((entry["entry_id"] + ":" + sha256(text.encode()) + ":"
                           + corpus["source_lock_sha256"]).encode())
        documents.append({"id": chunk_id, "text": text, "metadata": {
            "entry_id": entry["entry_id"], "title": entry["title"],
            "vulnerability_type": entry["vulnerability_type"], "dbms": entry["dbms"],
            "corpus_kind": CORPUS_KIND, "source_refs_json": json.dumps(refs, sort_keys=True),
            "source_path": "knowledge/sqli-entries.json", "text_sha256": sha256(text.encode()),
        }})
    return documents


def build_config(corpus: dict, corpus_path: Path, model: str, input_format: str) -> dict:
    return {"schema_version": "1.0.0", "corpus_kind": CORPUS_KIND, "purpose": "proposal-rag",
            "corpus_version": corpus["corpus_version"], "corpus_sha256": sha256(corpus_path.read_bytes()),
            "source_lock_sha256": corpus["source_lock_sha256"], "embedding_model": model,
            "embedding_input_format": input_format, "entry_serialization": "complete-json-pattern-v1"}


def knowledge_base_id(config: dict) -> str:
    return "sqli-knowledge-" + sha256(json.dumps(config, sort_keys=True).encode())[:16]
