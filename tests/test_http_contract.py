import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from genesis_http import build_response, build_action_response
from main import GenesisHandler
from genesis_warden_request import WardenRequestError


class GenesisHttpContractTests(unittest.TestCase):
    def _request_handler(self, method, body=None, headers=None):
        server = ThreadingHTTPServer(("127.0.0.1", 0), GenesisHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request(method, "/v1/genesis/warden-request", body=body, headers=headers or {})
            response = connection.getresponse()
            result = response.status, response.read()
            connection.close()
            return result
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_health_is_independent_of_database(self):
        status, payload = build_response("/health", {}, lambda host, port: False)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_readiness_reports_missing_database_configuration(self):
        status, payload = build_response("/ready", {}, lambda host, port: True)
        self.assertEqual(status, 503)
        self.assertEqual(payload["database"], "not_configured")

    def test_readiness_accepts_reachable_legacy_mysql(self):
        env = {"MYSQL_URL": "mysql://u:p@mysql.railway.internal:3306/railway"}
        status, payload = build_response("/ready", env, lambda host, port: host == "mysql.railway.internal" and port == 3306)
        self.assertEqual(status, 200)
        self.assertEqual(payload["database_provider"], "mysql")

    def test_readiness_accepts_reachable_canonical_postgres(self):
        env = {"DATABASE_URL": "postgresql://u:p@postgres.internal:5432/genesis"}
        status, payload = build_response("/ready", env, lambda host, port: host == "postgres.internal" and port == 5432)
        self.assertEqual(status, 200)
        self.assertEqual(payload["database_provider"], "postgresql")

    def test_runtime_projection_is_observational(self):
        status, payload = build_response("/v1/genesis/runtime", {
            "WARDEN_URL": "http://warden.internal",
            "RIVER_URL": "http://river.internal",
        })
        self.assertEqual(status, 200)
        self.assertFalse(payload["provider_effects"]["admitted"])

    def test_capability_registry_endpoint_is_observational(self):
        registry = {
            "schema_version": "genesis.capability-registry.r0.3",
            "registry_id": "REG-HTTP-001",
            "state": "ACTIVE",
            "providers": [],
        }
        with patch("genesis_http.load_registry", return_value=registry):
            status, payload = build_response("/v1/genesis/capabilities", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["provider_count"], 0)
        self.assertEqual(payload["execution_authority"], "NONE")

    def test_qualification_authority_endpoint_is_observational(self):
        status, payload = build_response("/v1/genesis/qualification-authority", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["authority_registry"]["state"], "ACTIVE_EMPTY")
        self.assertFalse(payload["provider_qualification"]["qualified"])
        self.assertEqual(payload["provider_qualification"]["execution_authority"], "NONE")

    def test_qualification_authority_endpoint_maps_invalid_registry_to_503(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad-authorities.json"
            p.write_text('{"schema_version":"wrong","authorities":[]}', encoding="utf-8")
            status, payload = build_response(
                "/v1/genesis/qualification-authority",
                {"GENESIS_QUALIFICATION_AUTHORITY_PATH": str(p)},
            )
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "qualification_authority_unavailable")
        self.assertEqual(payload["error"], "INVALID_AUTHORITY_REGISTRY")

    def test_warden_admission_endpoint_defaults_to_not_admitted(self):
        status, payload = build_response("/v1/genesis/warden-admission", {})
        self.assertEqual(status, 200)
        self.assertFalse(payload["admitted"])
        self.assertEqual(payload["admission_state"], "NOT_ADMITTED")
        self.assertEqual(payload["execution_authority"], "NONE")
        self.assertTrue(payload["projection_only"])
        self.assertFalse(payload["request_evaluation"])

    def test_warden_admission_projection_uses_signed_claim_scope(self):
        qualification = {"provider_id": "P1"}
        providers = {"providers": [{"provider_id": "P1", "state": "REGISTERED", "endpoint_binding_env": None}]}
        decision = {"signed_claim": {"capability_scope": ["APPLICATION_RUNTIME"]}}
        projected = {"admitted": False, "admission_state": "NOT_ADMITTED", "execution_authority": "NONE"}
        with patch("genesis_http.load_qualification", return_value=qualification), \
             patch("genesis_http.load_registry", return_value=providers), \
             patch("genesis_http.load_authority_registry", return_value={}), \
             patch("genesis_http.load_attestation", return_value=None), \
             patch("genesis_http.evaluate_attestation", return_value={"qualified": True, "capability_scope": ["APPLICATION_RUNTIME"]}), \
             patch("genesis_http.load_warden_decision", return_value=decision), \
             patch("genesis_http.load_warden_authority_registry", return_value={}), \
             patch("genesis_http.evaluate_warden_admission", return_value=projected) as evaluate:
            status, payload = build_response("/v1/genesis/warden-admission", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload, projected)
        self.assertEqual(evaluate.call_args.args[3], ["APPLICATION_RUNTIME"])

    def test_warden_admission_endpoint_fails_closed_for_malformed_decision(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad-decision.json"
            p.write_text('{"schema_version":"wrong"}', encoding="utf-8")
            status, payload = build_response(
                "/v1/genesis/warden-admission",
                {"GENESIS_WARDEN_DECISION_PATH": str(p)},
            )
        self.assertEqual(status, 200)
        self.assertFalse(payload["admitted"])
        self.assertEqual(payload["admission_state"], "NOT_ADMITTED")
        self.assertEqual(payload["reason"], "invalid_warden_decision")
        self.assertEqual(payload["execution_authority"], "NONE")

    def test_warden_request_action_is_validation_only(self):
        envelope = {"schema_version": "genesis.warden-evaluation-request.r0.8"}
        projected = {
            "request_validated": True,
            "request_state": "VALIDATED_NOT_DISPATCHED",
            "dispatch_authority": "NONE",
            "execution_authority": "NONE",
        }
        with patch("genesis_http.load_principal_authority_registry", return_value={}), \
             patch("genesis_http.load_registry", return_value={}), \
             patch("genesis_http.evaluate_warden_request", return_value=projected) as evaluate:
            status, payload = build_action_response(
                "POST", "/v1/genesis/warden-request", {}, envelope
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload, projected)
        self.assertEqual(evaluate.call_args.args[0], envelope)

    def test_warden_request_dependency_failure_is_503(self):
        with patch(
            "genesis_http.load_principal_authority_registry",
            side_effect=WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_REGISTRY"),
        ):
            status, payload = build_action_response(
                "POST", "/v1/genesis/warden-request", {}, {}
            )
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "warden_request_unavailable")
        self.assertEqual(payload["error"], "INVALID_PRINCIPAL_AUTHORITY_REGISTRY")

    def test_warden_request_rejects_wrong_method_and_route(self):
        status, payload = build_action_response("GET", "/v1/genesis/warden-request", {}, {})
        self.assertEqual(status, 405)
        self.assertEqual(payload["error"], "method_not_allowed")
        status, payload = build_action_response("POST", "/missing", {}, {})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_warden_request_http_methods_are_rejected_at_handler(self):
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                status, _ = self._request_handler(method)
                self.assertEqual(status, 405)

    def test_warden_request_http_rejects_ambiguous_or_nonstandard_json(self):
        headers = {"Content-Type": "application/json"}
        for body in (b'{"schema_version":"a","schema_version":"b"}', b'{"value":NaN}'):
            with self.subTest(body=body):
                status, _ = self._request_handler("POST", body=body, headers=headers)
                self.assertEqual(status, 400)

    def test_warden_request_http_rejects_transfer_encoding(self):
        status, _ = self._request_handler(
            "POST",
            body=b"{}",
            headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
        )
        self.assertEqual(status, 400)

    def test_unknown_route_returns_404(self):
        status, payload = build_response("/missing", {}, lambda host, port: False)
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
