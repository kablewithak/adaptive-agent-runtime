import httpx

from adaptive_runtime.capability_probe import run_openai_text_probe
from adaptive_runtime.contracts.capability import ProbeStatus
from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import ProviderErrorCode, ProviderProtocol


def _profile() -> EndpointProfile:
    return EndpointProfile.model_validate(
        {
            "profile_name": "primary-openai",
            "protocol": "openai_compatible",
            "full_endpoint_url": (
                "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
            ),
            "region_label": "console-region",
            "model_id": "glm-5.1",
            "observed_at": "2026-09-11T14:00:00Z",
        }
    )


def test_probe_passes_only_on_exact_expected_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "glm-5.1",
                "choices": [
                    {
                        "message": {"content": "MAAS_SMOKE_OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    receipt = run_openai_text_probe(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    assert receipt.status is ProbeStatus.PASS
    assert receipt.exact_output_pass is True
    assert receipt.protocol is ProviderProtocol.OPENAI_COMPATIBLE
    assert receipt.usage_present is True
    assert len(receipt.receipt_sha256) == 64


def test_probe_records_failure_without_provider_error_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": "do-not-store-this-provider-body"},
        )

    receipt = run_openai_text_probe(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    assert receipt.status is ProbeStatus.FAIL
    assert receipt.error_code is ProviderErrorCode.ENTITLEMENT_DENIED
    assert receipt.http_status == 403
    dumped = receipt.model_dump_json()
    assert "do-not-store-this-provider-body" not in dumped
