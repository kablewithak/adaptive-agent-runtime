from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    HarbourDeskVisibleState,
    OperationStatus,
    TicketStatus,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import (
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


def test_fresh_idempotency_key_cannot_retry_unknown_reconciliation() -> None:
    with _store("hdm-012") as store:
        before = store.snapshot()

        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-012",
            ticket_id="ticket-012",
            call_id="call-unknown-fresh-key",
            idempotency_key="fresh-host-generated-key",
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
        assert store.snapshot() == before


def test_unknown_reconciliation_still_allows_ticket_escalation() -> None:
    with _store("hdm-012") as store:
        result = execute_write_tool(
            store,
            RULES,
            tenant_id="tenant-012",
            ticket_id="ticket-012",
            call_id="call-escalate-unknown",
            idempotency_key="fresh-ticket-update-key",
            tool=WriteToolName.UPDATE_TICKET,
            arguments={
                "ticket_id": "ticket-012",
                "expected_ticket_revision": 1,
                "status": "escalated",
                "resolution_reason_code": "OPERATION_OUTCOME_UNCERTAIN",
                "evidence_document_ids": ["policy-ops-v1"],
                "operation_ids": ["op-012-prior"],
            },
        )

        assert result.status is WriteToolStatus.OK
        assert isinstance(result.data, TicketWriteObservation)
        assert result.data.ticket.status is TicketStatus.ESCALATED
        assert result.data.ticket.operation_ids == ("op-012-prior",)
        assert result.data.ticket.evidence_document_ids == ("policy-ops-v1",)

        operations = store.snapshot().operations
        assert len(operations) == 2
        assert operations[0].operation_id == "op-012-prior"
        assert operations[0].status is OperationStatus.UNKNOWN
        assert operations[1].effective_write is False
