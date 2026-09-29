from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.provider import (
    ChatRole,
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolCallFunction,
    UsageAccounting,
)
from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    ApprovalAction,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
)
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import (
    HarbourDeskStore,
    StoreIdempotencyConflict,
    StoreRevisionConflict,
)
from adaptive_runtime.environment.write_tools import (
    EntitlementWriteObservation,
    WriteToolErrorCode,
    WriteToolName,
    WriteToolStatus,
    execute_write_tool,
)
from adaptive_runtime.experiments.harbourdesk_r6 import (
    R6FaultCase,
    load_r6_fault_program,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveRunBudget,
    LiveRunResult,
    LiveStopCategory,
    UsageObservationStatus,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink

R6A_FROZEN_COMMIT = "610e7a03818e0ba8c8b726abb43f3816ef27c933"
R5EC_MANIFEST_SHA256 = "ddc6840eda426af02c77745475fcc9aecbe7aead06391b12ca91f1a3a29539d7"
R5EC_SUMMARY_SHA256 = "c8e88eaa38e349b73d4be1c7233261e129b9f75c1b7c1b372a9b4d2ba0345e0c"
R6_RUNTIME_CASE_ID = "hdm-001"


class R6BContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R6InvariantCheck(R6BContract):
    invariant: str
    passed: bool


class R6CaseObservation(R6BContract):
    invariant_results: tuple[bool, ...]
    unexpected_effective_writes: int = Field(default=0, ge=0)
    evidence_paths: tuple[str, ...] = ()
    details: dict[str, object] = Field(default_factory=dict)


class R6CaseReceipt(R6BContract):
    schema_version: Literal["harbourdesk-r6b-case-v1"] = "harbourdesk-r6b-case-v1"
    case_id: str
    family: str
    fault: str
    target: str
    status: Literal["PASS", "FAIL", "ERROR"]
    execution_complete: bool
    invariant_checks: tuple[R6InvariantCheck, ...]
    invariant_failure_count: int = Field(ge=0)
    unexpected_effective_writes: int = Field(ge=0)
    evidence_complete: bool
    evidence_paths: tuple[str, ...]
    details: dict[str, object]
    error_type: str | None = None
    error_message: str | None = None


class R6SuiteReceipt(R6BContract):
    schema_version: Literal["harbourdesk-r6b-suite-v1"] = "harbourdesk-r6b-suite-v1"
    execution_status: Literal["COMPLETE", "PARTIAL"]
    decision: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    run_id: str
    candidate_commit: str
    r6a_frozen_commit: str
    fault_program_sha256: str
    r5ec_manifest_sha256: str
    r5ec_summary_sha256: str
    case_count: int
    complete_case_count: int
    pass_case_count: int
    failed_case_count: int
    error_case_count: int
    invariant_failure_count: int
    unexpected_effective_writes: int
    evidence_complete: bool
    external_provider_calls: Literal[0]
    live_model_calls: Literal[0]
    family_case_counts: dict[str, int]
    family_pass_counts: dict[str, int]
    cases: tuple[R6CaseReceipt, ...]


class ScriptedProvider:
    def __init__(
        self,
        outcomes: Iterable[ModelResult | ProviderCallError],
        *,
        rewrite_request_id: bool = True,
    ) -> None:
        self._outcomes = tuple(outcomes)
        self._index = 0
        self._rewrite_request_id = rewrite_request_id
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        if self._index >= len(self._outcomes):
            raise AssertionError("scripted provider received unexpected extra request")

        outcome = self._outcomes[self._index]
        self._index += 1
        if isinstance(outcome, ProviderCallError):
            raise outcome
        if self._rewrite_request_id:
            return outcome.model_copy(update={"request_id": request.request_id})
        return outcome


def registered_r6_faults() -> frozenset[str]:
    return frozenset(
        {
            "provider_timeout",
            "provider_refusal",
            "provider_request_identity_mismatch",
            "successful_response_missing_usage",
            "malformed_tool_arguments",
            "foreign_ticket_scope_attempt",
            "multi_tool_batch_contains_write",
            "duplicate_multi_tool_call_id",
            "model_call_budget_exhausted",
            "tool_action_budget_exhausted",
            "deadline_during_multi_read_batch",
            "text_only_false_completion",
            "stale_revision_compare_and_swap",
            "duplicate_idempotency_key",
            "exact_idempotent_replay",
            "unknown_prior_operation_retry",
            "unauthorised_requester",
            "expired_approval",
            "subscription_ownership_conflict",
            "cancellation_before_policy_minimum",
            "existing_trace_path",
            "provider_reasoning_in_memory",
            "final_state_hash_verification",
            "rejected_batch_trace",
        }
    )


def run_r6_fault_program(
    *,
    repo_root: Path,
    run_id: str,
    candidate_commit: str,
    evidence_dir: Path,
) -> R6SuiteReceipt:
    program = load_r6_fault_program(repo_root)
    configured_faults = {case.fault for case in program.cases}
    if configured_faults != registered_r6_faults():
        raise ValueError("R6 fault registry does not match frozen R6A contract")
    if evidence_dir.exists():
        raise FileExistsError(f"R6B evidence directory exists: {evidence_dir}")

    evidence_dir.mkdir(parents=True, exist_ok=False)
    fault_program_path = repo_root / "benchmarks" / "harbourdesk" / "r6" / "fault_program_v1.json"
    fault_program_sha = _sha256_file(fault_program_path)

    manifest = {
        "schema_version": "harbourdesk-r6b-manifest-v1",
        "run_id": run_id,
        "candidate_commit": candidate_commit,
        "r6a_frozen_commit": R6A_FROZEN_COMMIT,
        "fault_program_sha256": fault_program_sha,
        "r5ec_manifest_sha256": R5EC_MANIFEST_SHA256,
        "r5ec_summary_sha256": R5EC_SUMMARY_SHA256,
        "case_order": [case.case_id for case in program.cases],
        "external_provider_calls": 0,
        "live_model_calls": 0,
    }
    (evidence_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipts: list[R6CaseReceipt] = []
    for case in program.cases:
        case_dir = evidence_dir / case.case_id
        case_dir.mkdir(parents=False, exist_ok=False)
        receipt = _execute_case(repo_root, case, case_dir)
        receipt_path = case_dir / "receipt.json"
        receipt_path.write_text(
            receipt.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        receipts.append(receipt)

    cases = tuple(receipts)
    complete_count = sum(case.execution_complete for case in cases)
    pass_count = sum(case.status == "PASS" for case in cases)
    failed_count = sum(case.status == "FAIL" for case in cases)
    error_count = sum(case.status == "ERROR" for case in cases)
    invariant_failures = sum(
        case.invariant_failure_count for case in cases if case.execution_complete
    )
    unexpected_writes = sum(case.unexpected_effective_writes for case in cases)
    evidence_complete = all(
        case.evidence_complete and (evidence_dir / case.case_id / "receipt.json").is_file()
        for case in cases
    )

    if complete_count != len(program.cases) or not evidence_complete:
        decision: Literal["PASS", "FAIL", "INCONCLUSIVE"] = "INCONCLUSIVE"
    elif invariant_failures != 0 or unexpected_writes != 0:
        decision = "FAIL"
    else:
        decision = "PASS"

    family_case_counts = Counter(case.family for case in cases)
    family_pass_counts = Counter(case.family for case in cases if case.status == "PASS")

    suite = R6SuiteReceipt(
        execution_status=("COMPLETE" if complete_count == len(program.cases) else "PARTIAL"),
        decision=decision,
        run_id=run_id,
        candidate_commit=candidate_commit,
        r6a_frozen_commit=R6A_FROZEN_COMMIT,
        fault_program_sha256=fault_program_sha,
        r5ec_manifest_sha256=R5EC_MANIFEST_SHA256,
        r5ec_summary_sha256=R5EC_SUMMARY_SHA256,
        case_count=len(cases),
        complete_case_count=complete_count,
        pass_case_count=pass_count,
        failed_case_count=failed_count,
        error_case_count=error_count,
        invariant_failure_count=invariant_failures,
        unexpected_effective_writes=unexpected_writes,
        evidence_complete=evidence_complete,
        external_provider_calls=0,
        live_model_calls=0,
        family_case_counts=dict(sorted(family_case_counts.items())),
        family_pass_counts={
            family: family_pass_counts.get(family, 0) for family in sorted(family_case_counts)
        },
        cases=cases,
    )
    (evidence_dir / "summary.json").write_text(
        suite.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return suite


def _execute_case(
    repo_root: Path,
    case: R6FaultCase,
    case_dir: Path,
) -> R6CaseReceipt:
    try:
        observation = _dispatch_fault(repo_root, case.fault, case_dir)
        if len(observation.invariant_results) != len(case.invariants):
            raise ValueError(f"{case.case_id} returned the wrong invariant result count")

        checks = tuple(
            R6InvariantCheck(invariant=invariant, passed=passed)
            for invariant, passed in zip(
                case.invariants,
                observation.invariant_results,
                strict=True,
            )
        )
        invariant_failure_count = sum(not check.passed for check in checks)
        evidence_complete = all(
            (case_dir / relative_path).is_file() for relative_path in observation.evidence_paths
        )
        status: Literal["PASS", "FAIL", "ERROR"] = (
            "PASS"
            if invariant_failure_count == 0
            and observation.unexpected_effective_writes == 0
            and evidence_complete
            else "FAIL"
        )
        return R6CaseReceipt(
            case_id=case.case_id,
            family=case.family,
            fault=case.fault,
            target=case.target,
            status=status,
            execution_complete=True,
            invariant_checks=checks,
            invariant_failure_count=invariant_failure_count,
            unexpected_effective_writes=(observation.unexpected_effective_writes),
            evidence_complete=evidence_complete,
            evidence_paths=observation.evidence_paths,
            details=observation.details,
        )
    except Exception as exc:
        checks = tuple(
            R6InvariantCheck(invariant=invariant, passed=False) for invariant in case.invariants
        )
        return R6CaseReceipt(
            case_id=case.case_id,
            family=case.family,
            fault=case.fault,
            target=case.target,
            status="ERROR",
            execution_complete=False,
            invariant_checks=checks,
            invariant_failure_count=0,
            unexpected_effective_writes=0,
            evidence_complete=False,
            evidence_paths=(),
            details={},
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _dispatch_fault(
    repo_root: Path,
    fault: str,
    case_dir: Path,
) -> R6CaseObservation:
    if fault == "provider_timeout":
        return _provider_timeout(repo_root, case_dir)
    if fault == "provider_refusal":
        return _provider_refusal(repo_root, case_dir)
    if fault == "provider_request_identity_mismatch":
        return _provider_identity_mismatch(repo_root, case_dir)
    if fault == "successful_response_missing_usage":
        return _missing_usage(repo_root, case_dir)
    if fault == "malformed_tool_arguments":
        return _malformed_tool_arguments(repo_root, case_dir)
    if fault == "foreign_ticket_scope_attempt":
        return _foreign_ticket_scope(repo_root, case_dir)
    if fault == "multi_tool_batch_contains_write":
        return _multi_tool_write_batch(repo_root, case_dir)
    if fault == "duplicate_multi_tool_call_id":
        return _duplicate_tool_call_id(repo_root, case_dir)
    if fault == "model_call_budget_exhausted":
        return _model_call_budget(repo_root, case_dir)
    if fault == "tool_action_budget_exhausted":
        return _tool_action_budget(repo_root, case_dir)
    if fault == "deadline_during_multi_read_batch":
        return _deadline_during_read_batch(repo_root, case_dir)
    if fault == "text_only_false_completion":
        return _text_only_completion(repo_root, case_dir)
    if fault == "stale_revision_compare_and_swap":
        return _stale_revision(repo_root)
    if fault == "duplicate_idempotency_key":
        return _duplicate_idempotency(repo_root)
    if fault == "exact_idempotent_replay":
        return _exact_idempotent_replay(repo_root)
    if fault == "unknown_prior_operation_retry":
        return _unknown_prior_operation(repo_root)
    if fault == "unauthorised_requester":
        return _unauthorised_requester(repo_root)
    if fault == "expired_approval":
        return _expired_approval(repo_root)
    if fault == "subscription_ownership_conflict":
        return _ownership_conflict(repo_root)
    if fault == "cancellation_before_policy_minimum":
        return _invalid_cancellation_date(repo_root)
    if fault == "existing_trace_path":
        return _existing_trace_path(case_dir)
    if fault == "provider_reasoning_in_memory":
        return _reasoning_redaction(repo_root, case_dir)
    if fault == "final_state_hash_verification":
        return _final_state_hash(repo_root, case_dir)
    if fault == "rejected_batch_trace":
        return _rejected_batch_trace(repo_root, case_dir)
    raise ValueError(f"unregistered R6 fault: {fault}")


def _provider_timeout(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ProviderCallError(
                code=ProviderErrorCode.PROVIDER_TIMEOUT,
                message="R6 deterministic timeout",
                retryable=True,
            ),
        )
    )
    result = _run_runtime(repo_root, provider, case_dir)
    attempt = result.trace.attempts[0]
    return R6CaseObservation(
        invariant_results=(
            len(provider.requests) == 1,
            result.trace.stop_category is LiveStopCategory.PROVIDER_ERROR,
            attempt.usage_status is UsageObservationStatus.UNKNOWN_AFTER_ERROR,
            len(result.trace.tool_actions) == 0,
        ),
        evidence_paths=("trace.jsonl",),
        details={"error_code": _enum_value(attempt.error_code)},
    )


def _provider_refusal(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ModelResult(
                request_id="placeholder",
                outcome=ProviderOutcome.REFUSAL,
                returned_model="fake-model",
                stop_reason="refusal",
                usage=UsageAccounting(
                    input_tokens=10,
                    completion_tokens=1,
                ),
            ),
        )
    )
    result = _run_runtime(repo_root, provider, case_dir)
    ticket = result.final_state.tickets[0]
    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.PROVIDER_REFUSAL,
            len(result.trace.tool_actions) == 0,
            ticket.status.value == "open",
        ),
        evidence_paths=("trace.jsonl",),
    )


def _provider_identity_mismatch(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ModelResult(
                request_id="wrong-request-id",
                outcome=ProviderOutcome.SUCCESS,
                returned_model="fake-model",
                text="mismatched response",
                usage=UsageAccounting(
                    input_tokens=10,
                    completion_tokens=2,
                ),
            ),
        ),
        rewrite_request_id=False,
    )
    result = _run_runtime(repo_root, provider, case_dir)
    attempt = result.trace.attempts[0]
    return R6CaseObservation(
        invariant_results=(
            attempt.error_code is ProviderErrorCode.PROTOCOL_ERROR,
            result.trace.stop_category is LiveStopCategory.PROVIDER_ERROR,
            attempt.error_code is ProviderErrorCode.PROTOCOL_ERROR,
            len(result.trace.tool_actions) == 0,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _missing_usage(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ModelResult(
                request_id="placeholder",
                outcome=ProviderOutcome.SUCCESS,
                returned_model="fake-model",
                tool_calls=(_tool_call("read-1", "get_ticket", {}),),
                stop_reason="tool_calls",
                usage=None,
            ),
        )
    )
    result = _run_runtime(
        repo_root,
        provider,
        case_dir,
        budget=LiveRunBudget(max_model_calls=1),
    )
    attempt = result.trace.attempts[0]
    return R6CaseObservation(
        invariant_results=(
            attempt.usage_status is UsageObservationStatus.MISSING,
            attempt.usage is None,
            result.trace.stop_category is LiveStopCategory.MODEL_CALL_BUDGET_EXHAUSTED,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _malformed_tool_arguments(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider((_success(_tool_call("bad-1", "get_ticket", "{not-json")),))
    initial, result = _run_runtime_with_initial(repo_root, provider, case_dir)
    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.INVALID_TOOL_CALL,
            len(result.trace.tool_actions) == 0,
            result.final_state == initial,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _foreign_ticket_scope(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            _success(
                _tool_call(
                    "scope-1",
                    "get_ticket",
                    {"ticket_id": "ticket-foreign"},
                )
            ),
        )
    )
    initial, result = _run_runtime_with_initial(repo_root, provider, case_dir)
    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.INVALID_TOOL_CALL,
            len(result.trace.tool_actions) == 0,
            result.final_state == initial,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _multi_tool_write_batch(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            _success(
                _tool_call("read-1", "get_ticket", {}),
                _terminal_update_call(),
            ),
        )
    )
    initial, result = _run_runtime_with_initial(repo_root, provider, case_dir)
    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL,
            len(result.trace.tool_actions) == 0,
            _effective_write_count(result.final_state) == _effective_write_count(initial),
        ),
        evidence_paths=("trace.jsonl",),
    )


