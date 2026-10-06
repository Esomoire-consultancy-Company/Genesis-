import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from genesis_http import build_response, build_action_response


MAX_REQUEST_BYTES = 65536


class GenesisHandler(BaseHTTPRequestHandler):
    server_version = "Genesis/0.1"

    def do_GET(self):
        path = urlparse(self.path).path
        status, payload = build_response(path, os.environ)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/v1/genesis/warden-request":
            self._write_json(404, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self._write_json(415, {"error": "unsupported_media_type"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_json(400, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._write_json(413 if length > MAX_REQUEST_BYTES else 400, {"error": "invalid_request_size"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._write_json(400, {"error": "invalid_json"})
            return
        status, response = build_action_response("POST", path, os.environ, payload)
        self._write_json(status, response)

    def _write_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"genesis_http {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), GenesisHandler)
    print(f"Genesis bootstrap listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
