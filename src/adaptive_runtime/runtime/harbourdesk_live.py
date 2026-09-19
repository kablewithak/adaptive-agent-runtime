from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolDefinition,
    ToolFunction,
    UsageAccounting,
)
from adaptive_runtime.environment.domain import HarbourDeskVisibleState, TicketStatus
from adaptive_runtime.environment.read_tools import (
    GetAccountArgs,
    GetEntitlementsArgs,
    GetOperationArgs,
    GetSubscriptionArgs,
    GetTicketArgs,
    ReadPolicyArgs,
    ReadToolName,
    SearchPoliciesArgs,
)
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    HarbourDeskEnvironment,
    ReadEnvironmentCall,
    WriteEnvironmentCall,
)
from adaptive_runtime.environment.write_tools import (
    ReconcileEntitlementArgs,
    ScheduleCancellationArgs,
    UpdateTicketArgs,
    WriteToolName,
)
from adaptive_runtime.providers.base import ProviderAdapter, ProviderCallError
from adaptive_runtime.runtime.multi_tool_contract import (
    M3A_REALIZABLE_READ_TOOL_NAMES,
    MultiToolBatchPreflight,
    MultiToolBatchRejectionReason,
    PreparedMultiToolRead,
)
from adaptive_runtime.runtime.trace import NullTraceSink, TraceEvent, TraceSink


class LiveRuntimeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LiveStopCategory(StrEnum):
    TICKET_TERMINAL = "ticket_terminal"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_REFUSAL = "provider_refusal"
    INVALID_TOOL_CALL = "invalid_tool_call"
    MULTI_TOOL_CALL = "multi_tool_call"
    MODEL_TEXT_WITHOUT_TERMINAL = "model_text_without_terminal"
    MODEL_CALL_BUDGET_EXHAUSTED = "model_call_budget_exhausted"
    TOOL_ACTION_BUDGET_EXHAUSTED = "tool_action_budget_exhausted"
    TRAJECTORY_DEADLINE_EXCEEDED = "trajectory_deadline_exceeded"


class UsageObservationStatus(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN_AFTER_ERROR = "unknown_after_error"


class LiveRunIdentity(LiveRuntimeContract):
    run_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._-]+$",
    )


class LiveRunBudget(LiveRuntimeContract):
    max_model_calls: int = Field(default=12, ge=1, le=50)
    max_tool_actions: int = Field(default=18, ge=1, le=100)
    trajectory_deadline_seconds: float = Field(default=480.0, gt=0, le=3600)
    request_deadline_seconds: float = Field(default=60.0, gt=0, le=300)
    max_completion_tokens: int = Field(default=768, gt=0, le=8192)


class LiveModelProfile(LiveRuntimeContract):
    model_id: str = Field(min_length=1, max_length=200)
    protocol: ProviderProtocol
    thinking: bool | None = None
    profile_version: str = Field(default="m0b-v1", min_length=1, max_length=100)


class ProviderAttemptTrace(LiveRuntimeContract):
    attempt_index: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=200)
    requested_model: str = Field(min_length=1, max_length=200)
    returned_model: str | None = Field(default=None, max_length=200)
    outcome: ProviderOutcome
    usage_status: UsageObservationStatus
    usage: UsageAccounting | None = None
    provider_request_id: str | None = Field(default=None, max_length=300)
    http_status: int | None = Field(default=None, ge=100, le=599)
    latency_ms: int | None = Field(default=None, ge=0)
    stop_reason: str | None = Field(default=None, max_length=200)
    error_code: ProviderErrorCode | None = None
    retryable: bool = False


