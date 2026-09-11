from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint, ModelCatalogReceipt
from adaptive_runtime.providers.huawei_models import HuaweiModelCatalogClient


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


def run_model_discovery(
    *,
    endpoint: ModelCatalogEndpoint,
    api_key: str,
    transport: httpx.BaseTransport | None = None,
) -> ModelCatalogReceipt:
    observed_at = datetime.now(UTC)

    with HuaweiModelCatalogClient(
        endpoint=endpoint,
        api_key=api_key,
        transport=transport,
    ) as client:
        model_ids, http_status, latency_ms = client.list_models()

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "endpoint_host": endpoint.url.host or "",
        "endpoint_path": endpoint.url.path or "/",
        "http_status": http_status,
        "latency_ms": latency_ms,
        "model_ids": model_ids,
        "model_count": len(model_ids),
    }
    payload["receipt_sha256"] = _receipt_hash(payload)
    return ModelCatalogReceipt.model_validate(payload)


def save_model_catalog_receipt(
    receipt: ModelCatalogReceipt,
    directory: Path,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = receipt.observed_at.strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{timestamp}-model-catalog-receipt.json"
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
