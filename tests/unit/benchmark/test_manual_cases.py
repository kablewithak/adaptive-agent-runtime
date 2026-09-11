from __future__ import annotations

import json
from pathlib import Path

from adaptive_runtime.environment.domain import HarbourDeskVisibleState, PolicyDocument

ROOT = Path(__file__).resolve().parents[3]
VISIBLE_ROOT = ROOT / "benchmarks" / "harbourdesk" / "dev"

HIDDEN_RUNTIME_KEYS = {
    "family",
    "family_name",
    "difficulty",
    "split",
    "expected",
    "expected_outcome",
    "preferred_model",
}


def test_manual_suite_has_twelve_visible_cases() -> None:
    expected_case_ids = {f"hdm-{index:03d}" for index in range(1, 13)}
    observed_case_ids = {path.name for path in VISIBLE_ROOT.iterdir() if path.is_dir()}

    assert observed_case_ids == expected_case_ids


def test_all_visible_manual_cases_validate_without_hidden_labels() -> None:
    for visible_dir in sorted(VISIBLE_ROOT.iterdir()):
        if not visible_dir.is_dir():
            continue

        case_payload = json.loads((visible_dir / "case.json").read_text(encoding="utf-8"))
        assert not HIDDEN_RUNTIME_KEYS.intersection(case_payload)

        state = HarbourDeskVisibleState.model_validate_json(
            (visible_dir / "initial_state.json").read_text(encoding="utf-8")
        )

        assert state.frozen_at.isoformat().startswith("2026-09-11T12:00:00")
        assert case_payload["ticket_id"] in {ticket.ticket_id for ticket in state.tickets}

        document_lines = (visible_dir / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        documents = tuple(
            PolicyDocument.model_validate_json(line) for line in document_lines if line.strip()
        )

        assert tuple(document.document_id for document in documents) == tuple(
            document.document_id for document in state.policies
        )


def test_runtime_visible_cases_do_not_contain_expected_outcomes() -> None:
    for visible_dir in sorted(VISIBLE_ROOT.iterdir()):
        if visible_dir.is_dir():
            assert not (visible_dir / "expected.json").exists()
