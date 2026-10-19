from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation


class SandboxProviderError(ValueError):
    """Raised when a SILK sandbox provider request violates a contract invariant."""


class SandboxProviderConflict(SandboxProviderError):
    """Raised when an idempotency key is reused for a materially different request."""


_CAPABILITY_BY_INSTRUCTION = {
    "PAYMENT": "PAY",
    "COLLECTION": "COLLECT",
    "SETTLEMENT": "SETTLE",
    "REFUND": "REFUND",
    "REMITTANCE": "REMIT",
}


def _parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    encoded = value.isoformat()
    if encoded.endswith("+00:00"):
        encoded = encoded[:-6] + "Z"
    return encoded


def _fingerprint(instruction: dict, binding: dict) -> str:
    material = {
        "instruction_ref": instruction["silk_instruction_id"],
        "instruction_type": instruction["instruction_type"],
        "principal_ref": instruction["principal_ref"],
        "silk_account_ref": instruction["silk_account_ref"],
        "counterparty_ref": instruction.get("counterparty_ref"),
        "value": instruction["value"],
        "warden_decision_ref": instruction["warden_decision_ref"],
        "execution_route_ref": instruction["execution_route_ref"],
        "provider_binding_ref": instruction["provider_binding_ref"],
        "binding_provider_ref": binding["provider_ref"],
        "idempotency_key": instruction["idempotency_key"],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result_id(fingerprint: str) -> str:
    return f"silk:provider-result:sandbox:{fingerprint[:24]}"


def _receipt_id(provider_result_id: str) -> str:
    digest = hashlib.sha256(provider_result_id.encode("utf-8")).hexdigest()
    return f"sandbox:provider-receipt:{digest[:24]}"


class SandboxProviderAdapter:
    """Deterministic, non-custodial provider adapter for SILK contract verification.

    This adapter never contacts an external service, never holds funds, and never interprets
    provider authentication as Warden authority. It only accepts an already-authorized SILK
    instruction and produces synthetic provider results for contract testing.
    """

    def __init__(self) -> None:
        self._requests_by_idempotency_key: dict[str, tuple[str, dict]] = {}

    def accept(self, instruction: dict, binding: dict, *, as_of: datetime) -> dict:
        self._validate_request(instruction, binding, as_of=as_of)
        fingerprint = _fingerprint(instruction, binding)
        key = instruction["idempotency_key"]

        existing = self._requests_by_idempotency_key.get(key)
        if existing is not None:
            existing_fingerprint, existing_result = existing
            if existing_fingerprint != fingerprint:
                raise SandboxProviderConflict(
                    "idempotency key already exists for a materially different SILK request"
                )
            return copy.deepcopy(existing_result)

        result = {
            "provider_result_id": _result_id(fingerprint),
            "instruction_ref": instruction["silk_instruction_id"],
            "provider_binding_ref": binding["provider_binding_id"],
            "warden_decision_ref": instruction["warden_decision_ref"],
            "execution_route_ref": instruction["execution_route_ref"],
            "idempotency_key": key,
            "outcome": "ACCEPTED",
            "value": {
                "amount": instruction["value"]["amount"],
                "currency": instruction["value"]["currency"],
            },
            "accepted_at": _iso(as_of),
            "version": "R0.2",
        }
        self._requests_by_idempotency_key[key] = (fingerprint, copy.deepcopy(result))
        return result

    def settle(self, accepted_result: dict, *, as_of: datetime) -> dict:
        if accepted_result.get("outcome") == "SETTLED":
            return copy.deepcopy(accepted_result)
        if accepted_result.get("outcome") != "ACCEPTED":
            raise SandboxProviderError("only an ACCEPTED sandbox provider result may settle")

        accepted_at = _parse_datetime(accepted_result["accepted_at"])
        if as_of < accepted_at:
            raise SandboxProviderError("settled_at cannot precede accepted_at")

        settled = copy.deepcopy(accepted_result)
        settled["outcome"] = "SETTLED"
        settled["settled_at"] = _iso(as_of)
        settled["provider_receipt_ref"] = _receipt_id(settled["provider_result_id"])

        key = settled["idempotency_key"]
        existing = self._requests_by_idempotency_key.get(key)
        if existing is not None:
            fingerprint, _ = existing
            self._requests_by_idempotency_key[key] = (fingerprint, copy.deepcopy(settled))
        return settled

    @staticmethod
    def _validate_request(instruction: dict, binding: dict, *, as_of: datetime) -> None:
        if instruction.get("state") != "EXECUTION_REQUESTED":
            raise SandboxProviderError("instruction must be in EXECUTION_REQUESTED state")

        for required_ref in (
            "warden_decision_ref",
            "execution_route_ref",
            "provider_binding_ref",
            "idempotency_key",
        ):
            if not instruction.get(required_ref):
                raise SandboxProviderError(f"instruction is missing {required_ref}")

        if instruction["provider_binding_ref"] != binding.get("provider_binding_id"):
            raise SandboxProviderError("instruction provider binding does not match binding")

        instruction_type = instruction.get("instruction_type")
        required_capability = _CAPABILITY_BY_INSTRUCTION.get(instruction_type)
        if required_capability is None:
            raise SandboxProviderError("sandbox provider only accepts monetary instruction types")
        if required_capability not in set(binding.get("capabilities", [])):
            raise SandboxProviderError(
                f"provider binding lacks required capability {required_capability}"
            )

        if binding.get("status") not in {"ACTIVE", "PROVISIONAL"}:
            raise SandboxProviderError("provider binding is not executable")

        valid_from = binding.get("valid_from")
        valid_until = binding.get("valid_until")
        if valid_from and as_of < _parse_datetime(valid_from):
            raise SandboxProviderError("provider binding is not yet valid")
        if valid_until and as_of >= _parse_datetime(valid_until):
            raise SandboxProviderError("provider binding has expired")

        value = instruction.get("value") or {}
        if value.get("kind") != "MONEY":
            raise SandboxProviderError("sandbox monetary execution requires value.kind=MONEY")
        try:
            amount = Decimal(value["amount"])
        except (KeyError, InvalidOperation) as exc:
            raise SandboxProviderError("invalid monetary amount") from exc
        if amount <= 0:
            raise SandboxProviderError("sandbox monetary amount must be greater than zero")
        currency = value.get("currency")
        if not isinstance(currency, str) or len(currency) != 3 or currency.upper() != currency:
            raise SandboxProviderError("sandbox monetary execution requires ISO-style currency")
