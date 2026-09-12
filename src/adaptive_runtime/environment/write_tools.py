from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    ApprovalAction,
    Entitlement,
    OperationRecord,
    OperationStatus,
    Subscription,
    SubscriptionStatus,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.environment.sqlite_store import (
    HarbourDeskStore,
    StoreError,
    StoreIdempotencyConflict,
    StoreRevisionConflict,
)


class WriteContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class WriteToolName(StrEnum):
    RECONCILE_ENTITLEMENT = "reconcile_entitlement"
    SCHEDULE_CANCELLATION = "schedule_cancellation"
    UPDATE_TICKET = "update_ticket"


class WriteToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class WriteToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_FOUND = "not_found"
    CONTEXT_MISMATCH = "context_mismatch"
    REQUESTER_NOT_AUTHORISED = "requester_not_authorised"
    APPROVAL_NOT_FOUND = "approval_not_found"
    APPROVAL_ACTION_MISMATCH = "approval_action_mismatch"
    APPROVAL_EXPIRED = "approval_expired"
    OWNERSHIP_CONFLICT = "ownership_conflict"
    REVISION_CONFLICT = "revision_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    OPERATION_OUTCOME_UNKNOWN = "operation_outcome_unknown"
    PRIOR_OPERATION_FAILED = "prior_operation_failed"
    EFFECTIVE_DATE_INVALID = "effective_date_invalid"
    UNSUPPORTED_PLAN = "unsupported_plan"
    INVALID_REFERENCE = "invalid_reference"
    STORE_ERROR = "store_error"


class ReconcileEntitlementArgs(WriteContract):
    account_id: str = Field(min_length=1, max_length=100)
    feature_id: str = Field(min_length=1, max_length=100)
    approval_id: str = Field(min_length=1, max_length=100)
    expected_subscription_revision: int = Field(ge=1)
    expected_entitlement_revision: int = Field(ge=1)


class ScheduleCancellationArgs(WriteContract):
    account_id: str = Field(min_length=1, max_length=100)
    subscription_id: str = Field(min_length=1, max_length=100)
    approval_id: str = Field(min_length=1, max_length=100)
    expected_subscription_revision: int = Field(ge=1)
    effective_at: datetime

    @model_validator(mode="after")
    def validate_effective_at(self) -> ScheduleCancellationArgs:
        offset = self.effective_at.utcoffset()
        if self.effective_at.tzinfo is None or offset is None:
            raise ValueError("effective_at must be timezone-aware")
        if offset.total_seconds() != 0:
            raise ValueError("effective_at must be UTC")
        return self


class UpdateTicketArgs(WriteContract):
    ticket_id: str = Field(min_length=1, max_length=100)
    expected_ticket_revision: int = Field(ge=1)
    status: TicketStatus
    resolution_reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    evidence_document_ids: tuple[str, ...] = ()
    operation_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_reason(self) -> UpdateTicketArgs:
        if self.status is not TicketStatus.OPEN and self.resolution_reason_code is None:
            raise ValueError("non-open ticket status requires resolution_reason_code")
        return self


class EntitlementWriteObservation(WriteContract):
    kind: Literal["entitlement_write"] = "entitlement_write"
    entitlement: Entitlement
    operation: OperationRecord
    replayed: bool = False


class SubscriptionWriteObservation(WriteContract):
    kind: Literal["subscription_write"] = "subscription_write"
    subscription: Subscription
    operation: OperationRecord
    replayed: bool = False


class TicketWriteObservation(WriteContract):
    kind: Literal["ticket_write"] = "ticket_write"
    ticket: Ticket
    operation: OperationRecord
    replayed: bool = False


WriteToolData = Annotated[
    EntitlementWriteObservation | SubscriptionWriteObservation | TicketWriteObservation,
    Field(discriminator="kind"),
]

_DATA_ADAPTER: TypeAdapter[WriteToolData] = TypeAdapter(WriteToolData)


class WriteToolResult(WriteContract):
    call_id: str = Field(min_length=1, max_length=100)
    tool: WriteToolName
    status: WriteToolStatus
    data: WriteToolData | None = None
    error_code: WriteToolErrorCode | None = None
    message: str | None = Field(default=None, max_length=300)


