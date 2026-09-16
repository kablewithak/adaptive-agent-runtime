from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptive_runtime.experiments import harbourdesk_m2b
from adaptive_runtime.experiments.harbourdesk_m1b import M1B_CASE_IDS
from adaptive_runtime.experiments.harbourdesk_m2b import (
    M2BError,
    run_m2b_oracle,
)
from adaptive_runtime.routing.contracts import RoutingGateStatus


def _summary(
    *,
    run_id: str,
    profile_name: str,
    model_id: str,
    passes: set[str],
    tokens: dict[str, int],
) -> dict[str, object]:
    cases = []
    for case_id in M1B_CASE_IDS:
        case_tokens = tokens[case_id]
        cases.append(
            {
                "case_id": case_id,
                "usage_complete": True,
                "observed_input_tokens": case_tokens,
                "observed_completion_tokens": 0,
                "score_passed": case_id in passes,
            }
        )

    return {
        "baseline_complete": True,
        "run_id": run_id,
        "frozen_configuration": {
            "profile_name": profile_name,
            "model_id": model_id,
            "case_order": list(M1B_CASE_IDS),
        },
        "case_count": 12,
        "cases": cases,
        "usage_complete": True,
        "observed_inference_tokens": sum(tokens.values()),
    }


def _write(path: Path, payload: dict[str, object]) -> str:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return harbourdesk_m2b._sha256(path)


def _configure_hashes(
    monkeypatch: pytest.MonkeyPatch,
    reference_path: Path,
    alternative_path: Path,
) -> None:
    monkeypatch.setattr(
        harbourdesk_m2b,
        "M2B_REFERENCE_SUMMARY_SHA256",
        harbourdesk_m2b._sha256(reference_path),
    )
    monkeypatch.setattr(
        harbourdesk_m2b,
        "M2B_ALTERNATIVE_SUMMARY_SHA256",
        harbourdesk_m2b._sha256(alternative_path),
    )


def test_oracle_finds_feasible_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.json"
    alternative_path = tmp_path / "alternative.json"

    reference_tokens = {case_id: 20_000 for case_id in M1B_CASE_IDS}
    alternative_tokens = {case_id: 5_000 for case_id in M1B_CASE_IDS}

    _write(
        reference_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_REFERENCE_RUN_ID,
            profile_name="primary-openai",
            model_id="glm-5.1",
            passes=set(M1B_CASE_IDS[:6]),
            tokens=reference_tokens,
        ),
    )
    _write(
        alternative_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_ALTERNATIVE_RUN_ID,
            profile_name="glm-5-2-openai",
            model_id="glm-5.2",
            passes={"hdm-001", "hdm-004"},
            tokens=alternative_tokens,
        ),
    )
    _configure_hashes(monkeypatch, reference_path, alternative_path)

    result = run_m2b_oracle(
        reference_summary_path=reference_path,
        alternative_summary_path=alternative_path,
    )

    assert result.oracle_feasible
    assert result.max_verified_passes == 6
    assert result.best_passing_assignment is not None
    assert result.best_passing_assignment.overall_status is RoutingGateStatus.PASS
    assert result.complementarity.reference_only_passes == 4
    assert result.complementarity.alternative_only_passes == 0
    assert result.complementarity.both_pass == 2
    assert result.complementarity.neither_pass == 6


def test_oracle_stops_when_efficiency_has_no_headroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.json"
    alternative_path = tmp_path / "alternative.json"

    tokens = {case_id: 30_000 for case_id in M1B_CASE_IDS}

    _write(
        reference_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_REFERENCE_RUN_ID,
            profile_name="primary-openai",
            model_id="glm-5.1",
            passes=set(M1B_CASE_IDS[:6]),
            tokens=tokens,
        ),
    )
    _write(
        alternative_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_ALTERNATIVE_RUN_ID,
            profile_name="glm-5-2-openai",
            model_id="glm-5.2",
            passes={"hdm-001", "hdm-004"},
            tokens=tokens,
        ),
    )
    _configure_hashes(monkeypatch, reference_path, alternative_path)

    result = run_m2b_oracle(
        reference_summary_path=reference_path,
        alternative_summary_path=alternative_path,
    )

    assert not result.oracle_feasible
    assert result.max_verified_passes == 6
    assert result.best_passing_assignment is None
    assert result.minimum_tokens_at_quality_floor is not None
    assert result.minimum_tokens_at_quality_floor.efficiency_status is RoutingGateStatus.FAIL


def test_oracle_rejects_noncanonical_hash(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    alternative_path = tmp_path / "alternative.json"
    tokens = {case_id: 1_000 for case_id in M1B_CASE_IDS}

    _write(
        reference_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_REFERENCE_RUN_ID,
            profile_name="primary-openai",
            model_id="glm-5.1",
            passes=set(),
            tokens=tokens,
        ),
    )
    _write(
        alternative_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_ALTERNATIVE_RUN_ID,
            profile_name="glm-5-2-openai",
            model_id="glm-5.2",
            passes=set(),
            tokens=tokens,
        ),
    )

    with pytest.raises(
        M2BError,
        match="hash differs from the frozen canonical evidence",
    ):
        run_m2b_oracle(
            reference_summary_path=reference_path,
            alternative_summary_path=alternative_path,
        )


def test_oracle_rejects_incomplete_case_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.json"
    alternative_path = tmp_path / "alternative.json"
    tokens = {case_id: 1_000 for case_id in M1B_CASE_IDS}

    reference = _summary(
        run_id=harbourdesk_m2b.M2B_REFERENCE_RUN_ID,
        profile_name="primary-openai",
        model_id="glm-5.1",
        passes=set(),
        tokens=tokens,
    )
    reference["cases"][0]["usage_complete"] = False  # type: ignore[index]

    _write(reference_path, reference)
    _write(
        alternative_path,
        _summary(
            run_id=harbourdesk_m2b.M2B_ALTERNATIVE_RUN_ID,
            profile_name="glm-5-2-openai",
            model_id="glm-5.2",
            passes=set(),
            tokens=tokens,
        ),
    )
    _configure_hashes(monkeypatch, reference_path, alternative_path)

    with pytest.raises(M2BError, match="complete per-case usage"):
        run_m2b_oracle(
            reference_summary_path=reference_path,
            alternative_summary_path=alternative_path,
        )
