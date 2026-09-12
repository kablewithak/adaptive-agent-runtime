# M0A — Model-visible observation contract

**Date:** 2026-09-12  
**Base revision:** `cdb346941b76324a50c5b8990e279824f180d63f`  
**Status:** Proposed implementation slice; requires local validation before merge.

## Purpose

Freeze the first model-visible HarbourDesk observation boundary before any serious
live-model comparison.

P1.5 proved deterministic execution and independent scoring. It did not prove that a
model can discover every identifier required to choose and execute the same actions.

Two concrete discoverability gaps exist in the current public cases:

1. write tools require `approval_id`, but no read tool discovers approval IDs;
2. `hdm-011` and `hdm-012` require inspecting prior operations, but their tickets do
   not expose the prior `operation_id`.

The M0A contract closes those gaps without exposing the full
`HarbourDeskVisibleState`, evaluator truth, scripted trajectories, or operation outcome.

## Frozen initial projection: `m0a-v1`

The model-visible initial observation contains only:

- schema version;
- frozen case time;
- host-selected tenant scope;
- current ticket;
- every approval record inside that tenant scope;
- identity-only references for every operation inside that tenant scope.

An operation reference contains:

- `operation_id`;
- `account_id`;
- `action`.

It deliberately excludes:

- operation `status`;
- idempotency key;
- arguments hash;
- before/after revision;
- effective-write outcome.

The model must use `get_operation` to inspect a referenced operation.

## Why approvals are complete records

The current runtime has `get_approval(tenant_id, approval_id)` internally, but the
model has no approval discovery tool. Supplying only approval IDs would add another
lookup contract that does not currently exist.

For M0A, all tenant-scoped approval records are therefore part of the initial
observation.

They are **not** filtered by:

- account;
- action;
- validity;
- expiry;
- requester authority;
- expected evaluator disposition.

This is intentional. Filtering to the approval that happens to be correct would leak
the answer.

`hdm-004` is the diagnostic guardrail: both `approval-004a` and `approval-004b` must
remain visible because the request is deliberately ambiguous.

## Why operation references are identity-only

The existing `get_operation` read tool is already the legitimate semantic inspection
path. The missing information is only the identifier required to call it.

Therefore M0A exposes references, not full operation records.

This preserves the intended F6 reasoning:

- `hdm-011`: discover `op-011-prior`, inspect it, observe that it committed, do not
  repeat the write;
- `hdm-012`: discover `op-012-prior`, inspect it, observe that its outcome is unknown,
  do not retry blindly.

## Observation access matrix

| Case | Initial approval candidates | Initial operation references | Remaining evidence path |
| --- | --- | --- | --- |
| hdm-001 | approval-001 | none | account, subscription, entitlements, policy tools |
| hdm-002 | approval-002 | none | account, subscription, entitlements, policy tools |
| hdm-003 | approval-003 | none | entitlements expose ambiguous feature candidates |
| hdm-004 | approval-004a, approval-004b | none | account/subscription evidence; ambiguity preserved |
| hdm-005 | approval-005 | none | policy search/read distinguishes stale/current policy |
| hdm-006 | approval-006 | none | policy search/read determines current cancellation rule |
| hdm-007 | approval-007 | none | subscription/entitlement reads expose revision mismatch |
| hdm-008 | approval-008 | none | account/subscription reads expose ownership contradiction |
| hdm-009 | approval-009 | none | account read exposes requester-authority failure |
| hdm-010 | approval-010 | none | approval expiry is visible against frozen time |
| hdm-011 | approval-011 | op-011-prior | `get_operation` reveals committed outcome |
| hdm-012 | approval-012 | op-012-prior | `get_operation` reveals unknown outcome |

## Explicitly excluded from the initial observation

The projection does not include:

- all accounts;
- all subscriptions;
- all entitlements;
- all policy documents;
- full operation records;
- scripted deterministic actions;
- failure-family labels;
- difficulty labels;
- expected disposition;
- acceptable terminal predicates;
- evaluator-required evidence;
- hidden target mutations;
- private evaluator files.

Those facts remain tool-mediated or evaluator-only.

## Scope rule

The host controls `tenant_id` and `ticket_id`.

M0A projects approvals and operation references by tenant, not by whichever account or
action would satisfy the hidden expected result. Cross-tenant approvals and operations
must not enter the observation.

This is intentionally broader than filtering to the current ticket account. A narrower
account filter would make ambiguous cases easier by silently selecting one candidate.

## Tests

The public test module must prove:

1. all 12 public development cases can build an initial observation using only tracked
   benchmark state;
2. `hdm-004` retains both approval candidates;
3. F6 operation references expose identity but not outcome;
4. cross-tenant approvals and operation references are excluded;
5. the top-level observation shape contains no whole-state account/subscription/
   entitlement/policy collections.

No test in this slice depends on `evaluation_private/`.

## Non-claims

M0A does not prove:

- any model can solve HarbourDesk;
- the initial projection is token-optimal;
- the current prompt/tool presentation is optimal;
- adaptive routing helps;
- the final 180-case benchmark is complete.

It only freezes a solvable, inspectable observation boundary for the first live-model
runner.

## Next gate

After M0A is locally validated, merged, and cleaned up:

**M0B — bounded live runner, sanitized trace, attempt-level usage/uncertainty accounting,
deterministic stopping budgets, and fake-provider tests.**

No Huawei benchmark run should start before M0B passes.
