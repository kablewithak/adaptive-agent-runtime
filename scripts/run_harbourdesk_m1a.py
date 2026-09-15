from __future__ import annotations

import argparse
import getpass
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_m1a import (
    M1AExperimentStatus,
    load_private_expected,
    load_public_case,
    run_m1a_experiment,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the bounded M1A HarbourDesk context-envelope probe and glm-5.1 canary."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    parser.add_argument("--profile", default="primary-openai")
    parser.add_argument("--case", default="hdm-001")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/m1a"),
    )
    return parser


def _api_key() -> str:
    value = os.environ.get("HUAWEI_MAAS_API_KEY", "").strip()
    if value:
        return value
    entered = getpass.getpass("Huawei MaaS API key (hidden): ").strip()
    if not entered:
        raise ValueError("Huawei MaaS API key is required")
    return entered


def _run_id(value: str | None) -> str:
    if value is not None and value.strip():
        return value.strip()
    return datetime.now(UTC).strftime("m1a-%Y%m%dT%H%M%SZ")


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, args.profile)
    case = load_public_case(repo_root, args.case)
    expected = load_private_expected(repo_root, args.case)
    run_id = _run_id(args.run_id)
    evidence_dir = repo_root / args.output_root / run_id
    api_key = _api_key()

    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_m1a_experiment(
            case=case,
            expected=expected,
            provider=provider,
            profile=profile,
            run_id=run_id,
            evidence_dir=evidence_dir,
        )

    print(f"M1A_STATUS={receipt.status.value}")
    print(f"M1A_GATE_PASSED={str(receipt.gate_passed).upper()}")
    print(f"M1A_CASE={receipt.case_id}")
    print(f"M1A_MODEL={receipt.model_id}")
    print(f"M1A_PROFILE={receipt.profile_name}")
    print(f"M1A_ENVELOPE_STATUS={receipt.envelope.status.value}")
    envelope_tokens = receipt.envelope.sufficient_working_envelope_tokens
    print(
        "M1A_SUFFICIENT_WORKING_ENVELOPE_TOKENS="
        f"{envelope_tokens if envelope_tokens is not None else 'UNKNOWN'}"
    )
    print(f"M1A_CANARY_STOP={receipt.canary.stop_category.value}")
    print(f"M1A_CANARY_SCORE_PASS={str(receipt.canary.score_passed).upper()}")
    print(f"M1A_CANARY_ATTEMPTS={receipt.canary.attempt_count}")
    print(f"M1A_CANARY_TOOL_ACTIONS={receipt.canary.tool_action_count}")
    print(f"M1A_STAGE_USAGE_COMPLETE={str(receipt.stage_usage_complete).upper()}")
    print(f"M1A_OBSERVED_STAGE_TOKENS={receipt.observed_stage_tokens}")
    within = receipt.within_stage_token_cap
    print(f"M1A_WITHIN_STAGE_TOKEN_CAP={str(within).upper() if within is not None else 'UNKNOWN'}")
    print(f"M1A_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")

    return 0 if receipt.status is M1AExperimentStatus.PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
