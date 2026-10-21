"""Execute the frozen 18-case P2 Qwen analysis evaluation once per case.

This runner consumes only prepared evidence requests. It never reads validator
annotations, retries requests, or sends a request whose completion is unknown.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "development"))
sys.path.insert(0, str(ROOT / "dvwa"))

from qwen_api_client import ChatSettings, QwenAPIClient, encoded_payload, redact, request_payload
from qwen_api_credentials import get_api_key
from qwen_api_p2_analysis import PROMPT_VERSION, TIMEOUT_SECONDS, MAX_OUTPUT_TOKENS, canonical_hash, parse


EXPECTED_REQUESTS = 18
MODEL = "Qwen3.8-27B"
RESULT_SCHEMA = "qwen-api-p2-case-result-v1"
RUN_SCHEMA = "qwen-api-p2-run-v1"
DEFAULT_REQUESTS = ROOT / "results/raw/development/qwen38-api-p2-eval-20261021-ready/operator/prepared-requests.jsonl"
DEFAULT_OUTPUT = ROOT / "results/raw/development/qwen38-api-p2-eval-20261021-run-001"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_review_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"rv-[a-zA-Z0-9-]{6,48}", value):
        raise ValueError("Invalid review ID in prepared request")
    return value


def load_requests(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    requests: list[dict] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed request JSON on line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Request on line {line_number} must be an object")
        requests.append(row)

    if len(requests) != EXPECTED_REQUESTS:
        raise ValueError(f"Expected exactly {EXPECTED_REQUESTS} prepared requests")
    ids = [safe_review_id(row.get("review_id")) for row in requests]
    if len(set(ids)) != EXPECTED_REQUESTS:
        raise ValueError("Prepared request IDs must be unique")

    settings = ChatSettings(max_tokens=MAX_OUTPUT_TOKENS, timeout_seconds=TIMEOUT_SECONDS)
    for row in requests:
        rid = safe_review_id(row["review_id"])
        document = row.get("document")
        prepared = row.get("prepared")
        if not isinstance(document, dict) or not isinstance(prepared, dict):
            raise ValueError(f"Prepared request {rid} is missing its evidence or adapter record")
        if prepared.get("prompt_version") != PROMPT_VERSION:
            raise ValueError(f"Prepared request {rid} uses an unexpected prompt version")
        if prepared.get("claim_override") is not False or prepared.get("rag_mode") != "off":
            raise ValueError(f"Prepared request {rid} is not the frozen no-RAG analysis condition")
        if prepared.get("document_sha256") != canonical_hash(document):
            raise ValueError(f"Prepared request {rid} is not bound to its evidence document")
        payload = prepared.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise ValueError(f"Prepared request {rid} has no chat payload")
        if payload.get("model") != MODEL or payload.get("temperature") != 0:
            raise ValueError(f"Prepared request {rid} has unexpected model settings")
        if payload.get("max_tokens") != MAX_OUTPUT_TOKENS or payload.get("stream") is not False:
            raise ValueError(f"Prepared request {rid} has unexpected output settings")
        expected_payload = request_payload(payload["messages"], settings)
        if payload != expected_payload:
            raise ValueError(f"Prepared request {rid} payload differs from the frozen settings")
        expected_hash = sha256_bytes(encoded_payload(payload))
        if row.get("request_sha256") != expected_hash or prepared.get("request_sha256") != expected_hash:
            raise ValueError(f"Prepared request {rid} payload hash does not match")

    return requests, sha256_bytes(raw)


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


@contextmanager
def exclusive_execution_lock(lock_path: Path):
    """Prevent two CLI processes from sending the same frozen batch concurrently."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    mutex_handle = None
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b" ")
        try:
            if os.name == "nt":
                # Windows byte-range locks behaved inconsistently when the
                # runner was started through nested terminal processes. A
                # named mutex is shared across those processes and is released
                # by the OS if its owner exits or is terminated.
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
                kernel32.CreateMutexW.restype = wintypes.HANDLE
                kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
                kernel32.ReleaseMutex.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL

                mutex_key = hashlib.sha256(
                    str(lock_path.resolve()).casefold().encode("utf-8")
                ).hexdigest()
                mutex_name = f"Local\\CodexQwenP2-{mutex_key}"
                mutex_handle = kernel32.CreateMutexW(None, False, mutex_name)
                if not mutex_handle:
                    raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
                wait_result = kernel32.WaitForSingleObject(mutex_handle, 0)
                if wait_result not in (0x00000000, 0x00000080):  # WAIT_OBJECT_0 / WAIT_ABANDONED
                    raise RuntimeError("Another P2 runner is already active for this output directory")
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError("Another P2 runner is already active for this output directory") from exc

        metadata = json.dumps({"pid": os.getpid(), "started_at_utc": utc_now()}).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, metadata)
        os.ftruncate(fd, len(metadata))
        os.fsync(fd)
        yield
    finally:
        if locked:
            try:
                if os.name != "nt":
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        else:
            os.close(fd)
        if mutex_handle:
            if locked:
                kernel32.ReleaseMutex(mutex_handle)
            kernel32.CloseHandle(mutex_handle)


