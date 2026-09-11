from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx

from adaptive_runtime.contracts.capability import CapabilityProbeReceipt, ProbeStatus
from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ProviderOutcome,
    ProviderProtocol,
)
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _receipt_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_openai_text_probe(
    *,
    profile: EndpointProfile,
    api_key: str,
    expected_text: str = "MAAS_SMOKE_OK",
    transport: httpx.BaseTransport | None = None,
) -> CapabilityProbeReceipt:
    observed_at = datetime.now(UTC)
    endpoint = profile.full_endpoint_url
    started = perf_counter()

    base_payload: dict[str, object] = {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "profile_name": profile.profile_name,
        "protocol": profile.protocol,
        "model_id": profile.model_id,
        "endpoint_host": endpoint.host or "",
        "endpoint_path": endpoint.path or "/",
    }

    request = ModelRequest(
        request_id=f"capability-{uuid4().hex}",
        model_id=profile.model_id,
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        messages=(
            ChatMessage(
                role=ChatRole.USER,
                content=f"Reply with exactly: {expected_text}",
            ),
        ),
        max_completion_tokens=None,
        thinking=None,
        deadline_seconds=60,
        experiment_reference="p0.2-text-capability-probe",
    )

    try:
        with HuaweiOpenAIAdapter(
            profile=profile,
            api_key=api_key,
            transport=transport,
        ) as adapter:
            result = adapter.complete(request)
    except ProviderCallError as exc:
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        failure_payload: dict[str, object] = {
            **base_payload,
            "status": ProbeStatus.FAIL,
            "outcome": ProviderOutcome.ERROR,
            "exact_output_pass": False,
            "returned_model": None,
            "stop_reason": None,
            "http_status": exc.http_status,
            "latency_ms": latency_ms,
            "usage_present": False,
            "usage": None,
            "error_code": exc.code,
            "retryable": exc.retryable,
        }
        failure_payload["receipt_sha256"] = _receipt_hash(failure_payload)
        return CapabilityProbeReceipt.model_validate(failure_payload)

    exact_output_pass = (
        result.outcome is ProviderOutcome.SUCCESS
        and result.text is not None
        and result.text.strip() == expected_text
    )
    status = ProbeStatus.PASS if exact_output_pass else ProbeStatus.FAIL

    success_payload: dict[str, object] = {
        **base_payload,
        "status": status,
        "outcome": result.outcome,
        "exact_output_pass": exact_output_pass,
        "returned_model": result.returned_model,
        "stop_reason": result.stop_reason,
        "http_status": result.http_status,
        "latency_ms": result.latency_ms or 0,
        "usage_present": result.usage is not None,
        "usage": result.usage.model_dump(mode="json") if result.usage is not None else None,
        "error_code": result.error_code,
        "retryable": result.retryable,
    }
    success_payload["receipt_sha256"] = _receipt_hash(success_payload)
    return CapabilityProbeReceipt.model_validate(success_payload)


def save_capability_receipt(
    receipt: CapabilityProbeReceipt,
    directory: Path,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = receipt.observed_at.strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-{receipt.profile_name}-receipt.json"
    path = directory / filename
    path.write_text(
        json.dumps(
            receipt.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
