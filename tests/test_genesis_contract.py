import unittest

from genesis_contract import db_target_from_env, service_status
from genesis_runtime import provider_effect_admission, runtime_projection


class GenesisContractTests(unittest.TestCase):
    def test_service_status_declares_r02_contract(self):
        status = service_status()
        self.assertEqual(status["service"], "genesis")
        self.assertEqual(status["phase"], "provider-flexible-bootstrap")
        self.assertEqual(status["version"], "0.2.0")
        self.assertIn("registry", status["capabilities"])
        self.assertIn("runtime-projection", status["capabilities"])

    def test_database_url_prefers_postgres_canonical_binding(self):
        target = db_target_from_env({
            "DATABASE_URL": "postgresql://user:pass@postgres.railway.internal:5432/genesis",
            "MYSQL_URL": "mysql://user:pass@mysql.railway.internal:3306/legacy",
        })
        self.assertEqual(target.provider, "postgresql")
        self.assertEqual(target.host, "postgres.railway.internal")
        self.assertEqual(target.port, 5432)
        self.assertEqual(target.database, "genesis")
        self.assertEqual(target.source, "DATABASE_URL")

    def test_mysql_url_remains_backward_compatible(self):
        target = db_target_from_env({"MYSQL_URL": "mysql://user:pass@mysql.railway.internal:3306/railway"})
        self.assertEqual(target.provider, "mysql")
        self.assertEqual(target.host, "mysql.railway.internal")
        self.assertEqual(target.port, 3306)
        self.assertEqual(target.database, "railway")

    def test_mysql_component_variables_are_supported(self):
        target = db_target_from_env({
            "MYSQLHOST": "db.internal",
            "MYSQLPORT": "3307",
            "MYSQLDATABASE": "genesis",
        })
        self.assertEqual(target.host, "db.internal")
        self.assertEqual(target.port, 3307)
        self.assertEqual(target.database, "genesis")

    def test_provider_effects_fail_closed_without_warden(self):
        admitted, reason = provider_effect_admission({"RIVER_URL": "http://river.internal"})
        self.assertFalse(admitted)
        self.assertEqual(reason, "warden_not_configured")

    def test_provider_effects_require_explicit_warden_enforcement(self):
        admitted, reason = provider_effect_admission({
            "WARDEN_URL": "http://warden.internal",
            "RIVER_URL": "http://river.internal",
        })
        self.assertFalse(admitted)
        self.assertEqual(reason, "warden_effect_admission_not_enforced")

    def test_provider_effects_require_river_evidence_path(self):
        admitted, reason = provider_effect_admission({
            "WARDEN_URL": "http://warden.internal",
            "WARDEN_EFFECT_ADMISSION": "REQUIRED",
        })
        self.assertFalse(admitted)
        self.assertEqual(reason, "river_not_configured")

    def test_governed_effect_path_requires_all_bindings(self):
        admitted, reason = provider_effect_admission({
            "WARDEN_URL": "http://warden.internal",
            "RIVER_URL": "http://river.internal",
            "WARDEN_EFFECT_ADMISSION": "REQUIRED",
        })
        self.assertTrue(admitted)
        self.assertEqual(reason, "governed_effect_path_configured")

    def test_runtime_projection_never_exposes_credentials(self):
        projection = runtime_projection({
            "DATABASE_URL": "postgresql://secret-user:secret-pass@db.internal:5432/genesis",
            "WARDEN_URL": "http://warden.internal",
        })
        serialized = repr(projection)
        self.assertNotIn("secret-user", serialized)
        self.assertNotIn("secret-pass", serialized)


if __name__ == "__main__":
    unittest.main()
