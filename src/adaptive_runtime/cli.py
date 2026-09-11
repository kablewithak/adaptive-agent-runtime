from __future__ import annotations

import argparse
import getpass
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.capability_probe import (
    run_openai_text_probe,
    save_capability_receipt,
)
from adaptive_runtime.contracts.capability import ProbeStatus
from adaptive_runtime.contracts.catalog import ModelCatalogEndpoint
from adaptive_runtime.contracts.config import (
    AccountConfig,
    ConfigurationLoadError,
    EndpointProfile,
    get_profile,
    load_account_config,
    save_account_config,
)
from adaptive_runtime.contracts.provider import ProviderProtocol
from adaptive_runtime.flash_wire_diagnostic import (
    run_flash_wire_diagnostic,
    save_flash_wire_diagnostic_receipt,
)
from adaptive_runtime.model_discovery import run_model_discovery, save_model_catalog_receipt
from adaptive_runtime.protocol_probe import (
    recommended_inter_call_seconds,
    run_protocol_capability_probes,
    save_protocol_capability_receipt,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adaptive_runtime")
    subparsers = parser.add_subparsers(dest="command")

    configure = subparsers.add_parser(
        "configure-profile",
        help="Create or update one nonsecret local Huawei endpoint profile.",
    )
    configure.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    configure.add_argument("--profile")
    configure.add_argument("--endpoint")
    configure.add_argument("--region")
    configure.add_argument("--model")

    capabilities = subparsers.add_parser(
        "capabilities",
        help="Run one bounded OpenAI-compatible exact-text capability probe.",
    )
    capabilities.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    capabilities.add_argument("--profile", required=True)
    capabilities.add_argument("--expected-text", default="MAAS_SMOKE_OK")
    capabilities.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("runs/capabilities"),
    )

    models = subparsers.add_parser(
        "models",
        help="Query the Huawei MaaS model catalog and save a sanitised receipt.",
    )
    models.add_argument("--endpoint", required=True)
    models.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("runs/capabilities"),
    )

    protocol_probes = subparsers.add_parser(
        "protocol-probes",
        help=(
            "Run bounded JSON, tool-calling, round-trip, output-cap, and "
            "thinking-control probes for one configured model."
        ),
    )
    protocol_probes.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    protocol_probes.add_argument("--profile", required=True)
    protocol_probes.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("runs/capabilities"),
    )
    protocol_probes.add_argument(
        "--inter-call-seconds",
        type=float,
        default=None,
    )

    flash_wire = subparsers.add_parser(
        "flash-wire-diagnostic",
        help=(
            "Run the bounded two-call DeepSeek V4 Flash raw assistant-message "
            "tool-continuation diagnostic."
        ),
    )
    flash_wire.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    flash_wire.add_argument("--profile", required=True)
    flash_wire.add_argument(
        "--receipt-dir",
        type=Path,
        default=Path("runs/capabilities"),
    )

    return parser


def _prompt(value: str | None, label: str, default: str | None = None) -> str:
    if value is not None and value.strip():
        return value.strip()

    prompt = label
    if default is not None:
        prompt = f"{label} [{default}]"

    entered = input(f"{prompt}: ").strip()

    if entered:
        return entered
    if default is not None:
        return default
    raise ValueError(f"{label} is required")


def _configure_profile(args: argparse.Namespace) -> int:
    config_path: Path = args.config

    profile_name = _prompt(args.profile, "Profile name", "primary-openai")
    endpoint = _prompt(args.endpoint, "Full Huawei chat completion URL")
    region = _prompt(args.region, "Console region label")
    model = _prompt(args.model, "Exact enabled model ID")

    profile = EndpointProfile.model_validate(
        {
            "profile_name": profile_name,
            "protocol": ProviderProtocol.OPENAI_COMPATIBLE,
            "full_endpoint_url": endpoint,
            "region_label": region,
            "model_id": model,
            "observed_at": datetime.now(UTC),
        }
    )

    existing_profiles: list[EndpointProfile] = []

    if config_path.exists():
        existing = load_account_config(config_path)
        existing_profiles = [
            item for item in existing.profiles if item.profile_name != profile.profile_name
        ]

    existing_profiles.append(profile)

    config = AccountConfig(
        schema_version="1.0",
        provider="huawei_maas",
        profiles=tuple(existing_profiles),
    )
    save_account_config(config_path, config)

    print(f"CONFIG_PROFILE_SAVED={profile.profile_name}")
    print(f"CONFIG_PATH={config_path}")
    print("SECRET_STORED=NO")
    return 0


