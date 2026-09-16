from __future__ import annotations

from pathlib import Path

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.experiments.harbourdesk_m1b import (
    FixedBaselineIdentity,
    M1BCaseInput,
    M1BExperimentReceipt,
    M1BExperimentStatus,
    M1BPublicCase,
    load_fixed_baseline_inputs,
    load_fixed_baseline_public_cases,
    run_fixed_model_baseline_experiment,
)
from adaptive_runtime.providers.base import ProviderAdapter

M1D_MODEL_ID = "deepseek-v4-flash"
M1D_PROFILE_NAME = "deepseek-flash-openai"

M1D_IDENTITY = FixedBaselineIdentity(
    stage_label="M1D",
    profile_name=M1D_PROFILE_NAME,
    model_id=M1D_MODEL_ID,
    frozen_configuration_schema_version="m1d-deepseek-flash-baseline-v1",
    manifest_schema_version="m1d-manifest-v1",
    case_receipt_schema_version="m1d-case-v1",
    experiment_receipt_schema_version="m1d-v1",
    model_profile_version="m1d-deepseek-flash-baseline-v1",
)

M1DCaseInput = M1BCaseInput
M1DPublicCase = M1BPublicCase
M1DExperimentReceipt = M1BExperimentReceipt
M1DExperimentStatus = M1BExperimentStatus


def load_m1d_public_cases(repo_root: Path) -> tuple[M1DPublicCase, ...]:
    return load_fixed_baseline_public_cases(repo_root)


def load_m1d_inputs(repo_root: Path) -> tuple[M1DCaseInput, ...]:
    return load_fixed_baseline_inputs(repo_root, stage_label="M1D")


def run_m1d_experiment(
    *,
    inputs: tuple[M1DCaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
) -> M1DExperimentReceipt:
    return run_fixed_model_baseline_experiment(
        inputs=inputs,
        provider=provider,
        profile=profile,
        run_id=run_id,
        evidence_dir=evidence_dir,
        identity=M1D_IDENTITY,
    )
