from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.read_tools import ReadToolStatus
from adaptive_runtime.environment.runtime import (
    HarbourDeskEnvironment,
    ReadEnvironmentCall,
    WriteEnvironmentCall,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import WriteToolStatus

ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = ROOT / "benchmarks" / "harbourdesk" / "dev" / "hdm-001"
RULES_PATH = ROOT / "benchmarks" / "harbourdesk" / "business_rules_v1.json"


def _environment() -> tuple[HarbourDeskStore, HarbourDeskEnvironment]:
    state = HarbourDeskVisibleState.model_validate_json(
        (CASE_ROOT / "initial_state.json").read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    environment = HarbourDeskEnvironment(
        store=store,
        rules=HarbourDeskBusinessRules.load(RULES_PATH),
        tenant_id="tenant-001",
        ticket_id="ticket-001",
    )
    return store, environment


def test_environment_dispatches_read_and_write_calls() -> None:
    store, environment = _environment()
    try:
        read_result = environment.execute(
            ReadEnvironmentCall(
                call_id="read-ticket",
                tool="get_ticket",
                arguments={"ticket_id": "ticket-001"},
            )
        )
        assert read_result.status is ReadToolStatus.OK

        write_result = environment.execute(
            WriteEnvironmentCall(
                call_id="repair-entitlement",
                tool="reconcile_entitlement",
                idempotency_key="test-runtime-reconcile",
                arguments={
                    "account_id": "acct-001",
                    "feature_id": "exports",
                    "approval_id": "approval-001",
                    "expected_subscription_revision": 5,
                    "expected_entitlement_revision": 7,
                },
            )
        )
        assert write_result.status is WriteToolStatus.OK

        final = environment.snapshot()
        entitlement = next(
            item
            for item in final.entitlements
            if item.account_id == "acct-001" and item.feature_id == "exports"
        )
        assert entitlement.enabled is True
        assert entitlement.source_subscription_revision == 5
        assert entitlement.revision == 8
    finally:
        store.close()
