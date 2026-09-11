import json

import httpx
import pytest

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _profile() -> EndpointProfile:
    return EndpointProfile.model_validate(
        {
            "profile_name": "primary-openai",
            "protocol": "openai_compatible",
            "full_endpoint_url": (
                "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
            ),
            "region_label": "console-region",
            "model_id": "glm-5.1",
            "observed_at": "2026-09-11T14:00:00Z",
        }
    )


def _request() -> ModelRequest:
    return ModelRequest(
        request_id="request-001",
        model_id="glm-5.1",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(
            ChatMessage(
                role=ChatRole.USER,
                content="Reply with exactly: MAAS_SMOKE_OK",
            ),
        ),
        max_completion_tokens=256,
        thinking=False,
        deadline_seconds=60,
    )


def _minimal_request() -> ModelRequest:
    return ModelRequest(
        request_id="request-minimal",
        model_id="glm-5.1",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(
            ChatMessage(
                role=ChatRole.USER,
                content="Reply with exactly: MAAS_SMOKE_OK",
            ),
        ),
        deadline_seconds=60,
    )


def test_minimal_request_omits_optional_controls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "model": "glm-5.1",
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly: MAAS_SMOKE_OK",
                }
            ],
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "model": "glm-5.1",
                "choices": [
                    {
                        "message": {"content": "MAAS_SMOKE_OK"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        result = adapter.complete(_minimal_request())

    assert result.outcome is ProviderOutcome.SUCCESS
    assert result.text == "MAAS_SMOKE_OK"


def test_success_normalises_response_and_sends_bounded_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-secret"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "glm-5.1"
        assert payload["stream"] is False
        assert payload["max_completion_tokens"] == 256
        assert payload["chat_template_kwargs"] == {"thinking": False}

        return httpx.Response(
            200,
            json={
                "model": "glm-5.1",
                "choices": [
                    {
                        "message": {"content": "MAAS_SMOKE_OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 4,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                    "prompt_tokens_details": {"cached_tokens": 2},
                },
            },
            headers={"x-request-id": "provider-request-1"},
        )

    transport = httpx.MockTransport(handler)

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=transport,
    ) as adapter:
        result = adapter.complete(_request())

    assert result.outcome is ProviderOutcome.SUCCESS
    assert result.text == "MAAS_SMOKE_OK"
    assert result.http_status == 200
    assert result.usage is not None
    assert result.usage.input_tokens == 11
    assert result.usage.completion_tokens == 4
    assert result.usage.reasoning_tokens == 1
    assert result.usage.cached_input_tokens == 2


def test_http_error_is_typed_without_leaking_provider_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": "SECRET_PROVIDER_BODY_SHOULD_NOT_ESCAPE"},
        )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        with pytest.raises(ProviderCallError) as exc_info:
            adapter.complete(_request())

    error = exc_info.value
    assert error.code is ProviderErrorCode.AUTHENTICATION_FAILED
    assert error.http_status == 401
    assert "SECRET_PROVIDER_BODY_SHOULD_NOT_ESCAPE" not in str(error)


def test_redirect_is_not_followed_and_fails_closed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            307,
            headers={"location": "https://example.com/steal"},
        )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        with pytest.raises(ProviderCallError) as exc_info:
            adapter.complete(_request())

    assert calls == 1
    assert exc_info.value.code is ProviderErrorCode.PROTOCOL_ERROR
    assert exc_info.value.http_status == 307


def test_transport_timeout_is_retryable_but_not_automatically_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        with pytest.raises(ProviderCallError) as exc_info:
            adapter.complete(_request())

    assert calls == 1
    assert exc_info.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert exc_info.value.retryable is True


def test_http_400_is_classified_as_ambiguous_provider_rejection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "cause intentionally treated as ambiguous"},
        )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        with pytest.raises(ProviderCallError) as exc_info:
            adapter.complete(_request())

    error = exc_info.value
    assert error.code is ProviderErrorCode.PROVIDER_REJECTED
    assert error.http_status == 400
    assert error.retryable is False
    assert "cause intentionally treated as ambiguous" not in str(error)


