# HarbourDesk M2A — Routing Experiment Contract

**Date:** 2026-09-16
**Stage:** M2A
**Status:** PROPOSED — validate locally before merge
**Live traffic:** NONE
**Runtime behavior change:** NONE

## Purpose

M2A freezes the experimental boundary for the first adaptive-routing intervention
before any router behavior is implemented.

The goal is to test whether a small inspectable deterministic routing policy can
preserve the independently verified HarbourDesk quality of the accepted GLM-5.1
reference while materially reducing inference usage.

M2A does not implement a router and does not send provider traffic.

## Reference comparator

The fixed-model phase selected GLM-5.1 as the reference among models with valid
comparable evidence:

- profile: `primary-openai`;
- model: `glm-5.1`;
- verified successes: 6/12;
- observed pass rate: 50.0%;
- observed inference tokens: 189,433;
- observed tokens per verified success: 31,572.166667;
- usage accounting: complete.

DeepSeek V4 Pro remains excluded from quality comparison because M1E was
inconclusive after provider rate limiting.

## M2A routing candidates

M2A freezes exactly two candidates for the first routing experiment:

1. reference: `primary-openai` / `glm-5.1`;
2. alternative: `glm-5-2-openai` / `glm-5.2`.

DeepSeek V4 Flash is excluded because its valid fixed baseline produced 0/12 verified
successes.

DeepSeek V4 Pro is excluded because its quality baseline is inconclusive and its usage
evidence is incomplete.

Qwen is excluded because it is not protocol-qualified.

The candidate set must not expand during M2B, M2C, or the first live routed run.

## One model per trajectory

The routing decision is made exactly once before the first model request for a case.
The selected model remains fixed for the entire trajectory.

M2A prohibits mid-trajectory model switching, model escalation after a weak answer,
cross-model retry after provider error or invalid tool behavior, and hidden fallback
after token or action budget exhaustion.

This isolates the effect of the routing decision from dynamic orchestration.

## Allowed routing information

Router v1 receives a deliberately smaller projection of the existing
`ModelVisibleInitialObservation`.

Allowed features are only:

- ticket status;
- ticket note count;
- approval count;
- set of active approval action types;
- set of inactive approval action types;
- prior-operation reference count;
- set of prior-operation action types.

Active approval state is computed deterministically against the frozen observation
clock.

## Prohibited routing information

Router v1 must not receive or derive decisions from benchmark case ID, run ID, tenant
ID, ticket ID, account ID, approval ID, operation ID, requesting-contact identity,
raw ticket text, raw ticket notes, evaluator expected outcomes, evaluator labels,
scorer outputs, per-case fixed-model outcomes or token usage, fixed-model traces,
hidden final state, model output, provider response metadata, or post-dispatch tool
results.

The explicit exclusion of raw ticket text is conservative. It reduces semantic
routing power but prevents a small known 12-case suite from being memorized through
case-specific wording after baseline outcomes have already been observed.

If semantic routing is later justified, it must be introduced as a separately
versioned intervention with new before/after evidence.

## Routing decision schema

Every routing decision must be machine-readable and contain schema version, selected
profile, selected model, reason code, and deterministic rule ID.

Allowed reason codes are:

- `REFERENCE_DEFAULT`
- `STRUCTURAL_RULE_MATCH`
- `SAFETY_FALLBACK`

`REFERENCE_DEFAULT` and `SAFETY_FALLBACK` may select only GLM-5.1.

A decision selecting any model/profile pair outside the frozen candidate set is
invalid before provider dispatch.

## Safety fallback

M2A permits only a pre-dispatch deterministic safety fallback. If a future router
cannot produce a valid routing decision from the allowed routing observation, it may
select GLM-5.1 with reason code `SAFETY_FALLBACK`.

After provider dispatch, no fallback or model switch is permitted in the first routed
experiment.

## Provider errors and tool behavior

