# HarbourDesk R4D — Benchmark Quality Gate

**Date:** 2026-09-28
**Stage:** R4D
**Status:** PROPOSED — validate locally before broader live evaluation
**Live provider traffic:** NONE

## Purpose

R4D tests whether the new 120-case development/validation population is worth using as experimental evidence before spending provider tokens.

R4C already established that all 120 fixtures execute deterministically and pass the independent scorer. R4D adds two different checks:

1. benchmark coverage and within-template structural variation;
2. scorer sensitivity to plausible wrong terminal states across the actual new population.

## Coverage gate

The public benchmark must contain:

- 90 development cases;
- 30 validation cases;
- 24 exposed substantive template mechanisms;
- 20 materialized cases per HarbourDesk failure family;
- 15 development and 5 validation cases per family;
- five instances per exposed template;
- no materialized locked payload directory.

The structural fingerprint deliberately ignores names, raw IDs, display text and ticket prose. It uses state structure such as plan/status/revisions, entitlement provenance, approval timing, prior-operation state, requester authorization relation and policy validity windows.

All five instances of every exposed template must have distinct structural fingerprints. This does not make the five instances statistically independent; the template remains the analysis unit.

## Scorer negative controls

After replaying each canonical deterministic trajectory, R4D mutates the final state and requires the independent scorer to reject it.

The planned population produces 520 negative controls:

- 120 wrong dispositions;
- 120 wrong terminal reason codes;
- 90 missing required policy references;
- 20 missing required prior-operation references;
- 40 wrong entitlement states;
- 10 wrong subscription states;
- 120 wrong effective-write counts.

Every mutated state must fail scoring with the expected failure code.

This tests the evaluator against the benchmark population rather than relying only on the original small synthetic scorer unit fixture.

## Acceptance

R4D passes only when:

- public coverage analysis passes;
- 120 canonical rehearsals still pass;
- all 520 negative controls are rejected as expected;
- there are zero replay failures;
- there are zero negative-control failures;
- Ruff, targeted tests, mypy and `git diff --check` pass.

## Claim boundary

A PASS establishes that the development/validation population is structurally balanced under the frozen R4 design and that the independent scorer is sensitive to the declared wrong-state perturbations.

It does not establish model competence, model generalization, final holdout performance, production readiness or the north-star result.

## Next gate

After R4D passes, R5 may begin: establish broader fixed-model references on the 90 development cases under one comparable runtime/configuration, preserving the 30 validation cases for bounded later selection and keeping the 60 locked cases sealed.
