from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ProviderOutcome,
)
from adaptive_runtime.providers.base import ProviderAdapter, ProviderCallError

R5EB_PROFILE_NAME = "primary-openai"
R5EB_MODEL_ID = "glm-5.1"
R5EB_MAX_COMPLETION_TOKENS = 1536
R5EB_EXPECTED_TEXT = "R5E_CAPABILITY_OK"


class R5EBContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R5EBQualificationReceipt(R5EBContract):
    schema_version: Literal["harbourdesk-r5eb-qualification-v1"] = (
        "harbourdesk-r5eb-qualification-v1"
    )
    status: Literal["PASS", "FAIL"]
    observed_at: datetime
    candidate_commit: str
    profile_name: str
    model_id: str
    protocol: str
    requested_max_completion_tokens: int
    returned_model: str | None
    provider_outcome: str | None
    http_status: int | None
    stop_reason: str | None
    usage_present: bool
    input_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: int | None
    exact_output_match: bool
    error_code: str | None
    retryable: bool | None
    failures: tuple[str, ...]


def run_glm51_r5e_qualification(
    *,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    candidate_commit: str,
) -> R5EBQualificationReceipt:
    failures: list[str] = []

    if profile.profile_name != R5EB_PROFILE_NAME:
        failures.append("profile_name_mismatch")
    if profile.model_id != R5EB_MODEL_ID:
        failures.append("model_id_mismatch")

    request = ModelRequest(
        request_id="r5eb-glm51-capability-1536",
        model_id=profile.model_id,
        protocol=profile.protocol,
        messages=(
            ChatMessage(
                role=ChatRole.USER,
                content=("Reply with exactly R5E_CAPABILITY_OK and no other text."),
            ),
        ),
        max_completion_tokens=R5EB_MAX_COMPLETION_TOKENS,
        thinking=False,
        deadline_seconds=60.0,
        experiment_reference="harbourdesk-r5eb-qualification-v1",
    )

    try:
        result = provider.complete(request)
    except ProviderCallError as exc:
        return R5EBQualificationReceipt(
            status="FAIL",
            observed_at=datetime.now(UTC),
            candidate_commit=candidate_commit,
            profile_name=profile.profile_name,
            model_id=profile.model_id,
            protocol=profile.protocol.value,
            requested_max_completion_tokens=R5EB_MAX_COMPLETION_TOKENS,
            returned_model=None,
            provider_outcome=None,
            http_status=exc.http_status,
            stop_reason=None,
            usage_present=False,
            input_tokens=None,
            completion_tokens=None,
            reasoning_tokens=None,
            latency_ms=None,
            exact_output_match=False,
            error_code=exc.code.value,
            retryable=exc.retryable,
            failures=(f"provider_error:{exc.code.value}",),
        )

    if result.outcome is not ProviderOutcome.SUCCESS:
        failures.append(f"provider_outcome:{result.outcome.value}")
    if result.returned_model != R5EB_MODEL_ID:
        failures.append("returned_model_mismatch")

    text = (result.text or "").strip()
    exact_output_match = text == R5EB_EXPECTED_TEXT
    if not exact_output_match:
        failures.append("exact_output_mismatch")

    usage = result.usage
    usage_present = (
        usage is not None and usage.input_tokens is not None and usage.completion_tokens is not None
    )
    if not usage_present:
        failures.append("usage_missing")

    return R5EBQualificationReceipt(
        status="PASS" if not failures else "FAIL",
        observed_at=datetime.now(UTC),
        candidate_commit=candidate_commit,
        profile_name=profile.profile_name,
        model_id=profile.model_id,
        protocol=profile.protocol.value,
        requested_max_completion_tokens=R5EB_MAX_COMPLETION_TOKENS,
        returned_model=result.returned_model,
        provider_outcome=result.outcome.value,
        http_status=result.http_status,
        stop_reason=result.stop_reason,
        usage_present=usage_present,
        input_tokens=None if usage is None else usage.input_tokens,
        completion_tokens=(None if usage is None else usage.completion_tokens),
        reasoning_tokens=(None if usage is None else usage.reasoning_tokens),
        latency_ms=result.latency_ms,
        exact_output_match=exact_output_match,
        error_code=None,
        retryable=result.retryable,
        failures=tuple(failures),
    )