def execute_write_tool(
    store: HarbourDeskStore,
    rules: HarbourDeskBusinessRules,
    tenant_id: str,
    ticket_id: str,
    call_id: str,
    idempotency_key: str,
    tool: WriteToolName,
    arguments: dict[str, object],
) -> WriteToolResult:
    try:
        if tool is WriteToolName.RECONCILE_ENTITLEMENT:
            reconcile_args = ReconcileEntitlementArgs.model_validate(arguments)
            return _reconcile_entitlement(
                store,
                rules,
                tenant_id,
                ticket_id,
                call_id,
                idempotency_key,
                reconcile_args,
            )

        if tool is WriteToolName.SCHEDULE_CANCELLATION:
            cancellation_args = ScheduleCancellationArgs.model_validate(arguments)
            return _schedule_cancellation(
                store,
                rules,
                tenant_id,
                ticket_id,
                call_id,
                idempotency_key,
                cancellation_args,
            )

        if tool is WriteToolName.UPDATE_TICKET:
            ticket_args = UpdateTicketArgs.model_validate(arguments)
            return _update_ticket(
                store,
                tenant_id,
                ticket_id,
                call_id,
                idempotency_key,
                ticket_args,
            )

        raise AssertionError(f"unhandled write tool: {tool}")  # pragma: no cover

    except ValidationError:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.INVALID_ARGUMENTS,
            "tool arguments failed schema validation",
        )


def _reconcile_entitlement(
    store: HarbourDeskStore,
    rules: HarbourDeskBusinessRules,
    tenant_id: str,
    ticket_id: str,
    call_id: str,
    idempotency_key: str,
    args: ReconcileEntitlementArgs,
) -> WriteToolResult:
    tool = WriteToolName.RECONCILE_ENTITLEMENT
    ticket = store.get_ticket(tenant_id, ticket_id)
    if ticket is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "ticket not found")

    account = store.get_account(tenant_id, args.account_id)
    if account is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "account not found")

    if ticket.account_id != account.account_id:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.CONTEXT_MISMATCH,
            "ticket and account context do not match",
        )

    if ticket.requesting_contact not in account.authorised_contacts:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REQUESTER_NOT_AUTHORISED,
            "requesting contact is not authorised for the account",
        )

    subscription = store.get_subscription(tenant_id, account.subscription_id)
    if subscription is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "subscription not found")

    if subscription.account_id != account.account_id:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.OWNERSHIP_CONFLICT,
            "subscription ownership conflicts with account reference",
        )

    entitlement = _find_entitlement(
        store,
        tenant_id,
        account.account_id,
        args.feature_id,
    )
    if entitlement is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "entitlement not found")

    arguments_hash = _arguments_hash(tool, tenant_id, ticket_id, args)
    prior = _prior_operation_result(
        store,
        tenant_id,
        ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key,
        arguments_hash,
    )
    if prior is not None:
        if isinstance(prior, WriteToolErrorCode):
            return _error(call_id, tool, prior, _prior_message(prior))
        current = _find_entitlement(
            store,
            tenant_id,
            account.account_id,
            args.feature_id,
        )
        if current is None:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.NOT_FOUND,
                "replayed entitlement not found",
            )
        return _ok(
            call_id,
            tool,
            EntitlementWriteObservation(
                entitlement=current,
                operation=prior,
                replayed=True,
            ),
        )

    if subscription.revision != args.expected_subscription_revision:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "subscription revision does not match expected revision",
        )

    if entitlement.revision != args.expected_entitlement_revision:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "entitlement revision does not match expected revision",
        )

    approval_error = _validate_approval(
        store,
        tenant_id,
        account.account_id,
        args.approval_id,
        ApprovalAction.RECONCILE_ENTITLEMENT,
    )
    if approval_error is not None:
        return _error(
            call_id,
            tool,
            approval_error,
            _approval_message(approval_error),
        )

    try:
        desired_enabled = rules.desired_entitlement_state(
            subscription.plan_id,
            entitlement.feature_id,
        )
    except KeyError:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.UNSUPPORTED_PLAN,
            "subscription plan is not present in the rule catalogue",
        )

    effective_write = (
        entitlement.enabled != desired_enabled
        or entitlement.source_subscription_revision != subscription.revision
    )
    operation = _operation(
        tenant_id=tenant_id,
        account_id=account.account_id,
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        before_revision=entitlement.revision if effective_write else None,
        after_revision=entitlement.revision + 1 if effective_write else None,
        effective_write=effective_write,
    )

    if not effective_write:
        try:
            store.append_noop_operation(operation)
        except StoreIdempotencyConflict:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.IDEMPOTENCY_CONFLICT,
                "idempotency key was concurrently reused",
            )
        return _ok(
            call_id,
            tool,
            EntitlementWriteObservation(
                entitlement=entitlement,
                operation=operation,
            ),
        )

    updated = entitlement.model_copy(
        update={
            "enabled": desired_enabled,
            "source_subscription_revision": subscription.revision,
            "revision": entitlement.revision + 1,
        }
    )
    try:
        store.replace_entitlement_with_operation(
            updated,
            entitlement.revision,
            operation,
        )
    except StoreRevisionConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "entitlement changed before commit",
        )
    except StoreIdempotencyConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.IDEMPOTENCY_CONFLICT,
            "idempotency key was concurrently reused",
        )
    except StoreError:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.STORE_ERROR,
            "store mutation failed",
        )

    return _ok(
        call_id,
        tool,
        EntitlementWriteObservation(
            entitlement=updated,
            operation=operation,
        ),
    )


