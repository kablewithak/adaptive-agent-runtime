# M0B — Bounded live HarbourDesk runner and accounting contract

**Date:** 2026-09-14
**Base revision:** `6b80c7c9966887190d203a4fc3d209067e5f721c`
**Status:** Proposed implementation slice; requires local repository validation before merge.

## Purpose

Introduce the smallest model-driven runtime needed to execute HarbourDesk tasks against the
already-trusted deterministic environment without introducing routing, automatic retries, or
evaluator leakage.

M0A froze the model-visible observation boundary. M0B adds the execution and evidence boundary
needed before a first Huawei canary.

## Scope

M0B adds:

- one bounded single-model loop;
- model-facing tool definitions derived from the current Pydantic argument contracts;
- host ownership of tenant scope, current ticket, environment call IDs, and idempotency keys;
- one-tool-call-per-model-turn enforcement;
- deterministic model-call, tool-action, request-time, and trajectory-time budgets;
- explicit stop categories;
- attempt-level usage status that distinguishes observed, missing, and unknown-after-error usage;
- JSONL trace events written before provider dispatch and after each completed attempt/tool action;
- final-state hashing and return of the authoritative final HarbourDesk state;
- fake-provider tests covering success and failure paths;
- a post-runtime scoring test proving the deterministic scorer remains outside the model loop.

## Explicit non-scope

M0B does **not** add:

- adaptive routing;
- provider retries;
- mid-trajectory durable resume;
- context compression or summarisation;
- benchmark expansion;
- Huawei live traffic;
- new write permissions;
- changes to the deterministic scorer;
- changes to HarbourDesk business rules;
- an agent framework.

## Model-facing scope controls

The model never controls:

- `tenant_id`;
- the current `ticket_id`;
- environment `call_id` values;
- write `idempotency_key` values.

`get_ticket` and `update_ticket` therefore hide `ticket_id` from their model-facing schemas. The
runner injects the host-selected current ticket ID immediately before environment dispatch.

This preserves M0A's rule that the host selects task scope rather than allowing the model to widen
it by guessing another ticket identifier.

## Tool schema source of truth

Tool schemas are generated from the current Pydantic argument contracts in:

- `read_tools.py`;
- `write_tools.py`.

The runner performs only the explicit host-controlled `ticket_id` projection described above. It
does not reproduce historical PRD schemas manually.

## Execution contract

The runner is deliberately simple:

1. Build the M0A initial observation.
2. Send the fixed system instruction plus that observation and the current tool schemas.
3. Record an `attempt_started` event before provider dispatch.
4. Accept at most one tool call from the model.
5. Convert the model call into the existing `EnvironmentCall` boundary.
6. Inject host-controlled call/idempotency/ticket metadata.
7. Execute through `HarbourDeskEnvironment.execute()`.
8. Return the structured tool result to the same model conversation.
9. Stop immediately when the authoritative current ticket becomes non-open.
10. Otherwise continue only while all budgets remain available.

A text-only model response cannot close the task while the ticket remains open.

## Stop categories

M0B records one of:

- `ticket_terminal`;
- `provider_error`;
- `provider_refusal`;
- `invalid_tool_call`;
- `multi_tool_call`;
- `model_text_without_terminal`;
- `model_call_budget_exhausted`;
- `tool_action_budget_exhausted`;
- `trajectory_deadline_exceeded`.

These are runtime outcomes, not evaluator verdicts.

## Budget defaults

Defaults are intentionally conservative starting points rather than measured provider limits:

- maximum model calls: 12;
- maximum tool actions: 18;
- trajectory wall-clock budget checked between operations: 480 seconds;
- request deadline: 60 seconds;
- maximum completion allowance: 768 tokens.

M1A may adjust the completion allowance once during the canary if evidence shows it is insufficient.
Any comparison run must freeze the values used.

The request timeout remains the actual HTTP client timeout semantics of the provider adapter. M0B
does not claim that it cancels remotely billed work after the local timeout fires.

## Usage accounting

Each provider attempt records exactly one usage status:

- `observed` — the provider returned structured usage;
- `missing` — the provider returned a usable result without usage;
- `unknown_after_error` — the adapter raised and exact usage is unavailable.

