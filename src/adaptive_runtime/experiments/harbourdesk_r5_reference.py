from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import ProviderProtocol
from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.read_tools import ReadToolName
from adaptive_runtime.environment.runtime import HarbourDeskEnvironment
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import WriteToolName
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import CaseScore, score_case
from adaptive_runtime.experiments.harbourdesk_m3d import M3D_BUDGET
from adaptive_runtime.experiments.harbourdesk_r5 import (
    R5_MODEL_ID,
    R5_PROFILE_NAME,
    R5DevelopmentReferenceManifest,
    load_r5_manifest,
)
from adaptive_runtime.providers.base import ProviderAdapter
from adaptive_runtime.runtime.harbourdesk_live import (
    LiveModelProfile,
    LiveStopCategory,
    ProviderAttemptTrace,
    UsageObservationStatus,
    run_live_harbourdesk,
)
from adaptive_runtime.runtime.trace import JsonlTraceSink


class R5ReferenceError(RuntimeError):
    """Raised when the frozen R5 development reference cannot run safely."""


class R5ReferenceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class R5PublicCaseManifest(R5ReferenceContract):
    schema_version: str
    task_ref: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    frozen_at: str
    initial_state_file: str = Field(min_length=1, max_length=200)
    documents_file: str = Field(min_length=1, max_length=200)


class R5ReferenceCase(R5ReferenceContract):
    case_id: str
    family: str
    template_id: str
    task_ref: str
    tenant_id: str
    ticket_id: str
    initial: HarbourDeskVisibleState
    rules: HarbourDeskBusinessRules
    expected: ExpectedCaseOutcome


class R5ReferenceCaseReceipt(R5ReferenceContract):
    schema_version: str = "harbourdesk-r5-case-v1"
    case_id: str
    family: str
    template_id: str
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
    score_passed: bool
    matched_predicate_index: int | None
    scoring_failures: tuple[str, ...]
    accepted_multi_read_batch_count: int = Field(ge=0)
    rejected_multi_tool_batch_count: int = Field(ge=0)
    deterministic_control_violation_count: int = Field(ge=0)
    realized_write_from_multi_tool_batch_count: int = Field(ge=0)
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class R5GroupMetric(R5ReferenceContract):
    case_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    inference_tokens: int = Field(ge=0)


class R5ReferenceRunReceipt(R5ReferenceContract):
    schema_version: str = "harbourdesk-r5-development-reference-run-v1"
    status: str
    run_id: str
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    development_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str
    profile_name: str
    max_model_calls: int
    max_tool_actions: int
    trajectory_deadline_seconds: float
    request_deadline_seconds: float
    max_completion_tokens: int
    case_count: int
    cases: tuple[R5ReferenceCaseReceipt, ...]
    score_pass_count: int
    score_pass_rate: float
    usage_complete: bool
    observed_input_tokens: int
    observed_completion_tokens: int
    observed_reasoning_tokens: int
    observed_cached_input_tokens: int
    observed_inference_tokens: int
    observed_provider_latency_ms: int
    observed_tokens_per_verified_success: float | None
    stop_category_counts: dict[str, int]
    scoring_failure_counts: dict[str, int]
    family_metrics: dict[str, R5GroupMetric]
    template_metrics: dict[str, R5GroupMetric]
    accepted_multi_read_batch_count: int
    rejected_multi_tool_batch_count: int
    deterministic_control_violation_count: int
    realized_write_from_multi_tool_batch_count: int
    validation_cases_selected: int = 0
    locked_cases_selected: int = 0


