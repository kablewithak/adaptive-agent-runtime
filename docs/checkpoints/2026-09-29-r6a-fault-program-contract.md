# HarbourDesk R6A — Fault Programme Contract

**Date:** 2026-09-29
**Status:** PROPOSED — validate and freeze before execution

R6 is a deterministic fault programme, not another model benchmark.

It contains 24 cases across six fault families:

1. provider/protocol boundaries;
2. tool realization and host-controlled scope;
3. trajectory budgets and deadlines;
4. store transactions and idempotency;
5. authorization and structured policy controls;
6. evidence integrity and privacy.

Each family contains exactly four cases.

R6A makes zero provider calls and zero live-model calls.

## Acceptance gate

R6 passes only when:

- all 24 cases complete;
- invariant failures equal zero;
- unexpected effective writes equal zero;
- evidence is complete.

An incomplete programme is INCONCLUSIVE rather than PASS.

The execution harness must reuse existing runtime, store, provider-test, and trace
seams. It must not create a parallel production runtime or a general chaos framework.