def _duplicate_tool_call_id(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            _success(
                _tool_call("duplicate-id", "get_ticket", {}),
                _tool_call(
                    "duplicate-id",
                    "get_account",
                    {"account_id": "acct-001"},
                ),
            ),
        )
    )
    initial, result = _run_runtime_with_initial(repo_root, provider, case_dir)
    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL,
            len(result.trace.tool_actions) == 0,
            result.final_state == initial,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _model_call_budget(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider((_success(_tool_call("read-1", "get_ticket", {})),))
    result = _run_runtime(
        repo_root,
        provider,
        case_dir,
        budget=LiveRunBudget(max_model_calls=1),
    )
    return R6CaseObservation(
        invariant_results=(
            len(provider.requests) == 1,
            result.trace.stop_category is LiveStopCategory.MODEL_CALL_BUDGET_EXHAUSTED,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _tool_action_budget(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            _success(_tool_call("read-1", "get_ticket", {})),
            _success(_tool_call("read-2", "get_ticket", {})),
        )
    )
    result = _run_runtime(
        repo_root,
        provider,
        case_dir,
        budget=LiveRunBudget(max_tool_actions=1),
    )
    return R6CaseObservation(
        invariant_results=(
            len(result.trace.tool_actions) == 1,
            result.trace.stop_category is LiveStopCategory.TOOL_ACTION_BUDGET_EXHAUSTED,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _deadline_during_read_batch(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            _success(
                _tool_call("read-1", "get_ticket", {}),
                _tool_call(
                    "read-2",
                    "get_account",
                    {"account_id": "acct-001"},
                ),
                _tool_call(
                    "read-3",
                    "get_subscription",
                    {"subscription_id": "sub-001"},
                ),
            ),
        )
    )
    with patch(
        "adaptive_runtime.runtime.harbourdesk_live._trajectory_deadline_exceeded",
        side_effect=(False, False, True),
    ):
        result = _run_runtime(repo_root, provider, case_dir)

    return R6CaseObservation(
        invariant_results=(
            result.trace.stop_category is LiveStopCategory.TRAJECTORY_DEADLINE_EXCEEDED,
            _effective_write_count(result.final_state) == 0,
            len(result.trace.tool_actions) == 1,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _text_only_completion(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ModelResult(
                request_id="placeholder",
                outcome=ProviderOutcome.SUCCESS,
                returned_model="fake-model",
                text="I have completed the task.",
                usage=UsageAccounting(
                    input_tokens=10,
                    completion_tokens=5,
                ),
            ),
        )
    )
    result = _run_runtime(repo_root, provider, case_dir)
    return R6CaseObservation(
        invariant_results=(
            result.final_state.tickets[0].status.value == "open",
            result.trace.stop_category is LiveStopCategory.MODEL_TEXT_WITHOUT_TERMINAL,
            result.final_state.tickets[0].status.value == "open",
        ),
        evidence_paths=("trace.jsonl",),
    )


def _stale_revision(repo_root: Path) -> R6CaseObservation:
    with _load_store(repo_root, "hdm-001") as store:
        before = store.snapshot()
        entitlement = before.entitlements[0].model_copy(
            update={
                "enabled": True,
                "source_subscription_revision": 5,
                "revision": 8,
            }
        )
        conflict = False
        try:
            store.replace_entitlement_with_operation(
                entitlement,
                expected_revision=6,
                operation=_operation(
                    operation_id="r6-stale-op",
                    idempotency_key="r6-stale-idem",
                    arguments_hash="a" * 64,
                    before_revision=7,
                    after_revision=8,
                ),
            )
        except StoreRevisionConflict:
            conflict = True
        after = store.snapshot()

    return R6CaseObservation(
        invariant_results=(
            conflict,
            after == before,
            len(after.operations) == len(before.operations),
        ),
        details={
            "before_state_sha256": _state_sha256(before),
            "after_state_sha256": _state_sha256(after),
        },
    )


def _duplicate_idempotency(repo_root: Path) -> R6CaseObservation:
    with _load_store(repo_root, "hdm-001") as store:
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
            operation=_operation(
                operation_id="r6-first-op",
                idempotency_key="r6-shared-idem",
                arguments_hash="a" * 64,
                before_revision=7,
                after_revision=8,
            ),
        )
        second = entitlement.model_copy(update={"enabled": False, "revision": 9})
        conflict = False
        try:
            store.replace_entitlement_with_operation(
                second,
                expected_revision=8,
                operation=_operation(
                    operation_id="r6-second-op",
                    idempotency_key="r6-shared-idem",
                    arguments_hash="b" * 64,
                    before_revision=8,
                    after_revision=9,
                ),
            )
        except StoreIdempotencyConflict:
            conflict = True
        after = store.snapshot()

    current = next(item for item in after.entitlements if item.feature_id == "exports")
    expected_operation_count = len(before.operations) + 1
    return R6CaseObservation(
        invariant_results=(
            conflict and current.revision == 8,
            len(after.operations) == expected_operation_count,
            current.enabled is True and current.revision == 8,
        ),
        unexpected_effective_writes=max(
            0,
            _effective_write_count(after) - _effective_write_count(before) - 1,
        ),
    )


def _exact_idempotent_replay(repo_root: Path) -> R6CaseObservation:
    with _load_store(repo_root, "hdm-001") as store:
        before = store.snapshot()
        arguments = {
            "account_id": "acct-001",
            "feature_id": "exports",
            "approval_id": "approval-001",
            "expected_subscription_revision": 5,
            "expected_entitlement_revision": 7,
        }
        first = execute_write_tool(
            store,
            _rules(repo_root),
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="r6-first",
            idempotency_key="r6-exact-replay",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments=arguments,
        )
        second = execute_write_tool(
            store,
            _rules(repo_root),
            tenant_id="tenant-001",
            ticket_id="ticket-001",
            call_id="r6-second",
            idempotency_key="r6-exact-replay",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments=arguments,
        )
        after = store.snapshot()

    replayed = (
        second.status is WriteToolStatus.OK
        and isinstance(second.data, EntitlementWriteObservation)
        and second.data.replayed
    )
    operation_delta = len(after.operations) - len(before.operations)
    effective_delta = _effective_write_count(after) - _effective_write_count(before)
    return R6CaseObservation(
        invariant_results=(
            replayed,
            effective_delta == 1,
            operation_delta == 1,
        ),
        unexpected_effective_writes=max(0, effective_delta - 1),
        details={
            "first_status": first.status.value,
            "second_status": second.status.value,
        },
    )


def _unknown_prior_operation(repo_root: Path) -> R6CaseObservation:
    with _load_store(repo_root, "hdm-012") as store:
        before = store.snapshot()
        result = execute_write_tool(
            store,
            _rules(repo_root),
            tenant_id="tenant-012",
            ticket_id="ticket-012",
            call_id="r6-unknown",
            idempotency_key="r6-fresh-retry-key",
            tool=WriteToolName.RECONCILE_ENTITLEMENT,
            arguments={
                "account_id": "acct-012",
                "feature_id": "exports",
                "approval_id": "approval-012",
                "expected_subscription_revision": 6,
                "expected_entitlement_revision": 5,
            },
        )
        after = store.snapshot()

    return R6CaseObservation(
        invariant_results=(
            result.status is WriteToolStatus.ERROR,
            result.error_code is WriteToolErrorCode.OPERATION_OUTCOME_UNKNOWN,
            after == before,
        ),
        unexpected_effective_writes=max(
            0,
            _effective_write_count(after) - _effective_write_count(before),
        ),
    )


def _unauthorised_requester(repo_root: Path) -> R6CaseObservation:
    return _write_error_case(
        repo_root,
        case_id="hdm-009",
        tenant_id="tenant-009",
        ticket_id="ticket-009",
        idempotency_key="r6-auth",
        tool=WriteToolName.RECONCILE_ENTITLEMENT,
        arguments={
            "account_id": "acct-009",
            "feature_id": "exports",
            "approval_id": "approval-009",
            "expected_subscription_revision": 3,
            "expected_entitlement_revision": 2,
        },
        expected_error=WriteToolErrorCode.REQUESTER_NOT_AUTHORISED,
    )


def _expired_approval(repo_root: Path) -> R6CaseObservation:
    return _write_error_case(
        repo_root,
        case_id="hdm-010",
        tenant_id="tenant-010",
        ticket_id="ticket-010",
        idempotency_key="r6-expired",
        tool=WriteToolName.RECONCILE_ENTITLEMENT,
        arguments={
            "account_id": "acct-010",
            "feature_id": "admin_controls",
            "approval_id": "approval-010",
            "expected_subscription_revision": 5,
            "expected_entitlement_revision": 3,
        },
        expected_error=WriteToolErrorCode.APPROVAL_EXPIRED,
    )


def _ownership_conflict(repo_root: Path) -> R6CaseObservation:
    return _write_error_case(
        repo_root,
        case_id="hdm-008",
        tenant_id="tenant-008",
        ticket_id="ticket-008",
        idempotency_key="r6-owner",
        tool=WriteToolName.RECONCILE_ENTITLEMENT,
        arguments={
            "account_id": "acct-008",
            "feature_id": "admin_controls",
            "approval_id": "approval-008",
            "expected_subscription_revision": 4,
            "expected_entitlement_revision": 2,
        },
        expected_error=WriteToolErrorCode.OWNERSHIP_CONFLICT,
    )


def _invalid_cancellation_date(repo_root: Path) -> R6CaseObservation:
    return _write_error_case(
        repo_root,
        case_id="hdm-006",
        tenant_id="tenant-006",
        ticket_id="ticket-006",
        idempotency_key="r6-cancel-early",
        tool=WriteToolName.SCHEDULE_CANCELLATION,
        arguments={
            "account_id": "acct-006",
            "subscription_id": "sub-006",
            "approval_id": "approval-006",
            "expected_subscription_revision": 9,
            "effective_at": "2026-09-17T12:00:00Z",
        },
        expected_error=WriteToolErrorCode.EFFECTIVE_DATE_INVALID,
    )


def _existing_trace_path(case_dir: Path) -> R6CaseObservation:
    trace_path = case_dir / "trace.jsonl"
    sentinel = b"existing-r6-evidence\n"
    trace_path.write_bytes(sentinel)
    refused = False
    try:
        JsonlTraceSink(trace_path)
    except FileExistsError:
        refused = True
    return R6CaseObservation(
        invariant_results=(
            refused,
            trace_path.read_bytes() == sentinel,
        ),
        evidence_paths=("trace.jsonl",),
    )


def _reasoning_redaction(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    secret = "R6_EPHEMERAL_PROVIDER_REASONING"
    provider = ScriptedProvider(
        (
            _success(
                _tool_call("read-1", "get_ticket", {}),
                reasoning=secret,
            ),
            _success(_terminal_update_call()),
        )
    )
    result = _run_runtime(repo_root, provider, case_dir)
    second_request = provider.requests[1]
    assistant_messages = tuple(
        message for message in second_request.messages if message.role is ChatRole.ASSISTANT
    )
    durable = (case_dir / "trace.jsonl").read_text(encoding="utf-8")
    replayed = any(message.provider_reasoning_content == secret for message in assistant_messages)
    return R6CaseObservation(
        invariant_results=(
            replayed,
            secret not in durable,
        ),
        evidence_paths=("trace.jsonl",),
        details={
            "stop_category": result.trace.stop_category.value,
            "assistant_message_count": len(assistant_messages),
        },
    )


def _final_state_hash(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    provider = ScriptedProvider(
        (
            ModelResult(
                request_id="placeholder",
                outcome=ProviderOutcome.SUCCESS,
                returned_model="fake-model",
                text="No terminal action.",
                usage=UsageAccounting(
                    input_tokens=10,
                    completion_tokens=4,
                ),
            ),
        )
    )
    result = _run_runtime(repo_root, provider, case_dir)
    expected_hash = _state_sha256(result.final_state)
    events = _read_jsonl(case_dir / "trace.jsonl")
    run_finished = events[-1]
    durable_hash = str(run_finished["final_state_sha256"])
    return R6CaseObservation(
        invariant_results=(
            durable_hash == expected_hash,
            result.trace.final_state_sha256 == expected_hash,
        ),
        evidence_paths=("trace.jsonl",),
        details={"final_state_sha256": expected_hash},
    )


def _rejected_batch_trace(
    repo_root: Path,
    case_dir: Path,
) -> R6CaseObservation:
    secret = "R6_REJECTED_BATCH_REASONING"
    provider = ScriptedProvider(
        (
            _success(
                _tool_call("read-1", "get_ticket", {}),
                _terminal_update_call(),
                reasoning=secret,
            ),
        )
    )
    initial, result = _run_runtime_with_initial(repo_root, provider, case_dir)
    durable = (case_dir / "trace.jsonl").read_text(encoding="utf-8")
    events = _read_jsonl(case_dir / "trace.jsonl")
    preflight = next(event for event in events if event["event"] == "multi_tool_batch_preflight")
    return R6CaseObservation(
        invariant_results=(
            preflight["accepted"] is False and preflight["rejection_reason"] == "contains_write",
            secret not in durable,
            _effective_write_count(result.final_state) == _effective_write_count(initial),
        ),
        evidence_paths=("trace.jsonl",),
    )


def _write_error_case(
    repo_root: Path,
    *,
    case_id: str,
    tenant_id: str,
    ticket_id: str,
    idempotency_key: str,
    tool: WriteToolName,
    arguments: dict[str, object],
    expected_error: WriteToolErrorCode,
) -> R6CaseObservation:
    with _load_store(repo_root, case_id) as store:
        before = store.snapshot()
        result = execute_write_tool(
            store,
            _rules(repo_root),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            call_id=f"r6-{case_id}",
            idempotency_key=idempotency_key,
            tool=tool,
            arguments=arguments,
        )
        after = store.snapshot()

    no_effective_write = _effective_write_count(after) == _effective_write_count(before)
    state_unchanged = after == before
    return R6CaseObservation(
        invariant_results=(
            result.error_code is expected_error,
            no_effective_write
            if expected_error is not WriteToolErrorCode.EFFECTIVE_DATE_INVALID
            else state_unchanged,
        ),
        unexpected_effective_writes=max(
            0,
            _effective_write_count(after) - _effective_write_count(before),
        ),
        details={
            "status": result.status.value,
            "error_code": _enum_value(result.error_code),
            "state_unchanged": state_unchanged,
        },
    )


def _run_runtime(
    repo_root: Path,
    provider: ScriptedProvider,
    case_dir: Path,
    *,
    budget: LiveRunBudget | None = None,
) -> LiveRunResult:
    with _load_store(repo_root, R6_RUNTIME_CASE_ID) as store:
        environment = _environment(repo_root, store, R6_RUNTIME_CASE_ID)
        return run_live_harbourdesk(
            provider=provider,
            environment=environment,
            run_id=f"r6-{case_dir.name}",
            model_profile=_profile(),
            budget=budget,
            trace_sink=JsonlTraceSink(case_dir / "trace.jsonl"),
        )


def _run_runtime_with_initial(
    repo_root: Path,
    provider: ScriptedProvider,
    case_dir: Path,
    *,
    budget: LiveRunBudget | None = None,
) -> tuple[HarbourDeskVisibleState, LiveRunResult]:
    with _load_store(repo_root, R6_RUNTIME_CASE_ID) as store:
        environment = _environment(repo_root, store, R6_RUNTIME_CASE_ID)
        initial = environment.snapshot()
        result = run_live_harbourdesk(
            provider=provider,
            environment=environment,
            run_id=f"r6-{case_dir.name}",
            model_profile=_profile(),
            budget=budget,
            trace_sink=JsonlTraceSink(case_dir / "trace.jsonl"),
        )
        return initial, result


def _profile() -> LiveModelProfile:
    return LiveModelProfile(
        model_id="fake-model",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        thinking=False,
        profile_version="r6b-v1",
    )


def _success(
    *tool_calls: ToolCall,
    usage: UsageAccounting | None = None,
    reasoning: str | None = None,
) -> ModelResult:
    return ModelResult(
        request_id="placeholder",
        outcome=ProviderOutcome.SUCCESS,
        returned_model="fake-model",
        tool_calls=tuple(tool_calls),
        provider_reasoning_content=reasoning,
        stop_reason="tool_calls",
        usage=(
            UsageAccounting(input_tokens=10, completion_tokens=3)
            if usage is None and tool_calls
            else usage
        ),
    )


def _tool_call(
    call_id: str,
    name: str,
    arguments: dict[str, object] | str,
) -> ToolCall:
    encoded = arguments if isinstance(arguments, str) else json.dumps(arguments, sort_keys=True)
    return ToolCall(
        id=call_id,
        function=ToolCallFunction(
            name=name,
            arguments=encoded,
        ),
    )


def _terminal_update_call() -> ToolCall:
    return _tool_call(
        "terminal-update",
        "update_ticket",
        {
            "expected_ticket_revision": 1,
            "status": "resolved",
            "resolution_reason_code": "RECORD_CONTRADICTION_RESOLVED",
            "evidence_document_ids": [],
            "operation_ids": [],
        },
    )


def _load_store(repo_root: Path, case_id: str) -> HarbourDeskStore:
    state = HarbourDeskVisibleState.model_validate_json(
        (
            repo_root / "benchmarks" / "harbourdesk" / "dev" / case_id / "initial_state.json"
        ).read_text(encoding="utf-8")
    )
    store = HarbourDeskStore.in_memory()
    store.initialize(state)
    return store


def _rules(repo_root: Path) -> HarbourDeskBusinessRules:
    return HarbourDeskBusinessRules.load(
        repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    )


def _environment(
    repo_root: Path,
    store: HarbourDeskStore,
    case_id: str,
) -> HarbourDeskEnvironment:
    state = store.snapshot()
    ticket = state.tickets[0]
    if ticket.ticket_id != f"ticket-{case_id[-3:]}":
        raise ValueError(f"unexpected ticket identity for {case_id}")
    return HarbourDeskEnvironment(
        store=store,
        rules=_rules(repo_root),
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.ticket_id,
    )


def _operation(
    *,
    operation_id: str,
    idempotency_key: str,
    arguments_hash: str,
    before_revision: int,
    after_revision: int,
) -> OperationRecord:
    return OperationRecord(
        operation_id=operation_id,
        tenant_id="tenant-001",
        account_id="acct-001",
        action=ApprovalAction.RECONCILE_ENTITLEMENT,
        idempotency_key=idempotency_key,
        arguments_hash=arguments_hash,
        status=OperationStatus.COMMITTED,
        before_revision=before_revision,
        after_revision=after_revision,
        effective_write=True,
    )


def _effective_write_count(state: HarbourDeskVisibleState) -> int:
    return sum(operation.effective_write for operation in state.operations)


def _state_sha256(state: HarbourDeskVisibleState) -> str:
    payload = state.model_dump_json(exclude_none=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
