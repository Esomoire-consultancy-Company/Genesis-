# SILK-PROJECTION-FABRIC-001

**Edition:** R0.3  
**Status:** Synthetic projection contract  
**Depends on:** `SILK-RAIL-001`, `SILK-SANDBOX-PROVIDER-001`  
**Scope:** Shared finalized economic fact -> VSR and EmpireOS projections

## 1. Purpose

R0.3 prevents Virtual Silk Road and EmpireOS from becoming independent transaction ledgers.

Both applications must project from one finalized SILK economic fact. They may present different operational meanings, but they must preserve the same canonical source lineage.

## 2. Canonical source fact

A `SILK Economic Fact` is created only after the proof chain reaches all of the following:

- the SILK instruction exists and preserves its Warden decision;
- the provider result is `SETTLED` for the R0.3 monetary proof;
- the provider result preserves the same instruction, Warden decision, route, amount, and currency;
- the SILK lifecycle reaches `FINALIZED -> FINAL`;
- RiverOS evidence is present;
- the ordered federation route remains valid.

The fact contains a deterministic `source_fingerprint` and derives its `economic_fact_id` from that source.

A material change to the source must therefore create a different fingerprint/fact rather than silently changing an existing projection.

## 3. Shared-truth invariant

VSR and EmpireOS projections MUST carry identical values for:

- `economic_fact_ref`;
- `instruction_ref`;
- `source_fingerprint`;
- `provider_result_ref`;
- `river_evidence_refs`;
- monetary `value`;
- `finalized_at`.

If any of those fields differ, the two surfaces are no longer projections of the same transaction truth.

## 4. VSR projection

For the R0.3 PAYMENT proof, the VSR projection expresses network participation meaning:

- `participation_effect = VALUE_TRANSFER`;
- counterparty;
- programme;
- ordered ARC references derived from the federation route.

VSR is therefore able to show where value participation occurred through the network without becoming the accounting ledger.

## 5. EmpireOS projection

For the same PAYMENT fact, the EmpireOS projection expresses operating-financial meaning:

- `financial_effect = OUTFLOW`;
- counterparty;
- originating commercial obligation;
- the exact same amount and currency as the VSR view.

EmpireOS is therefore able to show cost/liability effects without creating a second settlement record.

## 6. Example

```text
SILK Economic Fact
  instruction: PAYMENT
  value: INR 1000.00
  provider result: SETTLED
  River evidence: present
  federation route:
      Factory -> Logistics -> Institution

          | same economic_fact_ref
          | same source_fingerprint
          | same provider result
          | same River evidence
          | same INR 1000.00
          |
          +-----------------------+
          |                       |
          v                       v
        VSR                    EmpireOS
  VALUE_TRANSFER                OUTFLOW
  programme/ARCs           obligation/cost
```

The two outputs differ in interpretation, not in canonical transaction facts.

## 7. Fail-closed rules

R0.3 projection MUST fail when:

1. the provider result is not `SETTLED`;
2. the provider result references a different instruction;
3. Warden decision lineage differs between instruction/provider/final event;
4. execution-route lineage differs;
5. provider amount or currency differs from the SILK instruction;
6. RiverOS evidence is absent;
7. the final event does not transition to `FINAL`;
8. the federation route is broken;
9. the economic fact fingerprint has been altered;
10. the economic-fact ID does not derive from the verified source fingerprint.

## 8. Projection immutability

A projection is rebuildable derived state.

Canonical truth remains in the governed SILK instruction/event/evidence chain. VSR and EmpireOS projections may be deleted and rebuilt from that source. They MUST NOT mutate the underlying economic fact.

This preserves the event-first/rebuildable-projection architecture.

## 9. Scope limit

R0.3 currently proves `PAYMENT` only.

It does not yet define projection semantics for:

- collections;
- refunds;
- remittances;
- receivables;
- invoices;
- royalties;
- revenue shares;
- carbon credits;
- creator/commons participation;
- asset participation;
- multi-currency conversion;
- tax or regulatory accounting.

Those should be added instruction class by instruction class with explicit financial direction and VSR participation meaning.

## 10. Acceptance criteria

R0.3 is acceptable when CI proves:

1. the economic-fact and projection schemas are valid Draft 2020-12 contracts;
2. one settled/finalized PAYMENT creates one valid economic fact;
3. both projections validate against the same projection contract;
4. canonical truth fields are byte-for-byte equal across VSR and EmpireOS outputs;
5. VSR preserves federation ARC context;
6. EmpireOS preserves counterparty and obligation context;
7. unsettled results are rejected;
8. amount drift is rejected;
9. missing River evidence is rejected;
10. Warden-lineage drift is rejected;
11. a tampered economic fact cannot be projected.

## 11. Next edition

The next edition should generalize this projection compiler across non-PAYMENT SILK instruction classes while preserving explicit directionality and accounting/participation semantics for each class.

## 12. Supersession

Later editions MUST state scope, effective date, authority/approver, evidence basis, compatibility impact, and migration requirements.
