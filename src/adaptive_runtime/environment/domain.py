from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _require_utc(value: datetime, field_name: str) -> None:
    offset = value.utcoffset()

    if value.tzinfo is None or offset is None:
        raise ValueError(f"{field_name} must be timezone-aware")

    if offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be UTC")


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    SCHEDULED_CANCELLATION = "scheduled_cancellation"
    CANCELED = "canceled"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING_CLARIFICATION = "pending_clarification"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class ApprovalAction(StrEnum):
    RECONCILE_ENTITLEMENT = "reconcile_entitlement"
    SCHEDULE_CANCELLATION = "schedule_cancellation"


class ApprovalIssuerType(StrEnum):
    SYSTEM = "system"
    AUTHORISED_OPERATOR = "authorised_operator"


class OperationStatus(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Tenant(DomainContract):
    tenant_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    active: bool


class Account(DomainContract):
    account_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    subscription_id: str = Field(min_length=1, max_length=100)
    authorised_contacts: tuple[str, ...] = Field(min_length=1)


class Subscription(DomainContract):
    subscription_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    plan_id: str = Field(min_length=1, max_length=100)
    status: SubscriptionStatus
    start_at: datetime
    end_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_dates(self) -> Subscription:
        _require_utc(self.start_at, "start_at")

        if self.end_at is not None:
            _require_utc(self.end_at, "end_at")
            if self.end_at <= self.start_at:
                raise ValueError("end_at must be after start_at")

        if self.cancellation_effective_at is not None:
            _require_utc(
                self.cancellation_effective_at,
                "cancellation_effective_at",
            )
            if self.cancellation_effective_at < self.start_at:
                raise ValueError("cancellation_effective_at cannot be before start_at")

        if (
            self.status is SubscriptionStatus.SCHEDULED_CANCELLATION
            and self.cancellation_effective_at is None
        ):
            raise ValueError("scheduled cancellation requires cancellation_effective_at")

        return self


class Entitlement(DomainContract):
    account_id: str = Field(min_length=1, max_length=100)
    feature_id: str = Field(min_length=1, max_length=100)
    source_subscription_revision: int = Field(ge=1)
    enabled: bool
    revision: int = Field(ge=1)


class Ticket(DomainContract):
    ticket_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    requesting_contact: str = Field(min_length=1, max_length=200)
    initial_text: str = Field(min_length=1, max_length=10_000)
    notes: tuple[str, ...] = ()
    status: TicketStatus
    revision: int = Field(ge=1)
    resolution_reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    evidence_document_ids: tuple[str, ...] = ()
    operation_ids: tuple[str, ...] = ()


class PolicyDocument(DomainContract):
    document_id: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    valid_from: datetime
    valid_to: datetime | None = None
    authority: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_validity_window(self) -> PolicyDocument:
        _require_utc(self.valid_from, "valid_from")

        if self.valid_to is not None:
            _require_utc(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be after valid_from")

        return self


class Approval(DomainContract):
    approval_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    permitted_action: ApprovalAction
    issued_at: datetime
    expires_at: datetime
    issuer_type: ApprovalIssuerType

    @model_validator(mode="after")
    def validate_approval_window(self) -> Approval:
        _require_utc(self.issued_at, "issued_at")
        _require_utc(self.expires_at, "expires_at")

        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")

        return self


class OperationRecord(DomainContract):
    operation_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    action: ApprovalAction
    idempotency_key: str = Field(min_length=1, max_length=200)
    arguments_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: OperationStatus
    before_revision: int | None = Field(default=None, ge=1)
    after_revision: int | None = Field(default=None, ge=1)
    effective_write: bool = False

    @model_validator(mode="after")
    def validate_effective_write(self) -> OperationRecord:
        if self.effective_write and self.status is not OperationStatus.COMMITTED:
            raise ValueError("effective_write requires committed status")

        if self.effective_write and (self.before_revision is None or self.after_revision is None):
            raise ValueError("effective_write requires before_revision and after_revision")

        if (
            self.before_revision is not None
            and self.after_revision is not None
            and self.after_revision <= self.before_revision
        ):
            raise ValueError("after_revision must exceed before_revision")

        return self


class HarbourDeskVisibleState(DomainContract):
    frozen_at: datetime
    tenants: tuple[Tenant, ...]
    accounts: tuple[Account, ...]
    subscriptions: tuple[Subscription, ...]
    entitlements: tuple[Entitlement, ...]
    tickets: tuple[Ticket, ...]
    policies: tuple[PolicyDocument, ...]
    approvals: tuple[Approval, ...]
    operations: tuple[OperationRecord, ...] = ()

    @model_validator(mode="after")
    def validate_frozen_clock(self) -> HarbourDeskVisibleState:
        _require_utc(self.frozen_at, "frozen_at")
        return self
