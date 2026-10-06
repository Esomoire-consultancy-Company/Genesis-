import http.client
import json
import threading
import unittest
from unittest.mock import patch

from http.server import ThreadingHTTPServer

from main import GenesisHandler


class GenesisServerIngressTests(unittest.TestCase):
    def _request_once(self, method, path, body=None, headers=None):
        server = ThreadingHTTPServer(("127.0.0.1", 0), GenesisHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            payload = response.read()
            conn.close()
            thread.join(timeout=3)
            return response.status, json.loads(payload) if payload else None
        finally:
            server.server_close()

    def test_post_warden_request_reaches_action_boundary(self):
        projected = {
            "request_validated": True,
            "request_state": "VALIDATED_NOT_DISPATCHED",
            "execution_authority": "NONE",
            "dispatch_authority": "NONE",
        }
        with patch("main.build_action_response", return_value=(200, projected)) as action:
            status, payload = self._request_once(
                "POST",
                "/v1/genesis/warden-request",
                body=json.dumps({"schema_version": "genesis.warden-evaluation-request.r0.8"}),
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload, projected)
        self.assertEqual(action.call_args.args[0], "POST")

    def test_excessive_json_nesting_returns_400(self):
        deep = "[" * 1100 + "0" + "]" * 1100
        status, payload = self._request_once(
            "POST",
            "/v1/genesis/warden-request",
            body=deep,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_json")

    def test_overlong_json_integer_returns_400(self):
        status, payload = self._request_once(
            "POST",
            "/v1/genesis/warden-request",
            body="9" * 5000,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid_json")

    def test_get_warden_request_is_method_not_allowed(self):
        status, payload = self._request_once("GET", "/v1/genesis/warden-request")
        self.assertEqual(status, 405)
        self.assertEqual(payload["error"], "method_not_allowed")


if __name__ == "__main__":
    unittest.main()
