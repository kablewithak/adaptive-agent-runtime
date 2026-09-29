# HarbourDesk R4C — Development and Validation Materialization

**Date:** 2026-09-28
**Stage:** R4C
**Status:** PROPOSED — validate locally before commit
**Live provider traffic:** NONE

## Purpose

Materialize the 90 development and 30 validation cases from the R4 template programme while keeping the 60 final locked cases unmaterialized.

## Pre-materialization corrections

Two contract issues were found before generating cases:

1. Some draft template mechanisms required terminal labels not present in the current HarbourDesk terminal-reason contract. Those nonlocked mechanisms were replaced with distinct cases that the current runtime and independent scorer can represent truthfully.
2. The first template catalog exposed locked mechanism descriptions. To preserve a stronger holdout, catalog v2 retains only two sealed locked reservation slots per failure family. Exact locked mechanisms and payloads are deferred to a separately sealed authoring step.

The previous catalog remains recoverable from Git history; catalog v2 is the active authority after this correction.

## Materialized evidence

- 18 development templates × 5 instances = 90 public development cases.
- 6 validation templates × 5 instances = 30 public validation cases.
- 12 locked template slots remain unmaterialized.
- Runtime-visible case directories contain only `case.json`, `initial_state.json`, and `documents.jsonl`.
- Evaluator expectations, authoring metadata, and deterministic rehearsal steps remain under ignored `evaluation_private/` paths.

## Deterministic validation gate

The private validator executes every rehearsal through the real HarbourDesk environment and independent scorer.
Every materialized case must:

- validate against the current domain schemas;
- complete its deterministic rehearsal in at most 10 environment actions;
- match all predeclared tool status/error expectations;
- finish in a state accepted by the independent terminal-state scorer;
- leave no exact expected outcome inside runtime-visible files.

A passing deterministic rehearsal establishes fixture solvability and contract consistency. It does not establish model competence.

## Locked-set custody

No `benchmarks/harbourdesk/r4/locked/` or `evaluation_private/harbourdesk/r4/locked/` payload directory is created by R4C.
The final 60 cases must be authored later under sealed custody after candidate/reference selection is frozen.

## Next gate

After R4C passes, inspect aggregate fixture coverage and run scorer counterexample/mutation checks against representative new cases before any broad live-model reference run.
