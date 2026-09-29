# HarbourDesk R4 — Benchmark and Final Acceptance Contract

**Date:** 2026-09-28  
**Stage:** R4  
**Status:** PROPOSED — validate locally before merge  
**Live traffic:** NONE  
**Runtime behavior change:** NONE

## Purpose

R4 freezes the benchmark structure and final north-star decision rule before broader model evaluation or candidate selection. The current `hdm-001` through `hdm-012` suite remains development/diagnostic evidence and is not promoted into the independent final claim.

## Prior diagnostic evidence closed before R4

M3D frozen implementation commit:

`03bc19fac76206057a4bba505eaf1edd843b2e4b`

Canonical M3D run:

`m3d-glm52-completion-envelope-20260928-01`

Observed: PASS, 8/12 verified successes, 12/12 ticket-terminal trajectories, all three target truncation cases (`hdm-003`, `hdm-008`, `hdm-012`) became terminal verified successes, M3C passes were preserved, and usage was complete.

Canonical M3D SHA256:

- manifest: `2BA158B90991A0100B5E2DC4BEB96DF46023F1F84A40E87AEDD0653E93B199B3`
- summary: `402A257C43D0323E7F050826E58BBCD0AD349367C020E40D4A523C92CADE81AF`
- decision: `61B9DCF502D26169B1D0A4192DCA0EC8665E05891C393A78A0AD9BC74E124729`

M3D remains diagnostic evidence, not final generalization evidence.

## Benchmark shape

The final benchmark contains 36 substantive templates with five instances per template:

- 18 development templates / 90 cases;
- 6 validation templates / 30 cases;
- 12 locked templates / 60 cases;
- 180 cases total.

For each of the six HarbourDesk failure families, three templates are development, one is validation, and two are locked. All five instances derived from a template remain in the same partition.

Public runtime-facing case IDs use opaque `hdb-NNN` identities. Family, partition, difficulty, authoring rationale, and expected outcomes remain evaluator-side and must not be exposed to the model.

The six existing families remain the benchmark backbone: F1 access mismatch, F2 ambiguous request, F3 stale/superseded policy, F4 multi-record contradiction, F5 authorisation boundary, and F6 interrupted workflow. Cosmetic paraphrases do not count as independent templates.

## Final paired comparison

The selected fixed reference and frozen candidate run the same 60 locked cases under the same scorer, expected-outcome version, runtime contracts, and accounting rules. These are frozen before locked outcomes are opened. No unscheduled locked reruns are part of the comparison.

## Quality gate

The original project north star specified non-inferiority within five percentage points. R4 preserves that target.

Quality is verified successes over the same 60 locked cases. The observed candidate-minus-reference difference must not be below `-5.0` percentage points.

Because those 60 instances represent only 12 independent task templates, uncertainty is evaluated at the template level with a paired bootstrap:

- statistic: mean candidate-minus-reference template success-rate difference;
- resampling unit: locked template;
- confidence: one-sided 95% lower bound;
- resamples: 10,000;
- seed: 20260928.

Decision:

- observed difference below -5 points -> FAIL;
- observed difference within margin but lower confidence bound below -5 -> INCONCLUSIVE;
- observed difference and lower bound both at or above -5 -> PASS.

## Family-regression veto

Each family has ten locked cases. A candidate may not regress any family by more than ten observed percentage points relative to the fixed reference. A larger drop is a FAIL even if the aggregate quality gate passes.

## Efficiency gate

The original north star required at least 20% efficiency improvement. R4 retains that target but freezes the final denominator as total inference tokens across the same 60 locked cases.

The candidate must use at least 20% fewer total observed inference tokens than the fixed reference. Tokens per verified success is reported but is not the final efficiency gate. If required usage is incomplete, efficiency is INCONCLUSIVE rather than estimated.

## Safety and fault gate

Any critical deterministic-safety violation in the candidate is a final FAIL.

The separate fault programme contains 24 cases. All 24 must execute with complete evidence and zero invariant failures for the safety gate to pass. Incomplete fault evidence is INCONCLUSIVE. A safety-invalid fixed reference makes the comparison INCONCLUSIVE rather than certifying the candidate against an invalid comparator.

## Provider failures and evidence

Provider failures remain reportable operational outcomes and are not silently removed from task-quality accounting. Missing usage or incomplete evidence can make the final verdict INCONCLUSIVE. No hidden retry or post-hoc case replacement is authorized.

## Final verdict

The result is exactly one of:

- PASS — quality, family regression, efficiency, safety, and evidence gates all pass;
- FAIL — any valid required gate fails;
- INCONCLUSIVE — no required gate fails, but uncertainty or missing required evidence prevents the claim.

The locked set must not be used to choose a new intervention after results are opened. A new claim after locked-result-driven changes requires new independent evidence.

## Immediate next step after validation

Author the 36 substantive template specifications first, preserving the 3/1/2 development/validation/locked allocation within each family. Only after template review should the five instances per template be materialized into the 180 public fixtures and private evaluator expectations.
