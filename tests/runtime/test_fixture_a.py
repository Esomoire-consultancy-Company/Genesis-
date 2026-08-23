import unittest

from runtime.nmk.alpha import AlphaRuntime, AuthorityDenied, IdempotencyConflict


FIXTURE_A_REQUEST = {
    "request_id": "REQ-FIXTURE-A-001",
    "idempotency_key": "fixture-a-request-001",
    "principal_ref": "DM-FACTORY-001",
    "silk_account_ref": "SA-E-FACTORY-001",
    "requested_capability": "CAP-ROUTE-OPTIMIZATION",
    "payload": {
        "origin": "LOCATION-A",
        "destination": "LOCATION-B",
    },
}


class AlphaFixtureATests(unittest.TestCase):
    def setUp(self):
        self.runtime = AlphaRuntime()

    def test_fixture_a_reconciles_with_expected_orthogonal_statuses(self):
        result = self.runtime.execute_fixture_a(dict(FIXTURE_A_REQUEST))

        self.assertEqual(
            result["statuses"],
            {
                "lifecycle": "COMPLETE",
                "authority": "AUTHORIZED",
                "execution": "COMPLETED",
                "evidence": "SUFFICIENT",
                "effect": "CONFORMING",
                "commercial": "COMPILED",
                "settlement": "CONFIRMED",
                "reconciliation": "RECONCILED",
            },
        )
        self.assertEqual(result["route"]["route_version"], 1)
        self.assertEqual(len(result["route"]["hops"]), 2)
        self.assertEqual(result["route"]["product_ref"], "SPP-ROUTE-001")
        self.assertEqual(
            sum(a["amount"] for a in result["commercial_event"]["allocations"]),
            result["commercial_event"]["gross_value"],
        )
        self.assertTrue(all(result["reconciliation"]["checks"].values()))

    def test_every_material_event_is_bound_to_same_journey(self):
        result = self.runtime.execute_fixture_a(dict(FIXTURE_A_REQUEST))
        journey_id = result["journey_id"]

        self.assertGreaterEqual(len(result["event_log"]), 12)
        self.assertTrue(
            all(event["journey_id"] == journey_id for event in result["event_log"])
        )
        event_types = [event["event_type"] for event in result["event_log"]]
        self.assertLess(
            event_types.index("silk.route.proposed"),
            event_types.index("silk.route.authorized"),
        )
        self.assertLess(
            event_types.index("silk.route.authorized"),
            event_types.index("synnergyze.execution.started"),
        )
        self.assertLess(
            event_types.index("river.effect.verified"),
            event_types.index("commercial.event.compiled"),
        )

    def test_replaying_identical_request_returns_same_journey_without_duplicate_value(self):
        first = self.runtime.execute_fixture_a(dict(FIXTURE_A_REQUEST))
        second = self.runtime.execute_fixture_a(dict(FIXTURE_A_REQUEST))

        self.assertEqual(first["journey_id"], second["journey_id"])
        self.assertEqual(
            first["commercial_event"]["commercial_event_id"],
            second["commercial_event"]["commercial_event_id"],
        )
        self.assertEqual(len(first["event_log"]), len(second["event_log"]))

    def test_same_idempotency_key_with_different_request_is_rejected(self):
        self.runtime.execute_fixture_a(dict(FIXTURE_A_REQUEST))
        conflicting = dict(FIXTURE_A_REQUEST)
        conflicting["request_id"] = "REQ-FIXTURE-A-002"

        with self.assertRaises(IdempotencyConflict):
            self.runtime.execute_fixture_a(conflicting)

    def test_individual_account_cannot_invoke_enterprise_only_capability(self):
        denied = dict(FIXTURE_A_REQUEST)
        denied["silk_account_ref"] = "SA-I-FACTORY-001"
        denied["idempotency_key"] = "fixture-a-personal-account"

        with self.assertRaises(AuthorityDenied) as raised:
            self.runtime.execute_fixture_a(denied)

        self.assertEqual(str(raised.exception), "ENTERPRISE_ACCOUNT_REQUIRED")

    def test_creator_is_not_a_silk_account_class(self):
        account_classes = {row["account_class"] for row in self.runtime.accounts.values()}
        self.assertNotIn("CREATOR", account_classes)
        self.assertEqual(account_classes, {"INDIVIDUAL", "ENTERPRISE"})


if __name__ == "__main__":
    unittest.main()
