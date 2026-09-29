from __future__ import annotations

from datetime import UTC, datetime

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ModelRequest,
    ModelResult,
    ProviderOutcome,
    ProviderProtocol,
    UsageAccounting,
)
from adaptive_runtime.experiments.harbourdesk_r5e_qualification import (
    R5EB_MAX_COMPLETION_TOKENS,
    run_glm51_r5e_qualification,
)


class FakeProvider:
    def __init__(self, result: ModelResult) -> None:
        self.result = result
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self.result.model_copy(update={"request_id": request.request_id})


def _profile() -> EndpointProfile:
    return EndpointProfile(
        profile_name="primary-openai",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        full_endpoint_url=("https://example.modelarts-maas.com/openai/v1/chat/completions"),
        region_label="test",
        model_id="glm-5.1",
        observed_at=datetime(2026, 9, 11, tzinfo=UTC),
    )


def test_glm51_qualification_passes_on_exact_output_and_usage() -> None:
    provider = FakeProvider(
        ModelResult(
            request_id="placeholder",
            outcome=ProviderOutcome.SUCCESS,
            returned_model="glm-5.1",
            text="R5E_CAPABILITY_OK",
            stop_reason="stop",
            usage=UsageAccounting(
                input_tokens=12,
                completion_tokens=5,
            ),
            http_status=200,
            latency_ms=10,
        )
    )

    receipt = run_glm51_r5e_qualification(
        provider=provider,
        profile=_profile(),
        candidate_commit="a" * 40,
    )

    assert receipt.status == "PASS"
    assert receipt.usage_present is True
    assert receipt.exact_output_match is True
    assert provider.requests[0].max_completion_tokens == (R5EB_MAX_COMPLETION_TOKENS)
    assert provider.requests[0].thinking is False


def test_glm51_qualification_fails_without_usage() -> None:
    provider = FakeProvider(
        ModelResult(
            request_id="placeholder",
            outcome=ProviderOutcome.SUCCESS,
            returned_model="glm-5.1",
            text="R5E_CAPABILITY_OK",
            stop_reason="stop",
            usage=None,
            http_status=200,
            latency_ms=10,
        )
    )

    receipt = run_glm51_r5e_qualification(
        provider=provider,
        profile=_profile(),
        candidate_commit="a" * 40,
    )

    assert receipt.status == "FAIL"
    assert "usage_missing" in receipt.failures
