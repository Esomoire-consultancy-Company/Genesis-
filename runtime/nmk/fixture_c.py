from __future__ import annotations

from copy import deepcopy
from typing import Any

from runtime.nmk.alpha import (
    ACCOUNT_CLASSES,
    AlphaRuntime,
    AlphaRuntimeError,
    AuthorityDenied,
    JourneyRecord,
    RouteHop,
    RouteManifest,
    WardenDecision,
)


class FixtureCRuntime(AlphaRuntime):
    """Nonconforming-but-fully-evidenced cold-chain reference journey."""

    TEMPERATURE_MIN_C = 2.0
    TEMPERATURE_MAX_C = 8.0

    def __init__(self) -> None:
        super().__init__()
        self.digitalmes.update(
            {
                "DM-DRIVER-C-001": {"status": "ACTIVE"},
                "DM-RECEIVER-C-001": {"status": "ACTIVE"},
                "DM-CREATOR-C-001": {"status": "ACTIVE"},
            }
        )
        self.accounts.update(
            {
                "SA-E-LOGISTICS-C-001": {
                    "account_class": "ENTERPRISE",
                    "status": "ACTIVE",
                    "members": {
                        "DM-DRIVER-C-001": {
                            "relationship": "EMPLOYEE",
                            "role": "SERVICE_OPERATOR",
                        }
                    },
                },
                "SA-I-RECEIVER-C-001": {
                    "account_class": "INSTITUTIONAL",
                    "status": "ACTIVE",
                    "members": {
                        "DM-RECEIVER-C-001": {
                            "relationship": "STAFF",
                            "role": "AUTHORIZED_RECEIVER",
                        }
                    },
                },
            }
        )
        self.arcs.update(
            {
                "QARC-E-LOGISTICS-C-001": {
                    "arc_class": "ENTERPRISE",
                    "silk_account_ref": "SA-E-LOGISTICS-C-001",
                    "status": "ACTIVE",
                },
                "QARC-I-RECEIVER-C-001": {
                    "arc_class": "INSTITUTIONAL",
                    "silk_account_ref": "SA-I-RECEIVER-C-001",
                    "status": "ACTIVE",
                },
            }
        )
        self.programmes["VSR-COLD-CHAIN-001"] = {
            "status": "ACTIVE",
            "eligible_arc_classes": {"ENTERPRISE", "INSTITUTIONAL"},
            "required_capabilities": {"CAP-COLD-CHAIN-TRANSPORT"},
        }
        self.programme_instances.update(
            {
                "PI-COLD-FACTORY-C-001": {
                    "programme_ref": "VSR-COLD-CHAIN-001",
                    "arc_ref": "QARC-E-FACTORY-001",
                    "status": "ACTIVE",
                },
                "PI-COLD-LOGISTICS-C-001": {
                    "programme_ref": "VSR-COLD-CHAIN-001",
                    "arc_ref": "QARC-E-LOGISTICS-C-001",
                    "status": "ACTIVE",
                },
                "PI-COLD-RECEIVER-C-001": {
                    "programme_ref": "VSR-COLD-CHAIN-001",
                    "arc_ref": "QARC-I-RECEIVER-C-001",
                    "status": "ACTIVE",
                },
            }
        )
        self.creator_licences["CL-COLD-SENSOR-001"] = {
            "creator_ref": "DM-CREATOR-C-001",
            "status": "ACTIVE",
            "eligible_arc_classes": {"ENTERPRISE", "INSTITUTIONAL"},
            "eligible_programmes": {"VSR-COLD-CHAIN-001"},
            "capabilities": {"CAP-COLD-CHAIN-TRANSPORT"},
        }
        self.products["SPP-COLD-SENSOR-001"] = {
            "creator_ref": "DM-CREATOR-C-001",
            "licence_ref": "CL-COLD-SENSOR-001",
            "status": "ACTIVE",
            "capabilities": {"CAP-COLD-CHAIN-TRANSPORT"},
        }
        self._fixture_c: dict[str, dict[str, Any]] = {}

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
            or account["account_class"] not in ACCOUNT_CLASSES
            or principal_ref not in account["members"]
            or not arc
            or arc["status"] != "ACTIVE"
            or arc["silk_account_ref"] != silk_account_ref
        ):
            raise AuthorityDenied("WARDEN_DENIED")
        self._decision_counter += 1
        return WardenDecision(
            decision_id=f"WD-C-{self._decision_counter:06d}",
            principal_ref=principal_ref,
            silk_account_ref=silk_account_ref,
            arc_ref=arc_ref,
            capability_ref=capability_ref,
            decision="ALLOW",
        )

    def _create_fixture_c_journey(
        self,
        *,
        request: dict[str, Any],
        source_decision: WardenDecision,
    ) -> JourneyRecord:
        semantic_request = {
            "principal_ref": request["principal_ref"],
            "silk_account_ref": request["silk_account_ref"],
            "programme_ref": "VSR-COLD-CHAIN-001",
            "programme_instance_ref": "PI-COLD-FACTORY-C-001",
            "capability_ref": request["requested_capability"],
            "payload": deepcopy(request.get("payload", {})),
        }
        existing = self._request_idempotency.get(request["idempotency_key"])
        if existing:
            existing_request, journey_id = existing
            if existing_request != semantic_request:
                from runtime.nmk.alpha import IdempotencyConflict

                raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
            return self._journeys[journey_id]

        self._assert_decision_binding(
            source_decision,
            principal_ref=request["principal_ref"],
            silk_account_ref=request["silk_account_ref"],
            arc_ref="QARC-E-FACTORY-001",
            capability_ref=request["requested_capability"],
        )
        self._journey_counter += 1
        journey = JourneyRecord(
            journey_id=f"SJ-C-{self._journey_counter:06d}",
            request_id=request["request_id"],
            idempotency_key=request["idempotency_key"],
            principal_ref=request["principal_ref"],
            silk_account_ref=request["silk_account_ref"],
            programme_ref="VSR-COLD-CHAIN-001",
            programme_instance_ref="PI-COLD-FACTORY-C-001",
            capability_ref=request["requested_capability"],
            request_payload=deepcopy(request.get("payload", {})),
        )
        journey.statuses["authority"] = "PARTIALLY_AUTHORIZED"
        self._journeys[journey.journey_id] = journey
        self._request_idempotency[request["idempotency_key"]] = (
            deepcopy(semantic_request),
            journey.journey_id,
        )
        return journey

    def _authorize_fixture_c_route(
        self,
        journey: JourneyRecord,
        *,
        source: WardenDecision,
        logistics: WardenDecision,
        receiver: WardenDecision,
    ) -> RouteManifest:
        bindings = (
            (source, journey.principal_ref, journey.silk_account_ref, "QARC-E-FACTORY-001"),
            (logistics, "DM-DRIVER-C-001", "SA-E-LOGISTICS-C-001", "QARC-E-LOGISTICS-C-001"),
            (receiver, "DM-RECEIVER-C-001", "SA-I-RECEIVER-C-001", "QARC-I-RECEIVER-C-001"),
        )
        for decision, principal, account, arc in bindings:
            self._assert_decision_binding(
                decision,
                principal_ref=principal,
                silk_account_ref=account,
                arc_ref=arc,
                capability_ref=journey.capability_ref,
            )
        route = RouteManifest(
            route_manifest_id=self._journey_ref("RM-C", journey),
            journey_id=journey.journey_id,
            route_version=1,
            product_ref="SPP-COLD-SENSOR-001",
            hops=(
                RouteHop(1, "QARC-E-FACTORY-001", "ORIGINATOR", "SA-E-FACTORY-001", source.decision_id),
                RouteHop(2, "QARC-E-LOGISTICS-C-001", "SERVICE_PROVIDER", "SA-E-LOGISTICS-C-001", logistics.decision_id),
                RouteHop(3, "QARC-I-RECEIVER-C-001", "RECEIVER", "SA-I-RECEIVER-C-001", receiver.decision_id),
            ),
        )
        journey.route_manifest = route
        journey.statuses["authority"] = "AUTHORIZED"
        self._emit(journey, "silk.route.authorized", actor_ref="WARDEN", object_ref=route.route_manifest_id)
        return route

    def execute_fixture_c(self, request: dict[str, Any]) -> dict[str, Any]:
        existing = self._request_idempotency.get(request["idempotency_key"])
        if existing:
            expected, journey_id = existing
            actual = {
                "principal_ref": request["principal_ref"],
                "silk_account_ref": request["silk_account_ref"],
                "programme_ref": "VSR-COLD-CHAIN-001",
                "programme_instance_ref": "PI-COLD-FACTORY-C-001",
                "capability_ref": request["requested_capability"],
                "payload": deepcopy(request.get("payload", {})),
            }
            if expected != actual:
                from runtime.nmk.alpha import IdempotencyConflict

                raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
            return self.get_fixture_c_journey(journey_id)

        if request["silk_account_ref"] != "SA-E-FACTORY-001":
            raise AuthorityDenied("ENTERPRISE_ACCOUNT_REQUIRED")
        capability = request["requested_capability"]
        if capability != "CAP-COLD-CHAIN-TRANSPORT":
            raise AuthorityDenied("CAPABILITY_NOT_ENTITLED")

        source = self.request_warden_decision(
            principal_ref=request["principal_ref"],
            silk_account_ref=request["silk_account_ref"],
            arc_ref="QARC-E-FACTORY-001",
            capability_ref=capability,
        )
        journey = self._create_fixture_c_journey(request=request, source_decision=source)
        self._emit(journey, "digitalme.context.resolved", actor_ref=journey.principal_ref, object_ref=journey.silk_account_ref)
        self._emit(journey, "warden.decision.issued", actor_ref="WARDEN", object_ref=source.decision_id)
        self._emit(journey, "silk.journey.created", actor_ref=journey.principal_ref, object_ref=journey.journey_id)

        product = self.products["SPP-COLD-SENSOR-001"]
        licence = self.creator_licences[product["licence_ref"]]
        if (
            product["status"] != "ACTIVE"
            or licence["status"] != "ACTIVE"
            or capability not in product["capabilities"]
            or capability not in licence["capabilities"]
            or journey.programme_ref not in licence["eligible_programmes"]
            or not {"ENTERPRISE", "INSTITUTIONAL"}.issubset(licence["eligible_arc_classes"])
        ):
            raise AlphaRuntimeError("PRODUCT_INELIGIBLE_FOR_ROUTE")
        self._emit(journey, "silk.route.proposed", actor_ref="VSR", object_ref=self._journey_ref("RM-C", journey))

        logistics = self.request_warden_decision(
            principal_ref="DM-DRIVER-C-001",
            silk_account_ref="SA-E-LOGISTICS-C-001",
            arc_ref="QARC-E-LOGISTICS-C-001",
            capability_ref=capability,
        )
        receiver = self.request_warden_decision(
            principal_ref="DM-RECEIVER-C-001",
            silk_account_ref="SA-I-RECEIVER-C-001",
            arc_ref="QARC-I-RECEIVER-C-001",
            capability_ref=capability,
        )
        self._emit(journey, "warden.decision.issued", actor_ref="WARDEN", object_ref=logistics.decision_id)
        self._emit(journey, "warden.decision.issued", actor_ref="WARDEN", object_ref=receiver.decision_id)
        self._authorize_fixture_c_route(journey, source=source, logistics=logistics, receiver=receiver)

        reserved = self._reserve_capacity(journey)
        observations: list[dict[str, Any]] = []
        exception: dict[str, Any] | None = None
        compensation: dict[str, Any] | None = None
        try:
            journey.statuses["execution"] = "RUNNING"
            self._emit(journey, "synnergyze.execution.started", actor_ref="SYNNERGYZE", object_ref=self._journey_ref("EP-C", journey))
            self._emit(journey, "creator_product.activated", actor_ref="SPP-COLD-SENSOR-001", object_ref="SPP-COLD-SENSOR-001")
            self._emit(journey, "custody.transfer.accepted", actor_ref="GENESIS", object_ref=self._journey_ref("CT-C-FACTORY-LOGISTICS", journey))

            series = request.get("payload", {}).get(
                "temperatures_c", [3.2, 4.8, 6.1, 7.4, 10.9, 9.6, 7.8]
            )
            for index, temperature in enumerate(series, start=1):
                evidence_id = f'{self._journey_ref("EV-C", journey)}-{index:03d}'
                observation = {
                    "evidence_id": evidence_id,
                    "evidence_type": "OBSERVED",
                    "fact_class": "FACT",
                    "temperature_c": float(temperature),
                }
                observations.append(observation)
                self._emit(journey, "river.evidence.recorded", actor_ref="RIVER", object_ref=evidence_id)
                if exception is None and not (self.TEMPERATURE_MIN_C <= float(temperature) <= self.TEMPERATURE_MAX_C):
                    exception = {
                        "exception_id": self._journey_ref("EX-C", journey),
                        "type": "TEMPERATURE_THRESHOLD_BREACH",
                        "triggering_evidence_ref": evidence_id,
                        "status": "OPEN",
                    }
                    self._emit(journey, "exception.opened", actor_ref="EXCEPTION_FABRIC", object_ref=exception["exception_id"])

            if exception is None:
                raise AlphaRuntimeError("FIXTURE_C_REQUIRES_NONCONFORMANCE")

            exception_decision = self.request_warden_decision(
                principal_ref="DM-RECEIVER-C-001",
                silk_account_ref="SA-I-RECEIVER-C-001",
                arc_ref="QARC-I-RECEIVER-C-001",
                capability_ref=capability,
            )
            self._emit(journey, "warden.decision.issued", actor_ref="WARDEN", object_ref=exception_decision.decision_id)

            journey.statuses["execution"] = "COMPLETED"
            genesis_transition = {
                "transition_id": self._journey_ref("GT-C", journey),
                "object_ref": "SHIPMENT-C-001",
                "from_state": "RECEIVED",
                "to_state": "QUARANTINED_FOR_INSPECTION",
                "status": "COMMITTED",
            }
            self._emit(journey, "genesis.transition.committed", actor_ref="GENESIS", object_ref=genesis_transition["transition_id"])
            self._emit(journey, "custody.transfer.accepted", actor_ref="GENESIS", object_ref=self._journey_ref("CT-C-LOGISTICS-RECEIVER", journey))

            effect_receipt = {
                "receipt_id": self._journey_ref("RR-C", journey),
                "evidence_status": "SUFFICIENT",
                "effect_status": "NONCONFORMING",
                "evidence_refs": [item["evidence_id"] for item in observations],
                "observed_maximum_c": max(item["temperature_c"] for item in observations),
            }
            journey.statuses["evidence"] = "SUFFICIENT"
            journey.statuses["effect"] = "NONCONFORMING"
            self._emit(journey, "river.effect.verified", actor_ref="RIVER", object_ref=effect_receipt["receipt_id"])

            commercial_event = {
                "commercial_event_id": self._journey_ref("CE-C", journey),
                "journey_id": journey.journey_id,
                "event_type": "NONCONFORMING_SERVICE_ADJUSTMENT",
                "contract_ref": "SCC-COLD-C-001",
                "trigger_receipt_ref": effect_receipt["receipt_id"],
                "gross_value": 10000,
                "currency": "INR",
                "status": "ADJUSTMENT_REQUIRED",
            }
            journey.commercial_event = deepcopy(commercial_event)
            journey.statuses["commercial"] = "ADJUSTMENT_REQUIRED"
            self._emit(journey, "commercial.event.compiled", actor_ref="COMMERCIAL_COMPILER", object_ref=commercial_event["commercial_event_id"])
            journey.settlement = {
                "settlement_id": self._journey_ref("SET-C", journey),
                "commercial_event_ref": commercial_event["commercial_event_id"],
                "status": "PENDING",
                "reason": "COMMERCIAL_ADJUSTMENT_OPEN",
            }
            self._emit(journey, "settlement.pending", actor_ref="SILK", object_ref=journey.settlement["settlement_id"])

            compensation = {
                "compensation_id": self._journey_ref("COMP-C", journey),
                "exception_ref": exception["exception_id"],
                "status": "RUNNING",
            }
            self._emit(journey, "compensation.started", actor_ref="COMPENSATION", object_ref=compensation["compensation_id"])
            journey.statuses["settlement"] = "PENDING"
        finally:
            self._release_capacity(journey, reserved)

        journey.statuses["lifecycle"] = "COMPLETE"
        journey.statuses["reconciliation"] = "OPEN"
        journey.reconciliation = {
            "reconciliation_id": self._journey_ref("REC-C", journey),
            "status": "OPEN",
            "unresolved_items": [
                "NONCONFORMING_EFFECT",
                "COMMERCIAL_ADJUSTMENT_REQUIRED",
                "SETTLEMENT_PENDING",
                "EXCEPTION_OPEN",
                "COMPENSATION_RUNNING",
            ],
        }
        self._emit(journey, "reconciliation.started", actor_ref="RECONCILIATION", object_ref=journey.reconciliation["reconciliation_id"])

        journey.empire_projection = {
            "projection_id": self._journey_ref("EMP-C", journey),
            "journey_id": journey.journey_id,
            "execution": "COMPLETED",
            "evidence": "SUFFICIENT",
            "effect": "NONCONFORMING",
            "sensor_effect": "CONFORMING",
            "commercial": "ADJUSTMENT_REQUIRED",
            "settlement": "PENDING",
            "reconciliation": "OPEN",
        }
        self._emit(journey, "empire.projection.updated", actor_ref="EMPIRE", object_ref=journey.empire_projection["projection_id"])

        self._fixture_c[journey.journey_id] = {
            "observations": deepcopy(observations),
            "effect_receipt": deepcopy(effect_receipt),
            "genesis_transition": deepcopy(genesis_transition),
            "exception": deepcopy(exception),
            "compensation": deepcopy(compensation),
            "commercial_history": [deepcopy(commercial_event)],
            "component_effects": {
                "SPP-COLD-SENSOR-001": "CONFORMING",
                "TRANSPORT_SERVICE": "NONCONFORMING",
            },
        }
        return self.get_fixture_c_journey(journey.journey_id)

    def resolve_fixture_c(self, journey_id: str) -> dict[str, Any]:
        journey = self._journeys[journey_id]
        state = self._fixture_c[journey_id]
        if journey.statuses["reconciliation"] == "RECONCILED":
            return self.get_fixture_c_journey(journey_id)

        adjustment = {
            "commercial_event_id": self._journey_ref("CE-C-ADJUSTMENT", journey),
            "journey_id": journey_id,
            "supersedes_ref": state["commercial_history"][0]["commercial_event_id"],
            "trigger_receipt_ref": state["effect_receipt"]["receipt_id"],
            "gross_value": 10000,
            "currency": "INR",
            "allocations": [
                {"beneficiary": "SA-E-LOGISTICS-C-001", "type": "PROVIDER", "amount": 6000},
                {"beneficiary": "DM-CREATOR-C-001", "type": "CREATOR_ROYALTY", "amount": 1000},
                {"beneficiary": "QARC-I-RECEIVER-C-001", "type": "INSPECTION", "amount": 500},
                {"beneficiary": "SA-I-RECEIVER-C-001", "type": "RECEIVER_COMPENSATION", "amount": 2500},
            ],
            "status": "COMPILED",
        }
        state["commercial_history"].append(deepcopy(adjustment))
        journey.commercial_event = deepcopy(adjustment)
        journey.statuses["commercial"] = "COMPILED"
        self._emit(journey, "commercial.event.adjusted", actor_ref="COMMERCIAL_COMPILER", object_ref=adjustment["commercial_event_id"])
        for index, allocation in enumerate(adjustment["allocations"], start=1):
            self._emit(journey, "commercial.allocation.created", actor_ref="COMMERCIAL_COMPILER", object_ref=f'{adjustment["commercial_event_id"]}:allocation:{index}')

        state["compensation"]["status"] = "COMPLETED"
        state["exception"]["status"] = "RESOLVED"
        self._emit(journey, "compensation.completed", actor_ref="COMPENSATION", object_ref=state["compensation"]["compensation_id"])
        self._emit(journey, "exception.resolved", actor_ref="EXCEPTION_FABRIC", object_ref=state["exception"]["exception_id"])

        journey.settlement = {
            "settlement_id": self._journey_ref("SET-C", journey),
            "commercial_event_ref": adjustment["commercial_event_id"],
            "status": "CONFIRMED",
        }
        self._emit(journey, "settlement.requested", actor_ref="SILK", object_ref=journey.settlement["settlement_id"])
        journey.statuses["settlement"] = "CONFIRMED"
        self._emit(journey, "settlement.confirmed", actor_ref="BANK-TEST-001", object_ref=journey.settlement["settlement_id"])

        journey.statuses["reconciliation"] = "RECONCILED"
        journey.reconciliation = {
            "reconciliation_id": self._journey_ref("REC-C", journey),
            "status": "RECONCILED",
            "checks": {
                "authority": journey.statuses["authority"] == "AUTHORIZED",
                "execution": journey.statuses["execution"] == "COMPLETED",
                "evidence": journey.statuses["evidence"] == "SUFFICIENT",
                "nonconformance_preserved": journey.statuses["effect"] == "NONCONFORMING",
                "commercial_balance": sum(a["amount"] for a in adjustment["allocations"]) == adjustment["gross_value"],
                "compensation": state["compensation"]["status"] == "COMPLETED",
                "exception": state["exception"]["status"] == "RESOLVED",
                "settlement": journey.statuses["settlement"] == "CONFIRMED",
            },
            "unresolved_items": [],
        }
        if not all(journey.reconciliation["checks"].values()):
            raise AlphaRuntimeError("RECONCILIATION_FAILED")
        self._emit(journey, "reconciliation.completed", actor_ref="RECONCILIATION", object_ref=journey.reconciliation["reconciliation_id"])

        journey.empire_projection.update(
            {
                "effect": "NONCONFORMING",
                "commercial": "COMPILED",
                "settlement": "CONFIRMED",
                "reconciliation": "RECONCILED",
            }
        )
        self._emit(journey, "empire.projection.updated", actor_ref="EMPIRE", object_ref=journey.empire_projection["projection_id"])
        return self.get_fixture_c_journey(journey_id)

    def get_fixture_c_journey(self, journey_id: str) -> dict[str, Any]:
        result = self.get_journey(journey_id)
        state = self._fixture_c.get(journey_id, {})
        result["fixture_c"] = deepcopy(state)
        return result
