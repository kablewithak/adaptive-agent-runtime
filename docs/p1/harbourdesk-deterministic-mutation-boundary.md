# HarbourDesk P1.4 — Deterministic Mutation Boundary

**Status:** Proposed implementation slice for the synthetic HarbourDesk environment.  
**Scope:** Deterministic write controls only. No model receives write access in this gate.

## Goal

Prove that HarbourDesk can reject unsafe or stale state changes and commit valid
state changes atomically before any LLM is allowed to call write-capable tools.

The mutation boundary supports:

- `reconcile_entitlement`
- `schedule_cancellation`
- `update_ticket`

## Boundary design

Write-tool arguments are validated with frozen Pydantic contracts.

The host, not the model, supplies:

- `tenant_id`
- current `ticket_id`
- `call_id`
- stable `idempotency_key`

This keeps tenancy and retry identity outside model control.

### Entitlement reconciliation

`reconcile_entitlement`:

1. scopes the ticket and account to the host tenant;
2. requires the ticket to target the same account;
3. checks that the requester is an authorised account contact;
4. detects subscription ownership contradictions;
5. checks an exact prior idempotency record before applying a new write;
6. rejects stale subscription or entitlement revisions;
7. requires an applicable, unexpired `reconcile_entitlement` approval;
8. derives the desired entitlement state from the structured plan catalogue;
9. commits the entitlement update and operation record in one SQLite transaction.

The model does not supply `enabled=true/false`. Reconciliation computes the target
state deterministically from the plan catalogue.

### Cancellation scheduling

`schedule_cancellation` applies the same tenant, requester, ownership, approval,
revision and idempotency controls.

The minimum cancellation date is now a structured rule in
`benchmarks/harbourdesk/business_rules_v1.json` rather than being inferred from
natural-language policy text.

For the current synthetic rules:

`minimum_notice_days = 7`

The environment therefore enforces the date deterministically.

### Ticket updates

`update_ticket` may update only the host-provided current ticket.

It validates:

- expected ticket revision;
- referenced policy document IDs;
- referenced operation IDs within tenant scope;
- idempotency.

Ticket bookkeeping is recorded as an operation with `effective_write=false`.
This keeps it auditable without causing evaluator business-write counters to treat a
ticket status change as a customer-state mutation.

## Atomicity

SQLite mutation methods use compare-and-swap revisions.

The customer-state update and its operation receipt are committed in the same
transaction.

Tests deliberately verify that:

- a stale compare-and-swap revision rolls back without inserting an operation;
- a duplicate idempotency key rolls back the second state change.

## Commit uncertainty

An existing operation with `status=unknown` blocks a blind retry.

This is intentionally conservative. The runtime must inspect or escalate an unknown
prior operation rather than assume that the missing acknowledgement means the write
did not happen.

P1.4 does not yet create real transport-level commit ambiguity. It proves the
recovery behavior for an already-observed unknown operation state.

## Idempotency

For business writes and ticket updates:

- an exact committed replay returns the prior operation and current committed state;
- a reused idempotency key with different arguments is rejected;
- an unknown prior outcome is rejected;
- a failed prior operation is not silently retried.

Operation IDs are deterministically derived from tenant, action and host-supplied
idempotency key.

## Evaluation independence

The mutation layer does not read `evaluation_private/*` and does not call the
terminal-state scorer.

Environment permissions and evaluator acceptance remain separate implementations.

The environment can therefore reject unsafe writes without becoming a self-grading
oracle.

## Offline mutation rehearsal

Run:

```powershell
python .\scripts\run_harbourdesk_mutation_rehearsal.py
```

The rehearsal covers nine deterministic scenarios:

1. valid entitlement reconciliation;
2. exact idempotent replay;
3. stale revision rejection;
4. valid cancellation scheduling;
5. unauthorised requester rejection;
6. expired approval rejection;
7. subscription ownership-conflict rejection;
8. unknown prior operation blocks blind retry;
9. ticket bookkeeping update.

Acceptance signals:

```text
MUTATION_REHEARSAL_STATUS=pass
MUTATION_REHEARSAL_SCENARIO_COUNT=9
MUTATION_REHEARSAL_PASSED_COUNT=9
MUTATION_REHEARSAL_EXPECTED_REJECTIONS=5
MUTATION_REHEARSAL_EFFECTIVE_BUSINESS_WRITES=2
MUTATION_REHEARSAL_TICKET_UPDATES=1
MUTATION_REHEARSAL_LLM_CALLS=0
```

A sanitised receipt is written under ignored `runs/harbourdesk/`.

## What this gate proves

If validation passes, P1.4 establishes evidence for:

- deterministic tenant/ticket mutation context;
- requester-authority enforcement;
- action-scoped approval enforcement;
- approval expiry enforcement at the frozen case clock;
- structured cancellation-date enforcement;
- revision compare-and-swap;
- idempotent replay behavior;
- atomic state+operation persistence;
- conservative unknown-operation recovery;
- ticket reference validation;
- no-LLM write rehearsal.

## Non-claims

P1.4 does **not** establish:

- model competence at choosing when to write;
- full agent trajectory correctness;
- provider tool-call compatibility for these HarbourDesk schemas;
- locked benchmark quality;
- routing quality or token savings;
- transport-level distributed transaction guarantees.

## Next gate

P1.5 should integrate the read and write tool registries into a deterministic
single-step environment interface and execute scripted end-to-end trajectories that
terminate in states scored by the independent evaluator.

Only after those no-LLM end-to-end trajectories pass should a model be allowed to
drive HarbourDesk tools.
