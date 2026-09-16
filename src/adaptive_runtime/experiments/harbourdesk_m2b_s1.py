from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.domain import ApprovalAction, TicketStatus
from adaptive_runtime.environment.model_observation import (
    build_initial_model_observation,
)
from adaptive_runtime.experiments.harbourdesk_m1b import (
    M1B_CASE_IDS,
    M1BExperimentReceipt,
    load_fixed_baseline_public_cases,
)
from adaptive_runtime.routing.contracts import (
    M2A_ALTERNATIVE_MODEL_ID,
    M2A_REFERENCE_MODEL_ID,
    RoutingGateInput,
    RoutingGateStatus,
    RoutingObservation,
    build_routing_observation,
    evaluate_routing_gate,
)

M2B_S1_M2B_SUMMARY_SHA256 = (
    "155dea27b087bb55a3445fb7162e375fc44c84a3671344ac154c2af094db0db8"
)
M2B_S1_REFERENCE_SUMMARY_SHA256 = (
    "f3eb5ed5091bb055679c21ccfe717b832b02a22aad4aa32e1c5446655be0e02d"
)
M2B_S1_ALTERNATIVE_SUMMARY_SHA256 = (
    "c0b4654c866bb75b65661e7198e8206da83bc0d188d880a8699f8d44b8551f3b"
)


class M2BS1Error(RuntimeError):
    """Raised when frozen evidence cannot support the structural audit safely."""


class M2BS1Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class OracleChoice(M2BS1Contract):
    case_id: str
    selected_model_id: str


class _M2BOracleAssignment(M2BS1Contract):
    choices: tuple[OracleChoice, ...]


class _M2BReceipt(M2BS1Contract):
    oracle_feasible: bool
    best_passing_assignment: _M2BOracleAssignment | None


class CaseModelEvidence(M2BS1Contract):
    case_id: str
    score_passed: bool
    inference_tokens: int = Field(ge=0)


class StructuralCase(M2BS1Contract):
    case_id: str
    observation: RoutingObservation
    oracle_model_id: str
    reference: CaseModelEvidence
    alternative: CaseModelEvidence


class SignatureGroup(M2BS1Contract):
    signature: str
    case_ids: tuple[str, ...]
    oracle_model_ids: tuple[str, ...]
    mixed_oracle_choice: bool


class PredicateKind(StrEnum):
    TICKET_STATUS_IS = "TICKET_STATUS_IS"
    HAS_NOTES = "HAS_NOTES"
    NO_NOTES = "NO_NOTES"
    HAS_APPROVALS = "HAS_APPROVALS"
    NO_APPROVALS = "NO_APPROVALS"
    HAS_ACTIVE_APPROVAL_ACTION = "HAS_ACTIVE_APPROVAL_ACTION"
    LACKS_ACTIVE_APPROVAL_ACTION = "LACKS_ACTIVE_APPROVAL_ACTION"
    HAS_INACTIVE_APPROVAL_ACTION = "HAS_INACTIVE_APPROVAL_ACTION"
    LACKS_INACTIVE_APPROVAL_ACTION = "LACKS_INACTIVE_APPROVAL_ACTION"
    HAS_OPERATION_REFERENCES = "HAS_OPERATION_REFERENCES"
    NO_OPERATION_REFERENCES = "NO_OPERATION_REFERENCES"
    HAS_OPERATION_ACTION = "HAS_OPERATION_ACTION"
    LACKS_OPERATION_ACTION = "LACKS_OPERATION_ACTION"


