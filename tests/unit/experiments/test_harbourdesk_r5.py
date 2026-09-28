from __future__ import annotations

from collections import Counter
from pathlib import Path

from adaptive_runtime.evaluation.benchmark_authoring import load_r4_template_catalog
from adaptive_runtime.evaluation.benchmark_program import BenchmarkPartition
from adaptive_runtime.experiments.harbourdesk_m3d import M3D_BUDGET
from adaptive_runtime.experiments.harbourdesk_r5 import (
    R5_R4_QUALIFIED_COMMIT,
    load_r5_manifest,
    validate_r5_public_contract,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r5_manifest_freezes_exactly_the_r4_development_population() -> None:
    manifest = load_r5_manifest(ROOT)
    catalog = load_r4_template_catalog(ROOT)

    expected_order = tuple(
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.DEVELOPMENT
        for case_id in template.instance_ids
    )

    assert manifest.r4_qualified_commit == R5_R4_QUALIFIED_COMMIT
    assert manifest.case_order == expected_order
    assert len(manifest.case_order) == 90
    assert len(set(manifest.case_order)) == 90
    assert Counter(entry.family for entry in manifest.entries) == Counter(
        {f"F{index}": 15 for index in range(1, 7)}
    )
    assert manifest.validation_case_count == 0
    assert manifest.locked_case_count == 0


def test_r5_manifest_preserves_qualified_m3d_budget() -> None:
    manifest = load_r5_manifest(ROOT)

    assert manifest.model_id == "glm-5.2"
    assert manifest.profile_name == "glm-5-2-openai"
    assert manifest.max_model_calls == M3D_BUDGET.max_model_calls == 8
    assert manifest.max_tool_actions == M3D_BUDGET.max_tool_actions == 10
    assert manifest.trajectory_deadline_seconds == M3D_BUDGET.trajectory_deadline_seconds == 300.0
    assert manifest.request_deadline_seconds == M3D_BUDGET.request_deadline_seconds == 60.0
    assert manifest.max_completion_tokens == M3D_BUDGET.max_completion_tokens == 1536


def test_r5_public_contract_hashes_and_selection_are_clean() -> None:
    assert validate_r5_public_contract(ROOT) == ()
