"""Measure the local Bonsai runtime with four bounded, development-only calls.

One JSON readiness request and three synthetic SQLi analysis fixtures are used.
No DVWA traffic, retrieval, evaluator annotations, paid API, or formal run occurs.
The temporary server is stopped on completion, including failures/timeouts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import threading
import time

import requests
from jsonschema import Draft202012Validator

import analysis_v5_pilot_cases as cases
import qwen_api_p2_analysis as p2

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("bonsai2_local_runtime.json")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gpu_sample() -> dict:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    used, free, utilization = (int(part.strip()) for part in result.stdout.strip().splitlines()[0].split(","))
    return {"at": datetime.now(timezone.utc).isoformat(), "used_mib": used,
            "free_mib": free, "gpu_utilization_percent": utilization}


def smoke_requests(config: dict, profile: str = "non-thinking") -> tuple[list[dict], list[dict]]:
    ready_schema = {"type": "object", "additionalProperties": False,
                    "properties": {"status": {"const": "ready"}, "sum": {"type": "integer"}},
                    "required": ["status", "sum"]}
    items = [{"case_id": "json-readiness", "schema": ready_schema,
              "messages": [{"role": "system", "content": "Return one JSON object only, without markdown."},
                           {"role": "user", "content": 'Return JSON with status="ready" and sum equal to 19+23.'}],
              "max_tokens": 128}]
    references = [{"case_id": "json-readiness", "expected": {"status": "ready", "sum": 42}}]
    specs = [
        ("synthetic-error-positive", "error-based", ["syntax"] * 3),
        ("synthetic-boolean-negative", "boolean-based blind", ["same"] * 3),
        ("synthetic-time-mixed", "time-based blind", ["above", "just-below", "unmatched"]),
    ]
    for case_id, technique, variants in specs:
        document = cases.make_document(technique, variants)
        prepared = p2.prepare(document)
        items.append({"case_id": case_id, "document": document, "prepared": prepared,
                      "schema": prepared["schema"], "messages": prepared["payload"]["messages"],
                      "max_tokens": 1536})
        references.append({"case_id": case_id, "expected": cases.reference(document)})
    for item in items:
        item["payload"] = {
            "model": "bonsai2-9b-local", "messages": item["messages"],
            "stream": False, "max_tokens": item["max_tokens"],
            **config["sampling"], "chat_template_kwargs": {"enable_thinking": False},
            "cache_prompt": False,
        }
        # The readiness request is unconstrained; the domain requests test the
        # same structural JSON contract used by the existing local pipeline.
        if "document" in item:
            item["payload"]["response_format"] = {
                "type": "json_schema", "json_schema": {
                    "name": "sqli_analysis", "strict": True, "schema": item["schema"]}}
            if profile == "bounded-thinking":
                # A separate diagnostic profile, never an overwrite/retry of
                # non-thinking evidence. Keep enough context for the final JSON.
                item["payload"].update(temperature=1.0, top_p=0.95, presence_penalty=1.0,
                                       max_tokens=2048, thinking_budget_tokens=1024,
                                       chat_template_kwargs={"enable_thinking": True})
    return items, references


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="Keep the local server running until Ctrl+C")
    parser.add_argument("--profile", choices=("non-thinking", "bounded-thinking"), default="non-thinking")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    install = ROOT / config["install_directory"]
    receipt = json.loads((install / "install-receipt.json").read_text(encoding="utf-8"))
    if receipt["config_sha256"] != file_hash(CONFIG):
        raise ValueError("Runtime configuration differs from the verified installation")
    if file_hash(Path(receipt["server_path"])) != receipt["server_sha256"]:
        raise ValueError("Runtime executable digest changed")
    model_entry = next(item for item in config["downloads"] if item["name"] == "model")
    if file_hash(Path(receipt["model_path"])) != model_entry["sha256"]:
        raise ValueError("Model digest changed")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / f"results/raw/development/bonsai2-9b-smoke-{timestamp}"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as port_probe:
        port_probe.bind((config["host"], config["port"]))
    command = [receipt["server_path"], "-m", receipt["model_path"],
               "--alias", "bonsai2-9b-local", "--host", config["host"], "--port", str(config["port"]),
               "-ngl", str(config["gpu_layers"]), "-c", str(config["context_tokens"]),
               "-np", str(config["parallel_requests"]), "-t", str(config["threads"]),
               "-b", str(config["batch_size"]), "-ub", str(config["microbatch_size"]),
               "-fa", "on", "--jinja", "--cache-ram", "0", "--no-webui",
               "--chat-template-kwargs", json.dumps({"enable_thinking": args.profile == "bounded-thinking"}),
               "--reasoning-budget", "1024" if args.profile == "bounded-thinking" else "0"]
    default_sampling = {**config["sampling"]}
    if args.profile == "bounded-thinking":
        default_sampling.update(temperature=1.0, top_p=0.95, presence_penalty=1.0)
    for option, key in [("--temp", "temperature"), ("--top-p", "top_p"), ("--top-k", "top_k"),
                        ("--min-p", "min_p"), ("--presence-penalty", "presence_penalty"),
                        ("--repeat-penalty", "repeat_penalty"), ("--repeat-last-n", "repeat_last_n"),
                        ("--seed", "seed")]:
        command.extend([option, str(default_sampling[key])])
    plan, references = smoke_requests(config, args.profile)
    write_json(output / "requests.json", plan)
    write_json(output / "synthetic-reference.json", {
        "origin": "AI-authored development fixtures; not human annotations or independent holdout",
        "cases": references})
    write_json(output / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "config": config, "profile": args.profile,
        "installation": receipt, "command": command, "source_sha256": file_hash(Path(__file__)),
        "scope": "local-runtime-smoke-only", "paid_api_calls": 0, "dvwa_requests": 0,
        "formal_FPR": False, "formal_PSR": False, "independent_holdout": False})
    telemetry = []
    stop_sampling = threading.Event()

    def monitor() -> None:
        while not stop_sampling.is_set():
            try:
                telemetry.append(gpu_sample())
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            stop_sampling.wait(1)

    baseline_gpu = gpu_sample()
    threading.Thread(target=monitor, daemon=True).start()
    client = requests.Session()
    client.trust_env = False  # All requests stay on loopback, irrespective of proxy environment.
    base_url = f"http://{config['host']}:{config['port']}"
    summary = {"schema": "bonsai2-local-smoke-v1", "output_directory": str(output),
               "profile": args.profile, "baseline_gpu": baseline_gpu, "cases": [], "status": "starting"}
    process = None
    start = time.perf_counter()
    try:
        with (output / "server.stdout.log").open("w", encoding="utf-8") as stdout, \
                (output / "server.stderr.log").open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(command, cwd=str(Path(receipt["server_path"]).parent),
                                       stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            summary["server_pid"] = process.pid
            deadline = time.monotonic() + 240
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Local server exited during startup: {process.returncode}")
                try:
                    health = client.get(base_url + "/health", timeout=2)
                    if health.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Local model did not become ready within 240 seconds")
                time.sleep(1)
            summary["startup_seconds"] = round(time.perf_counter() - start, 3)
            write_json(output / "props.json", client.get(base_url + "/props", timeout=10).json())
            write_json(output / "models.json", client.get(base_url + "/v1/models", timeout=10).json())
            print(f"Local model ready after {summary['startup_seconds']} seconds", flush=True)
            if args.serve:
                print(f"Serving at {base_url}/v1. Ctrl+C stops this process only.", flush=True)
                process.wait()
                summary["status"] = "server-stopped"
                return
            for item, reference in zip(plan, references):
                before = time.perf_counter()
                response = client.post(base_url + "/v1/chat/completions", json=item["payload"], timeout=(10, 180))
                response_path = output / f"{item['case_id']}.response.json"
                response_path.write_text(response.text, encoding="utf-8")
                response.raise_for_status()
                raw = response.json()
                choice = raw["choices"][0]
                message = choice["message"]
                result = {"case_id": item["case_id"], "wall_seconds": round(time.perf_counter() - before, 3),
                          "finish_reason": choice.get("finish_reason"), "usage": raw.get("usage"),
                          "timings": raw.get("timings"), "reasoning_content_present": bool(message.get("reasoning_content"))}
                try:
                    content = json.loads(message["content"])
                    Draft202012Validator(item["schema"]).validate(content)
                    result["json_schema_valid"] = True
                    if "document" in item:
                        parsed = p2.parse(item["document"], item["prepared"], {
                            "status": "ok", "content": message["content"]})
                        result.update(parsed_status=parsed["status"], decision=parsed["decision"],
                                      warnings=parsed["warnings"], parse_error=parsed["error"],
                                      expected_decision=reference["expected"]["decision"])
                        expected_outcomes = {trial["trial"]: trial["outcome"]
                                             for trial in reference["expected"]["trial_assessments"]}
                        actual_outcomes = {trial["trial"]: trial["outcome"]
                                           for trial in parsed["trial_assessments"]}
                        result["trial_outcomes_match"] = actual_outcomes == expected_outcomes
                        result["passed"] = (parsed["status"] == "ok" and not parsed["warnings"]
                                            and parsed["decision"] == reference["expected"]["decision"]
                                            and result["trial_outcomes_match"]
                                            and choice.get("finish_reason") == "stop")
                    else:
                        result["passed"] = content == reference["expected"]
                except Exception as exc:
                    result.update(json_schema_valid=False, passed=False, validation_error=type(exc).__name__)
                summary["cases"].append(result)
                write_json(output / "summary.json", summary)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            summary["passed_count"] = sum(item["passed"] for item in summary["cases"])
            summary["status"] = "completed"
    except Exception as exc:
        summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        # Only terminate the exact server started by this invocation.
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        stop_sampling.set()
        summary["total_wall_seconds"] = round(time.perf_counter() - start, 3)
        summary["peak_sampled_gpu_used_mib"] = max((sample["used_mib"] for sample in telemetry), default=None)
        summary["server_stopped"] = process is None or process.poll() is not None
        write_json(output / "gpu-telemetry.json", telemetry)
        write_json(output / "summary.json", summary)
        print(f"Receipt: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
