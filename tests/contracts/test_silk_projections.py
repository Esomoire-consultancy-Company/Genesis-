import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from silk.projections import ProjectionError, build_economic_fact, build_projection_pair  # noqa: E402
from silk.sandbox_provider import SandboxProviderAdapter  # noqa: E402


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "silk" / "sandbox-payment-request.json"
CONTRACT_DIR = ROOT / "contracts" / "silk"


def _schema(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def _dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _final_event(instruction: dict, river_ref: str) -> dict:
    return {
        "event_id": "silk:event:test:projection:final",
        "event_type": "FINALIZED",
        "instruction_ref": instruction["silk_instruction_id"],
        "principal_ref": instruction["principal_ref"],
        "silk_account_ref": instruction["silk_account_ref"],
        "correlation_id": "silk:correlation:test:projection-001",
        "occurred_at": "2026-08-23T05:40:00Z",
        "actor": {"actor_class": "SILK", "actor_ref": "silk:test:rail"},
        "transition": {"from_state": "RECONCILED", "to_state": "FINAL"},
        "warden_decision_ref": instruction["warden_decision_ref"],
        "river_evidence_refs": [river_ref],
        "version": "R0.1",
    }


class SilkProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.instruction = fixture["instruction"]
        cls.binding = fixture["provider_binding"]

        checker = FormatChecker()
        cls.fact_validator = Draft202012Validator(
            _schema("silk-economic-fact.schema.json"), format_checker=checker
        )
        cls.projection_validator = Draft202012Validator(
            _schema("silk-projection.schema.json"), format_checker=checker
        )
        cls.event_validator = Draft202012Validator(
            _schema("silk-event.schema.json"), format_checker=checker
        )

    def _settled_result(self):
        adapter = SandboxProviderAdapter()
        accepted = adapter.accept(
            self.instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z")
        )
        return adapter.settle(accepted, as_of=_dt("2026-08-23T05:32:00Z"))

    def test_one_final_fact_builds_two_projections_with_same_truth_refs(self):
        settled = self._settled_result()
        final_event = _final_event(
            self.instruction, "river:receipt:test:projection-payment-001"
        )
        self.event_validator.validate(final_event)

        fact = build_economic_fact(self.instruction, settled, final_event)
        self.fact_validator.validate(fact)

        vsr, empire = build_projection_pair(fact)
        self.projection_validator.validate(vsr)
        self.projection_validator.validate(empire)

        for field in (
            "economic_fact_ref",
            "instruction_ref",
            "source_fingerprint",
            "provider_result_ref",
            "river_evidence_refs",
            "value",
            "finalized_at",
        ):
            self.assertEqual(vsr[field], empire[field])

        self.assertEqual(vsr["projection_kind"], "VSR")
        self.assertEqual(empire["projection_kind"], "EMPIRE")
        self.assertEqual(vsr["payload"]["participation_effect"], "VALUE_TRANSFER")
        self.assertEqual(empire["payload"]["financial_effect"], "OUTFLOW")
        self.assertEqual(vsr["value"], {"amount": "1000.00", "currency": "INR"})
        self.assertEqual(empire["value"], {"amount": "1000.00", "currency": "INR"})

    def test_vsr_preserves_federation_arcs_from_same_fact(self):
        settled = self._settled_result()
        fact = build_economic_fact(
            self.instruction,
            settled,
            _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
        )
        vsr, _ = build_projection_pair(fact)
        self.assertEqual(
            vsr["payload"]["arc_refs"],
            ["arc:test:factory-logistics", "arc:test:logistics-institution"],
        )

    def test_empire_preserves_same_counterparty_and_obligation(self):
        settled = self._settled_result()
        fact = build_economic_fact(
            self.instruction,
            settled,
            _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
        )
        _, empire = build_projection_pair(fact)
        self.assertEqual(empire["payload"]["counterparty_ref"], self.instruction["counterparty_ref"])
        self.assertEqual(
            empire["payload"]["obligation_ref"], self.instruction["right_or_obligation_ref"]
        )

    def test_projection_refuses_unsettled_provider_result(self):
        adapter = SandboxProviderAdapter()
        accepted = adapter.accept(
            self.instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z")
        )
        with self.assertRaises(ProjectionError):
            build_economic_fact(
                self.instruction,
                accepted,
                _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
            )

    def test_projection_refuses_provider_value_drift(self):
        settled = self._settled_result()
        settled["value"]["amount"] = "999.00"
        with self.assertRaises(ProjectionError):
            build_economic_fact(
                self.instruction,
                settled,
                _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
            )

    def test_projection_refuses_final_without_river_evidence(self):
        settled = self._settled_result()
        event = _final_event(self.instruction, "river:receipt:test:projection-payment-001")
        event["river_evidence_refs"] = []
        with self.assertRaises(ProjectionError):
            build_economic_fact(self.instruction, settled, event)

    def test_projection_refuses_warden_lineage_drift(self):
        settled = self._settled_result()
        settled["warden_decision_ref"] = "warden:decision:test:other"
        with self.assertRaises(ProjectionError):
            build_economic_fact(
                self.instruction,
                settled,
                _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
            )

    def test_tampered_economic_fact_fingerprint_cannot_project(self):
        settled = self._settled_result()
        fact = build_economic_fact(
            self.instruction,
            settled,
            _final_event(self.instruction, "river:receipt:test:projection-payment-001"),
        )
        tampered = copy.deepcopy(fact)
        tampered["value"]["amount"] = "1200.00"
        with self.assertRaises(ProjectionError):
            build_projection_pair(tampered)


if __name__ == "__main__":
    unittest.main()
