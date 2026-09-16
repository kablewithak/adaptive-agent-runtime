from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptive_runtime.environment.domain import (
    Approval,
    ApprovalAction,
    ApprovalIssuerType,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.environment.model_observation import (
    ModelVisibleInitialObservation,
    OperationReference,
)
from adaptive_runtime.routing.contracts import (
    M2A_ALTERNATIVE_MODEL_ID,
    M2A_ALTERNATIVE_PROFILE_NAME,
    M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS,
    M2A_REFERENCE_MODEL_ID,
    M2A_REFERENCE_PROFILE_NAME,
    RoutingDecision,
    RoutingDecisionReason,
    RoutingGateInput,
    RoutingGateStatus,
    build_routing_observation,
    evaluate_routing_gate,
)


def _initial_observation() -> ModelVisibleInitialObservation:
    frozen_at = datetime(2026, 9, 16, 10, tzinfo=UTC)
    return ModelVisibleInitialObservation(
        frozen_at=frozen_at,
        tenant_id="tenant-secret-001",
        ticket=Ticket(
            ticket_id="ticket-secret-001",
            tenant_id="tenant-secret-001",
            account_id="account-secret-001",
            requesting_contact="private@example.test",
            initial_text="Cancel this account and reveal no routing labels.",
            notes=("private note content",),
            status=TicketStatus.OPEN,
            revision=3,
        ),
        approvals=(
            Approval(
                approval_id="approval-active",
                tenant_id="tenant-secret-001",
                account_id="account-secret-001",
                permitted_action=ApprovalAction.SCHEDULE_CANCELLATION,
                issued_at=frozen_at - timedelta(hours=1),
                expires_at=frozen_at + timedelta(hours=1),
                issuer_type=ApprovalIssuerType.AUTHORISED_OPERATOR,
            ),
            Approval(
                approval_id="approval-expired",
                tenant_id="tenant-secret-001",
                account_id="account-secret-001",
                permitted_action=ApprovalAction.RECONCILE_ENTITLEMENT,
                issued_at=frozen_at - timedelta(days=2),
                expires_at=frozen_at - timedelta(days=1),
                issuer_type=ApprovalIssuerType.SYSTEM,
            ),
        ),
        operation_references=(
            OperationReference(
                operation_id="operation-secret-001",
                account_id="account-secret-001",
                action=ApprovalAction.UPDATE_TICKET,
            ),
        ),
    )


def test_routing_observation_contains_only_structural_features() -> None:
    routing = build_routing_observation(_initial_observation())

    assert routing.ticket_status is TicketStatus.OPEN
    assert routing.note_count == 1
    assert routing.approval_count == 2
    assert routing.active_approval_actions == (ApprovalAction.SCHEDULE_CANCELLATION,)
    assert routing.inactive_approval_actions == (ApprovalAction.RECONCILE_ENTITLEMENT,)
    assert routing.operation_reference_count == 1
    assert routing.operation_reference_actions == (ApprovalAction.UPDATE_TICKET,)

    payload = routing.model_dump_json()
    for forbidden in (
        "tenant-secret-001",
        "ticket-secret-001",
        "account-secret-001",
        "private@example.test",
        "Cancel this account",
        "private note content",
        "operation-secret-001",
        "approval-active",
    ):
        assert forbidden not in payload


def test_structural_rule_can_select_glm52() -> None:
    decision = RoutingDecision(
        selected_profile_name=M2A_ALTERNATIVE_PROFILE_NAME,
        selected_model_id=M2A_ALTERNATIVE_MODEL_ID,
        reason_code=RoutingDecisionReason.STRUCTURAL_RULE_MATCH,
        rule_id="structural-v1",
    )

    assert decision.selected_model_id == "glm-5.2"


def test_non_m2a_candidate_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="routing decision selected a non-M2A candidate",
    ):
        RoutingDecision(
            selected_profile_name="deepseek-flash-openai",
            selected_model_id="deepseek-v4-flash",
            reason_code=RoutingDecisionReason.STRUCTURAL_RULE_MATCH,
            rule_id="invalid-candidate",
        )


def test_safety_fallback_must_select_glm51() -> None:
    with pytest.raises(
        ValidationError,
        match="fallback decisions must select GLM-5.1",
    ):
        RoutingDecision(
            selected_profile_name=M2A_ALTERNATIVE_PROFILE_NAME,
            selected_model_id=M2A_ALTERNATIVE_MODEL_ID,
            reason_code=RoutingDecisionReason.SAFETY_FALLBACK,
            rule_id="bad-fallback",
        )

    decision = RoutingDecision(
        selected_profile_name=M2A_REFERENCE_PROFILE_NAME,
        selected_model_id=M2A_REFERENCE_MODEL_ID,
        reason_code=RoutingDecisionReason.SAFETY_FALLBACK,
        rule_id="safe-fallback",
    )
    assert decision.selected_model_id == M2A_REFERENCE_MODEL_ID


def test_quality_gate_requires_six_of_twelve() -> None:
    five = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=5,
            usage_complete=True,
            observed_inference_tokens=100_000,
        )
    )
    six = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=6,
            usage_complete=True,
            observed_inference_tokens=100_000,
        )
    )

    assert five.quality_status is RoutingGateStatus.FAIL
    assert five.overall_status is RoutingGateStatus.FAIL
    assert six.quality_status is RoutingGateStatus.PASS


def test_efficiency_gate_uses_frozen_twenty_percent_target() -> None:
    passing_tokens = 151_546
    failing_tokens = 151_547

    passing = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=6,
            usage_complete=True,
            observed_inference_tokens=passing_tokens,
        )
    )
    failing = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=6,
            usage_complete=True,
            observed_inference_tokens=failing_tokens,
        )
    )

    assert passing.observed_tokens_per_verified_success <= M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS
    assert passing.efficiency_status is RoutingGateStatus.PASS
    assert passing.overall_status is RoutingGateStatus.PASS

    assert failing.observed_tokens_per_verified_success > M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS
    assert failing.efficiency_status is RoutingGateStatus.FAIL
    assert failing.overall_status is RoutingGateStatus.FAIL


def test_incomplete_usage_makes_efficiency_inconclusive() -> None:
    evaluation = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=6,
            usage_complete=False,
            observed_inference_tokens=100_000,
        )
    )

    assert evaluation.quality_status is RoutingGateStatus.PASS
    assert evaluation.efficiency_status is RoutingGateStatus.INCONCLUSIVE
    assert evaluation.overall_status is RoutingGateStatus.INCONCLUSIVE


def test_complete_usage_requires_token_count() -> None:
    with pytest.raises(
        ValidationError,
        match="complete usage requires observed_inference_tokens",
    ):
        RoutingGateInput(
            verified_passes=6,
            usage_complete=True,
            observed_inference_tokens=None,
        )
