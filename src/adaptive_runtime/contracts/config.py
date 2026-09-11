from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from adaptive_runtime.contracts.provider import ProviderProtocol


class EndpointProfile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    profile_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    protocol: ProviderProtocol
    full_endpoint_url: HttpUrl
    region_label: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    max_tested_prompt_tokens: int | None = Field(default=None, gt=0)
    max_tested_completion_tokens: int | None = Field(default=None, gt=0)
    thinking_control: bool | None = None
    usage_mapping_version: str | None = Field(default=None, max_length=100)
    rpm_operating_limit: int | None = Field(default=None, gt=0)
    tpm_operating_limit: int | None = Field(default=None, gt=0)
    capability_receipt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_endpoint(self) -> EndpointProfile:
        url = self.full_endpoint_url
        host = url.host or ""

        if url.scheme != "https":
            raise ValueError("full_endpoint_url must use HTTPS")

        if not host.endswith(".modelarts-maas.com"):
            raise ValueError("full_endpoint_url must use a Huawei ModelArts MaaS host")

        if url.username is not None or url.password is not None:
            raise ValueError("credentials must not be embedded in full_endpoint_url")

        if url.query is not None:
            raise ValueError("full_endpoint_url must not contain a query string")

        if url.fragment is not None:
            raise ValueError("full_endpoint_url must not contain a fragment")

        path = (url.path or "").rstrip("/")

        if self.protocol is ProviderProtocol.OPENAI_COMPATIBLE and not path.endswith(
            "/chat/completions"
        ):
            raise ValueError("OpenAI-compatible profile requires a full /chat/completions endpoint")

        if self.protocol is ProviderProtocol.ANTHROPIC_COMPATIBLE and not path.endswith(
            "/messages"
        ):
            raise ValueError("Anthropic-compatible profile requires a full /messages endpoint")

        return self


class AccountConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    schema_version: str = Field(pattern=r"^1\.0$")
    provider: str = Field(pattern=r"^huawei_maas$")
    profiles: tuple[EndpointProfile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_profile_names(self) -> AccountConfig:
        names = [profile.profile_name for profile in self.profiles]
        if len(names) != len(set(names)):
            raise ValueError("profile_name values must be unique")
        return self


class ConfigurationLoadError(RuntimeError):
    pass


def load_account_config(path: Path) -> AccountConfig:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationLoadError(f"unable to read account config: {path}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigurationLoadError("account config is not valid JSON") from exc

    try:
        return AccountConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigurationLoadError("account config failed validation") from exc


def save_account_config(path: Path, config: AccountConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def get_profile(config: AccountConfig, profile_name: str) -> EndpointProfile:
    for profile in config.profiles:
        if profile.profile_name == profile_name:
            return profile
    raise ConfigurationLoadError(f"profile not found: {profile_name}")
