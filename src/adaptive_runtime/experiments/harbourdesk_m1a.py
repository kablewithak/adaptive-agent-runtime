from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    ModelResult,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderProtocol,
)
from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import CaseScore, score_case
from adaptive_runtime.providers.base import ProviderAdapter, ProviderCallError
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveRunBudget,
    LiveStopCategory,
    ProviderAttemptTrace,
    ToolActionTrace,
    UsageObservationStatus,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink

M1A_MODEL_ID = "glm-5.1"
M1A_STAGE_TOKEN_CAP = 250_000
M1A_OUTPUT_RESERVE = 768


class M1AError(RuntimeError):
    """Raised when M1A evidence cannot be produced safely."""


class M1APrivateEvaluationMissing(M1AError):
    """Raised before live traffic when evaluator-only expected data is unavailable."""


class M1AExperimentStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class M1AEnvelopeStatus(StrEnum):
    VERIFIED_SUFFICIENT = "verified_sufficient"
    ACCEPTED_USAGE_INCOMPLETE = "accepted_usage_incomplete"
    INITIAL_ONLY = "initial_only"
    FAILED = "failed"


class M1AContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class _PublicCaseManifest(M1AContract):
    schema_version: str
    task_ref: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    frozen_at: str
    initial_state_file: str = Field(min_length=1, max_length=200)
    documents_file: str = Field(min_length=1, max_length=200)


class M1APublicCase(M1AContract):
    case_id: str = Field(min_length=1, max_length=100)
    task_ref: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    initial: HarbourDeskVisibleState
    rules: HarbourDeskBusinessRules


class M1AProbeAttempt(M1AContract):
    phase: Literal["initial", "continuation"]
    request_message_count: int = Field(ge=1)
    tool_count: int = Field(ge=0)
    max_completion_tokens: int | None = Field(default=None, gt=0)
    outcome: ProviderOutcome
    usage_status: UsageObservationStatus
    input_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: ProviderErrorCode | None = None


class M1AEnvelopeReceipt(M1AContract):
    schema_version: str = "m1a-envelope-v1"
    case_id: str
    model_id: str
    output_reserve_tokens: int = Field(gt=0)
    initial: M1AProbeAttempt
    continuation: M1AProbeAttempt | None
    continuation_mode: Literal["tool_result", "user_followup", "unavailable"]
    status: M1AEnvelopeStatus
    sufficient_working_envelope_tokens: int | None = Field(default=None, gt=0)
    claims_absolute_context_limit: bool = False


class M1ACanaryReceipt(M1AContract):
    schema_version: str = "m1a-canary-v1"
    case_id: str
    run_id: str
    model_id: str
    stop_category: LiveStopCategory
    attempt_count: int = Field(ge=0)
    tool_action_count: int = Field(ge=0)
    usage_complete: bool
    observed_input_tokens: int = Field(ge=0)
    observed_completion_tokens: int = Field(ge=0)
    observed_reasoning_tokens: int = Field(ge=0)
    observed_cached_input_tokens: int = Field(ge=0)
    model_selected_trajectory: bool
    independent_score_recorded: bool
    score_passed: bool
    matched_predicate_index: int | None
    scoring_failures: tuple[str, ...]
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class M1AExperimentReceipt(M1AContract):
    schema_version: str = "m1a-v1"
    status: M1AExperimentStatus
    run_id: str
    case_id: str
    task_ref: str
    profile_name: str
    model_id: str
    envelope: M1AEnvelopeReceipt
    canary: M1ACanaryReceipt
    stage_token_cap: int = Field(gt=0)
    observed_stage_tokens: int = Field(ge=0)
    stage_usage_complete: bool
    within_stage_token_cap: bool | None
    gate_passed: bool


class _CapturingProvider:
    def __init__(self, delegate: ProviderAdapter) -> None:
        self._delegate = delegate
        self.requests: list[ModelRequest] = []
        self.results: list[ModelResult] = []
        self.errors: list[ProviderCallError] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        try:
            result = self._delegate.complete(request)
        except ProviderCallError as exc:
            self.errors.append(exc)
            raise
        self.results.append(result)
        return result


def load_public_case(repo_root: Path, case_id: str = "hdm-001") -> M1APublicCase:
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
        raise M1AError(f"case ticket missing from initial state: {manifest.ticket_id}")

    rules_path = repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    return M1APublicCase(
        case_id=case_id,
        task_ref=manifest.task_ref,
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.ticket_id,
        initial=initial,
        rules=HarbourDeskBusinessRules.load(rules_path),
    )


