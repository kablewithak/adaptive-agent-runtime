from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from adaptive_runtime.contracts.provider import (
    ChatRole,
    ModelRequest,
    ModelResult,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolCallFunction,
    UsageAccounting,
)
from adaptive_runtime.environment.domain import (
    ApprovalAction,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.environment.model_observation import ModelVisibleInitialObservation
from adaptive_runtime.environment.read_tools import (
    ReadToolErrorCode,
    ReadToolName,
    ReadToolResult,
    ReadToolStatus,
    TicketObservation,
)
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    HarbourDeskEnvironment,
    ReadEnvironmentCall,
    WriteEnvironmentCall,
)
from adaptive_runtime.environment.write_tools import (
    TicketWriteObservation,
    UpdateTicketArgs,
    WriteToolName,
    WriteToolResult,
    WriteToolStatus,
)
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveRunBudget,
    LiveStopCategory,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink


class FakeProvider:
    def __init__(self, outcomes: Iterable[ModelResult]) -> None:
        self._outcomes = iter(outcomes)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return next(self._outcomes).model_copy(update={"request_id": request.request_id})


class FakeEnvironment:
    def __init__(self) -> None:
        self._ticket = Ticket(
            ticket_id="ticket-001",
            tenant_id="tenant-001",
            account_id="account-001",
            requesting_contact="owner@example.test",
            initial_text="Please inspect and resolve this synthetic support ticket.",
            status=TicketStatus.OPEN,
            revision=1,
        )
        self.execute_count = 0
        self.write_count = 0
        self.received_calls: list[EnvironmentCall] = []

    @property
    def tenant_id(self) -> str:
        return self._ticket.tenant_id

    @property
    def ticket_id(self) -> str:
        return self._ticket.ticket_id

    def initial_observation(self) -> ModelVisibleInitialObservation:
        return ModelVisibleInitialObservation(
            frozen_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
            tenant_id=self.tenant_id,
            ticket=self._ticket,
            approvals=(),
        )

    def execute(self, call: EnvironmentCall) -> ReadToolResult | WriteToolResult:
        self.execute_count += 1
        self.received_calls.append(call)
        if isinstance(call, ReadEnvironmentCall):
            if call.tool is ReadToolName.GET_TICKET:
                return ReadToolResult(
                    call_id=call.call_id,
                    tool=call.tool,
                    status=ReadToolStatus.OK,
                    data=TicketObservation(ticket=self._ticket),
                )
            return ReadToolResult(
                call_id=call.call_id,
                tool=call.tool,
                status=ReadToolStatus.ERROR,
                error_code=ReadToolErrorCode.NOT_FOUND,
                message="synthetic read not found",
            )

        self.write_count += 1
        assert call.tool is WriteToolName.UPDATE_TICKET
        args = UpdateTicketArgs.model_validate(call.arguments)
        updated = self._ticket.model_copy(
            update={
                "status": args.status,
                "resolution_reason_code": args.resolution_reason_code,
                "evidence_document_ids": args.evidence_document_ids,
                "operation_ids": args.operation_ids,
                "revision": self._ticket.revision + 1,
            }
        )
        operation = OperationRecord(
            operation_id=f"operation-{self.execute_count}",
            tenant_id=self.tenant_id,
            account_id=self._ticket.account_id,
            action=ApprovalAction.UPDATE_TICKET,
            idempotency_key=call.idempotency_key,
            arguments_hash="0" * 64,
            status=OperationStatus.COMMITTED,
            before_revision=self._ticket.revision,
            after_revision=updated.revision,
            effective_write=False,
        )
        self._ticket = updated
        return WriteToolResult(
            call_id=call.call_id,
            tool=call.tool,
            status=WriteToolStatus.OK,
            data=TicketWriteObservation(ticket=updated, operation=operation),
        )

    def snapshot(self) -> HarbourDeskVisibleState:
        return HarbourDeskVisibleState(
            frozen_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
            tenants=(),
            accounts=(),
            subscriptions=(),
            entitlements=(),
            tickets=(self._ticket,),
            policies=(),
            approvals=(),
            operations=(),
        )


def _tool_call(call_id: str, name: str, arguments: dict[str, object] | str) -> ToolCall:
    encoded = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(
        id=call_id,
        function=ToolCallFunction(name=name, arguments=encoded),
    )


