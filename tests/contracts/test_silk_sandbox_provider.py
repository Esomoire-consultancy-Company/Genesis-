import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from silk.sandbox_provider import (  # noqa: E402
    SandboxProviderAdapter,
    SandboxProviderConflict,
    SandboxProviderError,
)


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "silk" / "sandbox-payment-request.json"
CONTRACT_DIR = ROOT / "contracts" / "silk"


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def _dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _assert_federation_route(route: list[dict]) -> None:
    if not route:
        raise ValueError("federation_route must contain at least one hop")
    expected_indexes = list(range(len(route)))
    actual_indexes = [hop["hop_index"] for hop in route]
    if actual_indexes != expected_indexes:
        raise ValueError("federation_route hop_index values must be contiguous and zero-based")
    for previous, current in zip(route, route[1:]):
        if previous["to_silk_account_ref"] != current["from_silk_account_ref"]:
            raise ValueError("federation_route account continuity is broken")


class SilkSandboxProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.instruction = fixture["instruction"]
        cls.binding = fixture["provider_binding"]

        checker = FormatChecker()
        cls.instruction_validator = Draft202012Validator(
            _load_schema("silk-instruction.schema.json"), format_checker=checker
        )
        cls.provider_binding_validator = Draft202012Validator(
            _load_schema("silk-provider-binding.schema.json"), format_checker=checker
        )
        cls.provider_result_validator = Draft202012Validator(
            _load_schema("silk-provider-result.schema.json"), format_checker=checker
        )
        cls.event_validator = Draft202012Validator(
            _load_schema("silk-event.schema.json"), format_checker=checker
        )
        cls.account_schema = _load_schema("silk-account.schema.json")

    def test_canonical_account_taxonomy_has_four_classes_only(self):
        account_classes = self.account_schema["properties"]["account_class"]["enum"]
        self.assertEqual(
            account_classes,
            ["INDIVIDUAL_STUDENT", "FAMILY", "ENTERPRISE", "INSTITUTIONAL"],
        )
        self.assertNotIn("CREATOR", account_classes)
        self.assertNotIn("ARC", account_classes)
        self.assertNotIn("PROGRAMME", account_classes)

    def test_sandbox_request_and_federation_route_validate(self):
        self.instruction_validator.validate(self.instruction)
        self.provider_binding_validator.validate(self.binding)
        _assert_federation_route(self.instruction["federation_route"])

        route = self.instruction["federation_route"]
        self.assertEqual(route[0]["from_silk_account_ref"], self.instruction["silk_account_ref"])
        self.assertEqual(route[-1]["to_silk_account_ref"], "silk:account:test:institution-c")
        self.assertTrue(all(hop["warden_decision_ref"] for hop in route))

    def test_broken_federation_route_is_rejected_semantically(self):
        route = copy.deepcopy(self.instruction["federation_route"])
        route[1]["hop_index"] = 4
        with self.assertRaises(ValueError):
            _assert_federation_route(route)

        route = copy.deepcopy(self.instruction["federation_route"])
        route[1]["from_silk_account_ref"] = "silk:account:test:wrong"
        with self.assertRaises(ValueError):
            _assert_federation_route(route)

    def test_adapter_refuses_execution_without_warden_authority(self):
        instruction = copy.deepcopy(self.instruction)
        instruction.pop("warden_decision_ref")
        adapter = SandboxProviderAdapter()
        with self.assertRaises(SandboxProviderError):
            adapter.accept(instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z"))

    def test_adapter_refuses_pre_execution_state(self):
        instruction = copy.deepcopy(self.instruction)
        instruction["state"] = "WARDEN_AUTHORIZED"
        adapter = SandboxProviderAdapter()
        with self.assertRaises(SandboxProviderError):
            adapter.accept(instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z"))

    def test_adapter_refuses_wrong_or_expired_provider_binding(self):
        adapter = SandboxProviderAdapter()

        wrong = copy.deepcopy(self.binding)
        wrong["provider_binding_id"] = "silk:provider-binding:test:other"
        with self.assertRaises(SandboxProviderError):
            adapter.accept(self.instruction, wrong, as_of=_dt("2026-08-23T05:31:00Z"))

        expired = copy.deepcopy(self.binding)
        expired["valid_until"] = "2026-08-23T05:30:59Z"
        with self.assertRaises(SandboxProviderError):
            adapter.accept(self.instruction, expired, as_of=_dt("2026-08-23T05:31:00Z"))

    def test_adapter_refuses_missing_payment_capability(self):
        binding = copy.deepcopy(self.binding)
        binding["capabilities"] = ["VERIFY_ACCOUNT"]
        adapter = SandboxProviderAdapter()
        with self.assertRaises(SandboxProviderError):
            adapter.accept(self.instruction, binding, as_of=_dt("2026-08-23T05:31:00Z"))

    def test_accept_is_deterministic_and_idempotent(self):
        adapter = SandboxProviderAdapter()
        as_of = _dt("2026-08-23T05:31:00Z")

        first = adapter.accept(self.instruction, self.binding, as_of=as_of)
        replay = adapter.accept(self.instruction, self.binding, as_of=as_of)

        self.assertEqual(first, replay)
        self.assertEqual(first["outcome"], "ACCEPTED")
        self.assertEqual(first["warden_decision_ref"], self.instruction["warden_decision_ref"])
        self.assertEqual(first["execution_route_ref"], self.instruction["execution_route_ref"])
        self.provider_result_validator.validate(first)

    def test_conflicting_reuse_of_idempotency_key_is_rejected(self):
        adapter = SandboxProviderAdapter()
        as_of = _dt("2026-08-23T05:31:00Z")
        adapter.accept(self.instruction, self.binding, as_of=as_of)

        conflicting = copy.deepcopy(self.instruction)
        conflicting["value"]["amount"] = "1001.00"
        with self.assertRaises(SandboxProviderConflict):
            adapter.accept(conflicting, self.binding, as_of=as_of)

    def test_settlement_result_requires_forward_time_and_validates(self):
        adapter = SandboxProviderAdapter()
        accepted = adapter.accept(
            self.instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z")
        )

        with self.assertRaises(SandboxProviderError):
            adapter.settle(accepted, as_of=_dt("2026-08-23T05:30:59Z"))

        settled = adapter.settle(accepted, as_of=_dt("2026-08-23T05:32:00Z"))
        self.provider_result_validator.validate(settled)
        self.assertEqual(settled["outcome"], "SETTLED")
        self.assertEqual(settled["provider_result_id"], accepted["provider_result_id"])
        self.assertTrue(settled["provider_receipt_ref"])

    def test_synthetic_provider_to_river_lifecycle_validates(self):
        adapter = SandboxProviderAdapter()
        accepted = adapter.accept(
            self.instruction, self.binding, as_of=_dt("2026-08-23T05:31:00Z")
        )
        settled = adapter.settle(accepted, as_of=_dt("2026-08-23T05:32:00Z"))
        river_ref = "river:receipt:test:sandbox-payment-001"
        common = {
            "instruction_ref": self.instruction["silk_instruction_id"],
            "principal_ref": self.instruction["principal_ref"],
            "silk_account_ref": self.instruction["silk_account_ref"],
            "correlation_id": "silk:correlation:test:sandbox-payment-001",
            "warden_decision_ref": self.instruction["warden_decision_ref"],
            "execution_route_ref": self.instruction["execution_route_ref"],
            "version": "R0.1",
        }
        events = [
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:provider-accepted",
                "event_type": "PROVIDER_ACCEPTED",
                "occurred_at": accepted["accepted_at"],
                "actor": {"actor_class": "PROVIDER", "actor_ref": self.binding["provider_ref"]},
                "transition": {"from_state": "EXECUTION_REQUESTED", "to_state": "PROVIDER_ACCEPTED"},
                "provider_result_ref": accepted["provider_result_id"],
            },
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:pending",
                "event_type": "SETTLEMENT_PENDING",
                "causation_id": "silk:event:test:sandbox-payment:provider-accepted",
                "occurred_at": "2026-08-23T05:31:30Z",
                "actor": {"actor_class": "SILK", "actor_ref": "silk:test:rail"},
                "transition": {"from_state": "PROVIDER_ACCEPTED", "to_state": "SETTLEMENT_PENDING"},
                "provider_result_ref": accepted["provider_result_id"],
            },
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:settled",
                "event_type": "SETTLED",
                "causation_id": "silk:event:test:sandbox-payment:pending",
                "occurred_at": settled["settled_at"],
                "actor": {"actor_class": "PROVIDER", "actor_ref": self.binding["provider_ref"]},
                "transition": {"from_state": "SETTLEMENT_PENDING", "to_state": "SETTLED"},
                "provider_result_ref": settled["provider_result_id"],
                "payload": {"provider_receipt_ref": settled["provider_receipt_ref"]},
            },
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:observed",
                "event_type": "EFFECT_OBSERVED",
                "causation_id": "silk:event:test:sandbox-payment:settled",
                "occurred_at": "2026-08-23T05:32:10Z",
                "actor": {"actor_class": "RIVEROS", "actor_ref": "river:test:observer"},
                "transition": {"from_state": "SETTLED", "to_state": "RIVER_OBSERVED"},
                "river_evidence_refs": [river_ref],
                "payload": {"observed_effect": "SANDBOX_SETTLEMENT_CONFIRMED"},
            },
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:reconciled",
                "event_type": "RECONCILED",
                "causation_id": "silk:event:test:sandbox-payment:observed",
                "occurred_at": "2026-08-23T05:32:20Z",
                "actor": {"actor_class": "SILK", "actor_ref": "silk:test:reconciler"},
                "transition": {"from_state": "RIVER_OBSERVED", "to_state": "RECONCILED"},
                "river_evidence_refs": [river_ref],
            },
            {
                **common,
                "event_id": "silk:event:test:sandbox-payment:final",
                "event_type": "FINALIZED",
                "causation_id": "silk:event:test:sandbox-payment:reconciled",
                "occurred_at": "2026-08-23T05:32:30Z",
                "actor": {"actor_class": "SILK", "actor_ref": "silk:test:rail"},
                "transition": {"from_state": "RECONCILED", "to_state": "FINAL"},
                "river_evidence_refs": [river_ref],
            },
        ]

        for event in events:
            self.event_validator.validate(event)

        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["causation_id"], previous["event_id"])
            self.assertEqual(
                current["transition"]["from_state"], previous["transition"]["to_state"]
            )

        self.assertEqual(events[-1]["transition"]["to_state"], "FINAL")
        self.assertEqual(events[2]["provider_result_ref"], settled["provider_result_id"])
        self.assertEqual(events[3]["river_evidence_refs"], [river_ref])

    def test_provider_result_schema_rejects_false_settlement_without_receipt(self):
        invalid = {
            "provider_result_id": "silk:provider-result:test:false-settlement",
            "instruction_ref": self.instruction["silk_instruction_id"],
            "provider_binding_ref": self.binding["provider_binding_id"],
            "warden_decision_ref": self.instruction["warden_decision_ref"],
            "execution_route_ref": self.instruction["execution_route_ref"],
            "idempotency_key": self.instruction["idempotency_key"],
            "outcome": "SETTLED",
            "value": {"amount": "1000.00", "currency": "INR"},
            "accepted_at": "2026-08-23T05:31:00Z",
            "settled_at": "2026-08-23T05:32:00Z",
            "version": "R0.2",
        }
        with self.assertRaises(ValidationError):
            self.provider_result_validator.validate(invalid)


if __name__ == "__main__":
    unittest.main()
