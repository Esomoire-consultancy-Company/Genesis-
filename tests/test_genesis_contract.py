import unittest

from genesis_contract import db_target_from_env, service_status


class GenesisContractTests(unittest.TestCase):
    def test_service_status_declares_bootstrap_contract(self):
        status = service_status()
        self.assertEqual(status["service"], "genesis")
        self.assertEqual(status["phase"], "bootstrap")
        self.assertEqual(status["version"], "0.1.0")
        self.assertIn("registry", status["capabilities"])

    def test_mysql_url_resolves_private_database_target(self):
        target = db_target_from_env({"MYSQL_URL": "mysql://user:pass@mysql.railway.internal:3306/railway"})
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


if __name__ == "__main__":
    unittest.main()
