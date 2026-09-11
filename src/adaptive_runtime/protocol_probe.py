from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.protocol_probe import (
    ProtocolCapabilityReceipt,
    ProtocolProbeKind,
    ProtocolProbeObservation,
    ProtocolProbeStatus,
)
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolChoice,
    ToolChoiceMode,
    ToolDefinition,
    ToolFunction,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter

_EXPECTED_JSON = {"fixture_id": "fixture-17", "value": 42}
_TOOL_RESULT_TEXT = '{"fixture_id":"fixture-17","value":42}'
_TERMINAL_ERROR_CODES = {
    ProviderErrorCode.AUTHENTICATION_FAILED,
    ProviderErrorCode.ENTITLEMENT_DENIED,
    ProviderErrorCode.RATE_LIMITED,
    ProviderErrorCode.QUOTA_EXHAUSTED,
    ProviderErrorCode.PROVIDER_UNAVAILABLE,
}


class _StrictProbeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _JsonFixture(_StrictProbeModel):
    fixture_id: Literal["fixture-17"]
    value: Literal[42]


class _ToolArguments(_StrictProbeModel):
    fixture_id: Literal["fixture-17"]


def recommended_inter_call_seconds(model_id: str) -> float:
    if model_id.startswith("deepseek-v4-"):
        return 22.0
    return 1.0


def _receipt_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _observation_from_result(
    *,
    kind: ProtocolProbeKind,
    result: ModelResult,
    passed: bool,
    condition_code: str,
) -> ProtocolProbeObservation:
    return ProtocolProbeObservation(
        kind=kind,
        status=ProtocolProbeStatus.PASS if passed else ProtocolProbeStatus.FAIL,
        http_status=result.http_status,
        returned_model=result.returned_model,
        stop_reason=result.stop_reason,
        latency_ms=result.latency_ms,
        usage_present=result.usage is not None,
        usage=result.usage,
        error_code=result.error_code,
        retryable=result.retryable,
        condition_code=condition_code,
    )


def _observation_from_error(
    *,
    kind: ProtocolProbeKind,
    error: ProviderCallError,
) -> ProtocolProbeObservation:
    return ProtocolProbeObservation(
        kind=kind,
        status=ProtocolProbeStatus.FAIL,
        http_status=error.http_status,
        returned_model=None,
        stop_reason=None,
        latency_ms=None,
        usage_present=False,
        usage=None,
        error_code=error.code,
        retryable=error.retryable,
        condition_code="provider_call_error",
    )


def _skipped_observation(
    *,
    kind: ProtocolProbeKind,
    condition_code: str,
) -> ProtocolProbeObservation:
    return ProtocolProbeObservation(
        kind=kind,
        status=ProtocolProbeStatus.SKIPPED,
        http_status=None,
        returned_model=None,
        stop_reason=None,
        latency_ms=None,
        usage_present=False,
        usage=None,
        error_code=None,
        retryable=False,
        condition_code=condition_code,
    )


class _ProbeRunner:
    def __init__(
        self,
        *,
        adapter: HuaweiOpenAIAdapter,
        inter_call_seconds: float,
        sleep_fn: Callable[[float], None],
    ) -> None:
        self._adapter = adapter
        self._inter_call_seconds = inter_call_seconds
        self._sleep_fn = sleep_fn
        self._call_count = 0

    def complete(self, request: ModelRequest) -> ModelResult:
        if self._call_count > 0 and self._inter_call_seconds > 0:
            self._sleep_fn(self._inter_call_seconds)
        self._call_count += 1
        return self._adapter.complete(request)


def _lookup_fixture_tool() -> ToolDefinition:
    return ToolDefinition(
        function=ToolFunction(
            name="lookup_fixture",
            description="Return the deterministic value for a fixture ID.",
            parameters={
                "type": "object",
                "properties": {
                    "fixture_id": {
                        "type": "string",
                        "description": "Fixture identifier.",
                    }
                },
                "required": ["fixture_id"],
                "additionalProperties": False,
            },
        )
    )


def _text_request(
    *,
    profile: EndpointProfile,
    prompt: str,
    max_completion_tokens: int | None,
    thinking: bool | None,
    reference: str,
) -> ModelRequest:
    return ModelRequest(
        request_id=f"protocol-{uuid4().hex}",
        model_id=profile.model_id,
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(ChatMessage(role=ChatRole.USER, content=prompt),),
        max_completion_tokens=max_completion_tokens,
        thinking=thinking,
        deadline_seconds=60,
        experiment_reference=reference,
    )


