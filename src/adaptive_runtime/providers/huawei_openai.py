from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolCallFunction,
    ToolChoiceMode,
    UsageAccounting,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_http import classify_huawei_http_error


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _CompletionTokenDetails(_WireModel):
    reasoning_tokens: int | None = Field(default=None, ge=0)


class _PromptTokenDetails(_WireModel):
    cached_tokens: int | None = Field(default=None, ge=0)


class _UsageWire(_WireModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    completion_tokens_details: _CompletionTokenDetails | None = None
    prompt_tokens_details: _PromptTokenDetails | None = None


class _ToolCallFunctionWire(_WireModel):
    name: str
    arguments: str


class _ToolCallWire(_WireModel):
    id: str
    type: str = "function"
    function: _ToolCallFunctionWire


class _MessageWire(_WireModel):
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: tuple[_ToolCallWire, ...] = ()


class _ChoiceWire(_WireModel):
    message: _MessageWire
    finish_reason: str | None = None


class _ChatResponseWire(_WireModel):
    model: str | None = None
    choices: tuple[_ChoiceWire, ...] = Field(min_length=1, max_length=1)
    usage: _UsageWire | None = None


class HuaweiOpenAIAdapter:
    def __init__(
        self,
        *,
        profile: EndpointProfile,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
            raise ValueError("HuaweiOpenAIAdapter requires an OpenAI-compatible profile")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")

        self._profile = profile
        self._api_key = api_key
        self._client = httpx.Client(
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HuaweiOpenAIAdapter:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def complete(self, request: ModelRequest) -> ModelResult:
        if request.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
            raise ProviderCallError(
                code=ProviderErrorCode.REQUEST_INVALID,
                message="request protocol does not match adapter protocol",
                retryable=False,
            )

        if request.model_id != self._profile.model_id:
            raise ProviderCallError(
                code=ProviderErrorCode.REQUEST_INVALID,
                message="request model does not match endpoint profile",
                retryable=False,
            )

        payload: dict[str, object] = {
            "model": request.model_id,
            "messages": [self._message_payload(message) for message in request.messages],
            "stream": False,
        }

        if request.tools:
            payload["tools"] = [
                {
                    "type": tool.type,
                    "function": {
                        "name": tool.function.name,
                        "description": tool.function.description,
                        "parameters": tool.function.parameters,
                    },
                }
                for tool in request.tools
            ]

        if request.tool_choice is not None:
            if request.tool_choice.mode is ToolChoiceMode.NAMED:
                payload["tool_choice"] = {
                    "type": "function",
                    "function": {"name": request.tool_choice.function_name},
                }
            else:
                payload["tool_choice"] = request.tool_choice.mode.value

        if request.max_completion_tokens is not None:
            payload["max_completion_tokens"] = request.max_completion_tokens

        if request.thinking is not None:
            payload["chat_template_kwargs"] = {"thinking": request.thinking}

        started = perf_counter()

        try:
            response = self._client.post(
                str(self._profile.full_endpoint_url),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=request.deadline_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROVIDER_TIMEOUT,
                message="Huawei MaaS request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                message="Huawei MaaS transport request failed",
                retryable=True,
            ) from exc

        latency_ms = max(0, round((perf_counter() - started) * 1000))

        if not response.is_success:
            raise classify_huawei_http_error(response.status_code)

        try:
            parsed = _ChatResponseWire.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROTOCOL_ERROR,
                message="Huawei MaaS returned an invalid chat response shape",
                retryable=False,
                http_status=response.status_code,
            ) from exc

        choice = parsed.choices[0]
        content = choice.message.content
        tool_calls = tuple(
            ToolCall(
                id=tool_call.id,
                type=tool_call.type,
                function=ToolCallFunction(
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                ),
            )
            for tool_call in choice.message.tool_calls
        )

        if content is None and not tool_calls:
            if choice.finish_reason in {"content_filter", "safety", "refusal"}:
                return ModelResult(
                    request_id=request.request_id,
                    outcome=ProviderOutcome.REFUSAL,
                    returned_model=parsed.model,
                    text=None,
                    stop_reason=choice.finish_reason,
                    usage=self._normalise_usage(parsed.usage),
                    provider_request_id=response.headers.get("x-request-id"),
                    http_status=response.status_code,
                    latency_ms=latency_ms,
                )

            raise ProviderCallError(
                code=ProviderErrorCode.PROTOCOL_ERROR,
                message="Huawei MaaS response contained neither text nor tool calls",
                retryable=False,
                http_status=response.status_code,
            )

        return ModelResult(
            request_id=request.request_id,
            outcome=ProviderOutcome.SUCCESS,
            returned_model=parsed.model,
            text=content,
            tool_calls=tool_calls,
            provider_reasoning_content=choice.message.reasoning_content,
            stop_reason=choice.finish_reason,
            usage=self._normalise_usage(parsed.usage),
            provider_request_id=response.headers.get("x-request-id"),
            http_status=response.status_code,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _message_payload(message: ChatMessage) -> dict[str, object]:
        payload: dict[str, object] = {"role": message.role.value}

        if message.content is not None:
            payload["content"] = message.content
        elif message.tool_calls:
            payload["content"] = None

        if message.name is not None:
            payload["name"] = message.name

        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id

        if message.provider_reasoning_content is not None:
            payload["reasoning_content"] = message.provider_reasoning_content

        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]

        return payload

    @staticmethod
    def _normalise_usage(usage: _UsageWire | None) -> UsageAccounting | None:
        if usage is None:
            return None

        reasoning_tokens = None
        if usage.completion_tokens_details is not None:
            reasoning_tokens = usage.completion_tokens_details.reasoning_tokens

        cached_input_tokens = None
        if usage.prompt_tokens_details is not None:
            cached_input_tokens = usage.prompt_tokens_details.cached_tokens

        return UsageAccounting(
            input_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
