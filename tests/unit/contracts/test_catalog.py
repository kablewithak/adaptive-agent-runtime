import pytest

from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint


@pytest.mark.parametrize(
    "url",
    [
        "http://api-ap-southeast-1.modelarts-maas.com/v2/models",
        "https://example.com/v2/models",
        "https://api-ap-southeast-1.modelarts-maas.com/v2/models?key=nope",
        "https://user:secret@api-ap-southeast-1.modelarts-maas.com/v2/models",
        "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/models",
    ],
)
def test_model_catalog_endpoint_rejects_unsafe_or_wrong_urls(url: str) -> None:
    with pytest.raises(ValueError):
        ModelCatalogEndpoint.model_validate({"url": url})


def test_model_catalog_endpoint_accepts_documented_hong_kong_url() -> None:
    endpoint = ModelCatalogEndpoint.model_validate(
        {"url": "https://api-ap-southeast-1.modelarts-maas.com/v2/models"}
    )

    assert endpoint.url.host == "api-ap-southeast-1.modelarts-maas.com"
