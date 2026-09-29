from __future__ import annotations

from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r7a import (
    R7A_EFFICIENCY_TARGET,
    analyze_r7a,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r7a_uses_only_frozen_development_evidence() -> None:
    receipt = analyze_r7a(ROOT)

    assert receipt.status == "PASS"
    assert receipt.case_count == 90
    assert receipt.validation_cases_accessed == 0
    assert receipt.locked_cases_accessed == 0
    assert receipt.private_expected_files_accessed == 0


def test_r7a_oracles_never_claim_policy_validity() -> None:
    receipt = analyze_r7a(ROOT)

    assert receipt.failure_only_oracle.policy_valid is False
    assert receipt.family_oracle.policy_valid is False
    assert receipt.failure_only_oracle.observed_pass_loss_count == 0
    assert receipt.family_oracle.observed_pass_loss_count == 0


def test_r7a_cap_table_covers_frozen_budget() -> None:
    receipt = analyze_r7a(ROOT)

    assert [metric.max_model_calls for metric in receipt.universal_cap_metrics] == list(range(1, 9))


def test_r7a_feasibility_is_derived_from_predeclared_20_percent_target() -> None:
    receipt = analyze_r7a(ROOT)

    assert receipt.efficiency_target_fraction == R7A_EFFICIENCY_TARGET
    assert receipt.efficiency_evidence_status == "DIAGNOSTIC_ONLY"
