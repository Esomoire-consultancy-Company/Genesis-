from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


ACCOUNT_CLASSES = {"INDIVIDUAL", "FAMILY", "ENTERPRISE", "INSTITUTIONAL"}


class AlphaRuntimeError(RuntimeError):
    """Base error for the deterministic NMK Alpha reference runtime."""


class AuthorityDenied(AlphaRuntimeError):
    pass


class IdempotencyConflict(AlphaRuntimeError):
    pass


@dataclass(frozen=True)
class WardenDecision:
    decision_id: str
    principal_ref: str
    silk_account_ref: str
    arc_ref: str
    capability_ref: str
    decision: str


@dataclass(frozen=True)
class RouteHop:
    sequence: int
    arc_ref: str
    role: str
    silk_account_ref: str
    warden_decision_ref: str


@dataclass(frozen=True)
class RouteManifest:
    route_manifest_id: str
    journey_id: str
    route_version: int
    product_ref: str
    hops: tuple[RouteHop, ...]


@dataclass
class JourneyRecord:
    journey_id: str
    request_id: str
    idempotency_key: str
    principal_ref: str
    silk_account_ref: str
    programme_ref: str
    programme_instance_ref: str
    capability_ref: str
    request_payload: dict[str, Any] = field(default_factory=dict)
    route_manifest: RouteManifest | None = None
    statuses: dict[str, str] = field(
        default_factory=lambda: {
            "lifecycle": "ACTIVE",
            "authority": "PENDING",
            "execution": "NOT_STARTED",
            "evidence": "PENDING",
            "effect": "UNKNOWN",
            "commercial": "PENDING",
            "settlement": "REQUIRED",
            "reconciliation": "OPEN",
        }
    )
    event_log: list[dict[str, Any]] = field(default_factory=list)
    commercial_event: dict[str, Any] | None = None
    settlement: dict[str, Any] | None = None
    empire_projection: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None


