from __future__ import annotations

from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r6 import (
    load_r6_fault_program,
)
from adaptive_runtime.experiments.harbourdesk_r6_faults import (
    registered_r6_faults,
    run_r6_fault_program,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r6b_fault_registry_exactly_matches_frozen_contract() -> None:
    program = load_r6_fault_program(ROOT)

    assert {case.fault for case in program.cases} == registered_r6_faults()
    assert len(registered_r6_faults()) == 24


def test_r6b_full_deterministic_program_passes(tmp_path: Path) -> None:
    receipt = run_r6_fault_program(
        repo_root=ROOT,
        run_id="r6b-unit-test",
        candidate_commit="a" * 40,
        evidence_dir=tmp_path / "r6b-unit-test",
    )

    assert receipt.execution_status == "COMPLETE"
    assert receipt.decision == "PASS"
    assert receipt.case_count == 24
    assert receipt.complete_case_count == 24
    assert receipt.pass_case_count == 24
    assert receipt.failed_case_count == 0
    assert receipt.error_case_count == 0
    assert receipt.invariant_failure_count == 0
    assert receipt.unexpected_effective_writes == 0
    assert receipt.evidence_complete is True
    assert receipt.external_provider_calls == 0
    assert receipt.live_model_calls == 0
    assert set(receipt.family_pass_counts.values()) == {4}
