from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.model_observation import (
    build_initial_model_observation,
)
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5PublicCaseManifest,
    R5ReferenceCaseReceipt,
    R5ReferenceRunReceipt,
)

R7A_R5_RUN_ID = "r5-glm52-development-reference-20260928-01"
R7A_R5_SUMMARY_SHA256 = "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"
R7A_EFFICIENCY_TARGET = 0.20
R7A_MIN_SIGNAL_SUPPORT = 10
R7A_SIGNAL_PASS_RATE_GAP = 0.25


class R7AContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R7ACase(R7AContract):
    case_id: str
    family: str
    template_id: str
    score_passed: bool
    stop_category: str
    usage_complete: bool
    attempt_count: int = Field(ge=0)
    tool_action_count: int = Field(ge=0)
    inference_tokens: int = Field(ge=0)
    per_attempt_inference_tokens: tuple[int | None, ...]
    initial_approval_count: int = Field(ge=0)
    initial_operation_reference_count: int = Field(ge=0)
    initial_note_count: int = Field(ge=0)
    initial_text_length: int = Field(ge=0)
    first_attempt_multi_read_accepted: bool
    first_attempt_realized_tool_count: int = Field(ge=0)
    first_attempt_tool_names: tuple[str, ...]


class R7ACapMetric(R7AContract):
    max_model_calls: int = Field(ge=1)
    retained_observed_passes: int = Field(ge=0)
    observed_pass_loss_count: int = Field(ge=0)
    complete_usage_case_count: int = Field(ge=0)
    baseline_complete_usage_tokens: int = Field(ge=0)
    simulated_complete_usage_tokens: int = Field(ge=0)
    diagnostic_token_reduction_fraction: float = Field(ge=0.0, le=1.0)


class R7ASignalMetric(R7AContract):
    signal: str
    value: str
    case_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    usage_complete_case_count: int = Field(ge=0)
    complete_usage_inference_tokens: int = Field(ge=0)


class R7AOracleMetric(R7AContract):
    strategy: str
    complete_usage_case_count: int = Field(ge=0)
    baseline_complete_usage_tokens: int = Field(ge=0)
    simulated_complete_usage_tokens: int = Field(ge=0)
    diagnostic_token_reduction_fraction: float = Field(ge=0.0, le=1.0)
    retained_observed_passes: int = Field(ge=0)
    observed_pass_loss_count: int = Field(ge=0)
    policy_valid: bool
    note: str


class R7AReceipt(R7AContract):
    schema_version: Literal["harbourdesk-r7a-feasibility-v1"] = "harbourdesk-r7a-feasibility-v1"
    status: Literal["PASS", "FAIL"]
    feasibility: Literal[
        "NO_STOP_ONLY_HEADROOM",
        "FIXED_BUDGET_CANDIDATE",
        "ADAPTATION_WORTH_INVESTIGATING",
    ]
    r5_run_id: str
    r5_summary_sha256: str
    case_count: int
    score_pass_count: int
    usage_complete_case_count: int
    usage_incomplete_case_ids: tuple[str, ...]
    efficiency_evidence_status: Literal["DIAGNOSTIC_ONLY"]
    efficiency_target_fraction: float
    failure_only_oracle: R7AOracleMetric
    family_oracle: R7AOracleMetric
    universal_cap_metrics: tuple[R7ACapMetric, ...]
    best_zero_observed_pass_loss_cap: R7ACapMetric | None
    observable_signal_metrics: tuple[R7ASignalMetric, ...]
    qualifying_signal_names: tuple[str, ...]
    family_attempt_maxima_for_observed_passes: dict[str, int]
    family_case_counts: dict[str, int]
    family_pass_counts: dict[str, int]
    validation_cases_accessed: Literal[0] = 0
    locked_cases_accessed: Literal[0] = 0
    private_expected_files_accessed: Literal[0] = 0
    integrity_failures: tuple[str, ...]


