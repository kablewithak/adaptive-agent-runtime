from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.environment.read_tools import ReadToolName
from adaptive_runtime.environment.write_tools import WriteToolName
from adaptive_runtime.experiments.harbourdesk_m1b import (
    FixedBaselineIdentity,
    M1BCaseInput,
    M1BExperimentReceipt,
    M1BPublicCase,
    load_fixed_baseline_inputs,
    load_fixed_baseline_public_cases,
    run_fixed_model_baseline_experiment,
)
from adaptive_runtime.experiments.harbourdesk_m3a import (
    M3A_CASE_IDS,
    M3CGateEvaluation,
    M3CInterventionMetrics,
    evaluate_m3c_gate,
)
from adaptive_runtime.providers.base import ProviderAdapter
from adaptive_runtime.runtime.harbourdesk_live import LiveStopCategory

M3C_MODEL_ID = "glm-5.2"
M3C_PROFILE_NAME = "glm-5-2-openai"
M3C_BASELINE_RUN_ID = "m1c-glm52-baseline-20260915-01"
M3C_BASELINE_MANIFEST_SHA256 = "71e037b91eff5298f7e1490e75bde568b002e0135f67b22497681d8c6734d7df"
M3C_BASELINE_SUMMARY_SHA256 = "c0b4654c866bb75b65661e7198e8206da83bc0d188d880a8699f8d44b8551f3b"

M3C_IDENTITY = FixedBaselineIdentity(
    stage_label="M3C",
    profile_name=M3C_PROFILE_NAME,
    model_id=M3C_MODEL_ID,
    frozen_configuration_schema_version="m3c-glm52-compatibility-v1",
    manifest_schema_version="m3c-manifest-v1",
    case_receipt_schema_version="m3c-case-v1",
    experiment_receipt_schema_version="m3c-run-v1",
    model_profile_version="m3c-glm52-compatibility-v1",
)

M3CCaseInput = M1BCaseInput
M3CPublicCase = M1BPublicCase


class M3CError(RuntimeError):
    """Raised when M3C evidence cannot be produced against its frozen contract."""


class M3CContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class M3CBaselineReference(M3CContract):
    schema_version: Literal["m3c-baseline-reference-v1"] = "m3c-baseline-reference-v1"
    run_id: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=0)
    verified_pass_case_ids: tuple[str, ...]
    multi_tool_incompatibility_stop_count: int = Field(ge=0)
    observed_inference_tokens: int = Field(ge=0)
    usage_complete: bool


class M3CBatchEvidence(M3CContract):
    schema_version: Literal["m3c-batch-evidence-v1"] = "m3c-batch-evidence-v1"
    accepted_batch_count: int = Field(ge=0)
    rejected_batch_count: int = Field(ge=0)
    accepted_read_call_count: int = Field(ge=0)
    rejection_reason_counts: dict[str, int]
    deterministic_control_violation_count: int = Field(ge=0)
    realized_write_from_multi_tool_batch_count: int = Field(ge=0)


class M3CExperimentReceipt(M3CContract):
    schema_version: Literal["m3c-evaluation-v1"] = "m3c-evaluation-v1"
    baseline: M3CBaselineReference
    intervention_run: M1BExperimentReceipt
    batch_evidence: M3CBatchEvidence
    intervention_metrics: M3CInterventionMetrics
    gate: M3CGateEvaluation


def load_m3c_public_cases(repo_root: Path) -> tuple[M3CPublicCase, ...]:
    return load_fixed_baseline_public_cases(repo_root)


def load_m3c_inputs(repo_root: Path) -> tuple[M3CCaseInput, ...]:
    return load_fixed_baseline_inputs(repo_root, stage_label="M3C")


def load_m3c_baseline_reference(baseline_dir: Path) -> M3CBaselineReference:
    manifest_path = baseline_dir / "manifest.json"
    summary_path = baseline_dir / "summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        raise M3CError("canonical M3C baseline manifest/summary is missing")

    manifest_sha256 = _sha256_file(manifest_path)
    summary_sha256 = _sha256_file(summary_path)
    if manifest_sha256 != M3C_BASELINE_MANIFEST_SHA256:
        raise M3CError("canonical M3C baseline manifest SHA256 does not match")
    if summary_sha256 != M3C_BASELINE_SUMMARY_SHA256:
        raise M3CError("canonical M3C baseline summary SHA256 does not match")

    baseline = M1BExperimentReceipt.model_validate_json(summary_path.read_text(encoding="utf-8"))
    if baseline.run_id != M3C_BASELINE_RUN_ID:
        raise M3CError("canonical M3C baseline run ID does not match")

    pass_case_ids = tuple(case.case_id for case in baseline.cases if case.score_passed)
    multi_tool_stops = sum(
        1 for case in baseline.cases if case.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    )

    return M3CBaselineReference(
        run_id=baseline.run_id,
        manifest_sha256=manifest_sha256,
        summary_sha256=summary_sha256,
        case_count=baseline.case_count,
        verified_pass_case_ids=pass_case_ids,
        multi_tool_incompatibility_stop_count=multi_tool_stops,
        observed_inference_tokens=baseline.observed_inference_tokens,
        usage_complete=baseline.usage_complete,
    )


