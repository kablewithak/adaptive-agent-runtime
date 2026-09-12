from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.mutation_rehearsal import (
    run_manual_mutation_rehearsal,
)

ROOT = Path(__file__).resolve().parents[3]


def test_manual_mutation_rehearsal_passes_all_control_scenarios() -> None:
    summary = run_manual_mutation_rehearsal(ROOT)

    assert summary.passed is True
    assert summary.scenario_count == 9
    assert summary.passed_count == 9
    assert summary.expected_rejection_count == 5
    assert summary.effective_business_write_count == 2
    assert summary.ticket_update_count == 1
    assert summary.llm_call_count == 0
