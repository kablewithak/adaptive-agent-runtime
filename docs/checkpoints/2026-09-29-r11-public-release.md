# HarbourDesk R11 — Public Evidence / Hugging Face Release

**Date:** 2026-09-29
**Status:** PROPOSED — freeze before building the public release

## Purpose

R11 converts the verified R10 no-candidate closeout into a small public results
artifact suitable for a Hugging Face repository or equivalent portfolio publication.

R11 does not rerun evaluation and does not open new benchmark evidence.

## Authoritative source

R10 freeze commit:

`4bd1b8c36202611d5503abb8536cc8e138056ce8`

R10 deterministic evidence-bundle SHA256:

`BFC2B8304481F8C3B61331F0E273343CC0D3F2EEF054F2D3120F9FF26A02A300`

R10 status:

- PASS;
- final frozen-contract verdict `INCONCLUSIVE`;
- development disposition `NO_ADAPTIVE_CANDIDATE_ADMITTED`;
- adaptive runtime promotion `REJECTED`;
- locked paired evaluation `NOT_RUN`;
- locked cases accessed: zero.

## Public surface

The release intentionally contains only:

- `README.md` formatted for Hugging Face;
- `results.json`;
- `provenance.json`;
- `PUBLICATION_NOTES.md`;
- four SVG result charts;
- `SHA256SUMS`.

It excludes:

- raw traces;
- private expected outcomes;
- validation cases;
- locked cases;
- development case payloads.

The public ZIP is deterministic and separately hashed.

## Public claim discipline

The strongest supported engineering statement is:

> The production-shaped reliability substrate passed the predeclared deterministic
> fault programme, while the tested bounded adaptive policy class failed development
> admission; the project therefore rejected the adaptive layer and preserved the
> locked benchmark.

The frozen R4 north-star verdict remains `INCONCLUSIVE` because no candidate was
admitted and no locked paired comparison was run.

Do not convert that verdict into PASS or FAIL for presentation.

## Hugging Face publication

The generated `huggingface_release` directory is the upload-ready surface. No
Hugging Face CLI or credentials are required by the R11 builder.

The release can be uploaded through the Hugging Face web interface as a dataset or
results repository. The repository should preserve the generated filenames and
`SHA256SUMS`.
