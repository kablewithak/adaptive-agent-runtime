from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import ProviderErrorCode, ProviderProtocol
from adaptive_runtime.contracts.wire_diagnostic import FlashWireDiagnosticReceipt
from adaptive_runtime.providers.huawei_http import classify_huawei_http_error

_EXPECTED_TOOL_NAME = "lookup_fixture"
_EXPECTED_FINAL_TEXT = "FIXTURE_VALUE=42"
_TOOL_RESULT_TEXT = '{"fixture_id":"fixture-17","value":42}'

_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": _EXPECTED_TOOL_NAME,
        "description": "Return the deterministic value for a fixture ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "fixture_id": {
                    "type": "string",
                    "description": "Fixture identifier.",
                }
            },
            "required": ["fixture_id"],
            "additionalProperties": False,
        },
    },
}

_USER_MESSAGE = {
    "role": "user",
    "content": (
        "Call lookup_fixture for fixture_id fixture-17. "
        "Do not answer from memory. After the tool result is returned, "
        "reply exactly FIXTURE_VALUE=<value>."
    ),
}


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _safe_provider_error_identifier(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if not isinstance(error, dict):
        return None

    candidate = error.get("code")
    if not isinstance(candidate, str):
        return None

    candidate = candidate.strip()
    if not candidate or len(candidate) > 100:
        return None

    if not all(character.isalnum() or character in "._-" for character in candidate):
        return None

    return candidate


def _receipt_hash(payload: dict[str, object]) -> str:
    without_hash = dict(payload)
    without_hash.pop("receipt_sha256", None)
    return _canonical_sha256(without_hash)


def _failure_receipt(
    *,
    profile: EndpointProfile,
    observed_at: datetime,
    condition_code: str,
    first_request_sha256: str,
    first_http_status: int | None,
    second_request_sha256: str | None = None,
    second_http_status: int | None = None,
    assistant_message_sha256: str | None = None,
    assistant_message_keys: tuple[str, ...] = (),
    reasoning_content_present: bool = False,
    tool_call_count: int = 0,
    tool_call_id_present: bool = False,
    tool_name: str | None = None,
    tool_arguments_valid: bool = False,
    error_code: ProviderErrorCode | None = None,
    provider_error_identifier: str | None = None,
    retryable: bool = False,
) -> FlashWireDiagnosticReceipt:
    endpoint = profile.full_endpoint_url
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "profile_name": profile.profile_name,
        "model_id": profile.model_id,
        "endpoint_host": endpoint.host or "",
        "endpoint_path": endpoint.path or "/",
        "status": "fail",
        "condition_code": condition_code,
        "first_http_status": first_http_status,
        "second_http_status": second_http_status,
        "first_request_sha256": first_request_sha256,
        "second_request_sha256": second_request_sha256,
        "assistant_message_sha256": assistant_message_sha256,
        "assistant_message_keys": assistant_message_keys,
        "reasoning_content_present": reasoning_content_present,
        "tool_call_count": tool_call_count,
        "tool_call_id_present": tool_call_id_present,
        "tool_name": tool_name,
        "tool_arguments_valid": tool_arguments_valid,
        "final_exact_output_pass": False,
        "error_code": error_code,
        "provider_error_identifier": provider_error_identifier,
        "retryable": retryable,
    }
    payload["receipt_sha256"] = _receipt_hash(payload)
    return FlashWireDiagnosticReceipt.model_validate(payload)


def _post_json(
    *,
    client: httpx.Client,
    profile: EndpointProfile,
    api_key: str,
    payload: dict[str, object],
    timeout_seconds: float,
) -> httpx.Response:
    return client.post(
        str(profile.full_endpoint_url),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout_seconds,
    )


