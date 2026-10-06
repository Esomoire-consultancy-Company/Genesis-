import unittest

from genesis_contract import db_target_from_env, service_status
from genesis_runtime import provider_effect_admission, runtime_projection


class GenesisContractTests(unittest.TestCase):
    def test_service_status_declares_r07_as_additive(self):
        status = service_status()
        self.assertEqual(status["service"], "genesis")
        self.assertEqual(status["phase"], "warden-admission-decision-contract")
        self.assertEqual(status["version"], "0.7.0")
        for capability in (
            "runtime-projection",
            "provider-binding-resolution",
            "capability-registry",
            "capability-candidate-resolution",
            "provider-provenance",
            "dependency-exit-metadata",
            "warden-admission-projection",
            "provider-qualification-evaluation",
            "qualification-authority-registry",
            "ed25519-qualification-attestation-verification",
            "warden-qualification-eligibility-projection",
            "warden-admission-decision-evaluation",
            "scoped-admission-projection",
        ):
            self.assertIn(capability, status["capabilities"])

    def test_database_url_prefers_postgres_canonical_binding(self):
        target = db_target_from_env({
            "DATABASE_URL": "postgresql://user:pass@postgres.railway.internal:5432/genesis",
            "MYSQL_URL": "mysql://user:pass@mysql.railway.internal:3306/legacy",
        })
        self.assertEqual(target.provider, "postgresql")
        self.assertEqual(target.host, "postgres.railway.internal")
        self.assertEqual(target.port, 5432)
        self.assertEqual(target.database, "genesis")

    def test_mysql_url_remains_backward_compatible(self):
        target = db_target_from_env({"MYSQL_URL": "mysql://user:pass@mysql.railway.internal:3306/railway"})
        self.assertEqual(target.provider, "mysql")

    def test_provider_effects_fail_closed_without_warden(self):
        admitted, reason = provider_effect_admission({"RIVER_URL": "http://river.internal"})
        self.assertEqual((admitted, reason), (False, "warden_not_configured"))

    def test_provider_effects_require_explicit_warden_enforcement(self):
        admitted, reason = provider_effect_admission({
            "WARDEN_URL": "http://warden.internal", "RIVER_URL": "http://river.internal"
        })
        self.assertEqual((admitted, reason), (False, "warden_effect_admission_not_enforced"))

    def test_provider_effects_require_river_evidence_path(self):
        admitted, reason = provider_effect_admission({
            "WARDEN_URL": "http://warden.internal", "WARDEN_EFFECT_ADMISSION": "REQUIRED"
        })
        self.assertEqual((admitted, reason), (False, "river_not_configured"))

    def test_runtime_projection_never_exposes_credentials(self):
        projection = runtime_projection({
            "DATABASE_URL": "postgresql://secret-user:secret-pass@db.internal:5432/genesis",
        })
        self.assertNotIn("secret-user", repr(projection))
        self.assertNotIn("secret-pass", repr(projection))


if __name__ == "__main__":
    unittest.main()
