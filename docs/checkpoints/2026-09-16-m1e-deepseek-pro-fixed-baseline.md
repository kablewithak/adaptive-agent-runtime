# HarbourDesk M1E — DeepSeek V4 Pro Fixed-Model Baseline

**Date:** 2026-09-16
**Stage:** M1E
**Execution status:** COMPLETE
**Quality status:** INCONCLUSIVE — provider rate limiting contaminated the run
**Model:** `deepseek-v4-pro`
**Profile:** `deepseek-pro-openai`
**Run ID:** `m1e-deepseek-pro-baseline-20260916-01`

## Purpose

M1E was intended to establish the fourth directly comparable fixed-model HarbourDesk
baseline under the same corrected 12-case benchmark contract used by M1B through M1D.

The runner completed all 12 cases, but the live evidence is not a valid model-quality
baseline because Huawei returned HTTP 429 `rate_limited` responses during the run.

The result is preserved as provider-operating-envelope evidence rather than being
misclassified as DeepSeek V4 Pro quality.

## Observed execution result

| Metric | Observed result |
| --- | ---: |
| Cases completed | 12/12 |
| Score passes | 0 |
| Raw pass rate | 0.0% |
| Usage complete | FALSE |
| Observed input tokens | 6,758 |
| Observed completion tokens | 302 |
| Observed inference tokens | 7,060 |
| Tokens per verified success | UNKNOWN |
| Provider-error stops | 12 |

These raw score values are not valid DeepSeek V4 Pro quality measurements because the
provider failures prevented comparable execution.

## Root cause

The trace establishes a provider rate-limit incident.

For `hdm-001`, the first three provider interactions succeeded. The fourth request
returned HTTP 429 with error code `rate_limited` and `retryable=true`. The case then
stopped with `provider_error`.

For `hdm-002`, the first provider request returned the same HTTP 429
`rate_limited` error. The remaining cases likewise stopped with `provider_error`.

This pattern demonstrates provider-rate-limit contamination rather than a clean model
quality result.

## Usage interpretation

Usage accounting was incomplete because requests that returned provider errors had
unknown usage after error.

The observed 7,060 inference tokens must not be compared as an efficiency measurement
against the complete-usage GLM and Flash baselines.

Tokens per verified success are not meaningful for M1E-01.

## Operating-limit inspection

The local `deepseek-pro-openai` profile contained no configured operating envelope:

- `rpm_operating_limit = None`
- `tpm_operating_limit = None`
- `max_tested_prompt_tokens = None`
- `max_tested_completion_tokens = None`

The run therefore did not knowingly violate a documented repository RPM or TPM
constraint.

## Recovery probe

After preserving M1E-01, one isolated DeepSeek V4 Pro health probe was run.

Observed result:

- provider outcome: success;
- returned model: `deepseek-v4-pro`;
- HTTP status: `200`;
- usage present: TRUE;
- input tokens: 11;
- completion tokens: 16;
- stop reason: `length`.

The probe establishes that the endpoint became reachable again. It does not establish
that an unpaced 12-case benchmark can execute without hitting the provider rate limit
again.

## Evidence custody

Evidence directory:

`runs/m1e/m1e-deepseek-pro-baseline-20260916-01`

Manifest SHA256:

`921720F99115B17FD2BB9003646F941210AEB73612523BE04922DA19ED750657`

Summary SHA256:

`E293C081758F941642C89F5DE59BDFB490B2663F5F2ECE3EB776C06BC6C8C62E`

The evidence directory remains ignored and must not be staged.

## Classification

M1E-01 is classified as:

- execution status: `COMPLETE`;
- model-quality status: `INCONCLUSIVE`;
- primary cause: `PROVIDER_RATE_LIMIT`.

The raw `0/12` score must not be used to rank DeepSeek V4 Pro against the valid
fixed-model baselines.

## Why M1E is not rerun immediately

A second identical unpaced run could reproduce the same provider-rate-limit
contamination.

Adding hidden sleeps, automatic retries, pacing, or a Pro-specific exception inside
M1E would alter the fixed-model experiment contract after observing the result.

Any rate-aware provider regulation should be introduced only as an explicit
intervention with its own acceptance criteria and before/after evidence.

## Supported claims

M1E supports the following claims:

- the runner mechanically completed 12/12 cases;
- all twelve cases stopped with `provider_error`;
- `hdm-001` completed three successful provider interactions before an HTTP 429;
- `hdm-002` immediately received the same HTTP 429;
- the provider classified the errors as retryable `rate_limited`;
- usage accounting was incomplete;
- an isolated later health probe returned HTTP 200 with observed usage;
- DeepSeek V4 Pro quality remains unmeasured by a valid comparable 12-case baseline.

## Non-claims

M1E does not establish:

- that DeepSeek V4 Pro has a 0% HarbourDesk quality rate;
- a valid tokens-per-success value for DeepSeek V4 Pro;
- that DeepSeek V4 Pro is worse than the other evaluated models;
- a stable provider RPM or TPM limit;
- that an unpaced rerun would succeed;
- routing benefit.

## Next gate

Close the fixed-model phase using only valid/evaluable baselines.

The adaptive-routing experiment should use the strongest valid fixed comparator as
its reference while preserving M1E as explicit inconclusive provider-capacity
evidence.
