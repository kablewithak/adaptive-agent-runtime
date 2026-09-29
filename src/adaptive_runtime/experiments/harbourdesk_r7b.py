from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
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
from adaptive_runtime.experiments.harbourdesk_r7a import R7AReceipt

R7B_R5_RUN_ID = "r5-glm52-development-reference-20260928-01"
R7B_R5_SUMMARY_SHA256 = "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"
R7B_R7A_COMMIT = "5fcb3ec2175d8b10c2708b3a45a7e1b4e7e2a56d"
R7B_BASELINE_MAX_MODEL_CALLS = 8
R7B_MIN_BUCKET_SUPPORT = 10
R7B_EFFICIENCY_TARGET = 0.20

SignalName = Literal[
    "initial_operation_reference_count",
    "first_attempt_realized_tool_count",
    "first_attempt_tool_signature",
]


class R7BContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R7BPolicySpec(R7BContract):
    name: str
    signals: tuple[SignalName, ...]


class R7BCase(R7BContract):
    case_id: str
    family: str
    template_id: str
    score_passed: bool
    usage_complete: bool
    attempt_count: int = Field(ge=0)
    inference_tokens: int = Field(ge=0)
    per_attempt_inference_tokens: tuple[int | None, ...]
    initial_operation_reference_count: int = Field(ge=0)
    first_attempt_realized_tool_count: int = Field(ge=0)
    first_attempt_tool_signature: str


class R7BFoldMetric(R7BContract):
    held_out_template_id: str
    case_count: int
    pass_count: int
    observed_pass_loss_count: int
    complete_usage_case_count: int
    baseline_complete_usage_tokens: int
    simulated_complete_usage_tokens: int
    diagnostic_token_reduction_fraction: float
    adapted_case_count: int


class R7BCandidateMetric(R7BContract):
    policy_name: str
    signals: tuple[SignalName, ...]
    fold_count: int
    case_count: int
    pass_count: int
    observed_pass_loss_count: int
    complete_usage_case_count: int
    baseline_complete_usage_tokens: int
    simulated_complete_usage_tokens: int
    diagnostic_token_reduction_fraction: float
    adapted_case_count: int
    qualifies: bool
    folds: tuple[R7BFoldMetric, ...]


class R7BPolicyEntry(R7BContract):
    signal_values: dict[str, str]
    max_model_calls: int = Field(ge=1, le=R7B_BASELINE_MAX_MODEL_CALLS)
    training_support: int = Field(ge=R7B_MIN_BUCKET_SUPPORT)
    training_pass_support: int = Field(ge=1)


class R7BSelectedPolicy(R7BContract):
    schema_version: Literal["harbourdesk-r7b-selected-policy-v1"] = (
        "harbourdesk-r7b-selected-policy-v1"
    )
    policy_name: str
    signals: tuple[SignalName, ...]
    decision_point: Literal["after_first_model_attempt"] = "after_first_model_attempt"
    baseline_max_model_calls: Literal[8] = 8
    fallback_max_model_calls: Literal[8] = 8
    minimum_training_bucket_support: Literal[10] = 10
    cross_validated_diagnostic_token_reduction_fraction: float
    cross_validated_observed_pass_loss_count: int
    entries: tuple[R7BPolicyEntry, ...]


class R7BReceipt(R7BContract):
    schema_version: Literal["harbourdesk-r7b-policy-discovery-v1"] = (
        "harbourdesk-r7b-policy-discovery-v1"
    )
    status: Literal["PASS", "FAIL"]
    decision: Literal["POLICY_CANDIDATE", "NO_POLICY_QUALIFIED"]
    candidate_commit: str
    r7a_commit: str
    r7a_summary_sha256: str
    r5_summary_sha256: str
    case_count: int
    template_count: int
    pass_count: int
    usage_complete_case_count: int
    usage_incomplete_case_ids: tuple[str, ...]
    allowed_signals: tuple[SignalName, ...]
    candidates: tuple[R7BCandidateMetric, ...]
    selected_policy: R7BSelectedPolicy | None
    selected_policy_name: str | None
    selected_policy_cv_reduction_fraction: float | None
    selected_policy_cv_pass_loss_count: int | None
    validation_cases_accessed: Literal[0] = 0
    locked_cases_accessed: Literal[0] = 0
    private_expected_files_accessed: Literal[0] = 0
    external_provider_calls: Literal[0] = 0
    live_model_calls: Literal[0] = 0
    runtime_mutations: Literal[0] = 0
    integrity_failures: tuple[str, ...]


