# HarbourDesk P1.2 — Manual Case Blueprint and Independent Scorer

**Status:** Implemented as development-only authoring evidence.  
**Scope:** 12 manual examples, two per benchmark family. These are not the final 180-case suite.

## Source alignment

The project PRD requires six families:

- F1 — Straightforward access mismatch
- F2 — Ambiguous request
- F3 — Stale or superseded policy
- F4 — Multi-record contradiction
- F5 — Authorisation boundary
- F6 — Interrupted workflow

It also requires manual development examples, evaluator-only expected outcomes,
mutation checks, and outcome scoring rather than exact golden transcripts.

## Frozen synthetic rules

The authoring blueprint is stored in
`benchmarks/harbourdesk/business_rules_v1.json`.

The initial plan catalogue is:

- `starter`: `base_access`
- `team`: `base_access`, `collaboration`, `exports`
- `business`: all Team features plus `admin_controls`

State-changing business actions require:

- same-tenant/account scope;
- an authorised requesting contact;
- an applicable unexpired action approval;
- the current expected revision;
- idempotent execution.

All times are explicit UTC and cases use a frozen clock.

These are invented HarbourDesk rules, not real terms of service.

## Manual development cases

The 12 cases are intentionally small and diagnostic. They are two examples per
family, not replacements for the required three independently designed development
templates per family in the final 36-template suite.

Runtime-visible files live under:

`benchmarks/harbourdesk/dev/<case>/`

Each contains:

- `case.json`
- `initial_state.json`
- `documents.jsonl`

Evaluator-only expectations remain local under:

`evaluation_private/harbourdesk/dev/<case>/expected.json`

`evaluation_private/*` is intentionally ignored by Git. The repository therefore
must not depend on private expected-outcome files for clean-clone unit tests or CI.

The local private manifest records family, difficulty, authoring rationale and
SHA-256 hashes. Runtime-facing `case.json` deliberately excludes family, difficulty,
split and expected-outcome labels.

## Scoring boundary

`score_case(...)` receives:

- initial state;
- final state;
- evaluator-only expected predicates.

It does not call an environment permission function.

It independently checks:

- terminal ticket disposition;
- reason code;
- required policy references;
- required prior-operation references;
- target entitlement state;
- target subscription state;
- new effective business-write count;
- unrelated-record preservation.

A case passes when at least one hand-reviewed acceptable terminal predicate passes.

## Repository-test boundary

Public scorer unit tests use a separate synthetic fixture defined inside the test
module. They do not read the ignored benchmark labels.

This preserves both properties:

1. a clean clone can run the repository test suite without private evaluator files;
2. benchmark expected outcomes remain outside the runtime-visible repository surface.

## Mutation evidence

The scorer regression tests deliberately inject:

1. wrong-account state mutation;
2. stale entitlement source revision;
3. extra effective write;
4. invalid policy citation;
5. false completion with the target state left incorrect.

All five must fail scoring.

This is the minimum evidence required before scaling case generation.

## Deliberate limits

P1.2 does not yet prove:

- tool permission logic;
- transaction correctness;
- idempotent write implementation;
- agent competence;
- benchmark generalisation;
- routing quality.

The manual cases are development examples. The locked evaluation set must not be
generated or tuned against until the environment and scorer pass later gates.

## Next gate

P1.3 should implement the local HarbourDesk store and read-only tool layer first,
then state-changing tools behind deterministic permission, revision and idempotency
checks. The first integration target should execute these manual cases without an
LLM using explicit scripted trajectories so simulator correctness can be measured
before model behavior is introduced.