class StructuralPredicate(M2BS1Contract):
    kind: PredicateKind
    value: str | None = None

    @property
    def rule_id(self) -> str:
        if self.value is None:
            return self.kind.value
        return f"{self.kind.value}:{self.value}"

    def matches(self, observation: RoutingObservation) -> bool:
        if self.kind is PredicateKind.TICKET_STATUS_IS:
            return observation.ticket_status.value == self.value
        if self.kind is PredicateKind.HAS_NOTES:
            return observation.note_count > 0
        if self.kind is PredicateKind.NO_NOTES:
            return observation.note_count == 0
        if self.kind is PredicateKind.HAS_APPROVALS:
            return observation.approval_count > 0
        if self.kind is PredicateKind.NO_APPROVALS:
            return observation.approval_count == 0
        if self.kind is PredicateKind.HAS_ACTIVE_APPROVAL_ACTION:
            return any(
                action.value == self.value
                for action in observation.active_approval_actions
            )
        if self.kind is PredicateKind.LACKS_ACTIVE_APPROVAL_ACTION:
            return all(
                action.value != self.value
                for action in observation.active_approval_actions
            )
        if self.kind is PredicateKind.HAS_INACTIVE_APPROVAL_ACTION:
            return any(
                action.value == self.value
                for action in observation.inactive_approval_actions
            )
        if self.kind is PredicateKind.LACKS_INACTIVE_APPROVAL_ACTION:
            return all(
                action.value != self.value
                for action in observation.inactive_approval_actions
            )
        if self.kind is PredicateKind.HAS_OPERATION_REFERENCES:
            return observation.operation_reference_count > 0
        if self.kind is PredicateKind.NO_OPERATION_REFERENCES:
            return observation.operation_reference_count == 0
        if self.kind is PredicateKind.HAS_OPERATION_ACTION:
            return any(
                action.value == self.value
                for action in observation.operation_reference_actions
            )
        if self.kind is PredicateKind.LACKS_OPERATION_ACTION:
            return all(
                action.value != self.value
                for action in observation.operation_reference_actions
            )
        raise AssertionError(f"unhandled predicate kind: {self.kind}")


class PredicateEvaluation(M2BS1Contract):
    rule_id: str
    alternative_case_ids: tuple[str, ...]
    reference_case_ids: tuple[str, ...]
    verified_passes: int = Field(ge=0)
    inference_tokens: int = Field(ge=0)
    tokens_per_verified_success: float | None
    quality_status: RoutingGateStatus
    efficiency_status: RoutingGateStatus
    overall_status: RoutingGateStatus


class StructuralAuditDecision(StrEnum):
    PROCEED_SINGLE_PREDICATE = "PROCEED_SINGLE_PREDICATE"
    NO_SINGLE_PREDICATE_PASS = "NO_SINGLE_PREDICATE_PASS"


class M2BS1Receipt(M2BS1Contract):
    schema_version: Literal["m2b-s1-v1"] = "m2b-s1-v1"
    status: Literal["complete"] = "complete"
    m2b_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    alternative_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int
    signature_group_count: int
    mixed_signature_group_count: int
    exact_signature_separable: bool
    predicate_count: int
    passing_predicate_count: int
    decision: StructuralAuditDecision
    signature_groups: tuple[SignatureGroup, ...]
    best_passing_predicate: PredicateEvaluation | None
    all_passing_predicates: tuple[PredicateEvaluation, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise M2BS1Error(f"required evidence file not found: {path}")
    if _sha256(path) != expected:
        raise M2BS1Error(f"evidence hash differs from frozen value: {path}")


def _load_baseline(
    path: Path,
    *,
    expected_sha256: str,
    expected_model_id: str,
) -> M1BExperimentReceipt:
    _require_hash(path, expected_sha256)
    receipt = M1BExperimentReceipt.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if not receipt.baseline_complete:
        raise M2BS1Error("structural audit requires complete baseline evidence")
    if not receipt.usage_complete:
        raise M2BS1Error("structural audit requires complete suite usage")
    if receipt.frozen_configuration.model_id != expected_model_id:
        raise M2BS1Error("baseline model differs from frozen M2A candidate")
    if tuple(case.case_id for case in receipt.cases) != M1B_CASE_IDS:
        raise M2BS1Error("baseline case order differs from frozen case order")
    if any(not case.usage_complete for case in receipt.cases):
        raise M2BS1Error("structural audit requires complete per-case usage")
    return receipt


def _load_oracle_choices(path: Path) -> dict[str, str]:
    _require_hash(path, M2B_S1_M2B_SUMMARY_SHA256)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise M2BS1Error("M2B summary is not valid JSON") from exc

    assignment = payload.get("best_passing_assignment")
    if assignment is not None and not isinstance(assignment, dict):
        raise M2BS1Error("M2B best_passing_assignment must be an object or null")

    projected_assignment: dict[str, object] | None = None
    if isinstance(assignment, dict):
        raw_choices = assignment.get("choices")
        if not isinstance(raw_choices, list):
            raise M2BS1Error("M2B oracle assignment choices must be a list")

        projected_choices: list[dict[str, object]] = []
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, dict):
                raise M2BS1Error("M2B oracle choice must be an object")
            projected_choices.append(
                {
                    "case_id": raw_choice.get("case_id"),
                    "selected_model_id": raw_choice.get("selected_model_id"),
                }
            )

        projected_assignment = {"choices": projected_choices}

    receipt = _M2BReceipt.model_validate(
        {
            "oracle_feasible": payload.get("oracle_feasible"),
            "best_passing_assignment": projected_assignment,
        }
    )
    if not receipt.oracle_feasible or receipt.best_passing_assignment is None:
        raise M2BS1Error("M2B-S1 requires a feasible frozen M2B oracle result")

    choices = {
        choice.case_id: choice.selected_model_id
        for choice in receipt.best_passing_assignment.choices
    }
    if tuple(sorted(choices)) != tuple(sorted(M1B_CASE_IDS)):
        raise M2BS1Error("oracle choices do not cover the frozen 12 cases")

    allowed_models = {
        M2A_REFERENCE_MODEL_ID,
        M2A_ALTERNATIVE_MODEL_ID,
    }
    if any(model_id not in allowed_models for model_id in choices.values()):
        raise M2BS1Error("oracle choice contains a model outside the M2A candidate set")

    return choices


