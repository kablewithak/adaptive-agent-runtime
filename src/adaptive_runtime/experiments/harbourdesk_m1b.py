from __future__ import annotations

import hashlib
from collections import Counter
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import ProviderProtocol
from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import CaseScore, score_case
from adaptive_runtime.providers.base import ProviderAdapter
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveRunBudget,
    LiveStopCategory,
    ProviderAttemptTrace,
    UsageObservationStatus,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink

M1B_MODEL_ID = "glm-5.1"
M1B_PROFILE_NAME = "primary-openai"
M1B_CASE_IDS = tuple(f"hdm-{index:03d}" for index in range(1, 13))
M1B_MAX_MODEL_CALLS = 8
M1B_MAX_TOOL_ACTIONS = 10
M1B_TRAJECTORY_DEADLINE_SECONDS = 300.0
M1B_REQUEST_DEADLINE_SECONDS = 60.0
M1B_MAX_COMPLETION_TOKENS = 768


class M1BError(RuntimeError):
    """Raised when the frozen M1B baseline cannot be produced safely."""


class M1BPrivateEvaluationMissing(M1BError):
    """Raised before live traffic when one or more evaluator labels are unavailable."""


class M1BExperimentStatus(StrEnum):
    COMPLETE = "complete"


class M1BContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class _PublicCaseManifest(M1BContract):
    schema_version: str
    task_ref: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    frozen_at: str
    initial_state_file: str = Field(min_length=1, max_length=200)
    documents_file: str = Field(min_length=1, max_length=200)


class M1BPublicCase(M1BContract):
    case_id: str = Field(min_length=1, max_length=100)
    task_ref: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    initial: HarbourDeskVisibleState
    rules: HarbourDeskBusinessRules


class M1BCaseInput(M1BContract):
    case: M1BPublicCase
    expected: ExpectedCaseOutcome


class M1BFrozenConfiguration(M1BContract):
    schema_version: str = "m1b-glm51-baseline-v1"
    profile_name: str
    model_id: str
    protocol: ProviderProtocol
    thinking: bool | None
    max_model_calls: int = Field(ge=1)
    max_tool_actions: int = Field(ge=1)
    trajectory_deadline_seconds: float = Field(gt=0)
    request_deadline_seconds: float = Field(gt=0)
    max_completion_tokens: int = Field(gt=0)
    case_order: tuple[str, ...]


class M1BSuiteManifest(M1BContract):
    schema_version: str = "m1b-manifest-v1"
    run_id: str = Field(min_length=1, max_length=100)
    status: str = "running"
    frozen_configuration: M1BFrozenConfiguration
    expected_case_count: int = 12


class M1BCaseReceipt(M1BContract):
    schema_version: str = "m1b-case-v1"
    case_id: str
    task_ref: str
    ticket_id: str
    run_id: str
    model_id: str
    stop_category: LiveStopCategory
    terminal_reached: bool
    attempt_count: int = Field(ge=0)
    tool_action_count: int = Field(ge=0)
    usage_complete: bool
    observed_input_tokens: int = Field(ge=0)
    observed_completion_tokens: int = Field(ge=0)
    observed_reasoning_tokens: int = Field(ge=0)
    observed_cached_input_tokens: int = Field(ge=0)
    observed_provider_latency_ms: int = Field(ge=0)
    independent_score_recorded: bool
    score_passed: bool
    matched_predicate_index: int | None
    scoring_failures: tuple[str, ...]
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class M1BExperimentReceipt(M1BContract):
    schema_version: str = "m1b-v1"
    status: M1BExperimentStatus
    baseline_complete: bool
    run_id: str
    frozen_configuration: M1BFrozenConfiguration
    case_count: int = Field(ge=0)
    cases: tuple[M1BCaseReceipt, ...]
    score_pass_count: int = Field(ge=0)
    score_pass_rate: float = Field(ge=0.0, le=1.0)
    usage_complete: bool
    observed_input_tokens: int = Field(ge=0)
    observed_completion_tokens: int = Field(ge=0)
    observed_reasoning_tokens: int = Field(ge=0)
    observed_cached_input_tokens: int = Field(ge=0)
    observed_inference_tokens: int = Field(ge=0)
    observed_provider_latency_ms: int = Field(ge=0)
    observed_tokens_per_verified_success: float | None = Field(default=None, gt=0)
    stop_category_counts: dict[str, int]
    scoring_failure_counts: dict[str, int]


