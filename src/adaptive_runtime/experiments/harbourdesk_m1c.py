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

M1C_MODEL_ID = "glm-5.2"
M1C_PROFILE_NAME = "glm-5-2-openai"

M1C_IDENTITY = FixedBaselineIdentity(
    stage_label="M1C",
    profile_name=M1C_PROFILE_NAME,
    model_id=M1C_MODEL_ID,
    frozen_configuration_schema_version="m1c-glm52-baseline-v1",
    manifest_schema_version="m1c-manifest-v1",
    case_receipt_schema_version="m1c-case-v1",
    experiment_receipt_schema_version="m1c-v1",
    model_profile_version="m1c-glm52-baseline-v1",
)

M1CCaseInput = M1BCaseInput
M1CPublicCase = M1BPublicCase
M1CExperimentReceipt = M1BExperimentReceipt
M1CExperimentStatus = M1BExperimentStatus


def load_m1c_public_cases(repo_root: Path) -> tuple[M1CPublicCase, ...]:
    return load_fixed_baseline_public_cases(repo_root)


def load_m1c_inputs(repo_root: Path) -> tuple[M1CCaseInput, ...]:
    return load_fixed_baseline_inputs(repo_root, stage_label="M1C")


def run_m1c_experiment(
    *,
    inputs: tuple[M1CCaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
) -> M1CExperimentReceipt:
    return run_fixed_model_baseline_experiment(
        inputs=inputs,
        provider=provider,
        profile=profile,
        run_id=run_id,
        evidence_dir=evidence_dir,
        identity=M1C_IDENTITY,
    )
