# HarbourDesk R5 — Fixed Reference Closeout

**Date:** 2026-09-29
**Status:** CLOSED FOR DEVELOPMENT REFERENCE SELECTION

## GLM-5.2 development reference

The frozen 90-case development run remains the reference candidate:

- 43/90 independently scored passes;
- 36 terminal-but-wrong failures;
- 11 nonterminal failures;
- one provider-error case with incomplete usage;
- zero deterministic-control violations;
- zero writes from accepted multi-tool batches.

Development efficiency for this run remains INCONCLUSIVE because usage was incomplete
for one provider-error case. That value is not repaired, imputed, or silently rerun.

## GLM-5.1 challenger screen

The predeclared 36-case challenger screen completed without provider contamination:

- GLM-5.1: 15/36;
- frozen GLM-5.2 result on the same cases: 16/36;
- paired challenger wins: 2;
- paired baseline wins: 3;
- F4+F5+F6 GLM-5.1: 1/18;
- F4+F5+F6 GLM-5.2: 2/18;
- usage complete: true;
- provider errors: 0;
- deterministic-control violations: 0.

The predeclared screen decision was `DO_NOT_PROMOTE`.

GLM-5.1 therefore does not receive a full 90-case development run.

## R5 conclusion

R5 selects the frozen GLM-5.2 execution contract as the fixed development reference
candidate for subsequent fault and adaptation work.

This is not a universal model ranking and does not establish final locked quality or
efficiency. Final acceptance still requires the separately locked paired evaluation.

The next gate is the 24-case deterministic R6 fault programme.