def _get_api_key() -> str:
    from_environment = os.environ.get("HUAWEI_MAAS_API_KEY", "").strip()
    if from_environment:
        return from_environment

    entered = getpass.getpass("Huawei MaaS API key (hidden): ").strip()
    if not entered:
        raise ValueError("Huawei MaaS API key is required")
    return entered


def _run_capability_probe(args: argparse.Namespace) -> int:
    config = load_account_config(args.config)
    profile = get_profile(config, args.profile)

    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise ConfigurationLoadError(
            "P0.2 capabilities command requires an OpenAI-compatible profile"
        )

    api_key = _get_api_key()
    receipt = run_openai_text_probe(
        profile=profile,
        api_key=api_key,
        expected_text=args.expected_text,
    )
    receipt_path = save_capability_receipt(receipt, args.receipt_dir)

    print(f"CAPABILITY_STATUS={receipt.status.value}")
    print(f"EXACT_OUTPUT_PASS={str(receipt.exact_output_pass).upper()}")
    print(f"HTTP_STATUS={receipt.http_status if receipt.http_status is not None else 'UNKNOWN'}")
    print(f"RETURNED_MODEL={receipt.returned_model or 'UNKNOWN'}")
    print(f"USAGE_PRESENT={str(receipt.usage_present).upper()}")
    print(f"LATENCY_MS={receipt.latency_ms}")
    print(f"ERROR_CODE={receipt.error_code.value if receipt.error_code else 'NONE'}")
    print(f"RETRYABLE={str(receipt.retryable).upper()}")
    print(f"RECEIPT_SHA256={receipt.receipt_sha256}")
    print(f"RECEIPT_PATH={receipt_path}")

    if receipt.status is ProbeStatus.PASS:
        return 0
    return 2


def _run_model_discovery(args: argparse.Namespace) -> int:
    endpoint = ModelCatalogEndpoint.model_validate({"url": args.endpoint})
    api_key = _get_api_key()
    receipt = run_model_discovery(endpoint=endpoint, api_key=api_key)
    receipt_path = save_model_catalog_receipt(receipt, args.receipt_dir)

    print("MODEL_DISCOVERY_STATUS=pass")
    print(f"HTTP_STATUS={receipt.http_status}")
    print(f"MODEL_COUNT={receipt.model_count}")
    for model_id in receipt.model_ids:
        print(f"MODEL_ID={model_id}")
    print(f"LATENCY_MS={receipt.latency_ms}")
    print(f"RECEIPT_SHA256={receipt.receipt_sha256}")
    print(f"RECEIPT_PATH={receipt_path}")
    return 0


def _run_protocol_probes(args: argparse.Namespace) -> int:
    config = load_account_config(args.config)
    profile = get_profile(config, args.profile)

    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise ConfigurationLoadError("P0.4 protocol probes require an OpenAI-compatible profile")

    interval = args.inter_call_seconds
    if interval is None:
        interval = recommended_inter_call_seconds(profile.model_id)
    if interval < 0 or interval > 120:
        raise ValueError("inter-call-seconds must be between 0 and 120")

    print(f"PROTOCOL_PROBE_MODEL={profile.model_id}")
    print("PROTOCOL_PROBE_PLANNED_MAX_CALLS=5")
    print(f"PROTOCOL_PROBE_INTER_CALL_SECONDS={interval}")
    print("PROTOCOL_PROBE_AUTOMATIC_RETRIES=0")

    api_key = _get_api_key()
    receipt = run_protocol_capability_probes(
        profile=profile,
        api_key=api_key,
        inter_call_seconds=interval,
    )
    receipt_path = save_protocol_capability_receipt(receipt, args.receipt_dir)

    print(f"PROTOCOL_PROBE_STATUS={receipt.overall_status.value}")
    for probe in receipt.probes:
        prefix = f"PROBE_{probe.kind.value.upper()}"
        print(f"{prefix}_STATUS={probe.status.value}")
        print(f"{prefix}_CONDITION={probe.condition_code}")
        print(
            f"{prefix}_HTTP_STATUS="
            f"{probe.http_status if probe.http_status is not None else 'UNKNOWN'}"
        )
        print(f"{prefix}_USAGE_PRESENT={str(probe.usage_present).upper()}")
        if probe.usage is not None:
            print(
                f"{prefix}_INPUT_TOKENS="
                f"{probe.usage.input_tokens if probe.usage.input_tokens is not None else 'UNKNOWN'}"
            )
            completion_tokens = probe.usage.completion_tokens
            reasoning_tokens = probe.usage.reasoning_tokens
            cached_input_tokens = probe.usage.cached_input_tokens
            print(
                f"{prefix}_COMPLETION_TOKENS="
                f"{completion_tokens if completion_tokens is not None else 'UNKNOWN'}"
            )
            print(
                f"{prefix}_REASONING_TOKENS="
                f"{reasoning_tokens if reasoning_tokens is not None else 'UNKNOWN'}"
            )
            print(
                f"{prefix}_CACHED_INPUT_TOKENS="
                f"{cached_input_tokens if cached_input_tokens is not None else 'UNKNOWN'}"
            )
        print(
            f"{prefix}_ERROR_CODE="
            f"{probe.error_code.value if probe.error_code is not None else 'NONE'}"
        )
        print(f"{prefix}_RETRYABLE={str(probe.retryable).upper()}")
        print(
            f"{prefix}_LATENCY_MS={probe.latency_ms if probe.latency_ms is not None else 'UNKNOWN'}"
        )

    print(f"RECEIPT_SHA256={receipt.receipt_sha256}")
    print(f"RECEIPT_PATH={receipt_path}")

    if receipt.overall_status.value == "pass":
        return 0
    return 2


