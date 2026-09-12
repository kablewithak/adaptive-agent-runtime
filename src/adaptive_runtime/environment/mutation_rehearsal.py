from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import (
    EntitlementWriteObservation,
    SubscriptionWriteObservation,
    TicketWriteObservation,
    WriteToolErrorCode,
    WriteToolName,
    WriteToolResult,
    WriteToolStatus,
    execute_write_tool,
)


class MutationRehearsalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MutationScenarioResult(MutationRehearsalContract):
    scenario: str
    passed: bool
    tool: WriteToolName
    status: WriteToolStatus
    error_code: WriteToolErrorCode | None
    replayed: bool
    effective_business_write: bool


class MutationRehearsalSummary(MutationRehearsalContract):
    passed: bool
    scenario_count: int
    passed_count: int
    expected_rejection_count: int
    effective_business_write_count: int
    ticket_update_count: int
    llm_call_count: int
    scenarios: tuple[MutationScenarioResult, ...]


def run_manual_mutation_rehearsal(repo_root: Path) -> MutationRehearsalSummary:
    benchmark_root = repo_root / "benchmarks" / "harbourdesk"
    rules = HarbourDeskBusinessRules.load(benchmark_root / "business_rules_v1.json")
    results: list[MutationScenarioResult] = []

    with _load_store(benchmark_root, "hdm-001") as store:
        reconcile_args = {
            "account_id": "acct-001",
            "feature_id": "exports",
            "approval_id": "approval-001",
            "expected_subscription_revision": 5,
            "expected_entitlement_revision": 7,
        }
        first = execute_write_tool(
            store,
            rules,
            "tenant-001",
            "ticket-001",
            "mut-001",
            "idem-rehearsal-reconcile",
            WriteToolName.RECONCILE_ENTITLEMENT,
            reconcile_args,
        )
        results.append(
            _expect_ok(
                "reconcile_entitlement_commits",
                first,
                replayed=False,
                effective_business_write=True,
            )
        )

        replay = execute_write_tool(
            store,
            rules,
            "tenant-001",
            "ticket-001",
            "mut-002",
            "idem-rehearsal-reconcile",
            WriteToolName.RECONCILE_ENTITLEMENT,
            reconcile_args,
        )
        results.append(
            _expect_ok(
                "exact_idempotent_replay",
                replay,
                replayed=True,
                effective_business_write=True,
            )
        )

    with _load_store(benchmark_root, "hdm-001") as store:
        stale = execute_write_tool(
            store,
            rules,
            "tenant-001",
            "ticket-001",
            "mut-003",
            "idem-rehearsal-stale",
            WriteToolName.RECONCILE_ENTITLEMENT,
            {
                "account_id": "acct-001",
                "feature_id": "exports",
                "approval_id": "approval-001",
                "expected_subscription_revision": 4,
                "expected_entitlement_revision": 7,
            },
        )
        results.append(
            _expect_error(
                "stale_revision_rejected",
                stale,
                WriteToolErrorCode.REVISION_CONFLICT,
            )
        )

    with _load_store(benchmark_root, "hdm-006") as store:
        cancellation = execute_write_tool(
            store,
            rules,
            "tenant-006",
            "ticket-006",
            "mut-004",
            "idem-rehearsal-cancel",
            WriteToolName.SCHEDULE_CANCELLATION,
            {
                "account_id": "acct-006",
                "subscription_id": "sub-006",
                "approval_id": "approval-006",
                "expected_subscription_revision": 9,
                "effective_at": "2026-09-18T12:00:00Z",
            },
        )
        results.append(
            _expect_ok(
                "schedule_cancellation_commits",
                cancellation,
                replayed=False,
                effective_business_write=True,
            )
        )

    with _load_store(benchmark_root, "hdm-009") as store:
        unauthorised = execute_write_tool(
            store,
            rules,
            "tenant-009",
            "ticket-009",
            "mut-005",
            "idem-rehearsal-auth",
            WriteToolName.RECONCILE_ENTITLEMENT,
            {
                "account_id": "acct-009",
                "feature_id": "exports",
                "approval_id": "approval-009",
                "expected_subscription_revision": 3,
                "expected_entitlement_revision": 2,
            },
        )
        results.append(
            _expect_error(
                "unauthorised_requester_rejected",
                unauthorised,
                WriteToolErrorCode.REQUESTER_NOT_AUTHORISED,
            )
        )

    with _load_store(benchmark_root, "hdm-010") as store:
        expired = execute_write_tool(
            store,
            rules,
            "tenant-010",
            "ticket-010",
            "mut-006",
            "idem-rehearsal-expired",
            WriteToolName.RECONCILE_ENTITLEMENT,
            {
                "account_id": "acct-010",
                "feature_id": "admin_controls",
                "approval_id": "approval-010",
                "expected_subscription_revision": 5,
                "expected_entitlement_revision": 3,
            },
        )
        results.append(
            _expect_error(
                "expired_approval_rejected",
                expired,
                WriteToolErrorCode.APPROVAL_EXPIRED,
            )
        )

    with _load_store(benchmark_root, "hdm-008") as store:
        ownership = execute_write_tool(
            store,
            rules,
            "tenant-008",
            "ticket-008",
            "mut-007",
            "idem-rehearsal-owner",
            WriteToolName.RECONCILE_ENTITLEMENT,
            {
                "account_id": "acct-008",
                "feature_id": "admin_controls",
                "approval_id": "approval-008",
                "expected_subscription_revision": 4,
                "expected_entitlement_revision": 2,
            },
        )
        results.append(
            _expect_error(
                "ownership_conflict_rejected",
                ownership,
                WriteToolErrorCode.OWNERSHIP_CONFLICT,
            )
        )

    with _load_store(benchmark_root, "hdm-012") as store:
        unknown = execute_write_tool(
            store,
            rules,
            "tenant-012",
            "ticket-012",
            "mut-008",
            "idem-case-012-prior",
            WriteToolName.RECONCILE_ENTITLEMENT,
            {
                "account_id": "acct-012",
                "feature_id": "exports",
                "approval_id": "approval-012",
                "expected_subscription_revision": 6,
                "expected_entitlement_revision": 5,
            },
        )
        results.append(
            _expect_error(
                "unknown_prior_operation_blocks_retry",
                unknown,
                WriteToolErrorCode.OPERATION_OUTCOME_UNKNOWN,
            )
        )

    with _load_store(benchmark_root, "hdm-003") as store:
        ticket_update = execute_write_tool(
            store,
            rules,
            "tenant-003",
            "ticket-003",
            "mut-009",
            "idem-rehearsal-ticket",
            WriteToolName.UPDATE_TICKET,
            {
                "ticket_id": "ticket-003",
                "expected_ticket_revision": 1,
                "status": "pending_clarification",
                "resolution_reason_code": "ACCOUNT_OR_FEATURE_AMBIGUOUS",
                "evidence_document_ids": [],
                "operation_ids": [],
            },
        )
        results.append(
            _expect_ok(
                "ticket_update_commits_without_business_write",
                ticket_update,
                replayed=False,
                effective_business_write=False,
            )
        )

    scenario_results = tuple(results)
    expected_rejections = sum(
        1 for result in scenario_results if result.status is WriteToolStatus.ERROR
    )
    effective_writes = sum(
        1 for result in scenario_results if result.effective_business_write and not result.replayed
    )
    ticket_updates = sum(
        1
        for result in scenario_results
        if result.tool is WriteToolName.UPDATE_TICKET
        and result.status is WriteToolStatus.OK
        and not result.replayed
    )

    return MutationRehearsalSummary(
        passed=all(result.passed for result in scenario_results),
        scenario_count=len(scenario_results),
        passed_count=sum(1 for result in scenario_results if result.passed),
        expected_rejection_count=expected_rejections,
        effective_business_write_count=effective_writes,
        ticket_update_count=ticket_updates,
        llm_call_count=0,
        scenarios=scenario_results,
    )


