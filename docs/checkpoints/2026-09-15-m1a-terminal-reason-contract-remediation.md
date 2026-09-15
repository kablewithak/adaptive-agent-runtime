# M1A terminal reason-code contract remediation

**Date:** 2026-09-15
**Status:** Implemented, locally validated and verified by a new bounded live canary
**Case:** `hdm-001`
**Model:** `glm-5.1`

## Before-remediation evidence

Original run:

`runs/m1a/m1a-glm51-hdm001-20260915-01/`

Observed receipt:

- M1A integration status: `pass`
- integration gate: `true`
- envelope status: `verified_sufficient`
- sufficient working envelope: 2,606 tokens
- canary stop: `ticket_terminal`
- model attempts: 8
- tool actions: 8
- stage usage complete: `true`
- observed stage tokens: 23,110
- stage token cap: passed
- independent task score: failed
- scoring failure: `reason_code_mismatch`

The model trajectory selected the correct account, subscription, entitlement, current policy and
reconciliation operation. Its final `update_ticket` call used:

`entitlement_reconciled`

The benchmark business rules define the canonical code:

`ENTITLEMENT_RECONCILED`

## Failure classification

This was a model-boundary contract defect rather than sufficient evidence of a substantive
HarbourDesk reasoning failure.

Before remediation, `UpdateTicketArgs.resolution_reason_code` accepted any non-empty string. The M0B
runtime derives its model-facing tool schema directly from that Pydantic contract, so the provider
was not constrained to the canonical terminal reason codes. The deterministic write boundary then
accepted the lowercase value and allowed the ticket to become terminal.

The independent scorer correctly rejected the non-canonical reason code.

## Remediation

The remediation centralizes canonical reason codes as `TicketResolutionReasonCode` in the HarbourDesk
domain contract.

The same enum is used by:

- `Ticket.resolution_reason_code`;
- `UpdateTicketArgs.resolution_reason_code`;
- `HarbourDeskBusinessRules.terminal_reason_codes`.

Because M0B derives tool schemas from `UpdateTicketArgs`, the model-facing `update_ticket` JSON
schema now exposes the canonical reason-code enum automatically.

The write boundary also verifies that a canonical domain reason is enabled by the active business
rules before mutating ticket state.

Lowercase aliases are not normalized. Invalid model output is rejected rather than silently repaired.

Regression tests verify:

- the business-rules catalogue matches the canonical reason enum;
- the provider-facing `update_ticket` schema exposes canonical codes;
- lowercase reason values are rejected without state mutation;
- valid canonical values survive as typed domain state;
- the active ruleset can restrict otherwise valid canonical codes.

## Verification run

New run:

`runs/m1a/m1a-glm51-hdm001-reason-contract-20260915-01/`

Observed receipt:

- M1A integration status: `pass`
- integration gate: `true`
- envelope status: `verified_sufficient`
- sufficient working envelope: 2,703 tokens
- canary stop: `ticket_terminal`
- model attempts: 8
- tool actions: 8
- stage usage complete: `true`
- observed stage tokens: 24,944
- stage token cap: passed
- independent task score: passed
- matched predicate index: `0`
- scoring failures: none

The final `update_ticket` call used:

`ENTITLEMENT_RECONCILED`

The trajectory otherwise retained the same substantive eight-step pattern as the failed canary:
ticket, account, subscription, entitlement, policy search, policy read, entitlement reconciliation,
then terminal ticket update.

This is a clean before/after reliability intervention: the demonstrated boundary defect was removed
and independent scoring changed from fail to pass on the remediation-verification run.

The second run used more observed tokens than the first. This intervention therefore supports a
correctness/control claim only, not an efficiency claim.

## Evaluation custody

Both run directories remain runtime evidence under `runs/` and must not be staged.

The original failed canary remains the before-remediation artifact. The verification canary is an
intervention check and must not be misrepresented as an untouched M1B baseline sample.

## Decision

The terminal reason-code contract defect is closed for M1A.

M1A may proceed to repository closeout and then M1B. M1B should use a frozen single-model
configuration across all 12 diagnostics exactly once, with fresh environment and conversation state
per case and independent scoring for every recoverable final state.

## Non-claims

This remediation does not establish that:

- `glm-5.1` is accurate across HarbourDesk;
- eight model/tool steps are efficient;
- `glm-5.1` is the best available model;
- adaptive routing is beneficial.

Those questions remain for the fixed-model baselines and later routing evaluation.
