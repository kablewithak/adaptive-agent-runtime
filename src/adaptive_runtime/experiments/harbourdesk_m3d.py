from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.experiments.harbourdesk_m1b import (
    FixedBaselineIdentity,
    M1BCaseInput,
    M1BExperimentReceipt,
    M1BPublicCase,
    load_fixed_baseline_inputs,
    load_fixed_baseline_public_cases,
    run_fixed_model_baseline_experiment,
)
from adaptive_runtime.experiments.harbourdesk_m3c import collect_m3c_batch_evidence
from adaptive_runtime.providers.base import ProviderAdapter
from adaptive_runtime.runtime.harbourdesk_live import LiveRunBudget, LiveStopCategory

M3D_MODEL_ID = "glm-5.2"
M3D_PROFILE_NAME = "glm-5-2-openai"
M3D_BASELINE_RUN_ID = "m3c-glm52-compatibility-20260927-01"
M3D_BASELINE_MANIFEST_SHA256 = "1f0172daaa9a275a64a4a6aa54e003d44d5d8e8bae8e05dd2c3313221f1fbaa8"
M3D_BASELINE_SUMMARY_SHA256 = "233b283bcbbfacf4ae3c1cbae461214db9d025f14f2ca25e3330c8064226c14c"
M3D_BASELINE_DECISION_SHA256 = "952d47f3ad771e74370c5fd7b85c70242f253c016669134d3466d203a3feab24"

M3D_CASE_IDS = tuple(f"hdm-{index:03d}" for index in range(1, 13))
M3D_TARGET_CASE_IDS = ("hdm-003", "hdm-008", "hdm-012")
M3D_BASELINE_MAX_COMPLETION_TOKENS = 768
M3D_MAX_COMPLETION_TOKENS = 1536

M3D_IDENTITY = FixedBaselineIdentity(
    stage_label="M3D",
    profile_name=M3D_PROFILE_NAME,
    model_id=M3D_MODEL_ID,
    frozen_configuration_schema_version="m3d-glm52-completion-envelope-v1",
    manifest_schema_version="m3d-manifest-v1",
    case_receipt_schema_version="m3d-case-v1",
    experiment_receipt_schema_version="m3d-run-v1",
    model_profile_version="m3d-glm52-completion-envelope-v1",
)

M3D_BUDGET = LiveRunBudget(
    max_model_calls=8,
    max_tool_actions=10,
    trajectory_deadline_seconds=300.0,
    request_deadline_seconds=60.0,
    max_completion_tokens=M3D_MAX_COMPLETION_TOKENS,
)

M3DCaseInput = M1BCaseInput
M3DPublicCase = M1BPublicCase


class M3DError(RuntimeError):
    """Raised when M3D evidence cannot be produced against its frozen contract."""


class M3DGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class M3DContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class M3DBaselineReference(M3DContract):
    schema_version: Literal["m3d-baseline-reference-v1"] = "m3d-baseline-reference-v1"
    run_id: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=0)
    verified_pass_case_ids: tuple[str, ...]
    length_limited_case_ids: tuple[str, ...]
    max_completion_tokens: int = Field(gt=0)
    observed_inference_tokens: int = Field(ge=0)
    usage_complete: bool


class M3DBatchEvidence(M3DContract):
    schema_version: Literal["m3d-batch-evidence-v1"] = "m3d-batch-evidence-v1"
    accepted_batch_count: int = Field(ge=0)
    rejected_batch_count: int = Field(ge=0)
    accepted_read_call_count: int = Field(ge=0)
    rejection_reason_counts: dict[str, int]
    deterministic_control_violation_count: int = Field(ge=0)
    realized_write_from_multi_tool_batch_count: int = Field(ge=0)