def _load_store(
    benchmark_root: Path,
    case_id: str,
) -> HarbourDeskStore:
    state = HarbourDeskVisibleState.model_validate_json(
        (benchmark_root / "dev" / case_id / "initial_state.json").read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    return store


def _expect_ok(
    scenario: str,
    result: WriteToolResult,
    *,
    replayed: bool,
    effective_business_write: bool,
) -> MutationScenarioResult:
    observed_replayed = False
    observed_effective = False
    if isinstance(
        result.data,
        EntitlementWriteObservation | SubscriptionWriteObservation | TicketWriteObservation,
    ):
        observed_replayed = result.data.replayed
        observed_effective = result.data.operation.effective_write

    return MutationScenarioResult(
        scenario=scenario,
        passed=(
            result.status is WriteToolStatus.OK
            and observed_replayed is replayed
            and observed_effective is effective_business_write
        ),
        tool=result.tool,
        status=result.status,
        error_code=result.error_code,
        replayed=observed_replayed,
        effective_business_write=observed_effective,
    )


def _expect_error(
    scenario: str,
    result: WriteToolResult,
    expected_error: WriteToolErrorCode,
) -> MutationScenarioResult:
    return MutationScenarioResult(
        scenario=scenario,
        passed=(result.status is WriteToolStatus.ERROR and result.error_code is expected_error),
        tool=result.tool,
        status=result.status,
        error_code=result.error_code,
        replayed=False,
        effective_business_write=False,
    )
