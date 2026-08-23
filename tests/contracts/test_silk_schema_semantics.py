import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "contracts" / "silk"


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_provider_binding_semantics(binding: dict, *, as_of: datetime) -> None:
    valid_from = binding.get("valid_from")
    valid_until = binding.get("valid_until")

    start = _parse_datetime(valid_from) if valid_from else None
    end = _parse_datetime(valid_until) if valid_until else None

    if start is not None and end is not None and end < start:
        raise ValueError("valid_until must be greater than or equal to valid_from")

    if binding["status"] == "EXPIRED" and end is None:
        raise ValueError("EXPIRED provider bindings require valid_until")

    if binding["status"] in {"ACTIVE", "PROVISIONAL"} and end is not None:
        if end <= as_of:
            raise ValueError("active/provisional provider binding is stale past valid_until")


class SilkSchemaSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instruction_schema = _load_schema("silk-instruction.schema.json")
        cls.event_schema = _load_schema("silk-event.schema.json")
        cls.provider_schema = _load_schema("silk-provider-binding.schema.json")
        cls.provider_result_schema = _load_schema("silk-provider-result.schema.json")
        cls.account_schema = _load_schema("silk-account.schema.json")

        checker = FormatChecker()
        cls.instruction_validator = Draft202012Validator(
            cls.instruction_schema, format_checker=checker
        )
        cls.event_validator = Draft202012Validator(
            cls.event_schema, format_checker=checker
        )
        cls.provider_validator = Draft202012Validator(
            cls.provider_schema, format_checker=checker
        )
        cls.provider_result_validator = Draft202012Validator(
            cls.provider_result_schema, format_checker=checker
        )
        cls.account_validator = Draft202012Validator(
            cls.account_schema, format_checker=checker
        )

    def test_all_schemas_are_valid_draft_2020_12(self):
        for schema in (
            self.instruction_schema,
            self.event_schema,
            self.provider_schema,
            self.provider_result_schema,
            self.account_schema,
        ):
            Draft202012Validator.check_schema(schema)

    def test_invalid_datetime_is_rejected_with_format_checker(self):
        event = {
            "event_id": "silk:event:test:bad-time",
            "event_type": "INSTRUCTION_CREATED",
            "instruction_ref": "silk:instruction:test:bad-time",
            "principal_ref": "digitalme:test:a",
            "silk_account_ref": "silk:account:test:a",
            "correlation_id": "silk:correlation:test:bad-time",
            "occurred_at": "not-a-date",
            "actor": {"actor_class": "PRINCIPAL", "actor_ref": "digitalme:test:a"},
            "transition": {"from_state": "DRAFT", "to_state": "DRAFT"},
            "version": "R0.1",
        }
        with self.assertRaises(ValidationError):
            self.event_validator.validate(event)

    def test_observed_effect_cannot_claim_empty_river_evidence(self):
        event = {
            "event_id": "silk:event:test:no-evidence",
            "event_type": "EFFECT_OBSERVED",
            "instruction_ref": "silk:instruction:test:no-evidence",
            "principal_ref": "digitalme:test:a",
            "silk_account_ref": "silk:account:test:a",
            "correlation_id": "silk:correlation:test:no-evidence",
            "occurred_at": "2026-08-23T05:00:00Z",
            "actor": {"actor_class": "RIVEROS", "actor_ref": "river:test:observer"},
            "transition": {
                "from_state": "EXECUTION_REQUESTED",
                "to_state": "RIVER_OBSERVED",
            },
            "warden_decision_ref": "warden:decision:test:a",
            "river_evidence_refs": [],
            "version": "R0.1",
        }
        with self.assertRaises(ValidationError):
            self.event_validator.validate(event)

    def test_payment_requires_money_value_amount_and_currency(self):
        base = {
            "silk_instruction_id": "silk:instruction:test:payment",
            "principal_ref": "digitalme:test:a",
            "silk_account_ref": "silk:account:test:a",
            "instruction_type": "PAYMENT",
            "objective": "Synthetic schema test only",
            "state": "DRAFT",
            "idempotency_key": "payment-test-v1",
            "created_at": "2026-08-23T05:00:00Z",
            "version": "R0.1",
        }
        with self.assertRaises(ValidationError):
            self.instruction_validator.validate(base)

        wrong_kind = copy.deepcopy(base)
        wrong_kind["value"] = {"kind": "RIGHT", "asset_ref": "right:test:a"}
        with self.assertRaises(ValidationError):
            self.instruction_validator.validate(wrong_kind)

        missing_currency = copy.deepcopy(base)
        missing_currency["value"] = {"kind": "MONEY", "amount": "10.00"}
        with self.assertRaises(ValidationError):
            self.instruction_validator.validate(missing_currency)

    def test_money_amount_is_decimal_string_not_binary_float(self):
        instruction = {
            "silk_instruction_id": "silk:instruction:test:payment-float",
            "principal_ref": "digitalme:test:a",
            "silk_account_ref": "silk:account:test:a",
            "instruction_type": "PAYMENT",
            "objective": "Synthetic schema test only",
            "value": {"kind": "MONEY", "amount": 0.1, "currency": "INR"},
            "state": "DRAFT",
            "idempotency_key": "payment-float-test-v1",
            "created_at": "2026-08-23T05:00:00Z",
            "version": "R0.1",
        }
        with self.assertRaises(ValidationError):
            self.instruction_validator.validate(instruction)

    def test_expired_provider_binding_requires_non_null_valid_until(self):
        binding = {
            "provider_binding_id": "silk:provider-binding:test:a",
            "principal_ref": "digitalme:test:a",
            "provider_type": "BANK",
            "provider_ref": "provider:test:bank-a",
            "capabilities": ["VERIFY_ACCOUNT"],
            "status": "EXPIRED",
            "created_at": "2026-08-23T05:00:00Z",
            "version": "R0.1",
        }
        with self.assertRaises(ValidationError):
            self.provider_validator.validate(binding)

        binding["valid_until"] = None
        with self.assertRaises(ValidationError):
            self.provider_validator.validate(binding)

    def test_provider_window_ordering_and_status_freshness_are_semantic_guards(self):
        as_of = _parse_datetime("2026-08-23T05:00:00Z")
        binding = {
            "provider_binding_id": "silk:provider-binding:test:a",
            "principal_ref": "digitalme:test:a",
            "provider_type": "BANK",
            "provider_ref": "provider:test:bank-a",
            "capabilities": ["VERIFY_ACCOUNT"],
            "valid_from": "2026-08-23T04:00:00Z",
            "valid_until": "2026-08-23T06:00:00Z",
            "status": "ACTIVE",
            "created_at": "2026-08-23T04:00:00Z",
            "version": "R0.1",
        }
        self.provider_validator.validate(binding)
        validate_provider_binding_semantics(binding, as_of=as_of)

        reversed_window = copy.deepcopy(binding)
        reversed_window["valid_until"] = "2026-08-23T03:59:59Z"
        with self.assertRaises(ValueError):
            validate_provider_binding_semantics(reversed_window, as_of=as_of)

        stale_active = copy.deepcopy(binding)
        stale_active["valid_until"] = "2026-08-23T04:59:59Z"
        with self.assertRaises(ValueError):
            validate_provider_binding_semantics(stale_active, as_of=as_of)


if __name__ == "__main__":
    unittest.main()