POLICY_SPECS: tuple[R7BPolicySpec, ...] = (
    R7BPolicySpec(
        name="opref_count",
        signals=("initial_operation_reference_count",),
    ),
    R7BPolicySpec(
        name="first_tool_count",
        signals=("first_attempt_realized_tool_count",),
    ),
    R7BPolicySpec(
        name="first_tool_signature",
        signals=("first_attempt_tool_signature",),
    ),
    R7BPolicySpec(
        name="opref_plus_first_tool_count",
        signals=(
            "initial_operation_reference_count",
            "first_attempt_realized_tool_count",
        ),
    ),
    R7BPolicySpec(
        name="opref_plus_first_tool_signature",
        signals=(
            "initial_operation_reference_count",
            "first_attempt_tool_signature",
        ),
    ),
)


def analyze_r7b(
    repo_root: Path,
    *,
    candidate_commit: str,
    expected_r7a_summary_sha256: str,
) -> R7BReceipt:
    failures: list[str] = []

    r7a_path = repo_root / "runs" / "r7a_feasibility" / "summary.json"
    if not r7a_path.is_file():
        raise FileNotFoundError("R7A summary is missing")
    r7a_sha = _sha256_file(r7a_path)
    if r7a_sha != expected_r7a_summary_sha256.lower():
        failures.append("r7a_summary_sha256_mismatch")

    r7a = R7AReceipt.model_validate_json(r7a_path.read_text(encoding="utf-8"))
    expected_signals = {
        "initial_operation_reference_count",
        "first_attempt_realized_tool_count",
        "first_attempt_tool_signature",
    }
    if r7a.status != "PASS":
        failures.append("r7a_status_not_pass")
    if r7a.feasibility != "ADAPTATION_WORTH_INVESTIGATING":
        failures.append("r7a_feasibility_mismatch")
    if set(r7a.qualifying_signal_names) != expected_signals:
        failures.append("r7a_qualifying_signal_set_mismatch")
    if (
        r7a.validation_cases_accessed != 0
        or r7a.locked_cases_accessed != 0
        or r7a.private_expected_files_accessed != 0
    ):
        failures.append("r7a_evidence_boundary_violation")

    run_dir = repo_root / "runs" / "r5_reference" / R7B_R5_RUN_ID
    r5_summary_path = run_dir / "summary.json"
    r5_sha = _sha256_file(r5_summary_path)
    if r5_sha != R7B_R5_SUMMARY_SHA256:
        failures.append("r5_summary_sha256_mismatch")

    r5 = R5ReferenceRunReceipt.model_validate_json(r5_summary_path.read_text(encoding="utf-8"))
    if r5.case_count != 90 or len(r5.cases) != 90:
        failures.append("r5_case_count_mismatch")
    if r5.validation_cases_selected != 0 or r5.locked_cases_selected != 0:
        failures.append("r5_non_development_case_leak")

    cases = _load_cases(repo_root, run_dir, r5.cases)
    template_counts = Counter(case.template_id for case in cases)
    if len(template_counts) != 18 or set(template_counts.values()) != {5}:
        failures.append("development_template_shape_mismatch")

    metrics = tuple(_cross_validate_policy(cases, spec) for spec in POLICY_SPECS)
    qualifiers = tuple(metric for metric in metrics if metric.qualifies)

    selected_metric = (
        sorted(
            qualifiers,
            key=lambda metric: (
                -metric.diagnostic_token_reduction_fraction,
                len(metric.signals),
                metric.policy_name,
            ),
        )[0]
        if qualifiers
        else None
    )
    selected_policy = (
        _fit_selected_policy(cases, selected_metric) if selected_metric is not None else None
    )

    usage_incomplete_ids = tuple(case.case_id for case in cases if not case.usage_complete)
    decision: Literal["POLICY_CANDIDATE", "NO_POLICY_QUALIFIED"] = (
        "POLICY_CANDIDATE" if selected_policy is not None else "NO_POLICY_QUALIFIED"
    )

    return R7BReceipt(
        status="PASS" if not failures else "FAIL",
        decision=decision,
        candidate_commit=candidate_commit,
        r7a_commit=R7B_R7A_COMMIT,
        r7a_summary_sha256=r7a_sha,
        r5_summary_sha256=r5_sha,
        case_count=len(cases),
        template_count=len(template_counts),
        pass_count=sum(case.score_passed for case in cases),
        usage_complete_case_count=sum(case.usage_complete for case in cases),
        usage_incomplete_case_ids=usage_incomplete_ids,
        allowed_signals=(
            "initial_operation_reference_count",
            "first_attempt_realized_tool_count",
            "first_attempt_tool_signature",
        ),
        candidates=metrics,
        selected_policy=selected_policy,
        selected_policy_name=(None if selected_metric is None else selected_metric.policy_name),
        selected_policy_cv_reduction_fraction=(
            None if selected_metric is None else selected_metric.diagnostic_token_reduction_fraction
        ),
        selected_policy_cv_pass_loss_count=(
            None if selected_metric is None else selected_metric.observed_pass_loss_count
        ),
        integrity_failures=tuple(failures),
    )


