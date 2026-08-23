from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from silk.projections import build_economic_fact, build_projection_pair
from silk.sandbox_provider import SandboxProviderAdapter

ACCOUNT_CLASSES = {"INDIVIDUAL_STUDENT", "FAMILY", "ENTERPRISE", "INSTITUTIONAL"}


class AlphaRuntimeError(RuntimeError):
    pass


class AuthorityDenied(AlphaRuntimeError):
    pass


class IdempotencyConflict(AlphaRuntimeError):
    pass


class NmkAlphaRuntime:
    """Deterministic Alpha proof for governed SILK federation."""

    def __init__(self) -> None:
        self.accounts = {
            "silk:account:factory": ("ENTERPRISE", {"digitalme:factory"}),
            "silk:account:provider": ("ENTERPRISE", {"digitalme:provider"}),
            "silk:account:logistics": ("ENTERPRISE", {"digitalme:driver"}),
            "silk:account:institution": ("INSTITUTIONAL", {"digitalme:receiver"}),
            "silk:account:individual": ("INDIVIDUAL_STUDENT", {"digitalme:factory"}),
        }
        self.arcs = {
            "arc:factory": ("ENTERPRISE", "silk:account:factory"),
            "arc:provider": ("ENTERPRISE", "silk:account:provider"),
            "arc:logistics": ("ENTERPRISE", "silk:account:logistics"),
            "arc:institution": ("INSTITUTIONAL", "silk:account:institution"),
        }
        self.products = {
            "product:route": ("licence:route", {"CAP_ROUTE_OPTIMIZATION"}, {"ENTERPRISE"}),
            "product:cold-sensor": (
                "licence:cold-sensor",
                {"CAP_COLD_CHAIN_TRANSPORT"},
                {"ENTERPRISE", "INSTITUTIONAL"},
            ),
        }
        self.licences = {
            "licence:route": ("ACTIVE", {"vsr:route"}),
            "licence:cold-sensor": ("ACTIVE", {"vsr:cold-chain"}),
        }
        self.capacity = {"COMPUTE": 100, "NETWORK": 100, "STORAGE": 100}
        self._journeys: dict[str, dict[str, Any]] = {}
        self._request_keys: dict[str, tuple[dict[str, Any], str]] = {}
        self._journey_counter = 0
        self._decision_counter = 0
        self._provider = SandboxProviderAdapter()

    @staticmethod
    def _statuses() -> dict[str, str]:
        return {
            "lifecycle": "ACTIVE",
            "authority": "PENDING",
            "execution": "NOT_STARTED",
            "evidence": "PENDING",
            "effect": "UNKNOWN",
            "commercial": "PENDING",
            "settlement": "REQUIRED",
            "reconciliation": "OPEN",
        }

    @staticmethod
    def _ref(prefix: str, journey: dict[str, Any]) -> str:
        return f'{prefix}:{journey["journey_id"]}'

    def _emit(self, journey: dict[str, Any], event_type: str, object_ref: str, actor_ref: str) -> None:
        journey["event_log"].append(
            {
                "sequence": len(journey["event_log"]),
                "event_type": event_type,
                "journey_id": journey["journey_id"],
                "object_ref": object_ref,
                "actor_ref": actor_ref,
            }
        )

    def _semantic(self, request: dict[str, Any], programme_ref: str) -> dict[str, Any]:
        return {
            "principal_ref": request["principal_ref"],
            "silk_account_ref": request["silk_account_ref"],
            "capability_ref": request["requested_capability"],
            "programme_ref": programme_ref,
            "payload": deepcopy(request.get("payload", {})),
        }

    def _existing(self, request: dict[str, Any], programme_ref: str) -> dict[str, Any] | None:
        found = self._request_keys.get(request["idempotency_key"])
        if found is None:
            return None
        material, journey_id = found
        if material != self._semantic(request, programme_ref):
            raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
        return self._journeys[journey_id]

    def _create(self, request: dict[str, Any], programme_ref: str) -> dict[str, Any]:
        self._journey_counter += 1
        journey = {
            "journey_id": f"silk:journey:{self._journey_counter:06d}",
            "request_id": request["request_id"],
            "idempotency_key": request["idempotency_key"],
            "principal_ref": request["principal_ref"],
            "silk_account_ref": request["silk_account_ref"],
            "programme_ref": programme_ref,
            "capability_ref": request["requested_capability"],
            "payload": deepcopy(request.get("payload", {})),
            "statuses": self._statuses(),
            "route": {"route_version": 0, "product_ref": None, "hops": []},
            "genesis_state": None,
            "evidence": [],
            "effect_receipt": None,
            "commercial_history": [],
            "settlement": None,
            "exception": None,
            "compensation": None,
            "projections": {},
            "reconciliation": None,
            "event_log": [],
        }
        self._journeys[journey["journey_id"]] = journey
        self._request_keys[journey["idempotency_key"]] = (
            self._semantic(request, programme_ref), journey["journey_id"]
        )
        return journey

    def _authorize(self, principal: str, account_ref: str, arc_ref: str, capability: str) -> dict[str, str]:
        account = self.accounts.get(account_ref)
        arc = self.arcs.get(arc_ref)
        if (
            account is None
            or account[0] not in ACCOUNT_CLASSES
            or principal not in account[1]
            or arc is None
            or arc[1] != account_ref
        ):
            raise AuthorityDenied("WARDEN_DENIED")
        self._decision_counter += 1
        return {
            "decision_id": f"warden:decision:{self._decision_counter:06d}",
            "principal_ref": principal,
            "silk_account_ref": account_ref,
            "arc_ref": arc_ref,
            "capability_ref": capability,
            "decision": "ALLOW",
        }

    @staticmethod
    def _assert_decision(decision: dict[str, str], principal: str, account: str, arc: str, capability: str) -> None:
        expected = ("ALLOW", principal, account, arc, capability)
        actual = (
            decision["decision"],
            decision["principal_ref"],
            decision["silk_account_ref"],
            decision["arc_ref"],
            decision["capability_ref"],
        )
        if actual != expected:
            raise AuthorityDenied("WARDEN_DECISION_CONTEXT_MISMATCH")

    def _route(
        self,
        journey: dict[str, Any],
        bindings: list[tuple[dict[str, str], str, str, str]],
        product_ref: str,
        roles: list[str],
    ) -> None:
        for decision, principal, account, arc in bindings:
            self._assert_decision(decision, principal, account, arc, journey["capability_ref"])
        licence_ref, capabilities, allowed_arc_classes = self.products[product_ref]
        licence_status, programmes = self.licences[licence_ref]
        route_arc_classes = {self.arcs[arc][0] for _d, _p, _a, arc in bindings}
        if (
            licence_status != "ACTIVE"
            or journey["programme_ref"] not in programmes
            or journey["capability_ref"] not in capabilities
            or not route_arc_classes.issubset(allowed_arc_classes)
        ):
            raise AlphaRuntimeError("PRODUCT_INELIGIBLE_FOR_ROUTE")
        journey["route"] = {
            "route_version": 1,
            "product_ref": product_ref,
            "hops": [
                {
                    "sequence": index,
                    "arc_ref": arc,
                    "role": role,
                    "silk_account_ref": account,
                    "warden_decision_ref": decision["decision_id"],
                }
                for index, ((decision, _principal, account, arc), role)
                in enumerate(zip(bindings, roles))
            ],
        }
        journey["statuses"]["authority"] = "AUTHORIZED"
        self._emit(journey, "silk.route.authorized", self._ref("silk:route", journey), "WARDEN")

    def _reserve(self, journey: dict[str, Any]) -> dict[str, int]:
        reserved = {"COMPUTE": 2, "NETWORK": 1, "STORAGE": 1}
        if any(self.capacity[k] < v for k, v in reserved.items()):
            raise AlphaRuntimeError("CAPACITY_UNAVAILABLE")
        for key, value in reserved.items():
            self.capacity[key] -= value
        self._emit(journey, "bnr.capacity.reserved", self._ref("bnr:reservation", journey), "BNR")
        return reserved

    def _release(self, journey: dict[str, Any], reserved: dict[str, int]) -> None:
        for key, value in reserved.items():
            self.capacity[key] += value
        self._emit(journey, "bnr.capacity.released", self._ref("bnr:reservation", journey), "BNR")

    def _settle(self, journey: dict[str, Any], amount: str, counterparty_ref: str) -> tuple[dict, dict]:
        route = []
        hops = journey["route"]["hops"]
        for index, (current, following) in enumerate(zip(hops, hops[1:])):
            route.append(
                {
                    "hop_index": index,
                    "arc_ref": current["arc_ref"],
                    "from_silk_account_ref": current["silk_account_ref"],
                    "to_silk_account_ref": following["silk_account_ref"],
                    "warden_decision_ref": current["warden_decision_ref"],
                }
            )
        instruction = {
            "silk_instruction_id": self._ref("silk:instruction", journey),
            "principal_ref": journey["principal_ref"],
            "silk_account_ref": journey["silk_account_ref"],
            "counterparty_ref": counterparty_ref,
            "programme_ref": journey["programme_ref"],
            "right_or_obligation_ref": f'obligation:{journey["journey_id"]}',
            "instruction_type": "PAYMENT",
            "objective": "Settle governed SILK obligation",
            "value": {"kind": "MONEY", "amount": amount, "currency": "INR"},
            "state": "EXECUTION_REQUESTED",
            "warden_decision_ref": hops[0]["warden_decision_ref"],
            "execution_route_ref": self._ref("silk:route", journey),
            "provider_binding_ref": "silk:provider-binding:sandbox-bank",
            "federation_route": route,
            "idempotency_key": f'settlement:{journey["journey_id"]}',
            "created_at": "2026-08-23T06:00:00Z",
            "version": "R0.3",
        }
        binding = {
            "provider_binding_id": "silk:provider-binding:sandbox-bank",
            "principal_ref": journey["principal_ref"],
            "provider_type": "BANK",
            "provider_ref": "provider:sandbox-bank",
            "capabilities": ["PAY", "VERIFY_ACCOUNT"],
            "status": "ACTIVE",
            "valid_from": "2026-08-23T05:00:00Z",
            "valid_until": "2026-08-24T05:00:00Z",
            "created_at": "2026-08-23T05:00:00Z",
            "version": "R0.3",
        }
        accepted = self._provider.accept(
            instruction, binding, as_of=datetime(2026, 8, 23, 6, 1, tzinfo=timezone.utc)
        )
        settled = self._provider.settle(
            accepted, as_of=datetime(2026, 8, 23, 6, 2, tzinfo=timezone.utc)
        )
        self._emit(journey, "settlement.confirmed", settled["provider_result_id"], binding["provider_ref"])
        return instruction, settled

    def execute_fixture_a(self, request: dict[str, Any]) -> dict[str, Any]:
        existing = self._existing(request, "vsr:route")
        if existing is not None:
            return self.get_journey(existing["journey_id"])
        if request["silk_account_ref"] != "silk:account:factory":
            raise AuthorityDenied("ENTERPRISE_ACCOUNT_REQUIRED")
        if request["requested_capability"] != "CAP_ROUTE_OPTIMIZATION":
            raise AuthorityDenied("CAPABILITY_NOT_ENTITLED")
        source = self._authorize(request["principal_ref"], "silk:account:factory", "arc:factory", request["requested_capability"])
        journey = self._create(request, "vsr:route")
        self._emit(journey, "digitalme.context.resolved", journey["silk_account_ref"], journey["principal_ref"])
        self._emit(journey, "warden.decision.issued", source["decision_id"], "WARDEN")
        self._emit(journey, "silk.journey.created", journey["journey_id"], journey["principal_ref"])
        self._emit(journey, "silk.route.proposed", self._ref("silk:route", journey), "VSR")
        destination = self._authorize("digitalme:provider", "silk:account:provider", "arc:provider", journey["capability_ref"])
        self._emit(journey, "warden.decision.issued", destination["decision_id"], "WARDEN")
        self._route(
            journey,
            [
                (source, journey["principal_ref"], "silk:account:factory", "arc:factory"),
                (destination, "digitalme:provider", "silk:account:provider", "arc:provider"),
            ],
            "product:route",
            ["ORIGINATOR", "SERVICE_PROVIDER"],
        )
        reserved = self._reserve(journey)
        try:
            journey["statuses"]["execution"] = "RUNNING"
            self._emit(journey, "synnergyze.execution.started", self._ref("synnergyze:plan", journey), "SYNNERGYZE")
            journey["statuses"]["execution"] = "COMPLETED"
            self._emit(journey, "creator_product.execution.completed", self._ref("route-result", journey), "product:route")
            journey["genesis_state"] = "PROCESSED"
            self._emit(journey, "genesis.transition.committed", self._ref("genesis:transition", journey), "GENESIS")
            evidence = {
                "evidence_id": self._ref("river:evidence", journey),
                "fact_class": "FACT",
                "route": [journey["payload"].get("origin", "A"), journey["payload"].get("destination", "B")],
            }
            journey["evidence"].append(evidence)
            self._emit(journey, "river.evidence.recorded", evidence["evidence_id"], "RIVER")
            journey["effect_receipt"] = {
                "receipt_id": self._ref("river:receipt", journey),
                "evidence_status": "SUFFICIENT",
                "effect_status": "CONFORMING",
                "evidence_refs": [evidence["evidence_id"]],
            }
            journey["statuses"].update({"evidence": "SUFFICIENT", "effect": "CONFORMING"})
            self._emit(journey, "river.effect.verified", journey["effect_receipt"]["receipt_id"], "RIVER")
            commercial = {
                "commercial_event_id": self._ref("commercial:event", journey),
                "gross_value": 100,
                "currency": "INR",
                "allocations": [
                    {"beneficiary": "silk:account:provider", "amount": 50},
                    {"beneficiary": "digitalme:creator", "amount": 30},
                    {"beneficiary": "bnr:reference", "amount": 20},
                ],
            }
            journey["commercial_history"].append(commercial)
            journey["statuses"]["commercial"] = "COMPILED"
            self._emit(journey, "commercial.event.compiled", commercial["commercial_event_id"], "COMMERCIAL_COMPILER")
            _instruction, settled = self._settle(journey, "100.00", "silk:account:provider")
            journey["settlement"] = settled
            journey["statuses"]["settlement"] = "CONFIRMED"
        finally:
            self._release(journey, reserved)
        checks = {
            "authority": journey["statuses"]["authority"] == "AUTHORIZED",
            "execution": journey["statuses"]["execution"] == "COMPLETED",
            "evidence": journey["statuses"]["evidence"] == "SUFFICIENT",
            "effect": journey["statuses"]["effect"] == "CONFORMING",
            "commercial_balance": sum(x["amount"] for x in commercial["allocations"]) == commercial["gross_value"],
            "settlement": journey["settlement"]["outcome"] == "SETTLED",
            "capacity_released": self.capacity == {"COMPUTE": 100, "NETWORK": 100, "STORAGE": 100},
        }
        if not all(checks.values()):
            raise AlphaRuntimeError("RECONCILIATION_FAILED")
        journey["statuses"].update({"lifecycle": "COMPLETE", "reconciliation": "RECONCILED"})
        journey["reconciliation"] = {"status": "RECONCILED", "checks": checks, "unresolved_items": []}
        self._emit(journey, "reconciliation.completed", self._ref("reconciliation", journey), "RECONCILIATION")
        return self.get_journey(journey["journey_id"])

    def execute_fixture_c(self, request: dict[str, Any]) -> dict[str, Any]:
        existing = self._existing(request, "vsr:cold-chain")
        if existing is not None:
            return self.get_journey(existing["journey_id"])
        if request["silk_account_ref"] != "silk:account:factory":
            raise AuthorityDenied("ENTERPRISE_ACCOUNT_REQUIRED")
        if request["requested_capability"] != "CAP_COLD_CHAIN_TRANSPORT":
            raise AuthorityDenied("CAPABILITY_NOT_ENTITLED")
        source = self._authorize(request["principal_ref"], "silk:account:factory", "arc:factory", request["requested_capability"])
        journey = self._create(request, "vsr:cold-chain")
        self._emit(journey, "digitalme.context.resolved", journey["silk_account_ref"], journey["principal_ref"])
        self._emit(journey, "warden.decision.issued", source["decision_id"], "WARDEN")
        self._emit(journey, "silk.journey.created", journey["journey_id"], journey["principal_ref"])
        self._emit(journey, "silk.route.proposed", self._ref("silk:route", journey), "VSR")
        logistics = self._authorize("digitalme:driver", "silk:account:logistics", "arc:logistics", journey["capability_ref"])
        receiver = self._authorize("digitalme:receiver", "silk:account:institution", "arc:institution", journey["capability_ref"])
        for decision in (logistics, receiver):
            self._emit(journey, "warden.decision.issued", decision["decision_id"], "WARDEN")
        self._route(
            journey,
            [
                (source, journey["principal_ref"], "silk:account:factory", "arc:factory"),
                (logistics, "digitalme:driver", "silk:account:logistics", "arc:logistics"),
                (receiver, "digitalme:receiver", "silk:account:institution", "arc:institution"),
            ],
            "product:cold-sensor",
            ["ORIGINATOR", "SERVICE_PROVIDER", "RECEIVER"],
        )
        reserved = self._reserve(journey)
        try:
            journey["statuses"]["execution"] = "RUNNING"
            self._emit(journey, "synnergyze.execution.started", self._ref("synnergyze:plan", journey), "SYNNERGYZE")
            for index, raw in enumerate(journey["payload"].get("temperatures_c", [3.2, 4.8, 7.4, 10.9, 9.6, 7.8])):
                evidence = {
                    "evidence_id": f'{self._ref("river:evidence", journey)}:{index:03d}',
                    "fact_class": "FACT",
                    "temperature_c": float(raw),
                }
                journey["evidence"].append(evidence)
                self._emit(journey, "river.evidence.recorded", evidence["evidence_id"], "RIVER")
                if journey["exception"] is None and not 2.0 <= evidence["temperature_c"] <= 8.0:
                    journey["exception"] = {
                        "exception_id": self._ref("exception", journey),
                        "type": "TEMPERATURE_THRESHOLD_BREACH",
                        "triggering_evidence_ref": evidence["evidence_id"],
                        "status": "OPEN",
                    }
                    self._emit(journey, "exception.opened", journey["exception"]["exception_id"], "EXCEPTION_FABRIC")
            if journey["exception"] is None:
                raise AlphaRuntimeError("FIXTURE_C_REQUIRES_NONCONFORMANCE")
            journey["statuses"]["execution"] = "COMPLETED"
            journey["genesis_state"] = "QUARANTINED_FOR_INSPECTION"
            self._emit(journey, "genesis.transition.committed", self._ref("genesis:transition", journey), "GENESIS")
            journey["effect_receipt"] = {
                "receipt_id": self._ref("river:receipt", journey),
                "evidence_status": "SUFFICIENT",
                "effect_status": "NONCONFORMING",
                "evidence_refs": [x["evidence_id"] for x in journey["evidence"]],
                "observed_maximum_c": max(x["temperature_c"] for x in journey["evidence"]),
            }
            journey["statuses"].update({"evidence": "SUFFICIENT", "effect": "NONCONFORMING"})
            self._emit(journey, "river.effect.verified", journey["effect_receipt"]["receipt_id"], "RIVER")
            initial = {
                "commercial_event_id": self._ref("commercial:event:initial", journey),
                "contract_ref": "contract:cold-chain",
                "trigger_receipt_ref": journey["effect_receipt"]["receipt_id"],
                "gross_value": 10000,
                "currency": "INR",
                "status": "ADJUSTMENT_REQUIRED",
            }
            journey["commercial_history"].append(initial)
            journey["statuses"]["commercial"] = "ADJUSTMENT_REQUIRED"
            self._emit(journey, "commercial.event.compiled", initial["commercial_event_id"], "COMMERCIAL_COMPILER")
            journey["settlement"] = {"status": "PENDING", "reason": "COMMERCIAL_ADJUSTMENT_OPEN"}
            journey["statuses"]["settlement"] = "PENDING"
            journey["compensation"] = {"compensation_id": self._ref("compensation", journey), "status": "RUNNING"}
            self._emit(journey, "compensation.started", journey["compensation"]["compensation_id"], "COMPENSATION")
        finally:
            self._release(journey, reserved)
        journey["statuses"]["lifecycle"] = "COMPLETE"
        journey["reconciliation"] = {
            "status": "OPEN",
            "unresolved_items": [
                "NONCONFORMING_EFFECT",
                "COMMERCIAL_ADJUSTMENT_REQUIRED",
                "SETTLEMENT_PENDING",
                "EXCEPTION_OPEN",
                "COMPENSATION_RUNNING",
            ],
        }
        self._emit(journey, "reconciliation.started", self._ref("reconciliation", journey), "RECONCILIATION")
        journey["projections"]["operational"] = {
            "execution": "COMPLETED",
            "evidence": "SUFFICIENT",
            "effect": "NONCONFORMING",
            "sensor_effect": "CONFORMING",
            "commercial": "ADJUSTMENT_REQUIRED",
            "settlement": "PENDING",
            "reconciliation": "OPEN",
        }
        return self.get_journey(journey["journey_id"])

    def resolve_fixture_c(self, journey_id: str) -> dict[str, Any]:
        journey = self._journeys[journey_id]
        if journey["statuses"]["reconciliation"] == "RECONCILED":
            return self.get_journey(journey_id)
        adjustment = {
            "commercial_event_id": self._ref("commercial:event:adjustment", journey),
            "supersedes_ref": journey["commercial_history"][0]["commercial_event_id"],
            "trigger_receipt_ref": journey["effect_receipt"]["receipt_id"],
            "gross_value": 10000,
            "currency": "INR",
            "status": "COMPILED",
            "allocations": [
                {"beneficiary": "silk:account:logistics", "amount": 6000},
                {"beneficiary": "digitalme:creator", "amount": 1000},
                {"beneficiary": "arc:institution", "amount": 500},
                {"beneficiary": "silk:account:institution", "amount": 2500},
            ],
        }
        journey["commercial_history"].append(adjustment)
        journey["statuses"]["commercial"] = "COMPILED"
        self._emit(journey, "commercial.event.adjusted", adjustment["commercial_event_id"], "COMMERCIAL_COMPILER")
        journey["compensation"]["status"] = "COMPLETED"
        journey["exception"]["status"] = "RESOLVED"
        self._emit(journey, "compensation.completed", journey["compensation"]["compensation_id"], "COMPENSATION")
        self._emit(journey, "exception.resolved", journey["exception"]["exception_id"], "EXCEPTION_FABRIC")
        instruction, settled = self._settle(journey, "10000.00", "silk:account:institution")
        journey["settlement"] = settled
        journey["statuses"]["settlement"] = "CONFIRMED"
        final_event = {
            "event_id": self._ref("silk:event:finalized", journey),
            "event_type": "FINALIZED",
            "instruction_ref": instruction["silk_instruction_id"],
            "warden_decision_ref": instruction["warden_decision_ref"],
            "river_evidence_refs": [journey["effect_receipt"]["receipt_id"]],
            "occurred_at": "2026-08-23T06:03:00Z",
            "transition": {"from_state": "RECONCILED", "to_state": "FINAL"},
        }
        fact = build_economic_fact(instruction, settled, final_event)
        vsr, empire = build_projection_pair(fact)
        journey["projections"].update({"economic_fact": fact, "vsr": vsr, "empire": empire})
        checks = {
            "authority": journey["statuses"]["authority"] == "AUTHORIZED",
            "execution": journey["statuses"]["execution"] == "COMPLETED",
            "evidence": journey["statuses"]["evidence"] == "SUFFICIENT",
            "nonconformance_preserved": journey["statuses"]["effect"] == "NONCONFORMING",
            "commercial_balance": sum(x["amount"] for x in adjustment["allocations"]) == adjustment["gross_value"],
            "compensation": journey["compensation"]["status"] == "COMPLETED",
            "exception": journey["exception"]["status"] == "RESOLVED",
            "settlement": settled["outcome"] == "SETTLED",
            "projection_lineage": vsr["economic_fact_ref"] == empire["economic_fact_ref"] == fact["economic_fact_id"],
        }
        if not all(checks.values()):
            raise AlphaRuntimeError("RECONCILIATION_FAILED")
        journey["statuses"]["reconciliation"] = "RECONCILED"
        journey["reconciliation"] = {"status": "RECONCILED", "checks": checks, "unresolved_items": []}
        self._emit(journey, "reconciliation.completed", self._ref("reconciliation", journey), "RECONCILIATION")
        journey["projections"]["operational"].update(
            {"effect": "NONCONFORMING", "commercial": "COMPILED", "settlement": "CONFIRMED", "reconciliation": "RECONCILED"}
        )
        return self.get_journey(journey_id)

    def get_journey(self, journey_id: str) -> dict[str, Any]:
        return deepcopy(self._journeys[journey_id])