def _schedule_cancellation(
    store: HarbourDeskStore,
    rules: HarbourDeskBusinessRules,
    tenant_id: str,
    ticket_id: str,
    call_id: str,
    idempotency_key: str,
    args: ScheduleCancellationArgs,
) -> WriteToolResult:
    tool = WriteToolName.SCHEDULE_CANCELLATION
    ticket = store.get_ticket(tenant_id, ticket_id)
    if ticket is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "ticket not found")

    account = store.get_account(tenant_id, args.account_id)
    if account is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "account not found")

    if ticket.account_id != account.account_id or account.subscription_id != args.subscription_id:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.CONTEXT_MISMATCH,
            "ticket, account and subscription context do not match",
        )

    if ticket.requesting_contact not in account.authorised_contacts:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REQUESTER_NOT_AUTHORISED,
            "requesting contact is not authorised for the account",
        )

    subscription = store.get_subscription(tenant_id, args.subscription_id)
    if subscription is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "subscription not found")

    if subscription.account_id != account.account_id:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.OWNERSHIP_CONFLICT,
            "subscription ownership conflicts with account reference",
        )

    arguments_hash = _arguments_hash(tool, tenant_id, ticket_id, args)
    prior = _prior_operation_result(
        store,
        tenant_id,
        ApprovalAction.SCHEDULE_CANCELLATION,
        idempotency_key,
        arguments_hash,
    )
    if prior is not None:
        if isinstance(prior, WriteToolErrorCode):
            return _error(call_id, tool, prior, _prior_message(prior))
        current = store.get_subscription(tenant_id, subscription.subscription_id)
        if current is None:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.NOT_FOUND,
                "replayed subscription not found",
            )
        return _ok(
            call_id,
            tool,
            SubscriptionWriteObservation(
                subscription=current,
                operation=prior,
                replayed=True,
            ),
        )

    if subscription.revision != args.expected_subscription_revision:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "subscription revision does not match expected revision",
        )

    approval_error = _validate_approval(
        store,
        tenant_id,
        account.account_id,
        args.approval_id,
        ApprovalAction.SCHEDULE_CANCELLATION,
    )
    if approval_error is not None:
        return _error(
            call_id,
            tool,
            approval_error,
            _approval_message(approval_error),
        )

    frozen_at = datetime.fromisoformat(store.frozen_at_iso())
    minimum_effective = rules.minimum_cancellation_effective_at(frozen_at)
    if args.effective_at < minimum_effective:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.EFFECTIVE_DATE_INVALID,
            "effective cancellation date is earlier than the structured policy minimum",
        )

    operation = _operation(
        tenant_id=tenant_id,
        account_id=account.account_id,
        action=ApprovalAction.SCHEDULE_CANCELLATION,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        before_revision=subscription.revision,
        after_revision=subscription.revision + 1,
        effective_write=True,
    )
    updated = subscription.model_copy(
        update={
            "status": SubscriptionStatus.SCHEDULED_CANCELLATION,
            "cancellation_effective_at": args.effective_at,
            "revision": subscription.revision + 1,
        }
    )

    try:
        store.replace_subscription_with_operation(
            updated,
            subscription.revision,
            operation,
        )
    except StoreRevisionConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "subscription changed before commit",
        )
    except StoreIdempotencyConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.IDEMPOTENCY_CONFLICT,
            "idempotency key was concurrently reused",
        )
    except StoreError:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.STORE_ERROR,
            "store mutation failed",
        )

    return _ok(
        call_id,
        tool,
        SubscriptionWriteObservation(
            subscription=updated,
            operation=operation,
        ),
    )


