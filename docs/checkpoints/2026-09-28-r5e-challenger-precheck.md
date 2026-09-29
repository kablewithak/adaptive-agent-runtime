# HarbourDesk R5E-A — Challenger Screen Precheck

**Date:** 2026-09-28
**Provider traffic:** none

R5E-A prepares a bounded fixed-model challenger screen without choosing a model by assumption.

The screen contains 36 development cases:

- 18 development templates;
- two cases per template;
- six cases per failure family;
- zero validation cases;
- zero locked cases.

The selection rule is the first two case IDs for each development template in the already-frozen R5 manifest order. This avoids selecting cases from the observed R5C outcomes.

The precheck reads the local account configuration but prints only profile name, model ID, protocol, tested completion capacity, capability-receipt presence, eligibility, and reasons. It does not print endpoint URLs or credentials.

A profile is marked eligible for the first OpenAI-compatible challenger screen only when:

- it is OpenAI-compatible;
- it is not the GLM-5.2 baseline;
- tested completion capacity is at least 1536;
- a capability receipt SHA256 is present.

The precheck also extracts GLM-5.2's already-observed R5C outcomes for the exact 36-case screen. GLM-5.2 is not rerun.

No challenger execution is authorized until this precheck is reviewed and one exact challenger profile is frozen.
