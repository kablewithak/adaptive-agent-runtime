from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.end_to_end import (
    ScriptedEnvironmentTrace,
    ScriptedEnvironmentTrajectory,
    load_trajectory_json,
    run_scripted_environment,
)
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import CaseScore, score_case


class EndToEndRehearsalError(RuntimeError):
    """Raised when deterministic P1.5 evidence cannot be produced safely."""


class PrivateEvaluationDataMissing(EndToEndRehearsalError):
    """Raised when local evaluator-only labels required for scoring are unavailable."""


class EndToEndRehearsalStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class EndToEndRehearsalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EndToEndCaseResult(EndToEndRehearsalContract):
    case_id: str
    trace_passed: bool
    score_passed: bool
    matched_predicate_index: int | None
    step_count: int = Field(ge=0)
    new_effective_write_count: int = Field(ge=0)
    scoring_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.trace_passed and self.score_passed


class EndToEndRehearsalSummary(EndToEndRehearsalContract):
    status: EndToEndRehearsalStatus
    case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    trace_passed_count: int = Field(ge=0)
    scorer_passed_count: int = Field(ge=0)
    total_step_count: int = Field(ge=0)
    effective_business_write_count: int = Field(ge=0)
    llm_call_count: int = Field(ge=0)
    cases: tuple[EndToEndCaseResult, ...]


def run_manual_end_to_end_rehearsal(repo_root: Path) -> EndToEndRehearsalSummary:
    public_root = repo_root / "benchmarks" / "harbourdesk" / "dev"
    trajectory_root = repo_root / "benchmarks" / "harbourdesk" / "end_to_end_rehearsals"
    private_root = repo_root / "evaluation_private" / "harbourdesk" / "dev"
    rules_path = repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"

    case_ids = tuple(f"hdm-{index:03d}" for index in range(1, 13))
    _require_private_labels(private_root, case_ids)
    rules = HarbourDeskBusinessRules.load(rules_path)

    results = tuple(
        _run_case(
            public_root=public_root,
            trajectory_root=trajectory_root,
            private_root=private_root,
            rules=rules,
            case_id=case_id,
        )
        for case_id in case_ids
    )

    passed_count = sum(result.passed for result in results)
    trace_passed = sum(result.trace_passed for result in results)
    scorer_passed = sum(result.score_passed for result in results)
    effective_writes = sum(result.new_effective_write_count for result in results)
    total_steps = sum(result.step_count for result in results)

    return EndToEndRehearsalSummary(
        status=(
            EndToEndRehearsalStatus.PASS
            if passed_count == len(case_ids)
            else EndToEndRehearsalStatus.FAIL
        ),
        case_count=len(case_ids),
        passed_case_count=passed_count,
        trace_passed_count=trace_passed,
        scorer_passed_count=scorer_passed,
        total_step_count=total_steps,
        effective_business_write_count=effective_writes,
        llm_call_count=0,
        cases=results,
    )


def _run_case(
    *,
    public_root: Path,
    trajectory_root: Path,
    private_root: Path,
    rules: HarbourDeskBusinessRules,
    case_id: str,
) -> EndToEndCaseResult:
    case_root = public_root / case_id
    initial = HarbourDeskVisibleState.model_validate_json(
        (case_root / "initial_state.json").read_text(encoding="utf-8")
    )
    trajectory = load_trajectory_json(
        (trajectory_root / f"{case_id}.json").read_text(encoding="utf-8")
    )
    expected = ExpectedCaseOutcome.model_validate_json(
        (private_root / case_id / "expected.json").read_text(encoding="utf-8")
    )
    return run_end_to_end_case(
        initial=initial,
        trajectory=trajectory,
        expected=expected,
        rules=rules,
    )


def run_end_to_end_case(
    *,
    initial: HarbourDeskVisibleState,
    trajectory: ScriptedEnvironmentTrajectory,
    expected: ExpectedCaseOutcome,
    rules: HarbourDeskBusinessRules,
) -> EndToEndCaseResult:
    if trajectory.case_id != expected.case_id:
        raise EndToEndRehearsalError("trajectory and expected case identities differ")

    ticket = next(
        (item for item in initial.tickets if item.ticket_id == trajectory.ticket_id),
        None,
    )
    if ticket is None:
        raise EndToEndRehearsalError("trajectory ticket is missing from initial state")
    if ticket.tenant_id != trajectory.tenant_id:
        raise EndToEndRehearsalError("trajectory tenant does not match initial ticket tenant")

    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        environment = HarbourDeskEnvironment(
            store=store,
            rules=rules,
            tenant_id=trajectory.tenant_id,
            ticket_id=trajectory.ticket_id,
        )
        trace = run_scripted_environment(environment, trajectory)
        final = environment.snapshot()

    score = score_case(initial, final, expected)
    return _case_result(initial, final, trace, score)


def _case_result(
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
    trace: ScriptedEnvironmentTrace,
    score: CaseScore,
) -> EndToEndCaseResult:
    initial_operation_ids = {operation.operation_id for operation in initial.operations}
    effective_write_count = sum(
        operation.operation_id not in initial_operation_ids and operation.effective_write
        for operation in final.operations
    )
    failures = tuple(
        sorted(
            {
                failure.value
                for predicate_score in score.predicate_scores
                for failure in predicate_score.failures
            }
        )
    )
    return EndToEndCaseResult(
        case_id=score.case_id,
        trace_passed=trace.all_steps_matched,
        score_passed=score.passed,
        matched_predicate_index=score.matched_predicate_index,
        step_count=len(trace.results),
        new_effective_write_count=effective_write_count,
        scoring_failures=failures,
    )


def _require_private_labels(private_root: Path, case_ids: tuple[str, ...]) -> None:
    missing = tuple(
        case_id for case_id in case_ids if not (private_root / case_id / "expected.json").is_file()
    )
    if missing:
        joined = ", ".join(missing)
        raise PrivateEvaluationDataMissing(
            "P1.5 independent scoring requires local evaluator-only expected.json files; "
            f"missing cases: {joined}"
        )
