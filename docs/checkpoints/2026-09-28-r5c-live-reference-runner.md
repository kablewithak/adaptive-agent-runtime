# HarbourDesk R5C — Live 90-Case Fixed Reference Runner

**Date:** 2026-09-28
**Stage:** R5C
**Status:** PROPOSED — validate and commit before live execution

## Purpose

R5C measures the first broad fixed reference on the qualified R4 development population.

It does not select cases dynamically. It consumes the frozen R5 development manifest created and qualified in R5A/R5B.

## Frozen execution

- benchmark: 90 R4 development cases
- validation cases: 0
- locked cases: 0
- model: `glm-5.2`
- profile: `glm-5-2-openai`
- max model calls: 8
- max tool actions: 10
- trajectory deadline: 300 seconds
- request deadline: 60 seconds
- max completion tokens: 1536

The live runner preserves the qualified M3D runtime budget and the existing sequential read-only multi-tool realization in `run_live_harbourdesk`.

## Live-traffic safeguards

The CLI refuses provider traffic unless all of the following are true:

1. `--confirm-live-r5` is explicitly supplied.
2. `--expected-head` exactly matches the current Git HEAD.
3. The tracked working tree is clean.
4. The R5A/R5B preflight still returns PASS.
5. The selected profile remains `glm-5-2-openai`.
6. The frozen 90-case manifest and private expectations still match.

The API key is requested only after these checks pass.

## Evidence

Each case produces:

- `trace.jsonl`
- `receipt.json`

The suite produces:

- `manifest.json`
- `summary.json`

The summary records:

- pass count and rate;
- family and template aggregates;
- input/completion/inference tokens;
- tokens per verified success when usage is complete;
- stop-category counts;
- scoring-failure taxonomy;
- accepted/rejected multi-tool batch counts;
- deterministic-control violation count;
- realized writes from accepted multi-tool batches;
- exact candidate commit and development-manifest SHA256.

Private expected predicates are not written into run receipts.

## Interpretation boundary

R5C is a fixed-reference measurement, not an adaptive result.

Do not tune the runtime during the 90-case run. Provider errors and nonterminal stops remain observed outcomes and are not silently removed.

The 30 validation cases and 60 locked cases remain untouched.

## Next gate

After R5C completes, R5D analyses the observed development results by family, template, failure type, stop reason and efficiency. Only then should the project decide whether a second fixed reference or an adaptive intervention is justified.
