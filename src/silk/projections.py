from __future__ import annotations

import copy
import hashlib
import json


class ProjectionError(ValueError):
    """Raised when a canonical SILK fact or projection cannot be derived safely."""


def _hash(material: dict) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_federation_route(route: list[dict]) -> None:
    if not route:
        raise ProjectionError("federated payment requires at least one federation hop")
    indexes = [hop.get("hop_index") for hop in route]
    if indexes != list(range(len(route))):
        raise ProjectionError("federation hop indexes must be contiguous and zero-based")
    for hop in route:
        if not hop.get("warden_decision_ref"):
            raise ProjectionError("every federation hop requires a Warden decision reference")
    for previous, current in zip(route, route[1:]):
        if previous.get("to_silk_account_ref") != current.get("from_silk_account_ref"):
            raise ProjectionError("federation route account continuity is broken")


def build_economic_fact(
    instruction: dict,
    settled_provider_result: dict,
    final_event: dict,
) -> dict:
    """Derive one immutable economic fact from a finalized synthetic PAYMENT flow."""

    if instruction.get("instruction_type") != "PAYMENT":
        raise ProjectionError("R0.3 projection proof currently supports PAYMENT only")
    if settled_provider_result.get("outcome") != "SETTLED":
        raise ProjectionError("provider result must be SETTLED before projection")
    if final_event.get("event_type") != "FINALIZED":
        raise ProjectionError("projection requires a FINALIZED SILK event")
    transition = final_event.get("transition") or {}
    if transition.get("to_state") != "FINAL":
        raise ProjectionError("FINALIZED event must transition to FINAL")

    instruction_ref = instruction.get("silk_instruction_id")
    if settled_provider_result.get("instruction_ref") != instruction_ref:
        raise ProjectionError("provider result instruction reference does not match")
    if final_event.get("instruction_ref") != instruction_ref:
        raise ProjectionError("final event instruction reference does not match")

    warden_ref = instruction.get("warden_decision_ref")
    if not warden_ref:
        raise ProjectionError("instruction is missing Warden authority")
    if settled_provider_result.get("warden_decision_ref") != warden_ref:
        raise ProjectionError("provider result does not preserve Warden authority lineage")
    if final_event.get("warden_decision_ref") != warden_ref:
        raise ProjectionError("final event does not preserve Warden authority lineage")

    route_ref = instruction.get("execution_route_ref")
    if settled_provider_result.get("execution_route_ref") != route_ref:
        raise ProjectionError("provider result execution route does not match instruction")

    value = instruction.get("value") or {}
    canonical_value = {"amount": value.get("amount"), "currency": value.get("currency")}
    if settled_provider_result.get("value") != canonical_value:
        raise ProjectionError("provider-settled value does not match SILK instruction value")

    provider_result_ref = settled_provider_result.get("provider_result_id")
    if not provider_result_ref:
        raise ProjectionError("settled provider result is missing provider_result_id")

    river_refs = final_event.get("river_evidence_refs") or []
    if not river_refs:
        raise ProjectionError("final economic fact requires RiverOS evidence")

    federation_route = copy.deepcopy(instruction.get("federation_route") or [])
    _validate_federation_route(federation_route)

    source_material = {
        "instruction_ref": instruction_ref,
        "principal_ref": instruction.get("principal_ref"),
        "silk_account_ref": instruction.get("silk_account_ref"),
        "counterparty_ref": instruction.get("counterparty_ref"),
        "programme_ref": instruction.get("programme_ref"),
        "right_or_obligation_ref": instruction.get("right_or_obligation_ref"),
        "instruction_type": instruction["instruction_type"],
        "value": canonical_value,
        "federation_route": federation_route,
        "final_event_ref": final_event.get("event_id"),
        "provider_result_ref": provider_result_ref,
        "river_evidence_refs": list(river_refs),
        "finalized_at": final_event.get("occurred_at"),
    }
    fingerprint = _hash(source_material)

    return {
        "economic_fact_id": f"silk:economic-fact:{fingerprint[:24]}",
        **source_material,
        "source_fingerprint": fingerprint,
        "version": "R0.3",
    }


def build_projection_pair(economic_fact: dict) -> tuple[dict, dict]:
    """Build VSR and EmpireOS projections from exactly the same canonical fact."""

    if economic_fact.get("version") != "R0.3":
        raise ProjectionError("unsupported SILK economic fact version")
    if economic_fact.get("instruction_type") != "PAYMENT":
        raise ProjectionError("R0.3 projection proof supports PAYMENT only")
    if not economic_fact.get("river_evidence_refs"):
        raise ProjectionError("projection source is missing RiverOS evidence")
    if not economic_fact.get("provider_result_ref"):
        raise ProjectionError("projection source is missing provider result")

    material = {
        key: copy.deepcopy(value)
        for key, value in economic_fact.items()
        if key not in {"economic_fact_id", "source_fingerprint", "version"}
    }
    expected_fingerprint = _hash(material)
    if economic_fact.get("source_fingerprint") != expected_fingerprint:
        raise ProjectionError("economic fact source fingerprint does not verify")
    expected_fact_id = f"silk:economic-fact:{expected_fingerprint[:24]}"
    if economic_fact.get("economic_fact_id") != expected_fact_id:
        raise ProjectionError("economic fact identifier does not match its source")

    common = {
        "economic_fact_ref": economic_fact["economic_fact_id"],
        "instruction_ref": economic_fact["instruction_ref"],
        "source_fingerprint": expected_fingerprint,
        "provider_result_ref": economic_fact["provider_result_ref"],
        "river_evidence_refs": copy.deepcopy(economic_fact["river_evidence_refs"]),
        "value": copy.deepcopy(economic_fact["value"]),
        "finalized_at": economic_fact["finalized_at"],
        "version": "R0.3",
    }
    suffix = expected_fingerprint[:24]

    route = economic_fact.get("federation_route") or []
    arc_refs = [hop["arc_ref"] for hop in route]
    if not arc_refs:
        raise ProjectionError("VSR projection requires federation ARC context")

    vsr = {
        "projection_id": f"silk:projection:vsr:{suffix}",
        "projection_kind": "VSR",
        **copy.deepcopy(common),
        "payload": {
            "participation_effect": "VALUE_TRANSFER",
            "counterparty_ref": economic_fact["counterparty_ref"],
            "programme_ref": economic_fact["programme_ref"],
            "arc_refs": arc_refs,
        },
    }

    empire = {
        "projection_id": f"silk:projection:empire:{suffix}",
        "projection_kind": "EMPIRE",
        **copy.deepcopy(common),
        "payload": {
            "financial_effect": "OUTFLOW",
            "counterparty_ref": economic_fact["counterparty_ref"],
            "obligation_ref": economic_fact["right_or_obligation_ref"],
        },
    }

    return vsr, empire
