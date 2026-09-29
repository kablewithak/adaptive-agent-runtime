from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r10 import (
    R10_EVIDENCE_ROOTS,
    R10_PARENT_R7B_COMMIT,
    R10_REQUIRED_COMMITS,
)


def test_r10_commit_lineage_ends_at_frozen_r7b() -> None:
    assert R10_REQUIRED_COMMITS[-1] == R10_PARENT_R7B_COMMIT
    assert R10_PARENT_R7B_COMMIT == ("644c27e757760d1ab7ced0f27b7297377670a454")


def test_r10_evidence_roots_do_not_include_validation_or_locked_cases() -> None:
    paths = tuple(path.as_posix().lower() for path in R10_EVIDENCE_ROOTS)

    assert not any("/validation/" in path for path in paths)
    assert not any("/locked/" in path for path in paths)


def test_r10_closeout_does_not_define_a_locked_candidate_run() -> None:
    paths = tuple(path.as_posix().lower() for path in R10_EVIDENCE_ROOTS)

    assert not any("r9" in path for path in paths)
    assert not any("locked_eval" in path for path in paths)