def _case_evidence(
    receipt: M1BExperimentReceipt,
) -> dict[str, CaseModelEvidence]:
    return {
        case.case_id: CaseModelEvidence(
            case_id=case.case_id,
            score_passed=case.score_passed,
            inference_tokens=(
                case.observed_input_tokens + case.observed_completion_tokens
            ),
        )
        for case in receipt.cases
    }


def _routing_cases(
    *,
    repo_root: Path,
    oracle_choices: dict[str, str],
    reference: M1BExperimentReceipt,
    alternative: M1BExperimentReceipt,
) -> tuple[StructuralCase, ...]:
    public_cases = load_fixed_baseline_public_cases(repo_root)
    reference_by_case = _case_evidence(reference)
    alternative_by_case = _case_evidence(alternative)

    cases: list[StructuralCase] = []
    for case in public_cases:
        model_observation = build_initial_model_observation(
            state=case.initial,
            tenant_id=case.tenant_id,
            ticket_id=case.ticket_id,
        )
        routing_observation = build_routing_observation(model_observation)
        cases.append(
            StructuralCase(
                case_id=case.case_id,
                observation=routing_observation,
                oracle_model_id=oracle_choices[case.case_id],
                reference=reference_by_case[case.case_id],
                alternative=alternative_by_case[case.case_id],
            )
        )
    return tuple(cases)


def _signature(observation: RoutingObservation) -> str:
    return observation.model_dump_json()


def _signature_groups(
    cases: tuple[StructuralCase, ...],
) -> tuple[SignatureGroup, ...]:
    grouped: dict[str, list[StructuralCase]] = defaultdict(list)
    for case in cases:
        grouped[_signature(case.observation)].append(case)

    result: list[SignatureGroup] = []
    for signature, members in sorted(grouped.items()):
        models = tuple(sorted({case.oracle_model_id for case in members}))
        result.append(
            SignatureGroup(
                signature=signature,
                case_ids=tuple(case.case_id for case in members),
                oracle_model_ids=models,
                mixed_oracle_choice=len(models) > 1,
            )
        )
    return tuple(result)


def _predicates() -> tuple[StructuralPredicate, ...]:
    predicates: list[StructuralPredicate] = [
        StructuralPredicate(kind=PredicateKind.HAS_NOTES),
        StructuralPredicate(kind=PredicateKind.NO_NOTES),
        StructuralPredicate(kind=PredicateKind.HAS_APPROVALS),
        StructuralPredicate(kind=PredicateKind.NO_APPROVALS),
        StructuralPredicate(kind=PredicateKind.HAS_OPERATION_REFERENCES),
        StructuralPredicate(kind=PredicateKind.NO_OPERATION_REFERENCES),
    ]

    for status in TicketStatus:
        predicates.append(
            StructuralPredicate(
                kind=PredicateKind.TICKET_STATUS_IS,
                value=status.value,
            )
        )

    for action in ApprovalAction:
        predicates.extend(
            (
                StructuralPredicate(
                    kind=PredicateKind.HAS_ACTIVE_APPROVAL_ACTION,
                    value=action.value,
                ),
                StructuralPredicate(
                    kind=PredicateKind.LACKS_ACTIVE_APPROVAL_ACTION,
                    value=action.value,
                ),
                StructuralPredicate(
                    kind=PredicateKind.HAS_INACTIVE_APPROVAL_ACTION,
                    value=action.value,
                ),
                StructuralPredicate(
                    kind=PredicateKind.LACKS_INACTIVE_APPROVAL_ACTION,
                    value=action.value,
                ),
                StructuralPredicate(
                    kind=PredicateKind.HAS_OPERATION_ACTION,
                    value=action.value,
                ),
                StructuralPredicate(
                    kind=PredicateKind.LACKS_OPERATION_ACTION,
                    value=action.value,
                ),
            )
        )

    unique = {predicate.rule_id: predicate for predicate in predicates}
    return tuple(unique[key] for key in sorted(unique))


