from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.read_rehearsal import (
    RehearsalStatus,
    run_manual_read_rehearsal,
)

ROOT = Path(__file__).resolve().parents[3]


def test_manual_read_rehearsal_passes_all_twelve_cases_without_mutation() -> None:
    summary = run_manual_read_rehearsal(ROOT)

    assert summary.status is RehearsalStatus.PASS
    assert summary.case_count == 12
    assert summary.total_call_count > 0
    assert all(case.status is RehearsalStatus.PASS for case in summary.cases)
    assert all(len(case.trace_sha256) == 64 for case in summary.cases)


def test_read_rehearsal_uses_committed_trajectory_fixtures() -> None:
    trajectory_root = ROOT / "benchmarks" / "harbourdesk" / "read_rehearsals"

    assert trajectory_root.is_dir()
    assert len(tuple(trajectory_root.glob("hdm-*.json"))) == 12
