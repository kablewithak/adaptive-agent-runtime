from __future__ import annotations

import hashlib
import json
from itertools import product
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_runtime.experiments.harbourdesk_m1b import M1B_CASE_IDS
from adaptive_runtime.routing.contracts import (
    M2A_ALTERNATIVE_MODEL_ID,
    M2A_ALTERNATIVE_PROFILE_NAME,
    M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS,
    M2A_MIN_VERIFIED_PASSES,
    M2A_REFERENCE_MODEL_ID,
    M2A_REFERENCE_PROFILE_NAME,
    M2A_REFERENCE_TOKENS_PER_SUCCESS,
    RoutingGateInput,
    RoutingGateStatus,
    evaluate_routing_gate,
)

M2B_REFERENCE_RUN_ID = "m1b-glm51-baseline-post-unknown-guard-20260915-01"
M2B_REFERENCE_SUMMARY_SHA256 = "f3eb5ed5091bb055679c21ccfe717b832b02a22aad4aa32e1c5446655be0e02d"
M2B_ALTERNATIVE_RUN_ID = "m1c-glm52-baseline-20260915-01"
M2B_ALTERNATIVE_SUMMARY_SHA256 = "c0b4654c866bb75b65661e7198e8206da83bc0d188d880a8699f8d44b8551f3b"


class M2BError(RuntimeError):
    """Raised when canonical fixed-baseline evidence cannot support M2B safely."""


class M2BContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class _FrozenConfigurationEvidence(M2BContract):
    profile_name: str
    model_id: str
    case_order: tuple[str, ...]


class _CaseEvidence(M2BContract):
    case_id: str
    usage_complete: bool
    observed_input_tokens: int = Field(ge=0)
    observed_completion_tokens: int = Field(ge=0)
    score_passed: bool

    @property
    def inference_tokens(self) -> int:
        return self.observed_input_tokens + self.observed_completion_tokens


class _SuiteEvidence(M2BContract):
    baseline_complete: bool
    run_id: str
    frozen_configuration: _FrozenConfigurationEvidence
    case_count: int
    cases: tuple[_CaseEvidence, ...]
    usage_complete: bool
    observed_inference_tokens: int = Field(ge=0)


class OracleCaseChoice(M2BContract):
    case_id: str
    selected_profile_name: str
    selected_model_id: str
    score_passed: bool
    inference_tokens: int = Field(ge=0)


class OracleComplementarity(M2BContract):
    reference_only_passes: int = Field(ge=0)
    alternative_only_passes: int = Field(ge=0)
    both_pass: int = Field(ge=0)
    neither_pass: int = Field(ge=0)


class OracleAssignment(M2BContract):
    verified_passes: int = Field(ge=0)
    observed_inference_tokens: int = Field(ge=0)
    observed_tokens_per_verified_success: float | None
    quality_status: RoutingGateStatus
    efficiency_status: RoutingGateStatus
    overall_status: RoutingGateStatus
    choices: tuple[OracleCaseChoice, ...]


