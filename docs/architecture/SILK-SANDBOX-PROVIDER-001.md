# SILK-SANDBOX-PROVIDER-001

**Edition:** R0.2  
**Status:** Synthetic execution contract  
**Depends on:** `SILK-RAIL-001`, `SILK-EVENT-GRAMMAR-001`  
**Scope:** Credential-free provider acceptance and settlement proof only

## 1. Purpose

R0.2 introduces the first executable provider boundary for SILK without connecting to a regulated provider or moving real funds.

The sandbox exists to prove the control flow and evidence model before any production adapter is considered.

It MUST NOT:

- hold or custody fiat or stored value;
- call a bank, UPI, card, wallet, payment gateway, or telecom API;
- contain live credentials or secrets;
- infer consent from provider access;
- create Warden authority;
- bypass RiverOS evidence or reconciliation;
- perform irreversible external action.

## 2. Entry gate

The sandbox provider accepts an instruction only when all of the following are true:

1. the instruction is in `EXECUTION_REQUESTED`;
2. the instruction carries a `warden_decision_ref`;
3. the instruction carries an `execution_route_ref`;
4. the instruction identifies an exact `provider_binding_ref`;
5. the instruction carries an `idempotency_key`;
6. the provider binding matches the instruction exactly;
7. the provider binding is `ACTIVE` or `PROVISIONAL` and valid at the execution time;
8. the binding carries the capability required by the monetary instruction;
9. the value is monetary and its amount is greater than zero.

The sandbox therefore consumes authority; it never manufactures authority.

## 3. Capability mapping

R0.2 maps monetary SILK instructions to provider capabilities as follows:

| SILK instruction | Required provider capability |
| --- | --- |
| `PAYMENT` | `PAY` |
| `COLLECTION` | `COLLECT` |
| `SETTLEMENT` | `SETTLE` |
| `REFUND` | `REFUND` |
| `REMITTANCE` | `REMIT` |

A provider binding without the exact required capability is non-executable.

## 4. Provider result contract

`silk-provider-result.schema.json` defines a provider result that always preserves:

- provider result ID;
- SILK instruction reference;
- provider binding reference;
- original Warden decision reference;
- original Synnergyze execution route reference;
- idempotency key;
- monetary value;
- provider outcome.

An `ACCEPTED` result requires `accepted_at`.

A `SETTLED` result additionally requires:

- `settled_at`; and
- a non-empty synthetic `provider_receipt_ref`.

A result cannot truthfully claim `SETTLED` in the contract without a receipt reference.

## 5. Idempotency rule

The sandbox derives a deterministic fingerprint from the material execution request.

When the same `idempotency_key` is delivered again:

- if the material request is identical, the existing result is returned and no second execution is created;
- if the material request differs, execution fails with an idempotency conflict.

This rule is required before a production provider adapter because network retry and duplicate delivery are normal operating conditions.

## 6. Settlement timing rule

Settlement MUST NOT predate provider acceptance.

The sandbox therefore rejects any attempt where `settled_at < accepted_at`.

This is a semantic time-ordering invariant in addition to JSON Schema date-time validation.

## 7. Provider-to-River lifecycle

The synthetic monetary proof is:

```text
EXECUTION_REQUESTED
  -> PROVIDER_ACCEPTED
  -> SETTLEMENT_PENDING
  -> SETTLED
  -> RIVER_OBSERVED
  -> RECONCILED
  -> FINAL
```

`PROVIDER_ACCEPTED`, `SETTLEMENT_PENDING`, and `SETTLED` each preserve the Warden decision, execution route, and provider-result reference.

`RIVER_OBSERVED` requires RiverOS evidence. Provider settlement alone is not treated as the final system truth.

## 8. Federation proof

The reference sandbox payment contains a two-hop `federation_route[]`.

The proof preserves:

```text
Factory SILK Account
  -> Factory/Logistics ARC
  -> Logistics SILK Account
  -> Logistics/Institution ARC
  -> Institutional SILK Account
```

Each hop has its own Warden decision and may carry custody and commercial-obligation state.

The test contract verifies that hop indexes are contiguous and that the output SILK account of one hop is the input SILK account of the next.

This prevents a multi-party journey from being flattened into an opaque source/destination transfer.

## 9. Evidence and projections

The sandbox provider may prove only synthetic provider acceptance and settlement.

RiverOS remains responsible for the observed effect/evidence layer. Reconciliation then determines whether the SILK obligation is closed.

VSR and EmpireOS must consume the same finalized instruction/event/evidence chain:

- VSR projects participation, route, counterparty, programme, ARC, rights and network contribution;
- EmpireOS projects cost, payable/receivable and financial operating effect.

Neither projection may invent an independent settlement truth.

## 10. Acceptance criteria

R0.2 is acceptable when CI proves all of the following:

1. all SILK schemas are valid Draft 2020-12 schemas;
2. the sandbox request validates against the instruction and provider-binding contracts;
3. the four canonical SILK account classes are preserved;
4. Creator is not an account class;
5. federation hops are ordered and continuous;
6. execution without Warden authority is rejected;
7. execution before `EXECUTION_REQUESTED` is rejected;
8. wrong, expired, or under-capable provider bindings are rejected;
9. exact duplicate execution is idempotent;
10. conflicting reuse of an idempotency key is rejected;
11. settlement cannot precede acceptance;
12. a settled provider result requires a receipt;
13. provider acceptance through River observation/reconciliation/finalization validates against the event contract.

## 11. Production-adapter gate

A production bank/UPI/payment adapter MUST NOT be derived merely by replacing the sandbox transport.

Before a production adapter exists, a later governed edition must separately define at minimum:

- provider-specific API and credential custody boundary;
- provider onboarding and legal/regulatory relationship;
- capability/mandate and payment-rail semantics;
- beneficiary/account verification;
- signing and secret-management architecture;
- timeout/retry/idempotency semantics;
- provider rejection and partial-settlement semantics;
- reconciliation source of truth;
- refunds/reversals/disputes;
- audit retention and evidence policy;
- Warden approval requirements by action/value/risk;
- incident isolation and kill switch;
- sandbox-to-production promotion evidence.

R0.2 provides no authorization to move production money.

## 12. Supersession

Later editions MUST identify scope, effective date, authority/approver, evidence basis, compatibility impact, and migration requirements.
