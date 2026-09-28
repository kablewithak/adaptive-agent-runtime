# HarbourDesk R5A/R5B — Fixed Reference Preflight

**Date:** 2026-09-28
**Stage:** R5A/R5B
**Status:** PROPOSED — local preflight required before any R5 provider traffic
**Provider traffic:** PROHIBITED BY THIS SLICE

## Bound experiment

R5 establishes a broader fixed-model reference before any adaptive intervention.

The experiment is bound to R4-qualified commit:

`0c741192e52916de2330462b9c95bbd31e004924`

The selected benchmark is the 90-case R4 development population only.

- development cases: 90
- validation cases: 0
- locked cases: 0
- model: `glm-5.2`
- endpoint profile: `glm-5-2-openai`
- max model calls: 8
- max tool actions: 10
- trajectory deadline: 300 seconds
- request deadline: 60 seconds
- max completion tokens: 1536

The budget is intentionally identical to the qualified M3D runtime budget.

## Why preflight is separate from execution

R5A/R5B does not contain a live provider runner. It creates a fail-closed authorization boundary before the paid/stochastic run.

The preflight proves:

- the qualified R4 commit is an ancestor of the current repository state;
- the R4 template catalog hash is unchanged;
- the exact 90-case development order matches the R4 catalog;
- no validation or locked case enters the selection;
- every runtime-visible case file matches its frozen SHA256;
- every private `expected.json` exists and matches its frozen SHA256;
- public case IDs and expected terminal-ticket IDs agree;
- the local GLM-5.2 endpoint profile matches the frozen model/protocol identity;
- the current M3D budget still matches the frozen R5 budget;
- the local R4 quality receipt still proves the previously observed 120-case / 520-negative-control PASS.

No API key is read and no provider adapter is constructed by the R5 preflight.

## Manifest custody

`benchmarks/harbourdesk/r5/development_reference_manifest_v1.json` is tracked.

It includes public case hashes and hashes of the private expectations. It does not include evaluator predicates or locked fixture material.

The private expectations remain under:

`evaluation_private/harbourdesk/r4/development/<case>/expected.json`

They remain untracked.

## Acceptance

R5A/R5B is complete only when:

- Ruff passes;
- targeted unit tests pass;
- mypy passes;
- `git diff --check` passes;
- `R5_PREFLIGHT_STATUS=PASS`;
- 90 public hash bindings match;
- 90 private expectation hash bindings match;
- validation selection is zero;
- locked selection is zero;
- the R4 quality receipt check passes.

## Next gate

After this preflight is committed, R5C may introduce the live 90-case runner. That runner must consume this frozen manifest rather than rediscovering or reselecting cases at execution time.

R5C must preserve the same GLM-5.2 profile and M3D budget and record per-case traces, independent scores, usage, stop categories, family/template aggregates, and deterministic-control evidence.
