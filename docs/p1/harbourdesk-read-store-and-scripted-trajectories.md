# HarbourDesk P1.3 — SQLite Read Store and Scripted No-LLM Trajectories

**Status:** Implemented as the read-only environment seam.  
**LLM calls:** none.  
**Business writes:** none.

## Purpose

P1.3 proves that the 12 manual development cases can be loaded into a local,
inspectable state store and queried through bounded tool contracts before any model
is allowed to change state.

The slice intentionally separates three concerns:

1. validated benchmark state;
2. SQLite persistence and tenant-scoped reads;
3. tool-level observations returned to a future runtime.

## SQLite design

`HarbourDeskStore` stores one case at a time. Each domain record is retained as
validated canonical JSON alongside the small set of indexed fields needed for safe
lookup. Ordinals preserve fixture ordering so a snapshot can reconstruct the
validated input state exactly.

The store does not enforce every logical domain relationship with database foreign
keys. This is intentional: benchmark family F4 contains contradictory records that
must remain representable and observable. Correctness checks belong to deterministic
business rules and the independent evaluator, not accidental database rejection.

Runtime-facing methods are read-only in P1.3.

## Read tools

Implemented tools:

- `get_ticket`
- `get_account`
- `get_subscription`
- `get_entitlements`
- `search_policies`
- `read_policy`
- `get_operation`

Each call has validated arguments and returns either a typed observation or a
machine-readable error. Missing or cross-tenant records fail closed.

`search_policies` is deterministic lexical retrieval. It deliberately returns both
stale and current matching policy versions and marks whether each document is active
at the case's frozen UTC time. This preserves the stale-policy benchmark family
rather than silently filtering the hard evidence away.

## Subscription scoping nuance

A subscription is visible when an account in the current tenant references its
subscription ID. The store does **not** require the subscription record's own
`account_id` to agree before returning it.

That rule is deliberate. If lookup instead joined on matching account ownership,
the F4 ownership-conflict case would degrade into a misleading `not_found` result
and the agent could never inspect the contradiction it is expected to detect.

## Scripted trajectories

Each of the 12 manual cases has a committed development-only read trajectory under
`benchmarks/harbourdesk/read_rehearsals/`. These trajectories are not intended to
represent optimal agent behavior. They are integration fixtures proving that:

- case state loads successfully;
- the intended read surfaces are usable;
- machine-readable tool contracts compose across a trajectory;
- no state changes occur;
- no LLM is needed to establish simulator read correctness.

The trajectories are committed because repository tests and the offline rehearsal
must work from a clean clone. They are development integration fixtures only and are
never included in model prompts or runtime case payloads. Private evaluator expected
outcomes remain under ignored `evaluation_private/`.

## Evidence gate

P1.3 passes only when:

- SQLite state round-trips exactly;
- cross-tenant reads fail closed;
- contradictory subscription ownership remains observable;
- stale and current policies are both retrievable with frozen-time validity flags;
- all 12 scripted read trajectories execute without tool errors;
- running a trajectory leaves the state snapshot unchanged.

## Non-claims

P1.3 does not establish:

- mutation correctness;
- approval enforcement;
- revision enforcement;
- idempotency;
- commit-uncertainty recovery;
- benchmark task success;
- model quality.

## Next gate

P1.4 should add state-changing operations behind deterministic controls:

- `reconcile_entitlement`
- `schedule_cancellation`
- `update_ticket`

The mutation layer must enforce tenant scope, requester authority, approval validity,
expected revision and idempotency before the first LLM-driven trajectory is allowed.
It should then run scripted success and deliberate-failure trajectories through the
independent terminal-state scorer.
