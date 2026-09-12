# HarbourDesk P1.5 — Deterministic End-to-End + Independent Scorer Gate

**Status:** implementation slice for the final deterministic integration gate before model-driven HarbourDesk runs.

## Purpose

P1.5 closes the deterministic loop established by P1.1–P1.4:

1. load one frozen HarbourDesk case;
2. expose read and write tools through one environment boundary;
3. execute a scripted end-to-end trajectory;
4. snapshot terminal state;
5. score that state through the independent evaluator;
6. fail the gate if either tool-level expectations or terminal-state scoring fails.

No LLM or provider call is made in this gate.

## Unified environment boundary

`HarbourDeskEnvironment` owns:

- the current tenant context;
- the current ticket context;
- the SQLite state store;
- structured HarbourDesk business rules;
- dispatch to existing read and write tool executors.

Two explicit call contracts are exposed:

- `ReadEnvironmentCall`
- `WriteEnvironmentCall`

Write calls require a host-supplied idempotency key. The model-facing runtime is not yet introduced.

P1.5 does not move permission logic into orchestration. All write permissions, revision checks,
idempotency checks, approval validation, ownership checks and transaction guarantees remain in the
P1.4 deterministic write boundary.

## Scripted development trajectories

The 12 development trajectories live under:

`benchmarks/harbourdesk/end_to_end_rehearsals/`

These are explicit integration fixtures, not benchmark labels and not candidate model prompts.
They may encode a development trajectory because their purpose is to prove environment plumbing.
They must never be injected into live-model context or reused as locked-evaluation hints.

The trajectories exercise:

- successful entitlement reconciliation;
- successful cancellation scheduling;
- clarification-only terminal states;
- stale-policy resolution without unnecessary business writes;
- ownership-conflict rejection;
- requester-authority rejection;
- expired-approval rejection;
- prior committed-operation inspection;
- unknown-operation blind-retry blocking;
- terminal ticket bookkeeping.

Each step declares only the expected tool status and, for expected failures, the deterministic error
code. Final correctness still comes from the separate evaluator.

## Independent scorer custody

The 12 evaluator outcomes remain local-only under:

`evaluation_private/harbourdesk/dev/<case>/expected.json`

That directory remains ignored by Git.

`run_manual_end_to_end_rehearsal(...)` fails closed if any expected file is missing. It does not
silently downgrade to unscored execution.

The committed unit test suite does **not** require evaluator-private files. A clean clone can run the
repository tests without them. A negative-control unit test wires the end-to-end runner to the
independent scorer using an intentionally incorrect synthetic expected predicate, proving that the
scorer can reject a trajectory even when every scripted tool step matches its local expectation.

## Gate outputs

Run:

```powershell
python .\scripts\run_harbourdesk_end_to_end_rehearsal.py
```

The script prints machine-readable gate lines and writes a sanitized local receipt to:

`runs/p1_5_end_to_end_rehearsal/summary.json`

The receipt contains case IDs, step/scorer pass state, effective-write counts and scorer failure
codes. It does not contain private expected predicates.

## P1.5 acceptance criteria

P1.5 passes only when all of the following are true:

- all 12 manual development cases execute;
- every scripted tool-step expectation matches;
- all 12 terminal states pass the independent scorer;
- no case exceeds its evaluator write budget;
- unrelated-state preservation checks pass;
- the prior-unknown operation case performs no blind business retry;
- the full repository test suite passes;
- Ruff passes;
- mypy passes;
- `git diff --check` passes;
- LLM call count is exactly zero.

A local reconstruction of the current P1.1–P1.4 state plus this P1.5 slice produced:

- 12/12 end-to-end case passes;
- 12/12 scripted-trace passes;
- 12/12 independent-scorer passes;
- 60 deterministic environment steps;
- 4 effective business writes;
- 0 LLM calls;
- 86/86 reconstructed repository tests passing.

These are reconstruction results, not a substitute for the authoritative user-repository gate.

## Non-claims

P1.5 does not establish:

- model competence;
- provider reliability under HarbourDesk task execution;
- context-window sufficiency;
- routing quality;
- token-efficiency improvement;
- retry-policy quality under live provider faults;
- benchmark generalisation;
- locked-evaluation performance.

No such claims should be made until the corresponding live experiments are measured.

## Handover boundary

After P1.5 is validated, merged and synced to clean `main`, the deterministic HarbourDesk substrate
is complete enough for a primary engineering handover.

That is the preferred handover point before introducing model-driven trajectories, because failures
after this gate can be attributed more cleanly to model/provider/runtime policy rather than to an
unproven simulator or scorer path.

## Next phase

The next phase should begin with a fixed-model HarbourDesk model screen, not adaptive routing.

The first model-driven experiment should preserve:

- the same 12 development cases;
- the same environment boundary;
- the same independent scorer;
- exact provider/model profile;
- tool-call trace;
- token usage;
- stop reason;
- failure taxonomy;
- zero changes to the expected labels during the run.

Only after a fixed-model baseline exists should routing or context-allocation interventions be
introduced.
