from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    Approval,
    ApprovalAction,
    ApprovalIssuerType,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
)
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore

ROOT = Path(__file__).resolve().parents[3]
DEV_ROOT = ROOT / "benchmarks" / "harbourdesk" / "dev"
RULES_PATH = ROOT / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
CASE_IDS = tuple(f"hdm-{index:03d}" for index in range(1, 13))


def _load_state(case_id: str) -> HarbourDeskVisibleState:
    return HarbourDeskVisibleState.model_validate_json(
        (DEV_ROOT / case_id / "initial_state.json").read_text(encoding="utf-8")
    )


def _ticket_id(case_id: str) -> str:
    payload = json.loads((DEV_ROOT / case_id / "case.json").read_text(encoding="utf-8"))
    ticket_id = payload["ticket_id"]
    assert isinstance(ticket_id, str)
    return ticket_id


def _environment(
    case_id: str,
    *,
    state: HarbourDeskVisibleState | None = None,
) -> tuple[HarbourDeskStore, HarbourDeskEnvironment]:
    current_state = _load_state(case_id) if state is None else state
    ticket_id = _ticket_id(case_id)
    ticket = next(item for item in current_state.tickets if item.ticket_id == ticket_id)
    store = HarbourDeskStore.in_memory()
    store.initialize(current_state)
    environment = HarbourDeskEnvironment(
        store=store,
        rules=HarbourDeskBusinessRules.load(RULES_PATH),
        tenant_id=ticket.tenant_id,
        ticket_id=ticket_id,
    )
    return store, environment


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_initial_observation_builds_from_public_case_state(case_id: str) -> None:
    store, environment = _environment(case_id)
    try:
        observation = environment.initial_observation()
        assert observation.schema_version == "m0a-v1"
        assert observation.tenant_id == environment.tenant_id
        assert observation.ticket.ticket_id == environment.ticket_id
        assert observation.frozen_at == environment.snapshot().frozen_at
        assert all(
            approval.tenant_id == environment.tenant_id for approval in observation.approvals
        )
        assert set(observation.model_dump(mode="json")) == {
            "schema_version",
            "frozen_at",
            "tenant_id",
            "ticket",
            "approvals",
            "operation_references",
        }
    finally:
        store.close()


def test_ambiguous_case_keeps_all_tenant_approval_candidates() -> None:
    store, environment = _environment("hdm-004")
    try:
        approval_ids = tuple(
            approval.approval_id for approval in environment.initial_observation().approvals
        )
        assert approval_ids == ("approval-004a", "approval-004b")
    finally:
        store.close()


@pytest.mark.parametrize(
    ("case_id", "expected_operation_id"),
    (
        ("hdm-011", "op-011-prior"),
        ("hdm-012", "op-012-prior"),
    ),
)
def test_prior_operation_reference_exposes_identity_not_outcome(
    case_id: str,
    expected_operation_id: str,
) -> None:
    store, environment = _environment(case_id)
    try:
        references = environment.initial_observation().operation_references
        reference = next(item for item in references if item.operation_id == expected_operation_id)
        assert reference.action is ApprovalAction.RECONCILE_ENTITLEMENT
        assert set(reference.model_dump(mode="json")) == {
            "operation_id",
            "account_id",
            "action",
        }
    finally:
        store.close()


def test_initial_observation_filters_cross_tenant_host_state() -> None:
    state = _load_state("hdm-001")
    foreign_approval = Approval(
        approval_id="approval-foreign",
        tenant_id="tenant-foreign",
        account_id="acct-foreign",
        permitted_action=ApprovalAction.RECONCILE_ENTITLEMENT,
        issued_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        expires_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        issuer_type=ApprovalIssuerType.SYSTEM,
    )
    foreign_operation = OperationRecord(
        operation_id="op-foreign",
        tenant_id="tenant-foreign",
        account_id="acct-foreign",
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key="foreign-idempotency-key",
        arguments_hash="0" * 64,
        status=OperationStatus.UNKNOWN,
    )
    scoped_state = state.model_copy(
        update={
            "approvals": state.approvals + (foreign_approval,),
            "operations": state.operations + (foreign_operation,),
        }
    )

    store, environment = _environment("hdm-001", state=scoped_state)
    try:
        observation = environment.initial_observation()
        assert "approval-foreign" not in {
            approval.approval_id for approval in observation.approvals
        }
        assert "op-foreign" not in {
            reference.operation_id for reference in observation.operation_references
        }
    finally:
        store.close()
