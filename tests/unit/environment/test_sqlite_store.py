from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore

ROOT = Path(__file__).resolve().parents[3]


def _state(case_id: str) -> HarbourDeskVisibleState:
    path = ROOT / "benchmarks" / "harbourdesk" / "dev" / case_id / "initial_state.json"
    return HarbourDeskVisibleState.model_validate_json(path.read_text(encoding="utf-8"))


def test_store_round_trips_validated_state_exactly() -> None:
    initial = _state("hdm-001")

    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        restored = store.snapshot()

    assert restored == initial


def test_subscription_reference_scope_preserves_ownership_conflict_evidence() -> None:
    initial = _state("hdm-008")

    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        subscription = store.get_subscription("tenant-008", "sub-008")

    assert subscription is not None
    assert subscription.subscription_id == "sub-008"
    assert subscription.account_id == "acct-008-other"


def test_cross_tenant_ticket_lookup_fails_closed() -> None:
    initial = _state("hdm-001")

    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        ticket = store.get_ticket("tenant-other", "ticket-001")

    assert ticket is None
