import unittest

from genesis_http import build_response


class GenesisHttpContractTests(unittest.TestCase):
    def test_health_is_independent_of_database(self):
        status, payload = build_response("/health", {}, lambda host, port: False)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_readiness_reports_missing_database_configuration(self):
        status, payload = build_response("/ready", {}, lambda host, port: True)
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["database"], "not_configured")

    def test_readiness_accepts_reachable_private_mysql(self):
        env = {"MYSQL_URL": "mysql://u:p@mysql.railway.internal:3306/railway"}
        status, payload = build_response("/ready", env, lambda host, port: host == "mysql.railway.internal" and port == 3306)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["database"], "reachable")

    def test_unknown_route_returns_404(self):
        status, payload = build_response("/missing", {}, lambda host, port: False)
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
