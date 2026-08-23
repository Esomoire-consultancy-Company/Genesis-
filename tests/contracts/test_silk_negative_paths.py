import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "silk"
EVENT_SCHEMA_PATH = ROOT / "contracts" / "silk" / "silk-event.schema.json"


class SilkNegativePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.denied = json.loads(
            (FIXTURE_DIR / "authority-denied-flow.json").read_text(encoding="utf-8")
        )
        cls.failure = json.loads(
            (FIXTURE_DIR / "execution-failure-compensation-flow.json").read_text(
                encoding="utf-8"
            )
        )
        cls.duplicate = json.loads(
            (FIXTURE_DIR / "duplicate-event-delivery.json").read_text(encoding="utf-8")
        )
        cls.event_schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_authority_denied_attempt_never_routes_or_executes(self):
        events = self.denied["events"]
        types = [event["event_type"] for event in events]

        self.assertEqual(types[-1], "AUTHORITY_DENIED")
        self.assertEqual(events[-1]["transition"]["to_state"], "DENIED")
        self.assertEqual(
            events[-1]["warden_decision_ref"],
            self.denied["instruction"]["warden_decision_ref"],
        )

        forbidden = {
            "ROUTE_SELECTED",
            "EXECUTION_REQUESTED",
            "EXECUTION_ACCEPTED",
            "PROVIDER_ACCEPTED",
            "SETTLEMENT_PENDING",
            "SETTLED",
            "EFFECT_OBSERVED",
            "RECONCILIATION_REQUIRED",
            "RECONCILED",
            "COMPENSATION_REQUIRED",
            "FINALIZED",
        }
        self.assertTrue(forbidden.isdisjoint(types))

    def test_execution_failure_preserves_original_authority_and_route(self):
        events = self.failure["events"]
        by_type = {event["event_type"]: event for event in events}
        decision_ref = by_type["AUTHORITY_GRANTED"]["warden_decision_ref"]
        route_ref = by_type["ROUTE_SELECTED"]["execution_route_ref"]
        failed = by_type["EXECUTION_FAILED"]

        self.assertEqual(failed["transition"]["to_state"], "FAILED")
        self.assertEqual(failed["warden_decision_ref"], decision_ref)
        self.assertEqual(failed["execution_route_ref"], route_ref)
        self.assertTrue(failed["exception_ref"])

    def test_partial_effect_requires_reconciliation_before_compensation(self):
        events = self.failure["events"]
        types = [event["event_type"] for event in events]

        observed_index = types.index("EFFECT_OBSERVED")
        reconciliation_index = types.index("RECONCILIATION_REQUIRED")
        compensation_index = types.index("COMPENSATION_REQUIRED")

        self.assertLess(observed_index, reconciliation_index)
        self.assertLess(reconciliation_index, compensation_index)

        observed = events[observed_index]
        reconciliation = events[reconciliation_index]
        compensation = events[compensation_index]

        self.assertTrue(observed["river_evidence_refs"])
        self.assertEqual(
            reconciliation["river_evidence_refs"], observed["river_evidence_refs"]
        )
        self.assertEqual(
            compensation["river_evidence_refs"], observed["river_evidence_refs"]
        )
        self.assertEqual(reconciliation["exception_ref"], compensation["exception_ref"])
        self.assertFalse(compensation["payload"]["compensation_action_authorized"])
        self.assertEqual(
            compensation["transition"]["to_state"], "COMPENSATION_REQUIRED"
        )

    def test_failure_flow_never_introduces_new_warden_authority(self):
        events = self.failure["events"]
        granted = [event for event in events if event["event_type"] == "AUTHORITY_GRANTED"]
        self.assertEqual(len(granted), 1)

        decision_ref = granted[0]["warden_decision_ref"]
        later_decision_refs = {
            event["warden_decision_ref"]
            for event in events
            if "warden_decision_ref" in event
        }
        self.assertEqual(later_decision_refs, {decision_ref})

    def test_duplicate_delivery_applies_transition_only_once(self):
        fixture = self.duplicate
        event = fixture["event"]
        seen_event_ids = set()
        state = fixture["initial_state"]
        applied = 0
        duplicates = 0
        downstream_execution_requests = 0

        for delivered_event_id in fixture["deliveries"]:
            self.assertEqual(delivered_event_id, event["event_id"])
            if delivered_event_id in seen_event_ids:
                duplicates += 1
                continue

            self.assertEqual(state, event["transition"]["from_state"])
            seen_event_ids.add(delivered_event_id)
            state = event["transition"]["to_state"]
            applied += 1
            if event["event_type"] == "EXECUTION_REQUESTED":
                downstream_execution_requests += 1

        expected = fixture["expected"]
        self.assertEqual(applied, expected["applied_transition_count"])
        self.assertEqual(duplicates, expected["duplicate_delivery_count"])
        self.assertEqual(state, expected["final_state"])
        self.assertEqual(
            downstream_execution_requests, expected["downstream_execution_requests"]
        )

    def test_negative_event_types_are_declared_by_schema(self):
        declared = set(self.event_schema["properties"]["event_type"]["enum"])
        used = {
            event["event_type"]
            for fixture in (self.denied, self.failure)
            for event in fixture["events"]
        }
        used.add(self.duplicate["event"]["event_type"])
        self.assertTrue(used.issubset(declared))

    def test_schema_contains_negative_path_guard_requirements(self):
        serialized = json.dumps(self.event_schema, sort_keys=True)
        for required_token in (
            "AUTHORITY_DENIED",
            "EXECUTION_FAILED",
            "RECONCILIATION_REQUIRED",
            "COMPENSATION_REQUIRED",
            "exception_ref",
            "warden_decision_ref",
            "river_evidence_refs",
        ):
            self.assertIn(required_token, serialized)


if __name__ == "__main__":
    unittest.main()
