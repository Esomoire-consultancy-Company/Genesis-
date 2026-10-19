# SILK-EVENT-GRAMMAR-001

**Edition:** R0.1  
**Status:** Provisional event contract  
**Depends on:** `SILK-RAIL-001`  
**Scope:** Event semantics only; no live provider execution

## 1. Purpose

This contract defines the canonical event grammar for SILK instructions. It exists so Genesis, Warden, Synnergyze, RiverOS, VSR, EmpireOS, and external providers can exchange attributable state changes without collapsing identity, authority, execution, evidence, or projection into one system.

SILK events describe what changed. They do not become a second source of canonical identity, Warden authority, or RiverOS evidence.

## 2. Event envelope

Every SILK event MUST contain:

- `event_id` — globally unique event identifier.
- `event_type` — governed event class.
- `instruction_ref` — SILK instruction being changed.
- `principal_ref` — principal associated with the instruction.
- `silk_account_ref` — SILK participation account.
- `correlation_id` — stable identifier shared by the instruction lifecycle.
- `occurred_at` — event occurrence time.
- `actor` — attributable system or principal that emitted the event.
- `transition.from_state` and `transition.to_state` — explicit state movement.
- `version` — contract edition.

Events MAY additionally carry an authority decision reference, route reference, provider result reference, evidence references, causation reference, and event-specific payload.

## 3. Actor classes

R0.1 recognises:

- `PRINCIPAL`
- `GENESIS`
- `WARDEN`
- `SILK`
- `SYNNERGYZE`
- `PROVIDER`
- `RIVEROS`
- `SYSTEM`

Actor class is provenance, not authority. For example, a `SYNNERGYZE` event may report execution routing, but it MUST NOT manufacture a Warden decision.

## 4. Event classes

### Instruction and resolution

- `INSTRUCTION_CREATED`
- `INSTRUCTION_RESOLVED`
- `AUTHORITY_REQUESTED`
- `AUTHORITY_GRANTED`
- `AUTHORITY_DENIED`
- `ROUTE_SELECTED`

### Execution

- `EXECUTION_REQUESTED`
- `EXECUTION_ACCEPTED`
- `EXECUTION_FAILED`
- `PROVIDER_ACCEPTED`

### Monetary settlement coordination

- `SETTLEMENT_PENDING`
- `SETTLED`

### Evidence and closure

- `EFFECT_OBSERVED`
- `RECONCILIATION_REQUIRED`
- `RECONCILED`
- `COMPENSATION_REQUIRED`
- `DISPUTED`
- `REVERSED`
- `FINALIZED`

## 5. Path semantics

Not every SILK instruction is monetary. Therefore R0.1 defines a common prefix and pathway-specific stages rather than forcing every instruction through payment states.

### 5.1 Common governed prefix

```text
DRAFT
  -> RESOLVED
  -> AWAITING_AUTHORITY
  -> WARDEN_AUTHORIZED
  -> ROUTE_SELECTED
  -> EXECUTION_REQUESTED
```

An execution-capable instruction MUST NOT enter `EXECUTION_REQUESTED` without a valid `warden_decision_ref` and `execution_route_ref`.

### 5.2 Non-monetary rights/effect path

A non-custodial entitlement, licence, participation, or registry effect MAY proceed:

```text
EXECUTION_REQUESTED
  -> RIVER_OBSERVED
  -> RECONCILED
  -> FINAL
```

`PROVIDER_ACCEPTED`, `SETTLEMENT_PENDING`, and `SETTLED` are not required when no external regulated provider or monetary settlement exists.

### 5.3 External-provider path

Where an external provider performs execution, the path MAY include:

```text
EXECUTION_REQUESTED
  -> PROVIDER_ACCEPTED
  -> RIVER_OBSERVED
  -> RECONCILED
  -> FINAL
```

Provider acceptance proves provider-side acceptance only. It does not substitute for Warden authority or RiverOS evidence.

### 5.4 Monetary settlement path

Where regulated money movement exists, the path MAY include:

```text
EXECUTION_REQUESTED
  -> PROVIDER_ACCEPTED
  -> SETTLEMENT_PENDING
  -> SETTLED
  -> RIVER_OBSERVED
  -> RECONCILED
  -> FINAL
```

SILK coordinates the economic meaning and reconciliation state. R0.1 does not custody fiat or execute live payment credentials.

## 6. Authority invariants

1. `AUTHORITY_GRANTED` MUST identify a Warden or explicitly recognised lawful authority decision reference.
2. `AUTHORITY_DENIED` is terminal for the attempted authority path unless a new governed instruction or explicitly permitted re-evaluation is created.
3. `EXECUTION_REQUESTED` MUST occur after authority is granted.
4. Provider authentication or acceptance MUST NOT be interpreted as consent.
5. A route selector MUST NOT broaden the scope granted by the authority decision.

## 7. Evidence invariants

1. `EFFECT_OBSERVED` MUST reference at least one RiverOS evidence receipt.
2. `RECONCILED` MUST reference evidence sufficient to explain the realised effect and outstanding state.
3. `FINALIZED` MUST NOT erase prior events; closure is append-only.
4. Projection systems such as VSR and EmpireOS consume the same event history and MUST NOT rewrite canonical evidence.

## 8. Idempotency and causality

- Every instruction keeps one stable `correlation_id` across its lifecycle.
- Every event has a unique `event_id`.
- Where one event directly causes another, `causation_id` SHOULD reference the predecessor event.
- Re-delivery of an existing `event_id` MUST be treated as duplicate delivery, not a new state transition.
- Externally executable operations remain subject to the instruction's `idempotency_key`.

## 9. First synthetic proof

The first R0.1 proof is intentionally non-monetary:

```text
DigitalMe creator
  -> ENTITLEMENT_GRANT instruction
  -> Warden authority request
  -> Warden grants exact scoped authority
  -> Synnergyze selects a registry entitlement execution route
  -> execution requested
  -> RiverOS observes entitlement effect
  -> reconciliation confirms the intended right exists
  -> SILK instruction finalises
```

The proof MUST contain no bank credentials, payment token, UPI secret, provider settlement, fiat custody, or irreversible external action.

## 10. Acceptance criteria for this slice

The R0.1 event slice is acceptable when:

1. the event envelope is machine-readable;
2. the synthetic flow preserves a single correlation ID;
3. execution cannot precede Warden authorization;
4. the non-monetary flow contains no required payment/provider state;
5. River evidence appears before reconciliation;
6. the lifecycle reaches `FINAL` without creating a second authority or identity source.

## 11. Supersession

Later editions MUST state scope, effective date, approver/authority, evidence basis, compatibility impact, and migration requirements.