def load_m1b_public_cases(repo_root: Path) -> tuple[M1BPublicCase, ...]:
    return tuple(_load_public_case(repo_root, case_id) for case_id in M1B_CASE_IDS)


def load_m1b_inputs(repo_root: Path) -> tuple[M1BCaseInput, ...]:
    cases = load_m1b_public_cases(repo_root)
    inputs: list[M1BCaseInput] = []
    missing: list[Path] = []

    for case in cases:
        expected_path = (
            repo_root
            / "evaluation_private"
            / "harbourdesk"
            / "dev"
            / case.case_id
            / "expected.json"
        )
        if not expected_path.is_file():
            missing.append(expected_path)
            continue

        expected = ExpectedCaseOutcome.model_validate_json(
            expected_path.read_text(encoding="utf-8")
        )
        _validate_expected(case, expected)
        inputs.append(M1BCaseInput(case=case, expected=expected))

    if missing:
        rendered = "\n".join(str(path) for path in missing)
        raise M1BPrivateEvaluationMissing(
            "M1B requires all 12 evaluator-only expected.json files before live traffic:\n"
            f"{rendered}"
        )

    result = tuple(inputs)
    _validate_inputs(result)
    return result


def run_m1b_experiment(
    *,
    inputs: tuple[M1BCaseInput, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
) -> M1BExperimentReceipt:
    _validate_profile(profile)
    _validate_inputs(inputs)
    _prepare_evidence_dir(evidence_dir)

    frozen = _frozen_configuration(profile)
    manifest = M1BSuiteManifest(
        run_id=run_id,
        frozen_configuration=frozen,
    )
    _write_json(evidence_dir / "manifest.json", manifest)

    receipts: list[M1BCaseReceipt] = []
    for item in inputs:
        case_dir = evidence_dir / item.case.case_id
        case_dir.mkdir(parents=False, exist_ok=False)
        receipt = _run_case(
            item=item,
            provider=provider,
            profile=profile,
            suite_run_id=run_id,
            trace_path=case_dir / "trace.jsonl",
        )
        _write_json(case_dir / "receipt.json", receipt)
        receipts.append(receipt)

    suite = _suite_receipt(
        run_id=run_id,
        frozen=frozen,
        cases=tuple(receipts),
    )
    _write_json(evidence_dir / "summary.json", suite)
    return suite


def _load_public_case(repo_root: Path, case_id: str) -> M1BPublicCase:
    case_root = repo_root / "benchmarks" / "harbourdesk" / "dev" / case_id
    manifest = _PublicCaseManifest.model_validate_json(
        (case_root / "case.json").read_text(encoding="utf-8")
    )
    initial = HarbourDeskVisibleState.model_validate_json(
        (case_root / manifest.initial_state_file).read_text(encoding="utf-8")
    )
    ticket = next(
        (item for item in initial.tickets if item.ticket_id == manifest.ticket_id),
        None,
    )
    if ticket is None:
        raise M1BError(f"case ticket missing from initial state: {case_id}")

    rules = HarbourDeskBusinessRules.load(
        repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    )
    return M1BPublicCase(
        case_id=case_id,
        task_ref=manifest.task_ref,
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.ticket_id,
        initial=initial,
        rules=rules,
    )


def _validate_profile(profile: EndpointProfile) -> None:
    if profile.profile_name != M1B_PROFILE_NAME:
        raise M1BError(
            f"M1B is frozen to profile {M1B_PROFILE_NAME}; selected {profile.profile_name}"
        )
    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise M1BError("M1B requires the qualified OpenAI-compatible Huawei profile")
    if profile.model_id != M1B_MODEL_ID:
        raise M1BError(f"M1B is frozen to {M1B_MODEL_ID}; selected profile uses {profile.model_id}")


def _validate_expected(case: M1BPublicCase, expected: ExpectedCaseOutcome) -> None:
    if expected.case_id != case.case_id:
        raise M1BError("public case and evaluator expected identities differ")
    if expected.terminal_ticket_id != case.ticket_id:
        raise M1BError("evaluator terminal ticket differs from the public case ticket")


def _validate_inputs(inputs: tuple[M1BCaseInput, ...]) -> None:
    case_order = tuple(item.case.case_id for item in inputs)
    if case_order != M1B_CASE_IDS:
        raise M1BError("M1B requires the frozen 12-case order hdm-001 through hdm-012 exactly once")

    for item in inputs:
        _validate_expected(item.case, item.expected)


def _prepare_evidence_dir(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"M1B evidence directory already exists: {path}")
    path.mkdir(parents=True, exist_ok=False)


def _frozen_configuration(profile: EndpointProfile) -> M1BFrozenConfiguration:
    return M1BFrozenConfiguration(
        profile_name=profile.profile_name,
        model_id=profile.model_id,
        protocol=profile.protocol,
        thinking=profile.thinking_control,
        max_model_calls=M1B_MAX_MODEL_CALLS,
        max_tool_actions=M1B_MAX_TOOL_ACTIONS,
        trajectory_deadline_seconds=M1B_TRAJECTORY_DEADLINE_SECONDS,
        request_deadline_seconds=M1B_REQUEST_DEADLINE_SECONDS,
        max_completion_tokens=M1B_MAX_COMPLETION_TOKENS,
        case_order=M1B_CASE_IDS,
    )


def _model_profile(profile: EndpointProfile) -> LiveModelProfile:
    return LiveModelProfile(
        model_id=profile.model_id,
        protocol=profile.protocol,
        thinking=profile.thinking_control,
        profile_version="m1b-glm51-baseline-v1",
    )


def _budget() -> LiveRunBudget:
    return LiveRunBudget(
        max_model_calls=M1B_MAX_MODEL_CALLS,
        max_tool_actions=M1B_MAX_TOOL_ACTIONS,
        trajectory_deadline_seconds=M1B_TRAJECTORY_DEADLINE_SECONDS,
        request_deadline_seconds=M1B_REQUEST_DEADLINE_SECONDS,
        max_completion_tokens=M1B_MAX_COMPLETION_TOKENS,
    )


def _run_case(
    *,
    item: M1BCaseInput,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    suite_run_id: str,
    trace_path: Path,
) -> M1BCaseReceipt:
    case = item.case
    case_run_id = f"{suite_run_id}-{case.case_id}"

    with HarbourDeskStore.in_memory() as store:
        store.initialize(case.initial)
        environment = HarbourDeskEnvironment(
            store=store,
            rules=case.rules,
            tenant_id=case.tenant_id,
            ticket_id=case.ticket_id,
        )
        run = run_live_harbourdesk(
            provider=provider,
            environment=environment,
            run_id=case_run_id,
            model_profile=_model_profile(profile),
            budget=_budget(),
            trace_sink=JsonlTraceSink(trace_path),
        )

    score = score_case(case.initial, run.final_state, item.expected)
    usage_complete, totals = _usage_totals(run.trace.attempts)
    provider_latency_ms = sum(attempt.latency_ms or 0 for attempt in run.trace.attempts)

    return M1BCaseReceipt(
        case_id=case.case_id,
        task_ref=case.task_ref,
        ticket_id=case.ticket_id,
        run_id=case_run_id,
        model_id=profile.model_id,
        stop_category=run.trace.stop_category,
        terminal_reached=run.trace.stop_category is LiveStopCategory.TICKET_TERMINAL,
        attempt_count=len(run.trace.attempts),
        tool_action_count=len(run.trace.tool_actions),
        usage_complete=usage_complete,
        observed_input_tokens=totals[0],
        observed_completion_tokens=totals[1],
        observed_reasoning_tokens=totals[2],
        observed_cached_input_tokens=totals[3],
        observed_provider_latency_ms=provider_latency_ms,
        independent_score_recorded=True,
        score_passed=score.passed,
        matched_predicate_index=score.matched_predicate_index,
        scoring_failures=_score_failures(score),
        final_state_sha256=run.trace.final_state_sha256,
        trace_sha256=_sha256_file(trace_path),
    )


def _score_failures(score: CaseScore) -> tuple[str, ...]:
    if score.passed:
        return ()
    return tuple(
        sorted(
            {
                failure.value
                for predicate in score.predicate_scores
                for failure in predicate.failures
            }
        )
    )


def _usage_totals(
    attempts: tuple[ProviderAttemptTrace, ...],
) -> tuple[bool, tuple[int, int, int, int]]:
    complete = bool(attempts)
    input_tokens = 0
    completion_tokens = 0
    reasoning_tokens = 0
    cached_input_tokens = 0

    for attempt in attempts:
        usage = attempt.usage
        if (
            attempt.usage_status is not UsageObservationStatus.OBSERVED
            or usage is None
            or usage.input_tokens is None
            or usage.completion_tokens is None
        ):
            complete = False

        if usage is None:
            continue

        input_tokens += usage.input_tokens or 0
        completion_tokens += usage.completion_tokens or 0
        reasoning_tokens += usage.reasoning_tokens or 0
        cached_input_tokens += usage.cached_input_tokens or 0

    return complete, (
        input_tokens,
        completion_tokens,
        reasoning_tokens,
        cached_input_tokens,
    )


def _suite_receipt(
    *,
    run_id: str,
    frozen: M1BFrozenConfiguration,
    cases: tuple[M1BCaseReceipt, ...],
) -> M1BExperimentReceipt:
    score_pass_count = sum(1 for case in cases if case.score_passed)
    case_count = len(cases)
    usage_complete = bool(cases) and all(case.usage_complete for case in cases)

    observed_input = sum(case.observed_input_tokens for case in cases)
    observed_completion = sum(case.observed_completion_tokens for case in cases)
    observed_reasoning = sum(case.observed_reasoning_tokens for case in cases)
    observed_cached = sum(case.observed_cached_input_tokens for case in cases)
    observed_inference = observed_input + observed_completion
    observed_latency = sum(case.observed_provider_latency_ms for case in cases)

    tokens_per_verified_success: float | None = None
    if usage_complete and score_pass_count > 0:
        tokens_per_verified_success = observed_inference / score_pass_count

    stop_counts = Counter(case.stop_category.value for case in cases)
    failure_counts = Counter(failure for case in cases for failure in case.scoring_failures)

    return M1BExperimentReceipt(
        status=M1BExperimentStatus.COMPLETE,
        baseline_complete=case_count == len(M1B_CASE_IDS),
        run_id=run_id,
        frozen_configuration=frozen,
        case_count=case_count,
        cases=cases,
        score_pass_count=score_pass_count,
        score_pass_rate=score_pass_count / case_count,
        usage_complete=usage_complete,
        observed_input_tokens=observed_input,
        observed_completion_tokens=observed_completion,
        observed_reasoning_tokens=observed_reasoning,
        observed_cached_input_tokens=observed_cached,
        observed_inference_tokens=observed_inference,
        observed_provider_latency_ms=observed_latency,
        observed_tokens_per_verified_success=tokens_per_verified_success,
        stop_category_counts=dict(sorted(stop_counts.items())),
        scoring_failure_counts=dict(sorted(failure_counts.items())),
    )


def _write_json(path: Path, payload: BaseModel) -> None:
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
