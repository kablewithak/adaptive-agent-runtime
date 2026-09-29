from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r7b import (
    POLICY_SPECS,
    R7B_EFFICIENCY_TARGET,
    R7B_MIN_BUCKET_SUPPORT,
)


def test_r7b_search_space_is_bounded_and_runtime_visible() -> None:
    assert len(POLICY_SPECS) == 5
    allowed = {
        "initial_operation_reference_count",
        "first_attempt_realized_tool_count",
        "first_attempt_tool_signature",
    }

    for spec in POLICY_SPECS:
        assert set(spec.signals) <= allowed
        assert 1 <= len(spec.signals) <= 2


def test_r7b_qualification_thresholds_are_frozen() -> None:
    assert R7B_MIN_BUCKET_SUPPORT == 10
    assert R7B_EFFICIENCY_TARGET == 0.20
