import json
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "silk" / "entitlement-grant-flow.json"
EVENT_SCHEMA_PATH = ROOT / "contracts" / "silk" / "silk-event.schema.json"
INSTRUCTION_SCHEMA_PATH = ROOT / "contracts" / "silk" / "silk-instruction.schema.json"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SilkEventContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.events = cls.fixture["events"]
        cls.instruction = cls.fixture["instruction"]
        cls.event_schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.instruction_schema = json.loads(INSTRUCTION_SCHEMA_PATH.read_text(encoding="utf-8"))

        Draft202012Validator.check_schema(cls.event_schema)
        Draft202012Validator.check_schema(cls.instruction_schema)
        checker = FormatChecker()
        cls.event_validator = Draft202012Validator(
            cls.event_schema, format_checker=checker
        )
        cls.instruction_validator = Draft202012Validator(
            cls.instruction_schema, format_checker=checker
        )

    def test_fixture_validates_against_contract_schemas(self):
        self.instruction_validator.validate(self.instruction)
        for event in self.events:
            self.event_validator.validate(event)

    def test_fixture_is_non_monetary_entitlement_flow(self):
        self.assertEqual(self.instruction["instruction_type"], "ENTITLEMENT_GRANT")
        self.assertEqual(self.instruction["value"]["kind"], "RIGHT")
        self.assertNotIn("provider_binding_ref", self.instruction)
        self.assertNotIn("currency", self.instruction["value"])

    def test_event_ids_are_unique_and_correlation_is_stable(self):
        event_ids = [event["event_id"] for event in self.events]
        correlation_ids = {event["correlation_id"] for event in self.events}

        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(correlation_ids, {"silk:correlation:test:entitlement-001"})

    def test_causation_chain_is_contiguous(self):
        for previous, current in zip(self.events, self.events[1:]):
            self.assertEqual(current.get("causation_id"), previous["event_id"])
            self.assertEqual(
                current["transition"]["from_state"],
                previous["transition"]["to_state"],
            )

    def test_event_times_are_monotonic_and_instruction_covers_final_event(self):
        event_times = [_parse_datetime(event["occurred_at"]) for event in self.events]
        self.assertEqual(event_times, sorted(event_times))
        self.assertLessEqual(
            _parse_datetime(self.instruction["created_at"]), event_times[0]
        )
        self.assertGreaterEqual(
            _parse_datetime(self.instruction["updated_at"]), event_times[-1]
        )

    def test_execution_occurs_only_after_warden_authority(self):
        types = [event["event_type"] for event in self.events]
        authority_index = types.index("AUTHORITY_GRANTED")
        execution_index = types.index("EXECUTION_REQUESTED")

        self.assertLess(authority_index, execution_index)

        decision_ref = self.events[authority_index]["warden_decision_ref"]
        execution_event = self.events[execution_index]
        self.assertEqual(execution_event["warden_decision_ref"], decision_ref)
        self.assertTrue(execution_event["execution_route_ref"])

    def test_non_monetary_path_skips_provider_and_settlement_states(self):
        forbidden_event_types = {"PROVIDER_ACCEPTED", "SETTLEMENT_PENDING", "SETTLED"}
        observed_types = {event["event_type"] for event in self.events}
        observed_states = {
            state
            for event in self.events
            for state in (
                event["transition"]["from_state"],
                event["transition"]["to_state"],
            )
        }

        self.assertTrue(forbidden_event_types.isdisjoint(observed_types))
        self.assertTrue(
            {"PROVIDER_ACCEPTED", "SETTLEMENT_PENDING", "SETTLED"}.isdisjoint(
                observed_states
            )
        )
        self.assertTrue(all("provider_result_ref" not in event for event in self.events))

    def test_river_evidence_precedes_reconciliation_and_finalization(self):
        types = [event["event_type"] for event in self.events]
        observed_index = types.index("EFFECT_OBSERVED")
        reconciled_index = types.index("RECONCILED")
        finalized_index = types.index("FINALIZED")

        self.assertLess(observed_index, reconciled_index)
        self.assertLess(reconciled_index, finalized_index)

        for index in (observed_index, reconciled_index, finalized_index):
            self.assertTrue(self.events[index]["river_evidence_refs"])

        self.assertEqual(self.events[finalized_index]["transition"]["to_state"], "FINAL")

    def test_fixture_event_types_are_declared_by_event_schema(self):
        declared = set(self.event_schema["properties"]["event_type"]["enum"])
        used = {event["event_type"] for event in self.events}
        self.assertTrue(used.issubset(declared))

    def test_fixture_states_are_declared_by_both_contracts(self):
        event_states = set(self.event_schema["$defs"]["state"]["enum"])
        instruction_states = set(
            self.instruction_schema["properties"]["state"]["enum"]
        )
        used_states = {
            state
            for event in self.events
            for state in (
                event["transition"]["from_state"],
                event["transition"]["to_state"],
            )
        }

        self.assertTrue(used_states.issubset(event_states))
        self.assertTrue(used_states.issubset(instruction_states))


if __name__ == "__main__":
    unittest.main()
