from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from adaptive_runtime.contracts.provider import (
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
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
from adaptive_runtime.evaluation.expected import (
    ExpectedCaseOutcome,
    ExpectedDisposition,
    ExpectedTerminalPredicate,
)
from adaptive_runtime.evaluation.scorer import score_case
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveRunBudget,
    LiveStopCategory,
    UsageObservationStatus,
    harbourdesk_tool_definitions,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink


class FakeProvider:
    def __init__(self, outcomes: Iterable[ModelResult | ProviderCallError]) -> None:
        self._outcomes = iter(outcomes)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        outcome = next(self._outcomes)
        if isinstance(outcome, ProviderCallError):
            raise outcome
        return outcome.model_copy(update={"request_id": request.request_id})


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
            assert call.tool is ReadToolName.GET_TICKET
            return ReadToolResult(
                call_id=call.call_id,
                tool=call.tool,
                status=ReadToolStatus.OK,
                data=TicketObservation(ticket=self._ticket),
            )

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
    request_id: str,
    *,
    tool_calls: tuple[ToolCall, ...],
    usage: UsageAccounting | None = None,
    reasoning: str | None = None,
) -> ModelResult:
    return ModelResult(
        request_id=request_id,
        outcome=ProviderOutcome.SUCCESS,
        returned_model="fake-model",
        tool_calls=tool_calls,
        provider_reasoning_content=reasoning,
        stop_reason="tool_calls",
        usage=usage,
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
        run_id="run-test",
        model_profile=_profile(),
        **kwargs,
    )


def test_tool_schema_hides_host_controlled_ticket_id() -> None:
    definitions = {tool.function.name: tool for tool in harbourdesk_tool_definitions()}
    for tool_name in (ReadToolName.GET_TICKET.value, WriteToolName.UPDATE_TICKET.value):
        schema = definitions[tool_name].function.parameters
        properties = cast(dict[str, object], schema["properties"])
        assert "ticket_id" not in properties
        assert "ticket_id" not in cast(list[str], schema.get("required", []))


def test_valid_continuation_reaches_terminal_ticket_and_sanitizes_trace(tmp_path: Path) -> None:
    provider = FakeProvider(
        (
            _success(
                "ignored-by-runner-1",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
                ),
                usage=UsageAccounting(input_tokens=100, completion_tokens=12),
                reasoning="EPHEMERAL_PROVIDER_REASONING",
            ),
            _success(
                "ignored-by-runner-2",
                tool_calls=(
                    _tool_call(
                        "provider-call-2",
                        WriteToolName.UPDATE_TICKET.value,
                        {
                            "expected_ticket_revision": 1,
                            "status": "resolved",
                            "resolution_reason_code": "RECORD_CONTRADICTION_RESOLVED",
                            "evidence_document_ids": [],
                            "operation_ids": [],
                        },
                    ),
                ),
                usage=UsageAccounting(input_tokens=130, completion_tokens=18),
            ),
        )
    )
    environment = FakeEnvironment()
    trace_path = tmp_path / "trace.jsonl"

    result = _run(
        provider,
        environment,
        trace_sink=JsonlTraceSink(trace_path),
    )

    assert result.trace.stop_category is LiveStopCategory.TICKET_TERMINAL
    assert len(result.trace.attempts) == 2
    assert len(result.trace.tool_actions) == 2
    assert result.trace.attempts[0].usage_status is UsageObservationStatus.OBSERVED
    assert result.final_state.tickets[0].status is TicketStatus.RESOLVED

    second_request = provider.requests[1]
    assistant_messages = [
        message for message in second_request.messages if message.role.value == "assistant"
    ]
    assert assistant_messages[0].provider_reasoning_content == "EPHEMERAL_PROVIDER_REASONING"

    update_call = cast(WriteEnvironmentCall, environment.received_calls[1])
    assert update_call.arguments["ticket_id"] == "ticket-001"
    assert update_call.idempotency_key.startswith("m0b-")

    durable_trace = trace_path.read_text(encoding="utf-8")
    assert "EPHEMERAL_PROVIDER_REASONING" not in durable_trace
    events = [json.loads(line) for line in durable_trace.splitlines()]
    assert [event["event"] for event in events] == [
        "run_started",
        "attempt_started",
        "attempt_finished",
        "tool_action_finished",
        "attempt_started",
        "attempt_finished",
        "tool_action_finished",
        "run_finished",
    ]


def test_provider_exception_records_unknown_usage_without_retry(tmp_path: Path) -> None:
    provider = FakeProvider(
        (
            ProviderCallError(
                code=ProviderErrorCode.PROVIDER_TIMEOUT,
                message="synthetic timeout",
                retryable=True,
            ),
        )
    )
    environment = FakeEnvironment()
    trace_path = tmp_path / "trace.jsonl"

    result = _run(provider, environment, trace_sink=JsonlTraceSink(trace_path))

    assert result.trace.stop_category is LiveStopCategory.PROVIDER_ERROR
    assert len(provider.requests) == 1
    assert result.trace.attempts[0].usage_status is UsageObservationStatus.UNKNOWN_AFTER_ERROR
    assert result.trace.attempts[0].usage is None
    assert result.trace.attempts[0].error_code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert environment.execute_count == 0

    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert events[1]["event"] == "attempt_started"
    assert events[2]["event"] == "attempt_finished"
    assert events[2]["attempt"]["usage_status"] == "unknown_after_error"