Missing or unknown usage is never converted to zero.

There are no automatic provider retries in M0B. A retryable provider classification remains evidence
for diagnosis, not an instruction to spend more inference automatically.

## Durable trace contract

The JSONL sink writes only sanitised structured events:

- `run_started`;
- `attempt_started`;
- `attempt_finished`;
- `tool_action_finished`;
- `run_finished`.

`attempt_started` is flushed and `fsync`-ed before provider dispatch so a caught or process-level
interruption has a durable admission record up to the last successful local write.

Durable events exclude:

- Huawei API credentials;
- raw system/user prompts;
- raw free-form assistant text;
- provider `reasoning_content`.

Provider continuation state remains in the in-memory `ChatMessage` history only. M0B therefore does
not claim exact mid-trajectory durable resume.

## Provider continuation rule

When a provider returns `provider_reasoning_content`, the runner carries it forward in the in-memory
assistant message so DeepSeek Flash continuation remains compatible with the repaired Huawei adapter.

The same field is absent from the durable JSONL event schema and from the returned sanitised trace.

## Fake-provider validation cases

The focused test module covers:

1. tool schemas hide host-controlled `ticket_id`;
2. a valid two-turn tool continuation reaches a terminal ticket;
3. provider continuation reasoning survives in memory but is absent from durable trace output;
4. host-generated idempotency metadata is used for writes;
5. a provider timeout stops without retry and records `unknown_after_error` usage;
6. a successful response without usage records `missing` rather than zero;
7. multiple tool calls in one model turn execute nothing;
8. malformed tool-call arguments execute nothing;
9. model-call budget exhaustion stops before another dispatch;
10. tool-action budget exhaustion rejects the next action before execution;
11. final state can be passed to the existing deterministic scorer only after the runtime returns;
12. text-only claims of completion do not close an open ticket;
13. provider request-identity mismatch fails closed as a protocol error;
14. an existing trace path is rejected rather than silently appended to.

The tests use no `evaluation_private/` files.

## Evaluator custody

The live runner imports no expected outcomes and invokes no scorer.

It returns the final authoritative `HarbourDeskVisibleState`. An outer evaluator process or test may
then call the existing deterministic scorer with evaluator-only expected outcomes.

This keeps:

```text
model/runtime execution
        separate from
evaluator truth and judgment
```

## Required local gate

Before merge, run the established changed-file remediation followed by full repository validation.
At minimum:

```text
changed-file Ruff fix/format
mypy src
focused M0B tests
full pytest
full Ruff
full mypy
git diff --check
private/runtime custody inspection
```

No Huawei canary should be run until those checks pass on the user's repository.

## Acceptance criteria

M0B passes only when:

- [ ] existing M0A observation tests remain green;
- [ ] model-facing ticket scope cannot be overridden;
- [ ] unsupported multi-action output is rejected without partial execution;
- [ ] malformed/unknown tool calls cannot execute;
- [ ] provider exceptions do not trigger automatic retries;
- [ ] every admitted provider attempt has a durable pre-dispatch event when a JSONL sink is used;
- [ ] missing/unknown usage is explicit;
- [ ] provider continuation reasoning is not present in durable trace output;
- [ ] the runtime stops at configured model/tool/time bounds;
- [ ] text-only completion cannot substitute for authoritative ticket state;
- [ ] the final state is available for independent post-run scoring;
- [ ] no evaluator-private data is needed by public M0B tests;
- [ ] full repository Ruff, mypy, pytest, and `git diff --check` pass locally.

## Non-claims

M0B does not prove:

- any Huawei model solves HarbourDesk;
- the prompt is optimal;
- the tool descriptions are optimal;
- the initial observation is token-optimal;
- current budget defaults are provider-optimal;
- exact usage can be recovered after all provider errors;
- interrupted trajectories can resume exactly;
- any model is better or cheaper than another;
- adaptive routing helps.

## Next gate

After M0B is validated, merged, and cleaned up:

**M1A — characterise a sufficient shared context envelope and run one bounded `glm-5.1` HarbourDesk
canary on a named development case.**

The canary must use the M0A observation contract, M0B runner/trace contract, the existing Huawei
adapter, a fresh synthetic store, no automatic retries, and independent post-run scoring.
