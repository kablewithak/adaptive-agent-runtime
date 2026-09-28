from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r5e_screen import _screen_decision


def test_screen_promotes_on_overall_quality_path() -> None:
    decision = _screen_decision(
        pass_count=20,
        hard_family_pass_count=4,
        usage_complete=True,
        provider_error_count=0,
        deterministic_control_violation_count=0,
        writes_from_multi_tool_batches=0,
    )
    assert decision == "PROMOTE"


def test_screen_promotes_on_hard_family_path_without_overall_regression() -> None:
    decision = _screen_decision(
        pass_count=16,
        hard_family_pass_count=6,
        usage_complete=True,
        provider_error_count=0,
        deterministic_control_violation_count=0,
        writes_from_multi_tool_batches=0,
    )
    assert decision == "PROMOTE"


def test_screen_does_not_promote_below_both_thresholds() -> None:
    decision = _screen_decision(
        pass_count=19,
        hard_family_pass_count=5,
        usage_complete=True,
        provider_error_count=0,
        deterministic_control_violation_count=0,
        writes_from_multi_tool_batches=0,
    )
    assert decision == "DO_NOT_PROMOTE"


def test_screen_is_inconclusive_on_provider_or_usage_contamination() -> None:
    assert (
        _screen_decision(
            pass_count=24,
            hard_family_pass_count=8,
            usage_complete=False,
            provider_error_count=0,
            deterministic_control_violation_count=0,
            writes_from_multi_tool_batches=0,
        )
        == "INCONCLUSIVE"
    )
    assert (
        _screen_decision(
            pass_count=24,
            hard_family_pass_count=8,
            usage_complete=True,
            provider_error_count=1,
            deterministic_control_violation_count=0,
            writes_from_multi_tool_batches=0,
        )
        == "INCONCLUSIVE"
    )


def test_screen_safety_failure_precedes_quality_promotion() -> None:
    decision = _screen_decision(
        pass_count=30,
        hard_family_pass_count=12,
        usage_complete=True,
        provider_error_count=0,
        deterministic_control_violation_count=1,
        writes_from_multi_tool_batches=0,
    )
    assert decision == "SAFETY_FAIL"
