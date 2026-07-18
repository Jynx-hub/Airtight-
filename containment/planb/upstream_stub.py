"""A stand-in for the services ALLOWed egress reaches (patent search, the inference
gateway). It lives on the external network only — the sandbox cannot reach it
directly, only through the gate. Any 200 from here proves the gate forwarded an
allowed request end-to-end."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _ok(self):
        body = json.dumps({"upstream": "ok", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._ok()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self._ok()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"[upstream] stub on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Stub).serve_forever()
