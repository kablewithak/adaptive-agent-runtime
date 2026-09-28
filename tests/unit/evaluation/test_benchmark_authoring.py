from __future__ import annotations

from collections import Counter
from pathlib import Path

from adaptive_runtime.evaluation.benchmark_authoring import load_r4_template_catalog
from adaptive_runtime.evaluation.benchmark_program import (
    R4_CASE_COUNT,
    R4_TEMPLATE_COUNT,
    BenchmarkPartition,
    HarbourDeskFailureFamily,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_r4_template_catalog_shape_and_mechanism_uniqueness() -> None:
    catalog = load_r4_template_catalog(_repo_root())

    assert catalog.exact_locked_fixture_material_sealed is True
    assert len(catalog.templates) == R4_TEMPLATE_COUNT

    case_ids = [case_id for template in catalog.templates for case_id in template.instance_ids]
    assert len(case_ids) == R4_CASE_COUNT
    assert len(set(case_ids)) == R4_CASE_COUNT

    mechanisms = [template.mechanism_key for template in catalog.templates]
    assert len(set(mechanisms)) == R4_TEMPLATE_COUNT

    for family in HarbourDeskFailureFamily:
        family_templates = [template for template in catalog.templates if template.family is family]
        assert len(family_templates) == 6
        assert Counter(template.partition for template in family_templates) == Counter(
            {
                BenchmarkPartition.DEVELOPMENT: 3,
                BenchmarkPartition.VALIDATION: 1,
                BenchmarkPartition.LOCKED: 2,
            }
        )


def test_public_case_ids_do_not_encode_family_or_partition() -> None:
    catalog = load_r4_template_catalog(_repo_root())

    for template in catalog.templates:
        for case_id in template.instance_ids:
            assert case_id.startswith("hdb-")
            assert template.family.value.lower() not in case_id.lower()
            assert template.partition.value.lower() not in case_id.lower()
            assert "hdm-" not in case_id.lower()


def test_exact_locked_fixture_material_remains_sealed() -> None:
    catalog = load_r4_template_catalog(_repo_root())

    locked = [
        template
        for template in catalog.templates
        if template.partition is BenchmarkPartition.LOCKED
    ]
    assert len(locked) == 12

    forbidden = (
        "expected.json",
        "resolution_reason_code",
        "ticket_id",
        "account_id",
        "subscription_id",
        "approval_id",
        "operation_id",
    )
    for template in locked:
        serialized = template.model_dump_json()
        for term in forbidden:
            assert term not in serialized