def _run_output_cap_probe(
    runner: _ProbeRunner,
    profile: EndpointProfile,
) -> ProtocolProbeObservation:
    request = _text_request(
        profile=profile,
        prompt="Reply with exactly: OUTPUT_CAP_OK",
        max_completion_tokens=512,
        thinking=None,
        reference="p0.4-output-cap",
    )
    try:
        result = runner.complete(request)
    except ProviderCallError as exc:
        return _observation_from_error(kind=ProtocolProbeKind.OUTPUT_CAP, error=exc)

    passed = result.outcome is ProviderOutcome.SUCCESS and result.text == "OUTPUT_CAP_OK"
    return _observation_from_result(
        kind=ProtocolProbeKind.OUTPUT_CAP,
        result=result,
        passed=passed,
        condition_code="exact_output_and_cap_accepted" if passed else "output_cap_condition_failed",
    )


def _run_thinking_off_probe(
    runner: _ProbeRunner,
    profile: EndpointProfile,
) -> ProtocolProbeObservation:
    request = _text_request(
        profile=profile,
        prompt="Reply with exactly: THINKING_OFF_OK",
        max_completion_tokens=128,
        thinking=False,
        reference="p0.4-thinking-off",
    )
    try:
        result = runner.complete(request)
    except ProviderCallError as exc:
        return _observation_from_error(kind=ProtocolProbeKind.THINKING_OFF, error=exc)

    passed = result.outcome is ProviderOutcome.SUCCESS and result.text == "THINKING_OFF_OK"

    condition_code = "thinking_off_condition_failed"
    if passed and result.usage is None:
        condition_code = "thinking_off_accepted_usage_unknown"
    if passed and result.usage is not None and result.usage.reasoning_tokens is None:
        condition_code = "thinking_off_accepted_reasoning_unknown"
    if passed and result.usage is not None and result.usage.reasoning_tokens == 0:
        condition_code = "thinking_off_accepted_reasoning_zero"
    if (
        passed
        and result.usage is not None
        and result.usage.reasoning_tokens is not None
        and result.usage.reasoning_tokens > 0
    ):
        condition_code = "thinking_off_accepted_reasoning_nonzero"

    return _observation_from_result(
        kind=ProtocolProbeKind.THINKING_OFF,
        result=result,
        passed=passed,
        condition_code=condition_code,
    )


def _run_json_probe(
    runner: _ProbeRunner,
    profile: EndpointProfile,
) -> ProtocolProbeObservation:
    request = _text_request(
        profile=profile,
        prompt=(
            'Return exactly one JSON object and no markdown: {"fixture_id":"fixture-17","value":42}'
        ),
        max_completion_tokens=1024,
        thinking=None,
        reference="p0.4-json-contract",
    )
    try:
        result = runner.complete(request)
    except ProviderCallError as exc:
        return _observation_from_error(kind=ProtocolProbeKind.JSON_CONTRACT, error=exc)

    valid = False
    if result.outcome is ProviderOutcome.SUCCESS and result.text is not None:
        try:
            payload = json.loads(result.text)
            parsed = _JsonFixture.model_validate(payload)
            valid = parsed.model_dump() == _EXPECTED_JSON
        except (json.JSONDecodeError, ValidationError):
            valid = False

    return _observation_from_result(
        kind=ProtocolProbeKind.JSON_CONTRACT,
        result=result,
        passed=valid,
        condition_code="local_schema_validation_pass" if valid else "local_schema_validation_fail",
    )


