# SILK-RAIL-001

**Edition:** R0.1  
**Status:** Provisional architecture contract  
**Repository role:** Genesis registry-side definition  
**Base commit:** `2c5316f9ae1d4971d7e8eb4894c3d212bd5b3bd2`

## 1. Purpose

SILK is the Registry-backed participation, value-instruction, and settlement-coordination fabric used by Virtual Silk Road programmes and related operating surfaces.

SILK does not replace Genesis, DigitalMe, Warden, RiverOS, Synnergyze, EmpireOS, a bank, a payment provider, or a telecom provider. It connects governed economic and participation instructions across those boundaries.

## 2. Authority boundaries

The following boundaries are normative for R0.1:

- **Genesis** is the canonical registry for principal, relationship, organisation, location, and SILK binding state.
- **DigitalMe** is the principal identity context for a person or other recognised actor.
- **Warden** is the authority, consent, and policy decision boundary. SILK MUST NOT self-authorise an instruction.
- **SILK Account** is a participation account that references rights, obligations, provider bindings, programmes, routes, and reconciliation state. It is not a bank account and is not, by itself, a custodial wallet.
- **Synnergyze** selects and orchestrates execution capabilities after authority has been established.
- **External regulated providers** perform regulated money movement or regulated network services under their own credentials and controls.
- **RiverOS** records evidence, receipts, observations, and realised effects.
- **VSR and EmpireOS** are projections over the same governed events and evidence; they MUST NOT create separate economic truth.

## 3. Canonical flow

```text
Genesis
  -> DigitalMe / recognised principal
  -> SILK Account
  -> SILK Instruction (DRAFT / RESOLVED)
  -> Warden authority decision
  -> Synnergyze route/orchestration
  -> External provider execution, when applicable
  -> RiverOS evidence/effect
  -> Reconciliation
  -> VSR + EmpireOS projections
```

The SILK Instruction exists before Warden decides it. Warden authorises or denies the resolved instruction; Warden does not create the instruction. No stage may silently assume the authority of another stage.

## 4. SILK Account classes

R0.1 defines the following account classes:

- `PERSONAL`
- `CREATOR`
- `BUSINESS`
- `LOCATION`
- `PROGRAMME`
- `ARC`
- `INSTITUTION`
- `COMMONS`

Account class describes participation context. It does not grant authority or regulated financial permissions.

## 5. SILK instruction classes

R0.1 recognises these instruction classes as a shared grammar:

### Monetary and settlement coordination

- `PAYMENT`
- `COLLECTION`
- `SETTLEMENT`
- `REFUND`
- `REMITTANCE`

### Rights and participation

- `ENTITLEMENT_GRANT`
- `ENTITLEMENT_TRANSFER`
- `LICENCE_GRANT`
- `REVENUE_SHARE`
- `ROYALTY`
- `ASSET_PARTICIPATION`
- `CREATOR_PARTICIPATION`
- `COMMONS_PARTICIPATION`

### Commercial obligations

- `PURCHASE_ORDER`
- `INVOICE`
- `RECEIVABLE`
- `OBLIGATION`

### Mission and network value

- `CARBON_CREDIT`
- `MISSION_ALLOCATION`
- `INCENTIVE`
- `BONUS`

This list is extensible by later governed editions. New instruction types MUST declare scope, authority requirements, evidence requirements, and reconciliation semantics.

Monetary instruction values MUST use decimal strings, not binary floating-point JSON numbers. Applicable currency/asset scale is governed by the selected provider or asset policy.

## 6. Instruction lifecycle

The canonical monetary happy-path state machine is:

```text
DRAFT
  -> RESOLVED
  -> AWAITING_AUTHORITY
  -> WARDEN_AUTHORIZED
  -> ROUTE_SELECTED
  -> EXECUTION_REQUESTED
  -> PROVIDER_ACCEPTED
  -> SETTLEMENT_PENDING
  -> SETTLED
  -> RIVER_OBSERVED
  -> RECONCILED
  -> FINAL
```

Non-monetary rights/effect paths MAY skip provider and settlement-only states when no external regulated provider or monetary settlement exists, as defined by `SILK-EVENT-GRAMMAR-001`.

Exception and terminal states include:

- `DENIED`
- `EXPIRED`
- `FAILED`
- `REVERSED`
- `DISPUTED`
- `PARTIALLY_SETTLED`
- `RECONCILIATION_REQUIRED`
- `COMPENSATION_REQUIRED`

