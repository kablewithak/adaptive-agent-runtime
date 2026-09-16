from __future__ import annotations

import hashlib
from itertools import product
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.model_observation import build_initial_model_observation
from adaptive_runtime.experiments.harbourdesk_m1b import (
    M1B_CASE_IDS,
    M1BExperimentReceipt,
    load_fixed_baseline_public_cases,
)
from adaptive_runtime.routing.contracts import (
    M2A_ALTERNATIVE_MODEL_ID,
    M2A_ALTERNATIVE_PROFILE_NAME,
    M2A_MIN_VERIFIED_PASSES,
    M2A_REFERENCE_MODEL_ID,
    M2A_REFERENCE_PROFILE_NAME,
    RoutingGateInput,
    RoutingGateStatus,
    RoutingObservation,
    build_routing_observation,
    evaluate_routing_gate,
)

REFERENCE_SHA256 = "f3eb5ed5091bb055679c21ccfe717b832b02a22aad4aa32e1c5446655be0e02d"
ALTERNATIVE_SHA256 = "c0b4654c866bb75b65661e7198e8206da83bc0d188d880a8699f8d44b8551f3b"


class M2BS2Error(RuntimeError):
    """Raised when frozen evidence cannot support the feature-ceiling audit."""


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CaseEvidence(Contract):
    case_id: str
    score_passed: bool
    inference_tokens: int = Field(ge=0)


class StructuralCase(Contract):
    case_id: str
    observation: RoutingObservation
    reference: CaseEvidence
    alternative: CaseEvidence


class SignatureGroup(Contract):
    signature_id: str
    signature: str
    case_ids: tuple[str, ...]


class SignatureChoice(Contract):
    signature_id: str
    selected_profile_name: str
    selected_model_id: str
    case_ids: tuple[str, ...]


class SignatureAssignment(Contract):
    verified_passes: int = Field(ge=0)
    observed_inference_tokens: int = Field(ge=0)
    observed_tokens_per_verified_success: float | None
    quality_status: RoutingGateStatus
    efficiency_status: RoutingGateStatus
    overall_status: RoutingGateStatus
    choices: tuple[SignatureChoice, ...]


class M2BS2Receipt(Contract):
    schema_version: Literal["m2b-s2-v1"] = "m2b-s2-v1"
    status: Literal["complete"] = "complete"
    reference_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    alternative_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int
    signature_group_count: int
    candidate_assignment_count: int
    max_verified_passes: int
    quality_floor: int = M2A_MIN_VERIFIED_PASSES
    feature_ceiling_feasible: bool
    best_passing_assignment: SignatureAssignment | None
    minimum_tokens_at_quality_floor: SignatureAssignment | None
    signature_groups: tuple[SignatureGroup, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_baseline(
    path: Path,
    *,
    expected_sha256: str,
    expected_model_id: str,
) -> M1BExperimentReceipt:
    if not path.is_file():
        raise M2BS2Error(f"required evidence file not found: {path}")
    if _sha256(path) != expected_sha256:
        raise M2BS2Error(f"evidence hash differs from frozen value: {path}")

    receipt = M1BExperimentReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    if not receipt.baseline_complete or not receipt.usage_complete:
        raise M2BS2Error("feature ceiling requires complete baseline evidence")
    if receipt.frozen_configuration.model_id != expected_model_id:
        raise M2BS2Error("baseline model differs from frozen M2A candidate")
    if tuple(case.case_id for case in receipt.cases) != M1B_CASE_IDS:
        raise M2BS2Error("baseline case order differs from frozen case order")
    if any(not case.usage_complete for case in receipt.cases):
        raise M2BS2Error("feature ceiling requires complete per-case usage")
    return receipt


def _case_evidence(receipt: M1BExperimentReceipt) -> dict[str, CaseEvidence]:
    return {
        case.case_id: CaseEvidence(
            case_id=case.case_id,
            score_passed=case.score_passed,
            inference_tokens=case.observed_input_tokens + case.observed_completion_tokens,
        )
        for case in receipt.cases
    }


def load_structural_cases(
    *,
    repo_root: Path,
    reference: M1BExperimentReceipt,
    alternative: M1BExperimentReceipt,
) -> tuple[StructuralCase, ...]:
    reference_by_case = _case_evidence(reference)
    alternative_by_case = _case_evidence(alternative)
    cases: list[StructuralCase] = []

    for case in load_fixed_baseline_public_cases(repo_root):
        initial = build_initial_model_observation(
            state=case.initial,
            tenant_id=case.tenant_id,
            ticket_id=case.ticket_id,
        )
        cases.append(
            StructuralCase(
                case_id=case.case_id,
                observation=build_routing_observation(initial),
                reference=reference_by_case[case.case_id],
                alternative=alternative_by_case[case.case_id],
            )
        )
    return tuple(cases)


def build_signature_groups(
    cases: tuple[StructuralCase, ...],
) -> tuple[SignatureGroup, ...]:
    grouped: dict[str, list[str]] = {}
    for case in cases:
        signature = case.observation.model_dump_json()
        grouped.setdefault(signature, []).append(case.case_id)

    return tuple(
        SignatureGroup(
            signature_id=f"signature-{index:02d}",
            signature=signature,
            case_ids=tuple(grouped[signature]),
        )
        for index, signature in enumerate(sorted(grouped), start=1)
    )


def _evaluate_assignment(
    *,
    cases: tuple[StructuralCase, ...],
    groups: tuple[SignatureGroup, ...],
    selection: tuple[bool, ...],
) -> SignatureAssignment:
    case_by_id = {case.case_id: case for case in cases}
    choices: list[SignatureChoice] = []
    passes = 0
    tokens = 0

    for use_alternative, group in zip(selection, groups, strict=True):
        profile = M2A_ALTERNATIVE_PROFILE_NAME if use_alternative else M2A_REFERENCE_PROFILE_NAME
        model = M2A_ALTERNATIVE_MODEL_ID if use_alternative else M2A_REFERENCE_MODEL_ID
        choices.append(
            SignatureChoice(
                signature_id=group.signature_id,
                selected_profile_name=profile,
                selected_model_id=model,
                case_ids=group.case_ids,
            )
        )
        for case_id in group.case_ids:
            case = case_by_id[case_id]
            selected = case.alternative if use_alternative else case.reference
            passes += int(selected.score_passed)
            tokens += selected.inference_tokens

    gate = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=passes,
            usage_complete=True,
            observed_inference_tokens=tokens,
        )
    )
    per_success = (
        float(gate.observed_tokens_per_verified_success)
        if gate.observed_tokens_per_verified_success is not None
        else None
    )
    return SignatureAssignment(
        verified_passes=passes,
        observed_inference_tokens=tokens,
        observed_tokens_per_verified_success=per_success,
        quality_status=gate.quality_status,
        efficiency_status=gate.efficiency_status,
        overall_status=gate.overall_status,
        choices=tuple(choices),
    )