class M2BOracleReceipt(M2BContract):
    schema_version: Literal["m2b-oracle-v1"] = "m2b-oracle-v1"
    status: Literal["complete"] = "complete"
    reference_run_id: str
    reference_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    alternative_run_id: str
    alternative_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_assignment_count: int = Field(ge=1)
    complementarity: OracleComplementarity
    max_verified_passes: int = Field(ge=0)
    quality_floor: int = M2A_MIN_VERIFIED_PASSES
    efficiency_target_tokens_per_success: float
    reference_tokens_per_verified_success: float
    oracle_feasible: bool
    best_passing_assignment: OracleAssignment | None
    minimum_tokens_at_quality_floor: OracleAssignment | None

    @model_validator(mode="after")
    def validate_feasibility(self) -> M2BOracleReceipt:
        if self.oracle_feasible != (self.best_passing_assignment is not None):
            raise ValueError("oracle_feasible must match best_passing_assignment")
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_suite(
    path: Path,
    *,
    expected_sha256: str,
    expected_run_id: str,
    expected_profile_name: str,
    expected_model_id: str,
) -> _SuiteEvidence:
    if not path.is_file():
        raise M2BError(f"baseline summary not found: {path}")

    observed_sha256 = _sha256(path)
    if observed_sha256 != expected_sha256:
        raise M2BError(f"baseline summary hash differs from the frozen canonical evidence: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise M2BError(f"baseline summary is not valid JSON: {path}") from exc

    required = {
        "baseline_complete",
        "run_id",
        "frozen_configuration",
        "case_count",
        "cases",
        "usage_complete",
        "observed_inference_tokens",
    }
    selected = {key: payload[key] for key in required if key in payload}
    if set(selected) != required:
        missing = sorted(required - set(selected))
        raise M2BError(f"baseline summary missing fields: {missing}")

    frozen_raw = selected["frozen_configuration"]
    if not isinstance(frozen_raw, dict):
        raise M2BError("frozen_configuration must be an object")

    cases_raw = selected["cases"]
    if not isinstance(cases_raw, list):
        raise M2BError("cases must be a list")

    frozen = _FrozenConfigurationEvidence.model_validate(
        {
            "profile_name": frozen_raw.get("profile_name"),
            "model_id": frozen_raw.get("model_id"),
            "case_order": frozen_raw.get("case_order"),
        }
    )
    cases = tuple(
        _CaseEvidence.model_validate(
            {
                "case_id": case.get("case_id"),
                "usage_complete": case.get("usage_complete"),
                "observed_input_tokens": case.get("observed_input_tokens"),
                "observed_completion_tokens": case.get("observed_completion_tokens"),
                "score_passed": case.get("score_passed"),
            }
        )
        for case in cases_raw
        if isinstance(case, dict)
    )
    suite = _SuiteEvidence.model_validate(
        {
            "baseline_complete": selected["baseline_complete"],
            "run_id": selected["run_id"],
            "frozen_configuration": frozen,
            "case_count": selected["case_count"],
            "cases": cases,
            "usage_complete": selected["usage_complete"],
            "observed_inference_tokens": selected["observed_inference_tokens"],
        }
    )

    if not suite.baseline_complete:
        raise M2BError("M2B requires a complete fixed-model baseline")
    if not suite.usage_complete:
        raise M2BError("M2B requires complete suite usage")
    if suite.run_id != expected_run_id:
        raise M2BError("baseline run_id differs from the frozen canonical run")
    if suite.frozen_configuration.profile_name != expected_profile_name:
        raise M2BError("baseline profile differs from the frozen candidate")
    if suite.frozen_configuration.model_id != expected_model_id:
        raise M2BError("baseline model differs from the frozen candidate")
    if suite.case_count != len(M1B_CASE_IDS):
        raise M2BError("baseline case_count is not 12")
    if suite.frozen_configuration.case_order != M1B_CASE_IDS:
        raise M2BError("baseline case order differs from hdm-001 through hdm-012")
    if tuple(case.case_id for case in suite.cases) != M1B_CASE_IDS:
        raise M2BError("baseline receipt case order differs from the frozen order")
    if any(not case.usage_complete for case in suite.cases):
        raise M2BError("M2B requires complete per-case usage")

    recomputed = sum(case.inference_tokens for case in suite.cases)
    if recomputed != suite.observed_inference_tokens:
        raise M2BError("suite inference-token total does not match case receipts")

    return suite


def _complementarity(
    reference: _SuiteEvidence,
    alternative: _SuiteEvidence,
) -> OracleComplementarity:
    reference_only = 0
    alternative_only = 0
    both = 0
    neither = 0

    for ref_case, alt_case in zip(reference.cases, alternative.cases, strict=True):
        if ref_case.score_passed and alt_case.score_passed:
            both += 1
        elif ref_case.score_passed:
            reference_only += 1
        elif alt_case.score_passed:
            alternative_only += 1
        else:
            neither += 1

    return OracleComplementarity(
        reference_only_passes=reference_only,
        alternative_only_passes=alternative_only,
        both_pass=both,
        neither_pass=neither,
    )


def _assignment(
    reference: _SuiteEvidence,
    alternative: _SuiteEvidence,
    selection: tuple[bool, ...],
) -> OracleAssignment:
    choices: list[OracleCaseChoice] = []

    for use_alternative, ref_case, alt_case in zip(
        selection,
        reference.cases,
        alternative.cases,
        strict=True,
    ):
        if use_alternative:
            selected_case = alt_case
            profile_name = M2A_ALTERNATIVE_PROFILE_NAME
            model_id = M2A_ALTERNATIVE_MODEL_ID
        else:
            selected_case = ref_case
            profile_name = M2A_REFERENCE_PROFILE_NAME
            model_id = M2A_REFERENCE_MODEL_ID

        choices.append(
            OracleCaseChoice(
                case_id=selected_case.case_id,
                selected_profile_name=profile_name,
                selected_model_id=model_id,
                score_passed=selected_case.score_passed,
                inference_tokens=selected_case.inference_tokens,
            )
        )

    verified_passes = sum(choice.score_passed for choice in choices)
    tokens = sum(choice.inference_tokens for choice in choices)
    gate = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=verified_passes,
            usage_complete=True,
            observed_inference_tokens=tokens,
        )
    )

    tokens_per_success = (
        float(gate.observed_tokens_per_verified_success)
        if gate.observed_tokens_per_verified_success is not None
        else None
    )

    return OracleAssignment(
        verified_passes=verified_passes,
        observed_inference_tokens=tokens,
        observed_tokens_per_verified_success=tokens_per_success,
        quality_status=gate.quality_status,
        efficiency_status=gate.efficiency_status,
        overall_status=gate.overall_status,
        choices=tuple(choices),
    )


