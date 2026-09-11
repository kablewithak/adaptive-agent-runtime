import httpx

from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint
from adaptive_runtime.model_discovery import run_model_discovery


def test_model_discovery_builds_sanitised_hashed_receipt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-flash"},
                    {"id": "deepseek-v4-pro"},
                    {"id": "glm-5.1"},
                    {"id": "glm-5.2"},
                ],
            },
        )

    receipt = run_model_discovery(
        endpoint=ModelCatalogEndpoint.model_validate(
            {"url": "https://api-ap-southeast-1.modelarts-maas.com/v2/models"}
        ),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    assert receipt.model_count == 4
    assert receipt.model_ids[-1] == "glm-5.2"
    assert len(receipt.receipt_sha256) == 64
    assert "test-secret" not in receipt.model_dump_json()
