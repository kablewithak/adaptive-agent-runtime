# HarbourDesk R5D — Frozen Reference Analysis

**Date:** 2026-09-28
**Stage:** R5D
**Provider traffic:** none

R5D is bound to the first R5C development reference:

- run: `r5-glm52-development-reference-20260928-01`
- candidate commit: `67d841527d5fb12f9ee1d108b95729ebe6113bcd`
- manifest SHA256: `e9eab99e4833387285a580dc212405581121f9907c5d9b3b2a7f0572016a0e84`
- summary SHA256: `b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7`

The analyzer validates all 90 per-case receipts and trace hashes against the frozen suite summary before producing diagnostics.

It separates terminal-but-wrong outcomes from nonterminal runtime/provider outcomes, reports family and template concentration, identifies usage-incomplete cases, and preserves the efficiency claim boundary.

Because R5C reported incomplete usage accounting, overall R5 efficiency remains **INCONCLUSIVE**. Complete-usage subset metrics are diagnostic only and must not be substituted for the full-run efficiency baseline.

No R5 rerun, validation-set execution, locked-case materialization, or adaptive intervention is authorized by this slice.