def _evaluate_predicate(
    predicate: StructuralPredicate,
    cases: tuple[StructuralCase, ...],
) -> PredicateEvaluation:
    alternative_case_ids: list[str] = []
    reference_case_ids: list[str] = []
    passes = 0
    tokens = 0

    for case in cases:
        if predicate.matches(case.observation):
            selected = case.alternative
            alternative_case_ids.append(case.case_id)
        else:
            selected = case.reference
            reference_case_ids.append(case.case_id)

        passes += int(selected.score_passed)
        tokens += selected.inference_tokens

    gate = evaluate_routing_gate(
        RoutingGateInput(
            verified_passes=passes,
            usage_complete=True,
            observed_inference_tokens=tokens,
        )
    )
    tokens_per_success = (
        float(gate.observed_tokens_per_verified_success)
        if gate.observed_tokens_per_verified_success is not None
        else None
    )

    return PredicateEvaluation(
        rule_id=predicate.rule_id,
        alternative_case_ids=tuple(alternative_case_ids),
        reference_case_ids=tuple(reference_case_ids),
        verified_passes=passes,
        inference_tokens=tokens,
        tokens_per_verified_success=tokens_per_success,
        quality_status=gate.quality_status,
        efficiency_status=gate.efficiency_status,
        overall_status=gate.overall_status,
    )


def run_m2b_s1_audit(
    *,
    repo_root: Path,
    m2b_summary_path: Path,
    reference_summary_path: Path,
    alternative_summary_path: Path,
) -> M2BS1Receipt:
    oracle_choices = _load_oracle_choices(m2b_summary_path)
    reference = _load_baseline(
        reference_summary_path,
        expected_sha256=M2B_S1_REFERENCE_SUMMARY_SHA256,
        expected_model_id=M2A_REFERENCE_MODEL_ID,
    )
    alternative = _load_baseline(
        alternative_summary_path,
        expected_sha256=M2B_S1_ALTERNATIVE_SUMMARY_SHA256,
        expected_model_id=M2A_ALTERNATIVE_MODEL_ID,
    )
    cases = _routing_cases(
        repo_root=repo_root,
        oracle_choices=oracle_choices,
        reference=reference,
        alternative=alternative,
    )

    groups = _signature_groups(cases)
    evaluations = tuple(
        _evaluate_predicate(predicate, cases)
        for predicate in _predicates()
    )
    passing = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.overall_status is RoutingGateStatus.PASS
    )
    best = min(
        passing,
        key=lambda evaluation: (
            evaluation.tokens_per_verified_success
            if evaluation.tokens_per_verified_success is not None
            else float("inf"),
            len(evaluation.alternative_case_ids),
            evaluation.rule_id,
        ),
        default=None,
    )

    return M2BS1Receipt(
        m2b_summary_sha256=M2B_S1_M2B_SUMMARY_SHA256,
        reference_summary_sha256=M2B_S1_REFERENCE_SUMMARY_SHA256,
        alternative_summary_sha256=M2B_S1_ALTERNATIVE_SUMMARY_SHA256,
        case_count=len(cases),
        signature_group_count=len(groups),
        mixed_signature_group_count=sum(
            group.mixed_oracle_choice for group in groups
        ),
        exact_signature_separable=all(
            not group.mixed_oracle_choice for group in groups
        ),
        predicate_count=len(evaluations),
        passing_predicate_count=len(passing),
        decision=(
            StructuralAuditDecision.PROCEED_SINGLE_PREDICATE
            if best is not None
            else StructuralAuditDecision.NO_SINGLE_PREDICATE_PASS
        ),
        signature_groups=groups,
        best_passing_predicate=best,
        all_passing_predicates=passing,
    )


def write_m2b_s1_receipt(path: Path, receipt: M2BS1Receipt) -> None:
    if path.exists():
        raise FileExistsError(f"M2B-S1 receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
