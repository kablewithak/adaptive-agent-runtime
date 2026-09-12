from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.scripted import (
    ScriptedReadTrajectory,
    run_scripted_reads,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore


class RehearsalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RehearsalStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class CaseReadRehearsalResult(RehearsalContract):
    case_id: str = Field(min_length=1, max_length=100)
    status: RehearsalStatus
    call_count: int = Field(ge=0)
    trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReadRehearsalSummary(RehearsalContract):
    status: RehearsalStatus
    case_count: int = Field(ge=0)
    total_call_count: int = Field(ge=0)
    cases: tuple[CaseReadRehearsalResult, ...]


def run_manual_read_rehearsal(repo_root: Path) -> ReadRehearsalSummary:
    visible_root = repo_root / "benchmarks" / "harbourdesk" / "dev"
    trajectory_root = repo_root / "benchmarks" / "harbourdesk" / "read_rehearsals"

    results: list[CaseReadRehearsalResult] = []

    for case_dir in sorted(visible_root.glob("hdm-*")):
        case_id = case_dir.name
        initial = HarbourDeskVisibleState.model_validate_json(
            (case_dir / "initial_state.json").read_text(encoding="utf-8")
        )
        trajectory = ScriptedReadTrajectory.model_validate_json(
            (trajectory_root / f"{case_id}.json").read_text(encoding="utf-8")
        )

        with HarbourDeskStore.in_memory() as store:
            store.initialize(initial)
            before = store.snapshot()
            trace = run_scripted_reads(store, trajectory)
            after = store.snapshot()

        passed = trace.all_calls_succeeded and after == before
        trace_bytes = trace.model_dump_json().encode("utf-8")

        results.append(
            CaseReadRehearsalResult(
                case_id=case_id,
                status=(RehearsalStatus.PASS if passed else RehearsalStatus.FAIL),
                call_count=len(trace.results),
                trace_sha256=hashlib.sha256(trace_bytes).hexdigest(),
            )
        )

    overall = (
        RehearsalStatus.PASS
        if results and all(result.status is RehearsalStatus.PASS for result in results)
        else RehearsalStatus.FAIL
    )

    return ReadRehearsalSummary(
        status=overall,
        case_count=len(results),
        total_call_count=sum(result.call_count for result in results),
        cases=tuple(results),
    )
