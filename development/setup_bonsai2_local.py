"""Install pinned Bonsai 2 assets locally without changing system packages.

Only official PrismML/Hugging Face artifacts are downloaded. Every complete
download is size/hash checked before any archive is extracted or executable run.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("bonsai2_local_runtime.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked(path: Path, item: dict) -> bool:
    return (path.is_file() and path.stat().st_size == item["bytes"]
            and sha256(path) == item["sha256"])


def download(item: dict, directory: Path) -> dict:
    target = directory / item["file"]
    if checked(target, item):
        print(f"Verified cached {item['name']}", flush=True)
        return {**item, "path": str(target), "verified": True}
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, 4):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == item["bytes"]:
            break
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with requests.get(item["url"], headers=headers, stream=True,
                              timeout=(30, 90)) as response:
                response.raise_for_status()
                # Restart safely if the origin ignores a partial-file range.
                append = offset > 0 and response.status_code == 206
                if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise RuntimeError("Unexpected download range")
                written = offset if append else 0
                milestone = written // (100 * 1024 * 1024)
                with partial.open("ab" if append else "wb") as handle:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            handle.write(block)
                            written += len(block)
                        if written // (100 * 1024 * 1024) > milestone:
                            milestone = written // (100 * 1024 * 1024)
                            print(f"{item['name']}: {written / item['bytes']:.0%}", flush=True)
            break
        except requests.RequestException as exc:
            print(f"{item['name']}: attempt {attempt} failed ({type(exc).__name__})", flush=True)
            if attempt == 3:
                raise
            time.sleep(attempt)
    if not checked(partial, item):
        raise RuntimeError(f"Integrity verification failed: {item['name']}")
    partial.replace(target)
    print(f"SHA256 verified: {item['name']}", flush=True)
    return {**item, "path": str(target), "verified": True}


def extract_checked(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            # Do not permit an archive member to escape this local runtime.
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(base):
                raise RuntimeError("Archive member is outside runtime directory")
        bundle.extractall(destination)


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    directory = (ROOT / config["install_directory"]).resolve()
    if not directory.is_relative_to((ROOT / "models").resolve()):
        raise ValueError("Install directory must remain inside workspace/models")
    directory.mkdir(parents=True, exist_ok=True)
    print("Downloading pinned Bonsai 2 9B PTQ1_0 and Windows CUDA 12.4 runtime", flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assets = list(pool.map(lambda item: download(item, directory), config["downloads"]))
    runtime = directory / "runtime"
    for asset in assets:
        if asset["name"] != "model":
            extract_checked(Path(asset["path"]), runtime)
    servers = list(runtime.rglob("llama-server.exe"))
    if len(servers) != 1:
        raise RuntimeError("Expected one extracted llama-server.exe")
    server = servers[0]
    # Release archives can use different enclosing directories. DLLs must sit
    # beside the executable on Windows; no global PATH modification is needed.
    for dll in list(runtime.rglob("*.dll")):
        if dll.parent != server.parent:
            dest = server.parent / dll.name
            if not dest.exists():
                shutil.copy2(dll, dest)
    manifest = {
        "schema": "bonsai2-local-install-receipt-v1",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256(CONFIG),
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "runtime_release": config["runtime_release"],
        "model_path": str(directory / config["model_file"]),
        "server_path": str(server),
        "server_sha256": sha256(server),
        "assets": assets,
    }
    (directory / "install-receipt.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Installation verified. No inference or paid API request was sent.", flush=True)


if __name__ == "__main__":
    main()
