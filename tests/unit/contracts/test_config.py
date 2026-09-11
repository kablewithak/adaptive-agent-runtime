from pathlib import Path

import pytest

from adaptive_runtime.contracts.config import (
    ConfigurationLoadError,
    EndpointProfile,
    load_account_config,
)
from adaptive_runtime.contracts.provider import ProviderProtocol


def _valid_profile_payload() -> dict[str, object]:
    return {
        "profile_name": "primary-openai",
        "protocol": "openai_compatible",
        "full_endpoint_url": "https://api.modelarts-maas.com/v1/chat/completions",
        "region_label": "console-confirmed-region",
        "model_id": "console-confirmed-model",
        "observed_at": "2026-09-11T14:00:00Z",
    }


def test_openai_profile_accepts_full_huawei_chat_endpoint() -> None:
    profile = EndpointProfile.model_validate(_valid_profile_payload())

    assert profile.protocol is ProviderProtocol.OPENAI_COMPATIBLE
    assert profile.full_endpoint_url.host == "api.modelarts-maas.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.modelarts-maas.com/v1/chat/completions",
        "https://example.com/v1/chat/completions",
        "https://api.modelarts-maas.com/v1/chat/completions?key=nope",
        "https://user:secret@api.modelarts-maas.com/v1/chat/completions",
    ],
)
def test_profile_rejects_unsafe_or_unexpected_endpoint(url: str) -> None:
    payload = _valid_profile_payload()
    payload["full_endpoint_url"] = url

    with pytest.raises(ValueError):
        EndpointProfile.model_validate(payload)


def test_openai_profile_requires_full_chat_completions_path() -> None:
    payload = _valid_profile_payload()
    payload["full_endpoint_url"] = "https://api.modelarts-maas.com/openai/v1"

    with pytest.raises(ValueError):
        EndpointProfile.model_validate(payload)


def test_anthropic_profile_requires_messages_path() -> None:
    payload = _valid_profile_payload()
    payload["protocol"] = "anthropic_compatible"
    payload["full_endpoint_url"] = "https://api.modelarts-maas.com/v1/messages"

    profile = EndpointProfile.model_validate(payload)

    assert profile.protocol is ProviderProtocol.ANTHROPIC_COMPATIBLE


def test_load_account_config_rejects_intentionally_incomplete_template(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "account.json"
    config_path.write_text(
        """
        {
          "schema_version": "1.0",
          "provider": "huawei_maas",
          "profiles": [
            {
              "profile_name": "",
              "protocol": "openai_compatible",
              "full_endpoint_url": "",
              "region_label": "",
              "model_id": "",
              "observed_at": ""
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationLoadError):
        load_account_config(config_path)
