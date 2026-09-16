# HarbourDesk M1C — GLM-5.2 Fixed-Model Baseline

**Date:** 2026-09-16
**Stage:** M1C
**Status:** COMPLETE — canonical GLM-5.2 fixed-model comparator
**Model:** `glm-5.2`
**Profile:** `glm-5-2-openai`
**Run ID:** `m1c-glm52-baseline-20260915-01`

## Purpose

M1C establishes the second directly comparable fixed-model HarbourDesk baseline.

It uses the same corrected environment, 12 diagnostic cases, independent evaluator,
runtime semantics, budgets, trace format, and usage accounting as the accepted M1B
GLM-5.1 comparator.

M1C is not a routing experiment and contains no model-specific case tuning.

## Frozen comparison contract

The run preserved the M1B execution contract:

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

The M1C suite completed all 12 cases.

| Metric | Result |
| --- | ---: |
| Cases completed | 12/12 |
| Independent passes | 2 |
| Pass rate | 16.6667% |
| Usage complete | TRUE |
| Observed input tokens | 97,077 |
| Observed completion tokens | 7,664 |
| Observed inference tokens | 104,741 |
| Tokens per verified success | 52,370.5 |

Stop categories:

- `multi_tool_call`: 8
- `ticket_terminal`: 3
- `model_text_without_terminal`: 1

Scoring failure counts:

- `disposition_mismatch`: 10
- `reason_code_mismatch`: 9
- `required_policy_reference_missing`: 7
- `effective_write_count_mismatch`: 3
- `entitlement_mismatch`: 2
- `required_operation_reference_missing`: 2
- `subscription_mismatch`: 1

## Case results

| Case | Result | Stop category | Attempts | Actions | Tokens |
| --- | --- | --- | ---: | ---: | ---: |
| hdm-001 | PASS | ticket_terminal | 8 | 8 | 22,190 |
| hdm-002 | FAIL | multi_tool_call | 2 | 1 | 4,181 |
| hdm-003 | FAIL | multi_tool_call | 3 | 2 | 6,454 |
| hdm-004 | PASS | ticket_terminal | 6 | 6 | 15,761 |
| hdm-005 | FAIL | multi_tool_call | 1 | 0 | 2,074 |
| hdm-006 | FAIL | multi_tool_call | 1 | 0 | 2,090 |
| hdm-007 | FAIL | multi_tool_call | 1 | 0 | 2,049 |
| hdm-008 | FAIL | multi_tool_call | 3 | 2 | 6,097 |
| hdm-009 | FAIL | ticket_terminal | 7 | 7 | 18,717 |
| hdm-010 | FAIL | multi_tool_call | 3 | 2 | 6,462 |
| hdm-011 | FAIL | multi_tool_call | 1 | 0 | 2,124 |
| hdm-012 | FAIL | model_text_without_terminal | 6 | 5 | 16,542 |

## Dominant failure mode

Eight of the twelve trajectories stopped with `multi_tool_call`.

The HarbourDesk live runtime intentionally permits one tool call per model turn.
When a model emits multiple tool calls in one turn, none are executed and the
trajectory stops with `multi_tool_call`.

This is part of the frozen runtime contract and is therefore legitimate model
compatibility evidence.

M1C does not change the runtime, prompt, retry policy, or action budget to
accommodate GLM-5.2 after observing this behavior.

## Other diagnostic observations

`hdm-009` reached `ticket_terminal` but still failed independent scoring because of a
`disposition_mismatch`.

`hdm-012` stopped with `model_text_without_terminal` and failed on disposition,
reason code, required operation reference, and required policy reference.

These remain model/trajectory quality failures rather than runtime failures.

## Comparison with canonical GLM-5.1

| Metric | GLM-5.1 | GLM-5.2 |
| --- | ---: | ---: |
| Verified passes | 6/12 | 2/12 |
| Pass rate | 50.0% | 16.7% |
| Observed inference tokens | 189,433 | 104,741 |
| Tokens per verified success | 31,572.166667 | 52,370.5 |
| `multi_tool_call` stops | 0 | 8 |
| Usage complete | TRUE | TRUE |

GLM-5.2 consumed 84,692 fewer observed inference tokens than GLM-5.1, approximately
44.7% less raw inference usage.

That lower total usage does not represent better efficiency because GLM-5.2 also
produced far fewer verified successes. Its observed tokens per verified success were
approximately 65.9% higher than GLM-5.1.

The correct interpretation is that GLM-5.2 terminated early on many trajectories
because of one-tool-per-turn contract violations.

## Evidence custody

Evidence directory:

`runs/m1c/m1c-glm52-baseline-20260915-01`

Manifest SHA256:

`71E037B91EFF5298F7E1490E75BDE568B002E0135F67B22497681D8C6734D7DF`

Summary SHA256:

`C0B4654C866BB75B65661E7198E8206DA83BC0D188D880A8699F8D44B8551F3B`

The evidence directory remains ignored and must not be staged.

## Supported claims

M1C supports the following claims:

- the frozen GLM-5.2 HarbourDesk suite completed 12/12 cases;
- GLM-5.2 achieved 2/12 independently verified successes;
- observed pass rate was 16.7%;
- usage accounting was complete;
- observed inference usage was 104,741 tokens;
- observed tokens per verified success were 52,370.5;
- eight trajectories stopped because the model emitted multiple tool calls in one turn;
- GLM-5.2 performed materially worse than the canonical GLM-5.1 run on this fixed
  diagnostic suite.

## Non-claims

M1C does not establish:

- production reliability from a 12-case diagnostic suite;
- a universal ranking of GLM-5.1 and GLM-5.2 outside HarbourDesk;
- that the raw token reduction represents better efficiency;
- that changing the one-tool-per-turn runtime contract would improve system quality;
- routing benefit;
- final best-fixed-model selection before the remaining fixed-model baselines.

## Next gate

Do not tune GLM-5.2.

Proceed to the next qualified fixed-model baseline under the same frozen contract:

`deepseek-v4-flash`

Only after comparable baselines for DeepSeek V4 Flash and DeepSeek V4 Pro should the
project select the fixed-model comparator for the adaptive-routing experiment.
