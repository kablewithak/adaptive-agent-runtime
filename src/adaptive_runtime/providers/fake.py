from __future__ import annotations

from enum import StrEnum

from adaptive_runtime.contracts.provider import (
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    UsageAccounting,
)
from adaptive_runtime.providers.base import ProviderCallError


class FakeProviderScenario(StrEnum):
    SUCCESS = "success"
    REFUSAL = "refusal"
    MALFORMED_RESULT = "malformed_result"
    TIMEOUT = "timeout"
    USAGE_NULL = "usage_null"


class FakeProvider:
    def __init__(
        self,
        *,
        scenario: FakeProviderScenario = FakeProviderScenario.SUCCESS,
        returned_model: str = "fake-model-v1",
        response_text: str = "FAKE_PROVIDER_OK",
    ) -> None:
        self._scenario = scenario
        self._returned_model = returned_model
        self._response_text = response_text
        self._requests: list[ModelRequest] = []

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        return tuple(self._requests)

    def complete(self, request: ModelRequest) -> ModelResult:
        self._requests.append(request)

        if self._scenario is FakeProviderScenario.TIMEOUT:
            raise ProviderCallError(
                code=ProviderErrorCode.PROVIDER_TIMEOUT,
                message="deterministic fake provider timeout",
                retryable=True,
            )

        if self._scenario is FakeProviderScenario.REFUSAL:
            return ModelResult(
                request_id=request.request_id,
                outcome=ProviderOutcome.REFUSAL,
                returned_model=self._returned_model,
                text=None,
                stop_reason="refusal",
                usage=UsageAccounting(input_tokens=12, completion_tokens=4),
                provider_request_id="fake-request-refusal",
                latency_ms=0,
            )

        if self._scenario is FakeProviderScenario.MALFORMED_RESULT:
            return ModelResult(
                request_id=request.request_id,
                outcome=ProviderOutcome.SUCCESS,
                returned_model=self._returned_model,
                text="{not-valid-json",
                stop_reason="stop",
                usage=UsageAccounting(input_tokens=12, completion_tokens=5),
                provider_request_id="fake-request-malformed",
                latency_ms=0,
            )

        if self._scenario is FakeProviderScenario.USAGE_NULL:
            return ModelResult(
                request_id=request.request_id,
                outcome=ProviderOutcome.SUCCESS,
                returned_model=self._returned_model,
                text=self._response_text,
                stop_reason="stop",
                usage=None,
                provider_request_id="fake-request-usage-null",
                latency_ms=0,
            )

        return ModelResult(
            request_id=request.request_id,
            outcome=ProviderOutcome.SUCCESS,
            returned_model=self._returned_model,
            text=self._response_text,
            stop_reason="stop",
            usage=UsageAccounting(input_tokens=12, completion_tokens=3),
            provider_request_id="fake-request-success",
            latency_ms=0,
        )