def load_r5_reference_inputs(repo_root: Path) -> tuple[R5ReferenceCase, ...]:
    manifest = load_r5_manifest(repo_root)
    rules = HarbourDeskBusinessRules.load(
        repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    )
    benchmark_root = repo_root / Path(manifest.benchmark_root)
    private_root = repo_root / Path(manifest.private_expected_root)

    inputs: list[R5ReferenceCase] = []
    for entry in manifest.entries:
        case_dir = benchmark_root / entry.case_id
        public = R5PublicCaseManifest.model_validate_json(
            (case_dir / "case.json").read_text(encoding="utf-8")
        )
        initial = HarbourDeskVisibleState.model_validate_json(
            (case_dir / public.initial_state_file).read_text(encoding="utf-8")
        )
        ticket = next(
            (item for item in initial.tickets if item.ticket_id == public.ticket_id),
            None,
        )
        if ticket is None:
            raise R5ReferenceError(f"{entry.case_id}: terminal ticket missing from initial state")

        expected = ExpectedCaseOutcome.model_validate_json(
            (private_root / entry.case_id / "expected.json").read_text(encoding="utf-8")
        )
        if expected.case_id != entry.case_id:
            raise R5ReferenceError(f"{entry.case_id}: private expected case identity mismatch")
        if expected.terminal_ticket_id != public.ticket_id:
            raise R5ReferenceError(f"{entry.case_id}: private expected terminal ticket mismatch")

        inputs.append(
            R5ReferenceCase(
                case_id=entry.case_id,
                family=entry.family,
                template_id=entry.template_id,
                task_ref=public.task_ref,
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.ticket_id,
                initial=initial,
                rules=rules,
                expected=expected,
            )
        )

    result = tuple(inputs)
    _validate_case_order(result, manifest)
    return result