def _run_flash_wire_diagnostic(args: argparse.Namespace) -> int:
    config = load_account_config(args.config)
    profile = get_profile(config, args.profile)

    if profile.model_id != "deepseek-v4-flash":
        raise ConfigurationLoadError("flash-wire-diagnostic requires the deepseek-v4-flash profile")

    print(f"FLASH_WIRE_MODEL={profile.model_id}")
    print("FLASH_WIRE_PLANNED_MAX_CALLS=2")
    print("FLASH_WIRE_AUTOMATIC_RETRIES=0")
    print("FLASH_WIRE_RAW_ASSISTANT_BODY_PERSISTED=NO")

    api_key = _get_api_key()
    receipt = run_flash_wire_diagnostic(profile=profile, api_key=api_key)
    receipt_path = save_flash_wire_diagnostic_receipt(receipt, args.receipt_dir)

    print(f"FLASH_WIRE_STATUS={receipt.status}")
    print(f"FLASH_WIRE_CONDITION={receipt.condition_code}")
    print(
        "FLASH_WIRE_FIRST_HTTP_STATUS="
        f"{receipt.first_http_status if receipt.first_http_status is not None else 'UNKNOWN'}"
    )
    print(
        "FLASH_WIRE_SECOND_HTTP_STATUS="
        f"{receipt.second_http_status if receipt.second_http_status is not None else 'UNKNOWN'}"
    )
    print("FLASH_WIRE_ASSISTANT_MESSAGE_KEYS=" + ",".join(receipt.assistant_message_keys))
    print(f"FLASH_WIRE_REASONING_CONTENT_PRESENT={str(receipt.reasoning_content_present).upper()}")
    print(f"FLASH_WIRE_TOOL_CALL_COUNT={receipt.tool_call_count}")
    print(f"FLASH_WIRE_TOOL_ARGUMENTS_VALID={str(receipt.tool_arguments_valid).upper()}")
    print(f"FLASH_WIRE_FINAL_EXACT_OUTPUT_PASS={str(receipt.final_exact_output_pass).upper()}")
    print(
        "FLASH_WIRE_ERROR_CODE="
        f"{receipt.error_code.value if receipt.error_code is not None else 'NONE'}"
    )
    print(f"FLASH_WIRE_PROVIDER_ERROR_IDENTIFIER={receipt.provider_error_identifier or 'NONE'}")
    print(f"RECEIPT_SHA256={receipt.receipt_sha256}")
    print(f"RECEIPT_PATH={receipt_path}")

    if receipt.status == "pass":
        return 0
    return 2


def main(argv: Sequence[str] = ()) -> int:
    if not argv:
        print("adaptive-agent-runtime bootstrap OK")
        return 0

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "configure-profile":
        return _configure_profile(args)

    if args.command == "capabilities":
        return _run_capability_probe(args)

    if args.command == "models":
        return _run_model_discovery(args)

    if args.command == "protocol-probes":
        return _run_protocol_probes(args)

    if args.command == "flash-wire-diagnostic":
        return _run_flash_wire_diagnostic(args)

    parser.print_help()
    return 2
