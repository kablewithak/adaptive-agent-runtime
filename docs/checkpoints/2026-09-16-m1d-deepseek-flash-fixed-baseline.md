# HarbourDesk M1D — DeepSeek V4 Flash Fixed-Model Baseline

**Date:** 2026-09-16
**Stage:** M1D
**Status:** COMPLETE — canonical DeepSeek V4 Flash fixed-model comparator
**Model:** `deepseek-v4-flash`
**Profile:** `deepseek-flash-openai`
**Run ID:** `m1d-deepseek-flash-baseline-20260916-01`

## Purpose

M1D establishes the third directly comparable fixed-model HarbourDesk baseline.

It uses the same corrected environment, 12 diagnostic cases, independent evaluator,
runtime semantics, budgets, trace format, and usage accounting as the accepted GLM
baselines.

M1D is not a routing experiment and contains no model-specific case tuning.

## Frozen comparison contract

The run preserved the same fixed-model execution contract:

- cases `hdm-001` through `hdm-012`, exactly once, fixed order;
- fresh in-memory HarbourDesk store per case;
- fresh model conversation per case;
- model-selected actions only;
- no evaluator labels exposed to the model;
- no case-specific tuning;
- no selective reruns;
- no automatic provider retries;
- max model calls: 8;
- max tool actions: 10;
- trajectory deadline: 300 seconds;
- request deadline: 60 seconds;
- max completion tokens: 768;
- independent post-run scoring;
- explicit missing-usage handling;
- sanitized durable traces;
- immutable evidence directory.

## Canonical result

The M1D suite completed all 12 cases.

| Metric | Result |
| --- | ---: |
| Cases completed | 12/12 |
| Independent passes | 0 |
| Pass rate | 0.0% |
| Usage complete | TRUE |
| Observed input tokens | 24,591 |
| Observed completion tokens | 2,461 |
| Observed inference tokens | 27,052 |
| Tokens per verified success | UNDEFINED |

Stop categories:

- `multi_tool_call`: 12

Scoring failure counts:

- `disposition_mismatch`: 12
- `reason_code_mismatch`: 12
- `required_policy_reference_missing`: 9
- `effective_write_count_mismatch`: 4
- `entitlement_mismatch`: 3
- `required_operation_reference_missing`: 2
- `subscription_mismatch`: 1

## Case results

| Case | Result | Stop category | Attempts | Actions | Tokens |
| --- | --- | --- | ---: | ---: | ---: |
| hdm-001 | FAIL | multi_tool_call | 1 | 0 | 2,208 |
| hdm-002 | FAIL | multi_tool_call | 1 | 0 | 2,176 |
| hdm-003 | FAIL | multi_tool_call | 1 | 0 | 2,191 |
| hdm-004 | FAIL | multi_tool_call | 1 | 0 | 2,287 |
| hdm-005 | FAIL | multi_tool_call | 1 | 0 | 2,232 |
| hdm-006 | FAIL | multi_tool_call | 1 | 0 | 2,358 |
| hdm-007 | FAIL | multi_tool_call | 1 | 0 | 2,228 |
| hdm-008 | FAIL | multi_tool_call | 1 | 0 | 2,167 |
| hdm-009 | FAIL | multi_tool_call | 1 | 0 | 2,258 |
| hdm-010 | FAIL | multi_tool_call | 1 | 0 | 2,263 |
| hdm-011 | FAIL | multi_tool_call | 1 | 0 | 2,325 |
| hdm-012 | FAIL | multi_tool_call | 1 | 0 | 2,359 |

## Dominant failure mode

All twelve trajectories stopped with `multi_tool_call` on the first model turn.

The HarbourDesk runtime intentionally permits one tool call per model turn. When a
model emits multiple tool calls in one turn, none are executed and the trajectory
stops with `multi_tool_call`.

The observed pattern was therefore:

- 12/12 `multi_tool_call`;
- 12/12 one model attempt;
- 12/12 zero executed tool actions.

This is model/runtime compatibility evidence under the frozen contract.

M1D does not change the runtime, prompt, retry policy, action budget, or provider
behavior after observing this result.

## Provider continuation behavior

DeepSeek V4 Flash was previously protocol-qualified after Huawei
`reasoning_content` was preserved as ephemeral continuation state during tool
round-trips.

M1D relied on that already-qualified provider path.

Because all twelve M1D trajectories stopped before any tool action was executed, the
live baseline did not exercise a tool-result continuation round-trip.

The baseline therefore supports the observed multi-tool-call result, but it does not
add new live evidence about continuation-state handling beyond the earlier protocol
qualification.

## Comparison with existing fixed baselines

| Metric | GLM-5.1 | GLM-5.2 | DeepSeek V4 Flash |
| --- | ---: | ---: | ---: |
| Verified passes | 6/12 | 2/12 | 0/12 |
| Pass rate | 50.0% | 16.7% | 0.0% |
| Observed inference tokens | 189,433 | 104,741 | 27,052 |
| Tokens per verified success | 31,572.166667 | 52,370.5 | Undefined |
| `multi_tool_call` stops | 0 | 8 | 12 |
| Usage complete | TRUE | TRUE | TRUE |

The 27,052-token total is not an efficiency win. DeepSeek V4 Flash produced no
verified successes, so tokens per verified success are undefined.

Its low total token usage is explained by all twelve trajectories terminating after
the first model attempt.

## Evidence custody

Evidence directory:

`runs/m1d/m1d-deepseek-flash-baseline-20260916-01`

Manifest SHA256:

`154F9252E42D73DA1E3E6740599D81C0ECC5CD4BD310EF34054A82D20A3437DA`

Summary SHA256:

`EA50160B3EA1CFE873298D881F598EFD20D8741D38F7403E344BE8B0F299B897`

The evidence directory remains ignored and must not be staged.

## Supported claims

M1D supports the following claims:

- the frozen DeepSeek V4 Flash HarbourDesk suite completed 12/12 cases;
- DeepSeek V4 Flash achieved 0/12 independently verified successes;
- observed pass rate was 0.0%;
- usage accounting was complete;
- observed inference usage was 27,052 tokens;
- tokens per verified success are undefined because there were zero verified successes;
- all twelve trajectories stopped with `multi_tool_call`;
- all twelve stopped after one model attempt and before any tool action was executed;
- under this frozen HarbourDesk runtime contract, DeepSeek V4 Flash did not produce
  a successful trajectory.

## Non-claims

M1D does not establish:

- production reliability from a 12-case diagnostic suite;
- universal model quality outside HarbourDesk;
- that lower raw token usage represents better efficiency;
- that permitting multiple tool calls would improve system quality;
- that provider continuation handling failed in this baseline;
- routing benefit;
- final best-fixed-model selection before the DeepSeek V4 Pro baseline.

## Architecture implication for later experiments

The repeated `multi_tool_call` pattern across GLM-5.2 and DeepSeek V4 Flash exposes a
potential future experiment seam around trajectory regulation and tool-call
realization.

That seam must not be introduced into the fixed-model sequence because doing so
would invalidate direct comparability with the accepted baselines.

It may be evaluated later as an explicit intervention with its own baseline,
acceptance criteria, traces, and regression gate.

## Next gate

Do not tune DeepSeek V4 Flash.

Proceed to the final qualified fixed-model baseline under the same frozen contract:

`deepseek-v4-pro`

Only after DeepSeek V4 Pro is complete should the project select the fixed-model
comparator for the adaptive-routing experiment.
