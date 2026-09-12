from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.read_tools import (
    PolicySearchObservation,
    ReadToolErrorCode,
    ReadToolName,
    ReadToolStatus,
    execute_read_tool,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore

ROOT = Path(__file__).resolve().parents[3]


def _state(case_id: str) -> HarbourDeskVisibleState:
    path = ROOT / "benchmarks" / "harbourdesk" / "dev" / case_id / "initial_state.json"
    return HarbourDeskVisibleState.model_validate_json(path.read_text(encoding="utf-8"))


def test_get_ticket_returns_scoped_typed_observation() -> None:
    with HarbourDeskStore.in_memory() as store:
        store.initialize(_state("hdm-001"))
        result = execute_read_tool(
            store,
            "tenant-001",
            "call-001",
            ReadToolName.GET_TICKET,
            {"ticket_id": "ticket-001"},
        )

    assert result.status is ReadToolStatus.OK
    assert result.data is not None
    assert result.data.kind == "ticket"
    assert result.data.ticket.ticket_id == "ticket-001"


def test_invalid_arguments_return_machine_readable_error() -> None:
    with HarbourDeskStore.in_memory() as store:
        store.initialize(_state("hdm-001"))
        result = execute_read_tool(
            store,
            "tenant-001",
            "call-002",
            ReadToolName.GET_ACCOUNT,
            {"unexpected": "value"},
        )

    assert result.status is ReadToolStatus.ERROR
    assert result.error_code is ReadToolErrorCode.INVALID_ARGUMENTS
    assert result.data is None


def test_policy_search_preserves_stale_and_current_versions() -> None:
    with HarbourDeskStore.in_memory() as store:
        store.initialize(_state("hdm-005"))
        result = execute_read_tool(
            store,
            "tenant-005",
            "call-003",
            ReadToolName.SEARCH_POLICIES,
            {"query": "Team admin_controls", "max_results": 5},
        )

    assert result.status is ReadToolStatus.OK
    assert isinstance(result.data, PolicySearchObservation)
    hit_by_id = {hit.document_id: hit for hit in result.data.hits}
    assert hit_by_id["policy-access-v1"].active_at_frozen_time is False
    assert hit_by_id["policy-access-v2"].active_at_frozen_time is True


def test_missing_operation_fails_closed_without_exception() -> None:
    with HarbourDeskStore.in_memory() as store:
        store.initialize(_state("hdm-011"))
        result = execute_read_tool(
            store,
            "tenant-011",
            "call-004",
            ReadToolName.GET_OPERATION,
            {"operation_id": "op-does-not-exist"},
        )

    assert result.status is ReadToolStatus.ERROR
    assert result.error_code is ReadToolErrorCode.NOT_FOUND