def render_r7b_markdown(receipt: R7BReceipt) -> str:
    lines = [
        "# HarbourDesk R7B Policy Discovery",
        "",
        f"- Integrity: **{receipt.status}**",
        f"- Decision: **{receipt.decision}**",
        f"- Development cases: **{receipt.case_count}**",
        f"- Development templates: **{receipt.template_count}**",
        f"- Frozen passes: **{receipt.pass_count}**",
        "",
        "## Template-held-out candidate results",
        "",
        "| Policy | Signals | Pass loss | Diagnostic reduction | Qualifies |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for candidate in receipt.candidates:
        lines.append(
            f"| `{candidate.policy_name}` | "
            f"`{','.join(candidate.signals)}` | "
            f"{candidate.observed_pass_loss_count} | "
            f"{candidate.diagnostic_token_reduction_fraction * 100:.2f}% | "
            f"{'yes' if candidate.qualifies else 'no'} |"
        )

    lines.extend(["", "## Selected policy", ""])
    if receipt.selected_policy is None:
        lines.append(
            "No bounded runtime-visible policy met both zero observed pass loss "
            "and the 20% diagnostic token-reduction screen."
        )
    else:
        policy = receipt.selected_policy
        lines.extend(
            [
                f"- Name: `{policy.policy_name}`",
                f"- Signals: `{','.join(policy.signals)}`",
                (
                    "- Template-held-out diagnostic reduction: "
                    f"**{policy.cross_validated_diagnostic_token_reduction_fraction * 100:.2f}%**"
                ),
                (
                    "- Template-held-out observed pass losses: "
                    f"**{policy.cross_validated_observed_pass_loss_count}**"
                ),
                f"- Frozen table entries: **{len(policy.entries)}**",
            ]
        )

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "R7B is development-only policy discovery. Token savings remain diagnostic "
            "because the R5 reference has one usage-incomplete provider-error case. "
            "No validation or locked cases are accessed, and no runtime is mutated.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_cases(
    repo_root: Path,
    run_dir: Path,
    receipts: tuple[R5ReferenceCaseReceipt, ...],
) -> tuple[R7BCase, ...]:
    public_root = repo_root / "benchmarks" / "harbourdesk" / "r4" / "development"
    cases: list[R7BCase] = []

    for receipt in receipts:
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
        attempt_tokens, first_tools = _trace_features(run_dir / receipt.case_id / "trace.jsonl")
        if len(attempt_tokens) != receipt.attempt_count:
            raise ValueError(f"{receipt.case_id}: attempt count does not match frozen receipt")

        cases.append(
            R7BCase(
                case_id=receipt.case_id,
                family=receipt.family,
                template_id=receipt.template_id,
                score_passed=receipt.score_passed,
                usage_complete=receipt.usage_complete,
                attempt_count=receipt.attempt_count,
                inference_tokens=(
                    receipt.observed_input_tokens + receipt.observed_completion_tokens
                ),
                per_attempt_inference_tokens=attempt_tokens,
                initial_operation_reference_count=len(observation.operation_references),
                first_attempt_realized_tool_count=len(first_tools),
                first_attempt_tool_signature=(",".join(first_tools) if first_tools else "<none>"),
            )
        )

    return tuple(cases)