def analyze_r7a(repo_root: Path) -> R7AReceipt:
    run_dir = repo_root / "runs" / "r5_reference" / R7A_R5_RUN_ID
    summary_path = run_dir / "summary.json"
    failures: list[str] = []

    if not summary_path.is_file():
        raise FileNotFoundError("frozen R5 summary is missing")
    summary_sha = _sha256_file(summary_path)
    if summary_sha != R7A_R5_SUMMARY_SHA256:
        failures.append("r5_summary_sha256_mismatch")

    summary = R5ReferenceRunReceipt.model_validate_json(summary_path.read_text(encoding="utf-8"))
    if summary.run_id != R7A_R5_RUN_ID:
        failures.append("r5_run_id_mismatch")
    if summary.case_count != 90 or len(summary.cases) != 90:
        failures.append("r5_case_count_mismatch")
    if summary.validation_cases_selected != 0:
        failures.append("validation_case_leak")
    if summary.locked_cases_selected != 0:
        failures.append("locked_case_leak")

    public_root = repo_root / "benchmarks" / "harbourdesk" / "r4" / "development"
    cases: list[R7ACase] = []
    for receipt in summary.cases:
        cases.append(
            _build_case(
                public_root=public_root,
                run_dir=run_dir,
                receipt=receipt,
            )
        )

    if len({case.case_id for case in cases}) != 90:
        failures.append("duplicate_case_ids")

    complete_cases = tuple(case for case in cases if case.usage_complete)
    usage_incomplete_ids = tuple(case.case_id for case in cases if not case.usage_complete)
    baseline_complete_tokens = sum(case.inference_tokens for case in complete_cases)
    pass_count = sum(case.score_passed for case in cases)

    failure_only_oracle = _failure_only_oracle(
        cases=tuple(cases),
        baseline_complete_tokens=baseline_complete_tokens,
        score_pass_count=pass_count,
    )
    family_attempt_maxima = _family_pass_attempt_maxima(tuple(cases))
    family_oracle = _family_oracle(
        cases=tuple(cases),
        family_attempt_maxima=family_attempt_maxima,
        baseline_complete_tokens=baseline_complete_tokens,
        score_pass_count=pass_count,
    )

    cap_metrics = tuple(
        _universal_cap_metric(
            cases=tuple(cases),
            max_model_calls=cap,
            baseline_complete_tokens=baseline_complete_tokens,
            score_pass_count=pass_count,
        )
        for cap in range(1, summary.max_model_calls + 1)
    )
    zero_loss_caps = tuple(metric for metric in cap_metrics if metric.observed_pass_loss_count == 0)
    best_zero_loss = (
        max(
            zero_loss_caps,
            key=lambda metric: metric.diagnostic_token_reduction_fraction,
        )
        if zero_loss_caps
        else None
    )

    signal_metrics = _observable_signal_metrics(tuple(cases))
    qualifying_signal_names = _qualifying_signals(signal_metrics)

    if failure_only_oracle.diagnostic_token_reduction_fraction < R7A_EFFICIENCY_TARGET:
        feasibility: Literal[
            "NO_STOP_ONLY_HEADROOM",
            "FIXED_BUDGET_CANDIDATE",
            "ADAPTATION_WORTH_INVESTIGATING",
        ] = "NO_STOP_ONLY_HEADROOM"
    elif (
        best_zero_loss is not None
        and best_zero_loss.diagnostic_token_reduction_fraction >= R7A_EFFICIENCY_TARGET
    ):
        feasibility = "FIXED_BUDGET_CANDIDATE"
    else:
        feasibility = "ADAPTATION_WORTH_INVESTIGATING"

    family_case_counts = Counter(case.family for case in cases)
    family_pass_counts = Counter(case.family for case in cases if case.score_passed)

    return R7AReceipt(
        status="PASS" if not failures else "FAIL",
        feasibility=feasibility,
        r5_run_id=summary.run_id,
        r5_summary_sha256=summary_sha,
        case_count=len(cases),
        score_pass_count=pass_count,
        usage_complete_case_count=len(complete_cases),
        usage_incomplete_case_ids=usage_incomplete_ids,
        efficiency_evidence_status="DIAGNOSTIC_ONLY",
        efficiency_target_fraction=R7A_EFFICIENCY_TARGET,
        failure_only_oracle=failure_only_oracle,
        family_oracle=family_oracle,
        universal_cap_metrics=cap_metrics,
        best_zero_observed_pass_loss_cap=best_zero_loss,
        observable_signal_metrics=signal_metrics,
        qualifying_signal_names=qualifying_signal_names,
        family_attempt_maxima_for_observed_passes=family_attempt_maxima,
        family_case_counts=dict(sorted(family_case_counts.items())),
        family_pass_counts={
            family: family_pass_counts.get(family, 0) for family in sorted(family_case_counts)
        },
        integrity_failures=tuple(failures),
    )


