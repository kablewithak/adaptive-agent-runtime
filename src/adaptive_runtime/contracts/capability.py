from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from adaptive_runtime.contracts.provider import (
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
    StrictContract,
    UsageAccounting,
)


class ProbeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class CapabilityProbeReceipt(StrictContract):
    schema_version: str = Field(pattern=r"^1\.0$")
    observed_at: datetime
    profile_name: str = Field(min_length=1, max_length=100)
    protocol: ProviderProtocol
    model_id: str = Field(min_length=1, max_length=200)
    endpoint_host: str = Field(min_length=1, max_length=253)
    endpoint_path: str = Field(min_length=1, max_length=500)
    status: ProbeStatus
    outcome: ProviderOutcome
    exact_output_pass: bool
    returned_model: str | None = Field(default=None, max_length=200)
    stop_reason: str | None = Field(default=None, max_length=200)
    http_status: int | None = Field(default=None, ge=100, le=599)
    latency_ms: int = Field(ge=0)
    usage_present: bool
    usage: UsageAccounting | None = None
    error_code: ProviderErrorCode | None = None
    retryable: bool = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