def run_flash_wire_diagnostic(
    *,
    profile: EndpointProfile,
    api_key: str,
    transport: httpx.BaseTransport | None = None,
) -> FlashWireDiagnosticReceipt:
    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise ValueError("flash wire diagnostic requires an OpenAI-compatible profile")
    if profile.model_id != "deepseek-v4-flash":
        raise ValueError("flash wire diagnostic is restricted to deepseek-v4-flash")
    if not api_key.strip():
        raise ValueError("api_key must not be empty")

    observed_at = datetime.now(UTC)

    first_payload: dict[str, object] = {
        "model": profile.model_id,
        "messages": [_USER_MESSAGE],
        "tools": [_TOOL_DEFINITION],
        "tool_choice": {
            "type": "function",
            "function": {"name": _EXPECTED_TOOL_NAME},
        },
    }
    first_request_sha256 = _canonical_sha256(first_payload)

    with httpx.Client(follow_redirects=False, transport=transport) as client:
        try:
            first_response = _post_json(
                client=client,
                profile=profile,
                api_key=api_key,
                payload=first_payload,
                timeout_seconds=60,
            )
        except httpx.TimeoutException:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="first_request_timeout",
                first_request_sha256=first_request_sha256,
                first_http_status=None,
                error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                retryable=True,
            )
        except httpx.RequestError:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="first_request_transport_error",
                first_request_sha256=first_request_sha256,
                first_http_status=None,
                error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            )

        if not first_response.is_success:
            classified = classify_huawei_http_error(first_response.status_code)
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="first_request_provider_rejected",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                error_code=classified.code,
                provider_error_identifier=_safe_provider_error_identifier(first_response),
                retryable=classified.retryable,
            )

        try:
            first_body = first_response.json()
        except ValueError:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="first_response_not_json",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        if not isinstance(first_body, dict):
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="first_response_shape_invalid",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        try:
            choices = first_body["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise TypeError
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError
            assistant_message = choice["message"]
            if not isinstance(assistant_message, dict):
                raise TypeError
        except (KeyError, TypeError):
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="assistant_message_missing",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        assistant_message_keys = tuple(sorted(str(key) for key in assistant_message))
        assistant_message_sha256 = _canonical_sha256(assistant_message)
        reasoning_content_present = bool(assistant_message.get("reasoning_content"))

        tool_calls = assistant_message.get("tool_calls")
        if not isinstance(tool_calls, list) or len(tool_calls) != 1:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="tool_call_count_invalid",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=len(tool_calls) if isinstance(tool_calls, list) else 0,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        tool_call = tool_calls[0]
        if not isinstance(tool_call, dict):
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="tool_call_shape_invalid",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        tool_call_id = tool_call.get("id")
        function = tool_call.get("function")
        if not isinstance(function, dict):
            function = {}
        tool_name = function.get("name")
        arguments_text = function.get("arguments")

        tool_arguments_valid = False
        if isinstance(arguments_text, str):
            try:
                arguments = json.loads(arguments_text)
                tool_arguments_valid = arguments == {"fixture_id": "fixture-17"}
            except json.JSONDecodeError:
                tool_arguments_valid = False

        if (
            not isinstance(tool_call_id, str)
            or not tool_call_id
            or tool_name != _EXPECTED_TOOL_NAME
            or not tool_arguments_valid
        ):
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="tool_call_semantics_invalid",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                tool_call_id_present=bool(tool_call_id),
                tool_name=str(tool_name) if tool_name is not None else None,
                tool_arguments_valid=tool_arguments_valid,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": _TOOL_RESULT_TEXT,
            "name": _EXPECTED_TOOL_NAME,
        }
        second_payload: dict[str, object] = {
            "model": profile.model_id,
            "messages": [_USER_MESSAGE, assistant_message, tool_message],
            "tools": [_TOOL_DEFINITION],
            "tool_choice": "auto",
        }
        second_request_sha256 = _canonical_sha256(second_payload)

        try:
            second_response = _post_json(
                client=client,
                profile=profile,
                api_key=api_key,
                payload=second_payload,
                timeout_seconds=60,
            )
        except httpx.TimeoutException:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="second_request_timeout",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                second_request_sha256=second_request_sha256,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                tool_call_id_present=True,
                tool_name=_EXPECTED_TOOL_NAME,
                tool_arguments_valid=True,
                error_code=ProviderErrorCode.PROVIDER_TIMEOUT,
                retryable=True,
            )
        except httpx.RequestError:
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="second_request_transport_error",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                second_request_sha256=second_request_sha256,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                tool_call_id_present=True,
                tool_name=_EXPECTED_TOOL_NAME,
                tool_arguments_valid=True,
                error_code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            )

        if not second_response.is_success:
            classified = classify_huawei_http_error(second_response.status_code)
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="raw_assistant_replay_provider_rejected",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                second_request_sha256=second_request_sha256,
                second_http_status=second_response.status_code,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                tool_call_id_present=True,
                tool_name=_EXPECTED_TOOL_NAME,
                tool_arguments_valid=True,
                error_code=classified.code,
                provider_error_identifier=_safe_provider_error_identifier(second_response),
                retryable=classified.retryable,
            )

        try:
            second_body: Any = second_response.json()
            choices = second_body["choices"]
            final_message = choices[0]["message"]
            final_content = final_message.get("content")
        except (ValueError, KeyError, TypeError, IndexError):
            return _failure_receipt(
                profile=profile,
                observed_at=observed_at,
                condition_code="second_response_shape_invalid",
                first_request_sha256=first_request_sha256,
                first_http_status=first_response.status_code,
                second_request_sha256=second_request_sha256,
                second_http_status=second_response.status_code,
                assistant_message_sha256=assistant_message_sha256,
                assistant_message_keys=assistant_message_keys,
                reasoning_content_present=reasoning_content_present,
                tool_call_count=1,
                tool_call_id_present=True,
                tool_name=_EXPECTED_TOOL_NAME,
                tool_arguments_valid=True,
                error_code=ProviderErrorCode.PROTOCOL_ERROR,
            )

    final_exact_output_pass = final_content == _EXPECTED_FINAL_TEXT
    payload = {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "profile_name": profile.profile_name,
        "model_id": profile.model_id,
        "endpoint_host": profile.full_endpoint_url.host or "",
        "endpoint_path": profile.full_endpoint_url.path or "/",
        "status": "pass" if final_exact_output_pass else "fail",
        "condition_code": (
            "raw_assistant_replay_round_trip_pass"
            if final_exact_output_pass
            else "raw_assistant_replay_final_output_mismatch"
        ),
        "first_http_status": first_response.status_code,
        "second_http_status": second_response.status_code,
        "first_request_sha256": first_request_sha256,
        "second_request_sha256": second_request_sha256,
        "assistant_message_sha256": assistant_message_sha256,
        "assistant_message_keys": assistant_message_keys,
        "reasoning_content_present": reasoning_content_present,
        "tool_call_count": 1,
        "tool_call_id_present": True,
        "tool_name": _EXPECTED_TOOL_NAME,
        "tool_arguments_valid": True,
        "final_exact_output_pass": final_exact_output_pass,
        "error_code": None,
        "provider_error_identifier": None,
        "retryable": False,
    }
    payload["receipt_sha256"] = _receipt_hash(payload)
    return FlashWireDiagnosticReceipt.model_validate(payload)


def save_flash_wire_diagnostic_receipt(
    receipt: FlashWireDiagnosticReceipt,
    directory: Path,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = receipt.observed_at.strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{timestamp}-{receipt.profile_name}-flash-wire-diagnostic.json"
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
