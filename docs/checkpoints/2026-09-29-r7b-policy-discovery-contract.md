# HarbourDesk R7B — Runtime-Visible Policy Discovery

**Date:** 2026-09-29
**Status:** PROPOSED — freeze before running the discovery analysis

R7A established:

- failure-only oracle diagnostic reduction: 43.8156%;
- family-label oracle diagnostic reduction: 4.2413%;
- best zero-observed-pass-loss universal cap: 8 calls / 0% reduction;
- qualifying runtime-visible signals:
  - `initial_operation_reference_count`;
  - `first_attempt_realized_tool_count`;
  - `first_attempt_tool_signature`.

R7B therefore searches only a bounded set of five interpretable policy forms built
from those three signals.

## Leakage control

Evaluation is leave-one-template-out across all 18 development templates.

All five instances belonging to a held-out template remain outside the training fold.
This prevents same-template instances from teaching the policy how to handle the
template currently being evaluated.

Benchmark family and template identifiers are evaluation/grouping metadata only.
They are never policy inputs.

Validation and locked cases remain untouched.

## Policy learning

A policy is a deterministic mapping from one or two runtime-visible signal values to
a maximum model-call budget.

The decision is applied only after the first model attempt.

For each training bucket:

- support must be at least 10 cases;
- at least one passing case must exist;
- the learned cap is the maximum attempt count among passing training cases;
- buckets requiring all 8 calls fall back to the normal 8-call budget;
- unseen or unsupported buckets also fall back to 8.

This makes the policy conservative by construction: it cannot reduce a training bucket
below the longest observed successful trajectory in that bucket.

## Qualification

A candidate qualifies only if template-held-out replay shows:

- zero observed pass losses across the 43 frozen development successes; and
- at least 20% diagnostic token reduction across the 89 usage-complete cases.

If multiple candidates qualify, choose:

1. highest cross-validated diagnostic token reduction;
2. fewer signal dimensions;
3. lexicographic policy name.

If none qualifies, R7B returns `NO_POLICY_QUALIFIED`. We do not force an adaptive
candidate.

Any selected policy is still only a development-derived candidate. It must be
implemented and evaluated under later gates before any quality or efficiency claim.
