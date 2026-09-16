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

M1E_MODEL_ID = "deepseek-v4-pro"
M1E_PROFILE_NAME = "deepseek-pro-openai"

M1E_IDENTITY = FixedBaselineIdentity(
    stage_label="M1E",
    profile_name=M1E_PROFILE_NAME,
    model_id=M1E_MODEL_ID,
    frozen_configuration_schema_version="m1e-deepseek-pro-baseline-v1",
    manifest_schema_version="m1e-manifest-v1",
    case_receipt_schema_version="m1e-case-v1",
    experiment_receipt_schema_version="m1e-v1",
    model_profile_version="m1e-deepseek-pro-baseline-v1",
)

M1ECaseInput = M1BCaseInput
M1EPublicCase = M1BPublicCase
M1EExperimentReceipt = M1BExperimentReceipt
M1EExperimentStatus = M1BExperimentStatus


def load_m1e_public_cases(repo_root: Path) -> tuple[M1EPublicCase, ...]:
    return load_fixed_baseline_public_cases(repo_root)


def load_m1e_inputs(repo_root: Path) -> tuple[M1ECaseInput, ...]:
    return load_fixed_baseline_inputs(repo_root, stage_label="M1E")


def run_m1e_experiment(
    *,
    inputs: tuple[M1ECaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
) -> M1EExperimentReceipt:
    return run_fixed_model_baseline_experiment(
        inputs=inputs,
        provider=provider,
        profile=profile,
        run_id=run_id,
        evidence_dir=evidence_dir,
        identity=M1E_IDENTITY,
    )