def _trace_features(
    path: Path,
) -> tuple[tuple[int | None, ...], tuple[str, ...]]:
    attempt_tokens: list[int | None] = []
    first_attempt_tools: list[str] = []
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
            if (
                attempt.get("usage_status") == "observed"
                and isinstance(usage, dict)
                and usage.get("input_tokens") is not None
                and usage.get("completion_tokens") is not None
            ):
                attempt_tokens.append(int(usage["input_tokens"]) + int(usage["completion_tokens"]))
            else:
                attempt_tokens.append(None)
            continue

        if current_attempt == 1 and event_name == "tool_action_finished":
            action = event.get("action")
            if isinstance(action, dict):
                first_attempt_tools.append(str(action.get("tool", "")))

    return tuple(attempt_tokens), tuple(first_attempt_tools)


def _cross_validate_policy(
    cases: tuple[R7BCase, ...],
    spec: R7BPolicySpec,
) -> R7BCandidateMetric:
    template_ids = sorted({case.template_id for case in cases})
    folds: list[R7BFoldMetric] = []

    for template_id in template_ids:
        training = tuple(case for case in cases if case.template_id != template_id)
        held_out = tuple(case for case in cases if case.template_id == template_id)
        mapping = _learn_mapping(training, spec)
        folds.append(
            _evaluate_cases(
                held_out,
                spec,
                mapping,
                held_out_template_id=template_id,
            )
        )

    baseline_tokens = sum(fold.baseline_complete_usage_tokens for fold in folds)
    simulated_tokens = sum(fold.simulated_complete_usage_tokens for fold in folds)
    reduction = _reduction(baseline_tokens, simulated_tokens)
    pass_loss = sum(fold.observed_pass_loss_count for fold in folds)

    return R7BCandidateMetric(
        policy_name=spec.name,
        signals=spec.signals,
        fold_count=len(folds),
        case_count=sum(fold.case_count for fold in folds),
        pass_count=sum(fold.pass_count for fold in folds),
        observed_pass_loss_count=pass_loss,
        complete_usage_case_count=sum(fold.complete_usage_case_count for fold in folds),
        baseline_complete_usage_tokens=baseline_tokens,
        simulated_complete_usage_tokens=simulated_tokens,
        diagnostic_token_reduction_fraction=reduction,
        adapted_case_count=sum(fold.adapted_case_count for fold in folds),
        qualifies=(pass_loss == 0 and reduction >= R7B_EFFICIENCY_TARGET),
        folds=tuple(folds),
    )


def _learn_mapping(
    cases: tuple[R7BCase, ...],
    spec: R7BPolicySpec,
) -> dict[tuple[str, ...], int]:
    grouped: dict[tuple[str, ...], list[R7BCase]] = defaultdict(list)
    for case in cases:
        grouped[_policy_key(case, spec)].append(case)

    mapping: dict[tuple[str, ...], int] = {}
    for key, group in grouped.items():
        if len(group) < R7B_MIN_BUCKET_SUPPORT:
            continue
        pass_attempts = [case.attempt_count for case in group if case.score_passed]
        if not pass_attempts:
            continue
        cap = max(pass_attempts)
        if cap < R7B_BASELINE_MAX_MODEL_CALLS:
            mapping[key] = max(1, cap)
    return mapping