Provider errors remain visible runtime outcomes. The routed experiment must not
automatically reroute after rate limiting, timeout, provider unavailability, protocol
error, authentication failure, or entitlement failure.

The existing runtime contract also remains frozen: one tool call per model turn,
multiple tool calls stop with `multi_tool_call`, malformed calls execute nothing,
model text alone cannot close an open ticket, and existing model-call, tool-action,
and deterministic write controls remain unchanged.

## Token accounting

The v1 router is deterministic and contributes zero model-inference tokens.

For the routed experiment, sum observed input plus completion tokens from the selected
model trajectory. Do not estimate missing provider usage or impute zero for failed
requests with unknown usage.

Compute tokens per verified successful outcome only when usage is complete and at
least one case passes.

Any future learned or LLM-based router must include its own inference usage.

## Quality gate

The original north star specified non-inferiority within 5 percentage points of the
GLM-5.1 50.0% observed pass rate.

A 12-case suite cannot resolve a 5-percentage-point margin because one case changes
the observed pass rate by approximately 8.33 percentage points.

M2A therefore freezes the operational diagnostic quality gate as:

`verified_passes >= 6 of 12`

The evaluation must still report exact pass count and observed pass rate. Five passes
are not accepted as "within 5 percentage points"; 5/12 is 41.67%, an 8.33-point drop
from the reference.

This is a diagnostic gate, not a claim of statistical non-inferiority at production
confidence levels.

## Efficiency gate

Reference:

`31,572.166667 observed inference tokens / verified success`

Required improvement: `>= 20%`

Frozen target:

`<= 25,257.733334 observed inference tokens / verified success`

The efficiency gate is evaluated only when provider usage evidence is complete.

## Final decision

The routed experiment ends in exactly one of `PASS`, `FAIL`, or `INCONCLUSIVE`.

- `PASS`: quality passes and efficiency passes.
- `FAIL`: quality fails or efficiency fails.
- `INCONCLUSIVE`: no gate has failed, but required evidence is incomplete.

Examples:

- 5/12 with incomplete usage -> `FAIL` because quality already failed;
- 6/12 with incomplete usage -> `INCONCLUSIVE`;
- 6/12 above the token target -> `FAIL`;
- 6/12 or better at or below the token target with complete usage -> `PASS`.

## M2B oracle-analysis boundary

M2B is an offline feasibility analysis only. It may read immutable M1B and M1C
fixed-model evidence to answer:

> If model choice were known perfectly per case, is there enough complementary
> GLM-5.1 / GLM-5.2 behavior to preserve at least 6 verified successes while reaching
> the 20% token-efficiency target?

Oracle outputs must not become runtime routing inputs. Oracle case labels must not be
imported by routing code. `runs/` and `evaluation_private/` remain unavailable to the
live router. M2C rules must use only the M2A routing observation schema.

If the oracle cannot meet both gates, the routing hypothesis has insufficient
headroom under the current candidate set and M2C should not be built.

## M2C boundary if M2B passes

The first live router must be deterministic, inspectable, rule-based, one-decision per
case before inference, limited to the M2A routing observation, limited to the two
frozen candidates, and fully traced with reason code and rule ID.

No LLM router, classifier model, embedding model, retrieval step, or learned policy is
part of router v1.

## Regression requirements

Before M2A merges:

- prohibited identity/text fields do not appear in serialized routing observations;
- non-candidate model selection is rejected;
- safety fallback can select only GLM-5.1;
- 5/12 fails the quality gate;
- 6/12 passes the quality gate;
- the frozen 20% efficiency threshold is enforced;
- incomplete usage produces an inconclusive efficiency gate;
- full pytest, Ruff, mypy, and `git diff --check` pass.

## Non-claims

M2A does not establish that routing is feasible, that GLM-5.2 complements GLM-5.1
enough to create savings, that structural routing features are sufficient, or any
live routing improvement. Those questions begin with M2B.
