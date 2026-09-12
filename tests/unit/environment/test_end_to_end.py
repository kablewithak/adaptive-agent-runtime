from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.end_to_end import (
    load_trajectory_json,
    run_scripted_environment,
)
from adaptive_runtime.environment.end_to_end_rehearsal import (
    PrivateEvaluationDataMissing,
    run_manual_end_to_end_rehearsal,
)
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore

ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = ROOT / "benchmarks" / "harbourdesk" / "business_rules_v1.json"


def test_scripted_end_to_end_rejection_path_matches_expectations() -> None:
    case_id = "hdm-009"
    state = HarbourDeskVisibleState.model_validate_json(
        (ROOT / "benchmarks" / "harbourdesk" / "dev" / case_id / "initial_state.json").read_text(
            encoding="utf-8"
        )
    )
    trajectory = load_trajectory_json(
        (
            ROOT / "benchmarks" / "harbourdesk" / "end_to_end_rehearsals" / f"{case_id}.json"
        ).read_text(encoding="utf-8")
    )

    with HarbourDeskStore.in_memory() as store:
        store.initialize(state)
        environment = HarbourDeskEnvironment(
            store=store,
            rules=HarbourDeskBusinessRules.load(RULES_PATH),
            tenant_id=trajectory.tenant_id,
            ticket_id=trajectory.ticket_id,
        )
        trace = run_scripted_environment(environment, trajectory)
        final = environment.snapshot()

    assert trace.all_steps_matched is True
    ticket = next(item for item in final.tickets if item.ticket_id == "ticket-009")
    assert ticket.status.value == "escalated"
    assert ticket.resolution_reason_code == "REQUESTER_NOT_AUTHORISED"
    assert not any(operation.effective_write for operation in final.operations)


def test_file_rehearsal_fails_closed_without_private_labels(tmp_path: Path) -> None:
    with pytest.raises(PrivateEvaluationDataMissing):
        run_manual_end_to_end_rehearsal(tmp_path)


def test_end_to_end_case_wires_independent_scorer_without_private_files() -> None:
    from adaptive_runtime.environment.end_to_end_rehearsal import run_end_to_end_case
    from adaptive_runtime.evaluation.expected import (
        ExpectedCaseOutcome,
        ExpectedDisposition,
        ExpectedTerminalPredicate,
    )

    case_id = "hdm-003"
    state = HarbourDeskVisibleState.model_validate_json(
        (ROOT / "benchmarks" / "harbourdesk" / "dev" / case_id / "initial_state.json").read_text(
            encoding="utf-8"
        )
    )
    trajectory = load_trajectory_json(
        (
            ROOT / "benchmarks" / "harbourdesk" / "end_to_end_rehearsals" / f"{case_id}.json"
        ).read_text(encoding="utf-8")
    )
    deliberately_wrong_expected = ExpectedCaseOutcome(
        case_id=case_id,
        terminal_ticket_id="ticket-003",
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.ESCALATION,
                reason_code="SYNTHETIC_NEGATIVE_CONTROL",
                expected_effective_write_count=0,
                max_effective_write_count=0,
            ),
        ),
    )

    result = run_end_to_end_case(
        initial=state,
        trajectory=trajectory,
        expected=deliberately_wrong_expected,
        rules=HarbourDeskBusinessRules.load(RULES_PATH),
    )

    assert result.trace_passed is True
    assert result.score_passed is False
    assert "disposition_mismatch" in result.scoring_failures