def render_r7a_markdown(receipt: R7AReceipt) -> str:
    oracle_pct = receipt.failure_only_oracle.diagnostic_token_reduction_fraction * 100
    family_pct = receipt.family_oracle.diagnostic_token_reduction_fraction * 100
    lines = [
        "# HarbourDesk R7A Adaptation Feasibility",
        "",
        f"- Integrity: **{receipt.status}**",
        f"- Feasibility: **{receipt.feasibility}**",
        f"- Frozen development passes: **{receipt.score_pass_count}/{receipt.case_count}**",
        (
            "- Usage-complete diagnostic subset: "
            f"**{receipt.usage_complete_case_count}/{receipt.case_count}**"
        ),
        "- Efficiency evidence: **DIAGNOSTIC ONLY**",
        "",
        "## Headroom",
        "",
        (f"- Failure-only oracle reduction: **{oracle_pct:.2f}%** on the usage-complete subset."),
        (f"- Family-label oracle reduction: **{family_pct:.2f}%** on the usage-complete subset."),
        "",
        "The failure-only oracle is deliberately invalid as a production policy because "
        "it uses final score labels. It is an upper-bound diagnostic for stop-only "
        "adaptation after the first model call.",
        "",
        "The family oracle is also not a valid production policy. Family labels are "
        "benchmark metadata, not runtime routing inputs.",
        "",
        "## Universal model-call caps",
        "",
        "| Cap | Retained passes | Observed pass loss | Diagnostic token reduction |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for cap_metric in receipt.universal_cap_metrics:
        lines.append(
            f"| {cap_metric.max_model_calls} | "
            f"{cap_metric.retained_observed_passes} | "
            f"{cap_metric.observed_pass_loss_count} | "
            f"{cap_metric.diagnostic_token_reduction_fraction * 100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Observable signal diagnostics",
            "",
            "| Signal | Value | Cases | Passes | Pass rate |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for signal_metric in receipt.observable_signal_metrics:
        lines.append(
            f"| {signal_metric.signal} | `{signal_metric.value}` | "
            f"{signal_metric.case_count} | {signal_metric.pass_count} | "
            f"{signal_metric.pass_rate * 100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "R7A does not train or implement a router. It does not access validation, "
            "locked, or private expected files. Outcome/family labels are used only "
            "for retrospective diagnostics and are prohibited as candidate-policy inputs.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_case(
    *,
    public_root: Path,
    run_dir: Path,
    receipt: R5ReferenceCaseReceipt,
) -> R7ACase:
    case_dir = public_root / receipt.case_id
    public = R5PublicCaseManifest.model_validate_json(
        (case_dir / "case.json").read_text(encoding="utf-8")
    )
    state = HarbourDeskVisibleState.model_validate_json(
        (case_dir / public.initial_state_file).read_text(encoding="utf-8")
    )
    ticket = next(item for item in state.tickets if item.ticket_id == public.ticket_id)
    observation = build_initial_model_observation(
        state=state,
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.ticket_id,
    )
    trace_path = run_dir / receipt.case_id / "trace.jsonl"
    attempt_tokens, first_attempt = _trace_features(trace_path)

    if len(attempt_tokens) != receipt.attempt_count:
        raise ValueError(f"{receipt.case_id}: trace attempt count does not match receipt")

    return R7ACase(
        case_id=receipt.case_id,
        family=receipt.family,
        template_id=receipt.template_id,
        score_passed=receipt.score_passed,
        stop_category=receipt.stop_category.value,
        usage_complete=receipt.usage_complete,
        attempt_count=receipt.attempt_count,
        tool_action_count=receipt.tool_action_count,
        inference_tokens=(receipt.observed_input_tokens + receipt.observed_completion_tokens),
        per_attempt_inference_tokens=attempt_tokens,
        initial_approval_count=len(observation.approvals),
        initial_operation_reference_count=len(observation.operation_references),
        initial_note_count=len(observation.ticket.notes),
        initial_text_length=len(observation.ticket.initial_text),
        first_attempt_multi_read_accepted=first_attempt[0],
        first_attempt_realized_tool_count=first_attempt[1],
        first_attempt_tool_names=first_attempt[2],
    )


def _trace_features(
    path: Path,
) -> tuple[
    tuple[int | None, ...],
    tuple[bool, int, tuple[str, ...]],
]:
    attempts: list[int | None] = []
    first_attempt_multi_read_accepted = False
    first_attempt_tool_names: list[str] = []
    current_attempt = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        event_name = event.get("event")

        if event_name == "attempt_started":
            current_attempt = int(event["attempt_index"])
            continue

        if event_name == "attempt_finished":
            attempt = event["attempt"]
            usage = attempt.get("usage")
            usage_status = attempt.get("usage_status")
            if (
                usage_status == "observed"
                and isinstance(usage, dict)
                and usage.get("input_tokens") is not None
                and usage.get("completion_tokens") is not None
            ):
                attempts.append(int(usage["input_tokens"]) + int(usage["completion_tokens"]))
            else:
                attempts.append(None)
            continue

        if (
            current_attempt == 1
            and event_name == "multi_tool_batch_preflight"
            and event.get("accepted") is True
        ):
            first_attempt_multi_read_accepted = True
            continue

        if current_attempt == 1 and event_name == "tool_action_finished":
            action = event.get("action")
            if isinstance(action, dict):
                first_attempt_tool_names.append(str(action.get("tool", "")))

    return (
        tuple(attempts),
        (
            first_attempt_multi_read_accepted,
            len(first_attempt_tool_names),
            tuple(first_attempt_tool_names),
        ),
    )


def _failure_only_oracle(
    *,
    cases: tuple[R7ACase, ...],
    baseline_complete_tokens: int,
    score_pass_count: int,
) -> R7AOracleMetric:
    simulated = 0
    for case in cases:
        if not case.usage_complete:
            continue
        if case.score_passed:
            simulated += case.inference_tokens
        else:
            simulated += _tokens_through_attempt(case, 1)

    return R7AOracleMetric(
        strategy="failure_only_after_first_attempt",
        complete_usage_case_count=sum(case.usage_complete for case in cases),
        baseline_complete_usage_tokens=baseline_complete_tokens,
        simulated_complete_usage_tokens=simulated,
        diagnostic_token_reduction_fraction=_reduction(
            baseline_complete_tokens,
            simulated,
        ),
        retained_observed_passes=score_pass_count,
        observed_pass_loss_count=0,
        policy_valid=False,
        note=(
            "Upper bound only: uses final score labels and therefore cannot "
            "be implemented as a production routing policy."
        ),
    )


def _family_pass_attempt_maxima(
    cases: tuple[R7ACase, ...],
) -> dict[str, int]:
    maxima: dict[str, int] = {}
    for family in sorted({case.family for case in cases}):
        passed = tuple(
            case.attempt_count for case in cases if case.family == family and case.score_passed
        )
        maxima[family] = max(passed) if passed else 1
    return maxima


def _family_oracle(
    *,
    cases: tuple[R7ACase, ...],
    family_attempt_maxima: dict[str, int],
    baseline_complete_tokens: int,
    score_pass_count: int,
) -> R7AOracleMetric:
    simulated = 0
    pass_loss = 0
    for case in cases:
        cap = family_attempt_maxima[case.family]
        if case.score_passed and case.attempt_count > cap:
            pass_loss += 1
        if case.usage_complete:
            simulated += _tokens_through_attempt(case, cap)

    return R7AOracleMetric(
        strategy="family_specific_pass_preserving_caps",
        complete_usage_case_count=sum(case.usage_complete for case in cases),
        baseline_complete_usage_tokens=baseline_complete_tokens,
        simulated_complete_usage_tokens=simulated,
        diagnostic_token_reduction_fraction=_reduction(
            baseline_complete_tokens,
            simulated,
        ),
        retained_observed_passes=score_pass_count - pass_loss,
        observed_pass_loss_count=pass_loss,
        policy_valid=False,
        note=("Diagnostic only: benchmark family is not an allowed runtime routing input."),
    )


def _universal_cap_metric(
    *,
    cases: tuple[R7ACase, ...],
    max_model_calls: int,
    baseline_complete_tokens: int,
    score_pass_count: int,
) -> R7ACapMetric:
    pass_loss = sum(case.score_passed and case.attempt_count > max_model_calls for case in cases)
    simulated = sum(
        _tokens_through_attempt(case, max_model_calls) for case in cases if case.usage_complete
    )
    return R7ACapMetric(
        max_model_calls=max_model_calls,
        retained_observed_passes=score_pass_count - pass_loss,
        observed_pass_loss_count=pass_loss,
        complete_usage_case_count=sum(case.usage_complete for case in cases),
        baseline_complete_usage_tokens=baseline_complete_tokens,
        simulated_complete_usage_tokens=simulated,
        diagnostic_token_reduction_fraction=_reduction(
            baseline_complete_tokens,
            simulated,
        ),
    )


def _observable_signal_metrics(
    cases: tuple[R7ACase, ...],
) -> tuple[R7ASignalMetric, ...]:
    rows: list[R7ASignalMetric] = []
    partitions: dict[str, Callable[[R7ACase], str]] = {
        "initial_approval_count": lambda case: str(case.initial_approval_count),
        "initial_operation_reference_count": (
            lambda case: str(case.initial_operation_reference_count)
        ),
        "initial_note_count": lambda case: str(case.initial_note_count),
        "first_attempt_multi_read_accepted": (
            lambda case: str(case.first_attempt_multi_read_accepted).lower()
        ),
        "first_attempt_realized_tool_count": (
            lambda case: str(case.first_attempt_realized_tool_count)
        ),
        "first_attempt_tool_signature": (
            lambda case: ",".join(case.first_attempt_tool_names) or "<none>"
        ),
    }

    for signal, value_fn in partitions.items():
        grouped: dict[str, list[R7ACase]] = defaultdict(list)
        for case in cases:
            grouped[value_fn(case)].append(case)
        for value, group in sorted(grouped.items()):
            usage_complete = tuple(case for case in group if case.usage_complete)
            pass_count = sum(case.score_passed for case in group)
            rows.append(
                R7ASignalMetric(
                    signal=signal,
                    value=value,
                    case_count=len(group),
                    pass_count=pass_count,
                    pass_rate=pass_count / len(group),
                    usage_complete_case_count=len(usage_complete),
                    complete_usage_inference_tokens=sum(
                        case.inference_tokens for case in usage_complete
                    ),
                )
            )
    return tuple(rows)


def _qualifying_signals(
    metrics: tuple[R7ASignalMetric, ...],
) -> tuple[str, ...]:
    grouped: dict[str, list[R7ASignalMetric]] = defaultdict(list)
    for metric in metrics:
        if metric.case_count >= R7A_MIN_SIGNAL_SUPPORT:
            grouped[metric.signal].append(metric)

    qualifying: list[str] = []
    for signal, groups in sorted(grouped.items()):
        if len(groups) < 2:
            continue
        rates = [group.pass_rate for group in groups]
        if max(rates) - min(rates) >= R7A_SIGNAL_PASS_RATE_GAP:
            qualifying.append(signal)
    return tuple(qualifying)


def _tokens_through_attempt(case: R7ACase, cap: int) -> int:
    tokens = case.per_attempt_inference_tokens[:cap]
    if any(value is None for value in tokens):
        raise ValueError(f"{case.case_id}: incomplete usage entered complete-usage simulation")
    return sum(int(value) for value in tokens if value is not None)


def _reduction(baseline: int, simulated: int) -> float:
    if baseline <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (simulated / baseline)))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
