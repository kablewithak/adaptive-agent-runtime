from __future__ import annotations

from datetime import UTC, datetime

from adaptive_runtime.environment.domain import (
    Account,
    ApprovalAction,
    Entitlement,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
    PolicyDocument,
    Subscription,
    SubscriptionStatus,
    Tenant,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.evaluation.expected import (
    ExpectedCaseOutcome,
    ExpectedDisposition,
    ExpectedEntitlementState,
    ExpectedTerminalPredicate,
)
from adaptive_runtime.evaluation.scorer import (
    CaseScore,
    ScoringFailureCode,
    score_case,
)


def _initial_state() -> HarbourDeskVisibleState:
    return HarbourDeskVisibleState(
        frozen_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
        tenants=(
            Tenant(
                tenant_id="tenant-001",
                display_name="Scorer Fixture",
                active=True,
            ),
        ),
        accounts=(
            Account(
                account_id="acct-001",
                tenant_id="tenant-001",
                subscription_id="sub-001",
                authorised_contacts=("owner@example.test",),
            ),
            Account(
                account_id="acct-002",
                tenant_id="tenant-001",
                subscription_id="sub-002",
                authorised_contacts=("other@example.test",),
            ),
        ),
        subscriptions=(
            Subscription(
                subscription_id="sub-001",
                account_id="acct-001",
                plan_id="team",
                status=SubscriptionStatus.ACTIVE,
                start_at=datetime(2026, 1, 1, tzinfo=UTC),
                revision=5,
            ),
            Subscription(
                subscription_id="sub-002",
                account_id="acct-002",
                plan_id="starter",
                status=SubscriptionStatus.ACTIVE,
                start_at=datetime(2026, 1, 1, tzinfo=UTC),
                revision=2,
            ),
        ),
        entitlements=(
            Entitlement(
                account_id="acct-001",
                feature_id="exports",
                source_subscription_revision=4,
                enabled=False,
                revision=7,
            ),
            Entitlement(
                account_id="acct-002",
                feature_id="base_access",
                source_subscription_revision=2,
                enabled=True,
                revision=2,
            ),
        ),
        tickets=(
            Ticket(
                ticket_id="ticket-001",
                tenant_id="tenant-001",
                account_id="acct-001",
                requesting_contact="owner@example.test",
                initial_text="Exports are unavailable.",
                status=TicketStatus.OPEN,
                revision=1,
            ),
        ),
        policies=(
            PolicyDocument(
                document_id="policy-access-v2",
                version=2,
                valid_from=datetime(2026, 7, 1, tzinfo=UTC),
                authority="HarbourDesk Operations",
                body="Team includes exports.",
                content_hash="a" * 64,
            ),
        ),
        approvals=(),
        operations=(),
    )


def _expected_outcome() -> ExpectedCaseOutcome:
    return ExpectedCaseOutcome(
        case_id="scorer-unit-001",
        terminal_ticket_id="ticket-001",
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.RESOLUTION,
                reason_code="ENTITLEMENT_RECONCILED",
                required_policy_document_ids=("policy-access-v2",),
                expected_entitlements=(
                    ExpectedEntitlementState(
                        account_id="acct-001",
                        feature_id="exports",
                        enabled=True,
                        source_subscription_revision=5,
                        revision=8,
                    ),
                ),
                expected_effective_write_count=1,
                max_effective_write_count=1,
                unrelated_records_must_remain_unchanged=True,
            ),
        ),
    )


def _good_final(initial: HarbourDeskVisibleState) -> HarbourDeskVisibleState:
    target = initial.entitlements[0]
    updated_entitlement = target.model_copy(
        update={
            "enabled": True,
            "source_subscription_revision": 5,
            "revision": 8,
        }
    )

    ticket = initial.tickets[0]
    updated_ticket = ticket.model_copy(
        update={
            "status": TicketStatus.RESOLVED,
            "revision": 2,
            "resolution_reason_code": "ENTITLEMENT_RECONCILED",
            "evidence_document_ids": ("policy-access-v2",),
            "operation_ids": ("op-new-001",),
        }
    )

    new_operation = OperationRecord(
        operation_id="op-new-001",
        tenant_id="tenant-001",
        account_id="acct-001",
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key="idem-new-001",
        arguments_hash="1" * 64,
        status=OperationStatus.COMMITTED,
        before_revision=7,
        after_revision=8,
        effective_write=True,
    )

    return initial.model_copy(
        update={
            "entitlements": (updated_entitlement, initial.entitlements[1]),
            "tickets": (updated_ticket,),
            "operations": (new_operation,),
        }
    )


def _failure_codes(score: CaseScore) -> set[ScoringFailureCode]:
    return {failure for predicate in score.predicate_scores for failure in predicate.failures}


def test_correct_terminal_state_passes() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    score = score_case(initial, final, _expected_outcome())

    assert score.passed is True
    assert score.matched_predicate_index == 0


def test_wrong_account_mutation_is_detected() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    wrong = final.entitlements[1].model_copy(update={"enabled": False})
    mutated = final.model_copy(update={"entitlements": (final.entitlements[0], wrong)})

    score = score_case(initial, mutated, _expected_outcome())

    assert score.passed is False
    assert ScoringFailureCode.UNRELATED_STATE_CHANGED in _failure_codes(score)


def test_stale_source_revision_is_detected() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    stale = final.entitlements[0].model_copy(update={"source_subscription_revision": 4})
    mutated = final.model_copy(update={"entitlements": (stale, final.entitlements[1])})

    score = score_case(initial, mutated, _expected_outcome())

    assert score.passed is False
    assert ScoringFailureCode.ENTITLEMENT_MISMATCH in _failure_codes(score)


def test_extra_effective_write_is_detected() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    extra = OperationRecord(
        operation_id="op-new-002",
        tenant_id="tenant-001",
        account_id="acct-001",
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key="idem-new-002",
        arguments_hash="2" * 64,
        status=OperationStatus.COMMITTED,
        before_revision=8,
        after_revision=9,
        effective_write=True,
    )
    mutated = final.model_copy(update={"operations": (*final.operations, extra)})

    score = score_case(initial, mutated, _expected_outcome())
    failures = _failure_codes(score)

    assert score.passed is False
    assert ScoringFailureCode.EFFECTIVE_WRITE_COUNT_MISMATCH in failures
    assert ScoringFailureCode.EFFECTIVE_WRITE_COUNT_EXCEEDED in failures


def test_invalid_policy_citation_is_detected() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    bad_ticket = final.tickets[0].model_copy(
        update={"evidence_document_ids": ("policy-access-v1",)}
    )
    mutated = final.model_copy(update={"tickets": (bad_ticket,)})

    score = score_case(initial, mutated, _expected_outcome())

    assert score.passed is False
    assert ScoringFailureCode.REQUIRED_POLICY_REFERENCE_MISSING in _failure_codes(score)


def test_false_completion_is_detected() -> None:
    initial = _initial_state()
    final = _good_final(initial)

    mutated = final.model_copy(update={"entitlements": initial.entitlements})

    score = score_case(initial, mutated, _expected_outcome())

    assert score.passed is False
    assert ScoringFailureCode.ENTITLEMENT_MISMATCH in _failure_codes(score)
