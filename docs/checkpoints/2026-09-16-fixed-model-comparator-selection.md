# HarbourDesk Fixed-Model Comparator Selection

**Date:** 2026-09-16
**Status:** COMPLETE — routing reference frozen
**Scope:** M1B through M1E fixed-model evidence

## Decision

Use **GLM-5.1** as the reference fixed-model comparator for the upcoming adaptive
routing experiment.

This is a selection among the fixed baselines that produced valid comparable
model-quality evidence.

It is not a universal model ranking and does not imply that GLM-5.1 is superior to
DeepSeek V4 Pro, whose M1E quality result was inconclusive because of provider rate
limiting.

## Valid fixed-model evidence

| Model | Valid quality result | Pass rate | Inference tokens | Tokens / verified success |
| --- | ---: | ---: | ---: | ---: |
| GLM-5.1 | 6/12 | 50.0% | 189,433 | 31,572.166667 |
| GLM-5.2 | 2/12 | 16.7% | 104,741 | 52,370.5 |
| DeepSeek V4 Flash | 0/12 | 0.0% | 27,052 | Undefined |
| DeepSeek V4 Pro | Inconclusive | Inconclusive | Incomplete | Inconclusive |

## GLM-5.1 reference

Canonical GLM-5.1 comparator:

- verified successes: 6/12;
- pass rate: 50.0%;
- observed inference tokens: 189,433;
- observed tokens per verified success: 31,572.166667;
- usage accounting: complete.

Among the models with valid comparable fixed-model evidence, GLM-5.1 produced the
highest independently verified pass count and pass rate.

## DeepSeek V4 Pro exclusion

M1E-01 is excluded from model-quality comparison because the run was contaminated by
HTTP 429 `rate_limited` provider errors and incomplete usage accounting.

A later isolated health probe returned HTTP 200 with observed usage, showing that the
endpoint recovered.

The correct M1E quality status is `INCONCLUSIVE`.

## Routing hypothesis

The adaptive-routing intervention must be evaluated against the frozen GLM-5.1
reference.

### Quality gate

The routing system must be non-inferior within 5 percentage points of the GLM-5.1
reference pass rate.

Reference:

- GLM-5.1 pass rate: 50.0%.

Because one case in a 12-case suite changes the observed pass rate by approximately
8.33 percentage points, the routing evaluation must report both exact pass count and
observed pass rate and must not overstate statistical precision.

### Efficiency gate

The routing system must achieve at least 20% fewer observed inference tokens per
verified successful outcome than the GLM-5.1 reference, provided usage accounting is
complete.

Reference:

- GLM-5.1 tokens per verified success: 31,572.166667.

A 20% reduction corresponds to a target of at most:

`25,257.733334` observed inference tokens per verified successful outcome.

If usage accounting is incomplete, the efficiency decision is `INCONCLUSIVE`.

## Decision states

The routing experiment must end in exactly one of:

- `PASS`
- `FAIL`
- `INCONCLUSIVE`

A routing result may be `PASS` only when both quality and efficiency gates are
satisfied with complete required evidence.

## Non-claims

This comparator selection does not establish:

- production reliability from a 12-case diagnostic suite;
- a universal ranking of the models;
- that GLM-5.1 would outperform DeepSeek V4 Pro under a valid Pro run;
- causal superiority from a single stochastic run per model;
- statistical non-inferiority at production confidence levels.

## Architecture implication

The fixed-model phase exposed two independent system-level concerns that may become
future explicit interventions:

1. tool-call realization / trajectory regulation for models that emit multiple tool
   calls in one turn;
2. provider rate regulation for models subject to dynamic or undocumented service
   limits.

Neither concern should be silently folded into the routing baseline.

The routing experiment should start from the frozen corrected runtime and measure any
new control explicitly.
