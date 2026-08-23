# SILK-NEGATIVE-PATHS-001

**Edition:** R0.1  
**Status:** Provisional negative-path contract  
**Depends on:** `SILK-RAIL-001`, `SILK-EVENT-GRAMMAR-001`  
**Scope:** Denial, replay, failure, reconciliation, and compensation semantics only

## 1. Purpose

This contract proves that SILK fails closed. A denied or failed instruction must not silently continue as though authority or execution succeeded. Duplicate event delivery must not create a second state transition. Recovery and compensation remain governed, attributable, and evidence-backed.

## 2. Authority-denied path

Canonical denial path:

```text
DRAFT
  -> RESOLVED
  -> AWAITING_AUTHORITY
  -> DENIED
```

Requirements:

1. `AUTHORITY_DENIED` MUST contain the exact `warden_decision_ref` that denied the action.
2. The transition MUST end in `DENIED`.
3. No `ROUTE_SELECTED`, `EXECUTION_REQUESTED`, provider, settlement, effect, reconciliation, or finalization event may occur on that denied attempt.
4. A later attempt requires a new governed instruction or an explicitly permitted re-evaluation path; the denied history is never rewritten.

## 3. Duplicate-delivery idempotency

Event transport may deliver the same event more than once. SILK therefore treats `event_id` as a replay key.

For a duplicate delivery with an already-applied `event_id`:

- the second delivery MUST be classified as duplicate/replay;
- it MUST NOT apply the transition again;
- it MUST NOT emit a second downstream execution request;
- it MUST NOT create a new economic, rights, or evidence effect;
- the original event remains the canonical event.

This is distinct from an instruction `idempotency_key`, which protects execution-capable instruction effects across retries. Both protections are required at their respective layers.

## 4. Execution failure path

A governed execution may fail after Warden authorization and route selection:

```text
WARDEN_AUTHORIZED
  -> ROUTE_SELECTED
  -> EXECUTION_REQUESTED
  -> FAILED
```

`EXECUTION_FAILED` MUST carry:

- the original `warden_decision_ref`;
- the selected `execution_route_ref`;
- an `exception_ref` identifying the failure/exception record.

Failure MUST NOT manufacture a new Warden authorization.

## 5. Observed partial effect and reconciliation

A failed request can still leave a real-world or registry-side partial effect. If RiverOS observes such an effect, SILK must not infer success or simply retry blindly.

Canonical escalation:

```text
FAILED
  -> RIVER_OBSERVED
  -> RECONCILIATION_REQUIRED
```

`RECONCILIATION_REQUIRED` MUST reference the relevant Warden decision and exception record. River evidence must remain attached to the observed effect.

## 6. Compensation requirement

If reconciliation determines that the realised effect must be corrected, reversed, restored, refunded, or otherwise compensated, SILK may enter:

```text
RECONCILIATION_REQUIRED
  -> COMPENSATION_REQUIRED
```

`COMPENSATION_REQUIRED` MUST contain:

- `warden_decision_ref` for the original governed instruction context;
- `exception_ref` for the unresolved exception/reconciliation case;
- `river_evidence_refs` proving the effect requiring compensation.

Entering `COMPENSATION_REQUIRED` does **not** itself authorize a compensating action. Any actual compensation execution requires its own lawful authority scope according to the applicable Warden/authority contract.

## 7. Safety invariants

1. Denied instructions do not execute.
2. Duplicate event delivery does not duplicate effects.
3. Failure does not become success by retry or projection.
4. River-observed partial effects are reconciled before closure.
5. Compensation need is evidence-backed but is not self-authorizing.
6. No recovery path may broaden the original Warden authority scope.
7. Historical events remain append-only and attributable.

## 8. R0.1 proofs

This slice contains three deterministic fixtures:

- authority denied before route/execution;
- execution failure with partial River-observed effect leading to reconciliation and compensation required;
- repeated delivery of the same event ID demonstrating replay suppression.

No live payment provider, bank credential, UPI credential, fiat custody, or irreversible external action is used.