def _evaluate_cases(
    cases: tuple[R7BCase, ...],
    spec: R7BPolicySpec,
    mapping: dict[tuple[str, ...], int],
    *,
    held_out_template_id: str,
) -> R7BFoldMetric:
    baseline_tokens = 0
    simulated_tokens = 0
    pass_loss = 0
    adapted = 0

    for case in cases:
        cap = mapping.get(
            _policy_key(case, spec),
            R7B_BASELINE_MAX_MODEL_CALLS,
        )
        if cap < R7B_BASELINE_MAX_MODEL_CALLS:
            adapted += 1
        if case.score_passed and case.attempt_count > cap:
            pass_loss += 1
        if case.usage_complete:
            baseline_tokens += case.inference_tokens
            simulated_tokens += _tokens_through_attempt(case, cap)

    return R7BFoldMetric(
        held_out_template_id=held_out_template_id,
        case_count=len(cases),
        pass_count=sum(case.score_passed for case in cases),
        observed_pass_loss_count=pass_loss,
        complete_usage_case_count=sum(case.usage_complete for case in cases),
        baseline_complete_usage_tokens=baseline_tokens,
        simulated_complete_usage_tokens=simulated_tokens,
        diagnostic_token_reduction_fraction=_reduction(
            baseline_tokens,
            simulated_tokens,
        ),
        adapted_case_count=adapted,
    )


def _fit_selected_policy(
    cases: tuple[R7BCase, ...],
    metric: R7BCandidateMetric,
) -> R7BSelectedPolicy:
    spec = next(spec for spec in POLICY_SPECS if spec.name == metric.policy_name)
    grouped: dict[tuple[str, ...], list[R7BCase]] = defaultdict(list)
    for case in cases:
        grouped[_policy_key(case, spec)].append(case)

    entries: list[R7BPolicyEntry] = []
    for key, group in sorted(grouped.items()):
        if len(group) < R7B_MIN_BUCKET_SUPPORT:
            continue
        pass_attempts = [case.attempt_count for case in group if case.score_passed]
        if not pass_attempts:
            continue
        cap = max(pass_attempts)
        if cap >= R7B_BASELINE_MAX_MODEL_CALLS:
            continue
        entries.append(
            R7BPolicyEntry(
                signal_values={
                    signal: value
                    for signal, value in zip(
                        spec.signals,
                        key,
                        strict=True,
                    )
                },
                max_model_calls=max(1, cap),
                training_support=len(group),
                training_pass_support=len(pass_attempts),
            )
        )

    return R7BSelectedPolicy(
        policy_name=metric.policy_name,
        signals=metric.signals,
        cross_validated_diagnostic_token_reduction_fraction=(
            metric.diagnostic_token_reduction_fraction
        ),
        cross_validated_observed_pass_loss_count=(metric.observed_pass_loss_count),
        entries=tuple(entries),
    )


def _policy_key(
    case: R7BCase,
    spec: R7BPolicySpec,
) -> tuple[str, ...]:
    values: list[str] = []
    for signal in spec.signals:
        if signal == "initial_operation_reference_count":
            values.append(str(case.initial_operation_reference_count))
        elif signal == "first_attempt_realized_tool_count":
            values.append(str(case.first_attempt_realized_tool_count))
        elif signal == "first_attempt_tool_signature":
            values.append(case.first_attempt_tool_signature)
        else:  # pragma: no cover - SignalName exhaustiveness
            raise AssertionError(f"unsupported signal: {signal}")
    return tuple(values)


def _tokens_through_attempt(case: R7BCase, cap: int) -> int:
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