def _success(
    *tool_calls: ToolCall,
    reasoning: str | None = None,
) -> ModelResult:
    return ModelResult(
        request_id="placeholder",
        outcome=ProviderOutcome.SUCCESS,
        returned_model="fake-model",
        tool_calls=tool_calls,
        provider_reasoning_content=reasoning,
        stop_reason="tool_calls",
        usage=UsageAccounting(input_tokens=50, completion_tokens=10),
    )


def _profile() -> LiveModelProfile:
    return LiveModelProfile(
        model_id="fake-model",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        thinking=True,
    )


def _run(
    provider: FakeProvider,
    environment: FakeEnvironment,
    **kwargs: object,
):
    return run_live_harbourdesk(
        provider=provider,
        environment=cast(HarbourDeskEnvironment, environment),
        run_id="run-m3b-test",
        model_profile=_profile(),
        **kwargs,
    )


def _terminal_update() -> ToolCall:
    return _tool_call(
        "provider-write-1",
        WriteToolName.UPDATE_TICKET.value,
        {
            "expected_ticket_revision": 1,
            "status": "resolved",
            "resolution_reason_code": "RECORD_CONTRADICTION_RESOLVED",
            "evidence_document_ids": [],
            "operation_ids": [],
        },
    )


def test_two_read_batch_realizes_in_provider_order_and_continues(tmp_path: Path) -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("provider-read-1", ReadToolName.GET_TICKET.value, {}),
                _tool_call(
                    "provider-read-2",
                    ReadToolName.GET_ACCOUNT.value,
                    {"account_id": "account-001"},
                ),
                reasoning="EPHEMERAL_BATCH_REASONING",
            ),
            _success(_terminal_update()),
        )
    )
    environment = FakeEnvironment()
    trace_path = tmp_path / "trace.jsonl"

    result = _run(provider, environment, trace_sink=JsonlTraceSink(trace_path))

    assert result.trace.stop_category is LiveStopCategory.TICKET_TERMINAL
    assert [call.tool.value for call in environment.received_calls] == [
        ReadToolName.GET_TICKET.value,
        ReadToolName.GET_ACCOUNT.value,
        WriteToolName.UPDATE_TICKET.value,
    ]
    assert environment.write_count == 1

    continuation_messages = provider.requests[1].messages
    tool_messages = [message for message in continuation_messages if message.role is ChatRole.TOOL]
    assert [message.tool_call_id for message in tool_messages] == [
        "provider-read-1",
        "provider-read-2",
    ]
    assert [message.name for message in tool_messages] == [
        ReadToolName.GET_TICKET.value,
        ReadToolName.GET_ACCOUNT.value,
    ]

    durable_trace = trace_path.read_text(encoding="utf-8")
    assert "EPHEMERAL_BATCH_REASONING" not in durable_trace
    events = [json.loads(line) for line in durable_trace.splitlines()]
    batch_events = [event for event in events if event["event"] == "multi_tool_batch_preflight"]
    assert batch_events == [
        {
            "event": "multi_tool_batch_preflight",
            "recorded_at": batch_events[0]["recorded_at"],
            "run_id": "run-m3b-test",
            "attempt_index": 1,
            "provider_tool_call_ids": ["provider-read-1", "provider-read-2"],
            "tool_names": [
                ReadToolName.GET_TICKET.value,
                ReadToolName.GET_ACCOUNT.value,
            ],
            "accepted": True,
        }
    ]
    action_events = [event for event in events if event["event"] == "tool_action_finished"]
    assert [event["action"]["provider_tool_call_id"] for event in action_events] == [
        "provider-read-1",
        "provider-read-2",
        "provider-write-1",
    ]