def test_native_tool_call_is_serialised_and_normalised() -> None:
    from adaptive_runtime.contracts.provider import (
        ToolChoice,
        ToolChoiceMode,
        ToolDefinition,
        ToolFunction,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["tools"][0]["function"]["name"] == "lookup_fixture"
        assert payload["tool_choice"] == {
            "type": "function",
            "function": {"name": "lookup_fixture"},
        }
        return httpx.Response(
            200,
            json={
                "model": "glm-5.1",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "reasoning_content": "private-provider-reasoning",
                            "tool_calls": [
                                {
                                    "id": "call-123",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_fixture",
                                        "arguments": '{"fixture_id":"fixture-17"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 7,
                },
            },
        )

    tool = ToolDefinition(
        function=ToolFunction(
            name="lookup_fixture",
            description="Lookup a deterministic fixture.",
            parameters={
                "type": "object",
                "properties": {"fixture_id": {"type": "string"}},
                "required": ["fixture_id"],
            },
        )
    )
    request = ModelRequest(
        request_id="request-tool",
        model_id="glm-5.1",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(ChatMessage(role=ChatRole.USER, content="Lookup fixture-17."),),
        tools=(tool,),
        tool_choice=ToolChoice(
            mode=ToolChoiceMode.NAMED,
            function_name="lookup_fixture",
        ),
        max_completion_tokens=256,
        deadline_seconds=60,
    )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        result = adapter.complete(request)

    assert result.outcome is ProviderOutcome.SUCCESS
    assert result.text is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call-123"
    assert result.tool_calls[0].function.name == "lookup_fixture"
    assert result.provider_reasoning_content == "private-provider-reasoning"
    assert "provider_reasoning_content" not in result.model_dump()
    assert "private-provider-reasoning" not in result.model_dump_json()


def test_tool_round_trip_serialises_assistant_call_and_tool_result() -> None:
    from adaptive_runtime.contracts.provider import (
        ToolCall,
        ToolCallFunction,
        ToolChoice,
        ToolChoiceMode,
        ToolDefinition,
        ToolFunction,
    )

    tool_call = ToolCall(
        id="call-123",
        function=ToolCallFunction(
            name="lookup_fixture",
            arguments='{"fixture_id":"fixture-17"}',
        ),
    )
    tool = ToolDefinition(
        function=ToolFunction(
            name="lookup_fixture",
            description="Lookup a deterministic fixture.",
            parameters={
                "type": "object",
                "properties": {"fixture_id": {"type": "string"}},
                "required": ["fixture_id"],
            },
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["messages"][1]["content"] is None
        assert payload["messages"][1]["reasoning_content"] == "private-provider-reasoning"
        assert payload["messages"][1]["tool_calls"][0]["id"] == "call-123"
        assert payload["messages"][2] == {
            "role": "tool",
            "content": '{"fixture_id":"fixture-17","value":42}',
            "name": "lookup_fixture",
            "tool_call_id": "call-123",
        }
        assert payload["tool_choice"] == "auto"
        return httpx.Response(
            200,
            json={
                "model": "glm-5.1",
                "choices": [
                    {
                        "message": {"content": "FIXTURE_VALUE=42"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    request = ModelRequest(
        request_id="request-round-trip",
        model_id="glm-5.1",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(
            ChatMessage(role=ChatRole.USER, content="Lookup fixture-17."),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=None,
                tool_calls=(tool_call,),
                provider_reasoning_content="private-provider-reasoning",
            ),
            ChatMessage(
                role=ChatRole.TOOL,
                content='{"fixture_id":"fixture-17","value":42}',
                name="lookup_fixture",
                tool_call_id="call-123",
            ),
        ),
        tools=(tool,),
        tool_choice=ToolChoice(mode=ToolChoiceMode.AUTO),
        deadline_seconds=60,
    )

    with HuaweiOpenAIAdapter(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as adapter:
        result = adapter.complete(request)

    assert result.text == "FIXTURE_VALUE=42"
    assert result.tool_calls == ()