def load_private_expected(repo_root: Path, case_id: str = "hdm-001") -> ExpectedCaseOutcome:
    path = repo_root / "evaluation_private" / "harbourdesk" / "dev" / case_id / "expected.json"
    if not path.is_file():
        raise M1APrivateEvaluationMissing(
            f"M1A requires the local evaluator-only expected.json before live traffic: {path}"
        )
    return ExpectedCaseOutcome.model_validate_json(path.read_text(encoding="utf-8"))


def run_m1a_experiment(
    *,
    case: M1APublicCase,
    expected: ExpectedCaseOutcome,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    evidence_dir: Path,
) -> M1AExperimentReceipt:
    _validate_profile(profile)
    _validate_expected(case, expected)
    _prepare_evidence_dir(evidence_dir)

    envelope = _run_envelope_probe(
        case=case,
        provider=provider,
        profile=profile,
        run_id=run_id,
    )
    _write_json(evidence_dir / "envelope.json", envelope)

    canary = _run_canary(
        case=case,
        expected=expected,
        provider=provider,
        profile=profile,
        run_id=run_id,
        trace_path=evidence_dir / "canary-trace.jsonl",
    )

    observed_stage_tokens, stage_usage_complete = _stage_usage(envelope, canary)
    within_cap: bool | None = None
    if stage_usage_complete:
        within_cap = observed_stage_tokens <= M1A_STAGE_TOKEN_CAP

    continuation_evidence = (
        envelope.continuation is not None
        and envelope.continuation.outcome is ProviderOutcome.SUCCESS
    ) or canary.attempt_count >= 2
    gate_passed = (
        envelope.initial.outcome is ProviderOutcome.SUCCESS
        and continuation_evidence
        and canary.model_selected_trajectory
        and canary.independent_score_recorded
        and within_cap is not False
    )

    receipt = M1AExperimentReceipt(
        status=M1AExperimentStatus.PASS if gate_passed else M1AExperimentStatus.FAIL,
        run_id=run_id,
        case_id=case.case_id,
        task_ref=case.task_ref,
        profile_name=profile.profile_name,
        model_id=profile.model_id,
        envelope=envelope,
        canary=canary,
        stage_token_cap=M1A_STAGE_TOKEN_CAP,
        observed_stage_tokens=observed_stage_tokens,
        stage_usage_complete=stage_usage_complete,
        within_stage_token_cap=within_cap,
        gate_passed=gate_passed,
    )
    _write_json(evidence_dir / "summary.json", receipt)
    return receipt


def _validate_profile(profile: EndpointProfile) -> None:
    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise M1AError("M1A requires the existing OpenAI-compatible Huawei profile")
    if profile.model_id != M1A_MODEL_ID:
        raise M1AError(f"M1A is frozen to {M1A_MODEL_ID}; selected profile uses {profile.model_id}")


def _validate_expected(case: M1APublicCase, expected: ExpectedCaseOutcome) -> None:
    if expected.case_id != case.case_id:
        raise M1AError("public case and evaluator expected identities differ")
    if expected.terminal_ticket_id != case.ticket_id:
        raise M1AError("evaluator terminal ticket differs from the public case ticket")


def _prepare_evidence_dir(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"M1A evidence directory already exists: {path}")
    path.mkdir(parents=True, exist_ok=False)


def _model_profile(profile: EndpointProfile) -> LiveModelProfile:
    return LiveModelProfile(
        model_id=profile.model_id,
        protocol=profile.protocol,
        thinking=profile.thinking_control,
        profile_version="m1a-glm51-v1",
    )


def _new_environment(store: HarbourDeskStore, case: M1APublicCase) -> HarbourDeskEnvironment:
    store.initialize(case.initial)
    return HarbourDeskEnvironment(
        store=store,
        rules=case.rules,
        tenant_id=case.tenant_id,
        ticket_id=case.ticket_id,
    )