def run_r5_reference(
    *,
    repo_root: Path,
    inputs: tuple[R5ReferenceCase, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    candidate_commit: str,
    evidence_dir: Path,
) -> R5ReferenceRunReceipt:
    manifest = load_r5_manifest(repo_root)
    _validate_profile(profile)
    _validate_case_order(inputs, manifest)

    if evidence_dir.exists():
        raise FileExistsError(f"R5 evidence directory already exists: {evidence_dir}")
    evidence_dir.mkdir(parents=True, exist_ok=False)

    development_manifest_path = (
        repo_root / "benchmarks" / "harbourdesk" / "r5" / "development_reference_manifest_v1.json"
    )
    development_manifest_sha256 = _sha256_file(development_manifest_path)

    run_manifest = {
        "schema_version": "harbourdesk-r5-live-manifest-v1",
        "run_id": run_id,
        "candidate_commit": candidate_commit,
        "development_manifest_sha256": development_manifest_sha256,
        "model_id": profile.model_id,
        "profile_name": profile.profile_name,
        "protocol": profile.protocol.value,
        "max_model_calls": M3D_BUDGET.max_model_calls,
        "max_tool_actions": M3D_BUDGET.max_tool_actions,
        "trajectory_deadline_seconds": M3D_BUDGET.trajectory_deadline_seconds,
        "request_deadline_seconds": M3D_BUDGET.request_deadline_seconds,
        "max_completion_tokens": M3D_BUDGET.max_completion_tokens,
        "case_order": list(manifest.case_order),
    }
    (evidence_dir / "manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipts: list[R5ReferenceCaseReceipt] = []
    for item in inputs:
        case_dir = evidence_dir / item.case_id
        case_dir.mkdir(parents=False, exist_ok=False)
        receipts.append(
            _run_reference_case(
                item=item,
                provider=provider,
                profile=profile,
                suite_run_id=run_id,
                trace_path=case_dir / "trace.jsonl",
            )
        )
        (case_dir / "receipt.json").write_text(
            receipts[-1].model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    suite = _suite_receipt(
        run_id=run_id,
        candidate_commit=candidate_commit,
        development_manifest_sha256=development_manifest_sha256,
        profile=profile,
        cases=tuple(receipts),
    )
    (evidence_dir / "summary.json").write_text(
        suite.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return suite


def _run_reference_case(
    *,
    item: R5ReferenceCase,
    provider: ProviderAdapter,
    profile: EndpointProfile,
    suite_run_id: str,
    trace_path: Path,
) -> R5ReferenceCaseReceipt:
    case_run_id = f"{suite_run_id}-{item.case_id}"

    with HarbourDeskStore.in_memory() as store:
        store.initialize(item.initial)
        environment = HarbourDeskEnvironment(
            store=store,
            rules=item.rules,
            tenant_id=item.tenant_id,
            ticket_id=item.ticket_id,
        )
        run = run_live_harbourdesk(
            provider=provider,
            environment=environment,
            run_id=case_run_id,
            model_profile=LiveModelProfile(
                model_id=profile.model_id,
                protocol=profile.protocol,
                thinking=profile.thinking_control,
                profile_version="harbourdesk-r5-development-reference-v1",
            ),
            budget=M3D_BUDGET,
            trace_sink=JsonlTraceSink(trace_path),
        )

    score = score_case(item.initial, run.final_state, item.expected)
    usage_complete, totals = _usage_totals(run.trace.attempts)
    batch = _collect_trace_control_evidence(trace_path)

    return R5ReferenceCaseReceipt(
        case_id=item.case_id,
        family=item.family,
        template_id=item.template_id,
        task_ref=item.task_ref,
        ticket_id=item.ticket_id,
        run_id=case_run_id,
        model_id=profile.model_id,
        stop_category=run.trace.stop_category,
        terminal_reached=(run.trace.stop_category is LiveStopCategory.TICKET_TERMINAL),
        attempt_count=len(run.trace.attempts),
        tool_action_count=len(run.trace.tool_actions),
        usage_complete=usage_complete,
        observed_input_tokens=totals[0],
        observed_completion_tokens=totals[1],
        observed_reasoning_tokens=totals[2],
        observed_cached_input_tokens=totals[3],
        observed_provider_latency_ms=sum(attempt.latency_ms or 0 for attempt in run.trace.attempts),
        score_passed=score.passed,
        matched_predicate_index=score.matched_predicate_index,
        scoring_failures=_score_failures(score),
        accepted_multi_read_batch_count=batch[0],
        rejected_multi_tool_batch_count=batch[1],
        deterministic_control_violation_count=batch[2],
        realized_write_from_multi_tool_batch_count=batch[3],
        final_state_sha256=run.trace.final_state_sha256,
        trace_sha256=_sha256_file(trace_path),
    )


def _suite_receipt(
    *,
    run_id: str,
    candidate_commit: str,
    development_manifest_sha256: str,
    profile: EndpointProfile,
    cases: tuple[R5ReferenceCaseReceipt, ...],
) -> R5ReferenceRunReceipt:
    case_count = len(cases)
    pass_count = sum(1 for case in cases if case.score_passed)
    usage_complete = bool(cases) and all(case.usage_complete for case in cases)

    input_tokens = sum(case.observed_input_tokens for case in cases)
    completion_tokens = sum(case.observed_completion_tokens for case in cases)
    reasoning_tokens = sum(case.observed_reasoning_tokens for case in cases)
    cached_tokens = sum(case.observed_cached_input_tokens for case in cases)
    inference_tokens = input_tokens + completion_tokens
    latency_ms = sum(case.observed_provider_latency_ms for case in cases)

    tokens_per_success: float | None = None
    if usage_complete and pass_count > 0:
        tokens_per_success = inference_tokens / pass_count

    return R5ReferenceRunReceipt(
        status="COMPLETE",
        run_id=run_id,
        candidate_commit=candidate_commit,
        development_manifest_sha256=development_manifest_sha256,
        model_id=profile.model_id,
        profile_name=profile.profile_name,
        max_model_calls=M3D_BUDGET.max_model_calls,
        max_tool_actions=M3D_BUDGET.max_tool_actions,
        trajectory_deadline_seconds=M3D_BUDGET.trajectory_deadline_seconds,
        request_deadline_seconds=M3D_BUDGET.request_deadline_seconds,
        max_completion_tokens=M3D_BUDGET.max_completion_tokens,
        case_count=case_count,
        cases=cases,
        score_pass_count=pass_count,
        score_pass_rate=(pass_count / case_count if case_count else 0.0),
        usage_complete=usage_complete,
        observed_input_tokens=input_tokens,
        observed_completion_tokens=completion_tokens,
        observed_reasoning_tokens=reasoning_tokens,
        observed_cached_input_tokens=cached_tokens,
        observed_inference_tokens=inference_tokens,
        observed_provider_latency_ms=latency_ms,
        observed_tokens_per_verified_success=tokens_per_success,
        stop_category_counts=dict(
            sorted(Counter(case.stop_category.value for case in cases).items())
        ),
        scoring_failure_counts=dict(
            sorted(Counter(failure for case in cases for failure in case.scoring_failures).items())
        ),
        family_metrics=_group_metrics(cases, key="family"),
        template_metrics=_group_metrics(cases, key="template"),
        accepted_multi_read_batch_count=sum(case.accepted_multi_read_batch_count for case in cases),
        rejected_multi_tool_batch_count=sum(case.rejected_multi_tool_batch_count for case in cases),
        deterministic_control_violation_count=sum(
            case.deterministic_control_violation_count for case in cases
        ),
        realized_write_from_multi_tool_batch_count=sum(
            case.realized_write_from_multi_tool_batch_count for case in cases
        ),
    )


def _group_metrics(
    cases: tuple[R5ReferenceCaseReceipt, ...],
    *,
    key: str,
) -> dict[str, R5GroupMetric]:
    groups: dict[str, list[R5ReferenceCaseReceipt]] = {}
    for case in cases:
        group_key = case.family if key == "family" else case.template_id
        groups.setdefault(group_key, []).append(case)

    return {
        group_key: R5GroupMetric(
            case_count=len(group),
            pass_count=sum(1 for item in group if item.score_passed),
            pass_rate=(sum(1 for item in group if item.score_passed) / len(group)),
            inference_tokens=sum(
                item.observed_input_tokens + item.observed_completion_tokens for item in group
            ),
        )
        for group_key, group in sorted(groups.items())
    }


def _collect_trace_control_evidence(
    trace_path: Path,
) -> tuple[int, int, int, int]:
    accepted_batches = 0
    rejected_batches = 0
    violations = 0
    realized_batch_writes = 0
    accepted_batch_active = False

    read_names = {tool.value for tool in ReadToolName}
    write_names = {tool.value for tool in WriteToolName}

    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        event_name = event.get("event")

        if event_name == "attempt_started":
            accepted_batch_active = False
            continue

        if event_name == "multi_tool_batch_preflight":
            accepted = event.get("accepted") is True
            tool_names = tuple(str(name) for name in event.get("tool_names", []))
            accepted_batch_active = accepted
            if accepted:
                accepted_batches += 1
                if any(name not in read_names for name in tool_names):
                    violations += 1
            else:
                rejected_batches += 1
            continue

        if event_name == "tool_action_finished" and accepted_batch_active:
            action = event.get("action")
            if not isinstance(action, dict):
                violations += 1
                continue
            tool_name = str(action.get("tool", ""))
            if tool_name in write_names:
                realized_batch_writes += 1
                violations += 1
            elif tool_name not in read_names:
                violations += 1
            continue

        if event_name == "run_finished":
            accepted_batch_active = False

    return (
        accepted_batches,
        rejected_batches,
        violations,
        realized_batch_writes,
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


def _validate_case_order(
    inputs: tuple[R5ReferenceCase, ...],
    manifest: R5DevelopmentReferenceManifest,
) -> None:
    case_order = tuple(item.case_id for item in inputs)
    if case_order != manifest.case_order:
        raise R5ReferenceError(
            "R5 live inputs must exactly match the frozen 90-case manifest order"
        )
    if len(inputs) != 90:
        raise R5ReferenceError("R5 live reference requires exactly 90 cases")


def _validate_profile(profile: EndpointProfile) -> None:
    if profile.profile_name != R5_PROFILE_NAME:
        raise R5ReferenceError(
            f"R5 is frozen to profile {R5_PROFILE_NAME}; selected {profile.profile_name}"
        )
    if profile.model_id != R5_MODEL_ID:
        raise R5ReferenceError(f"R5 is frozen to model {R5_MODEL_ID}; selected {profile.model_id}")
    if profile.protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        raise R5ReferenceError("R5 requires the qualified OpenAI-compatible profile")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
