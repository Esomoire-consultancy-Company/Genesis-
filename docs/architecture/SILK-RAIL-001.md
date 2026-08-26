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
- **SILK Account** is a participation account that references roles, licences, rights, obligations, provider bindings, programmes, routes, and reconciliation state. It is not a bank account and is not, by itself, a custodial wallet.
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

SILK has exactly four account classes in this edition:

- `INDIVIDUAL_STUDENT`
- `FAMILY`
- `ENTERPRISE`
- `INSTITUTIONAL`

Creator is a role/licence relationship, not an account class. Programme, Location, ARC, Commons, commercial roles, creator rights, and similar participation contexts are represented through governed relationships, memberships, licences, entitlements, and references attached to one of the four SILK account classes.

Account class describes the principal participation container. It does not grant authority or regulated financial permissions.

## 5. SILK instruction classes

R0.1 recognises these instruction classes as a shared grammar:

### Monetary settlement-execution instructions

- `PAYMENT`
- `COLLECTION`
- `SETTLEMENT`
- `REFUND`
- `REMITTANCE`

These five classes represent instructions that may be sent to a regulated or sandbox provider for monetary execution. They MUST carry `value.kind = MONEY`, a decimal-string amount, and currency before execution.

### Economic rights and participation instructions

- `ENTITLEMENT_GRANT`
- `ENTITLEMENT_TRANSFER`
- `LICENCE_GRANT`
- `REVENUE_SHARE`
- `ROYALTY`
- `ASSET_PARTICIPATION`
- `CREATOR_PARTICIPATION`
- `COMMONS_PARTICIPATION`

These classes are not intrinsically cash movements. For example, a `REVENUE_SHARE` or `ROYALTY` may first represent a governed right, participation formula, entitlement, or obligation before any money is realised.

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

Mission, incentive, bonus, participation, revenue-share, and royalty instructions MAY represent rights, credits, participation interests, services, assets, or other non-cash economic semantics when that is their actual state.

When such an economic relationship becomes payable or collectable in money, the actual cash movement MUST be represented by a separate settlement-execution instruction such as `PAYMENT`, `COLLECTION`, `SETTLEMENT`, `REFUND`, or `REMITTANCE`. That execution instruction receives its own Warden authorization and provider/reconciliation chain. A right or formula therefore does not silently become permission to move money.

This list is extensible by later governed editions. New instruction types MUST declare scope, authority requirements, evidence requirements, reconciliation semantics, and whether they are economic-semantic instructions or provider-executable settlement instructions.

All monetary values, whenever present, MUST use decimal strings rather than binary floating-point JSON numbers. Applicable currency/asset scale is governed by the selected provider or asset policy.

## 6. Ordered federation route

A SILK journey that crosses more than one ARC, programme boundary, custody boundary, or commercial responsibility boundary MUST preserve the journey as an ordered `federation_route[]` rather than reducing the transaction to a source and destination pair.

Each federation hop records at minimum:

- zero-based `hop_index`;
- `arc_ref`;
- `from_silk_account_ref`;
- `to_silk_account_ref`;
- the Warden decision governing that hop.

A hop MAY additionally preserve:

- custody state before and after the hop;
- commercial obligation references;
- River/evidence references.

The route has two semantic invariants that JSON Schema alone cannot express:

1. `hop_index` values are contiguous and ordered from zero; and
2. each hop's `to_silk_account_ref` equals the next hop's `from_silk_account_ref`.

Per-hop authority does not replace the instruction-level Warden decision. It preserves local authority and custody/commercial context along a federated journey.

## 7. Instruction lifecycle

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

Post-execution exception states such as `PARTIALLY_SETTLED`, `REVERSED`, and `DISPUTED` MUST preserve the Warden decision, execution route, River evidence, and exception reference. They cannot be used as lineage-free escape states after money or another external effect has moved.

Every transition MUST be attributable to an actor/system, timestamped, and linked to evidence or a decision reference where applicable.

## 8. Provider binding rule

SILK stores governed references to provider relationships. R0.1 MUST NOT store plaintext secrets, private keys, bank login credentials, card secrets, UPI PINs, telecom authentication secrets, or equivalent sensitive credentials in Genesis source control.

Provider bindings may identify capabilities such as:

- bank account or beneficiary reference;
- payment instrument token/reference;
- UPI or payment-provider route;
- telecom/eSIM subscription reference;
- network capability;
- provider-specific opaque account identifier.

