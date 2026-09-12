from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.scripted import (
    ScriptedReadTrajectory,
    run_scripted_reads,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore

ROOT = Path(__file__).resolve().parents[3]
VISIBLE_ROOT = ROOT / "benchmarks" / "harbourdesk" / "dev"
TRAJECTORY_ROOT = ROOT / "benchmarks" / "harbourdesk" / "read_rehearsals"


def test_all_manual_read_trajectories_execute_without_llm() -> None:
    for case_dir in sorted(VISIBLE_ROOT.glob("hdm-*")):
        case_id = case_dir.name
        initial = HarbourDeskVisibleState.model_validate_json(
            (case_dir / "initial_state.json").read_text(encoding="utf-8")
        )
        trajectory = ScriptedReadTrajectory.model_validate_json(
            (TRAJECTORY_ROOT / f"{case_id}.json").read_text(encoding="utf-8")
        )

        with HarbourDeskStore.in_memory() as store:
            store.initialize(initial)
            trace = run_scripted_reads(store, trajectory)

        assert trace.case_id == case_id
        assert trace.all_calls_succeeded is True
        assert len(trace.results) == len(trajectory.steps)


def test_scripted_read_trajectory_does_not_mutate_state() -> None:
    case_id = "hdm-011"
    initial = HarbourDeskVisibleState.model_validate_json(
        (VISIBLE_ROOT / case_id / "initial_state.json").read_text(encoding="utf-8")
    )
    trajectory = ScriptedReadTrajectory.model_validate_json(
        (TRAJECTORY_ROOT / f"{case_id}.json").read_text(encoding="utf-8")
    )

    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        before = store.snapshot()
        run_scripted_reads(store, trajectory)
        after = store.snapshot()

    assert after == before
