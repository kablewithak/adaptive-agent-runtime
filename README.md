# Adaptive Agent Runtime

An experimental AI reliability system for measuring whether step-level model
selection and bounded evidence allocation can reduce inference consumption while
preserving independently verified task outcomes.

## Status

Design and bootstrap phase.

No optimisation result has been established.

## Primary research question

Can a small, inspectable routing policy use less inference than the best fixed
model configuration while preserving independently verified end-to-end task
outcomes?

## Initial environment

HarbourDesk is a synthetic B2B software support environment involving:

- subscription state
- feature entitlements
- policy evidence
- authorisation boundaries
- state-changing operations
- interruption and recovery

No real customer systems or payment systems are connected.

## Engineering principles

- schema-first model boundaries
- deterministic controls where semantic reasoning is unnecessary
- independent terminal-state evaluation
- bounded retries and execution
- explicit resource accounting
- provider-neutral application contracts
- preserved evidence for material experimental claims

## Current phase

P0 — Account, environment and capability verification.