def _update_ticket(
    store: HarbourDeskStore,
    tenant_id: str,
    ticket_id: str,
    call_id: str,
    idempotency_key: str,
    args: UpdateTicketArgs,
) -> WriteToolResult:
    tool = WriteToolName.UPDATE_TICKET
    if args.ticket_id != ticket_id:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.CONTEXT_MISMATCH,
            "tool may update only the current ticket context",
        )

    ticket = store.get_ticket(tenant_id, ticket_id)
    if ticket is None:
        return _error(call_id, tool, WriteToolErrorCode.NOT_FOUND, "ticket not found")

    arguments_hash = _arguments_hash(tool, tenant_id, ticket_id, args)
    prior = _prior_operation_result(
        store,
        tenant_id,
        ApprovalAction.UPDATE_TICKET,
        idempotency_key,
        arguments_hash,
    )
    if prior is not None:
        if isinstance(prior, WriteToolErrorCode):
            return _error(call_id, tool, prior, _prior_message(prior))
        current = store.get_ticket(tenant_id, ticket_id)
        if current is None:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.NOT_FOUND,
                "replayed ticket not found",
            )
        return _ok(
            call_id,
            tool,
            TicketWriteObservation(
                ticket=current,
                operation=prior,
                replayed=True,
            ),
        )

    if ticket.revision != args.expected_ticket_revision:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "ticket revision does not match expected revision",
        )

    for document_id in args.evidence_document_ids:
        if store.read_policy(document_id) is None:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.INVALID_REFERENCE,
                "ticket evidence references an unknown policy document",
            )

    for operation_id in args.operation_ids:
        if store.get_operation(tenant_id, operation_id) is None:
            return _error(
                call_id,
                tool,
                WriteToolErrorCode.INVALID_REFERENCE,
                "ticket references an unknown operation in tenant scope",
            )

    updated = ticket.model_copy(
        update={
            "status": args.status,
            "resolution_reason_code": args.resolution_reason_code,
            "evidence_document_ids": args.evidence_document_ids,
            "operation_ids": args.operation_ids,
            "revision": ticket.revision + 1,
        }
    )
    operation = _operation(
        tenant_id=tenant_id,
        account_id=ticket.account_id,
        action=ApprovalAction.UPDATE_TICKET,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        before_revision=ticket.revision,
        after_revision=updated.revision,
        effective_write=False,
    )

    try:
        store.replace_ticket_with_operation(
            updated,
            ticket.revision,
            operation,
        )
    except StoreRevisionConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.REVISION_CONFLICT,
            "ticket changed before commit",
        )
    except StoreIdempotencyConflict:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.IDEMPOTENCY_CONFLICT,
            "idempotency key was concurrently reused",
        )
    except StoreError:
        return _error(
            call_id,
            tool,
            WriteToolErrorCode.STORE_ERROR,
            "store mutation failed",
        )

    return _ok(
        call_id,
        tool,
        TicketWriteObservation(
            ticket=updated,
            operation=operation,
        ),
    )


