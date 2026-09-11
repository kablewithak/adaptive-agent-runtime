import httpx
import pytest

from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint
from adaptive_runtime.contracts.provider import ProviderErrorCode
from adaptive_runtime.providers.base import ProviderCallError
from adaptive_runtime.providers.huawei_models import HuaweiModelCatalogClient


def _endpoint() -> ModelCatalogEndpoint:
    return ModelCatalogEndpoint.model_validate(
        {"url": "https://api-ap-southeast-1.modelarts-maas.com/v2/models"}
    )


def test_model_catalog_returns_model_ids_without_raw_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-flash", "object": "model", "created": 0},
                    {"id": "glm-5.2", "object": "model", "created": 0},
                ],
            },
        )

    with HuaweiModelCatalogClient(
        endpoint=_endpoint(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        model_ids, status, latency_ms = client.list_models()

    assert model_ids == ("deepseek-v4-flash", "glm-5.2")
    assert status == 200
    assert latency_ms >= 0


def test_model_catalog_does_not_follow_redirects() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(307, headers={"location": "https://example.com/steal"})

    with HuaweiModelCatalogClient(
        endpoint=_endpoint(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ProviderCallError) as exc_info:
            client.list_models()

    assert calls == 1
    assert exc_info.value.code is ProviderErrorCode.PROTOCOL_ERROR


def test_model_catalog_http_400_remains_ambiguous() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "secret provider explanation"})

    with HuaweiModelCatalogClient(
        endpoint=_endpoint(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ProviderCallError) as exc_info:
            client.list_models()

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_REJECTED
    assert "secret provider explanation" not in str(exc_info.value)


def test_model_catalog_rejects_duplicate_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "glm-5.2"},
                    {"id": "glm-5.2"},
                ],
            },
        )

    with HuaweiModelCatalogClient(
        endpoint=_endpoint(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ProviderCallError) as exc_info:
            client.list_models()

    assert exc_info.value.code is ProviderErrorCode.PROTOCOL_ERROR