A provider credential proves provider-side access only. It does not substitute for Warden authority.

Provider validity rules are fail-closed:

- an `EXPIRED` binding MUST carry a non-null `valid_until`;
- when both are present, `valid_until` MUST be greater than or equal to `valid_from`;
- an `ACTIVE` or `PROVISIONAL` binding MUST NOT remain operational after `valid_until`;
- cross-field ordering and as-of-time freshness are semantic checks because JSON Schema cannot compare sibling timestamp values or evaluate wall-clock freshness by itself;
- contract CI MUST run JSON Schema Draft 2020-12 validation with `date-time` format checking enabled.

## 9. Atomic SILK meaning

Every SILK movement must be explainable using the following fields:

1. **Who** — principal and SILK account.
2. **Did what** — instruction type and objective.
3. **To/through whom** — counterparty and ordered federation route.
4. **Under what right** — contract, licence, entitlement, programme, or obligation.
5. **With whose authority** — instruction-level and, where applicable, per-hop Warden decision references.
6. **For what value** — money, asset, right, service, credit, or participation interest.
7. **Using what provider** — selected external execution provider where applicable.
8. **What happened** — provider result and RiverOS evidence.
9. **What changed** — realised effect and custody/state transitions.
10. **What remains** — open obligation, exception, dispute, reconciliation, or compensation state.

## 10. Invariants

R0.1 implementations MUST preserve these invariants:

1. SILK MUST NOT create or mutate canonical principal identity outside Genesis.
2. SILK MUST NOT authorise itself; authority comes from Warden or an explicitly recognised lawful authority boundary.
3. External provider authentication MUST NOT be treated as Warden consent.
4. Monetary execution MUST remain separated from SILK participation semantics unless a later authorised product boundary explicitly changes this.
5. VSR and EmpireOS MUST consume the same canonical SILK instruction/effect history rather than maintaining separate transaction truth.
6. Every execution-capable instruction MUST carry an idempotency key and execution must be idempotent at the external boundary.
7. Every externally executed instruction MUST be reconcilable against provider result and RiverOS evidence.
8. Sensitive provider secrets MUST NOT be committed to this repository.
9. Learned/derived projections MUST NOT replace Genesis, Warden, or RiverOS canonical state.
10. A claimed observed/reconciled/final effect MUST carry at least one RiverOS evidence reference.
11. Federated journeys MUST preserve ordered per-hop account, authority, custody, evidence, and commercial context rather than collapsing intermediate hops.
12. An economic right, formula, entitlement, incentive, royalty, or participation relationship MUST NOT itself be treated as authorization for monetary provider execution; cash realization requires a separate governed settlement-execution instruction.

## 11. R0.1 implementation scope

This edition includes contract and synthetic-proof surfaces:

- rail authority/custody boundary;
- four-class SILK account schema;
- role/licence references separate from account classes;
- provider binding schema;
- SILK instruction envelope schema;
- ordered federation-route grammar;
- SILK event envelope and event grammar;
- non-monetary entitlement happy-path fixture;
- authority-denied, execution-failure/compensation, and duplicate-delivery fixtures;
- contract tests, adversarial schema tests, and read-only CI verification.

It intentionally excludes:

- custody of fiat or stored value;
- live bank/UPI/payment credentials;
- production provider adapters;
- production settlement execution;
- automatic revenue distribution;
- tax or regulatory determination;
- irreversible external actions.

Those capabilities require separate later editions, tests, provider contracts, and authority review.

## 12. Reference proofs

### R0.1 non-monetary proof

```text
DigitalMe principal
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

### R0.2 sandbox provider proof

R0.2 adds a deterministic, credential-free provider adapter and provider-result contract. The proof exercises:

```text
EXECUTION_REQUESTED
  -> sandbox provider ACCEPTED
  -> SETTLEMENT_PENDING
  -> sandbox provider SETTLED + synthetic provider receipt
  -> RiverOS EFFECT_OBSERVED
  -> RECONCILED
  -> FINAL
```

The sandbox never connects to a bank or payment network, never holds funds, and never interprets provider access as Warden authority. See `SILK-SANDBOX-PROVIDER-001`.

## 13. Supersession

This document is additive and provisional. Later editions MUST identify:

- scope;
- effective date;
- authority/approver;
- evidence or test basis;
- fields or behaviours superseded;
- migration requirements.
