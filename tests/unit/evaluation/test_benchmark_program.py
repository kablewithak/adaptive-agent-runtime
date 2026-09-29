from __future__ import annotations

from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from adaptive_runtime.evaluation.benchmark_program import (
    R4_CASE_COUNT,
    R4_FINAL_ACCEPTANCE,
    R4_TEMPLATE_COUNT,
    BenchmarkPartition,
    BenchmarkProgramManifest,
    BenchmarkTemplateSpec,
    FaultSuiteSummary,
    GateStatus,
    HarbourDeskFailureFamily,
    LockedTemplateArmResult,
    NorthStarComparisonInput,
    evaluate_north_star,
)


def _manifest() -> BenchmarkProgramManifest:
    templates: list[BenchmarkTemplateSpec] = []
    case_number = 1
    for family in HarbourDeskFailureFamily:
        partitions = (
            BenchmarkPartition.DEVELOPMENT,
            BenchmarkPartition.DEVELOPMENT,
            BenchmarkPartition.DEVELOPMENT,
            BenchmarkPartition.VALIDATION,
            BenchmarkPartition.LOCKED,
            BenchmarkPartition.LOCKED,
        )
        for index, partition in enumerate(partitions, 1):
            instance_ids = tuple(f"hdb-{case_number + offset:03d}" for offset in range(5))
            case_number += 5
            templates.append(
                BenchmarkTemplateSpec(
                    template_id=f"{family.value.lower()}-template-{index:02d}",
                    family=family,
                    partition=partition,
                    instance_ids=instance_ids,
                )
            )
    return BenchmarkProgramManifest(templates=tuple(templates))


def _arm(
    successes: Iterable[int],
    *,
    tokens_per_template: int,
    usage_complete: bool = True,
    evidence_complete: bool = True,
    critical_safety_violations: int = 0,
) -> tuple[LockedTemplateArmResult, ...]:
    values = tuple(successes)
    assert len(values) == 12
    result: list[LockedTemplateArmResult] = []
    cursor = 0
    for family in HarbourDeskFailureFamily:
        for family_index in range(2):
            result.append(
                LockedTemplateArmResult(
                    template_id=f"{family.value.lower()}-locked-{family_index + 1:02d}",
                    family=family,
                    verified_successes=values[cursor],
                    inference_tokens=tokens_per_template,
                    usage_complete=usage_complete,
                    evidence_complete=evidence_complete,
                    critical_safety_violation_count=(
                        critical_safety_violations if cursor == 0 else 0
                    ),
                )
            )
            cursor += 1
    return tuple(result)


def _comparison(
    reference_successes: Iterable[int],
    candidate_successes: Iterable[int],
    *,
    reference_tokens_per_template: int = 10_000,
    candidate_tokens_per_template: int = 7_500,
    candidate_usage_complete: bool = True,
    candidate_evidence_complete: bool = True,
    candidate_safety_violations: int = 0,
    fault_failures: int = 0,
    fault_evidence_complete: bool = True,
) -> NorthStarComparisonInput:
    return NorthStarComparisonInput(
        reference=_arm(reference_successes, tokens_per_template=reference_tokens_per_template),
        candidate=_arm(
            candidate_successes,
            tokens_per_template=candidate_tokens_per_template,
            usage_complete=candidate_usage_complete,
            evidence_complete=candidate_evidence_complete,
            critical_safety_violations=candidate_safety_violations,
        ),
        fault_suite=FaultSuiteSummary(
            executed_case_count=24,
            invariant_failure_count=fault_failures,
            evidence_complete=fault_evidence_complete,
        ),
    )


def test_r4_manifest_freezes_36_templates_and_180_cases() -> None:
    manifest = _manifest()
    assert len(manifest.templates) == R4_TEMPLATE_COUNT
    assert sum(len(item.instance_ids) for item in manifest.templates) == R4_CASE_COUNT
    for family in HarbourDeskFailureFamily:
        family_templates = tuple(item for item in manifest.templates if item.family is family)
        assert len(family_templates) == 6
        assert (
            sum(item.partition is BenchmarkPartition.DEVELOPMENT for item in family_templates) == 3
        )
        assert (
            sum(item.partition is BenchmarkPartition.VALIDATION for item in family_templates) == 1
        )
        assert sum(item.partition is BenchmarkPartition.LOCKED for item in family_templates) == 2


def test_r4_manifest_rejects_duplicate_public_case_identity() -> None:
    manifest = _manifest()
    templates = list(manifest.templates)
    duplicate = templates[1].model_copy(
        update={"instance_ids": (templates[0].instance_ids[0], *templates[1].instance_ids[1:])}
    )
    with pytest.raises(ValidationError):
        BenchmarkProgramManifest(templates=(templates[0], duplicate, *templates[2:]))


