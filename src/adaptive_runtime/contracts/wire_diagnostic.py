from __future__ import annotations

from datetime import datetime

from pydantic import Field

from adaptive_runtime.contracts.provider import ProviderErrorCode, StrictContract


class FlashWireDiagnosticReceipt(StrictContract):
    schema_version: str = Field(pattern=r"^1\.0$")
    observed_at: datetime
    profile_name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(pattern=r"^deepseek-v4-flash$")
    endpoint_host: str = Field(min_length=1, max_length=253)
    endpoint_path: str = Field(min_length=1, max_length=500)
    status: str = Field(pattern=r"^(pass|fail)$")
    condition_code: str = Field(min_length=1, max_length=120)
    first_http_status: int | None = Field(default=None, ge=100, le=599)
    second_http_status: int | None = Field(default=None, ge=100, le=599)
    first_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    second_request_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    assistant_message_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    assistant_message_keys: tuple[str, ...] = ()
    reasoning_content_present: bool = False
    tool_call_count: int = Field(default=0, ge=0)
    tool_call_id_present: bool = False
    tool_name: str | None = Field(default=None, max_length=100)
    tool_arguments_valid: bool = False
    final_exact_output_pass: bool = False
    error_code: ProviderErrorCode | None = None
    provider_error_identifier: str | None = Field(default=None, max_length=100)
    retryable: bool = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
