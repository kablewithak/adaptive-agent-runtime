from __future__ import annotations

from datetime import datetime
from pathlib import Path

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import (
    EntitlementWriteObservation,
    SubscriptionWriteObservation,
    TicketWriteObservation,
    WriteToolErrorCode,
    WriteToolName,
    WriteToolStatus,
    execute_write_tool,
)

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = ROOT / "benchmarks" / "harbourdesk"
RULES = HarbourDeskBusinessRules.load(BENCHMARK_ROOT / "business_rules_v1.json")


def _store(case_id: str) -> HarbourDeskStore:
    state = HarbourDeskVisibleState.model_validate_json(
        (BENCHMARK_ROOT / "dev" / case_id / "initial_state.json").read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    return store


def test_reconcile_entitlement_commits_expected_state() -> None:
    with _store("hdm-001") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="call-001",
            idempotency_key="idem-reconcile-001",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-001",
                "feature_id": "exports",
                "approval_id": "approval-001",
                "expected_subscription_revision": 5,
                "expected_entitlement_revision": 7,
            },
        )

        assert result.status is WriteToolStatus.OK
        assert isinstance(result.data, EntitlementWriteObservation)
        assert result.data.entitlement.enabled is True
        assert result.data.entitlement.source_subscription_revision == 5
        assert result.data.entitlement.revision == 8
        assert result.data.operation.effective_write is True


def test_exact_idempotent_replay_does_not_duplicate_write() -> None:
    with _store("hdm-001") as store:
        kwargs = {
            "store": store,
            "rules": RULES,
            "tenant_id": "tenant-001",
            "ticket_id": "ticket-001",
            "idempotency_key": "idem-reconcile-replay",
            "tool": WriteToolName.RECONCILE_ENTITLEMENT,
            "arguments": {
                "account_id": "acct-001",
                "feature_id": "exports",
                "approval_id": "approval-001",
                "expected_subscription_revision": 5,
                "expected_entitlement_revision": 7,
            },
        }

        first = execute_write_tool(call_id="call-first", **kwargs)
        second = execute_write_tool(call_id="call-second", **kwargs)

        assert first.status is WriteToolStatus.OK
        assert second.status is WriteToolStatus.OK
        assert isinstance(second.data, EntitlementWriteObservation)
        assert second.data.replayed is True
        assert len(store.snapshot().operations) == 1
        assert store.snapshot().entitlements[0].revision == 8


def test_stale_revision_is_rejected_without_write() -> None:
    with _store("hdm-001") as store:
        before = store.snapshot()

        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="call-stale",
            idempotency_key="idem-stale",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-001",
                "feature_id": "exports",
                "approval_id": "approval-001",
                "expected_subscription_revision": 4,
                "expected_entitlement_revision": 7,
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.REVISION_CONFLICT
        assert store.snapshot() == before


def test_unauthorised_requester_is_rejected() -> None:
    with _store("hdm-009") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-009",
            ticket_id="ticket-009",
            call_id="call-auth",
            idempotency_key="idem-auth",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-009",
                "feature_id": "exports",
                "approval_id": "approval-009",
                "expected_subscription_revision": 3,
                "expected_entitlement_revision": 2,
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.REQUESTER_NOT_AUTHORISED
        assert len(store.snapshot().operations) == 0


def test_expired_approval_is_rejected() -> None:
    with _store("hdm-010") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-010",
            ticket_id="ticket-010",
            call_id="call-expired",
            idempotency_key="idem-expired",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-010",
                "feature_id": "admin_controls",
                "approval_id": "approval-010",
                "expected_subscription_revision": 5,
                "expected_entitlement_revision": 3,
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.APPROVAL_EXPIRED


def test_ownership_conflict_is_rejected() -> None:
    with _store("hdm-008") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-008",
            ticket_id="ticket-008",
            call_id="call-owner",
            idempotency_key="idem-owner",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-008",
                "feature_id": "admin_controls",
                "approval_id": "approval-008",
                "expected_subscription_revision": 4,
                "expected_entitlement_revision": 2,
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.OWNERSHIP_CONFLICT


def test_cancellation_enforces_structured_minimum_date() -> None:
    with _store("hdm-006") as store:
        too_early = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-006",
            ticket_id="ticket-006",
            call_id="call-cancel-early",
            idempotency_key="idem-cancel-early",
            tool=WriteToolName.SCHEDULE_CANCELLATION,
            arguments={
                "account_id": "acct-006",
                "subscription_id": "sub-006",
                "approval_id": "approval-006",
                "expected_subscription_revision": 9,
                "effective_at": "2026-09-17T12:00:00Z",
            },
        )

        assert too_early.status is WriteToolStatus.ERROR
        assert too_early.error_code is WriteToolErrorCode.EFFECTIVE_DATE_INVALID

        accepted = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-006",
            ticket_id="ticket-006",
            call_id="call-cancel-ok",
            idempotency_key="idem-cancel-ok",
            tool=WriteToolName.SCHEDULE_CANCELLATION,
            arguments={
                "account_id": "acct-006",
                "subscription_id": "sub-006",
                "approval_id": "approval-006",
                "expected_subscription_revision": 9,
                "effective_at": "2026-09-18T12:00:00Z",
            },
        )

        assert accepted.status is WriteToolStatus.OK
        assert isinstance(accepted.data, SubscriptionWriteObservation)
        assert accepted.data.subscription.revision == 10
        assert accepted.data.subscription.cancellation_effective_at == datetime.fromisoformat(
            "2026-09-18T12:00:00+00:00"
        )


def test_unknown_prior_operation_blocks_blind_retry() -> None:
    with _store("hdm-012") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-012",
            ticket_id="ticket-012",
            call_id="call-unknown",
            idempotency_key="idem-case-012-prior",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-012",
                "feature_id": "exports",
                "approval_id": "approval-012",
                "expected_subscription_revision": 6,
                "expected_entitlement_revision": 5,
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.OPERATION_OUTCOME_UNKNOWN
        assert len(store.snapshot().operations) == 1


def test_update_ticket_is_revision_guarded_and_idempotent() -> None:
    with _store("hdm-003") as store:
        kwargs = {
            "store": store,
            "rules": RULES,
            "tenant_id": "tenant-003",
            "ticket_id": "ticket-003",
            "idempotency_key": "idem-ticket-003",
            "tool": WriteToolName.UPDATE_TICKET,
            "arguments": {
                "ticket_id": "ticket-003",
                "expected_ticket_revision": 1,
                "status": "pending_clarification",
                "resolution_reason_code": "ACCOUNT_OR_FEATURE_AMBIGUOUS",
                "evidence_document_ids": [],
                "operation_ids": [],
            },
        }

        first = execute_write_tool(call_id="call-ticket-first", **kwargs)
        second = execute_write_tool(call_id="call-ticket-second", **kwargs)

        assert first.status is WriteToolStatus.OK
        assert second.status is WriteToolStatus.OK
        assert isinstance(first.data, TicketWriteObservation)
        assert isinstance(second.data, TicketWriteObservation)
        assert first.data.ticket.revision == 2
        assert first.data.operation.effective_write is False
        assert second.data.replayed is True
        assert len(store.snapshot().operations) == 1