def redact_tree(value: Any, api_key: str) -> Any:
    if isinstance(value, str):
        return redact(value, api_key)
    if isinstance(value, list):
        return [redact_tree(item, api_key) for item in value]
    if isinstance(value, dict):
        return {key: redact_tree(item, api_key) for key, item in value.items()}
    return value


def load_or_create_manifest(output_dir: Path, requests_sha256: str, requests: list[dict],
                            allow_ambiguous: bool = False) -> dict:
    manifest_path = output_dir / "run-manifest.json"
    request_ids = [row["review_id"] for row in requests]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("schema") != RUN_SCHEMA
                or manifest.get("requests_sha256") != requests_sha256
                or manifest.get("request_ids") != request_ids
                or manifest.get("prompt_version") != PROMPT_VERSION):
            raise ValueError("Existing run manifest belongs to a different frozen request packet")
        if manifest.get("state") == "halted":
            if not allow_ambiguous:
                raise RuntimeError("This run halted or has an ambiguous request. Use --skip-ambiguous-and-continue only to continue without retrying unresolved requests.")
            saved_statuses = []
            for rid in request_ids:
                result_path = output_dir / "results" / f"{rid}.json"
                if result_path.exists():
                    try:
                        saved_statuses.append(json.loads(result_path.read_text(encoding="utf-8")))
                    except Exception:
                        raise RuntimeError("A saved result is unreadable; the halted run cannot be resumed safely")
            recoverable = [
                item for item in saved_statuses
                if item.get("api_status") == "transport-error" and item.get("http_status") is None
            ]
            other_failures = [
                item for item in saved_statuses
                if item.get("api_status") not in {"ok", "ambiguous-no-response", "transport-error"}
            ]
            if not recoverable or other_failures:
                raise RuntimeError("This run halted on a non-recoverable API error; no further requests will be sent")
            manifest["state"] = "ambiguous"
        if manifest.get("state") == "ambiguous" and not allow_ambiguous:
            raise RuntimeError("This run has an ambiguous request. Use --skip-ambiguous-and-continue to preserve it without retrying.")
        return manifest

    if output_dir.exists():
        children = list(output_dir.iterdir())
        allowed_root_entries = {"operator", ".execution.lock"}
        if any(child.name not in allowed_root_entries for child in children):
            raise ValueError("Output directory already contains files but has no matching run manifest")
        operator_dir = output_dir / "operator"
        if operator_dir.exists():
            allowed_operator_files = {"annotations-VAL-01.locked.csv", "annotation-lock.json"}
            if any(child.name not in allowed_operator_files for child in operator_dir.iterdir()):
                raise ValueError("Operator directory contains unexpected files")
    manifest = {
        "schema": RUN_SCHEMA,
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "state": "ready",
        "requests_sha256": requests_sha256,
        "request_ids": request_ids,
        "request_count": len(requests),
        "requested_model": MODEL,
        "endpoint": "https://api.hcnsec.cn/v1/chat/completions",
        "prompt_version": PROMPT_VERSION,
        "rag_mode": "off",
        "claim_override": False,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "retry_policy": "none; one request maximum per review ID",
    }
    write_json_atomic(manifest_path, manifest)
    return manifest