class AlphaRuntime:
    """
    Deterministic reference runtime for NMK Fixture A.

    It is intentionally in-memory and dependency-free. Its purpose is to pin
    the semantic boundaries before persistence, HTTP, MCP, and external
    provider adapters are added.
    """

    def __init__(self) -> None:
        self.digitalmes = {
            "DM-FACTORY-001": {"status": "ACTIVE"},
            "DM-PROVIDER-001": {"status": "ACTIVE"},
            "DM-CREATOR-001": {"status": "ACTIVE"},
        }
        self.accounts = {
            "SA-E-FACTORY-001": {
                "account_class": "ENTERPRISE",
                "status": "ACTIVE",
                "members": {
                    "DM-FACTORY-001": {
                        "relationship": "EMPLOYEE",
                        "role": "OPERATIONS_REQUESTER",
                    }
                },
            },
            "SA-E-PROVIDER-001": {
                "account_class": "ENTERPRISE",
                "status": "ACTIVE",
                "members": {
                    "DM-PROVIDER-001": {
                        "relationship": "EMPLOYEE",
                        "role": "SERVICE_OPERATOR",
                    }
                },
            },
            "SA-I-FACTORY-001": {
                "account_class": "INDIVIDUAL",
                "status": "ACTIVE",
                "members": {
                    "DM-FACTORY-001": {
                        "relationship": "OWNER",
                        "role": "INDIVIDUAL",
                    }
                },
            },
        }
        self.arcs = {
            "QARC-E-FACTORY-001": {
                "arc_class": "ENTERPRISE",
                "silk_account_ref": "SA-E-FACTORY-001",
                "status": "ACTIVE",
            },
            "QARC-E-PROVIDER-001": {
                "arc_class": "ENTERPRISE",
                "silk_account_ref": "SA-E-PROVIDER-001",
                "status": "ACTIVE",
            },
        }
        self.programmes = {
            "VSR-ROUTE-SERVICE-001": {
                "status": "ACTIVE",
                "eligible_arc_classes": {"ENTERPRISE"},
                "required_capabilities": {"CAP-ROUTE-OPTIMIZATION"},
            }
        }
        self.programme_instances = {
            "PI-ROUTE-FACTORY-001": {
                "programme_ref": "VSR-ROUTE-SERVICE-001",
                "arc_ref": "QARC-E-FACTORY-001",
                "status": "ACTIVE",
            },
            "PI-ROUTE-PROVIDER-001": {
                "programme_ref": "VSR-ROUTE-SERVICE-001",
                "arc_ref": "QARC-E-PROVIDER-001",
                "status": "ACTIVE",
            },
        }
        self.creator_licences = {
            "CL-ROUTE-001": {
                "creator_ref": "DM-CREATOR-001",
                "status": "ACTIVE",
                "eligible_arc_classes": {"ENTERPRISE"},
                "eligible_programmes": {"VSR-ROUTE-SERVICE-001"},
                "capabilities": {"CAP-ROUTE-OPTIMIZATION"},
            }
        }
        self.products = {
            "SPP-ROUTE-001": {
                "creator_ref": "DM-CREATOR-001",
                "licence_ref": "CL-ROUTE-001",
                "status": "ACTIVE",
                "capabilities": {"CAP-ROUTE-OPTIMIZATION"},
            }
        }

        self.capacity = {"COMPUTE": 100, "NETWORK": 100, "STORAGE": 100}

        self._journey_counter = 0
        self._decision_counter = 0
        self._request_idempotency: dict[str, tuple[dict[str, Any], str]] = {}
        self._journeys: dict[str, JourneyRecord] = {}
        self._commercial_idempotency: dict[str, dict[str, Any]] = {}

    def _emit(
        self,
        journey: JourneyRecord,
        event_type: str,
        *,
        actor_ref: str,
        object_ref: str,
    ) -> None:
        journey.event_log.append(
            {
                "sequence": len(journey.event_log) + 1,
                "event_type": event_type,
                "journey_id": journey.journey_id,
                "actor_ref": actor_ref,
                "object_ref": object_ref,
            }
        )

    @staticmethod
    def _journey_ref(prefix: str, journey: JourneyRecord) -> str:
        sequence = int(journey.journey_id.rsplit("-", 1)[1])
        return f"{prefix}-{sequence:03d}"

    @staticmethod
    def _assert_decision_binding(
        decision: WardenDecision,
        *,
        principal_ref: str,
        silk_account_ref: str,
        arc_ref: str,
        capability_ref: str,
    ) -> None:
        if (
            decision.decision != "ALLOW"
            or decision.principal_ref != principal_ref
            or decision.silk_account_ref != silk_account_ref
            or decision.arc_ref != arc_ref
            or decision.capability_ref != capability_ref
        ):
            raise AuthorityDenied("WARDEN_DECISION_CONTEXT_MISMATCH")

    def resolve_context(
        self,
        *,
        principal_ref: str,
        silk_account_ref: str,
        capability_ref: str,
    ) -> dict[str, str]:
        principal = self.digitalmes.get(principal_ref)
        account = self.accounts.get(silk_account_ref)
        if not principal or principal["status"] != "ACTIVE":
            raise AuthorityDenied("IDENTITY_UNRESOLVED")
        if not account or account["status"] != "ACTIVE":
            raise AuthorityDenied("ACCOUNT_INVALID")
        if account["account_class"] not in ACCOUNT_CLASSES:
            raise AlphaRuntimeError("INVALID_ACCOUNT_CLASS")
        membership = account["members"].get(principal_ref)
        if not membership:
            raise AuthorityDenied("ACCOUNT_MEMBERSHIP_MISSING")

        if capability_ref == "CAP-ROUTE-OPTIMIZATION":
            if account["account_class"] != "ENTERPRISE":
                raise AuthorityDenied("ENTERPRISE_ACCOUNT_REQUIRED")
            return {
                "principal_ref": principal_ref,
                "silk_account_ref": silk_account_ref,
                "relationship": membership["relationship"],
                "role": membership["role"],
                "arc_ref": "QARC-E-FACTORY-001",
                "programme_ref": "VSR-ROUTE-SERVICE-001",
                "programme_instance_ref": "PI-ROUTE-FACTORY-001",
                "capability_ref": capability_ref,
            }

        raise AuthorityDenied("CAPABILITY_NOT_ENTITLED")

    def request_warden_decision(
        self,
        *,
        principal_ref: str,
        silk_account_ref: str,
        arc_ref: str,
        capability_ref: str,
    ) -> WardenDecision:
        account = self.accounts.get(silk_account_ref)
        arc = self.arcs.get(arc_ref)
        if (
            not account
            or account["status"] != "ACTIVE"
            or principal_ref not in account["members"]
            or account["account_class"] != "ENTERPRISE"
            or not arc
            or arc["status"] != "ACTIVE"
            or arc["silk_account_ref"] != silk_account_ref
        ):
            raise AuthorityDenied("WARDEN_DENIED")
        self._decision_counter += 1
        return WardenDecision(
            decision_id=f"WD-{self._decision_counter:06d}",
            principal_ref=principal_ref,
            silk_account_ref=silk_account_ref,
            arc_ref=arc_ref,
            capability_ref=capability_ref,
            decision="ALLOW",
        )

    def create_journey(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        principal_ref: str,
        silk_account_ref: str,
        programme_ref: str,
        programme_instance_ref: str,
        capability_ref: str,
        request_payload: dict[str, Any],
        source_decision: WardenDecision,
    ) -> JourneyRecord:
        semantic_request = {
            "principal_ref": principal_ref,
            "silk_account_ref": silk_account_ref,
            "programme_ref": programme_ref,
            "programme_instance_ref": programme_instance_ref,
            "capability_ref": capability_ref,
            "payload": deepcopy(request_payload),
        }
        existing = self._request_idempotency.get(idempotency_key)
        if existing:
            existing_request, journey_id = existing
            if existing_request != semantic_request:
                raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
            return self._journeys[journey_id]

        source_arc_ref = self.programme_instances[programme_instance_ref]["arc_ref"]
        self._assert_decision_binding(
            source_decision,
            principal_ref=principal_ref,
            silk_account_ref=silk_account_ref,
            arc_ref=source_arc_ref,
            capability_ref=capability_ref,
        )

        self._journey_counter += 1
        journey = JourneyRecord(
            journey_id=f"SJ-A-{self._journey_counter:06d}",
            request_id=request_id,
            idempotency_key=idempotency_key,
            principal_ref=principal_ref,
            silk_account_ref=silk_account_ref,
            programme_ref=programme_ref,
            programme_instance_ref=programme_instance_ref,
            capability_ref=capability_ref,
            request_payload=deepcopy(request_payload),
        )
        journey.statuses["authority"] = "PARTIALLY_AUTHORIZED"
        self._journeys[journey.journey_id] = journey
        self._request_idempotency[idempotency_key] = (
            deepcopy(semantic_request),
            journey.journey_id,
        )
        return journey

    def resolve_route(self, journey: JourneyRecord) -> tuple[str, str]:
        programme = self.programmes[journey.programme_ref]
        provider_arc = self.arcs["QARC-E-PROVIDER-001"]
        product = self.products["SPP-ROUTE-001"]
        licence = self.creator_licences[product["licence_ref"]]

        eligible = (
            programme["status"] == "ACTIVE"
            and journey.capability_ref in programme["required_capabilities"]
            and provider_arc["arc_class"] in programme["eligible_arc_classes"]
            and product["status"] == "ACTIVE"
            and journey.capability_ref in product["capabilities"]
            and licence["status"] == "ACTIVE"
            and provider_arc["arc_class"] in licence["eligible_arc_classes"]
            and journey.programme_ref in licence["eligible_programmes"]
        )
        if not eligible:
            raise AlphaRuntimeError("NO_COMPATIBLE_ROUTE")

        self._emit(
            journey,
            "silk.route.proposed",
            actor_ref="VSR",
            object_ref=self._journey_ref("RM-A", journey),
        )
        return "QARC-E-PROVIDER-001", "SPP-ROUTE-001"

    def authorize_route(
        self,
        journey: JourneyRecord,
        *,
        source_decision: WardenDecision,
        destination_decision: WardenDecision,
        product_ref: str,
    ) -> RouteManifest:
        self._assert_decision_binding(
            source_decision,
            principal_ref=journey.principal_ref,
            silk_account_ref=journey.silk_account_ref,
            arc_ref="QARC-E-FACTORY-001",
            capability_ref=journey.capability_ref,
        )
        self._assert_decision_binding(
            destination_decision,
            principal_ref="DM-PROVIDER-001",
            silk_account_ref="SA-E-PROVIDER-001",
            arc_ref="QARC-E-PROVIDER-001",
            capability_ref=journey.capability_ref,
        )

        route = RouteManifest(
            route_manifest_id=self._journey_ref("RM-A", journey),
            journey_id=journey.journey_id,
            route_version=1,
            product_ref=product_ref,
            hops=(
                RouteHop(
                    sequence=1,
                    arc_ref="QARC-E-FACTORY-001",
                    role="ORIGINATOR",
                    silk_account_ref="SA-E-FACTORY-001",
                    warden_decision_ref=source_decision.decision_id,
                ),
                RouteHop(
                    sequence=2,
                    arc_ref="QARC-E-PROVIDER-001",
                    role="SERVICE_PROVIDER",
                    silk_account_ref="SA-E-PROVIDER-001",
                    warden_decision_ref=destination_decision.decision_id,
                ),
            ),
        )
        journey.route_manifest = route
        journey.statuses["authority"] = "AUTHORIZED"
        self._emit(
            journey,
            "silk.route.authorized",
            actor_ref="WARDEN",
            object_ref=route.route_manifest_id,
        )
        return route

    def _reserve_capacity(self, journey: JourneyRecord) -> dict[str, int]:
        required = {"COMPUTE": 2, "NETWORK": 1, "STORAGE": 1}
        if any(self.capacity[k] < v for k, v in required.items()):
            raise AlphaRuntimeError("CAPACITY_UNAVAILABLE")
        for key, units in required.items():
            self.capacity[key] -= units
        self._emit(
            journey,
            "bnr.capacity.reserved",
            actor_ref="BNR",
            object_ref=self._journey_ref("BNR-RES-A", journey),
        )
        return required

    def _release_capacity(self, journey: JourneyRecord, reserved: dict[str, int]) -> None:
        for key, units in reserved.items():
            self.capacity[key] += units
        self._emit(
            journey,
            "bnr.capacity.released",
            actor_ref="BNR",
            object_ref=self._journey_ref("BNR-RES-A", journey),
        )

    def execute_fixture_a(self, request: dict[str, Any]) -> dict[str, Any]:
        semantic_request = {
            "principal_ref": request["principal_ref"],
            "silk_account_ref": request["silk_account_ref"],
            "programme_ref": "VSR-ROUTE-SERVICE-001",
            "programme_instance_ref": "PI-ROUTE-FACTORY-001",
            "capability_ref": request["requested_capability"],
            "payload": deepcopy(request.get("payload", {})),
        }
        existing = self._request_idempotency.get(request["idempotency_key"])
        if existing:
            existing_request, journey_id = existing
            if existing_request != semantic_request:
                raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
            return self.get_journey(journey_id)

        context = self.resolve_context(
            principal_ref=request["principal_ref"],
            silk_account_ref=request["silk_account_ref"],
            capability_ref=request["requested_capability"],
        )

        source_decision = self.request_warden_decision(
            principal_ref=context["principal_ref"],
            silk_account_ref=context["silk_account_ref"],
            arc_ref=context["arc_ref"],
            capability_ref=context["capability_ref"],
        )

        journey = self.create_journey(
            request_id=request["request_id"],
            idempotency_key=request["idempotency_key"],
            principal_ref=context["principal_ref"],
            silk_account_ref=context["silk_account_ref"],
            programme_ref=context["programme_ref"],
            programme_instance_ref=context["programme_instance_ref"],
            capability_ref=context["capability_ref"],
            request_payload=request.get("payload", {}),
            source_decision=source_decision,
        )

        self._emit(
            journey,
            "digitalme.context.resolved",
            actor_ref=context["principal_ref"],
            object_ref=context["silk_account_ref"],
        )
        self._emit(
            journey,
            "warden.decision.issued",
            actor_ref="WARDEN",
            object_ref=source_decision.decision_id,
        )
        self._emit(
            journey,
            "silk.journey.created",
            actor_ref=context["principal_ref"],
            object_ref=journey.journey_id,
        )

        provider_arc_ref, product_ref = self.resolve_route(journey)

        destination_decision = self.request_warden_decision(
            principal_ref="DM-PROVIDER-001",
            silk_account_ref="SA-E-PROVIDER-001",
            arc_ref=provider_arc_ref,
            capability_ref=context["capability_ref"],
        )
        self._emit(
            journey,
            "warden.decision.issued",
            actor_ref="WARDEN",
            object_ref=destination_decision.decision_id,
        )

        self.authorize_route(
            journey,
            source_decision=source_decision,
            destination_decision=destination_decision,
            product_ref=product_ref,
        )

        reserved = self._reserve_capacity(journey)
        try:
            journey.statuses["execution"] = "RUNNING"
            self._emit(
                journey,
                "synnergyze.execution.started",
                actor_ref="SYNNERGYZE",
                object_ref=self._journey_ref("EP-A", journey),
            )

            payload = journey.request_payload
            route_result = {
                "route_result_id": self._journey_ref("ROUTE-RESULT-A", journey),
                "route": [
                    payload.get("origin", "LOCATION-A"),
                    "NODE-01",
                    "NODE-02",
                    payload.get("destination", "LOCATION-B"),
                ],
                "distance_km": "42.5",
                "status": "GENERATED",
            }
            self._emit(
                journey,
                "creator_product.execution.completed",
                actor_ref=product_ref,
                object_ref=route_result["route_result_id"],
            )
            journey.statuses["execution"] = "COMPLETED"

            genesis_transition = {
                "transition_id": self._journey_ref("GT-A", journey),
                "object_ref": "ROUTE-REQUEST-A-001",
                "from_state": "REQUESTED",
                "to_state": "PROCESSED",
                "status": "COMMITTED",
            }
            self._emit(
                journey,
                "genesis.transition.committed",
                actor_ref="GENESIS",
                object_ref=genesis_transition["transition_id"],
            )

            evidence = {
                "evidence_id": self._journey_ref("EV-A", journey),
                "evidence_type": "OBSERVED",
                "fact_class": "FACT",
                "content_ref": route_result["route_result_id"],
            }
            self._emit(
                journey,
                "river.evidence.recorded",
                actor_ref="RIVER",
                object_ref=evidence["evidence_id"],
            )

            effect_receipt = {
                "receipt_id": self._journey_ref("RR-A", journey),
                "evidence_status": "SUFFICIENT",
                "effect_status": "CONFORMING",
                "evidence_refs": [
                    evidence["evidence_id"],
                    genesis_transition["transition_id"],
                ],
            }
            journey.statuses["evidence"] = effect_receipt["evidence_status"]
            journey.statuses["effect"] = effect_receipt["effect_status"]
            self._emit(
                journey,
                "river.effect.verified",
                actor_ref="RIVER",
                object_ref=effect_receipt["receipt_id"],
            )

            commercial_event = self.compile_commercial_event(
                journey,
                idempotency_key=f"ce:{journey.journey_id}:route",
                trigger_receipt_ref=effect_receipt["receipt_id"],
            )
            journey.commercial_event = commercial_event
            journey.statuses["commercial"] = "COMPILED"

            self._emit(
                journey,
                "settlement.requested",
                actor_ref="SILK",
                object_ref=self._journey_ref("SET-A", journey),
            )
            journey.settlement = {
                "settlement_id": self._journey_ref("SET-A", journey),
                "commercial_event_ref": commercial_event["commercial_event_id"],
                "status": "CONFIRMED",
            }
            journey.statuses["settlement"] = "CONFIRMED"
            self._emit(
                journey,
                "settlement.confirmed",
                actor_ref="BANK-TEST-001",
                object_ref=journey.settlement["settlement_id"],
            )
        finally:
            self._release_capacity(journey, reserved)

        journey.empire_projection = {
            "projection_id": self._journey_ref("EMP-A", journey),
            "journey_id": journey.journey_id,
            "principal_ref": journey.principal_ref,
            "programme_ref": journey.programme_ref,
            "provider_arc_ref": "QARC-E-PROVIDER-001",
            "product_ref": product_ref,
            "execution": journey.statuses["execution"],
            "effect": journey.statuses["effect"],
            "gross_value": (journey.commercial_event or {}).get("gross_value"),
            "settlement": journey.statuses["settlement"],
            "bnr_consumption": {"COMPUTE": 2, "NETWORK": 1, "STORAGE": 1},
        }
        self._emit(
            journey,
            "empire.projection.updated",
            actor_ref="EMPIRE",
            object_ref=journey.empire_projection["projection_id"],
        )

        allocations = journey.commercial_event["allocations"] if journey.commercial_event else []
        checks = {
            "authority": journey.statuses["authority"] == "AUTHORIZED",
            "execution": journey.statuses["execution"] == "COMPLETED",
            "evidence": journey.statuses["evidence"] == "SUFFICIENT",
            "effect": journey.statuses["effect"] == "CONFORMING",
            "commercial_balance": sum(a["amount"] for a in allocations)
            == (journey.commercial_event or {}).get("gross_value", -1),
            "settlement": journey.statuses["settlement"] == "CONFIRMED",
            "capacity_released": self.capacity
            == {"COMPUTE": 100, "NETWORK": 100, "STORAGE": 100},
            "projection": journey.empire_projection is not None,
        }
        self._emit(
            journey,
            "reconciliation.started",
            actor_ref="RECONCILIATION",
            object_ref=self._journey_ref("REC-A", journey),
        )
        if not all(checks.values()):
            raise AlphaRuntimeError("RECONCILIATION_FAILED")

        journey.statuses["reconciliation"] = "RECONCILED"
        journey.statuses["lifecycle"] = "COMPLETE"
        journey.reconciliation = {
            "reconciliation_id": self._journey_ref("REC-A", journey),
            "status": "RECONCILED",
            "checks": checks,
            "unresolved_items": [],
        }
        self._emit(
            journey,
            "reconciliation.completed",
            actor_ref="RECONCILIATION",
            object_ref=journey.reconciliation["reconciliation_id"],
        )
        return self.get_journey(journey.journey_id)

    def compile_commercial_event(
        self,
        journey: JourneyRecord,
        *,
        idempotency_key: str,
        trigger_receipt_ref: str,
    ) -> dict[str, Any]:
        existing = self._commercial_idempotency.get(idempotency_key)
        if existing:
            return deepcopy(existing)

        event = {
            "commercial_event_id": self._journey_ref("CE-A", journey),
            "journey_id": journey.journey_id,
            "trigger_receipt_ref": trigger_receipt_ref,
            "gross_value": 100,
            "currency": "INR",
            "allocations": [
                {"beneficiary": "SA-E-PROVIDER-001", "type": "PROVIDER", "amount": 50},
                {"beneficiary": "DM-CREATOR-001", "type": "CREATOR_ROYALTY", "amount": 30},
                {"beneficiary": "BNR-REFERENCE-001", "type": "BNR_INFRASTRUCTURE", "amount": 20},
            ],
        }
        self._commercial_idempotency[idempotency_key] = deepcopy(event)
        self._emit(
            journey,
            "commercial.event.compiled",
            actor_ref="COMMERCIAL_COMPILER",
            object_ref=event["commercial_event_id"],
        )
        for index, allocation in enumerate(event["allocations"], start=1):
            self._emit(
                journey,
                "commercial.allocation.created",
                actor_ref="COMMERCIAL_COMPILER",
                object_ref=f'{event["commercial_event_id"]}:allocation:{index}:{allocation["type"]}',
            )
        return event

    def get_journey(self, journey_id: str) -> dict[str, Any]:
        journey = self._journeys[journey_id]
        route = journey.route_manifest
        return {
            "journey_id": journey.journey_id,
            "request_id": journey.request_id,
            "principal_ref": journey.principal_ref,
            "silk_account_ref": journey.silk_account_ref,
            "programme_ref": journey.programme_ref,
            "programme_instance_ref": journey.programme_instance_ref,
            "capability_ref": journey.capability_ref,
            "request_payload": deepcopy(journey.request_payload),
            "route": None
            if route is None
            else {
                "route_manifest_id": route.route_manifest_id,
                "route_version": route.route_version,
                "product_ref": route.product_ref,
                "hops": [
                    {
                        "sequence": hop.sequence,
                        "arc_ref": hop.arc_ref,
                        "role": hop.role,
                        "silk_account_ref": hop.silk_account_ref,
                        "warden_decision_ref": hop.warden_decision_ref,
                    }
                    for hop in route.hops
                ],
            },
            "statuses": deepcopy(journey.statuses),
            "commercial_event": deepcopy(journey.commercial_event),
            "settlement": deepcopy(journey.settlement),
            "empire_projection": deepcopy(journey.empire_projection),
            "reconciliation": deepcopy(journey.reconciliation),
            "event_log": deepcopy(journey.event_log),
        }
