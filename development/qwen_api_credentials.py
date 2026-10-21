"""Load a Qwen API key from the environment or a Git-ignored local file.

Run with --save once to enter a key privately, or --check to check availability.
Neither command contacts the API or prints the credential.
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import tempfile


ENV_NAME = "HCNSEC_API_KEY"
KEY_PATH = Path(__file__).resolve().parents[1] / ".env.hcnsec.local"


def _validate_key(value: str) -> str:
    key = value.strip()
    if not key or any(character.isspace() or not character.isprintable() for character in key):
        # Error messages must never include the value supplied by the user.
        raise ValueError("API key must be a nonempty single value without whitespace.")
    return key


def saved_api_key(path: Path = KEY_PATH) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1 or not lines[0].startswith(ENV_NAME + "="):
        raise ValueError("Invalid local API key file. Configure it again with --save.")
    return _validate_key(lines[0].partition("=")[2])


def get_api_key(*, path: Path = KEY_PATH, prompt: bool = True) -> str:
    # An explicit environment value overrides the saved key for this process.
    value = os.environ.get(ENV_NAME, "").strip()
    if value:
        return _validate_key(value)
    value = saved_api_key(path)
    if value:
        return value
    if prompt:
        return _validate_key(getpass.getpass(ENV_NAME + " (input is hidden): "))
    return ""


def save_api_key(value: str, path: Path = KEY_PATH) -> None:
    key = _validate_key(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement also supports rotation without leaving a partial file.
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.hcnsec.local.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(ENV_NAME + "=" + key + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--save", action="store_true", help="Save or replace the key using hidden input")
    action.add_argument("--check", action="store_true", help="Check availability without printing the key")
    args = parser.parse_args()
    try:
        if args.save:
            save_api_key(getpass.getpass(ENV_NAME + " (input is hidden): "))
            print("API key saved locally. No API request was sent.")
            if os.environ.get(ENV_NAME, "").strip():
                print("The current environment value still takes precedence over the saved key.")
            return 0
        available = bool(get_api_key(prompt=False))
    except (OSError, UnicodeError, ValueError):
        # Do not let a parse or filesystem error expose credential file contents.
        parser.error("Unable to use the local API key. Check file access or configure it with --save.")
    print("API key available. No API request was sent." if available
          else "API key not configured. Run this script with --save.")
    return 0 if available else 1


if __name__ == "__main__":
    raise SystemExit(main())