class ToolActionTrace(LiveRuntimeContract):
    action_index: int = Field(ge=1)
    provider_tool_call_id: str = Field(min_length=1, max_length=300)
    environment_call_id: str = Field(min_length=1, max_length=100)
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, object]
    status: str = Field(min_length=1, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    result: dict[str, object]


class LiveTrajectoryTrace(LiveRuntimeContract):
    schema_version: str = "m0b-v1"
    run_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    model_profile: LiveModelProfile
    budget: LiveRunBudget
    initial_observation_schema_version: str = Field(min_length=1, max_length=100)
    started_at: datetime
    ended_at: datetime
    stop_category: LiveStopCategory
    attempts: tuple[ProviderAttemptTrace, ...]
    tool_actions: tuple[ToolActionTrace, ...]
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LiveRunResult(LiveRuntimeContract):
    trace: LiveTrajectoryTrace
    final_state: HarbourDeskVisibleState


class RunStartedTraceEvent(TraceEvent):
    event: Literal["run_started"] = "run_started"
    recorded_at: datetime
    run_id: str
    tenant_id: str
    ticket_id: str
    model_profile: LiveModelProfile
    budget: LiveRunBudget
    initial_observation_schema_version: str


class AttemptStartedTraceEvent(TraceEvent):
    event: Literal["attempt_started"] = "attempt_started"
    recorded_at: datetime
    run_id: str
    attempt_index: int = Field(ge=1)
    request_id: str
    requested_model: str


class AttemptFinishedTraceEvent(TraceEvent):
    event: Literal["attempt_finished"] = "attempt_finished"
    recorded_at: datetime
    run_id: str
    attempt: ProviderAttemptTrace


class ToolActionFinishedTraceEvent(TraceEvent):
    event: Literal["tool_action_finished"] = "tool_action_finished"
    recorded_at: datetime
    run_id: str
    action: ToolActionTrace


class MultiToolBatchPreflightTraceEvent(TraceEvent):
    event: Literal["multi_tool_batch_preflight"] = "multi_tool_batch_preflight"
    recorded_at: datetime
    run_id: str
    attempt_index: int = Field(ge=1)
    provider_tool_call_ids: tuple[str, ...]
    tool_names: tuple[str, ...]
    accepted: bool
    rejection_reason: MultiToolBatchRejectionReason | None = None


class RunFinishedTraceEvent(TraceEvent):
    event: Literal["run_finished"] = "run_finished"
    recorded_at: datetime
    run_id: str
    stop_category: LiveStopCategory
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


_READ_ARGUMENT_MODELS: Mapping[ReadToolName, type[BaseModel]] = {
    ReadToolName.GET_TICKET: GetTicketArgs,
    ReadToolName.GET_ACCOUNT: GetAccountArgs,
    ReadToolName.GET_SUBSCRIPTION: GetSubscriptionArgs,
    ReadToolName.GET_ENTITLEMENTS: GetEntitlementsArgs,
    ReadToolName.SEARCH_POLICIES: SearchPoliciesArgs,
    ReadToolName.READ_POLICY: ReadPolicyArgs,
    ReadToolName.GET_OPERATION: GetOperationArgs,
}
_WRITE_ARGUMENT_MODELS: Mapping[WriteToolName, type[BaseModel]] = {
    WriteToolName.RECONCILE_ENTITLEMENT: ReconcileEntitlementArgs,
    WriteToolName.SCHEDULE_CANCELLATION: ScheduleCancellationArgs,
    WriteToolName.UPDATE_TICKET: UpdateTicketArgs,
}
_TOOL_DESCRIPTIONS: Mapping[str, str] = {
    ReadToolName.GET_TICKET.value: "Read a ticket in the current tenant scope.",
    ReadToolName.GET_ACCOUNT.value: "Read an account in the current tenant scope.",
    ReadToolName.GET_SUBSCRIPTION.value: "Read a subscription referenced in tenant scope.",
    ReadToolName.GET_ENTITLEMENTS.value: "List entitlements for an account in tenant scope.",
    ReadToolName.SEARCH_POLICIES.value: "Search policy documents by lexical evidence.",
    ReadToolName.READ_POLICY.value: "Read one policy document by identifier.",
    ReadToolName.GET_OPERATION.value: "Inspect one prior operation in tenant scope.",
    WriteToolName.RECONCILE_ENTITLEMENT.value: (
        "Reconcile one entitlement under deterministic controls."
    ),
    WriteToolName.SCHEDULE_CANCELLATION.value: (
        "Schedule cancellation under deterministic controls."
    ),
    WriteToolName.UPDATE_TICKET.value: "Update only the current ticket disposition and evidence.",
}

_CALL_ADAPTER: TypeAdapter[EnvironmentCall] = TypeAdapter(EnvironmentCall)

_SYSTEM_PROMPT = """You operate one HarbourDesk support task inside a bounded tool runtime.
Use tools to gather evidence before acting. Never invent identifiers or hidden state.
Make at most one tool call per response. Tool results are authoritative.
The host controls tenant scope, the current ticket, call IDs, and idempotency keys.
Finish the task by updating the current ticket to resolved, pending_clarification, or escalated.
If evidence is ambiguous, request clarification. If an operation outcome is uncertain or a safe
write cannot be justified, escalate. Do not claim completion in prose while the ticket is open."""


def harbourdesk_tool_definitions() -> tuple[ToolDefinition, ...]:
    """Build model-facing tool schemas from the current deterministic argument contracts."""
    definitions: list[ToolDefinition] = []

    for read_tool, read_model in _READ_ARGUMENT_MODELS.items():
        schema = read_model.model_json_schema()
        if read_tool is ReadToolName.GET_TICKET:
            schema = _without_host_controlled_ticket_id(schema)
        definitions.append(_tool_definition(read_tool.value, schema))

    for write_tool, write_model in _WRITE_ARGUMENT_MODELS.items():
        schema = write_model.model_json_schema()
        if write_tool is WriteToolName.UPDATE_TICKET:
            schema = _without_host_controlled_ticket_id(schema)
        definitions.append(_tool_definition(write_tool.value, schema))

    return tuple(definitions)


def run_live_harbourdesk(
    *,
    provider: ProviderAdapter,
    environment: HarbourDeskEnvironment,
    run_id: str,
    model_profile: LiveModelProfile,
    budget: LiveRunBudget | None = None,
    trace_sink: TraceSink | None = None,
) -> LiveRunResult:
    """Run one model-driven HarbourDesk trajectory without retries or evaluator access."""
    validated_run_id = LiveRunIdentity(run_id=run_id).run_id
    current_budget = LiveRunBudget() if budget is None else budget
    sink: TraceSink = NullTraceSink() if trace_sink is None else trace_sink
    started_at = datetime.now(UTC)
    started_monotonic = monotonic()
    observation = environment.initial_observation()
    messages: list[ChatMessage] = [
        ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
        ChatMessage(
            role=ChatRole.USER,
            content=observation.model_dump_json(exclude_none=True),
        ),
    ]
    tools = harbourdesk_tool_definitions()
    attempts: list[ProviderAttemptTrace] = []
    tool_actions: list[ToolActionTrace] = []
    stop_category: LiveStopCategory | None = None
    sink.record(
        RunStartedTraceEvent(
            recorded_at=started_at,
            run_id=validated_run_id,
            tenant_id=environment.tenant_id,
            ticket_id=environment.ticket_id,
            model_profile=model_profile,
            budget=current_budget,
            initial_observation_schema_version=observation.schema_version,
        )
    )

    while stop_category is None:
        if _trajectory_deadline_exceeded(started_monotonic, current_budget):
            stop_category = LiveStopCategory.TRAJECTORY_DEADLINE_EXCEEDED
            break
        if len(attempts) >= current_budget.max_model_calls:
            stop_category = LiveStopCategory.MODEL_CALL_BUDGET_EXHAUSTED
            break

        attempt_index = len(attempts) + 1
        request_id = f"{validated_run_id}-model-{attempt_index:02d}"
        remaining = _remaining_deadline(started_monotonic, current_budget)
        request = ModelRequest(
            request_id=request_id,
            model_id=model_profile.model_id,
            protocol=model_profile.protocol,
            messages=tuple(messages),
            tools=tools,
            max_completion_tokens=current_budget.max_completion_tokens,
            thinking=model_profile.thinking,
            deadline_seconds=min(current_budget.request_deadline_seconds, remaining),
            experiment_reference=validated_run_id,
        )

        sink.record(
            AttemptStartedTraceEvent(
                recorded_at=datetime.now(UTC),
                run_id=validated_run_id,
                attempt_index=attempt_index,
                request_id=request.request_id,
                requested_model=request.model_id,
            )
        )
        try:
            model_result = provider.complete(request)
        except ProviderCallError as exc:
            attempt_trace = _provider_error_trace(attempt_index, request, exc)
            attempts.append(attempt_trace)
            sink.record(
                AttemptFinishedTraceEvent(
                    recorded_at=datetime.now(UTC),
                    run_id=validated_run_id,
                    attempt=attempt_trace,
                )
            )
            stop_category = LiveStopCategory.PROVIDER_ERROR
            break

        if model_result.request_id != request.request_id:
            attempt_trace = _provider_protocol_mismatch_trace(
                attempt_index,
                request,
                model_result,
            )
            attempts.append(attempt_trace)
            sink.record(
                AttemptFinishedTraceEvent(
                    recorded_at=datetime.now(UTC),
                    run_id=validated_run_id,
                    attempt=attempt_trace,
                )
            )
            stop_category = LiveStopCategory.PROVIDER_ERROR
            break

        attempt_trace = _provider_result_trace(attempt_index, request, model_result)
        attempts.append(attempt_trace)
        sink.record(
            AttemptFinishedTraceEvent(
                recorded_at=datetime.now(UTC),
                run_id=validated_run_id,
                attempt=attempt_trace,
            )
        )
        if model_result.outcome is ProviderOutcome.ERROR:
            stop_category = LiveStopCategory.PROVIDER_ERROR
            break
        if model_result.outcome is ProviderOutcome.REFUSAL:
            stop_category = LiveStopCategory.PROVIDER_REFUSAL
            break

        assistant_message = ChatMessage(
            role=ChatRole.ASSISTANT,
            content=model_result.text,
            tool_calls=model_result.tool_calls,
            provider_reasoning_content=model_result.provider_reasoning_content,
        )
        messages.append(assistant_message)

        if not model_result.tool_calls:
            stop_category = LiveStopCategory.MODEL_TEXT_WITHOUT_TERMINAL
            break

        if len(model_result.tool_calls) > 1:
            preflight = _preflight_multi_read_batch(
                provider_calls=model_result.tool_calls,
                ticket_id=environment.ticket_id,
                realized_action_count=len(tool_actions),
                budget=current_budget,
            )
            sink.record(
                MultiToolBatchPreflightTraceEvent(
                    recorded_at=datetime.now(UTC),
                    run_id=validated_run_id,
                    attempt_index=attempt_index,
                    provider_tool_call_ids=tuple(
                        call.id for call in model_result.tool_calls
                    ),
                    tool_names=tuple(
                        call.function.name for call in model_result.tool_calls
                    ),
                    accepted=preflight.accepted,
                    rejection_reason=preflight.rejection_reason,
                )
            )
            if not preflight.accepted:
                stop_category = LiveStopCategory.MULTI_TOOL_CALL
                break

            for prepared_read in preflight.prepared_reads:
                if _trajectory_deadline_exceeded(started_monotonic, current_budget):
                    stop_category = LiveStopCategory.TRAJECTORY_DEADLINE_EXCEEDED
                    break

                action_index = len(tool_actions) + 1
                read_environment_call = ReadEnvironmentCall(
                    call_id=f"{validated_run_id}-tool-{action_index:02d}",
                    tool=prepared_read.tool,
                    arguments=dict(prepared_read.arguments),
                )
                action_trace, tool_message = _realize_environment_call(
                    environment=environment,
                    environment_call=read_environment_call,
                    provider_tool_call_id=prepared_read.provider_tool_call_id,
                    provider_tool_name=prepared_read.tool.value,
                    action_index=action_index,
                )
                tool_actions.append(action_trace)
                sink.record(
                    ToolActionFinishedTraceEvent(
                        recorded_at=datetime.now(UTC),
                        run_id=validated_run_id,
                        action=action_trace,
                    )
                )
                messages.append(tool_message)

            if stop_category is not None:
                break
            continue

        if len(tool_actions) >= current_budget.max_tool_actions:
            stop_category = LiveStopCategory.TOOL_ACTION_BUDGET_EXHAUSTED
            break

        provider_tool_call = model_result.tool_calls[0]
        try:
            environment_call = _environment_call(
                run_id=validated_run_id,
                action_index=len(tool_actions) + 1,
                provider_call=provider_tool_call,
                ticket_id=environment.ticket_id,
            )
        except (ValueError, ValidationError):
            stop_category = LiveStopCategory.INVALID_TOOL_CALL
            break

        action_index = len(tool_actions) + 1
        action_trace, tool_message = _realize_environment_call(
            environment=environment,
            environment_call=environment_call,
            provider_tool_call_id=provider_tool_call.id,
            provider_tool_name=provider_tool_call.function.name,
            action_index=action_index,
        )
        tool_actions.append(action_trace)
        sink.record(
            ToolActionFinishedTraceEvent(
                recorded_at=datetime.now(UTC),
                run_id=validated_run_id,
                action=action_trace,
            )
        )
        messages.append(tool_message)

        if _current_ticket_status(environment) is not TicketStatus.OPEN:
            stop_category = LiveStopCategory.TICKET_TERMINAL

    if stop_category is None:  # pragma: no cover - loop exit invariant
        raise AssertionError("live run exited without a stop category")

    final_state = environment.snapshot()
    final_state_sha256 = _state_sha256(final_state)
    ended_at = datetime.now(UTC)
    sink.record(
        RunFinishedTraceEvent(
            recorded_at=ended_at,
            run_id=validated_run_id,
            stop_category=stop_category,
            final_state_sha256=final_state_sha256,
        )
    )
    trace = LiveTrajectoryTrace(
        run_id=validated_run_id,
        tenant_id=environment.tenant_id,
        ticket_id=environment.ticket_id,
        model_profile=model_profile,
        budget=current_budget,
        initial_observation_schema_version=observation.schema_version,
        started_at=started_at,
        ended_at=ended_at,
        stop_category=stop_category,
        attempts=tuple(attempts),
        tool_actions=tuple(tool_actions),
        final_state_sha256=final_state_sha256,
    )
    return LiveRunResult(trace=trace, final_state=final_state)


def _preflight_multi_read_batch(
    *,
    provider_calls: tuple[ToolCall, ...],
    ticket_id: str,
    realized_action_count: int,
    budget: LiveRunBudget,
) -> MultiToolBatchPreflight:
    remaining_action_budget = budget.max_tool_actions - realized_action_count
    if len(provider_calls) > remaining_action_budget:
        return MultiToolBatchPreflight(
            accepted=False,
            rejection_reason=MultiToolBatchRejectionReason.ACTION_BUDGET_EXCEEDED,
        )

    seen_provider_call_ids: set[str] = set()
    seen_normalized_reads: set[str] = set()
    prepared_reads: list[PreparedMultiToolRead] = []
    write_tool_names = {tool.value for tool in WriteToolName}

    for provider_call in provider_calls:
        if provider_call.id in seen_provider_call_ids:
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=(
                    MultiToolBatchRejectionReason.DUPLICATE_PROVIDER_CALL_ID
                ),
            )
        seen_provider_call_ids.add(provider_call.id)

        tool_name = provider_call.function.name
        if tool_name in write_tool_names:
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.CONTAINS_WRITE,
            )
        if tool_name not in M3A_REALIZABLE_READ_TOOL_NAMES:
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.UNKNOWN_TOOL,
            )

        try:
            parsed = json.loads(provider_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.MALFORMED_ARGUMENTS,
            )
        if not isinstance(parsed, dict):
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.MALFORMED_ARGUMENTS,
            )

        arguments: dict[str, object] = {str(key): value for key, value in parsed.items()}
        read_tool = ReadToolName(tool_name)
        if read_tool is ReadToolName.GET_TICKET:
            supplied_ticket_id = arguments.get("ticket_id")
            if supplied_ticket_id is not None and supplied_ticket_id != ticket_id:
                return MultiToolBatchPreflight(
                    accepted=False,
                    rejection_reason=(
                        MultiToolBatchRejectionReason.MALFORMED_ARGUMENTS
                    ),
                )
            arguments["ticket_id"] = ticket_id

        argument_model = _READ_ARGUMENT_MODELS[read_tool]
        try:
            validated_arguments = argument_model.model_validate(arguments)
        except ValidationError:
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.MALFORMED_ARGUMENTS,
            )

        normalized_arguments = validated_arguments.model_dump(
            mode="json",
            exclude_none=True,
        )
        normalized_signature = json.dumps(
            {
                "tool": read_tool.value,
                "arguments": normalized_arguments,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if normalized_signature in seen_normalized_reads:
            return MultiToolBatchPreflight(
                accepted=False,
                rejection_reason=MultiToolBatchRejectionReason.DUPLICATE_READ_CALL,
            )
        seen_normalized_reads.add(normalized_signature)
        prepared_reads.append(
            PreparedMultiToolRead(
                provider_tool_call_id=provider_call.id,
                tool=read_tool,
                arguments=normalized_arguments,
                normalized_signature=normalized_signature,
            )
        )

    return MultiToolBatchPreflight(
        accepted=True,
        prepared_reads=tuple(prepared_reads),
    )


def _realize_environment_call(
    *,
    environment: HarbourDeskEnvironment,
    environment_call: EnvironmentCall,
    provider_tool_call_id: str,
    provider_tool_name: str,
    action_index: int,
) -> tuple[ToolActionTrace, ChatMessage]:
    observed = environment.execute(environment_call)
    observed_payload = observed.model_dump(mode="json", exclude_none=True)
    action_trace = ToolActionTrace(
        action_index=action_index,
        provider_tool_call_id=provider_tool_call_id,
        environment_call_id=observed.call_id,
        tool=observed.tool.value,
        arguments=dict(environment_call.arguments),
        status=observed.status.value,
        error_code=(None if observed.error_code is None else observed.error_code.value),
        result=observed_payload,
    )
    tool_message = ChatMessage(
        role=ChatRole.TOOL,
        tool_call_id=provider_tool_call_id,
        name=provider_tool_name,
        content=json.dumps(observed_payload, sort_keys=True, separators=(",", ":")),
    )
    return action_trace, tool_message


def _tool_definition(name: str, parameters: dict[str, Any]) -> ToolDefinition:
    return ToolDefinition(
        function=ToolFunction(
            name=name,
            description=_TOOL_DESCRIPTIONS[name],
            parameters=parameters,
        )
    )


def _without_host_controlled_ticket_id(schema: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = json.loads(json.dumps(schema))
    properties = copied.get("properties")
    if isinstance(properties, dict):
        properties.pop("ticket_id", None)
    required = copied.get("required")
    if isinstance(required, list):
        remaining = [item for item in required if item != "ticket_id"]
        if remaining:
            copied["required"] = remaining
        else:
            copied.pop("required", None)
    return copied


def _environment_call(
    *,
    run_id: str,
    action_index: int,
    provider_call: ToolCall,
    ticket_id: str,
) -> EnvironmentCall:
    parsed = json.loads(provider_call.function.arguments)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must decode to an object")
    arguments: dict[str, object] = {str(key): value for key, value in parsed.items()}
    call_id = f"{run_id}-tool-{action_index:02d}"
    name = provider_call.function.name

    try:
        read_tool = ReadToolName(name)
    except ValueError:
        read_tool = None
    if read_tool is not None:
        if read_tool is ReadToolName.GET_TICKET:
            if "ticket_id" in arguments and arguments["ticket_id"] != ticket_id:
                raise ValueError("model cannot override the current ticket")
            arguments["ticket_id"] = ticket_id
        return _CALL_ADAPTER.validate_python(
            ReadEnvironmentCall(
                call_id=call_id,
                tool=read_tool,
                arguments=arguments,
            )
        )

    try:
        write_tool = WriteToolName(name)
    except ValueError as exc:
        raise ValueError("unknown HarbourDesk tool") from exc

    if write_tool is WriteToolName.UPDATE_TICKET:
        if "ticket_id" in arguments and arguments["ticket_id"] != ticket_id:
            raise ValueError("model cannot override the current ticket")
        arguments["ticket_id"] = ticket_id

    return _CALL_ADAPTER.validate_python(
        WriteEnvironmentCall(
            call_id=call_id,
            tool=write_tool,
            idempotency_key=_idempotency_key(run_id, provider_call.id, write_tool.value),
            arguments=arguments,
        )
    )


def _idempotency_key(run_id: str, provider_tool_call_id: str, tool: str) -> str:
    material = f"{run_id}\x1f{provider_tool_call_id}\x1f{tool}".encode()
    return f"m0b-{hashlib.sha256(material).hexdigest()}"


def _provider_result_trace(
    attempt_index: int,
    request: ModelRequest,
    result: ModelResult,
) -> ProviderAttemptTrace:
    return ProviderAttemptTrace(
        attempt_index=attempt_index,
        request_id=request.request_id,
        requested_model=request.model_id,
        returned_model=result.returned_model,
        outcome=result.outcome,
        usage_status=(
            UsageObservationStatus.OBSERVED
            if result.usage is not None
            else UsageObservationStatus.MISSING
        ),
        usage=result.usage,
        provider_request_id=result.provider_request_id,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        stop_reason=result.stop_reason,
        error_code=result.error_code,
        retryable=result.retryable,
    )


def _provider_protocol_mismatch_trace(
    attempt_index: int,
    request: ModelRequest,
    result: ModelResult,
) -> ProviderAttemptTrace:
    return ProviderAttemptTrace(
        attempt_index=attempt_index,
        request_id=request.request_id,
        requested_model=request.model_id,
        returned_model=result.returned_model,
        outcome=ProviderOutcome.ERROR,
        usage_status=(
            UsageObservationStatus.OBSERVED
            if result.usage is not None
            else UsageObservationStatus.MISSING
        ),
        usage=result.usage,
        provider_request_id=result.provider_request_id,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        stop_reason=result.stop_reason,
        error_code=ProviderErrorCode.PROTOCOL_ERROR,
        retryable=False,
    )


def _provider_error_trace(
    attempt_index: int,
    request: ModelRequest,
    exc: ProviderCallError,
) -> ProviderAttemptTrace:
    return ProviderAttemptTrace(
        attempt_index=attempt_index,
        request_id=request.request_id,
        requested_model=request.model_id,
        outcome=ProviderOutcome.ERROR,
        usage_status=UsageObservationStatus.UNKNOWN_AFTER_ERROR,
        usage=None,
        http_status=exc.http_status,
        error_code=exc.code,
        retryable=exc.retryable,
    )


def _trajectory_deadline_exceeded(started: float, budget: LiveRunBudget) -> bool:
    return monotonic() - started >= budget.trajectory_deadline_seconds


def _remaining_deadline(started: float, budget: LiveRunBudget) -> float:
    return max(0.001, budget.trajectory_deadline_seconds - (monotonic() - started))


def _current_ticket_status(environment: HarbourDeskEnvironment) -> TicketStatus:
    ticket = next(
        item
        for item in environment.snapshot().tickets
        if item.ticket_id == environment.ticket_id and item.tenant_id == environment.tenant_id
    )
    return ticket.status


def _state_sha256(state: HarbourDeskVisibleState) -> str:
    payload = state.model_dump_json(exclude_none=True).encode()
    return hashlib.sha256(payload).hexdigest()
