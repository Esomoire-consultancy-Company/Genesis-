import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from silk.nmk_alpha import (  # noqa: E402
    AlphaRuntimeError,
    AuthorityDenied,
    IdempotencyConflict,
    NmkAlphaRuntime,
)


FIXTURE_A = {
    "request_id": "REQ-A-1",
    "idempotency_key": "idem-a-1",
    "principal_ref": "digitalme:factory",
    "silk_account_ref": "silk:account:factory",
    "requested_capability": "CAP_ROUTE_OPTIMIZATION",
    "payload": {"origin": "A", "destination": "B"},
}

FIXTURE_C = {
    "request_id": "REQ-C-1",
    "idempotency_key": "idem-c-1",
    "principal_ref": "digitalme:factory",
    "silk_account_ref": "silk:account:factory",
    "requested_capability": "CAP_COLD_CHAIN_TRANSPORT",
    "payload": {"temperatures_c": [3.2, 4.8, 7.4, 10.9, 9.6, 7.8]},
}


class NmkAlphaReferenceTests(unittest.TestCase):
    def setUp(self):
        self.runtime = NmkAlphaRuntime()

    def test_live_account_taxonomy_is_preserved(self):
        classes = {value[0] for value in self.runtime.accounts.values()}
        self.assertEqual(classes, {"INDIVIDUAL_STUDENT", "ENTERPRISE", "INSTITUTIONAL"})
        self.assertNotIn("CREATOR", classes)

    def test_fixture_a_executes_and_reconciles(self):
        result = self.runtime.execute_fixture_a(copy.deepcopy(FIXTURE_A))
        self.assertEqual(result["statuses"]["reconciliation"], "RECONCILED")
        self.assertEqual(result["statuses"]["effect"], "CONFORMING")
        self.assertEqual(result["statuses"]["settlement"], "CONFIRMED")
        self.assertEqual(result["settlement"]["outcome"], "SETTLED")
        self.assertEqual(len(result["route"]["hops"]), 2)
        self.assertTrue(all(result["reconciliation"]["checks"].values()))

    def test_fixture_a_replay_returns_same_journey_without_duplicate_events(self):
        first = self.runtime.execute_fixture_a(copy.deepcopy(FIXTURE_A))
        replay = copy.deepcopy(FIXTURE_A)
        replay["request_id"] = "REQ-A-RETRY"
        second = self.runtime.execute_fixture_a(replay)
        self.assertEqual(first["journey_id"], second["journey_id"])
        self.assertEqual(len(first["event_log"]), len(second["event_log"]))

    def test_reused_idempotency_key_with_changed_business_payload_is_rejected(self):
        self.runtime.execute_fixture_a(copy.deepcopy(FIXTURE_A))
        conflict = copy.deepcopy(FIXTURE_A)
        conflict["payload"]["destination"] = "C"
        with self.assertRaises(IdempotencyConflict):
            self.runtime.execute_fixture_a(conflict)

    def test_enterprise_only_request_cannot_enter_through_individual_account(self):
        denied = copy.deepcopy(FIXTURE_A)
        denied["silk_account_ref"] = "silk:account:individual"
        denied["idempotency_key"] = "personal-route-request"
        with self.assertRaises(AuthorityDenied):
            self.runtime.execute_fixture_a(denied)

    def test_fixture_c_checkpoint_separates_evidence_from_effect(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C))
        self.assertEqual(
            result["statuses"],
            {
                "lifecycle": "COMPLETE",
                "authority": "AUTHORIZED",
                "execution": "COMPLETED",
                "evidence": "SUFFICIENT",
                "effect": "NONCONFORMING",
                "commercial": "ADJUSTMENT_REQUIRED",
                "settlement": "PENDING",
                "reconciliation": "OPEN",
            },
        )
        self.assertEqual(result["effect_receipt"]["evidence_status"], "SUFFICIENT")
        self.assertEqual(result["effect_receipt"]["effect_status"], "NONCONFORMING")
        self.assertEqual(result["effect_receipt"]["observed_maximum_c"], 10.9)
        self.assertEqual(result["genesis_state"], "QUARANTINED_FOR_INSPECTION")
        self.assertEqual(result["projections"]["operational"]["sensor_effect"], "CONFORMING")
        self.assertEqual(len(result["route"]["hops"]), 3)

    def test_returned_evidence_snapshot_cannot_rewrite_internal_observation(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C))
        breach = next(item for item in result["evidence"] if item["temperature_c"] == 10.9)
        breach["temperature_c"] = 7.9
        reread = self.runtime.get_journey(result["journey_id"])
        self.assertIn(10.9, [item["temperature_c"] for item in reread["evidence"]])
        self.assertEqual(reread["statuses"]["effect"], "NONCONFORMING")

    def test_fixture_c_requires_real_nonconformance(self):
        conforming = copy.deepcopy(FIXTURE_C)
        conforming["idempotency_key"] = "fixture-c-conforming"
        conforming["payload"]["temperatures_c"] = [3.2, 4.0, 5.0, 7.8]
        with self.assertRaises(AlphaRuntimeError) as raised:
            self.runtime.execute_fixture_c(conforming)
        self.assertEqual(str(raised.exception), "FIXTURE_C_REQUIRES_NONCONFORMANCE")

    def test_cold_sensor_product_must_cover_institutional_hop(self):
        licence, capabilities, _ = self.runtime.products["product:cold-sensor"]
        self.runtime.products["product:cold-sensor"] = (
            licence,
            capabilities,
            {"ENTERPRISE"},
        )
        with self.assertRaises(AlphaRuntimeError) as raised:
            self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C))
        self.assertEqual(str(raised.exception), "PRODUCT_INELIGIBLE_FOR_ROUTE")

    def test_fixture_c_reconciles_without_rewriting_nonconforming_effect(self):
        checkpoint = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C))
        final = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        self.assertEqual(final["statuses"]["effect"], "NONCONFORMING")
        self.assertEqual(final["statuses"]["reconciliation"], "RECONCILED")
        self.assertEqual(final["statuses"]["settlement"], "CONFIRMED")
        self.assertEqual(final["settlement"]["outcome"], "SETTLED")
        self.assertEqual(final["exception"]["status"], "RESOLVED")
        self.assertEqual(final["compensation"]["status"], "COMPLETED")
        self.assertEqual(len(final["commercial_history"]), 2)
        self.assertEqual(
            final["commercial_history"][1]["supersedes_ref"],
            final["commercial_history"][0]["commercial_event_id"],
        )
        self.assertEqual(
            final["projections"]["vsr"]["economic_fact_ref"],
            final["projections"]["empire"]["economic_fact_ref"],
        )
        self.assertTrue(all(final["reconciliation"]["checks"].values()))

    def test_fixture_c_resolution_is_idempotent(self):
        checkpoint = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C))
        first = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        event_count = len(first["event_log"])
        second = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        self.assertEqual(event_count, len(second["event_log"]))
        self.assertEqual(len(second["commercial_history"]), 2)
        self.assertEqual(
            first["settlement"]["provider_result_id"],
            second["settlement"]["provider_result_id"],
        )


if __name__ == "__main__":
    unittest.main()
