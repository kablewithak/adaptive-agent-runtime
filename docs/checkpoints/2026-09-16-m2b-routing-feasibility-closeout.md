# HarbourDesk M2B Routing Feasibility Closeout

**Date:** 2026-09-16
**Phase:** M2B / M2B-S1 / M2B-S2
**Status:** COMPLETE
**Routing v1 decision:** STOP
**M2C implementation:** NOT JUSTIFIED
**Next intervention:** MODEL_RUNTIME_COMPATIBILITY
**Live provider traffic introduced by this phase:** NONE

## Executive decision

Do not implement M2C under the current M2A routing feature boundary.

The routing investigation produced a clean three-stage evidence chain:

1. M2B showed that a perfect per-case oracle could satisfy the frozen routing gates.
2. M2B-S1 showed that the oracle advantage cannot be recovered with any tested
   single domain-readable structural predicate.
3. M2B-S2 exhaustively evaluated every deterministic mapping over the complete
   frozen M2A structural signatures and proved that the feature boundary itself
   cannot satisfy the frozen routing gates.

The correct engineering action is therefore to stop adding routing-rule complexity.

## Frozen acceptance gates

Quality:

`verified_passes >= 6 of 12`

Efficiency:

`observed inference tokens / verified success <= 25,257.733334`

Reference comparator:

- model: GLM-5.1;
- verified successes: 6/12;
- observed inference tokens: 189,433;
- observed tokens per verified success: 31,572.166667.

The 12-case suite remains a diagnostic development suite. These gates do not claim
production statistical non-inferiority.

## M2B — perfect oracle feasibility

Canonical run:

`m2b-glm51-glm52-oracle-20260916-01`

Canonical summary SHA256:

`155DEA27B087BB55A3445FB7162E375FC44C84A3671344AC154C2AF094DB0DB8`

Observed result:

- candidate assignments evaluated: 4,096;
- maximum verified successes: 6/12;
- reference-only passes: 4;
- alternative-only passes: 0;
- both models pass: 2;
- neither model passes: 6;
- oracle inference tokens: 148,300;
- oracle tokens per verified success: 24,716.666667;
- oracle gate: PASS.

The oracle therefore demonstrated theoretical headroom.

However, GLM-5.2 added zero unique successes. The oracle achieved savings primarily by
routing some cases that fail under both candidates to the cheaper GLM-5.2 trajectory.

This is failure-cost containment, not complementary model capability.

## M2B-S1 — simple structural-rule audit

Canonical run:

`m2b-s1-structural-audit-20260916-01`

Observed result:

- cases: 12;
- distinct M2A structural signatures: 6;
- signatures containing conflicting oracle choices: 3;
- exact structural separability: FALSE;
- single predicates evaluated: 28;
- passing predicates: 0;
- decision: `NO_SINGLE_PREDICATE_PASS`.

This result established that no tested single, domain-readable structural predicate
could recover the oracle's quality and efficiency simultaneously.

More importantly, identical complete M2A structural observations sometimes required
different oracle model choices.

That justified the stronger feature-ceiling audit rather than escalating to arbitrary
two-feature or three-feature rule search.

## M2B-S2 — complete M2A feature-ceiling audit

Canonical run:

`m2b-s2-feature-ceiling-20260916-01`

Canonical summary SHA256:

`169A82654368E81D47A2F54A772039A603301B01F2FBB8D8DF423B3E5EAF365B`

Observed result:

- cases: 12;
- complete structural signature groups: 6;
- deterministic signature mappings evaluated: 64;
- maximum verified successes: 6/12;
- feature ceiling feasible: FALSE;
- minimum inference tokens at the quality floor: 171,174;
- minimum tokens per verified success at the quality floor: 28,529;
- minimum-quality-floor gate: FAIL.

Because every deterministic router restricted to the M2A observation is equivalent to
one of these 64 signature mappings, this is a feature-boundary result rather than a
failure of a particular rule-search algorithm.

