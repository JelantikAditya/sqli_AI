"""Generate a fresh local token for the temporary DVWA gateway."""

from pathlib import Path
import secrets


path = Path(__file__).with_name(".env")
if path.exists():
    raise SystemExit("dvwa/.env already exists; keep the active token or remove it intentionally")
path.write_text("LAB_TOKEN=" + secrets.token_urlsafe(32) + "\n", encoding="ascii")
print("Created dvwa/.env; keep this token private")
