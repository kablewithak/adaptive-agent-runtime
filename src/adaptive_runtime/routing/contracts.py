from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_runtime.environment.domain import ApprovalAction, TicketStatus
from adaptive_runtime.environment.model_observation import ModelVisibleInitialObservation

M2A_REFERENCE_PROFILE_NAME = "primary-openai"
M2A_REFERENCE_MODEL_ID = "glm-5.1"
M2A_ALTERNATIVE_PROFILE_NAME = "glm-5-2-openai"
M2A_ALTERNATIVE_MODEL_ID = "glm-5.2"

M2A_TOTAL_CASES = 12
M2A_MIN_VERIFIED_PASSES = 6
M2A_REFERENCE_TOKENS_PER_SUCCESS = Decimal("31572.166667")
M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS = Decimal("25257.733334")


class RoutingContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class RoutingCandidate(RoutingContract):
    profile_name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)


M2A_REFERENCE_CANDIDATE = RoutingCandidate(
    profile_name=M2A_REFERENCE_PROFILE_NAME,
    model_id=M2A_REFERENCE_MODEL_ID,
)

M2A_ALTERNATIVE_CANDIDATE = RoutingCandidate(
    profile_name=M2A_ALTERNATIVE_PROFILE_NAME,
    model_id=M2A_ALTERNATIVE_MODEL_ID,
)

M2A_ALLOWED_CANDIDATES = (
    M2A_REFERENCE_CANDIDATE,
    M2A_ALTERNATIVE_CANDIDATE,
)

_M2A_ALLOWED_CANDIDATE_PAIRS = frozenset(
    (candidate.profile_name, candidate.model_id)
    for candidate in M2A_ALLOWED_CANDIDATES
)


class RoutingDecisionReason(StrEnum):
    REFERENCE_DEFAULT = "REFERENCE_DEFAULT"
    STRUCTURAL_RULE_MATCH = "STRUCTURAL_RULE_MATCH"
    SAFETY_FALLBACK = "SAFETY_FALLBACK"


class RoutingObservation(RoutingContract):
    schema_version: Literal["m2a-routing-observation-v1"] = (
        "m2a-routing-observation-v1"
    )
    ticket_status: TicketStatus
    note_count: int = Field(ge=0)
    approval_count: int = Field(ge=0)
    active_approval_actions: tuple[ApprovalAction, ...]
    inactive_approval_actions: tuple[ApprovalAction, ...]
    operation_reference_count: int = Field(ge=0)
    operation_reference_actions: tuple[ApprovalAction, ...]


def _sorted_actions(actions: set[ApprovalAction]) -> tuple[ApprovalAction, ...]:
    return tuple(sorted(actions, key=lambda action: action.value))


def build_routing_observation(
    observation: ModelVisibleInitialObservation,
) -> RoutingObservation:
    active_actions: set[ApprovalAction] = set()
    inactive_actions: set[ApprovalAction] = set()

    for approval in observation.approvals:
        if approval.issued_at <= observation.frozen_at < approval.expires_at:
            active_actions.add(approval.permitted_action)
        else:
            inactive_actions.add(approval.permitted_action)

    operation_actions = {
        reference.action for reference in observation.operation_references
    }

    return RoutingObservation(
        ticket_status=observation.ticket.status,
        note_count=len(observation.ticket.notes),
        approval_count=len(observation.approvals),
        active_approval_actions=_sorted_actions(active_actions),
        inactive_approval_actions=_sorted_actions(inactive_actions),
        operation_reference_count=len(observation.operation_references),
        operation_reference_actions=_sorted_actions(operation_actions),
    )


class RoutingDecision(RoutingContract):
    schema_version: Literal["m2a-routing-decision-v1"] = (
        "m2a-routing-decision-v1"
    )
    selected_profile_name: str = Field(min_length=1, max_length=100)
    selected_model_id: str = Field(min_length=1, max_length=200)
    reason_code: RoutingDecisionReason
    rule_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_candidate_and_reason(self) -> RoutingDecision:
        selected = (self.selected_profile_name, self.selected_model_id)
        if selected not in _M2A_ALLOWED_CANDIDATE_PAIRS:
            raise ValueError("routing decision selected a non-M2A candidate")

        if self.reason_code in {
            RoutingDecisionReason.REFERENCE_DEFAULT,
            RoutingDecisionReason.SAFETY_FALLBACK,
        }:
            reference = (
                M2A_REFERENCE_PROFILE_NAME,
                M2A_REFERENCE_MODEL_ID,
            )
            if selected != reference:
                raise ValueError(
                    "default and safety fallback decisions must select GLM-5.1"
                )

        return self


class RoutingGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class RoutingGateInput(RoutingContract):
    total_cases: Literal[12] = 12
    verified_passes: int = Field(ge=0, le=M2A_TOTAL_CASES)
    usage_complete: bool
    observed_inference_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_usage_evidence(self) -> RoutingGateInput:
        if self.usage_complete and self.observed_inference_tokens is None:
            raise ValueError(
                "complete usage requires observed_inference_tokens"
            )
        return self


class RoutingGateEvaluation(RoutingContract):
    schema_version: Literal["m2a-routing-gate-v1"] = "m2a-routing-gate-v1"
    quality_status: RoutingGateStatus
    efficiency_status: RoutingGateStatus
    overall_status: RoutingGateStatus
    verified_passes: int
    total_cases: int
    observed_pass_rate: Decimal
    usage_complete: bool
    observed_inference_tokens: int | None
    observed_tokens_per_verified_success: Decimal | None
    minimum_verified_passes: int = M2A_MIN_VERIFIED_PASSES
    efficiency_target_tokens_per_success: Decimal = (
        M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS
    )


def evaluate_routing_gate(
    gate_input: RoutingGateInput,
) -> RoutingGateEvaluation:
    quality_status = (
        RoutingGateStatus.PASS
        if gate_input.verified_passes >= M2A_MIN_VERIFIED_PASSES
        else RoutingGateStatus.FAIL
    )

    pass_rate = Decimal(gate_input.verified_passes) / Decimal(
        gate_input.total_cases
    )

    tokens_per_success: Decimal | None = None
    efficiency_status = RoutingGateStatus.INCONCLUSIVE

    if gate_input.usage_complete and gate_input.verified_passes > 0:
        assert gate_input.observed_inference_tokens is not None
        tokens_per_success = (
            Decimal(gate_input.observed_inference_tokens)
            / Decimal(gate_input.verified_passes)
        )
        efficiency_status = (
            RoutingGateStatus.PASS
            if tokens_per_success
            <= M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS
            else RoutingGateStatus.FAIL
        )

    if (
        quality_status is RoutingGateStatus.PASS
        and efficiency_status is RoutingGateStatus.PASS
    ):
        overall_status = RoutingGateStatus.PASS
    elif (
        quality_status is RoutingGateStatus.FAIL
        or efficiency_status is RoutingGateStatus.FAIL
    ):
        overall_status = RoutingGateStatus.FAIL
    else:
        overall_status = RoutingGateStatus.INCONCLUSIVE

    return RoutingGateEvaluation(
        quality_status=quality_status,
        efficiency_status=efficiency_status,
        overall_status=overall_status,
        verified_passes=gate_input.verified_passes,
        total_cases=gate_input.total_cases,
        observed_pass_rate=pass_rate,
        usage_complete=gate_input.usage_complete,
        observed_inference_tokens=gate_input.observed_inference_tokens,
        observed_tokens_per_verified_success=tokens_per_success,
    )
