import json

import httpx

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import ProviderErrorCode
from adaptive_runtime.flash_wire_diagnostic import run_flash_wire_diagnostic


def _profile() -> EndpointProfile:
    return EndpointProfile.model_validate(
        {
            "profile_name": "deepseek-flash-openai",
            "protocol": "openai_compatible",
            "full_endpoint_url": (
                "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
            ),
            "region_label": "ap-southeast-1",
            "model_id": "deepseek-v4-flash",
            "observed_at": "2026-09-11T14:00:00Z",
        }
    )


def test_raw_assistant_message_is_replayed_without_dropping_provider_fields() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content.decode("utf-8"))

        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_content": "synthetic-provider-field",
                                "tool_calls": [
                                    {
                                        "id": "call-17",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup_fixture",
                                            "arguments": '{"fixture_id":"fixture-17"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                },
            )

        assert calls == 2
        assistant = payload["messages"][1]
        assert assistant["reasoning_content"] == "synthetic-provider-field"
        assert assistant["tool_calls"][0]["id"] == "call-17"
        assert payload["messages"][2] == {
            "role": "tool",
            "tool_call_id": "call-17",
            "content": '{"fixture_id":"fixture-17","value":42}',
            "name": "lookup_fixture",
        }
        assert payload["tool_choice"] == "auto"

        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "FIXTURE_VALUE=42",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    receipt = run_flash_wire_diagnostic(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    assert calls == 2
    assert receipt.status == "pass"
    assert receipt.condition_code == "raw_assistant_replay_round_trip_pass"
    assert receipt.reasoning_content_present is True
    assert "reasoning_content" in receipt.assistant_message_keys
    assert receipt.final_exact_output_pass is True


def test_second_request_http_400_is_preserved_as_failure_without_raw_body() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-17",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup_fixture",
                                            "arguments": '{"fixture_id":"fixture-17"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "wire_shape_rejected",
                    "message": "raw error body must not be persisted",
                }
            },
        )

    receipt = run_flash_wire_diagnostic(
        profile=_profile(),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    assert calls == 2
    assert receipt.status == "fail"
    assert receipt.condition_code == "raw_assistant_replay_provider_rejected"
    assert receipt.second_http_status == 400
    assert receipt.error_code is ProviderErrorCode.PROVIDER_REJECTED
    assert receipt.provider_error_identifier == "wire_shape_rejected"
    dumped = receipt.model_dump_json()
    assert "raw error body must not be persisted" not in dumped


def test_wrong_model_is_rejected_before_network_use() -> None:
    payload = _profile().model_dump(mode="json")
    payload["model_id"] = "deepseek-v4-pro"
    profile = EndpointProfile.model_validate(payload)

    try:
        run_flash_wire_diagnostic(profile=profile, api_key="test-secret")
    except ValueError as exc:
        assert "deepseek-v4-flash" in str(exc)
    else:
        raise AssertionError("expected diagnostic to reject non-Flash model")
