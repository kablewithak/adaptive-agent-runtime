from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from adaptive_runtime.contracts.provider import (
    ProviderErrorCode,
    StrictContract,
    UsageAccounting,
)


class ProtocolProbeKind(StrEnum):
    OUTPUT_CAP = "output_cap"
    THINKING_OFF = "thinking_off"
    JSON_CONTRACT = "json_contract"
    TOOL_CALL = "tool_call"
    TOOL_ROUND_TRIP = "tool_round_trip"


class ProtocolProbeStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class ProtocolProbeObservation(StrictContract):
    kind: ProtocolProbeKind
    status: ProtocolProbeStatus
    http_status: int | None = Field(default=None, ge=100, le=599)
    returned_model: str | None = Field(default=None, max_length=200)
    stop_reason: str | None = Field(default=None, max_length=200)
    latency_ms: int | None = Field(default=None, ge=0)
    usage_present: bool
    usage: UsageAccounting | None = None
    error_code: ProviderErrorCode | None = None
    retryable: bool = False
    condition_code: str = Field(min_length=1, max_length=100)


class ProtocolCapabilityReceipt(StrictContract):
    schema_version: str = Field(pattern=r"^1\.0$")
    observed_at: datetime
    profile_name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    endpoint_host: str = Field(min_length=1, max_length=253)
    endpoint_path: str = Field(min_length=1, max_length=500)
    planned_max_calls: int = Field(ge=1, le=10)
    inter_call_seconds: float = Field(ge=0, le=120)
    probes: tuple[ProtocolProbeObservation, ...] = Field(min_length=1)
    overall_status: ProtocolProbeStatus
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