def refresh_manifest(manifest: dict, output_dir: Path, requests: list[dict], state: str) -> None:
    results_dir = output_dir / "results"
    statuses = []
    cases = []
    decisions: Counter[str] = Counter()
    unresolved_ids = []
    for row in requests:
        result_path = results_dir / f"{row['review_id']}.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                api_status = result.get("api_status", "unknown")
                analysis = result.get("analysis")
                statuses.append(api_status)
                if isinstance(analysis, dict) and isinstance(analysis.get("decision"), str):
                    decisions[analysis["decision"]] += 1
                if result.get("request_completion_unknown"):
                    unresolved_ids.append(row["review_id"])
                cases.append({
                    "review_id": row["review_id"],
                    "request_sha256": result.get("request_sha256"),
                    "api_status": api_status,
                    "analysis_status": result.get("analysis_status", "unknown"),
                    "decision": analysis.get("decision") if isinstance(analysis, dict) else None,
                    "analysis": analysis,
                    "http_status": result.get("http_status"),
                    "requested_model": result.get("requested_model", MODEL),
                    "reported_model": result.get("reported_model"),
                    "response_id": result.get("response_id"),
                    "usage": result.get("usage"),
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "request_completion_unknown": bool(result.get("request_completion_unknown", False)),
                    "retry_performed": bool(result.get("retry_performed", False)),
                })
            except Exception:
                statuses.append("unreadable")
                cases.append({
                    "review_id": row["review_id"],
                    "api_status": "unreadable",
                    "analysis_status": "not-evaluable",
                })
    manifest["updated_at_utc"] = utc_now()
    manifest["state"] = state
    manifest["saved_result_count"] = len(statuses)
    manifest["api_status_counts"] = dict(sorted(Counter(statuses).items()))
    write_json_atomic(output_dir / "run-manifest.json", manifest)
    write_json_atomic(output_dir / "evaluation-results.json", {
        "schema": "qwen-api-p2-evaluation-results-v1",
        "state": state,
        "created_at_utc": manifest["created_at_utc"],
        "updated_at_utc": manifest["updated_at_utc"],
        "request_count": len(requests),
        "saved_result_count": len(statuses),
        "requests_sha256": manifest["requests_sha256"],
        "requested_model": manifest["requested_model"],
        "prompt_version": manifest["prompt_version"],
        "rag_mode": manifest["rag_mode"],
        "claim_override": manifest["claim_override"],
        "temperature": manifest["temperature"],
        "max_tokens": manifest["max_tokens"],
        "timeout_seconds": manifest["timeout_seconds"],
        "retry_policy": manifest["retry_policy"],
        "api_status_counts": dict(sorted(Counter(statuses).items())),
        "analysis_decision_counts": dict(sorted(decisions.items())),
        "unresolved_request_ids": unresolved_ids,
        "cases": cases,
    })