def _validate_approval(
    store: HarbourDeskStore,
    tenant_id: str,
    account_id: str,
    approval_id: str,
    expected_action: ApprovalAction,
) -> WriteToolErrorCode | None:
    approval = store.get_approval(tenant_id, approval_id)
    if approval is None or approval.account_id != account_id:
        return WriteToolErrorCode.APPROVAL_NOT_FOUND
    if approval.permitted_action is not expected_action:
        return WriteToolErrorCode.APPROVAL_ACTION_MISMATCH

    frozen_at = datetime.fromisoformat(store.frozen_at_iso())
    if not (approval.issued_at <= frozen_at < approval.expires_at):
        return WriteToolErrorCode.APPROVAL_EXPIRED
    return None


def _approval_message(code: WriteToolErrorCode) -> str:
    messages = {
        WriteToolErrorCode.APPROVAL_NOT_FOUND: "applicable approval not found in account scope",
        WriteToolErrorCode.APPROVAL_ACTION_MISMATCH: "approval does not permit this action",
        WriteToolErrorCode.APPROVAL_EXPIRED: "approval is not valid at the frozen case time",
    }
    return messages[code]


def _prior_operation_result(
    store: HarbourDeskStore,
    tenant_id: str,
    action: ApprovalAction,
    idempotency_key: str,
    arguments_hash: str,
) -> OperationRecord | WriteToolErrorCode | None:
    prior = store.get_operation_by_idempotency(tenant_id, action, idempotency_key)
    if prior is None:
        return None
    if prior.status is OperationStatus.UNKNOWN:
        return WriteToolErrorCode.OPERATION_OUTCOME_UNKNOWN
    if prior.arguments_hash != arguments_hash:
        return WriteToolErrorCode.IDEMPOTENCY_CONFLICT
    if prior.status is OperationStatus.FAILED:
        return WriteToolErrorCode.PRIOR_OPERATION_FAILED
    return prior


def _prior_message(code: WriteToolErrorCode) -> str:
    messages = {
        WriteToolErrorCode.OPERATION_OUTCOME_UNKNOWN: (
            "prior operation outcome is unknown; blind retry is blocked"
        ),
        WriteToolErrorCode.IDEMPOTENCY_CONFLICT: (
            "idempotency key was reused for different arguments"
        ),
        WriteToolErrorCode.PRIOR_OPERATION_FAILED: (
            "prior operation with this idempotency key failed"
        ),
    }
    return messages[code]


def _arguments_hash(
    tool: WriteToolName,
    tenant_id: str,
    ticket_id: str,
    args: WriteContract,
) -> str:
    payload = {
        "tool": tool.value,
        "tenant_id": tenant_id,
        "ticket_id": ticket_id,
        "arguments": args.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _operation(
    *,
    tenant_id: str,
    account_id: str,
    action: ApprovalAction,
    idempotency_key: str,
    arguments_hash: str,
    before_revision: int | None,
    after_revision: int | None,
    effective_write: bool,
) -> OperationRecord:
    operation_seed = f"{tenant_id}|{action.value}|{idempotency_key}"
    operation_id = "op-" + hashlib.sha256(operation_seed.encode("utf-8")).hexdigest()[:24]
    return OperationRecord(
        operation_id=operation_id,
        tenant_id=tenant_id,
        account_id=account_id,
        action=action,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        status=OperationStatus.COMMITTED,
        before_revision=before_revision,
        after_revision=after_revision,
        effective_write=effective_write,
    )


def _find_entitlement(
    store: HarbourDeskStore,
    tenant_id: str,
    account_id: str,
    feature_id: str,
) -> Entitlement | None:
    entitlements = store.get_entitlements(tenant_id, account_id)
    if entitlements is None:
        return None
    return next((item for item in entitlements if item.feature_id == feature_id), None)


def _ok(
    call_id: str,
    tool: WriteToolName,
    data: WriteToolData,
) -> WriteToolResult:
    return WriteToolResult(
        call_id=call_id,
        tool=tool,
        status=WriteToolStatus.OK,
        data=_DATA_ADAPTER.validate_python(data),
    )


def _error(
    call_id: str,
    tool: WriteToolName,
    error_code: WriteToolErrorCode,
    message: str,
) -> WriteToolResult:
    return WriteToolResult(
        call_id=call_id,
        tool=tool,
        status=WriteToolStatus.ERROR,
        error_code=error_code,
        message=message,
    )
