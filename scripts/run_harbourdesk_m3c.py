from __future__ import annotations

import argparse
import getpass
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_m3c import (
    load_m3c_baseline_reference,
    load_m3c_inputs,
    run_m3c_experiment,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen HarbourDesk M3C glm-5.2 read-only multi-tool "
            "compatibility evaluation exactly once."
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
        default=Path("runs/m3c"),
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("runs/m1c/m1c-glm52-baseline-20260915-01"),
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
    return datetime.now(UTC).strftime("m3c-glm52-compatibility-%Y%m%dT%H%M%SZ")


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, args.profile)
    inputs = load_m3c_inputs(repo_root)
    baseline = load_m3c_baseline_reference(repo_root / args.baseline_dir)

    run_id = _run_id(args.run_id)
    evidence_dir = repo_root / args.output_root / run_id
    api_key = _api_key()

    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_m3c_experiment(
            inputs=inputs,
            provider=provider,
            profile=profile,
            run_id=run_id,
            evidence_dir=evidence_dir,
            baseline=baseline,
        )

    run = receipt.intervention_run
    gate = receipt.gate
    batch = receipt.batch_evidence

    print(f"M3C_STATUS={gate.overall_status.value}")
    print(f"M3C_MODEL={run.frozen_configuration.model_id}")
    print(f"M3C_PROFILE={run.frozen_configuration.profile_name}")
    print(f"M3C_CASES={run.case_count}")
    print(f"M3C_SCORE_PASSES={run.score_pass_count}")
    print(f"M3C_SCORE_PASS_RATE={run.score_pass_rate:.6f}")
    print(f"M3C_USAGE_COMPLETE={str(run.usage_complete).upper()}")
    print(f"M3C_OBSERVED_INPUT_TOKENS={run.observed_input_tokens}")
    print(f"M3C_OBSERVED_COMPLETION_TOKENS={run.observed_completion_tokens}")
    print(f"M3C_OBSERVED_INFERENCE_TOKENS={run.observed_inference_tokens}")
    per_success = run.observed_tokens_per_verified_success
    print(
        f"M3C_TOKENS_PER_VERIFIED_SUCCESS={per_success:.6f}"
        if per_success is not None
        else "M3C_TOKENS_PER_VERIFIED_SUCCESS=UNKNOWN"
    )
    print(
        "M3C_STOP_COUNTS="
        + json.dumps(run.stop_category_counts, sort_keys=True, separators=(",", ":"))
    )
    print(
        "M3C_SCORING_FAILURE_COUNTS="
        + json.dumps(run.scoring_failure_counts, sort_keys=True, separators=(",", ":"))
    )
    print(f"M3C_ACCEPTED_MULTI_READ_BATCHES={batch.accepted_batch_count}")
    print(f"M3C_REJECTED_MULTI_TOOL_BATCHES={batch.rejected_batch_count}")
    print(f"M3C_ACCEPTED_MULTI_READ_CALLS={batch.accepted_read_call_count}")
    print(
        "M3C_BATCH_REJECTION_REASONS="
        + json.dumps(batch.rejection_reason_counts, sort_keys=True, separators=(",", ":"))
    )
    print(f"M3C_DETERMINISTIC_CONTROL_VIOLATIONS={batch.deterministic_control_violation_count}")
    print(
        "M3C_REALIZED_WRITES_FROM_MULTI_TOOL_BATCHES="
        f"{batch.realized_write_from_multi_tool_batch_count}"
    )
    print(f"M3C_GATE_SAFETY={gate.safety_status.value}")
    print(f"M3C_GATE_BASELINE_PASS_PRESERVATION={gate.baseline_pass_preservation_status.value}")
    print(f"M3C_GATE_QUALITY={gate.quality_status.value}")
    print(f"M3C_GATE_COMPATIBILITY={gate.compatibility_status.value}")
    print(f"M3C_GATE_USAGE={gate.usage_status.value}")

    for case in run.cases:
        score = "PASS" if case.score_passed else "FAIL"
        usage = "COMPLETE" if case.usage_complete else "INCOMPLETE"
        print(
            "M3C_CASE_RESULT="
            f"{case.case_id}|{score}|{case.stop_category.value}|"
            f"attempts={case.attempt_count}|actions={case.tool_action_count}|"
            f"tokens={case.observed_input_tokens + case.observed_completion_tokens}|"
            f"usage={usage}"
        )

    print(f"M3C_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