def test_success_without_usage_is_marked_missing() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
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
    assert result.trace.attempts[0].usage_status is UsageObservationStatus.MISSING


def test_multi_tool_response_executes_nothing() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
                    _tool_call(
                        "provider-call-2",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    assert environment.execute_count == 0
    assert result.trace.tool_actions == ()


def test_malformed_tool_arguments_execute_nothing() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        "{not-json",
                    ),
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.INVALID_TOOL_CALL
    assert environment.execute_count == 0


def test_model_call_budget_stops_before_second_dispatch() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
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
    assert len(provider.requests) == 1
    assert environment.execute_count == 1


def test_tool_action_budget_rejects_second_action_before_execution() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result-1",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
                ),
            ),
            _success(
                "provider-result-2",
                tool_calls=(
                    _tool_call(
                        "provider-call-2",
                        ReadToolName.GET_TICKET.value,
                        {},
                    ),
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

    assert result.trace.stop_category is LiveStopCategory.TOOL_ACTION_BUDGET_EXHAUSTED
    assert len(provider.requests) == 2
    assert environment.execute_count == 1


def test_final_state_can_be_scored_only_after_runtime_returns() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        WriteToolName.UPDATE_TICKET.value,
                        {
                            "expected_ticket_revision": 1,
                            "status": "resolved",
                            "resolution_reason_code": "RECORD_CONTRADICTION_RESOLVED",
                            "evidence_document_ids": [],
                            "operation_ids": [],
                        },
                    ),
                ),
            ),
        )
    )
    environment = FakeEnvironment()
    initial_state = environment.snapshot()

    result = _run(provider, environment)
    expected = ExpectedCaseOutcome(
        case_id="synthetic-runtime-case",
        terminal_ticket_id="ticket-001",
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.RESOLUTION,
                reason_code="RECORD_CONTRADICTION_RESOLVED",
                expected_effective_write_count=0,
            ),
        ),
    )

    score = score_case(initial_state, result.final_state, expected)

    assert result.trace.stop_category is LiveStopCategory.TICKET_TERMINAL
    assert score.passed


def test_text_only_completion_does_not_close_open_ticket() -> None:
    provider = FakeProvider(
        (
            ModelResult(
                request_id="provider-result",
                outcome=ProviderOutcome.SUCCESS,
                returned_model="fake-model",
                text="I have completed the task.",
                usage=UsageAccounting(input_tokens=50, completion_tokens=6),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.MODEL_TEXT_WITHOUT_TERMINAL
    assert result.final_state.tickets[0].status is TicketStatus.OPEN
    assert environment.execute_count == 0


def test_model_cannot_override_host_ticket_scope() -> None:
    provider = FakeProvider(
        (
            _success(
                "provider-result",
                tool_calls=(
                    _tool_call(
                        "provider-call-1",
                        ReadToolName.GET_TICKET.value,
                        {"ticket_id": "ticket-foreign"},
                    ),
                ),
            ),
        )
    )
    environment = FakeEnvironment()

    result = _run(provider, environment)

    assert result.trace.stop_category is LiveStopCategory.INVALID_TOOL_CALL
    assert environment.execute_count == 0


def test_trace_sink_refuses_to_append_to_existing_run(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("existing evidence\n", encoding="utf-8")

    try:
        JsonlTraceSink(trace_path)
    except FileExistsError:
        pass
    else:  # pragma: no cover - fail-closed guard
        raise AssertionError("existing trace path must be rejected")


def test_provider_request_identity_mismatch_fails_closed() -> None:
    class WrongRequestProvider:
        def complete(self, request: ModelRequest) -> ModelResult:
            return ModelResult(
                request_id="wrong-request-id",
                outcome=ProviderOutcome.SUCCESS,
                returned_model=request.model_id,
                text="unexpected mismatched result",
                usage=UsageAccounting(input_tokens=20, completion_tokens=4),
            )

    environment = FakeEnvironment()
    result = run_live_harbourdesk(
        provider=WrongRequestProvider(),
        environment=cast(HarbourDeskEnvironment, environment),
        run_id="run-identity-mismatch",
        model_profile=_profile(),
    )

    assert result.trace.stop_category is LiveStopCategory.PROVIDER_ERROR
    assert result.trace.attempts[0].error_code is ProviderErrorCode.PROTOCOL_ERROR
    assert result.trace.attempts[0].usage_status is UsageObservationStatus.OBSERVED
    assert environment.execute_count == 0
