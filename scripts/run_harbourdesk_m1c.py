from __future__ import annotations

import argparse
import getpass
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_m1c import (
    M1CExperimentStatus,
    load_m1c_inputs,
    run_m1c_experiment,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run the frozen 12-case HarbourDesk M1C glm-5.2 baseline exactly once.")
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    parser.add_argument("--profile", default="glm-5-2-openai")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/m1c"),
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
    return datetime.now(UTC).strftime("m1c-glm52-%Y%m%dT%H%M%SZ")


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, args.profile)

    inputs = load_m1c_inputs(repo_root)

    run_id = _run_id(args.run_id)
    evidence_dir = repo_root / args.output_root / run_id
    api_key = _api_key()

    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_m1c_experiment(
            inputs=inputs,
            provider=provider,
            profile=profile,
            run_id=run_id,
            evidence_dir=evidence_dir,
        )

    print(f"M1C_STATUS={receipt.status.value}")
    print(f"M1C_BASELINE_COMPLETE={str(receipt.baseline_complete).upper()}")
    print(f"M1C_MODEL={receipt.frozen_configuration.model_id}")
    print(f"M1C_PROFILE={receipt.frozen_configuration.profile_name}")
    print(f"M1C_CASES={receipt.case_count}")
    print(f"M1C_SCORE_PASSES={receipt.score_pass_count}")
    print(f"M1C_SCORE_PASS_RATE={receipt.score_pass_rate:.6f}")
    print(f"M1C_USAGE_COMPLETE={str(receipt.usage_complete).upper()}")
    print(f"M1C_OBSERVED_INPUT_TOKENS={receipt.observed_input_tokens}")
    print(f"M1C_OBSERVED_COMPLETION_TOKENS={receipt.observed_completion_tokens}")
    print(f"M1C_OBSERVED_INFERENCE_TOKENS={receipt.observed_inference_tokens}")
    per_success = receipt.observed_tokens_per_verified_success
    print(
        f"M1C_TOKENS_PER_VERIFIED_SUCCESS={per_success:.6f}"
        if per_success is not None
        else "M1C_TOKENS_PER_VERIFIED_SUCCESS=UNKNOWN"
    )
    print(
        "M1C_STOP_COUNTS="
        + json.dumps(
            receipt.stop_category_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "M1C_SCORING_FAILURE_COUNTS="
        + json.dumps(
            receipt.scoring_failure_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    for case in receipt.cases:
        score = "PASS" if case.score_passed else "FAIL"
        usage = "COMPLETE" if case.usage_complete else "INCOMPLETE"
        print(
            "M1C_CASE_RESULT="
            f"{case.case_id}|{score}|{case.stop_category.value}|"
            f"attempts={case.attempt_count}|actions={case.tool_action_count}|"
            f"tokens={case.observed_input_tokens + case.observed_completion_tokens}|"
            f"usage={usage}"
        )

    print(f"M1C_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0 if receipt.status is M1CExperimentStatus.COMPLETE else 2


if __name__ == "__main__":
    raise SystemExit(main())