def run_m3c_experiment(
    *,
    inputs: tuple[M3CCaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
    baseline: M3CBaselineReference,
) -> M3CExperimentReceipt:
    run = run_fixed_model_baseline_experiment(
        inputs=inputs,
        provider=provider,
        profile=profile,
        run_id=run_id,
        evidence_dir=evidence_dir,
        identity=M3C_IDENTITY,
    )

    batch_evidence = collect_m3c_batch_evidence(evidence_dir, run)
    verified_pass_case_ids = tuple(case.case_id for case in run.cases if case.score_passed)
    multi_tool_stops = sum(
        1 for case in run.cases if case.stop_category is LiveStopCategory.MULTI_TOOL_CALL
    )
    metrics = M3CInterventionMetrics(
        case_ids=M3A_CASE_IDS,
        verified_pass_case_ids=verified_pass_case_ids,
        multi_tool_incompatibility_stop_count=multi_tool_stops,
        deterministic_control_violation_count=(
            batch_evidence.deterministic_control_violation_count
        ),
        realized_write_from_multi_tool_batch_count=(
            batch_evidence.realized_write_from_multi_tool_batch_count
        ),
        usage_complete=run.usage_complete,
    )
    gate = evaluate_m3c_gate(metrics)
    receipt = M3CExperimentReceipt(
        baseline=baseline,
        intervention_run=run,
        batch_evidence=batch_evidence,
        intervention_metrics=metrics,
        gate=gate,
    )
    _write_json(evidence_dir / "m3c_decision.json", receipt)
    return receipt


def collect_m3c_batch_evidence(
    evidence_dir: Path,
    run: M1BExperimentReceipt,
) -> M3CBatchEvidence:
    accepted_batches = 0
    rejected_batches = 0
    accepted_read_calls = 0
    control_violations = 0
    realized_batch_writes = 0
    rejection_reasons: Counter[str] = Counter()
    read_names = {tool.value for tool in ReadToolName}
    write_names = {tool.value for tool in WriteToolName}

    for case in run.cases:
        trace_path = evidence_dir / case.case_id / "trace.jsonl"
        if not trace_path.is_file():
            raise M3CError(f"M3C trace missing for {case.case_id}")

        accepted_batch_active = False
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise M3CError(f"M3C trace is not valid JSONL: {trace_path}") from exc

            event_name = event.get("event")
            if event_name == "attempt_started":
                accepted_batch_active = False
                continue

            if event_name == "multi_tool_batch_preflight":
                accepted = event.get("accepted") is True
                tool_names = tuple(str(name) for name in event.get("tool_names", []))
                accepted_batch_active = accepted
                if accepted:
                    accepted_batches += 1
                    accepted_read_calls += sum(name in read_names for name in tool_names)
                    if any(name not in read_names for name in tool_names):
                        control_violations += 1
                else:
                    rejected_batches += 1
                    reason = event.get("rejection_reason")
                    rejection_reasons[str(reason or "unknown")] += 1
                continue

            if event_name == "tool_action_finished" and accepted_batch_active:
                action = event.get("action")
                if not isinstance(action, dict):
                    control_violations += 1
                    continue
                tool_name = str(action.get("tool", ""))
                if tool_name in write_names:
                    realized_batch_writes += 1
                    control_violations += 1
                elif tool_name not in read_names:
                    control_violations += 1
                continue

            if event_name == "run_finished":
                accepted_batch_active = False

    return M3CBatchEvidence(
        accepted_batch_count=accepted_batches,
        rejected_batch_count=rejected_batches,
        accepted_read_call_count=accepted_read_calls,
        rejection_reason_counts=dict(sorted(rejection_reasons.items())),
        deterministic_control_violation_count=control_violations,
        realized_write_from_multi_tool_batch_count=realized_batch_writes,
    )


def _write_json(path: Path, payload: BaseModel) -> None:
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
