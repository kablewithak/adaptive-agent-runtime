from __future__ import annotations

from collections import Counter
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r6 import (
    load_r6_fault_program,
    r6_contract_summary,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r6_fault_program_is_exactly_six_by_four() -> None:
    program = load_r6_fault_program(ROOT)

    assert len(program.cases) == 24
    assert len({case.case_id for case in program.cases}) == 24

    family_counts = Counter(case.family for case in program.cases)
    assert len(family_counts) == 6
    assert set(family_counts.values()) == {4}


def test_r6_contract_has_zero_live_provider_scope() -> None:
    program = load_r6_fault_program(ROOT)

    assert program.provider_calls == 0
    assert program.live_model_calls == 0


def test_r6_acceptance_is_fail_closed() -> None:
    program = load_r6_fault_program(ROOT)

    assert program.acceptance.all_cases_complete is True
    assert program.acceptance.invariant_failures_required == 0
    assert program.acceptance.unexpected_effective_writes_required == 0
    assert program.acceptance.evidence_complete_required is True
    assert program.acceptance.partial_program_result == "INCONCLUSIVE"


def test_r6_contract_summary_is_deterministic() -> None:
    program = load_r6_fault_program(ROOT)
    summary = r6_contract_summary(program)

    assert summary["status"] == "PASS"
    assert summary["case_count"] == 24
    assert summary["family_count"] == 6
