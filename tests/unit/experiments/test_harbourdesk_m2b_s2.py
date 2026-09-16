from __future__ import annotations

from adaptive_runtime.environment.domain import TicketStatus
from adaptive_runtime.experiments.harbourdesk_m2b_s2 import (
    CaseEvidence,
    StructuralCase,
    build_signature_groups,
    evaluate_feature_ceiling,
)
from adaptive_runtime.routing.contracts import RoutingObservation


def _observation(notes: int) -> RoutingObservation:
    return RoutingObservation(
        ticket_status=TicketStatus.OPEN,
        note_count=notes,
        approval_count=0,
        active_approval_actions=(),
        inactive_approval_actions=(),
        operation_reference_count=0,
        operation_reference_actions=(),
    )


def _case(
    case_id: str,
    *,
    observation: RoutingObservation,
    reference_pass: bool,
    reference_tokens: int,
    alternative_pass: bool,
    alternative_tokens: int,
) -> StructuralCase:
    return StructuralCase(
        case_id=case_id,
        observation=observation,
        reference=CaseEvidence(
            case_id=case_id,
            score_passed=reference_pass,
            inference_tokens=reference_tokens,
        ),
        alternative=CaseEvidence(
            case_id=case_id,
            score_passed=alternative_pass,
            inference_tokens=alternative_tokens,
        ),
    )


def test_identical_observations_share_signature() -> None:
    observation = _observation(0)
    cases = (
        _case(
            "a",
            observation=observation,
            reference_pass=True,
            reference_tokens=10_000,
            alternative_pass=False,
            alternative_tokens=1_000,
        ),
        _case(
            "b",
            observation=observation,
            reference_pass=False,
            reference_tokens=10_000,
            alternative_pass=False,
            alternative_tokens=1_000,
        ),
    )
    groups = build_signature_groups(cases)
    assert len(groups) == 1
    assert groups[0].case_ids == ("a", "b")


def test_feature_ceiling_can_pass() -> None:
    cases = tuple(
        _case(
            f"hdm-{index:03d}",
            observation=_observation(0 if index <= 6 else 1),
            reference_pass=index <= 6,
            reference_tokens=20_000,
            alternative_pass=False,
            alternative_tokens=1_000,
        )
        for index in range(1, 13)
    )
    receipt = evaluate_feature_ceiling(cases)
    assert receipt.signature_group_count == 2
    assert receipt.candidate_assignment_count == 4
    assert receipt.max_verified_passes == 6
    assert receipt.feature_ceiling_feasible
    assert receipt.best_passing_assignment is not None
    assert receipt.best_passing_assignment.observed_inference_tokens == 126_000


def test_feature_ceiling_can_prove_boundary_infeasible() -> None:
    shared = _observation(0)
    cases = tuple(
        _case(
            f"hdm-{index:03d}",
            observation=shared,
            reference_pass=index <= 6,
            reference_tokens=30_000,
            alternative_pass=False,
            alternative_tokens=1_000,
        )
        for index in range(1, 13)
    )
    receipt = evaluate_feature_ceiling(cases)
    assert receipt.signature_group_count == 1
    assert receipt.candidate_assignment_count == 2
    assert receipt.max_verified_passes == 6
    assert not receipt.feature_ceiling_feasible
    assert receipt.best_passing_assignment is None