def _run_envelope_probe(
    *,
    case: M1APublicCase,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
) -> M1AEnvelopeReceipt:
    capturing = _CapturingProvider(provider)
    probe_budget = LiveRunBudget(
        max_model_calls=1,
        max_tool_actions=1,
        trajectory_deadline_seconds=120.0,
        request_deadline_seconds=60.0,
        max_completion_tokens=M1A_OUTPUT_RESERVE,
    )

    with HarbourDeskStore.in_memory() as store:
        environment = _new_environment(store, case)
        probe_run = run_live_harbourdesk(
            provider=capturing,
            environment=environment,
            run_id=f"{run_id}-envelope",
            model_profile=_model_profile(profile),
            budget=probe_budget,
        )

    if not capturing.requests or not probe_run.trace.attempts:
        raise M1AError("envelope probe did not admit an initial provider attempt")

    initial_request = capturing.requests[0]
    initial = _probe_from_trace(
        phase="initial",
        request=initial_request,
        attempt=probe_run.trace.attempts[0],
    )

    continuation: M1AProbeAttempt | None = None
    continuation_mode: Literal["tool_result", "user_followup", "unavailable"] = "unavailable"
    continuation_request = None
    if capturing.results:
        continuation_request, continuation_mode = _continuation_request(
            base_request=initial_request,
            result=capturing.results[0],
            tool_actions=probe_run.trace.tool_actions,
            run_id=run_id,
        )

    if continuation_request is not None:
        try:
            result = provider.complete(continuation_request)
        except ProviderCallError as exc:
            continuation = _probe_from_error(
                phase="continuation",
                request=continuation_request,
                error=exc,
            )
        else:
            continuation = _probe_from_result(
                phase="continuation",
                request=continuation_request,
                result=result,
            )

    status = _envelope_status(initial, continuation)
    sufficient_tokens = _sufficient_working_envelope(
        initial,
        continuation,
        M1A_OUTPUT_RESERVE,
    )
    return M1AEnvelopeReceipt(
        case_id=case.case_id,
        model_id=profile.model_id,
        output_reserve_tokens=M1A_OUTPUT_RESERVE,
        initial=initial,
        continuation=continuation,
        continuation_mode=continuation_mode,
        status=status,
        sufficient_working_envelope_tokens=sufficient_tokens,
    )


