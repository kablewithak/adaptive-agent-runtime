from __future__ import annotations

import json
from pathlib import Path

from adaptive_runtime.environment.domain import HarbourDeskVisibleState, PolicyDocument
from adaptive_runtime.evaluation.benchmark_authoring import load_r4_template_catalog
from adaptive_runtime.evaluation.benchmark_program import BenchmarkPartition

ROOT = Path(__file__).resolve().parents[3]
VISIBLE_ROOT = ROOT / "benchmarks" / "harbourdesk" / "r4"

HIDDEN_RUNTIME_KEYS = {
    "family",
    "family_name",
    "difficulty",
    "split",
    "partition",
    "template_id",
    "mechanism_key",
    "expected",
    "expected_outcome",
    "preferred_model",
}


def _case_dirs(partition: str) -> tuple[Path, ...]:
    root = VISIBLE_ROOT / partition
    return tuple(sorted(path for path in root.iterdir() if path.is_dir()))


def test_r4_public_materialization_has_90_dev_30_validation_and_no_locked_payloads() -> None:
    catalog = load_r4_template_catalog(ROOT)

    development = _case_dirs("development")
    validation = _case_dirs("validation")

    assert len(development) == 90
    assert len(validation) == 30
    assert not (VISIBLE_ROOT / "locked").exists()

    expected_ids = {
        case_id
        for template in catalog.templates
        if template.partition is not BenchmarkPartition.LOCKED
        for case_id in template.instance_ids
    }
    observed_ids = {path.name for path in (*development, *validation)}
    assert observed_ids == expected_ids


def test_r4_public_cases_validate_without_hidden_authoring_labels() -> None:
    for partition in ("development", "validation"):
        for visible_dir in _case_dirs(partition):
            case_payload = json.loads((visible_dir / "case.json").read_text(encoding="utf-8"))
            assert not HIDDEN_RUNTIME_KEYS.intersection(case_payload)
            assert set(case_payload) == {
                "schema_version",
                "task_ref",
                "ticket_id",
                "frozen_at",
                "initial_state_file",
                "documents_file",
            }

            state = HarbourDeskVisibleState.model_validate_json(
                (visible_dir / "initial_state.json").read_text(encoding="utf-8")
            )
            assert case_payload["ticket_id"] in {ticket.ticket_id for ticket in state.tickets}
            assert case_payload["frozen_at"] == state.frozen_at.isoformat().replace("+00:00", "Z")

            lines = (visible_dir / "documents.jsonl").read_text(encoding="utf-8").splitlines()
            documents = tuple(
                PolicyDocument.model_validate_json(line) for line in lines if line.strip()
            )
            assert tuple(item.document_id for item in documents) == tuple(
                item.document_id for item in state.policies
            )
            assert not (visible_dir / "expected.json").exists()
            assert not (visible_dir / "rehearsal.json").exists()
            assert not (visible_dir / "authoring.json").exists()
