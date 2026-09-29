# HarbourDesk R6B — Deterministic Fault Executor

**Date:** 2026-09-29
**Status:** PROPOSED — validate and freeze before authoritative execution

R6B executes the frozen R6A 24-case fault programme against existing production
runtime, store, write-tool, multi-tool, and trace seams.

It does not call Huawei or any other external provider. Scripted provider outcomes
exist only to exercise the production runtime boundary deterministically.

## Evidence

Every case writes a `receipt.json`.

Runtime-boundary cases additionally write sanitized `trace.jsonl` evidence through
the existing `JsonlTraceSink`.

The suite writes:

- `manifest.json`;
- 24 case receipts;
- runtime traces where applicable;
- `summary.json`.

The suite is bound to:

- frozen R6A commit `610e7a03818e0ba8c8b726abb43f3816ef27c933`;
- the frozen R6 fault-program SHA256 computed at execution;
- R5E-C manifest SHA256
  `DDC6840EDA426AF02C77745475FCC9AECBE7AEAD06391B12CA91F1A3A29539D7`;
- R5E-C summary SHA256
  `C8E88EAA38E349B73D4BE1C7233261E129B9F75C1B7C1B372A9B4D2BA0345E0C`.

## Decision

PASS requires:

- 24/24 cases execution-complete;
- 24/24 case receipts PASS;
- zero invariant failures;
- zero unexpected effective writes;
- complete evidence;
- zero external-provider calls;
- zero live-model calls.

A case execution error or missing evidence makes the suite INCONCLUSIVE.

A completed suite with an invariant failure or unexpected effective write is FAIL.

No selective reruns are authorized for the authoritative run. A failed harness must
be repaired under a new commit and a new run ID.
