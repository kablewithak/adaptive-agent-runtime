from __future__ import annotations

import json
from pathlib import Path

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    HarbourDeskVisibleState,
    TicketResolutionReasonCode,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import (
    WriteToolErrorCode,
    WriteToolName,
    WriteToolStatus,
    execute_write_tool,
)
from adaptive_runtime.runtime.harbourdesk_live import harbourdesk_tool_definitions

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = ROOT / "benchmarks" / "harbourdesk"
RULES = HarbourDeskBusinessRules.load(BENCHMARK_ROOT / "business_rules_v1.json")


def _store() -> HarbourDeskStore:
    state = HarbourDeskVisibleState.model_validate_json(
        (BENCHMARK_ROOT / "dev" / "hdm-001" / "initial_state.json").read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    return store


def test_business_rules_use_canonical_reason_enum() -> None:
    observed = {item.value for item in RULES.terminal_reason_codes}
    expected = {item.value for item in TicketResolutionReasonCode}
    assert observed == expected


def test_update_ticket_tool_schema_exposes_canonical_reason_codes() -> None:
    definitions = {tool.function.name: tool for tool in harbourdesk_tool_definitions()}
    schema = definitions[WriteToolName.UPDATE_TICKET.value].function.parameters
    encoded = json.dumps(schema, sort_keys=True)

    for reason_code in TicketResolutionReasonCode:
        assert reason_code.value in encoded

    assert "entitlement_reconciled" not in encoded


def test_lowercase_reason_code_is_rejected_without_mutation() -> None:
    with _store() as store:
        before = store.snapshot()

        result = execute_write_tool(
            store=store,
            rules=RULES,
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="call-lowercase-reason",
            idempotency_key="idem-lowercase-reason",
            tool=WriteToolName.UPDATE_TICKET,
            arguments={
                "ticket_id": "ticket-001",
                "expected_ticket_revision": 1,
                "status": "resolved",
                "resolution_reason_code": "entitlement_reconciled",
                "evidence_document_ids": [],
                "operation_ids": [],
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.INVALID_ARGUMENTS
        assert store.snapshot() == before


def test_canonical_reason_code_is_stored_as_domain_enum() -> None:
    with _store() as store:
        result = execute_write_tool(
            store=store,
            rules=RULES,
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="call-canonical-reason",
            idempotency_key="idem-canonical-reason",
            tool=WriteToolName.UPDATE_TICKET,
            arguments={
                "ticket_id": "ticket-001",
                "expected_ticket_revision": 1,
                "status": "escalated",
                "resolution_reason_code": "OPERATION_OUTCOME_UNCERTAIN",
                "evidence_document_ids": [],
                "operation_ids": [],
            },
        )

        assert result.status is WriteToolStatus.OK
        ticket = store.get_ticket("tenant-001", "ticket-001")
        assert ticket is not None
        assert (
            ticket.resolution_reason_code is TicketResolutionReasonCode.OPERATION_OUTCOME_UNCERTAIN
        )


def test_active_rules_can_restrict_valid_domain_reason_codes() -> None:
    restricted_rules = RULES.model_copy(
        update={"terminal_reason_codes": (TicketResolutionReasonCode.OPERATION_OUTCOME_UNCERTAIN,)}
    )

    with _store() as store:
        before = store.snapshot()

        result = execute_write_tool(
            store=store,
            rules=restricted_rules,
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="call-disabled-reason",
            idempotency_key="idem-disabled-reason",
            tool=WriteToolName.UPDATE_TICKET,
            arguments={
                "ticket_id": "ticket-001",
                "expected_ticket_revision": 1,
                "status": "resolved",
                "resolution_reason_code": "ENTITLEMENT_RECONCILED",
                "evidence_document_ids": [],
                "operation_ids": [],
            },
        )

        assert result.status is WriteToolStatus.ERROR
        assert result.error_code is WriteToolErrorCode.INVALID_ARGUMENTS
        assert store.snapshot() == before
