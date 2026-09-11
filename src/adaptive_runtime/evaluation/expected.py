from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ExpectedDisposition(StrEnum):
    RESOLUTION = "resolution"
    CLARIFICATION = "clarification"
    ESCALATION = "escalation"


class ExpectedEntitlementState(EvaluationContract):
    account_id: str = Field(min_length=1, max_length=100)
    feature_id: str = Field(min_length=1, max_length=100)
    enabled: bool
    source_subscription_revision: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=1)


class ExpectedSubscriptionState(EvaluationContract):
    subscription_id: str = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, min_length=1, max_length=100)
    cancellation_effective_at: datetime | None = None
    revision: int | None = Field(default=None, ge=1)


class ExpectedTerminalPredicate(EvaluationContract):
    disposition: ExpectedDisposition
    reason_code: str | None = Field(default=None, min_length=1, max_length=100)
    required_policy_document_ids: tuple[str, ...] = ()
    required_operation_ids: tuple[str, ...] = ()
    expected_entitlements: tuple[ExpectedEntitlementState, ...] = ()
    expected_subscription: ExpectedSubscriptionState | None = None
    expected_effective_write_count: int | None = Field(default=None, ge=0)
    max_effective_write_count: int | None = Field(default=None, ge=0)
    unrelated_records_must_remain_unchanged: bool = True

    @model_validator(mode="after")
    def validate_write_bounds(self) -> ExpectedTerminalPredicate:
        if (
            self.expected_effective_write_count is not None
            and self.max_effective_write_count is not None
            and self.expected_effective_write_count > self.max_effective_write_count
        ):
            raise ValueError(
                "expected_effective_write_count cannot exceed max_effective_write_count"
            )
        return self


class ExpectedCaseOutcome(EvaluationContract):
    case_id: str = Field(min_length=1, max_length=100)
    terminal_ticket_id: str = Field(min_length=1, max_length=100)
    acceptable_terminal_predicates: tuple[ExpectedTerminalPredicate, ...] = Field(min_length=1)
