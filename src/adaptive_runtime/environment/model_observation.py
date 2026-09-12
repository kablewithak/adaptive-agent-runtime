from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.domain import (
    Approval,
    ApprovalAction,
    HarbourDeskVisibleState,
    Ticket,
)


class ModelObservationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class OperationReference(ModelObservationContract):
    """Model-visible identity for an operation that can be inspected with get_operation."""

    operation_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    action: ApprovalAction


class ModelVisibleInitialObservation(ModelObservationContract):
    """Small, task-scoped initial observation for model-driven HarbourDesk runs."""

    schema_version: Literal["m0a-v1"] = "m0a-v1"
    frozen_at: datetime
    tenant_id: str = Field(min_length=1, max_length=100)
    ticket: Ticket
    approvals: tuple[Approval, ...]
    operation_references: tuple[OperationReference, ...] = ()


def build_initial_model_observation(
    *,
    state: HarbourDeskVisibleState,
    tenant_id: str,
    ticket_id: str,
) -> ModelVisibleInitialObservation:
    """Project host-visible state into the intentionally smaller model-visible boundary."""
    matching_tickets = tuple(
        ticket
        for ticket in state.tickets
        if ticket.tenant_id == tenant_id and ticket.ticket_id == ticket_id
    )
    if len(matching_tickets) != 1:
        raise ValueError("initial observation requires exactly one ticket in tenant scope")

    approvals = tuple(approval for approval in state.approvals if approval.tenant_id == tenant_id)
    operation_references = tuple(
        OperationReference(
            operation_id=operation.operation_id,
            account_id=operation.account_id,
            action=operation.action,
        )
        for operation in state.operations
        if operation.tenant_id == tenant_id
    )

    return ModelVisibleInitialObservation(
        frozen_at=state.frozen_at,
        tenant_id=tenant_id,
        ticket=matching_tickets[0],
        approvals=approvals,
        operation_references=operation_references,
    )
