from __future__ import annotations

from datetime import UTC, datetime

from adaptive_runtime.environment.domain import ApprovalAction, TicketStatus
from adaptive_runtime.experiments.harbourdesk_m2b_s1 import (
    CaseModelEvidence,
    PredicateKind,
    StructuralCase,
    StructuralPredicate,
    _evaluate_predicate,
    _signature_groups,
)
from adaptive_runtime.routing.contracts import (
    RoutingGateStatus,
    RoutingObservation,
)


def _observation(
    *,
    notes: int = 0,
    approvals: int = 0,
    active: tuple[ApprovalAction, ...] = (),
    inactive: tuple[ApprovalAction, ...] = (),
    operations: int = 0,
    operation_actions: tuple[ApprovalAction, ...] = (),
) -> RoutingObservation:
    return RoutingObservation(
        ticket_status=TicketStatus.OPEN,
        note_count=notes,
        approval_count=approvals,
        active_approval_actions=active,
        inactive_approval_actions=inactive,
        operation_reference_count=operations,
        operation_reference_actions=operation_actions,
    )


def _case(
    case_id: str,
    *,
    observation: RoutingObservation,
    reference_pass: bool,
    reference_tokens: int,
    alternative_pass: bool,
    alternative_tokens: int,
    oracle_model_id: str,
) -> StructuralCase:
    return StructuralCase(
        case_id=case_id,
        observation=observation,
        oracle_model_id=oracle_model_id,
        reference=CaseModelEvidence(
            case_id=case_id,
            score_passed=reference_pass,
            inference_tokens=reference_tokens,
        ),
        alternative=CaseModelEvidence(
            case_id=case_id,
            score_passed=alternative_pass,
            inference_tokens=alternative_tokens,
        ),
    )


def test_signature_groups_detect_conflicting_oracle_choices() -> None:
    observation = _observation(notes=1)
    cases = (
        _case(
            "hdm-a",
            observation=observation,
            reference_pass=True,
            reference_tokens=10_000,
            alternative_pass=False,
            alternative_tokens=1_000,
            oracle_model_id="glm-5.1",
        ),
        _case(
            "hdm-b",
            observation=observation,
            reference_pass=False,
            reference_tokens=10_000,
            alternative_pass=False,
            alternative_tokens=1_000,
            oracle_model_id="glm-5.2",
        ),
    )

    groups = _signature_groups(cases)

    assert len(groups) == 1
    assert groups[0].mixed_oracle_choice


def test_has_notes_predicate_routes_alternative_only_when_true() -> None:
    cases = (
        _case(
            "hdm-a",
            observation=_observation(notes=0),
            reference_pass=True,
            reference_tokens=20_000,
            alternative_pass=False,
            alternative_tokens=2_000,
            oracle_model_id="glm-5.1",
        ),
        _case(
            "hdm-b",
            observation=_observation(notes=1),
            reference_pass=False,
            reference_tokens=20_000,
            alternative_pass=False,
            alternative_tokens=2_000,
            oracle_model_id="glm-5.2",
        ),
    )

    result = _evaluate_predicate(
        StructuralPredicate(kind=PredicateKind.HAS_NOTES),
        cases,
    )

    assert result.reference_case_ids == ("hdm-a",)
    assert result.alternative_case_ids == ("hdm-b",)
    assert result.verified_passes == 1


def test_predicate_evaluation_uses_frozen_gate() -> None:
    cases = tuple(
        _case(
            f"hdm-{index:03d}",
            observation=_observation(notes=1 if index > 6 else 0),
            reference_pass=index <= 6,
            reference_tokens=20_000,
            alternative_pass=False,
            alternative_tokens=1_000,
            oracle_model_id="glm-5.1" if index <= 6 else "glm-5.2",
        )
        for index in range(1, 13)
    )

    result = _evaluate_predicate(
        StructuralPredicate(kind=PredicateKind.HAS_NOTES),
        cases,
    )

    assert result.verified_passes == 6
    assert result.inference_tokens == 126_000
    assert result.quality_status is RoutingGateStatus.PASS
    assert result.efficiency_status is RoutingGateStatus.PASS
    assert result.overall_status is RoutingGateStatus.PASS


def test_action_predicate_matches_domain_enum_value() -> None:
    predicate = StructuralPredicate(
        kind=PredicateKind.HAS_ACTIVE_APPROVAL_ACTION,
        value=ApprovalAction.SCHEDULE_CANCELLATION.value,
    )
    observation = _observation(
        approvals=1,
        active=(ApprovalAction.SCHEDULE_CANCELLATION,),
    )

    assert predicate.matches(observation)


def test_test_module_has_stable_clock_import() -> None:
    assert datetime(2026, 9, 16, tzinfo=UTC).utcoffset() is not None
