from __future__ import annotations

import argparse
import getpass
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_m3d import (
    load_m3d_baseline_reference,
    load_m3d_inputs,
    run_m3d_experiment,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen HarbourDesk M3D glm-5.2 completion-envelope diagnostic exactly once."
        )
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
        default=Path("runs/m3d"),
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("runs/m3c/m3c-glm52-compatibility-20260927-01"),
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
    return datetime.now(UTC).strftime("m3d-glm52-completion-envelope-%Y%m%dT%H%M%SZ")


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, args.profile)
    inputs = load_m3d_inputs(repo_root)
    baseline = load_m3d_baseline_reference(repo_root / args.baseline_dir)

    run_id = _run_id(args.run_id)
    evidence_dir = repo_root / args.output_root / run_id
    api_key = _api_key()

    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_m3d_experiment(
            inputs=inputs,
            provider=provider,
            profile=profile,
            run_id=run_id,
            evidence_dir=evidence_dir,
            baseline=baseline,
        )

    run = receipt.intervention_run
    gate = receipt.gate
    metrics = receipt.intervention_metrics

    print(f"M3D_STATUS={gate.overall_status.value}")
    print(f"M3D_MODEL={run.frozen_configuration.model_id}")
    print(f"M3D_PROFILE={run.frozen_configuration.profile_name}")
    print(f"M3D_MAX_COMPLETION_TOKENS={run.frozen_configuration.max_completion_tokens}")
    print(f"M3D_CASES={run.case_count}")
    print(f"M3D_SCORE_PASSES={run.score_pass_count}")
    print(f"M3D_SCORE_PASS_RATE={run.score_pass_rate:.6f}")
    print(f"M3D_USAGE_COMPLETE={str(run.usage_complete).upper()}")
    print(f"M3D_OBSERVED_INFERENCE_TOKENS={run.observed_inference_tokens}")
    per_success = run.observed_tokens_per_verified_success
    print(
        f"M3D_TOKENS_PER_VERIFIED_SUCCESS={per_success:.6f}"
        if per_success is not None
        else "M3D_TOKENS_PER_VERIFIED_SUCCESS=UNKNOWN"
    )
    print(
        "M3D_STOP_COUNTS="
        + json.dumps(
            run.stop_category_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "M3D_SCORING_FAILURE_COUNTS="
        + json.dumps(
            run.scoring_failure_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print("M3D_TARGET_LENGTH_STOPS=" + ",".join(metrics.target_length_stop_case_ids))
    print("M3D_TARGET_TERMINALS=" + ",".join(metrics.target_terminal_case_ids))
    print("M3D_TARGET_VERIFIED_PASSES=" + ",".join(gate.target_verified_pass_case_ids))
    print("M3D_PRESERVATION_FAILURES=" + ",".join(gate.preservation_fail_case_ids))
    print(f"M3D_GATE_SAFETY={gate.safety_status.value}")
    print(f"M3D_GATE_BASELINE_PASS_PRESERVATION={gate.baseline_pass_preservation_status.value}")
    print(f"M3D_GATE_COMPLETION_ENVELOPE={gate.completion_envelope_status.value}")
    print(f"M3D_GATE_USAGE={gate.usage_status.value}")

    for case in run.cases:
        score = "PASS" if case.score_passed else "FAIL"
        usage = "COMPLETE" if case.usage_complete else "INCOMPLETE"
        print(
            "M3D_CASE_RESULT="
            f"{case.case_id}|{score}|{case.stop_category.value}|"
            f"attempts={case.attempt_count}|actions={case.tool_action_count}|"
            f"tokens={case.observed_input_tokens + case.observed_completion_tokens}|"
            f"usage={usage}"
        )

    print(f"M3D_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