Every transition MUST be attributable to an actor/system, timestamped, and linked to evidence or a decision reference where applicable.

## 7. Provider binding rule

SILK stores governed references to provider relationships. R0.1 MUST NOT store plaintext secrets, private keys, bank login credentials, card secrets, UPI PINs, telecom authentication secrets, or equivalent sensitive credentials in Genesis source control.

Provider bindings may identify capabilities such as:

- bank account or beneficiary reference
- payment instrument token/reference
- UPI or payment-provider route
- telecom/eSIM subscription reference
- network capability
- provider-specific account identifier

A provider credential proves provider-side access only. It does not substitute for Warden authority.

Provider validity rules are fail-closed:

- an `EXPIRED` binding MUST carry a non-null `valid_until`;
- when both are present, `valid_until` MUST be greater than or equal to `valid_from`;
- an `ACTIVE` or `PROVISIONAL` binding MUST NOT remain operational after `valid_until`;
- cross-field ordering and as-of-time freshness are semantic checks because JSON Schema cannot compare sibling timestamp values or evaluate wall-clock freshness by itself;
- contract CI MUST run JSON Schema Draft 2020-12 validation with `date-time` format checking enabled.

## 8. Atomic SILK meaning

Every SILK movement must be explainable using the following fields:

1. **Who** — principal and SILK account.
2. **Did what** — instruction type and objective.
3. **To/through whom** — counterparty and route.
4. **Under what right** — contract, licence, entitlement, programme, or obligation.
5. **With whose authority** — Warden decision reference.
6. **For what value** — money, asset, right, service, credit, or participation interest.
7. **Using what provider** — selected external execution provider where applicable.
8. **What happened** — RiverOS evidence and provider result.
9. **What changed** — realised effect.
10. **What remains** — open obligation, exception, dispute, reconciliation, or compensation state.

## 9. Invariants

R0.1 implementations MUST preserve these invariants:

1. SILK MUST NOT create or mutate canonical principal identity outside Genesis.
2. SILK MUST NOT authorise itself; authority comes from Warden or an explicitly recognised lawful authority boundary.
3. External provider authentication MUST NOT be treated as Warden consent.
4. Monetary execution MUST remain separated from SILK participation semantics unless a later authorised product boundary explicitly changes this.
5. VSR and EmpireOS MUST consume the same canonical SILK instruction/effect history rather than maintaining separate transaction truth.
6. Every execution-capable instruction MUST be idempotent or carry an idempotency key.
7. Every externally executed instruction MUST be reconcilable against provider result and RiverOS evidence.
8. Sensitive provider secrets MUST NOT be committed to this repository.
9. Learned/derived projections MUST NOT replace Genesis, Warden, or RiverOS canonical state.
10. A claimed observed/reconciled/final effect MUST carry at least one RiverOS evidence reference.

## 10. R0.1 implementation scope

This edition includes only contract and synthetic-proof surfaces:

- rail authority/custody boundary;
- SILK account schema;
- provider binding schema;
- SILK instruction envelope schema;
- SILK event envelope and event grammar;
- non-monetary entitlement happy-path fixture;
- authority-denied, execution-failure/compensation, and duplicate-delivery fixtures;
- contract tests, adversarial schema tests, and read-only CI verification.

It intentionally excludes:

- custody of fiat or stored value;
- live bank/UPI/payment credentials;
- live provider adapters;
- production settlement execution;
- automatic revenue distribution;
- tax or regulatory determination;
- irreversible external actions.

Those capabilities require separate later editions, tests, provider contracts, and authority review.

## 11. Reference proofs

The implemented first proof is synthetic and non-custodial:

```text
DigitalMe creator
  -> creates ENTITLEMENT_GRANT instruction
  -> Genesis resolves the instruction context
  -> Warden authorises the exact instruction
  -> Synnergyze selects a registry-entitlement route
  -> execution is requested
  -> RiverOS observes the entitlement effect
  -> reconciliation confirms the intended right
  -> SILK finalises the instruction
```

Negative proofs cover Warden denial, duplicate delivery, execution failure, reconciliation requirement, and compensation requirement without creating new authority.

The next provider-bound proof MUST remain sandbox-only and credential-free until a separate provider-adapter contract and authority review are complete.

## 12. Supersession

This document is additive and provisional. Later editions MUST identify:

- scope;
- effective date;
- authority/approver;
- evidence or test basis;
- fields or behaviours superseded;
- migration requirements.