def run_batch(requests: list[dict], requests_sha256: str, output_dir: Path,
              client: Any, api_key_for_redaction: str,
              skip_ambiguous_and_continue: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_or_create_manifest(output_dir, requests_sha256, requests,
                                       allow_ambiguous=skip_ambiguous_and_continue)
    results_dir = output_dir / "results"
    started_dir = output_dir / "request-started"
    results_dir.mkdir(exist_ok=True)
    started_dir.mkdir(exist_ok=True)

    completed = 0
    for row in requests:
        review_id = row["review_id"]
        prepared = row["prepared"]
        result_path = results_dir / f"{review_id}.json"
        started_path = started_dir / f"{review_id}.json"
        request_hash = row["request_sha256"]

        if result_path.exists():
            prior = json.loads(result_path.read_text(encoding="utf-8"))
            if prior.get("request_sha256") != request_hash:
                raise ValueError(f"Saved result for {review_id} has a different request hash")
            completed += 1
            continue
        if started_path.exists():
            if not skip_ambiguous_and_continue:
                refresh_manifest(manifest, output_dir, requests, "ambiguous")
                raise RuntimeError(f"Request {review_id} was marked started without a saved result; no retry was sent")
            write_json_atomic(result_path, {
                "schema": RESULT_SCHEMA,
                "review_id": review_id,
                "recorded_at_utc": utc_now(),
                "prompt_version": prepared["prompt_version"],
                "document_sha256": prepared["document_sha256"],
                "request_sha256": request_hash,
                "api_status": "ambiguous-no-response",
                "analysis_status": "not-evaluable",
                "request_completion_unknown": True,
                "retry_performed": False,
                "note": "The request may have reached the provider, but no response was saved. It was not resent.",
            })
            completed += 1
            refresh_manifest(manifest, output_dir, requests, "running")
            continue

        write_json_atomic(started_path, {
            "review_id": review_id,
            "request_sha256": request_hash,
            "started_at_utc": utc_now(),
            "policy": "single attempt; no retry",
        })
        refresh_manifest(manifest, output_dir, requests, "running")

        try:
            api_result = client.chat(prepared["payload"]["messages"])
            if api_result.get("request_sha256") != request_hash:
                api_result = {
                    **api_result,
                    "status": "request-hash-mismatch",
                    "halt": True,
                }
            record = {
                "schema": RESULT_SCHEMA,
                "review_id": review_id,
                "recorded_at_utc": utc_now(),
                "prompt_version": prepared["prompt_version"],
                "document_sha256": prepared["document_sha256"],
                "request_sha256": request_hash,
                "api_status": api_result.get("status", "unknown"),
                "http_status": api_result.get("http_status"),
                "requested_model": api_result.get("requested_model", MODEL),
                "reported_model": api_result.get("reported_model"),
                "response_id": api_result.get("response_id"),
                "finish_reason": api_result.get("finish_reason"),
                "usage": api_result.get("usage"),
                "elapsed_seconds": api_result.get("elapsed_seconds"),
                "content": api_result.get("content"),
                "raw_response": api_result.get("response"),
                "error_detail": api_result.get("error_detail"),
            }
            if api_result.get("status") == "ok":
                try:
                    record["analysis"] = parse(row["document"], prepared, api_result)
                    record["analysis_status"] = "parsed"
                except Exception as exc:
                    record["analysis_status"] = "parse-error"
                    record["analysis_error"] = f"{type(exc).__name__}: {exc}"
            else:
                record["analysis_status"] = "not-parsed"
            recoverable_transport_error = (
                api_result.get("status") == "transport-error"
                and api_result.get("http_status") is None
            )
            if recoverable_transport_error:
                record["request_completion_unknown"] = True
                record["retry_performed"] = False
                record["note"] = (
                    "The client timed out without an HTTP response. The provider may have received the request; "
                    "it was not resent."
                )
            write_json_atomic(result_path, redact_tree(record, api_key_for_redaction))
            completed += 1
            if recoverable_transport_error and skip_ambiguous_and_continue:
                refresh_manifest(manifest, output_dir, requests, "running")
                continue
            if api_result.get("status") != "ok" or api_result.get("halt"):
                refresh_manifest(manifest, output_dir, requests, "halted")
                return manifest
        except Exception as exc:
            record = {
                "schema": RESULT_SCHEMA,
                "review_id": review_id,
                "recorded_at_utc": utc_now(),
                "prompt_version": prepared["prompt_version"],
                "document_sha256": prepared["document_sha256"],
                "request_sha256": request_hash,
                "api_status": "client-exception",
                "analysis_status": "not-parsed",
                "error_detail": f"{type(exc).__name__}: {exc}",
            }
            write_json_atomic(result_path, redact_tree(record, api_key_for_redaction))
            refresh_manifest(manifest, output_dir, requests, "halted")
            return manifest

    if completed == EXPECTED_REQUESTS:
        statuses = manifest.get("api_status_counts", {})
        final_state = (
            "completed_with_ambiguity"
            if statuses.get("ambiguous-no-response", 0) or statuses.get("transport-error", 0)
            else "completed"
        )
    else:
        final_state = "running"
    refresh_manifest(manifest, output_dir, requests, final_state)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, default=DEFAULT_REQUESTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true", help="Send the 18 frozen requests, once each")
    parser.add_argument("--skip-ambiguous-and-continue", action="store_true",
                        help="Record orphaned started requests as unresolved, never resend them, then continue")
    args = parser.parse_args()

    requests_path = args.requests.resolve()
    output_dir = args.output_dir.resolve()
    development_root = (ROOT / "results/raw/development").resolve()
    if development_root not in output_dir.parents:
        parser.error("Output directory must remain under results/raw/development")
    try:
        requests, requests_sha256 = load_requests(requests_path)
    except Exception as exc:
        parser.error(str(exc))

    if not args.execute:
        print(json.dumps({
            "state": "validated-dry-run",
            "request_count": len(requests),
            "request_ids_unique": True,
            "requests_sha256": requests_sha256,
            "requested_model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "calls_made": 0,
        }, indent=2))
        return 0

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with exclusive_execution_lock(output_dir / ".execution.lock"):
            api_key = get_api_key()

            client = QwenAPIClient(api_key, settings=ChatSettings(
                max_tokens=MAX_OUTPUT_TOKENS, timeout_seconds=TIMEOUT_SECONDS))
            manifest = run_batch(requests, requests_sha256, output_dir, client, api_key,
                                 skip_ambiguous_and_continue=args.skip_ambiguous_and_continue)
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps({
        "state": manifest.get("state"),
        "request_count": manifest.get("request_count"),
        "saved_result_count": manifest.get("saved_result_count", 0),
        "api_status_counts": manifest.get("api_status_counts", {}),
        "output_dir": str(output_dir),
    }, indent=2))
    return 0 if manifest.get("state") in {"completed", "completed_with_ambiguity"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
