import unittest
from unittest.mock import patch

from genesis_http import build_response


class GenesisHttpContractTests(unittest.TestCase):
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

    def test_unknown_route_returns_404(self):
        status, payload = build_response("/missing", {}, lambda host, port: False)
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
