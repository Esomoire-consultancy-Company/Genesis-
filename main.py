import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from genesis_http import build_response, build_action_response


MAX_REQUEST_BYTES = 65536
MAX_JSON_DEPTH = 64
REQUEST_READ_TIMEOUT_SECONDS = 5.0


def _json_depth_exceeds(value, limit=MAX_JSON_DEPTH):
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            return True
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return False


class GenesisHandler(BaseHTTPRequestHandler):
    server_version = "Genesis/0.1"

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/genesis/warden-request":
            status, payload = build_action_response("GET", path, os.environ, {})
        else:
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
        if self.headers.get("Transfer-Encoding") is not None:
            self._write_json(400, {"error": "invalid_transfer_encoding"})
            return
        if self.headers.get_content_type() != "application/json":
            self._write_json(415, {"error": "unsupported_media_type"})
            return
        content_lengths = self.headers.get_all("Content-Length", [])
        if len(content_lengths) != 1:
            self._write_json(400, {"error": "invalid_content_length"})
            return
        content_length = content_lengths[0]
        if not content_length.isascii() or not content_length.isdecimal():
            self._write_json(400, {"error": "invalid_content_length"})
            return
        try:
            length = int(content_length)
        except ValueError:
            self._write_json(400, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._write_json(413 if length > MAX_REQUEST_BYTES else 400, {"error": "invalid_request_size"})
            return
        try:
            self.connection.settimeout(REQUEST_READ_TIMEOUT_SECONDS)
            payload = json.loads(
                self.rfile.read(length),
                object_pairs_hook=self._reject_duplicate_json_keys,
                parse_constant=self._reject_json_constant,
            )
        except socket.timeout:
            self._write_json(408, {"error": "request_timeout"})
            return
        except (ValueError, UnicodeDecodeError, RecursionError):
            self._write_json(400, {"error": "invalid_json"})
            return
        if _json_depth_exceeds(payload):
            self._write_json(400, {"error": "invalid_json"})
            return
        status, response = build_action_response("POST", path, os.environ, payload)
        self._write_json(status, response)

    @staticmethod
    def _reject_duplicate_json_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    @staticmethod
    def _reject_json_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    def _unsupported_action_method(self, method):
        path = urlparse(self.path).path
        status, payload = build_action_response(method, path, os.environ, {})
        self._write_json(status, payload)

    def do_PUT(self):
        self._unsupported_action_method("PUT")

    def do_PATCH(self):
        self._unsupported_action_method("PATCH")

    def do_DELETE(self):
        self._unsupported_action_method("DELETE")

    def do_OPTIONS(self):
        self._unsupported_action_method("OPTIONS")

    def do_HEAD(self):
        path = urlparse(self.path).path
        status, payload = build_action_response("HEAD", path, os.environ, {})
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

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