## Quantified gap

At six verified successes, the frozen efficiency target allows approximately:

`151,546.400004 total inference tokens`

The best M2A-feature-constrained quality-preserving assignment required:

`171,174 total inference tokens`

Gap:

`19,627.599996 additional inference tokens`

Per verified success:

- allowed: 25,257.733334;
- feature ceiling: 28,529;
- gap: 3,271.266666.

Relative to the GLM-5.1 reference, the feature-ceiling assignment reduces inference
tokens from 189,433 to 171,174, approximately a 9.64% reduction.

The frozen routing target requires at least a 20% reduction.

## Supported conclusion

Supported:

> No deterministic router restricted to the complete M2A structural observation can
> satisfy the frozen HarbourDesk routing acceptance criteria on this 12-case
> development suite.

Also supported:

> Increasing routing-rule complexity while preserving the same feature boundary
> cannot solve the measured problem.

Not supported:

- that routing can never work with a different legitimate feature boundary;
- that semantic routing cannot work;
- that GLM-5.2 is universally worse than GLM-5.1;
- that the current 12 cases establish production reliability;
- that a learned router would generalize;
- that the perfect-oracle result represents deployable routing capability.

## Why M2C is not justified

Implementing M2C now would create code for a policy class that the exhaustive
feature-ceiling audit already proved cannot meet the frozen target.

Possible attempts to continue anyway would include:

- increasingly specific structural rules;
- decision trees over the same M2A fields;
- per-signature lookup behavior;
- hand-selected combinations of the 28 tested predicates.

Those approaches do not add information. They only re-express mappings that M2B-S2
has already exhausted.

The maintainable decision is therefore to stop.

## Architecture finding

The deeper bottleneck is candidate-model/runtime compatibility.

Fixed baselines showed:

### GLM-5.2

- 2/12 verified successes;
- 8 `multi_tool_call` stops;
- zero unique successes over GLM-5.1 on the diagnostic suite.

### DeepSeek V4 Flash

- 0/12 verified successes;
- 12/12 `multi_tool_call` stops;
- zero tool actions executed.

This means the current cheap candidates do not yet provide sufficiently useful
complementary capability under the one-tool-call-per-turn runtime boundary.

The routing experiment was therefore forced toward predicting where cheaper failure
was acceptable rather than choosing between two independently useful capabilities.

## Next intervention

Open a separate model/runtime compatibility phase.

Primary target:

`multi_tool_call`

The next intervention should preserve the fixed-model evidence and change exactly one
system boundary at a time.

Recommended sequence:

1. define a trajectory-regulation / tool-call-realization contract;
2. preserve current one-tool-per-turn fixed baselines as the baseline condition;
3. implement the smallest deterministic intervention that can safely realize or
   regulate multi-tool model output without weakening write controls;
4. re-run GLM-5.2 on the same diagnostic cases as an intervention measurement;
5. independently score quality, tool behavior, usage, and new failure modes;
6. compare before vs after;
7. only reopen routing if a cheaper candidate gains genuine verified capability or
   materially better verified outcomes per token.

DeepSeek V4 Pro provider-rate regulation remains a separate intervention seam and
must not be mixed into the multi-tool experiment.

## Regression / evidence requirements for branch closeout

Before merge:

- full pytest passes;
- full Ruff passes;
- full mypy passes;
- `git diff --check` passes;
- only intended M2B / S1 / S2 source, scripts, tests, and checkpoint files are staged;
- `runs/` is not staged;
- `evaluation_private/` is not staged;
- canonical evidence remains locally hash-verifiable.

## Final phase receipt

`ROUTING_V1_DECISION=STOP`

`M2C_IMPLEMENTATION=NOT_JUSTIFIED`

`NEXT_INTERVENTION=MODEL_RUNTIME_COMPATIBILITY`

This is a successful negative result: the project rejected an unsupported routing
architecture before converting it into production code and technical debt.
