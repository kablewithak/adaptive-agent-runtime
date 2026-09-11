# HarbourDesk Domain and Independent Evaluation Contract

**Phase:** P1.1  
**Status:** Proposed domain contract implemented; simulator and scorer not yet implemented.

## Purpose

HarbourDesk is the synthetic B2B support environment used to test whether model and
context allocation can reduce inference consumption while preserving verified task
outcomes.

This phase freezes the vocabulary of the environment before implementing business
tools or the evaluator.

## Requirements

1. Every simulated case has an explicit frozen UTC clock.
2. Operational records are typed, immutable values; state changes replace records
   rather than mutating model-owned state.
3. Tenant/account/subscription/entitlement relationships are explicit IDs.
4. Policy validity and approval validity are represented as data, not inferred from
   wall-clock time.
5. Evaluator expectations live in a separate module and describe acceptable terminal
   states rather than exact tool trajectories.

## Domain records

The initial state vocabulary is:

- `Tenant`
- `Account`
- `Subscription`
- `Entitlement`
- `Ticket`
- `PolicyDocument`
- `Approval`

Operations are intentionally deferred to the simulator slice because idempotency,
commit uncertainty, and before/after revisions must be designed together.

## Initial invented business semantics

These are synthetic HarbourDesk rules, not real legal or commercial terms.

### Plans and entitlements

The benchmark will use a small explicit plan catalogue. At minimum:

- `starter`: base application access
- `team`: base access plus collaboration and export features
- `business`: team features plus administrative controls

The exact feature matrix will be frozen before manual benchmark cases are authored.

### Reconciliation

An entitlement reconciliation may only succeed when:

- the target account is in the current tenant scope;
- the subscription state supports the requested entitlement;
- the runtime has an applicable, unexpired approval for
  `reconcile_entitlement`;
- the write uses the expected current record revision;
- an identical previously committed logical operation is not applied twice.

The model may propose the action. Deterministic environment code enforces these
conditions.

### Cancellation

A cancellation may only be scheduled when:

- account and subscription scope are valid;
- an applicable approval for `schedule_cancellation` exists;
- the requested effective date satisfies the frozen policy in force for the case;
- the expected subscription revision matches current state.

The actual effective-date policy will be represented in case-visible policy
documents rather than hidden in a model prompt.

### Requester authority

A requester lacking the required authority must not cause a state-changing write.
The correct terminal outcome may be clarification or escalation depending on the
case-specific policy and evidence.

### Policy versions

Cases may contain superseded policy material. Validity is determined against the
case's frozen UTC clock and version metadata. A stale note is evidence, not
authority.

## Evaluation boundary

The runtime must not receive:

- expected dispositions;
- benchmark family or difficulty labels;
- evaluator predicates;
- hidden required evidence annotations;
- future tool results.

The evaluator receives the initial state, final state, operation evidence, and
`ExpectedCaseOutcome`.

An `ExpectedCaseOutcome` can contain multiple acceptable terminal predicates. This
allows different valid trajectories or dispositions without requiring an exact
golden transcript.

The evaluator contract can constrain:

- resolution / clarification / escalation;
- reason code;
- required policy-document references;
- entitlement terminal values;
- subscription terminal values;
- expected or maximum effective-write counts;
- whether unrelated records must remain unchanged.

## Independence rule

Runtime permission checks and evaluator scoring must not collapse into one shared
"correct action" function.

Sharing ID types, enum values, and canonical serialization helpers is acceptable.
The scorer must independently compare observed terminal state with hand-reviewed
expected predicates.

This is necessary so a bug in the environment's write validator cannot certify
itself as correct.

## Non-claims

P1.1 does not establish:

- a functioning HarbourDesk simulator;
- correct business-tool behavior;
- benchmark quality;
- evaluator correctness;
- model performance;
- routing performance.

Those require later phases.

## Next slice

P1.2 will:

1. freeze the explicit plan/feature and policy rule set;
2. author 12 manual development cases across the six benchmark families;
3. create evaluator-only `expected.json` fixtures;
4. implement the independent terminal-state scorer;
5. mutation-test known wrong final states before any LLM-generated case scaling.
