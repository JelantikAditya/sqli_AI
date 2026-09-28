"""Token-gated proxy for temporary Colab access to the local DVWA lab."""

import hmac
import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


TOKEN = os.environ.get("LAB_TOKEN", "")
if len(TOKEN) < 32:
    raise SystemExit("LAB_TOKEN must be at least 32 characters")

HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "x-lab-token",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.forward()

    def do_HEAD(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        # The token is checked before any request reaches intentionally vulnerable DVWA.
        supplied = self.headers.get("X-Lab-Token", "")
        if not hmac.compare_digest(supplied, TOKEN):
            self.send_error(403, "Lab token required")
            return

        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            self.send_error(400, "Relative paths only")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self.send_error(413, "Request too large")
            return
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        headers["Host"] = "dvwa"

        connection = http.client.HTTPConnection("dvwa", 80, timeout=30)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (OSError, http.client.HTTPException):
            self.send_error(502, "DVWA unavailable")
        finally:
            connection.close()


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
