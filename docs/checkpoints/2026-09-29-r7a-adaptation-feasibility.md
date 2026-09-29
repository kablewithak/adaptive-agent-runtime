# HarbourDesk R7A — Adaptation Feasibility / Oracle Study

**Date:** 2026-09-29
**Status:** PROPOSED — validate and freeze before interpretation

## Question

Before implementing an adaptive runtime, determine whether the frozen 90-case
development evidence contains enough resource-saving headroom to justify adaptation.

R7A does not mutate the runtime and does not call a model.

## Evidence boundary

R7A reads only:

- the frozen R5 GLM-5.2 90-case development summary;
- the corresponding 90 sanitized runtime traces;
- public R4 development case state needed to reconstruct the runtime-visible initial
  observation.

It does not read validation cases, locked cases, or private expected files.

The final pass/fail labels already frozen inside the R5 receipts are used only as
retrospective dependent variables. Benchmark family/template labels may be used only
for diagnostics/oracle bounds and are prohibited as production routing inputs.

## Studies

### Failure-only oracle

Successful trajectories retain their complete observed path. Failed trajectories are
truncated after their first model call.

This is intentionally impossible as a production policy because it uses final outcome
labels. It estimates an upper bound for stop-only adaptation that cannot save the first
model call.

If this upper bound cannot reach the 20% north-star efficiency target, stop-only
adaptation has insufficient development headroom.

### Universal model-call caps

Replay token accounting under caps from 1 through 8 model calls.

For each cap report:

- retained observed successes;
- observed successes that would be cut off before their terminal attempt;
- diagnostic token reduction on the usage-complete subset.

If a universal cap preserves every observed success and reaches at least 20% diagnostic
token reduction, prefer the simpler fixed-budget intervention over adaptation.

### Family-label oracle

For each family, use the maximum attempt count required by any observed successful case
as that family's cap.

This is not production-valid because family is benchmark metadata. It measures whether
coarse case heterogeneity contains useful theoretical headroom.

### Runtime-visible signals

Report pass rates and support for deterministic features available at or immediately
after the first model attempt:

- initial approval count;
- initial prior-operation-reference count;
- initial ticket-note count;
- first-attempt accepted multi-read status;
- first-attempt realized tool count;
- first-attempt tool signature.

A signal is marked diagnostic-interest only when at least two values each have support
of at least 10 cases and their observed pass-rate gap is at least 25 percentage points.

This threshold is a screen, not a statistical significance claim.

## Interpretation

R7A returns one of:

- `NO_STOP_ONLY_HEADROOM` — even the failure-only oracle is below 20%;
- `FIXED_BUDGET_CANDIDATE` — a universal cap preserves all observed successes while
  reaching at least 20% diagnostic token reduction;
- `ADAPTATION_WORTH_INVESTIGATING` — oracle headroom is at least 20% but no universal
  zero-observed-pass-loss cap reaches the target.

All token reductions are diagnostic only because the frozen R5 reference contains one
usage-incomplete provider-error case.

No final efficiency claim can be made from R7A.
