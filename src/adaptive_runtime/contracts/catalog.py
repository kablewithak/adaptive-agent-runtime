from __future__ import annotations

from datetime import datetime

from pydantic import Field, HttpUrl, model_validator

from adaptive_runtime.contracts.provider import StrictContract


class ModelCatalogEndpoint(StrictContract):
    url: HttpUrl

    @model_validator(mode="after")
    def validate_endpoint(self) -> ModelCatalogEndpoint:
        url = self.url
        host = url.host or ""
        path = (url.path or "").rstrip("/")

        if url.scheme != "https":
            raise ValueError("model catalog endpoint must use HTTPS")
        if not host.endswith(".modelarts-maas.com"):
            raise ValueError("model catalog endpoint must use a Huawei ModelArts MaaS host")
        if url.username is not None or url.password is not None:
            raise ValueError("credentials must not be embedded in model catalog endpoint")
        if url.query is not None:
            raise ValueError("model catalog endpoint must not contain a query string")
        if url.fragment is not None:
            raise ValueError("model catalog endpoint must not contain a fragment")
        if path != "/v2/models":
            raise ValueError("model catalog endpoint must end with /v2/models")
        return self


class ModelCatalogEntry(StrictContract):
    id: str = Field(min_length=1, max_length=200)
    object: str | None = Field(default=None, max_length=100)
    created: int | None = Field(default=None, ge=0)
    owned_by: str | None = Field(default=None, max_length=200)


class ModelCatalogReceipt(StrictContract):
    schema_version: str = Field(pattern=r"^1\.0$")
    observed_at: datetime
    endpoint_host: str = Field(min_length=1, max_length=253)
    endpoint_path: str = Field(min_length=1, max_length=500)
    http_status: int = Field(ge=100, le=599)
    latency_ms: int = Field(ge=0)
    model_ids: tuple[str, ...]
    model_count: int = Field(ge=0)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_model_count(self) -> ModelCatalogReceipt:
        if self.model_count != len(self.model_ids):
            raise ValueError("model_count must match model_ids length")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("model_ids must be unique")
        return self
