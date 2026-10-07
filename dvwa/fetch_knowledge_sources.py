"""Restore pinned public SQLi source snapshots; never update their locked versions."""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lock = json.loads((ROOT / "knowledge/sources.lock.json").read_text(encoding="utf-8"))
    allowed = {"owasp-wstg": "https://github.com/OWASP/wstg",
               "payloadsallthethings": "https://github.com/swisskyrepo/PayloadsAllTheThings"}
    for source in lock["sources"]:
        if source["repository"] != allowed.get(source["source_id"]):
            raise ValueError("Only the two official proposal repositories may be fetched.")
        commit = source["commit"]
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("Source versions must use full commit hashes.")
        repo = source["repository"].removeprefix("https://github.com/")
        for record in source["files"]:
            target = (ROOT / record["snapshot_path"]).resolve()
            if not target.is_relative_to((ROOT / "data/raw/knowledge-sources").resolve()):
                raise ValueError("Snapshot path leaves the intended directory.")
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == record["snapshot_sha256"]:
                continue
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/" + quote(record["repository_path"], safe="/")
            raw = urlopen(Request(url, headers={"User-Agent": "TA-SQLi-Knowledge-Curation"}), timeout=60).read()
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("Downloaded source hash differs from the locked source.")
            if record["snapshot_kind"] == "selected-sections":
                lines = raw.decode("utf-8").split("\n")
                sections = []
                for section in record["selected_sections"]:
                    start, end = section["line_start"], section["line_end"]
                    if lines[start - 1] != section["heading"]:
                        raise ValueError("Pinned section heading does not match the source.")
                    sections.append({**section, "text": "\n".join(lines[start - 1:end])})
                # Only relevant SQLi sections are saved, not the full MySQL document.
                content = (json.dumps({"source_sha256": record["sha256"], "sections": sections},
                                     ensure_ascii=False, indent=2) + "\n").encode()
            elif record["snapshot_kind"] == "full-file":
                content = raw
            else:
                raise ValueError("Unsupported source snapshot kind.")
            if hashlib.sha256(content).hexdigest() != record["snapshot_sha256"]:
                raise ValueError("Restored snapshot differs from the curated snapshot.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print("Pinned OWASP v4.2 and PayloadsAllTheThings SQLi snapshots verified.")


if __name__ == "__main__":
    main()
