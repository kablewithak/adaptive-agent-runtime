from __future__ import annotations

import pytest
from pydantic import ValidationError

from adaptive_runtime.environment.read_tools import ReadToolName
from adaptive_runtime.experiments.harbourdesk_m3a import (
    M3A_CASE_IDS,
    M3CGateStatus,
    M3CInterventionMetrics,
    evaluate_m3c_gate,
)
from adaptive_runtime.runtime.multi_tool_contract import (
    M3A_POLICY,
    M3A_REALIZABLE_READ_TOOLS,
    MultiToolRealizationMode,
)


def _metrics(
    *,
    passes: tuple[str, ...],
    incompatibility_stops: int,
    control_violations: int = 0,
    realized_batch_writes: int = 0,
    usage_complete: bool = True,
) -> M3CInterventionMetrics:
    return M3CInterventionMetrics(
        case_ids=M3A_CASE_IDS,
        verified_pass_case_ids=passes,
        multi_tool_incompatibility_stop_count=incompatibility_stops,
        deterministic_control_violation_count=control_violations,
        realized_write_from_multi_tool_batch_count=realized_batch_writes,
        usage_complete=usage_complete,
    )


def test_m3a_policy_is_read_only_sequential_and_bounded() -> None:
    assert M3A_POLICY.mode is MultiToolRealizationMode.READ_ONLY_SEQUENTIAL
    assert M3A_POLICY.require_full_preflight
    assert M3A_POLICY.preserve_provider_order
    assert not M3A_POLICY.allow_write_calls
    assert not M3A_POLICY.allow_parallel_execution
    assert not M3A_POLICY.allow_model_retry
    assert not M3A_POLICY.allow_model_switch
    assert not M3A_POLICY.allow_provider_retry
    assert M3A_POLICY.bound_by_remaining_tool_action_budget
    assert M3A_POLICY.validate_deadline_before_each_realized_action
    assert set(M3A_REALIZABLE_READ_TOOLS) == set(ReadToolName)


def test_m3c_pass_requires_improvement_and_preserved_baseline_passes() -> None:
    result = evaluate_m3c_gate(
        _metrics(
            passes=("hdm-001", "hdm-004", "hdm-007"),
            incompatibility_stops=7,
        )
    )

    assert result.safety_status is M3CGateStatus.PASS
    assert result.baseline_pass_preservation_status is M3CGateStatus.PASS
    assert result.quality_status is M3CGateStatus.PASS
    assert result.compatibility_status is M3CGateStatus.PASS
    assert result.usage_status is M3CGateStatus.PASS
    assert result.overall_status is M3CGateStatus.PASS


def test_m3c_fails_if_existing_glm52_pass_regresses() -> None:
    result = evaluate_m3c_gate(
        _metrics(
            passes=("hdm-001", "hdm-007", "hdm-008"),
            incompatibility_stops=6,
        )
    )

    assert result.baseline_pass_preservation_status is M3CGateStatus.FAIL
    assert result.overall_status is M3CGateStatus.FAIL


def test_m3c_fails_if_multi_tool_compatibility_does_not_improve() -> None:
    result = evaluate_m3c_gate(
        _metrics(
            passes=("hdm-001", "hdm-004", "hdm-007"),
            incompatibility_stops=8,
        )
    )

    assert result.compatibility_status is M3CGateStatus.FAIL
    assert result.overall_status is M3CGateStatus.FAIL


@pytest.mark.parametrize(
    ("control_violations", "realized_batch_writes"),
    ((1, 0), (0, 1)),
)
def test_m3c_fails_on_safety_violation(
    control_violations: int,
    realized_batch_writes: int,
) -> None:
    result = evaluate_m3c_gate(
        _metrics(
            passes=("hdm-001", "hdm-004", "hdm-007"),
            incompatibility_stops=7,
            control_violations=control_violations,
            realized_batch_writes=realized_batch_writes,
        )
    )

    assert result.safety_status is M3CGateStatus.FAIL
    assert result.overall_status is M3CGateStatus.FAIL


def test_m3c_is_inconclusive_when_only_usage_evidence_is_missing() -> None:
    result = evaluate_m3c_gate(
        _metrics(
            passes=("hdm-001", "hdm-004", "hdm-007"),
            incompatibility_stops=7,
            usage_complete=False,
        )
    )

    assert result.usage_status is M3CGateStatus.INCONCLUSIVE
    assert result.overall_status is M3CGateStatus.INCONCLUSIVE


def test_m3c_rejects_noncanonical_case_order() -> None:
    with pytest.raises(ValidationError, match="frozen hdm-001"):
        M3CInterventionMetrics(
            case_ids=tuple(reversed(M3A_CASE_IDS)),
            verified_pass_case_ids=("hdm-001",),
            multi_tool_incompatibility_stop_count=7,
            deterministic_control_violation_count=0,
            realized_write_from_multi_tool_batch_count=0,
            usage_complete=True,
        )
