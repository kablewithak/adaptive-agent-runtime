import pytest

from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.fake import FakeProvider, FakeProviderScenario


def _request() -> ModelRequest:
    return ModelRequest(
        request_id="request-001",
        model_id="fake-model-v1",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(ChatMessage(role=ChatRole.USER, content="Return a deterministic fixture."),),
        max_completion_tokens=128,
        thinking=False,
        deadline_seconds=30,
    )


def test_fake_provider_success_is_deterministic_and_records_request() -> None:
    provider = FakeProvider(response_text="EXPECTED")

    result = provider.complete(_request())

    assert result.outcome is ProviderOutcome.SUCCESS
    assert result.text == "EXPECTED"
    assert result.usage is not None
    assert result.usage.input_tokens == 12
    assert len(provider.requests) == 1


def test_fake_provider_timeout_raises_typed_retryable_error() -> None:
    provider = FakeProvider(scenario=FakeProviderScenario.TIMEOUT)

    with pytest.raises(ProviderCallError) as exc_info:
        provider.complete(_request())

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert exc_info.value.retryable is True


def test_fake_provider_usage_null_remains_unknown() -> None:
    provider = FakeProvider(scenario=FakeProviderScenario.USAGE_NULL)

    result = provider.complete(_request())

    assert result.outcome is ProviderOutcome.SUCCESS
    assert result.usage is None


def test_fake_provider_does_not_repair_malformed_model_text() -> None:
    provider = FakeProvider(scenario=FakeProviderScenario.MALFORMED_RESULT)

    result = provider.complete(_request())

    assert result.text == "{not-valid-json"


def test_fake_provider_refusal_is_explicit() -> None:
    provider = FakeProvider(scenario=FakeProviderScenario.REFUSAL)

    result = provider.complete(_request())

    assert result.outcome is ProviderOutcome.REFUSAL
    assert result.stop_reason == "refusal"
