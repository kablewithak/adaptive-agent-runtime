from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint, ModelCatalogEntry
from adaptive_runtime.contracts.provider import ProviderErrorCode
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_http import classify_huawei_http_error


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _ModelCatalogWire(_WireModel):
    object: str | None = None
    data: tuple[ModelCatalogEntry, ...] = Field(default=())


class HuaweiModelCatalogClient:
    def __init__(
        self,
        *,
        endpoint: ModelCatalogEndpoint,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")

        self._endpoint = endpoint
        self._api_key = api_key
        self._client = httpx.Client(
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HuaweiModelCatalogClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def list_models(self, *, deadline_seconds: float = 30) -> tuple[tuple[str, ...], int, int]:
        if deadline_seconds <= 0 or deadline_seconds > 300:
            raise ValueError("deadline_seconds must be greater than 0 and at most 300")

        started = perf_counter()

        try:
            response = self._client.get(
                str(self._endpoint.url),
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=deadline_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROVIDER_TIMEOUT,
                message="Huawei MaaS model-list request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                message="Huawei MaaS model-list transport request failed",
                retryable=True,
            ) from exc

        latency_ms = max(0, round((perf_counter() - started) * 1000))

        if not response.is_success:
            raise classify_huawei_http_error(response.status_code)

        try:
            parsed = _ModelCatalogWire.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ProviderCallError(
                code=ProviderErrorCode.PROTOCOL_ERROR,
                message="Huawei MaaS returned an invalid model-list response shape",
                retryable=False,
                http_status=response.status_code,
            ) from exc

        model_ids = tuple(entry.id for entry in parsed.data)
        if len(set(model_ids)) != len(model_ids):
            raise ProviderCallError(
                code=ProviderErrorCode.PROTOCOL_ERROR,
                message="Huawei MaaS model-list response contained duplicate model IDs",
                retryable=False,
                http_status=response.status_code,
            )

        return model_ids, response.status_code, latency_ms
