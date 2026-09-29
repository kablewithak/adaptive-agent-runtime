# HarbourDesk R5E-B — GLM-5.1 Challenger Qualification

**Date:** 2026-09-28
**Stage:** R5E-B
**Target profile:** `primary-openai`
**Target model:** `glm-5.1`

## Purpose

R5E-A found no challenger profile eligible because the local account configuration did not bind current profiles to tested 1536-token completion capacity and capability receipt hashes.

Historical project evidence already protocol-qualified GLM-5.1. R5E-B therefore performs one bounded current capability call to establish the missing R5E-specific completion-envelope evidence.

## Live scope

Exactly one provider request is made.

The request:

- uses `primary-openai`;
- requires `glm-5.1`;
- requests `max_completion_tokens=1536`;
- disables thinking;
- asks for one exact short output;
- requires successful usage accounting.

No HarbourDesk benchmark case, private expectation, validation case, or locked case is read or executed.

## PASS

PASS requires:

- successful provider response;
- returned model `glm-5.1`;
- exact expected output;
- observed input and completion token accounting.

On PASS, the sanitized qualification receipt is hashed and the ignored local profile metadata is updated with:

- `max_tested_completion_tokens=1536`;
- `capability_receipt_sha256=<new receipt SHA256>`.

The script refuses to mutate `configs/account.local.json` if Git reports that file as tracked.

## Next gate

After PASS, rerun R5E-A. `primary-openai` should become an eligible challenger. Only then freeze and execute the 36-case challenger screen.