class M3DInterventionMetrics(M3DContract):
    schema_version: Literal["m3d-intervention-metrics-v1"] = "m3d-intervention-metrics-v1"
    case_ids: tuple[str, ...]
    baseline_verified_pass_case_ids: tuple[str, ...]
    verified_pass_case_ids: tuple[str, ...]
    target_case_ids: tuple[str, ...]
    target_length_stop_case_ids: tuple[str, ...]
    target_terminal_case_ids: tuple[str, ...]
    deterministic_control_violation_count: int = Field(ge=0)
    realized_write_from_multi_tool_batch_count: int = Field(ge=0)
    usage_complete: bool

    @model_validator(mode="after")
    def validate_identity(self) -> M3DInterventionMetrics:
        if self.case_ids != M3D_CASE_IDS:
            raise ValueError("M3D requires hdm-001 through hdm-012 exactly once")
        if self.target_case_ids != M3D_TARGET_CASE_IDS:
            raise ValueError("M3D target cases are frozen to hdm-003, hdm-008, hdm-012")

        case_ids = set(self.case_ids)
        target_ids = set(self.target_case_ids)
        for values, label, allowed in (
            (
                self.baseline_verified_pass_case_ids,
                "baseline verified pass case IDs",
                case_ids,
            ),
            (self.verified_pass_case_ids, "verified pass case IDs", case_ids),
            (
                self.target_length_stop_case_ids,
                "target length-stop case IDs",
                target_ids,
            ),
            (self.target_terminal_case_ids, "target terminal case IDs", target_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
            if set(values) - allowed:
                raise ValueError(f"{label} contain unknown case IDs")
        return self


class M3DGateEvaluation(M3DContract):
    schema_version: Literal["m3d-gate-v1"] = "m3d-gate-v1"
    safety_status: M3DGateStatus
    baseline_pass_preservation_status: M3DGateStatus
    completion_envelope_status: M3DGateStatus
    usage_status: M3DGateStatus
    overall_status: M3DGateStatus
    verified_pass_count: int = Field(ge=0)
    preserved_baseline_pass_count: int = Field(ge=0)
    target_length_stop_count: int = Field(ge=0)
    target_terminal_count: int = Field(ge=0)
    target_verified_pass_count: int = Field(ge=0)
    preservation_fail_case_ids: tuple[str, ...]
    target_verified_pass_case_ids: tuple[str, ...]
    deterministic_control_violation_count: int = Field(ge=0)
    realized_write_from_multi_tool_batch_count: int = Field(ge=0)


class M3DExperimentReceipt(M3DContract):
    schema_version: Literal["m3d-evaluation-v1"] = "m3d-evaluation-v1"
    baseline: M3DBaselineReference
    intervention_run: M1BExperimentReceipt
    batch_evidence: M3DBatchEvidence
    intervention_metrics: M3DInterventionMetrics
    gate: M3DGateEvaluation


def load_m3d_public_cases(repo_root: Path) -> tuple[M3DPublicCase, ...]:
    return load_fixed_baseline_public_cases(repo_root)


def load_m3d_inputs(repo_root: Path) -> tuple[M3DCaseInput, ...]:
    return load_fixed_baseline_inputs(repo_root, stage_label="M3D")


def load_m3d_baseline_reference(baseline_dir: Path) -> M3DBaselineReference:
    manifest_path = baseline_dir / "manifest.json"
    summary_path = baseline_dir / "summary.json"
    decision_path = baseline_dir / "m3c_decision.json"
    required = (manifest_path, summary_path, decision_path)
    if any(not path.is_file() for path in required):
        raise M3DError("canonical M3D comparator evidence is incomplete")

    manifest_sha256 = _sha256_file(manifest_path)
    summary_sha256 = _sha256_file(summary_path)
    decision_sha256 = _sha256_file(decision_path)

    if manifest_sha256 != M3D_BASELINE_MANIFEST_SHA256:
        raise M3DError("canonical M3D comparator manifest SHA256 does not match")
    if summary_sha256 != M3D_BASELINE_SUMMARY_SHA256:
        raise M3DError("canonical M3D comparator summary SHA256 does not match")
    if decision_sha256 != M3D_BASELINE_DECISION_SHA256:
        raise M3DError("canonical M3D comparator decision SHA256 does not match")

    baseline = M1BExperimentReceipt.model_validate_json(summary_path.read_text(encoding="utf-8"))
    if baseline.run_id != M3D_BASELINE_RUN_ID:
        raise M3DError("canonical M3D comparator run ID does not match")
    if baseline.frozen_configuration.max_completion_tokens != (M3D_BASELINE_MAX_COMPLETION_TOKENS):
        raise M3DError("canonical M3D comparator completion ceiling does not match")

    length_limited: list[str] = []
    for case_id in M3D_TARGET_CASE_IDS:
        stop_reason, completion_tokens = _final_attempt_evidence(
            baseline_dir / case_id / "trace.jsonl"
        )
        if stop_reason != "length" or completion_tokens != M3D_BASELINE_MAX_COMPLETION_TOKENS:
            raise M3DError(
                f"canonical M3D comparator no longer proves the 768-token ceiling for {case_id}"
            )
        length_limited.append(case_id)

    return M3DBaselineReference(
        run_id=baseline.run_id,
        manifest_sha256=manifest_sha256,
        summary_sha256=summary_sha256,
        decision_sha256=decision_sha256,
        case_count=baseline.case_count,
        verified_pass_case_ids=tuple(case.case_id for case in baseline.cases if case.score_passed),
        length_limited_case_ids=tuple(length_limited),
        max_completion_tokens=baseline.frozen_configuration.max_completion_tokens,
        observed_inference_tokens=baseline.observed_inference_tokens,
        usage_complete=baseline.usage_complete,
    )


def run_m3d_experiment(
    *,
    inputs: tuple[M3DCaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
    baseline: M3DBaselineReference,
) -> M3DExperimentReceipt:
    run = run_fixed_model_baseline_experiment(
        inputs=inputs,
        provider=provider,
        profile=profile,
        run_id=run_id,
        evidence_dir=evidence_dir,
        identity=M3D_IDENTITY,
        budget=M3D_BUDGET,
    )

    batch_evidence = _collect_batch_evidence(evidence_dir, run)
    target_length_stops: list[str] = []
    target_terminal: list[str] = []

    receipt_by_case = {case.case_id: case for case in run.cases}
    for case_id in M3D_TARGET_CASE_IDS:
        stop_reason, _ = _final_attempt_evidence(evidence_dir / case_id / "trace.jsonl")
        if stop_reason == "length":
            target_length_stops.append(case_id)
        if receipt_by_case[case_id].stop_category is LiveStopCategory.TICKET_TERMINAL:
            target_terminal.append(case_id)

    metrics = M3DInterventionMetrics(
        case_ids=M3D_CASE_IDS,
        baseline_verified_pass_case_ids=baseline.verified_pass_case_ids,
        verified_pass_case_ids=tuple(case.case_id for case in run.cases if case.score_passed),
        target_case_ids=M3D_TARGET_CASE_IDS,
        target_length_stop_case_ids=tuple(target_length_stops),
        target_terminal_case_ids=tuple(target_terminal),
        deterministic_control_violation_count=(
            batch_evidence.deterministic_control_violation_count
        ),
        realized_write_from_multi_tool_batch_count=(
            batch_evidence.realized_write_from_multi_tool_batch_count
        ),
        usage_complete=run.usage_complete,
    )
    gate = evaluate_m3d_gate(metrics)
    receipt = M3DExperimentReceipt(
        baseline=baseline,
        intervention_run=run,
        batch_evidence=batch_evidence,
        intervention_metrics=metrics,
        gate=gate,
    )
    _write_json(evidence_dir / "m3d_decision.json", receipt)
    return receipt


def evaluate_m3d_gate(metrics: M3DInterventionMetrics) -> M3DGateEvaluation:
    current_passes = set(metrics.verified_pass_case_ids)
    baseline_passes = set(metrics.baseline_verified_pass_case_ids)
    target_ids = set(metrics.target_case_ids)

    preservation_failures = tuple(
        case_id
        for case_id in metrics.baseline_verified_pass_case_ids
        if case_id not in current_passes
    )
    target_verified = tuple(
        case_id for case_id in metrics.target_case_ids if case_id in current_passes
    )

    safety_status = (
        M3DGateStatus.PASS
        if metrics.deterministic_control_violation_count == 0
        and metrics.realized_write_from_multi_tool_batch_count == 0
        else M3DGateStatus.FAIL
    )
    preservation_status = (
        M3DGateStatus.PASS if baseline_passes.issubset(current_passes) else M3DGateStatus.FAIL
    )
    completion_envelope_status = (
        M3DGateStatus.PASS
        if not metrics.target_length_stop_case_ids
        and bool(set(metrics.target_terminal_case_ids) & target_ids)
        else M3DGateStatus.FAIL
    )
    usage_status = M3DGateStatus.PASS if metrics.usage_complete else M3DGateStatus.INCONCLUSIVE

    deterministic_statuses = (
        safety_status,
        preservation_status,
        completion_envelope_status,
    )
    if M3DGateStatus.FAIL in deterministic_statuses:
        overall_status = M3DGateStatus.FAIL
    elif usage_status == M3DGateStatus.INCONCLUSIVE:
        overall_status = M3DGateStatus.INCONCLUSIVE
    else:
        overall_status = M3DGateStatus.PASS

    return M3DGateEvaluation(
        safety_status=safety_status,
        baseline_pass_preservation_status=preservation_status,
        completion_envelope_status=completion_envelope_status,
        usage_status=usage_status,
        overall_status=overall_status,
        verified_pass_count=len(current_passes),
        preserved_baseline_pass_count=len(current_passes & baseline_passes),
        target_length_stop_count=len(metrics.target_length_stop_case_ids),
        target_terminal_count=len(metrics.target_terminal_case_ids),
        target_verified_pass_count=len(target_verified),
        preservation_fail_case_ids=preservation_failures,
        target_verified_pass_case_ids=target_verified,
        deterministic_control_violation_count=(metrics.deterministic_control_violation_count),
        realized_write_from_multi_tool_batch_count=(
            metrics.realized_write_from_multi_tool_batch_count
        ),
    )


def _collect_batch_evidence(
    evidence_dir: Path,
    run: M1BExperimentReceipt,
) -> M3DBatchEvidence:
    evidence = collect_m3c_batch_evidence(evidence_dir, run)
    return M3DBatchEvidence(
        accepted_batch_count=evidence.accepted_batch_count,
        rejected_batch_count=evidence.rejected_batch_count,
        accepted_read_call_count=evidence.accepted_read_call_count,
        rejection_reason_counts=evidence.rejection_reason_counts,
        deterministic_control_violation_count=(evidence.deterministic_control_violation_count),
        realized_write_from_multi_tool_batch_count=(
            evidence.realized_write_from_multi_tool_batch_count
        ),
    )


def _final_attempt_evidence(trace_path: Path) -> tuple[str | None, int | None]:
    if not trace_path.is_file():
        raise M3DError(f"M3D trace missing: {trace_path}")

    final_attempt: dict[str, object] | None = None
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise M3DError(f"M3D trace is not valid JSONL: {trace_path}") from exc
        if event.get("event") == "attempt_finished":
            attempt = event.get("attempt")
            if isinstance(attempt, dict):
                final_attempt = attempt

    if final_attempt is None:
        raise M3DError(f"M3D trace has no completed provider attempt: {trace_path}")

    stop_reason_raw = final_attempt.get("stop_reason")
    stop_reason = str(stop_reason_raw) if stop_reason_raw is not None else None
    usage = final_attempt.get("usage")
    completion_tokens: int | None = None
    if isinstance(usage, dict):
        value = usage.get("completion_tokens")
        if isinstance(value, int):
            completion_tokens = value
    return stop_reason, completion_tokens


def _write_json(path: Path, payload: BaseModel) -> None:
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
