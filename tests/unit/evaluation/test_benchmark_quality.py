from __future__ import annotations

from pathlib import Path

from adaptive_runtime.evaluation.benchmark_quality import (
    analyze_r4_public_benchmark,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r4_public_benchmark_quality_shape_and_structural_diversity() -> None:
    summary = analyze_r4_public_benchmark(ROOT)

    assert summary.passed is True
    assert summary.case_count == 120
    assert summary.development_case_count == 90
    assert summary.validation_case_count == 30
    assert summary.exposed_template_count == 24
    assert summary.unique_mechanism_count == 24
    assert summary.minimum_template_structural_diversity == 5
    assert summary.family_case_counts == {
        "F1": 20,
        "F2": 20,
        "F3": 20,
        "F4": 20,
        "F5": 20,
        "F6": 20,
    }
    assert summary.family_development_counts == {
        "F1": 15,
        "F2": 15,
        "F3": 15,
        "F4": 15,
        "F5": 15,
        "F6": 15,
    }
    assert summary.family_validation_counts == {
        "F1": 5,
        "F2": 5,
        "F3": 5,
        "F4": 5,
        "F5": 5,
        "F6": 5,
    }
    assert all(
        item.case_count == 5 and item.unique_structural_fingerprint_count == 5
        for item in summary.templates
    )
