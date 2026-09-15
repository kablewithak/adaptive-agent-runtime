# M1A — Context envelope and first HarbourDesk canary

**Date:** 2026-09-15
**Base revision:** `8b62a0dea6838b571a8be28a4d4952bf994512b6`
**Status:** Verified live integration gate; terminal reason-code contract remediated and verified.

## Purpose

M1A is the first bounded live HarbourDesk integration gate after M0A and M0B. It does not rank
models and does not introduce routing. It answers two narrower questions:

1. Does the actual M0A observation plus M0B tool surface fit a sufficient working context envelope
   for the qualified `glm-5.1` profile, including a short continuation?
2. Can one named development case run through the M0B runtime with model-selected actions and then
   be scored independently after the runtime closes?

The reported approximately 6K context window is not treated as an exact model limit. M1A records a
sufficient observed working envelope and explicitly does not claim the absolute maximum.

## Frozen M1A identities

- model: `glm-5.1`
- local endpoint profile: `primary-openai`
- case: `hdm-001`
- runtime: M0B bounded live runner
- observation: M0A `m0a-v1`
- stage accounting ceiling: 250,000 observed tokens when usage is complete
- completion reserve: 768 tokens

`glm-5.1` is an integration choice only. M1A does not claim it is better than GLM-5.2 or either
qualified DeepSeek model.

## Envelope characterization

The envelope probe uses a fresh in-memory copy of the public development case and the actual M0B
runner. The first request therefore contains the real system instruction, M0A observation and tool
schemas used by the runtime.

After the first bounded provider response, M1A attempts one short continuation. When the model made
one tool call and the probe executed it, the continuation uses the real structured tool result. When
the first response is text-only, M1A uses a short user follow-up instead. Provider reasoning state is
carried only in memory where the provider contract requires it.

The durable envelope receipt records only counts, outcomes, usage and errors. It does not persist raw
prompts, free-form model text, provider reasoning or credentials.

A sufficient working envelope is recorded as the largest observed provider input-token count across
the accepted initial/continuation requests plus the frozen 768-token output reserve. This is an
observed sufficient shape, not a context-window maximum.

## Canary execution

The canary uses a second fresh in-memory store for `hdm-001`. It does not reuse state mutated during
the envelope probe.

The model chooses its own tools and arguments. The canary does not load or replay the deterministic
`end_to_end_rehearsals/hdm-001.json` trajectory and does not place expected outcomes in the model
payload.

The M0B runner retains host control of tenant scope, ticket scope, call IDs and write idempotency
keys. It also retains the M0B no-automatic-retry rule and deterministic call/action/time budgets.

## Evaluator custody

Before any live request, the outer M1A orchestration requires:

`evaluation_private/harbourdesk/dev/hdm-001/expected.json`

That file remains local and evaluator-only. The live runtime never receives it. After the live run
returns its authoritative final state, the outer experiment layer invokes the existing deterministic
scorer.

Public M1A tests construct expected outcomes inline and do not depend on `evaluation_private/`.

## Evidence layout

One M1A run writes under `runs/m1a/<run-id>/`:

- `envelope.json`
- `canary-trace.jsonl`
- `summary.json`

`runs/` remains runtime evidence and must not be staged.

The summary preserves:

- envelope acceptance and usage completeness;
- sufficient observed working-envelope tokens when measurable;
- canary stop category;
- provider-attempt and tool-action counts;
- observed usage totals and usage completeness;
- independent score result and failure taxonomy;
- final-state hash and trace hash;
- stage token-cap status.

Unknown or missing usage is never silently converted into a complete zero-cost result.

## First live canary — before contract remediation

Run:

`runs/m1a/m1a-glm51-hdm001-20260915-01/`

Observed:

- M1A status: `pass`
- gate passed: `true`
- envelope: `verified_sufficient`
- sufficient working envelope: 2,606 tokens
- stop: `ticket_terminal`
- attempts: 8
- tool actions: 8
- usage complete: `true`
- observed stage tokens: 23,110
- stage token cap: passed
- independent score: `false`
- scoring failure: `reason_code_mismatch`

The trajectory gathered the correct ticket, account, subscription, entitlement and policy evidence,
performed the expected entitlement reconciliation, and referenced the resulting operation. The final
ticket update used the non-canonical reason string `entitlement_reconciled`.

The scorer correctly rejected that terminal state.

Review showed this was a model-boundary contract defect: `UpdateTicketArgs.resolution_reason_code`
allowed an arbitrary string even though HarbourDesk has a closed canonical reason-code vocabulary.

## Contract remediation

The remediation introduced one canonical `TicketResolutionReasonCode` enum and reused it at the
domain, tool-argument and business-rule boundaries. Because the M0B tool schema is generated from
`UpdateTicketArgs`, the provider-facing `update_ticket` schema now exposes canonical reason values.

The deterministic write boundary also verifies that a canonical reason is enabled by the active
business rules.

Invalid lowercase aliases are rejected; they are not silently normalized.

## Remediation-verification canary

Run:

`runs/m1a/m1a-glm51-hdm001-reason-contract-20260915-01/`

Observed:

- M1A status: `pass`
- gate passed: `true`
- envelope: `verified_sufficient`
- sufficient working envelope: 2,703 tokens
- stop: `ticket_terminal`
- attempts: 8
- tool actions: 8
- usage complete: `true`
- observed stage tokens: 24,944
- stage token cap: passed
- independent score: `true`
- matched predicate index: `0`
- scoring failures: none

The model selected the same substantive eight-step pattern:

1. `get_ticket`
2. `get_account`
3. `get_subscription`
4. `get_entitlements`
5. `search_policies`
6. `read_policy`
7. `reconcile_entitlement`
8. `update_ticket`

The final update used the canonical reason code:

`ENTITLEMENT_RECONCILED`

The independent scorer passed the final state.

The remediation-verification run consumed more tokens than the first canary, so M1A makes no
efficiency-improvement claim from this intervention. The demonstrated improvement is boundary
correctness and independent outcome validity.

## M1A gate result

M1A is complete.

Verified evidence shows:

- the actual HarbourDesk request is accepted by `glm-5.1`;
- a short continuation is supported;
- the model can complete a genuinely model-selected bounded trajectory;
- provider usage is observable and retained;
- the runtime terminates explicitly;
- evaluator truth remains outside the provider payload;
- the final state is independently scoreable;
- the demonstrated terminal-reason contract defect was reproduced, classified, remediated and
  re-verified;
- the verified remediation canary passes independent scoring;
- the stage accounting ceiling was not exceeded.

## Non-claims

M1A does not prove:

- an absolute context limit;
- that `glm-5.1` is the best model;
- that HarbourDesk accuracy is acceptable across the diagnostic set;
- that the current prompt, tool descriptions or budgets are optimal;
- that the eight-step trajectory is token efficient;
- that adaptive routing helps;
- that missing provider usage can be reconstructed exactly.

## Next gate

M1B runs one frozen `glm-5.1` configuration across all 12 development diagnostics once, with a fresh
store and conversation per case and independent scoring for every recoverable final state.

The first M1A canary is retained as before-remediation evidence. The second canary is retained as an
intervention-verification run. Neither should be silently substituted for an untouched M1B baseline
sample.