def test_final_acceptance_contract_is_frozen_to_original_north_star() -> None:
    assert R4_FINAL_ACCEPTANCE.quality_noninferiority_margin_percentage_points == 5.0
    assert R4_FINAL_ACCEPTANCE.minimum_total_inference_reduction_fraction == 0.20
    assert R4_FINAL_ACCEPTANCE.template_confidence_level == 0.95
    assert R4_FINAL_ACCEPTANCE.paired_bootstrap_resamples == 10_000
    assert R4_FINAL_ACCEPTANCE.unscheduled_locked_reruns_allowed is False


def test_north_star_passes_when_quality_is_preserved_and_inference_drops_25_percent() -> None:
    decision = evaluate_north_star(
        _comparison(
            [4] * 12,
            [4] * 12,
            reference_tokens_per_template=10_000,
            candidate_tokens_per_template=7_500,
        )
    )
    assert decision.reference_verified_successes == 48
    assert decision.candidate_verified_successes == 48
    assert decision.observed_quality_difference_percentage_points == 0.0
    assert decision.template_bootstrap_lower_bound_percentage_points == 0.0
    assert decision.observed_total_inference_reduction_fraction == 0.25
    assert decision.quality_status is GateStatus.PASS
    assert decision.efficiency_status is GateStatus.PASS
    assert decision.family_regression_status is GateStatus.PASS
    assert decision.safety_status is GateStatus.PASS
    assert decision.evidence_status is GateStatus.PASS
    assert decision.overall_status is GateStatus.PASS


def test_quality_drop_beyond_five_points_is_a_fail() -> None:
    decision = evaluate_north_star(_comparison([5] * 12, [4] * 12))
    assert decision.observed_quality_difference_percentage_points == -20.0
    assert decision.quality_status is GateStatus.FAIL
    assert decision.overall_status is GateStatus.FAIL


def test_template_uncertainty_can_make_observed_noninferiority_inconclusive() -> None:
    decision = evaluate_north_star(_comparison([4] * 12, [3, 5, 3, 5, 3, 5, 3, 5, 3, 5, 3, 5]))
    assert decision.observed_quality_difference_percentage_points == 0.0
    assert decision.template_bootstrap_lower_bound_percentage_points < -5.0
    assert decision.quality_status is GateStatus.INCONCLUSIVE
    assert decision.overall_status is GateStatus.INCONCLUSIVE


def test_family_regression_beyond_ten_points_is_a_veto() -> None:
    reference = [4] * 12
    candidate = [4] * 12
    candidate[0] = 3
    candidate[1] = 3
    candidate[2] = 5
    candidate[3] = 5
    decision = evaluate_north_star(_comparison(reference, candidate))
    assert decision.observed_quality_difference_percentage_points == 0.0
    assert decision.family_comparisons[0].observed_difference_percentage_points == -20.0
    assert decision.family_regression_status is GateStatus.FAIL
    assert decision.overall_status is GateStatus.FAIL


def test_less_than_twenty_percent_inference_reduction_fails_efficiency() -> None:
    decision = evaluate_north_star(
        _comparison(
            [4] * 12,
            [4] * 12,
            reference_tokens_per_template=10_000,
            candidate_tokens_per_template=8_500,
        )
    )
    assert decision.observed_total_inference_reduction_fraction == 0.15
    assert decision.efficiency_status is GateStatus.FAIL
    assert decision.overall_status is GateStatus.FAIL


def test_incomplete_usage_makes_efficiency_inconclusive() -> None:
    decision = evaluate_north_star(_comparison([4] * 12, [4] * 12, candidate_usage_complete=False))
    assert decision.observed_total_inference_reduction_fraction is None
    assert decision.efficiency_status is GateStatus.INCONCLUSIVE
    assert decision.overall_status is GateStatus.INCONCLUSIVE


def test_candidate_critical_safety_violation_fails_final_gate() -> None:
    decision = evaluate_north_star(_comparison([4] * 12, [4] * 12, candidate_safety_violations=1))
    assert decision.safety_status is GateStatus.FAIL
    assert decision.overall_status is GateStatus.FAIL


def test_incomplete_fault_evidence_is_inconclusive() -> None:
    decision = evaluate_north_star(_comparison([4] * 12, [4] * 12, fault_evidence_complete=False))
    assert decision.safety_status is GateStatus.INCONCLUSIVE
    assert decision.evidence_status is GateStatus.INCONCLUSIVE
    assert decision.overall_status is GateStatus.INCONCLUSIVE
