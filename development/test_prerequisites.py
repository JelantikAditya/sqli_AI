"""Skip tests whose pinned local research sources are intentionally not versioned."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def require_local_snapshots(*lock_paths, extra_paths=()):
    missing = []
    for relative in lock_paths:
        lock_path = ROOT / relative
        if not lock_path.is_file():
            missing.append(relative)
            continue
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for source in lock.get("sources", []):
            records = source.get("files") or [source]
            for record in records:
                for key in ("snapshot_path", "raw_html_path"):
                    value = record.get(key)
                    if value and not (ROOT / value).is_file():
                        missing.append(value)
    missing.extend(path for path in extra_paths if not (ROOT / path).is_file())
    if missing:
        raise unittest.SkipTest(
            "Pinned local research sources are intentionally excluded from Git; "
            "install them per docs/candidate-sources.md before running this suite."
        )
