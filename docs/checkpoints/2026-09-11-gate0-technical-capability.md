# Gate 0 Technical Capability Checkpoint

**Project:** Adaptive Agent Runtime  
**Date:** 2026-09-11  
**Status:** Technical capability PASS; account-governance evidence partially observable

## Scope

This checkpoint records the live Huawei MaaS capability evidence observed before HarbourDesk implementation.

It deliberately excludes:
- API keys and Authorization headers
- raw provider response bodies
- account identifiers
- billing screenshots
- raw reasoning / chain-of-thought content
- ignored `runs/` artifacts

## Live model catalog

The authenticated `/v2/models` discovery call returned:

- `deepseek-v4-flash`
- `glm-5.1`
- `glm-5.2`
- `qwen3-32b`
- `deepseek-v4-pro`

Sanitised model-catalog receipt SHA-256:

`53960ab83b09e7e828d1d6ea4f5be07b7d625eb253e00795c3fefe6a0a418208`

## Exact-output capability probes

| Model | Result | HTTP | Usage present | Observed latency | Receipt SHA-256 |
| --- | --- | ---: | --- | ---: | --- |
| `glm-5.1` | PASS | 200 | yes | 9,432 ms | `1a9bfec9db19238bcac1c0473ee1e2f5de34f0b1c80aa5c8ea7c9a0c9ec5fc86` |
| `deepseek-v4-flash` | PASS | 200 | yes | 2,609 ms | `aa1f9845931fcd3fb56ff870aa0f1d0d95dac41aaef3938c7cb97c593c4a2cc3` |
| `glm-5.2` | PASS | 200 | yes | 7,889 ms | `81028ecd7451030b619e46d6f18adb16da403d2fc24b5a301ab52f823d98bc69` |
| `deepseek-v4-pro` | PASS | 200 | yes | 2,856 ms | `acdaf5f9a76dcb1b6d48c9b3e78dc84de5ec19fd6f2af731cd4e3a0746d4ec26` |
| `qwen3-32b` | FAIL | 401 | no | 1,668 ms | `a873b4a2bd70c9af26ce7234d5ccdd2334ad1912e2e87a419f3edbc8ce847924` |

The Qwen failure was repeated while the same process-loaded API key successfully called `deepseek-v4-flash`. Therefore the evidence supports a model-specific entitlement/authentication mismatch rather than a generic invalid credential.

Known-good same-process control receipt SHA-256:

`4206281e9487fddc61ff601cb040c5fc7ecccb30badc2f09bc0bcb6bc19adc8f`

## Protocol qualification

The live protocol harness tested:

1. output-cap acceptance
2. thinking-off control
3. prompted JSON with local schema validation
4. native tool-call generation
5. tool-result round trip

### `glm-5.2`

All five checks passed.

Thinking-off returned `reasoning_tokens=0`.

Receipt SHA-256:

`bea2bb81b19404567bf84e075738a51fd9ba218c5fa0882795ecb7bfd1a1fc16`

### `glm-5.1`

All five checks passed.

Thinking-off returned `reasoning_tokens=0`.

Receipt SHA-256:

`cbbde9ec0833af140df7eee85dd233c4fedb41967c7443925b216a81ccfb8498`

### `deepseek-v4-pro`

All five checks passed.

Thinking-off returned `reasoning_tokens=0`.

Receipt SHA-256:

`6212462f6d4b31bdb00312af006179bbcd8806934a9ff9497c184561cbf0e665`

### `deepseek-v4-flash`

The initial normalized protocol probe passed output-cap, thinking-off, JSON validation and native tool-call generation but failed the tool-result continuation with HTTP 400.

Initial failed protocol receipt SHA-256:

`25a0bc5e536e616799f495813db1ab37bdcef29ed68a27da954eff25408d013f`

A documented-shape intervention still failed at the same continuation boundary.

Second failed protocol receipt SHA-256:

`42aceba61692dffbb996bfb0a98ac33d2fc804beffd9fe06b134aaeddabc4f01`

A bounded two-call raw-wire diagnostic then replayed the provider's assistant message in memory. The assistant message contained:

- `content`
- `reasoning_content`
- `role`
- `tool_calls`

Raw replay passed the full tool round trip with HTTP 200 on both calls.

Wire-diagnostic receipt SHA-256:

`e7981b880668e6485cdc81d14043ae99c1d35bf84c8eab4bb87fa2399067681d`

This isolated the defect to the normalization boundary dropping Huawei continuation state. P0.4C preserved `reasoning_content` as ephemeral provider continuation state, excluded it from ordinary serialization, and the user subsequently completed the normal Flash protocol rerun successfully. The final P0.4C receipt hash was not pasted into the project handover and is therefore not asserted here.

## Engineering conclusion

Protocol-qualified candidates:

- `glm-5.1`
- `glm-5.2`
- `deepseek-v4-flash`
- `deepseek-v4-pro`

Unresolved candidate:

- `qwen3-32b` — catalog-visible but HTTP 401 on inference with a credential proven valid against another model in the same process

The DeepSeek Flash investigation demonstrated a production-shaped boundary failure:

> Successful tool-call generation did not guarantee successful continuation because a provider-specific continuation field was lost during normalization.

The repair preserves that continuation field only for provider replay and excludes it from normal evidence serialization.

## Gate state

- `GATE_0_TECHNICAL_CAPABILITY=PASS`
- `MULTI_MODEL_SUBSTRATE=VERIFIED`
- `USAGE_METADATA_PRESENT=VERIFIED`
- `ACCOUNT_BALANCE=UNKNOWN_NOT_OBSERVABLE`
- `GRANT_EXPIRY=UNKNOWN_NOT_OBSERVABLE`
- `PAID_FALLBACK=UNKNOWN_NOT_OBSERVABLE`
- `TOKEN_POOL_SCOPE=UNKNOWN_NOT_OBSERVABLE`
- `CONTEXT_ENVELOPE=NOT_YET_MEASURED`

The account-governance unknowns exist because the credential was awarded to the project owner without access to the underlying Huawei MaaS account/console.

## Non-claims

This checkpoint does not establish:

- comparative model quality
- general latency superiority
- pricing or currency savings
- exact remaining token balance
- grant expiry
- maximum context windows
- production readiness
- HarbourDesk task success

Those require later evidence.
