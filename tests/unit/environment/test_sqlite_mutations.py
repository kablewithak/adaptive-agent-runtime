from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_runtime.environment.domain import (
    ApprovalAction,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
)
from adaptive_runtime.environment.sqlite_store import (
    HarbourDeskStore,
    StoreIdempotencyConflict,
    StoreRevisionConflict,
)

ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "benchmarks" / "harbourdesk" / "dev" / "hdm-001"


def _store() -> HarbourDeskStore:
    state = HarbourDeskVisibleState.model_validate_json(
        (CASE / "initial_state.json").read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    return store


def _operation(operation_id: str, idempotency_key: str) -> OperationRecord:
    return OperationRecord(
        operation_id=operation_id,
        tenant_id="tenant-001",
        account_id="acct-001",
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key=idempotency_key,
        arguments_hash="a" * 64,
        status=OperationStatus.COMMITTED,
        before_revision=7,
        after_revision=8,
        effective_write=True,
    )


def test_compare_and_swap_conflict_rolls_back_operation_insert() -> None:
    with _store() as store:
        before = store.snapshot()
        entitlement = before.entitlements[0].model_copy(
            update={
                "enabled": True,
                "source_subscription_revision": 5,
                "revision": 8,
            }
        )

        with pytest.raises(StoreRevisionConflict):
            store.replace_entitlement_with_operation(
                entitlement,
                expected_revision=6,
                operation=_operation("op-race", "idem-race"),
            )

        assert store.snapshot() == before


def test_idempotency_uniqueness_rolls_back_second_state_change() -> None:
    with _store() as store:
        before = store.snapshot()
        entitlement = before.entitlements[0].model_copy(
            update={
                "enabled": True,
                "source_subscription_revision": 5,
                "revision": 8,
            }
        )
        store.replace_entitlement_with_operation(
            entitlement,
            expected_revision=7,
            operation=_operation("op-first", "idem-shared"),
        )

        second = entitlement.model_copy(
            update={
                "enabled": False,
                "revision": 9,
            }
        )
        duplicate = OperationRecord(
            operation_id="op-second",
            tenant_id="tenant-001",
            account_id="acct-001",
            action=ApprovalAction.RECONCILE_ENTITLEMENT,
            idempotency_key="idem-shared",
            arguments_hash="b" * 64,
            status=OperationStatus.COMMITTED,
            before_revision=8,
            after_revision=9,
            effective_write=True,
        )

        with pytest.raises(StoreIdempotencyConflict):
            store.replace_entitlement_with_operation(
                second,
                expected_revision=8,
                operation=duplicate,
            )

        current = store.get_entitlements("tenant-001", "acct-001")
        assert current is not None
        assert current[0].revision == 8
        assert current[0].enabled is True
        assert len(store.snapshot().operations) == 1
