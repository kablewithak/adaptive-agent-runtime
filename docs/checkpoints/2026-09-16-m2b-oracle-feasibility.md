# HarbourDesk M2B — Offline Routing Oracle Feasibility

**Date:** 2026-09-16
**Stage:** M2B
**Status:** COMPLETE
**Live provider traffic:** NONE

## Purpose

M2B asked whether the frozen GLM-5.1 / GLM-5.2 candidate set contains enough
counterfactual routing headroom to justify building a real router.

The analysis exhaustively evaluated all 4,096 possible per-case assignments across
the 12 HarbourDesk diagnostic cases.

This was an oracle analysis only. Per-case fixed-model outcomes are not permitted
runtime routing inputs.

## Canonical evidence

M2B run ID:

`m2b-glm51-glm52-oracle-20260916-01`

Evidence directory:

`runs/m2b/m2b-glm51-glm52-oracle-20260916-01`

Summary SHA256:

`155DEA27B087BB55A3445FB7162E375FC44C84A3671344AC154C2AF094DB0DB8`

Exactly one M2B run directory was present after execution. An accidental second
invocation did not create a second canonical evidence directory.

## Oracle result

- assignments evaluated: 4,096;
- maximum verified successes: 6/12;
- oracle feasible: TRUE;
- best inference tokens: 148,300;
- best tokens per verified success: 24,716.666667;
- frozen efficiency target: 25,257.733334;
- overall oracle gate: PASS.

## Complementarity

Observed success overlap:

- GLM-5.1-only passes: 4;
- GLM-5.2-only passes: 0;
- both models pass: 2;
- neither model passes: 6.

GLM-5.2 therefore adds no unique verified successes on the current diagnostic suite.

The oracle preserves all six GLM-5.1 successes and obtains savings by assigning some
already-failing cases to the cheaper GLM-5.2 trajectories.

## Best oracle assignment

| Case | Selected model | Verified pass | Inference tokens |
| --- | --- | --- | ---: |
| hdm-001 | GLM-5.1 | TRUE | 20,520 |
| hdm-002 | GLM-5.1 | TRUE | 18,571 |
| hdm-003 | GLM-5.1 | TRUE | 15,125 |
| hdm-004 | GLM-5.1 | TRUE | 12,168 |
| hdm-005 | GLM-5.1 | TRUE | 18,290 |
| hdm-006 | GLM-5.1 | TRUE | 19,177 |
| hdm-007 | GLM-5.2 | FALSE | 2,049 |
| hdm-008 | GLM-5.2 | FALSE | 6,097 |
| hdm-009 | GLM-5.1 | FALSE | 15,217 |
| hdm-010 | GLM-5.2 | FALSE | 6,462 |
| hdm-011 | GLM-5.2 | FALSE | 2,124 |
| hdm-012 | GLM-5.1 | FALSE | 12,500 |

## Headroom

GLM-5.1 reference:

- 189,433 inference tokens;
- 31,572.166667 tokens per verified success.

M2B oracle:

- 148,300 inference tokens;
- 24,716.666667 tokens per verified success.

Observed token reduction:

- 41,133 total inference tokens;
- approximately 21.71% reduction.

At six verified successes, the frozen 20% efficiency threshold permits approximately
151,546.400004 total inference tokens.

The oracle is therefore only approximately 3,246.4 tokens below the total threshold,
or approximately 541.07 tokens per verified success below the acceptance ceiling.

The theoretical routing opportunity exists but has little efficiency headroom.

## Interpretation

M2B demonstrates counterfactual feasibility, not routing capability.

The opportunity on this suite is primarily failure-cost containment:

> preserve GLM-5.1 on cases it can solve and spend fewer tokens on some cases that
> fail under either candidate.

It is not evidence that GLM-5.2 contributes complementary task-solving capability.

## Leakage boundary

The 12 fixed-model outcomes have now been inspected during development.

Any routing rule derived from these same cases is development-set logic and cannot by
itself establish independent routing improvement.

A fresh holdout is required before making a supported claim that routing improves the
system.

## Next gate

Before implementing M2C, run M2B-S1 structural-separability analysis.

M2B-S1 must use only the routing features allowed by M2A and answer:

1. do identical allowed structural observations ever require conflicting oracle
   assignments?
2. can any single domain-readable structural predicate meet both frozen routing
   gates?

If no simple structural predicate passes, do not implement the first live router from
this development set.
