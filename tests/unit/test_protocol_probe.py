import json

import httpx

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.protocol_probe import (
    ProtocolProbeKind,
    ProtocolProbeStatus,
)
from adaptive_runtime.protocol_probe import (
    recommended_inter_call_seconds,
    run_protocol_capability_probes,
)


def _profile(model_id: str = "glm-5.2") -> EndpointProfile:
    return EndpointProfile.model_validate(
        {
            "profile_name": "probe-profile",
            "protocol": "openai_compatible",
            "full_endpoint_url": (
                "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
            ),
            "region_label": "ap-southeast-1",
            "model_id": model_id,
            "observed_at": "2026-09-11T14:00:00Z",
        }
    )


def test_deepseek_default_spacing_is_conservative_for_three_rpm() -> None:
    assert recommended_inter_call_seconds("deepseek-v4-flash") == 22.0
    assert recommended_inter_call_seconds("deepseek-v4-pro") == 22.0
    assert recommended_inter_call_seconds("glm-5.2") == 1.0


def test_protocol_probe_validates_json_tools_round_trip_thinking_and_usage() -> None:
    call_number = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_number
        call_number += 1
        payload = json.loads(request.content.decode("utf-8"))

        usage = {
            "prompt_tokens": 10 + call_number,
            "completion_tokens": 3,
            "completion_tokens_details": {"reasoning_tokens": 0},
            "prompt_tokens_details": {"cached_tokens": 0},
        }

        if call_number == 1:
            assert payload["max_completion_tokens"] == 512
            return httpx.Response(
                200,
                json={
                    "model": "glm-5.2",
                    "choices": [
                        {
                            "message": {"content": "OUTPUT_CAP_OK"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                },
            )

        if call_number == 2:
            assert payload["chat_template_kwargs"] == {"thinking": False}
            return httpx.Response(
                200,
                json={
                    "model": "glm-5.2",
                    "choices": [
                        {
                            "message": {"content": "THINKING_OFF_OK"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                },
            )

        if call_number == 3:
            return httpx.Response(
                200,
                json={
                    "model": "glm-5.2",
                    "choices": [
                        {
                            "message": {"content": '{"fixture_id":"fixture-17","value":42}'},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                },
            )

        if call_number == 4:
            assert payload["tool_choice"]["function"]["name"] == "lookup_fixture"
            return httpx.Response(
                200,
                json={
                    "model": "glm-5.2",
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "reasoning_content": "private-provider-reasoning",
                                "tool_calls": [
                                    {
                                        "id": "call-fixture",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup_fixture",
                                            "arguments": ('{"fixture_id":"fixture-17"}'),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": usage,
                },
            )

        assert call_number == 5
        assert payload["tool_choice"] == "auto"
        assert payload["messages"][2]["name"] == "lookup_fixture"
        return httpx.Response(
            200,
            json={
                "model": "glm-5.2",
                "choices": [
                    {
                        "message": {"content": "FIXTURE_VALUE=42"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            },
        )

    sleeps: list[float] = []
    receipt = run_protocol_capability_probes(
        profile=_profile(),
        api_key="test-secret",
        inter_call_seconds=0.5,
        sleep_fn=sleeps.append,
        transport=httpx.MockTransport(handler),
    )

    assert call_number == 5
    assert sleeps == [0.5, 0.5, 0.5, 0.5]
    assert receipt.overall_status is ProtocolProbeStatus.PASS
    assert [item.kind for item in receipt.probes] == [
        ProtocolProbeKind.OUTPUT_CAP,
        ProtocolProbeKind.THINKING_OFF,
        ProtocolProbeKind.JSON_CONTRACT,
        ProtocolProbeKind.TOOL_CALL,
        ProtocolProbeKind.TOOL_ROUND_TRIP,
    ]
    assert all(item.status is ProtocolProbeStatus.PASS for item in receipt.probes)
    assert all(item.usage_present for item in receipt.probes)
    assert receipt.probes[1].condition_code == "thinking_off_accepted_reasoning_zero"


def test_terminal_auth_failure_stops_further_live_calls() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "not stored"})

    receipt = run_protocol_capability_probes(
        profile=_profile(),
        api_key="bad-key",
        inter_call_seconds=0,
        sleep_fn=lambda _: None,
        transport=httpx.MockTransport(handler),
    )

    assert calls == 1
    assert receipt.overall_status is ProtocolProbeStatus.FAIL
    assert receipt.probes[0].status is ProtocolProbeStatus.FAIL
    assert all(item.status is ProtocolProbeStatus.SKIPPED for item in receipt.probes[1:])
