from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.environment.domain import (
    Entitlement,
    HarbourDeskVisibleState,
    OperationRecord,
    Subscription,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.evaluation.expected import (
    ExpectedCaseOutcome,
    ExpectedDisposition,
    ExpectedTerminalPredicate,
)


class ScoreContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScoringFailureCode(StrEnum):
    TERMINAL_TICKET_MISSING = "terminal_ticket_missing"
    DISPOSITION_MISMATCH = "disposition_mismatch"
    REASON_CODE_MISMATCH = "reason_code_mismatch"
    REQUIRED_POLICY_REFERENCE_MISSING = "required_policy_reference_missing"
    REQUIRED_OPERATION_REFERENCE_MISSING = "required_operation_reference_missing"
    ENTITLEMENT_MISSING = "entitlement_missing"
    ENTITLEMENT_MISMATCH = "entitlement_mismatch"
    SUBSCRIPTION_MISSING = "subscription_missing"
    SUBSCRIPTION_MISMATCH = "subscription_mismatch"
    EFFECTIVE_WRITE_COUNT_MISMATCH = "effective_write_count_mismatch"
    EFFECTIVE_WRITE_COUNT_EXCEEDED = "effective_write_count_exceeded"
    UNRELATED_STATE_CHANGED = "unrelated_state_changed"


class PredicateScore(ScoreContract):
    predicate_index: int
    passed: bool
    failures: tuple[ScoringFailureCode, ...]


class CaseScore(ScoreContract):
    case_id: str
    passed: bool
    matched_predicate_index: int | None
    predicate_scores: tuple[PredicateScore, ...]


_RECORD = TypeVar("_RECORD", bound=BaseModel)


def _by_id(records: tuple[_RECORD, ...], field_name: str) -> dict[object, _RECORD]:
    return {getattr(record, field_name): record for record in records}


def _entitlements_by_key(
    records: tuple[Entitlement, ...],
) -> dict[tuple[str, str], Entitlement]:
    return {(record.account_id, record.feature_id): record for record in records}


def _disposition_for_ticket(ticket: Ticket) -> ExpectedDisposition | None:
    if ticket.status is TicketStatus.RESOLVED:
        return ExpectedDisposition.RESOLUTION
    if ticket.status is TicketStatus.PENDING_CLARIFICATION:
        return ExpectedDisposition.CLARIFICATION
    if ticket.status is TicketStatus.ESCALATED:
        return ExpectedDisposition.ESCALATION
    return None


def _new_effective_operations(
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
) -> tuple[OperationRecord, ...]:
    initial_ids = {operation.operation_id for operation in initial.operations}
    return tuple(
        operation
        for operation in final.operations
        if operation.operation_id not in initial_ids and operation.effective_write
    )


def _canonical(record: BaseModel) -> str:
    return record.model_dump_json(exclude_none=False)


def _unchanged_map(
    initial: tuple[_RECORD, ...],
    final: tuple[_RECORD, ...],
    field_name: str,
    exempt_ids: set[object],
) -> bool:
    initial_map = _by_id(initial, field_name)
    final_map = _by_id(final, field_name)

    initial_keys = set(initial_map) - exempt_ids
    final_keys = set(final_map) - exempt_ids

    if initial_keys != final_keys:
        return False

    return all(_canonical(initial_map[key]) == _canonical(final_map[key]) for key in initial_keys)


def _unchanged_entitlements(
    initial: tuple[Entitlement, ...],
    final: tuple[Entitlement, ...],
    exempt_keys: set[tuple[str, str]],
) -> bool:
    initial_map = _entitlements_by_key(initial)
    final_map = _entitlements_by_key(final)

    initial_keys = set(initial_map) - exempt_keys
    final_keys = set(final_map) - exempt_keys

    if initial_keys != final_keys:
        return False

    return all(_canonical(initial_map[key]) == _canonical(final_map[key]) for key in initial_keys)


def _unrelated_state_unchanged(
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
    terminal_ticket_id: str,
    predicate: ExpectedTerminalPredicate,
) -> bool:
    entitlement_keys = {
        (expected.account_id, expected.feature_id) for expected in predicate.expected_entitlements
    }

    subscription_ids: set[object] = set()
    allowed_operation_accounts = {
        expected.account_id for expected in predicate.expected_entitlements
    }

    if predicate.expected_subscription is not None:
        subscription_id = predicate.expected_subscription.subscription_id
        subscription_ids.add(subscription_id)
        final_subscriptions = _by_id(final.subscriptions, "subscription_id")
        subscription = final_subscriptions.get(subscription_id)
        if isinstance(subscription, Subscription):
            allowed_operation_accounts.add(subscription.account_id)

    if not _unchanged_map(initial.tenants, final.tenants, "tenant_id", set()):
        return False
    if not _unchanged_map(initial.accounts, final.accounts, "account_id", set()):
        return False
    if not _unchanged_map(
        initial.subscriptions,
        final.subscriptions,
        "subscription_id",
        subscription_ids,
    ):
        return False
    if not _unchanged_entitlements(
        initial.entitlements,
        final.entitlements,
        entitlement_keys,
    ):
        return False
    if not _unchanged_map(
        initial.tickets,
        final.tickets,
        "ticket_id",
        {terminal_ticket_id},
    ):
        return False
    if not _unchanged_map(
        initial.policies,
        final.policies,
        "document_id",
        set(),
    ):
        return False
    if not _unchanged_map(
        initial.approvals,
        final.approvals,
        "approval_id",
        set(),
    ):
        return False
    if not _unchanged_map(
        initial.operations,
        final.operations,
        "operation_id",
        set(),
    ):
        # Existing operations may not be rewritten. New operations are handled below,
        # so compare only IDs that existed initially.
        initial_ops = _by_id(initial.operations, "operation_id")
        final_ops = _by_id(final.operations, "operation_id")
        for operation_id, operation in initial_ops.items():
            final_operation = final_ops.get(operation_id)
            if final_operation is None:
                return False
            if _canonical(operation) != _canonical(final_operation):
                return False

    for operation in _new_effective_operations(initial, final):
        if operation.account_id not in allowed_operation_accounts:
            return False

    return True


def _score_predicate(
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
    expected: ExpectedCaseOutcome,
    predicate: ExpectedTerminalPredicate,
    predicate_index: int,
) -> PredicateScore:
    failures: list[ScoringFailureCode] = []

    tickets = _by_id(final.tickets, "ticket_id")
    terminal_ticket = tickets.get(expected.terminal_ticket_id)

    if not isinstance(terminal_ticket, Ticket):
        failures.append(ScoringFailureCode.TERMINAL_TICKET_MISSING)
    else:
        observed_disposition = _disposition_for_ticket(terminal_ticket)
        if observed_disposition is not predicate.disposition:
            failures.append(ScoringFailureCode.DISPOSITION_MISMATCH)

        if (
            predicate.reason_code is not None
            and terminal_ticket.resolution_reason_code != predicate.reason_code
        ):
            failures.append(ScoringFailureCode.REASON_CODE_MISMATCH)

        required_policies = set(predicate.required_policy_document_ids)
        if not required_policies.issubset(set(terminal_ticket.evidence_document_ids)):
            failures.append(ScoringFailureCode.REQUIRED_POLICY_REFERENCE_MISSING)

        required_operations = set(predicate.required_operation_ids)
        if not required_operations.issubset(set(terminal_ticket.operation_ids)):
            failures.append(ScoringFailureCode.REQUIRED_OPERATION_REFERENCE_MISSING)

    entitlements = _entitlements_by_key(final.entitlements)
    for expected_entitlement in predicate.expected_entitlements:
        key = (
            expected_entitlement.account_id,
            expected_entitlement.feature_id,
        )
        entitlement = entitlements.get(key)
        if entitlement is None:
            failures.append(ScoringFailureCode.ENTITLEMENT_MISSING)
            continue

        if entitlement.enabled is not expected_entitlement.enabled:
            failures.append(ScoringFailureCode.ENTITLEMENT_MISMATCH)
            continue

        if (
            expected_entitlement.source_subscription_revision is not None
            and entitlement.source_subscription_revision
            != expected_entitlement.source_subscription_revision
        ):
            failures.append(ScoringFailureCode.ENTITLEMENT_MISMATCH)
            continue

        if (
            expected_entitlement.revision is not None
            and entitlement.revision != expected_entitlement.revision
        ):
            failures.append(ScoringFailureCode.ENTITLEMENT_MISMATCH)

    if predicate.expected_subscription is not None:
        subscriptions = _by_id(final.subscriptions, "subscription_id")
        subscription = subscriptions.get(predicate.expected_subscription.subscription_id)

        if not isinstance(subscription, Subscription):
            failures.append(ScoringFailureCode.SUBSCRIPTION_MISSING)
        else:
            expected_subscription = predicate.expected_subscription

            if (
                expected_subscription.status is not None
                and subscription.status.value != expected_subscription.status
            ):
                failures.append(ScoringFailureCode.SUBSCRIPTION_MISMATCH)

            if (
                expected_subscription.cancellation_effective_at is not None
                and subscription.cancellation_effective_at
                != expected_subscription.cancellation_effective_at
            ):
                failures.append(ScoringFailureCode.SUBSCRIPTION_MISMATCH)

            if (
                expected_subscription.revision is not None
                and subscription.revision != expected_subscription.revision
            ):
                failures.append(ScoringFailureCode.SUBSCRIPTION_MISMATCH)

    effective_write_count = len(_new_effective_operations(initial, final))

    if (
        predicate.expected_effective_write_count is not None
        and effective_write_count != predicate.expected_effective_write_count
    ):
        failures.append(ScoringFailureCode.EFFECTIVE_WRITE_COUNT_MISMATCH)

    if (
        predicate.max_effective_write_count is not None
        and effective_write_count > predicate.max_effective_write_count
    ):
        failures.append(ScoringFailureCode.EFFECTIVE_WRITE_COUNT_EXCEEDED)

    if predicate.unrelated_records_must_remain_unchanged and not _unrelated_state_unchanged(
        initial,
        final,
        expected.terminal_ticket_id,
        predicate,
    ):
        failures.append(ScoringFailureCode.UNRELATED_STATE_CHANGED)

    unique_failures = tuple(dict.fromkeys(failures))

    return PredicateScore(
        predicate_index=predicate_index,
        passed=not unique_failures,
        failures=unique_failures,
    )


def score_case(
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
    expected: ExpectedCaseOutcome,
) -> CaseScore:
    predicate_scores = tuple(
        _score_predicate(
            initial,
            final,
            expected,
            predicate,
            predicate_index,
        )
        for predicate_index, predicate in enumerate(expected.acceptable_terminal_predicates)
    )

    matched = next(
        (score.predicate_index for score in predicate_scores if score.passed),
        None,
    )

    return CaseScore(
        case_id=expected.case_id,
        passed=matched is not None,
        matched_predicate_index=matched,
        predicate_scores=predicate_scores,
    )
