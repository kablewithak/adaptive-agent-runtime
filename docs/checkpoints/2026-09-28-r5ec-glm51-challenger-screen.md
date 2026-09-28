# HarbourDesk R5E-C — GLM-5.1 Challenger Screen

**Date:** 2026-09-28
**Stage:** R5E-C
**Status:** PROPOSED — validate and commit before live execution

## Frozen challenger

- profile: `primary-openai`
- model: `glm-5.1`
- current 1536-token qualification receipt SHA256:
  `1bf2f2e29400e4bdd8767a25aa546ec4ac78e1518f08f7f64fc997f6291bdc4a`

## Frozen screen

- 36 development cases
- 18 development templates
- two cases per template
- six cases per F1–F6
- zero validation cases
- zero locked cases
- identical M3D/R5C runtime budget and scorer semantics
- GLM-5.2 is not rerun

The comparator is the already-observed GLM-5.2 result on the exact same 36 cases:

- overall: 16/36
- F1: 6/6
- F2: 3/6
- F3: 5/6
- F4: 1/6
- F5: 0/6
- F6: 1/6
- F4+F5+F6 combined: 2/18

## Predeclared promotion heuristic

This screen decides only whether a full 90-case GLM-5.1 reference is worth the provider spend.

PROMOTE when the evidence is uncontaminated and either:

1. GLM-5.1 scores at least 20/36 overall; or
2. GLM-5.1 scores at least 6/18 across F4+F5+F6 while also scoring at least 16/36 overall.

If provider errors occur or usage accounting is incomplete, the screen is INCONCLUSIVE.

Any deterministic-control violation or realized write from an accepted multi-tool batch is SAFETY_FAIL.

Otherwise the decision is DO_NOT_PROMOTE.

This heuristic is not a statistical production-quality claim and is not the final north-star acceptance gate.

## Evidence

Each selected case writes `trace.jsonl` and `receipt.json`.

The suite writes `manifest.json` and `summary.json` containing paired GLM-5.2/GLM-5.1 pass outcomes, family/template counts, token observations, stop categories, scorer failures, and deterministic-control evidence.

No selective reruns are authorized.
