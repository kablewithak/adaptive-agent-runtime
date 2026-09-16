# HarbourDesk M3A — Multi-Tool Realization Contract

**Date:** 2026-09-16
**Stage:** M3A
**Status:** PROPOSED — validate locally before merge
**Live provider traffic:** NONE
**Runtime behavior change:** NONE

## Purpose

M3A freezes the first model/runtime compatibility intervention before any live runtime
behavior is changed.

The fixed-model phase showed that multi-tool emission is the dominant compatibility
failure for the cheaper candidates:

- GLM-5.2: 2/12 verified successes and 8 `multi_tool_call` stops;
- DeepSeek V4 Flash: 0/12 verified successes and 12 `multi_tool_call` stops.

Routing v1 is closed. M3A does not reopen routing.

The intervention question is narrower:

> Can the host safely realize provider responses containing multiple independent
> read-tool calls while preserving the existing HarbourDesk safety boundary?

## Baseline behavior

The current live runtime requires exactly one tool call per model response.

A response containing more than one tool call stops with:

`multi_tool_call`

and executes none of the proposed calls.

That behavior remains the frozen baseline condition.

## M3A v1 intervention boundary

M3A freezes a deliberately conservative intervention:

`READ_ONLY_SEQUENTIAL`

A provider response containing multiple tool calls may be realized only when every
call in the batch is an allowed HarbourDesk read tool.

A multi-tool response containing any write tool is rejected before the first action.

Single-tool responses remain on the existing runtime path, including single-tool
writes.

## Why write batches are excluded

The existing environment validates writes against current state and enforces
authority, approval, revision, ownership, idempotency, and unknown-operation
controls.

A provider-emitted multi-tool batch is not transactional.

If a write earlier in a batch commits and a later action fails, the runtime has no
general rollback contract. Later writes may also depend on state produced by earlier
actions even though the model has not observed intermediate results.

M3A therefore does not pretend structural batch preflight can provide transactional
write safety.

Read-only realization avoids that problem:

- reads do not mutate HarbourDesk state;
- the full batch can be structurally validated before execution;
- provider order can be preserved;
- partial realization caused by a deadline cannot leave partial writes behind.

Write-batch realization would require a separate explicit transaction or compensation
design and is outside M3A.

## Full preflight requirement

Before executing the first read in a multi-tool batch, the runtime intervention must
validate the whole batch.

The batch is rejected before execution if any call:

- names a write tool;
- names an unknown tool;
- contains malformed JSON arguments;
- violates the corresponding read-tool argument schema after host-controlled scope is
  applied;
- attempts to override a host-controlled current-ticket identifier;
- reuses a provider tool-call ID;
- duplicates an identical normalized read call within the same batch;
- would cause the batch to exceed the remaining tool-action budget.

No prefix of a rejected batch may execute.

## Bounded realization

M3A introduces no independent arbitrary batch-size constant.

The maximum realizable batch is bounded by the existing remaining
`max_tool_actions` budget.

For the frozen fixed-model experiment configuration, the existing maximum is ten tool
actions for the entire trajectory.

The intervention must not increase that trajectory budget.

## Execution semantics

For an accepted read-only batch:

1. preserve provider-emitted order;
2. execute one read at a time through the existing environment boundary;
3. preserve host-controlled call IDs and current-ticket scope;
4. append one tool-result message per provider tool-call ID;
5. record one tool-action trace per realized read;
6. do not perform parallel execution;
7. do not semantically reorder or merge calls;
8. do not retry the provider;
9. do not retry the model;
10. do not switch models.

The trajectory deadline must be checked before each realized action.

If the deadline expires after some reads have been realized, the trajectory stops with
the existing deadline outcome. Because M3A realizes only reads, this cannot leave a
partial write batch.

## Duplicate semantics

Provider tool-call IDs must be unique within the batch.

An exact duplicate normalized read call in the same batch is rejected rather than
executed twice.

This is deterministic redundancy control, not semantic deduplication across different
arguments.

## Tool-result semantics

A read result is authoritative even when it contains an environment-level read error.

Accepted calls are executed in order and their observed results are returned to the
model as separate tool messages.

The host does not fabricate missing intermediate evidence and does not synthesize a
combined result.

## Trace requirement for M3B

The runtime implementation must make multi-tool realization inspectable.

For each provider response that contains multiple tool calls, durable evidence must
identify:

- originating provider attempt index;
- provider tool-call count;
- batch disposition: realized or rejected;
- rejection reason when rejected;
- provider tool-call IDs in original order;
- resulting tool-action indexes when realized.