def evaluate_feature_ceiling(cases: tuple[StructuralCase, ...]) -> M2BS2Receipt:
    groups = build_signature_groups(cases)
    assignments = tuple(
        _evaluate_assignment(cases=cases, groups=groups, selection=selection)
        for selection in product((False, True), repeat=len(groups))
    )
    passing = tuple(item for item in assignments if item.overall_status is RoutingGateStatus.PASS)
    quality_floor = tuple(
        item for item in assignments if item.verified_passes >= M2A_MIN_VERIFIED_PASSES
    )

    best = min(
        passing,
        key=lambda item: (
            -item.verified_passes,
            item.observed_tokens_per_verified_success
            if item.observed_tokens_per_verified_success is not None
            else float("inf"),
            item.observed_inference_tokens,
        ),
        default=None,
    )
    minimum = min(
        quality_floor,
        key=lambda item: (item.observed_inference_tokens, -item.verified_passes),
        default=None,
    )

    return M2BS2Receipt(
        reference_summary_sha256=REFERENCE_SHA256,
        alternative_summary_sha256=ALTERNATIVE_SHA256,
        case_count=len(cases),
        signature_group_count=len(groups),
        candidate_assignment_count=len(assignments),
        max_verified_passes=max(item.verified_passes for item in assignments),
        feature_ceiling_feasible=best is not None,
        best_passing_assignment=best,
        minimum_tokens_at_quality_floor=minimum,
        signature_groups=groups,
    )


def run_m2b_s2_audit(
    *,
    repo_root: Path,
    reference_summary_path: Path,
    alternative_summary_path: Path,
) -> M2BS2Receipt:
    reference = _load_baseline(
        reference_summary_path,
        expected_sha256=REFERENCE_SHA256,
        expected_model_id=M2A_REFERENCE_MODEL_ID,
    )
    alternative = _load_baseline(
        alternative_summary_path,
        expected_sha256=ALTERNATIVE_SHA256,
        expected_model_id=M2A_ALTERNATIVE_MODEL_ID,
    )
    cases = load_structural_cases(
        repo_root=repo_root,
        reference=reference,
        alternative=alternative,
    )
    return evaluate_feature_ceiling(cases)


def write_m2b_s2_receipt(path: Path, receipt: M2BS2Receipt) -> None:
    if path.exists():
        raise FileExistsError(f"M2B-S2 receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