def _continuation_request(
    *,
    base_request: ModelRequest,
    result: ModelResult,
    tool_actions: tuple[ToolActionTrace, ...],
    run_id: str,
) -> tuple[
    ModelRequest | None,
    Literal["tool_result", "user_followup", "unavailable"],
]:
    if result.outcome is not ProviderOutcome.SUCCESS:
        return None, "unavailable"

    messages = list(base_request.messages)
    messages.append(
        ChatMessage(
            role=ChatRole.ASSISTANT,
            content=result.text,
            tool_calls=result.tool_calls,
            provider_reasoning_content=result.provider_reasoning_content,
        )
    )

    mode: Literal["tool_result", "user_followup", "unavailable"]
    if len(result.tool_calls) == 1 and len(tool_actions) == 1:
        tool_call = result.tool_calls[0]
        action = tool_actions[0]
        messages.append(
            ChatMessage(
                role=ChatRole.TOOL,
                tool_call_id=tool_call.id,
                name=tool_call.function.name,
                content=json.dumps(
                    action.result,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        mode = "tool_result"
    elif not result.tool_calls and result.text:
        messages.append(
            ChatMessage(
                role=ChatRole.USER,
                content=(
                    "Continue the same HarbourDesk task using the available tools. "
                    "Do not invent state."
                ),
            )
        )
        mode = "user_followup"
    else:
        return None, "unavailable"

    return (
        ModelRequest(
            request_id=f"{run_id}-envelope-continuation",
            model_id=base_request.model_id,
            protocol=base_request.protocol,
            messages=tuple(messages),
            tools=base_request.tools,
            max_completion_tokens=M1A_OUTPUT_RESERVE,
            thinking=base_request.thinking,
            deadline_seconds=60.0,
            experiment_reference=run_id,
        ),
        mode,
    )


def _probe_from_trace(
    *,
    phase: Literal["initial", "continuation"],
    request: ModelRequest,
    attempt: ProviderAttemptTrace,
) -> M1AProbeAttempt:
    usage = attempt.usage
    return M1AProbeAttempt(
        phase=phase,
        request_message_count=len(request.messages),
        tool_count=len(request.tools),
        max_completion_tokens=request.max_completion_tokens,
        outcome=attempt.outcome,
        usage_status=attempt.usage_status,
        input_tokens=None if usage is None else usage.input_tokens,
        completion_tokens=None if usage is None else usage.completion_tokens,
        reasoning_tokens=None if usage is None else usage.reasoning_tokens,
        cached_input_tokens=None if usage is None else usage.cached_input_tokens,
        http_status=attempt.http_status,
        latency_ms=attempt.latency_ms,
        error_code=attempt.error_code,
    )


def _probe_from_result(
    *,
    phase: Literal["initial", "continuation"],
    request: ModelRequest,
    result: ModelResult,
) -> M1AProbeAttempt:
    usage = result.usage
    return M1AProbeAttempt(
        phase=phase,
        request_message_count=len(request.messages),
        tool_count=len(request.tools),
        max_completion_tokens=request.max_completion_tokens,
        outcome=result.outcome,
        usage_status=(
            UsageObservationStatus.OBSERVED if usage is not None else UsageObservationStatus.MISSING
        ),
        input_tokens=None if usage is None else usage.input_tokens,
        completion_tokens=None if usage is None else usage.completion_tokens,
        reasoning_tokens=None if usage is None else usage.reasoning_tokens,
        cached_input_tokens=None if usage is None else usage.cached_input_tokens,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        error_code=result.error_code,
    )


def _probe_from_error(
    *,
    phase: Literal["initial", "continuation"],
    request: ModelRequest,
    error: ProviderCallError,
) -> M1AProbeAttempt:
    return M1AProbeAttempt(
        phase=phase,
        request_message_count=len(request.messages),
        tool_count=len(request.tools),
        max_completion_tokens=request.max_completion_tokens,
        outcome=ProviderOutcome.ERROR,
        usage_status=UsageObservationStatus.UNKNOWN_AFTER_ERROR,
        http_status=error.http_status,
        error_code=error.code,
    )


def _envelope_status(
    initial: M1AProbeAttempt,
    continuation: M1AProbeAttempt | None,
) -> M1AEnvelopeStatus:
    if initial.outcome is not ProviderOutcome.SUCCESS:
        return M1AEnvelopeStatus.FAILED
    if continuation is None:
        return M1AEnvelopeStatus.INITIAL_ONLY
    if continuation.outcome is not ProviderOutcome.SUCCESS:
        return M1AEnvelopeStatus.FAILED
    if initial.input_tokens is None or continuation.input_tokens is None:
        return M1AEnvelopeStatus.ACCEPTED_USAGE_INCOMPLETE
    return M1AEnvelopeStatus.VERIFIED_SUFFICIENT


def _sufficient_working_envelope(
    initial: M1AProbeAttempt,
    continuation: M1AProbeAttempt | None,
    output_reserve: int,
) -> int | None:
    observed = [item for item in (initial.input_tokens,) if item is not None]
    if continuation is not None and continuation.input_tokens is not None:
        observed.append(continuation.input_tokens)
    if not observed:
        return None
    return max(observed) + output_reserve


def _run_canary(
    *,
    case: M1APublicCase,
    expected: ExpectedCaseOutcome,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    trace_path: Path,
) -> M1ACanaryReceipt:
    budget = LiveRunBudget(
        max_model_calls=8,
        max_tool_actions=10,
        trajectory_deadline_seconds=300.0,
        request_deadline_seconds=60.0,
        max_completion_tokens=M1A_OUTPUT_RESERVE,
    )
    with HarbourDeskStore.in_memory() as store:
        environment = _new_environment(store, case)
        run = run_live_harbourdesk(
            provider=provider,
            environment=environment,
            run_id=f"{run_id}-canary",
            model_profile=_model_profile(profile),
            budget=budget,
            trace_sink=JsonlTraceSink(trace_path),
        )

    score = score_case(case.initial, run.final_state, expected)
    failures = _score_failures(score)
    usage_complete, totals = _usage_totals(run.trace.attempts)
    model_selected = any(
        attempt.outcome is ProviderOutcome.SUCCESS for attempt in run.trace.attempts
    )
    return M1ACanaryReceipt(
        case_id=case.case_id,
        run_id=run_id,
        model_id=profile.model_id,
        stop_category=run.trace.stop_category,
        attempt_count=len(run.trace.attempts),
        tool_action_count=len(run.trace.tool_actions),
        usage_complete=usage_complete,
        observed_input_tokens=totals[0],
        observed_completion_tokens=totals[1],
        observed_reasoning_tokens=totals[2],
        observed_cached_input_tokens=totals[3],
        model_selected_trajectory=model_selected,
        independent_score_recorded=True,
        score_passed=score.passed,
        matched_predicate_index=score.matched_predicate_index,
        scoring_failures=failures,
        final_state_sha256=run.trace.final_state_sha256,
        trace_sha256=_sha256_file(trace_path),
    )


def _score_failures(score: CaseScore) -> tuple[str, ...]:
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


def _stage_usage(
    envelope: M1AEnvelopeReceipt,
    canary: M1ACanaryReceipt,
) -> tuple[int, bool]:
    probe_attempts = [envelope.initial]
    if envelope.continuation is not None:
        probe_attempts.append(envelope.continuation)

    complete = canary.usage_complete
    total = canary.observed_input_tokens + canary.observed_completion_tokens
    for attempt in probe_attempts:
        if attempt.input_tokens is None or attempt.completion_tokens is None:
            complete = False
            continue
        total += attempt.input_tokens + attempt.completion_tokens
    return total, complete


def _write_json(path: Path, payload: BaseModel) -> None:
    path.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
