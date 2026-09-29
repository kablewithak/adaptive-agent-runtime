from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r5_analysis import _failure_signature
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5ReferenceCaseReceipt,
)
from adaptive_runtime.runtime.harbourdesk_live import LiveStopCategory


def _case(
    *,
    terminal: bool,
    passed: bool,
    failures: tuple[str, ...] = (),
    stop: LiveStopCategory = LiveStopCategory.TICKET_TERMINAL,
) -> R5ReferenceCaseReceipt:
    return R5ReferenceCaseReceipt(
        case_id="hdb-001",
        family="F4",
        template_id="f4-dev-01",
        task_ref="test",
        ticket_id="ticket",
        run_id="run-hdb-001",
        model_id="glm-5.2",
        stop_category=stop,
        terminal_reached=terminal,
        attempt_count=1,
        tool_action_count=1,
        usage_complete=True,
        observed_input_tokens=100,
        observed_completion_tokens=20,
        observed_reasoning_tokens=0,
        observed_cached_input_tokens=0,
        observed_provider_latency_ms=10,
        score_passed=passed,
        matched_predicate_index=0 if passed else None,
        scoring_failures=failures,
        accepted_multi_read_batch_count=0,
        rejected_multi_tool_batch_count=0,
        deterministic_control_violation_count=0,
        realized_write_from_multi_tool_batch_count=0,
        final_state_sha256="a" * 64,
        trace_sha256="b" * 64,
    )


def test_terminal_failure_signature() -> None:
    case = _case(
        terminal=True,
        passed=False,
        failures=("reason_code_mismatch", "required_policy_reference_missing"),
    )
    assert _failure_signature(case) == (
        "terminal:reason_code_mismatch+required_policy_reference_missing"
    )


def test_nonterminal_failure_signature() -> None:
    case = _case(
        terminal=False,
        passed=False,
        stop=LiveStopCategory.MODEL_TEXT_WITHOUT_TERMINAL,
    )
    assert _failure_signature(case) == "nonterminal:model_text_without_terminal"


def test_pass_signature() -> None:
    assert _failure_signature(_case(terminal=True, passed=True)) == "PASS"
