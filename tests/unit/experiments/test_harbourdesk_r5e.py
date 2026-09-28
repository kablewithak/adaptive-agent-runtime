from __future__ import annotations

from collections import Counter
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r5e import (
    load_r5e_screen_manifest,
)

ROOT = Path(__file__).resolve().parents[3]


def test_r5e_screen_is_two_cases_per_development_template() -> None:
    screen = load_r5e_screen_manifest(ROOT)

    assert screen.case_count == 36
    assert screen.template_count == 18
    assert screen.cases_per_template == 2
    assert len(screen.case_order) == 36
    assert len(set(screen.case_order)) == 36

    template_counts = Counter(str(entry.get("template_id")) for entry in screen.entries)
    family_counts = Counter(str(entry.get("family")) for entry in screen.entries)

    assert len(template_counts) == 18
    assert set(template_counts.values()) == {2}
    assert family_counts == Counter({f"F{i}": 6 for i in range(1, 7)})


def test_r5e_selection_rule_is_frozen_manifest_order() -> None:
    screen = load_r5e_screen_manifest(ROOT)

    assert screen.selection_rule == (
        "first_two_cases_per_development_template_in_frozen_r5_manifest_order"
    )
