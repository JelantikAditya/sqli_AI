"""Smoke test level DVWA melalui antarmuka web (tanpa membaca kode target)."""

import http.cookiejar
import re
import urllib.parse
import urllib.request


BASE = "http://127.0.0.1:4280/"
LEVELS = ("low", "medium", "high", "impossible")


def token(html: str) -> str:
    match = re.search(r"name=['\"]user_token['\"] value=['\"]([0-9a-f]+)", html)
    if not match:
        raise RuntimeError("Token form DVWA tidak ditemukan")
    return match.group(1)


def post(opener, path: str, values: dict[str, str]) -> str:
    data = urllib.parse.urlencode(values).encode()
    with opener.open(BASE + path, data, timeout=10) as response:
        return response.read().decode("utf-8", "replace")


def main() -> None:
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    with opener.open(BASE + "login.php", timeout=10) as response:
        login = response.read().decode("utf-8", "replace")

    post(
        opener,
        "login.php",
        {"username": "admin", "password": "password", "Login": "Login", "user_token": token(login)},
    )

    # Setiap perubahan level diuji pada sesi yang sama agar cookie tetap konsisten.
    for level in LEVELS:
        with opener.open(BASE + "security.php", timeout=10) as response:
            page = response.read().decode("utf-8", "replace")
        updated = post(
            opener,
            "security.php",
            {"security": level, "seclev_submit": "Submit", "user_token": token(page)},
        )
        selected = re.search(
            r'<option value="([^"]+)" selected=["\']selected["\']>', updated
        )
        if not selected or selected.group(1) != level:
            raise RuntimeError(f"Level {level} tidak terkonfirmasi")
        print(f"{level}: OK")


if __name__ == "__main__":
    main()
