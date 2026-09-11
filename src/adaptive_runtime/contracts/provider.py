from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveTokenCount = Annotated[int, Field(gt=0)]


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ProviderName(StrEnum):
    HUAWEI_MAAS = "huawei_maas"
    FAKE = "fake"


class ProviderProtocol(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC_COMPATIBLE = "anthropic_compatible"


class CapabilityStatus(StrEnum):
    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProviderOutcome(StrEnum):
    SUCCESS = "success"
    REFUSAL = "refusal"
    ERROR = "error"


class ProviderErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    ENTITLEMENT_DENIED = "entitlement_denied"
    MODEL_UNAVAILABLE = "model_unavailable"
    REQUEST_INVALID = "request_invalid"
    PROVIDER_REJECTED = "provider_rejected"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROTOCOL_ERROR = "protocol_error"
    USAGE_UNKNOWN = "usage_unknown"


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolChoiceMode(StrEnum):
    NONE = "none"
    AUTO = "auto"
    NAMED = "named"


class ToolFunction(StrictContract):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    parameters: dict[str, object]


class ToolDefinition(StrictContract):
    type: str = Field(default="function", pattern=r"^function$")
    function: ToolFunction


class ToolCallFunction(StrictContract):
    name: str = Field(min_length=1, max_length=100)
    arguments: str = Field(min_length=1)


class ToolCall(StrictContract):
    id: str = Field(min_length=1, max_length=300)
    type: str = Field(default="function", pattern=r"^function$")
    function: ToolCallFunction


class ToolChoice(StrictContract):
    mode: ToolChoiceMode
    function_name: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_named_choice(self) -> ToolChoice:
        if self.mode is ToolChoiceMode.NAMED and self.function_name is None:
            raise ValueError("named tool choice requires function_name")
        if self.mode is not ToolChoiceMode.NAMED and self.function_name is not None:
            raise ValueError("function_name is only valid for named tool choice")
        return self


class ChatMessage(StrictContract):
    role: ChatRole
    content: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=300)
    tool_calls: tuple[ToolCall, ...] = ()
    provider_reasoning_content: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    @model_validator(mode="after")
    def validate_role_contract(self) -> ChatMessage:
        if self.role in {ChatRole.SYSTEM, ChatRole.USER}:
            if self.content is None or not self.content:
                raise ValueError("system/user message requires content")
            if (
                self.name is not None
                or self.tool_call_id is not None
                or self.tool_calls
                or self.provider_reasoning_content is not None
            ):
                raise ValueError("system/user message cannot contain tool metadata")
            return self

        if self.role is ChatRole.TOOL:
            if self.content is None or not self.content:
                raise ValueError("tool message requires content")
            if self.tool_call_id is None:
                raise ValueError("tool message requires tool_call_id")
            if self.tool_calls:
                raise ValueError("tool message cannot contain tool_calls")
            if self.provider_reasoning_content is not None:
                raise ValueError("tool message cannot contain provider reasoning content")
            return self

        if self.name is not None:
            raise ValueError("assistant message cannot contain name")
        if self.tool_call_id is not None:
            raise ValueError("assistant message cannot contain tool_call_id")
        if self.content is None and not self.tool_calls:
            raise ValueError("assistant message requires content or tool_calls")
        return self


class UsageAccounting(StrictContract):
    input_tokens: NonNegativeInt | None = None
    completion_tokens: NonNegativeInt | None = None
    reasoning_tokens: NonNegativeInt | None = None
    cached_input_tokens: NonNegativeInt | None = None


class ModelCapability(StrictContract):
    provider: ProviderName
    protocol: ProviderProtocol
    endpoint_profile: str = Field(min_length=1, max_length=100)
    exact_model_id: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    status: CapabilityStatus
    max_tested_prompt_tokens: PositiveTokenCount | None = None
    max_tested_completion_tokens: PositiveTokenCount | None = None
    thinking_control: bool | None = None
    usage_mapping_version: str | None = Field(default=None, max_length=100)
    rpm_operating_limit: PositiveTokenCount | None = None
    tpm_operating_limit: PositiveTokenCount | None = None
    capability_receipt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class ModelRequest(StrictContract):
    request_id: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=200)
    protocol: ProviderProtocol
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    tools: tuple[ToolDefinition, ...] = ()
    tool_choice: ToolChoice | None = None
    max_completion_tokens: PositiveTokenCount | None = None
    thinking: bool | None = None
    deadline_seconds: float = Field(gt=0, le=300)
    experiment_reference: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_tool_choice(self) -> ModelRequest:
        if self.tool_choice is not None and not self.tools:
            raise ValueError("tool_choice requires at least one tool")
        if (
            self.tool_choice is not None
            and self.tool_choice.mode is ToolChoiceMode.NAMED
            and self.tool_choice.function_name not in {tool.function.name for tool in self.tools}
        ):
            raise ValueError("named tool choice must reference a supplied tool")
        return self


class ModelResult(StrictContract):
    request_id: str = Field(min_length=1, max_length=200)
    outcome: ProviderOutcome
    returned_model: str | None = Field(default=None, max_length=200)
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    provider_reasoning_content: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    stop_reason: str | None = Field(default=None, max_length=200)
    usage: UsageAccounting | None = None
    provider_request_id: str | None = Field(default=None, max_length=300)
    http_status: int | None = Field(default=None, ge=100, le=599)
    latency_ms: NonNegativeInt | None = None
    error_code: ProviderErrorCode | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_outcome_contract(self) -> ModelResult:
        if self.outcome is ProviderOutcome.ERROR and self.error_code is None:
            raise ValueError("error outcome requires error_code")
        if self.outcome is not ProviderOutcome.ERROR and self.error_code is not None:
            raise ValueError("error_code is only valid for error outcomes")
        if self.outcome is ProviderOutcome.SUCCESS and self.text is None and not self.tool_calls:
            raise ValueError("success outcome requires text or tool_calls")
        return self
