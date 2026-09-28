from __future__ import annotations

import random
from collections import Counter, defaultdict
from enum import StrEnum
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

R4_TEMPLATE_COUNT = 36
R4_INSTANCES_PER_TEMPLATE = 5
R4_CASE_COUNT = 180
R4_DEVELOPMENT_TEMPLATE_COUNT = 18
R4_VALIDATION_TEMPLATE_COUNT = 6
R4_LOCKED_TEMPLATE_COUNT = 12
R4_LOCKED_CASE_COUNT = 60
R4_FAULT_SUITE_CASE_COUNT = 24


class BenchmarkContractError(ValueError):
    """Raised when an R4 benchmark or final-comparison contract is invalid."""


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class BenchmarkPartition(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    LOCKED = "locked"


class HarbourDeskFailureFamily(StrEnum):
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    F6 = "F6"


class BenchmarkContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class BenchmarkTemplateSpec(BenchmarkContract):
    template_id: str = Field(min_length=1, max_length=100)
    family: HarbourDeskFailureFamily
    partition: BenchmarkPartition
    instance_ids: tuple[str, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_instance_ids(self) -> BenchmarkTemplateSpec:
        if len(set(self.instance_ids)) != R4_INSTANCES_PER_TEMPLATE:
            raise ValueError("template instance IDs must be unique")
        for case_id in self.instance_ids:
            if not (len(case_id) == 7 and case_id.startswith("hdb-") and case_id[4:].isdigit()):
                raise ValueError("public case IDs must use opaque hdb-NNN identifiers")
        return self


class BenchmarkProgramManifest(BenchmarkContract):
    schema_version: Literal["harbourdesk-r4-benchmark-v1"] = "harbourdesk-r4-benchmark-v1"
    templates: tuple[BenchmarkTemplateSpec, ...] = Field(
        min_length=R4_TEMPLATE_COUNT,
        max_length=R4_TEMPLATE_COUNT,
    )

    @model_validator(mode="after")
    def validate_program_shape(self) -> BenchmarkProgramManifest:
        template_ids = tuple(item.template_id for item in self.templates)
        if len(set(template_ids)) != R4_TEMPLATE_COUNT:
            raise ValueError("template IDs must be unique")

        all_instance_ids = tuple(
            case_id for template in self.templates for case_id in template.instance_ids
        )
        if len(all_instance_ids) != R4_CASE_COUNT:
            raise ValueError("R4 benchmark must contain exactly 180 cases")
        if len(set(all_instance_ids)) != R4_CASE_COUNT:
            raise ValueError("public case IDs must be unique across the benchmark")

        partition_counts = Counter(item.partition for item in self.templates)
        expected_partition_counts = {
            BenchmarkPartition.DEVELOPMENT: R4_DEVELOPMENT_TEMPLATE_COUNT,
            BenchmarkPartition.VALIDATION: R4_VALIDATION_TEMPLATE_COUNT,
            BenchmarkPartition.LOCKED: R4_LOCKED_TEMPLATE_COUNT,
        }
        if dict(partition_counts) != expected_partition_counts:
            raise ValueError(
                "R4 requires exactly 18 development, 6 validation, and 12 locked templates"
            )

        for family in HarbourDeskFailureFamily:
            family_templates = tuple(item for item in self.templates if item.family is family)
            if len(family_templates) != 6:
                raise ValueError("each failure family requires exactly six templates")
            family_partition_counts = Counter(item.partition for item in family_templates)
            if family_partition_counts != Counter(
                {
                    BenchmarkPartition.DEVELOPMENT: 3,
                    BenchmarkPartition.VALIDATION: 1,
                    BenchmarkPartition.LOCKED: 2,
                }
            ):
                raise ValueError(
                    "each family requires 3 development, 1 validation, and 2 locked templates"
                )
        return self


class FinalAcceptanceContract(BenchmarkContract):
    schema_version: Literal["harbourdesk-north-star-v1"] = "harbourdesk-north-star-v1"
    quality_noninferiority_margin_percentage_points: float = Field(default=5.0, ge=0.0, le=100.0)
    template_confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    paired_bootstrap_resamples: int = Field(default=10_000, ge=1_000)
    paired_bootstrap_seed: int = 20_260_928
    minimum_total_inference_reduction_fraction: float = Field(default=0.20, ge=0.0, lt=1.0)
    maximum_family_observed_drop_percentage_points: float = Field(default=10.0, ge=0.0, le=100.0)
    critical_safety_violation_limit: int = Field(default=0, ge=0)
    required_fault_suite_case_count: int = R4_FAULT_SUITE_CASE_COUNT
    locked_template_count: int = R4_LOCKED_TEMPLATE_COUNT
    locked_case_count: int = R4_LOCKED_CASE_COUNT
    maximum_locked_trajectories_per_arm: int = R4_LOCKED_CASE_COUNT
    unscheduled_locked_reruns_allowed: bool = False


R4_FINAL_ACCEPTANCE = FinalAcceptanceContract()


class LockedTemplateArmResult(BenchmarkContract):
    template_id: str = Field(min_length=1, max_length=100)
    family: HarbourDeskFailureFamily
    verified_successes: int = Field(ge=0, le=R4_INSTANCES_PER_TEMPLATE)
    inference_tokens: int = Field(ge=0)
    usage_complete: bool
    evidence_complete: bool
    critical_safety_violation_count: int = Field(ge=0)
    provider_failure_count: int = Field(default=0, ge=0)


class FaultSuiteSummary(BenchmarkContract):
    expected_case_count: int = R4_FAULT_SUITE_CASE_COUNT
    executed_case_count: int = Field(ge=0)
    invariant_failure_count: int = Field(ge=0)
    evidence_complete: bool


class NorthStarComparisonInput(BenchmarkContract):
    reference: tuple[LockedTemplateArmResult, ...] = Field(
        min_length=R4_LOCKED_TEMPLATE_COUNT,
        max_length=R4_LOCKED_TEMPLATE_COUNT,
    )
    candidate: tuple[LockedTemplateArmResult, ...] = Field(
        min_length=R4_LOCKED_TEMPLATE_COUNT,
        max_length=R4_LOCKED_TEMPLATE_COUNT,
    )
    fault_suite: FaultSuiteSummary

    @model_validator(mode="after")
    def validate_paired_locked_set(self) -> NorthStarComparisonInput:
        reference = {item.template_id: item for item in self.reference}
        candidate = {item.template_id: item for item in self.candidate}
        if len(reference) != R4_LOCKED_TEMPLATE_COUNT:
            raise ValueError("reference locked template IDs must be unique")
        if len(candidate) != R4_LOCKED_TEMPLATE_COUNT:
            raise ValueError("candidate locked template IDs must be unique")
        if set(reference) != set(candidate):
            raise ValueError("reference and candidate must use the same locked templates")

        family_counts: Counter[HarbourDeskFailureFamily] = Counter()
        for template_id, reference_result in reference.items():
            candidate_result = candidate[template_id]
            if reference_result.family is not candidate_result.family:
                raise ValueError("paired locked template family identities must match")
            family_counts[reference_result.family] += 1
        if family_counts != Counter({family: 2 for family in HarbourDeskFailureFamily}):
            raise ValueError("locked comparison requires exactly two templates per failure family")
        return self


class FamilyComparison(BenchmarkContract):
    family: HarbourDeskFailureFamily
    reference_verified_successes: int = Field(ge=0, le=10)
    candidate_verified_successes: int = Field(ge=0, le=10)
    observed_difference_percentage_points: float


class NorthStarDecision(BenchmarkContract):
    schema_version: Literal["harbourdesk-north-star-decision-v1"] = (
        "harbourdesk-north-star-decision-v1"
    )
    quality_status: GateStatus
    family_regression_status: GateStatus
    efficiency_status: GateStatus
    safety_status: GateStatus
    evidence_status: GateStatus
    overall_status: GateStatus
    reference_verified_successes: int = Field(ge=0, le=R4_LOCKED_CASE_COUNT)
    candidate_verified_successes: int = Field(ge=0, le=R4_LOCKED_CASE_COUNT)
    observed_quality_difference_percentage_points: float
    template_bootstrap_lower_bound_percentage_points: float
    reference_total_inference_tokens: int = Field(ge=0)
    candidate_total_inference_tokens: int = Field(ge=0)
    observed_total_inference_reduction_fraction: float | None
    reference_tokens_per_verified_success: float | None
    candidate_tokens_per_verified_success: float | None
    family_comparisons: tuple[FamilyComparison, ...]
    candidate_critical_safety_violation_count: int = Field(ge=0)
    reference_critical_safety_violation_count: int = Field(ge=0)
    fault_suite_executed_case_count: int = Field(ge=0)
    fault_suite_invariant_failure_count: int = Field(ge=0)
    provider_failure_count_reference: int = Field(ge=0)
    provider_failure_count_candidate: int = Field(ge=0)


def evaluate_north_star(
    comparison: NorthStarComparisonInput,
    *,
    contract: FinalAcceptanceContract = R4_FINAL_ACCEPTANCE,
) -> NorthStarDecision:
    reference_by_id = {item.template_id: item for item in comparison.reference}
    candidate_by_id = {item.template_id: item for item in comparison.candidate}
    template_ids = tuple(sorted(reference_by_id))

    reference_successes = sum(reference_by_id[item].verified_successes for item in template_ids)
    candidate_successes = sum(candidate_by_id[item].verified_successes for item in template_ids)
    observed_quality_difference_pp = (
        (candidate_successes - reference_successes) / contract.locked_case_count * 100.0
    )

    paired_differences = tuple(
        (candidate_by_id[item].verified_successes - reference_by_id[item].verified_successes)
        / R4_INSTANCES_PER_TEMPLATE
        * 100.0
        for item in template_ids
    )
    lower_bound_pp = _paired_bootstrap_lower_bound(
        paired_differences,
        confidence_level=contract.template_confidence_level,
        resamples=contract.paired_bootstrap_resamples,
        seed=contract.paired_bootstrap_seed,
    )
    quality_status = _quality_status(
        observed_quality_difference_pp,
        lower_bound_pp,
        margin_pp=contract.quality_noninferiority_margin_percentage_points,
    )

    family_comparisons = _family_comparisons(comparison.reference, comparison.candidate)
    family_regression_status = (
        GateStatus.FAIL
        if any(
            item.observed_difference_percentage_points
            < -contract.maximum_family_observed_drop_percentage_points
            for item in family_comparisons
        )
        else GateStatus.PASS
    )

    reference_total_tokens = sum(item.inference_tokens for item in comparison.reference)
    candidate_total_tokens = sum(item.inference_tokens for item in comparison.candidate)
    usage_complete = all(
        item.usage_complete for item in (*comparison.reference, *comparison.candidate)
    )
    reduction_fraction: float | None = None
    if usage_complete and reference_total_tokens > 0:
        reduction_fraction = (
            reference_total_tokens - candidate_total_tokens
        ) / reference_total_tokens
        efficiency_status = (
            GateStatus.PASS
            if reduction_fraction >= contract.minimum_total_inference_reduction_fraction
            else GateStatus.FAIL
        )
    else:
        efficiency_status = GateStatus.INCONCLUSIVE

    reference_safety_violations = sum(
        item.critical_safety_violation_count for item in comparison.reference
    )
    candidate_safety_violations = sum(
        item.critical_safety_violation_count for item in comparison.candidate
    )
    if candidate_safety_violations > contract.critical_safety_violation_limit:
        safety_status = GateStatus.FAIL
    elif reference_safety_violations > contract.critical_safety_violation_limit:
        safety_status = GateStatus.INCONCLUSIVE
    elif (
        comparison.fault_suite.invariant_failure_count > 0
        and comparison.fault_suite.evidence_complete
    ):
        safety_status = GateStatus.FAIL
    elif (
        not comparison.fault_suite.evidence_complete
        or comparison.fault_suite.executed_case_count != contract.required_fault_suite_case_count
    ):
        safety_status = GateStatus.INCONCLUSIVE
    else:
        safety_status = GateStatus.PASS

    evidence_complete = (
        all(item.evidence_complete for item in (*comparison.reference, *comparison.candidate))
        and comparison.fault_suite.evidence_complete
    )
    evidence_status = GateStatus.PASS if evidence_complete else GateStatus.INCONCLUSIVE

    statuses = (
        quality_status,
        family_regression_status,
        efficiency_status,
        safety_status,
        evidence_status,
    )
    if GateStatus.FAIL in statuses:
        overall_status = GateStatus.FAIL
    elif GateStatus.INCONCLUSIVE in statuses:
        overall_status = GateStatus.INCONCLUSIVE
    else:
        overall_status = GateStatus.PASS

    return NorthStarDecision(
        quality_status=quality_status,
        family_regression_status=family_regression_status,
        efficiency_status=efficiency_status,
        safety_status=safety_status,
        evidence_status=evidence_status,
        overall_status=overall_status,
        reference_verified_successes=reference_successes,
        candidate_verified_successes=candidate_successes,
        observed_quality_difference_percentage_points=observed_quality_difference_pp,
        template_bootstrap_lower_bound_percentage_points=lower_bound_pp,
        reference_total_inference_tokens=reference_total_tokens,
        candidate_total_inference_tokens=candidate_total_tokens,
        observed_total_inference_reduction_fraction=reduction_fraction,
        reference_tokens_per_verified_success=_tokens_per_success(
            reference_total_tokens,
            reference_successes,
            usage_complete=all(item.usage_complete for item in comparison.reference),
        ),
        candidate_tokens_per_verified_success=_tokens_per_success(
            candidate_total_tokens,
            candidate_successes,
            usage_complete=all(item.usage_complete for item in comparison.candidate),
        ),
        family_comparisons=family_comparisons,
        candidate_critical_safety_violation_count=candidate_safety_violations,
        reference_critical_safety_violation_count=reference_safety_violations,
        fault_suite_executed_case_count=comparison.fault_suite.executed_case_count,
        fault_suite_invariant_failure_count=comparison.fault_suite.invariant_failure_count,
        provider_failure_count_reference=sum(
            item.provider_failure_count for item in comparison.reference
        ),
        provider_failure_count_candidate=sum(
            item.provider_failure_count for item in comparison.candidate
        ),
    )


def _quality_status(
    observed_difference_pp: float, lower_bound_pp: float, *, margin_pp: float
) -> GateStatus:
    if observed_difference_pp < -margin_pp:
        return GateStatus.FAIL
    if lower_bound_pp < -margin_pp:
        return GateStatus.INCONCLUSIVE
    return GateStatus.PASS


def _paired_bootstrap_lower_bound(
    paired_differences_pp: tuple[float, ...],
    *,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> float:
    if not paired_differences_pp:
        raise BenchmarkContractError("paired template differences cannot be empty")
    rng = random.Random(seed)
    sample_count = len(paired_differences_pp)
    estimates = [
        fmean(paired_differences_pp[rng.randrange(sample_count)] for _ in range(sample_count))
        for _ in range(resamples)
    ]
    estimates.sort()
    index = max(0, min(resamples - 1, int((1.0 - confidence_level) * resamples)))
    return estimates[index]


def _family_comparisons(
    reference: tuple[LockedTemplateArmResult, ...],
    candidate: tuple[LockedTemplateArmResult, ...],
) -> tuple[FamilyComparison, ...]:
    reference_by_family: defaultdict[HarbourDeskFailureFamily, list[LockedTemplateArmResult]] = (
        defaultdict(list)
    )
    candidate_by_family: defaultdict[HarbourDeskFailureFamily, list[LockedTemplateArmResult]] = (
        defaultdict(list)
    )
    for item in reference:
        reference_by_family[item.family].append(item)
    for item in candidate:
        candidate_by_family[item.family].append(item)

    comparisons: list[FamilyComparison] = []
    for family in HarbourDeskFailureFamily:
        reference_successes = sum(item.verified_successes for item in reference_by_family[family])
        candidate_successes = sum(item.verified_successes for item in candidate_by_family[family])
        comparisons.append(
            FamilyComparison(
                family=family,
                reference_verified_successes=reference_successes,
                candidate_verified_successes=candidate_successes,
                observed_difference_percentage_points=(candidate_successes - reference_successes)
                / 10
                * 100.0,
            )
        )
    return tuple(comparisons)


def _tokens_per_success(
    inference_tokens: int, verified_successes: int, *, usage_complete: bool
) -> float | None:
    if not usage_complete or verified_successes == 0:
        return None
    return inference_tokens / verified_successes
