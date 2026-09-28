"""Check that the public tunnel blocks requests without the lab token."""

import pathlib
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> None:
    url = sys.argv[1].rstrip("/") + "/login.php"
    token = (pathlib.Path(__file__).parent / ".env").read_text().split("=", 1)[1].strip()

    try:
        urllib.request.urlopen(url, timeout=20)
    except urllib.error.HTTPError as error:
        if error.code != 403:
            raise RuntimeError(f"Unexpected unauthenticated status: {error.code}")
        print("Without token: 403 OK")
    else:
        raise RuntimeError("Tunnel accepted a request without the token")

    request = urllib.request.Request(url, headers={"X-Lab-Token": token})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", "replace")
        if response.status != 200 or "DVWA" not in body:
            raise RuntimeError("Token accepted but DVWA login page not found")
        print("With token: 200 DVWA OK")

    # Verify a real authenticated session survives the tunnel and proxy.
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    opener.addheaders = [("X-Lab-Token", token)]
    login = opener.open(url, timeout=20).read().decode("utf-8", "replace")
    match = re.search(r"name=['\"]user_token['\"] value=['\"]([0-9a-f]+)", login)
    if not match:
        raise RuntimeError("DVWA login token not found through tunnel")
    data = urllib.parse.urlencode(
        {"username": "admin", "password": "password", "Login": "Login", "user_token": match.group(1)}
    ).encode()
    with opener.open(url, data, timeout=20) as response:
        page = response.read().decode("utf-8", "replace")
        if "security.php" not in page:
            raise RuntimeError("DVWA login did not persist through tunnel")
        print("Login session through tunnel: OK")


if __name__ == "__main__":
    main()