def test_three_read_batch_realizes_in_provider_order() -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("provider-read-1", ReadToolName.GET_TICKET.value, {}),
                _tool_call(
                    "provider-read-2",
                    ReadToolName.GET_ACCOUNT.value,
                    {"account_id": "account-001"},
                ),
                _tool_call(
                    "provider-read-3",
                    ReadToolName.GET_SUBSCRIPTION.value,
                    {"subscription_id": "subscription-001"},
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(
        provider,
        environment,
        budget=LiveRunBudget(max_model_calls=1),
    )

    assert result.trace.stop_category is LiveStopCategory.MODEL_CALL_BUDGET_EXHAUSTED
    assert [call.tool.value for call in environment.received_calls] == [
        ReadToolName.GET_TICKET.value,
        ReadToolName.GET_ACCOUNT.value,
        ReadToolName.GET_SUBSCRIPTION.value,
    ]
    assert environment.write_count == 0


@pytest.mark.parametrize(
    "tool_calls",
    (
        (
            _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
            _terminal_update(),
        ),
        (
            _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
            _tool_call("unknown-2", "unknown_tool", {}),
        ),
        (
            _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
            _tool_call("bad-2", ReadToolName.GET_ACCOUNT.value, "{not-json"),
        ),
        (
            _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
            _tool_call("bad-schema-2", ReadToolName.GET_ACCOUNT.value, {}),
        ),
        (
            _tool_call("read-1", ReadToolName.GET_ACCOUNT.value, {"account_id": "a"}),
            _tool_call(
                "scope-2",
                ReadToolName.GET_TICKET.value,
                {"ticket_id": "ticket-foreign"},
            ),
        ),
    ),
)
def test_rejected_multi_tool_batch_executes_no_prefix(
    tool_calls: tuple[ToolCall, ToolCall],
) -> None:
    provider = FakeProvider((_success(*tool_calls),))
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0
    assert environment.write_count == 0
    assert result.trace.tool_actions == ()


def test_rejected_batch_trace_records_sanitized_reason(tmp_path: Path) -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
                _terminal_update(),
                reasoning="SHOULD_NOT_PERSIST",
            ),
        )
    )
    environment = FakeEnvironment()
    trace_path = tmp_path / "rejected-trace.jsonl"

    result = _run(provider, environment, trace_sink=JsonlTraceSink(trace_path))

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0
    durable_trace = trace_path.read_text(encoding="utf-8")
    assert "SHOULD_NOT_PERSIST" not in durable_trace
    events = [json.loads(line) for line in durable_trace.splitlines()]
    batch_event = next(event for event in events if event["event"] == "multi_tool_batch_preflight")
    assert batch_event["accepted"] is False
    assert batch_event["rejection_reason"] == "contains_write"
    assert batch_event["provider_tool_call_ids"] == ["read-1", "provider-write-1"]


def test_duplicate_provider_call_id_rejects_entire_batch() -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("duplicate-id", ReadToolName.GET_TICKET.value, {}),
                _tool_call(
                    "duplicate-id",
                    ReadToolName.GET_ACCOUNT.value,
                    {"account_id": "account-001"},
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0


def test_duplicate_normalized_read_rejects_entire_batch() -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call(
                    "search-1",
                    ReadToolName.SEARCH_POLICIES.value,
                    {"query": "cancellation"},
                ),
                _tool_call(
                    "search-2",
                    ReadToolName.SEARCH_POLICIES.value,
                    {"query": "cancellation", "max_results": 5},
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0


def test_remaining_action_budget_rejects_entire_batch() -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
                _tool_call(
                    "read-2",
                    ReadToolName.GET_ACCOUNT.value,
                    {"account_id": "account-001"},
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(
        provider,
        environment,
        budget=LiveRunBudget(max_tool_actions=1),
    )

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0


def test_single_tool_write_behavior_remains_unchanged() -> None:
    provider = FakeProvider((_success(_terminal_update()),))
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.TICKET_TERMINAL
    assert environment.execute_count == 1
    assert environment.write_count == 1
    assert isinstance(environment.received_calls[0], WriteEnvironmentCall)


def test_deadline_interrupts_read_batch_without_partial_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(
        (
            _success(
                _tool_call("read-1", ReadToolName.GET_TICKET.value, {}),
                _tool_call(
                    "read-2",
                    ReadToolName.GET_ACCOUNT.value,
                    {"account_id": "account-001"},
                ),
                _tool_call(
                    "read-3",
                    ReadToolName.GET_SUBSCRIPTION.value,
                    {"subscription_id": "subscription-001"},
                ),
            ),
        )
    )
    environment = FakeEnvironment()
    deadline_checks = iter((False, False, True))

    def fake_deadline_exceeded(*_args: object) -> bool:
        return next(deadline_checks)

    monkeypatch.setattr(
        "adaptive_runtime.runtime.harbourdesk_live._trajectory_deadline_exceeded",
        fake_deadline_exceeded,
    )

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.TRAJECTORY_DEADLINE_EXCEEDED
    assert environment.execute_count == 1
    assert environment.write_count == 0
    assert len(result.trace.tool_actions) == 1
