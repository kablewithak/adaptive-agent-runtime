from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_r5 import run_r5_preflight
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    load_r5_reference_inputs,
    run_r5_reference,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen 90-case HarbourDesk R5 GLM-5.2 development reference exactly once."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    parser.add_argument("--profile", default="glm-5-2-openai")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/r5_reference"),
    )
    parser.add_argument(
        "--confirm-live-r5",
        action="store_true",
        help="Required explicit acknowledgement that this command makes live provider calls.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    if not args.confirm_live_r5:
        raise SystemExit("R5 live execution requires explicit --confirm-live-r5")

    current_head = _git(repo_root, "rev-parse", "HEAD")
    if current_head != args.expected_head:
        raise SystemExit("current HEAD does not match --expected-head; refusing live traffic")

    dirty = _git(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
    )
    if dirty:
        raise SystemExit(
            "tracked working tree is not clean; commit or restore changes before R5 live traffic"
        )

    preflight = run_r5_preflight(
        repo_root,
        config_path=args.config,
    )
    if preflight.status != "PASS":
        raise SystemExit(
            "R5 preflight no longer passes; refusing live traffic: "
            + json.dumps(preflight.failures)
        )

    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, args.profile)
    inputs = load_r5_reference_inputs(repo_root)
    evidence_dir = repo_root / args.output_root / args.run_id

    api_key = _api_key()
    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_r5_reference(
            repo_root=repo_root,
            inputs=inputs,
            provider=provider,
            profile=profile,
            run_id=args.run_id,
            candidate_commit=current_head,
            evidence_dir=evidence_dir,
        )

    print(f"R5_REFERENCE_STATUS={receipt.status}")
    print(f"R5_REFERENCE_COMMIT={receipt.candidate_commit}")
    print(f"R5_REFERENCE_MODEL={receipt.model_id}")
    print(f"R5_REFERENCE_PROFILE={receipt.profile_name}")
    print(f"R5_REFERENCE_MAX_COMPLETION_TOKENS={receipt.max_completion_tokens}")
    print(f"R5_REFERENCE_CASES={receipt.case_count}")
    print(f"R5_REFERENCE_SCORE_PASSES={receipt.score_pass_count}")
    print(f"R5_REFERENCE_SCORE_PASS_RATE={receipt.score_pass_rate:.6f}")
    print(f"R5_REFERENCE_USAGE_COMPLETE={str(receipt.usage_complete).upper()}")
    print(f"R5_REFERENCE_INPUT_TOKENS={receipt.observed_input_tokens}")
    print(f"R5_REFERENCE_COMPLETION_TOKENS={receipt.observed_completion_tokens}")
    print(f"R5_REFERENCE_INFERENCE_TOKENS={receipt.observed_inference_tokens}")
    if receipt.observed_tokens_per_verified_success is None:
        print("R5_REFERENCE_TOKENS_PER_VERIFIED_SUCCESS=UNKNOWN")
    else:
        print(
            "R5_REFERENCE_TOKENS_PER_VERIFIED_SUCCESS="
            f"{receipt.observed_tokens_per_verified_success:.6f}"
        )
    print(
        "R5_REFERENCE_STOP_COUNTS="
        + json.dumps(
            receipt.stop_category_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "R5_REFERENCE_SCORING_FAILURE_COUNTS="
        + json.dumps(
            receipt.scoring_failure_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "R5_REFERENCE_FAMILY_METRICS="
        + json.dumps(
            {key: value.model_dump(mode="json") for key, value in receipt.family_metrics.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R5_REFERENCE_ACCEPTED_MULTI_READ_BATCHES={receipt.accepted_multi_read_batch_count}")
    print(f"R5_REFERENCE_REJECTED_MULTI_TOOL_BATCHES={receipt.rejected_multi_tool_batch_count}")
    print(
        "R5_REFERENCE_DETERMINISTIC_CONTROL_VIOLATIONS="
        f"{receipt.deterministic_control_violation_count}"
    )
    print(
        "R5_REFERENCE_WRITES_FROM_MULTI_TOOL_BATCHES="
        f"{receipt.realized_write_from_multi_tool_batch_count}"
    )
    print(f"R5_REFERENCE_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0


def _api_key() -> str:
    value = os.environ.get("HUAWEI_MAAS_API_KEY", "").strip()
    if value:
        return value

    entered = getpass.getpass("Huawei MaaS API key (hidden): ").strip()
    if not entered:
        raise ValueError("Huawei MaaS API key is required")
    return entered


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