def run_m2b_oracle(
    *,
    reference_summary_path: Path,
    alternative_summary_path: Path,
) -> M2BOracleReceipt:
    reference = _load_suite(
        reference_summary_path,
        expected_sha256=M2B_REFERENCE_SUMMARY_SHA256,
        expected_run_id=M2B_REFERENCE_RUN_ID,
        expected_profile_name=M2A_REFERENCE_PROFILE_NAME,
        expected_model_id=M2A_REFERENCE_MODEL_ID,
    )
    alternative = _load_suite(
        alternative_summary_path,
        expected_sha256=M2B_ALTERNATIVE_SUMMARY_SHA256,
        expected_run_id=M2B_ALTERNATIVE_RUN_ID,
        expected_profile_name=M2A_ALTERNATIVE_PROFILE_NAME,
        expected_model_id=M2A_ALTERNATIVE_MODEL_ID,
    )

    assignments = tuple(
        _assignment(reference, alternative, selection)
        for selection in product((False, True), repeat=len(M1B_CASE_IDS))
    )

    passing = tuple(
        assignment
        for assignment in assignments
        if assignment.overall_status is RoutingGateStatus.PASS
    )
    quality_floor = tuple(
        assignment
        for assignment in assignments
        if assignment.verified_passes >= M2A_MIN_VERIFIED_PASSES
    )

    best_passing = min(
        passing,
        key=lambda assignment: (
            -assignment.verified_passes,
            assignment.observed_tokens_per_verified_success
            if assignment.observed_tokens_per_verified_success is not None
            else float("inf"),
            assignment.observed_inference_tokens,
        ),
        default=None,
    )
    minimum_tokens_at_quality_floor = min(
        quality_floor,
        key=lambda assignment: (
            assignment.observed_inference_tokens,
            -assignment.verified_passes,
        ),
        default=None,
    )

    return M2BOracleReceipt(
        reference_run_id=reference.run_id,
        reference_summary_sha256=M2B_REFERENCE_SUMMARY_SHA256,
        alternative_run_id=alternative.run_id,
        alternative_summary_sha256=M2B_ALTERNATIVE_SUMMARY_SHA256,
        candidate_assignment_count=len(assignments),
        complementarity=_complementarity(reference, alternative),
        max_verified_passes=max(assignment.verified_passes for assignment in assignments),
        efficiency_target_tokens_per_success=float(M2A_EFFICIENCY_TARGET_TOKENS_PER_SUCCESS),
        reference_tokens_per_verified_success=float(M2A_REFERENCE_TOKENS_PER_SUCCESS),
        oracle_feasible=best_passing is not None,
        best_passing_assignment=best_passing,
        minimum_tokens_at_quality_floor=minimum_tokens_at_quality_floor,
    )


def write_m2b_receipt(path: Path, receipt: M2BOracleReceipt) -> None:
    if path.exists():
        raise FileExistsError(f"M2B receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