def _run_tool_probes(
    runner: _ProbeRunner,
    profile: EndpointProfile,
) -> tuple[ProtocolProbeObservation, ProtocolProbeObservation]:
    tool = _lookup_fixture_tool()
    prompt = (
        "Call lookup_fixture for fixture_id fixture-17. "
        "Do not answer from memory. After the tool result is returned, "
        "reply exactly FIXTURE_VALUE=<value>."
    )
    first_request = ModelRequest(
        request_id=f"protocol-{uuid4().hex}",
        model_id=profile.model_id,
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(ChatMessage(role=ChatRole.USER, content=prompt),),
        tools=(tool,),
        tool_choice=ToolChoice(
            mode=ToolChoiceMode.NAMED,
            function_name="lookup_fixture",
        ),
        max_completion_tokens=1024,
        deadline_seconds=60,
        experiment_reference="p0.4-tool-call",
    )

    try:
        first_result = runner.complete(first_request)
    except ProviderCallError as exc:
        return (
            _observation_from_error(kind=ProtocolProbeKind.TOOL_CALL, error=exc),
            _skipped_observation(
                kind=ProtocolProbeKind.TOOL_ROUND_TRIP,
                condition_code="tool_call_unavailable",
            ),
        )

    tool_call_valid = False
    selected_tool_call: ToolCall | None = None
    if first_result.outcome is ProviderOutcome.SUCCESS and len(first_result.tool_calls) == 1:
        candidate = first_result.tool_calls[0]
        if candidate.function.name == "lookup_fixture":
            try:
                arguments = _ToolArguments.model_validate_json(candidate.function.arguments)
                if arguments.fixture_id == "fixture-17":
                    tool_call_valid = True
                    selected_tool_call = candidate
            except ValidationError:
                tool_call_valid = False

    tool_observation = _observation_from_result(
        kind=ProtocolProbeKind.TOOL_CALL,
        result=first_result,
        passed=tool_call_valid,
        condition_code="native_tool_call_valid" if tool_call_valid else "native_tool_call_invalid",
    )

    if not tool_call_valid or selected_tool_call is None:
        return (
            tool_observation,
            _skipped_observation(
                kind=ProtocolProbeKind.TOOL_ROUND_TRIP,
                condition_code="invalid_tool_call_prevented_round_trip",
            ),
        )

    round_trip_request = ModelRequest(
        request_id=f"protocol-{uuid4().hex}",
        model_id=profile.model_id,
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(
            ChatMessage(role=ChatRole.USER, content=prompt),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=first_result.text,
                tool_calls=(selected_tool_call,),
                provider_reasoning_content=first_result.provider_reasoning_content,
            ),
            ChatMessage(
                role=ChatRole.TOOL,
                content=_TOOL_RESULT_TEXT,
                name=selected_tool_call.function.name,
                tool_call_id=selected_tool_call.id,
            ),
        ),
        tools=(tool,),
        tool_choice=ToolChoice(mode=ToolChoiceMode.AUTO),
        max_completion_tokens=1024,
        deadline_seconds=60,
        experiment_reference="p0.4-tool-round-trip",
    )

    try:
        final_result = runner.complete(round_trip_request)
    except ProviderCallError as exc:
        return (
            tool_observation,
            _observation_from_error(kind=ProtocolProbeKind.TOOL_ROUND_TRIP, error=exc),
        )

    passed = (
        final_result.outcome is ProviderOutcome.SUCCESS
        and final_result.text == "FIXTURE_VALUE=42"
        and not final_result.tool_calls
    )
    round_trip_observation = _observation_from_result(
        kind=ProtocolProbeKind.TOOL_ROUND_TRIP,
        result=final_result,
        passed=passed,
        condition_code="tool_round_trip_exact_output_pass"
        if passed
        else "tool_round_trip_condition_failed",
    )
    return tool_observation, round_trip_observation


def _terminal_failure(observation: ProtocolProbeObservation) -> bool:
    return (
        observation.status is ProtocolProbeStatus.FAIL
        and observation.error_code in _TERMINAL_ERROR_CODES
    )


def run_protocol_capability_probes(
    *,
    profile: EndpointProfile,
    api_key: str,
    inter_call_seconds: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    transport: httpx.BaseTransport | None = None,
) -> ProtocolCapabilityReceipt:
    observed_at = datetime.now(UTC)
    interval = (
        recommended_inter_call_seconds(profile.model_id)
        if inter_call_seconds is None
        else inter_call_seconds
    )
    endpoint = profile.full_endpoint_url
    observations: list[ProtocolProbeObservation] = []

    with HuaweiOpenAIAdapter(
        profile=profile,
        api_key=api_key,
        transport=transport,
    ) as adapter:
        runner = _ProbeRunner(
            adapter=adapter,
            inter_call_seconds=interval,
            sleep_fn=sleep_fn,
        )

        output_cap = _run_output_cap_probe(runner, profile)
        observations.append(output_cap)
        if _terminal_failure(output_cap):
            observations.extend(
                _skipped_observation(
                    kind=kind,
                    condition_code="terminal_provider_failure",
                )
                for kind in (
                    ProtocolProbeKind.THINKING_OFF,
                    ProtocolProbeKind.JSON_CONTRACT,
                    ProtocolProbeKind.TOOL_CALL,
                    ProtocolProbeKind.TOOL_ROUND_TRIP,
                )
            )
        else:
            thinking = _run_thinking_off_probe(runner, profile)
            observations.append(thinking)

            json_probe = _run_json_probe(runner, profile)
            observations.append(json_probe)

            tool_call, round_trip = _run_tool_probes(runner, profile)
            observations.extend((tool_call, round_trip))

    overall_status = ProtocolProbeStatus.PASS
    if any(item.status is not ProtocolProbeStatus.PASS for item in observations):
        overall_status = ProtocolProbeStatus.FAIL

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "profile_name": profile.profile_name,
        "model_id": profile.model_id,
        "endpoint_host": endpoint.host or "",
        "endpoint_path": endpoint.path or "/",
        "planned_max_calls": 5,
        "inter_call_seconds": interval,
        "probes": [item.model_dump(mode="json") for item in observations],
        "overall_status": overall_status,
    }
    payload["receipt_sha256"] = _receipt_hash(payload)
    return ProtocolCapabilityReceipt.model_validate(payload)


def save_protocol_capability_receipt(
    receipt: ProtocolCapabilityReceipt,
    directory: Path,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = receipt.observed_at.strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-{receipt.profile_name}-protocol-receipt.json"
    path = directory / filename
    path.write_text(
        json.dumps(
            receipt.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