Existing provider reasoning content remains ephemeral and must not be added to durable
traces.

## Safety invariants

M3A must preserve all existing controls.

In particular:

- tenant scope remains host-controlled;
- current ticket remains host-controlled;
- environment call IDs remain host-controlled;
- idempotency keys remain host-controlled;
- single-tool writes continue through existing deterministic write controls;
- no write from a multi-tool provider response may execute in M3A v1;
- malformed or unknown calls execute nothing;
- action budgets are not expanded;
- provider/model retries are not introduced.

`MULTI_TOOL REALIZATION` does not mean `BYPASS TOOL BOUNDARY`.

## M3B scope

M3B implements and tests only the deterministic runtime realization layer.

M3B must use synthetic provider responses and must send zero provider traffic.

Required unit evidence includes:

- two valid reads are fully preflighted and realized in provider order;
- three valid reads are realized with distinct result messages;
- a batch containing one valid read and one write executes nothing;
- a batch containing an unknown tool executes nothing;
- malformed arguments anywhere in the batch execute nothing;
- duplicate provider tool-call IDs execute nothing;
- duplicate normalized reads execute nothing;
- insufficient remaining action budget executes nothing;
- single-tool behavior is unchanged;
- single-tool writes are unchanged;
- deadline interruption cannot create partial writes;
- durable traces contain batch metadata but no provider reasoning content.

## M3C intervention evaluation

If M3B passes, run GLM-5.2 on the same frozen 12-case diagnostic suite.

The M3C intervention changes only multi-tool realization behavior.

Keep unchanged:

- model: `glm-5.2`;
- profile: `glm-5-2-openai`;
- case order;
- prompts;
- model-call budget;
- tool-action budget;
- trajectory deadline;
- request deadline;
- completion-token limit;
- evaluator;
- scorer;
- provider retry behavior.

## M3C baseline

Existing GLM-5.2 baseline:

- verified successes: 2/12;
- passing cases: `hdm-001`, `hdm-004`;
- multi-tool incompatibility stops: 8;
- observed inference tokens: 104,741;
- observed tokens per verified success: 52,370.5;
- usage accounting: complete.

## M3C acceptance gate

The compatibility intervention ends in exactly one of:

- `PASS`
- `FAIL`
- `INCONCLUSIVE`

### Safety

PASS requires:

- zero deterministic-control violations;
- zero writes realized from a multi-tool batch.

Any violation is FAIL.

### Existing-pass preservation

Both existing GLM-5.2 passing cases must remain verified passes:

- `hdm-001`;
- `hdm-004`.

Regression of either is FAIL.

### Quality improvement

PASS requires at least:

`3/12 verified successes`

This is a strict improvement over the 2/12 baseline.

### Compatibility improvement

Count all terminal outcomes attributable to multi-tool incompatibility, including any
new explicit multi-tool-batch rejection category.

PASS requires:

`<= 7 multi-tool incompatibility stops`

This is a strict reduction from the baseline count of eight.

Renaming a rejected multi-tool outcome does not count as compatibility improvement.

### Usage evidence

Usage accounting must be complete.

If all deterministic gates pass but required usage evidence is incomplete, the result
is INCONCLUSIVE.

### Overall decision

- PASS: safety, existing-pass preservation, quality, compatibility, and usage pass;
- FAIL: any deterministic gate fails;
- INCONCLUSIVE: deterministic gates pass but required usage evidence is incomplete.

Token efficiency must be reported but is not an M3C PASS requirement.

M3C measures whether the compatibility intervention works. It does not yet decide
whether GLM-5.2 is suitable for routing.

## Routing remains closed

A successful M3C result does not automatically reopen routing.

Routing should be reconsidered only if the intervention produces a cheaper candidate
with genuine verified capability or materially improved verified outcomes per token.

A new routing experiment would require its own frozen comparison and feature-boundary
decision.

## DeepSeek Flash

Do not include DeepSeek V4 Flash in M3C.

If GLM-5.2 demonstrates a valid compatibility improvement, the same frozen
intervention may later be evaluated on Flash as a separate experiment.

## DeepSeek Pro

Provider-rate regulation for DeepSeek V4 Pro remains a separate intervention seam.

Do not combine rate regulation with multi-tool realization.

## Non-claims

M3A does not establish:

- that read-only realization will improve GLM-5.2;
- that the eight GLM-5.2 multi-tool responses are all read-only;
- that write batches are unsafe in every possible architecture;
- that GLM-5.2 will become routing-worthy;
- that Flash will improve;
- production reliability from the 12-case diagnostic suite.

M3A only freezes a conservative intervention contract that can be measured cleanly.
