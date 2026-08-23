import copy
import unittest

from runtime.nmk.alpha import AlphaRuntimeError, IdempotencyConflict
from runtime.nmk.fixture_c import FixtureCRuntime


FIXTURE_C_REQUEST = {
    "request_id": "REQ-FIXTURE-C-001",
    "idempotency_key": "fixture-c-request-001",
    "principal_ref": "DM-FACTORY-001",
    "silk_account_ref": "SA-E-FACTORY-001",
    "requested_capability": "CAP-COLD-CHAIN-TRANSPORT",
    "payload": {
        "shipment_ref": "SHIPMENT-C-001",
        "temperatures_c": [3.2, 4.8, 6.1, 7.4, 10.9, 9.6, 7.8],
    },
}


class AlphaFixtureCTests(unittest.TestCase):
    def setUp(self):
        self.runtime = FixtureCRuntime()

    def test_checkpoint_is_completed_sufficient_nonconforming_and_open(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
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
        self.assertEqual(result["settlement"]["status"], "PENDING")
        self.assertEqual(result["route"]["route_version"], 1)
        self.assertEqual(len(result["route"]["hops"]), 3)

    def test_evidence_sufficiency_is_independent_from_effect_outcome(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        state = result["fixture_c"]
        self.assertEqual(state["effect_receipt"]["evidence_status"], "SUFFICIENT")
        self.assertEqual(state["effect_receipt"]["effect_status"], "NONCONFORMING")
        self.assertEqual(state["effect_receipt"]["observed_maximum_c"], 10.9)
        self.assertEqual(len(state["effect_receipt"]["evidence_refs"]), 7)

    def test_sensor_is_not_blamed_for_truthfully_proving_transport_failure(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        effects = result["fixture_c"]["component_effects"]
        self.assertEqual(effects["SPP-COLD-SENSOR-001"], "CONFORMING")
        self.assertEqual(effects["TRANSPORT_SERVICE"], "NONCONFORMING")

    def test_nonconformance_quarantines_instead_of_auto_accepting(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        transition = result["fixture_c"]["genesis_transition"]
        self.assertEqual(transition["from_state"], "RECEIVED")
        self.assertEqual(transition["to_state"], "QUARANTINED_FOR_INSPECTION")
        self.assertNotEqual(transition["to_state"], "ACCEPTED")

    def test_observations_are_append_only_from_caller_perspective(self):
        result = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        journey_id = result["journey_id"]
        external = result["fixture_c"]["observations"]
        breach_index = next(i for i, item in enumerate(external) if item["temperature_c"] == 10.9)
        external[breach_index]["temperature_c"] = 7.9
        reread = self.runtime.get_fixture_c_journey(journey_id)
        self.assertEqual(reread["fixture_c"]["observations"][breach_index]["temperature_c"], 10.9)
        self.assertEqual(reread["statuses"]["effect"], "NONCONFORMING")

    def test_final_reconciliation_preserves_nonconforming_effect(self):
        checkpoint = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        final = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        self.assertEqual(final["statuses"]["reconciliation"], "RECONCILED")
        self.assertEqual(final["statuses"]["effect"], "NONCONFORMING")
        self.assertEqual(final["statuses"]["commercial"], "COMPILED")
        self.assertEqual(final["statuses"]["settlement"], "CONFIRMED")
        self.assertTrue(all(final["reconciliation"]["checks"].values()))
        self.assertEqual(final["fixture_c"]["exception"]["status"], "RESOLVED")
        self.assertEqual(final["fixture_c"]["compensation"]["status"], "COMPLETED")

    def test_original_commercial_event_is_preserved_after_adjustment(self):
        checkpoint = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        original = copy.deepcopy(checkpoint["fixture_c"]["commercial_history"][0])
        final = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        history = final["fixture_c"]["commercial_history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], original)
        self.assertEqual(history[0]["status"], "ADJUSTMENT_REQUIRED")
        self.assertEqual(history[1]["status"], "COMPILED")
        self.assertEqual(history[1]["supersedes_ref"], history[0]["commercial_event_id"])
        self.assertEqual(sum(a["amount"] for a in history[1]["allocations"]), 10000)

    def test_repeated_resolution_is_idempotent(self):
        checkpoint = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        first = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        event_count = len(first["event_log"])
        second = self.runtime.resolve_fixture_c(checkpoint["journey_id"])
        self.assertEqual(len(second["event_log"]), event_count)
        self.assertEqual(len(second["fixture_c"]["commercial_history"]), 2)
        self.assertEqual(first["settlement"]["settlement_id"], second["settlement"]["settlement_id"])

    def test_request_replay_and_business_payload_conflict_follow_same_alpha_rules(self):
        first = self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        replay = copy.deepcopy(FIXTURE_C_REQUEST)
        replay["request_id"] = "REQ-FIXTURE-C-RETRY"
        second = self.runtime.execute_fixture_c(replay)
        self.assertEqual(first["journey_id"], second["journey_id"])
        conflicting = copy.deepcopy(FIXTURE_C_REQUEST)
        conflicting["payload"]["temperatures_c"] = [3.2, 4.0, 5.0]
        with self.assertRaises(IdempotencyConflict):
            self.runtime.execute_fixture_c(conflicting)

    def test_fixture_requires_actual_nonconformance(self):
        conforming = copy.deepcopy(FIXTURE_C_REQUEST)
        conforming["idempotency_key"] = "fixture-c-conforming-not-allowed"
        conforming["payload"]["temperatures_c"] = [3.2, 4.0, 5.0, 7.8]
        with self.assertRaises(AlphaRuntimeError) as raised:
            self.runtime.execute_fixture_c(conforming)
        self.assertEqual(str(raised.exception), "FIXTURE_C_REQUIRES_NONCONFORMANCE")

    def test_product_licence_must_cover_institutional_hop(self):
        self.runtime.creator_licences["CL-COLD-SENSOR-001"]["eligible_arc_classes"] = {"ENTERPRISE"}
        with self.assertRaises(AlphaRuntimeError) as raised:
            self.runtime.execute_fixture_c(copy.deepcopy(FIXTURE_C_REQUEST))
        self.assertEqual(str(raised.exception), "PRODUCT_INELIGIBLE_FOR_ROUTE")


if __name__ == "__main__":
    unittest.main()
