from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5ReferenceCaseReceipt,
    R5ReferenceRunReceipt,
)

R5D_RUN_ID = "r5-glm52-development-reference-20260928-01"
R5D_COMMIT = "67d841527d5fb12f9ee1d108b95729ebe6113bcd"
R5D_MANIFEST_SHA256 = "e9eab99e4833387285a580dc212405581121f9907c5d9b3b2a7f0572016a0e84"
R5D_SUMMARY_SHA256 = "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"


class R5DContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GroupMetric(R5DContract):
    case_count: int
    pass_count: int
    terminal_failure_count: int
    nonterminal_failure_count: int
    usage_incomplete_count: int
    observed_inference_tokens: int
    stop_counts: dict[str, int]
    scoring_failure_counts: dict[str, int]


class R5DAnalysisReceipt(R5DContract):
    schema_version: Literal["harbourdesk-r5d-analysis-v1"] = "harbourdesk-r5d-analysis-v1"
    status: Literal["PASS", "FAIL"]
    run_id: str
    candidate_commit: str
    manifest_sha256: str
    summary_sha256: str
    case_count: int
    per_case_receipt_match_count: int
    trace_hash_match_count: int
    trace_final_state_match_count: int
    score_pass_count: int
    score_fail_count: int
    terminal_pass_count: int
    terminal_failure_count: int
    nonterminal_failure_count: int
    usage_complete_case_count: int
    usage_incomplete_case_count: int
    usage_incomplete_case_ids: tuple[str, ...]
    provider_error_case_ids: tuple[str, ...]
    model_call_budget_case_ids: tuple[str, ...]
    model_text_without_terminal_case_ids: tuple[str, ...]
    observed_inference_tokens: int
    efficiency_status: Literal["INCONCLUSIVE", "QUALIFIED"]
    complete_usage_subset_case_count: int
    complete_usage_subset_pass_count: int
    complete_usage_subset_inference_tokens: int
    complete_usage_subset_tokens_per_success: float | None
    family_metrics: dict[str, GroupMetric]
    template_metrics: dict[str, GroupMetric]
    failure_signature_counts: dict[str, int]
    integrity_failures: tuple[str, ...]


def analyze_r5_reference(run_dir: Path) -> R5DAnalysisReceipt:
    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.json"
    failures: list[str] = []

    if not manifest_path.is_file() or not summary_path.is_file():
        raise FileNotFoundError("frozen R5 manifest/summary missing")

    manifest_sha = _sha256_file(manifest_path)
    summary_sha = _sha256_file(summary_path)
    if manifest_sha != R5D_MANIFEST_SHA256:
        failures.append("manifest_sha256_mismatch")
    if summary_sha != R5D_SUMMARY_SHA256:
        failures.append("summary_sha256_mismatch")

    summary = R5ReferenceRunReceipt.model_validate_json(
        summary_path.read_text(encoding="utf-8")
    )
    if summary.run_id != R5D_RUN_ID:
        failures.append("run_id_mismatch")
    if summary.candidate_commit != R5D_COMMIT:
        failures.append("candidate_commit_mismatch")
    if summary.case_count != 90 or len(summary.cases) != 90:
        failures.append("case_count_mismatch")
    if len({case.case_id for case in summary.cases}) != 90:
        failures.append("duplicate_case_ids")
    if summary.validation_cases_selected != 0:
        failures.append("validation_case_leak")
    if summary.locked_cases_selected != 0:
        failures.append("locked_case_leak")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("case_order") != [case.case_id for case in summary.cases]:
        failures.append("manifest_case_order_mismatch")

    receipt_matches = 0
    trace_matches = 0
    final_state_matches = 0

    for suite_case in summary.cases:
        case_dir = run_dir / suite_case.case_id
        receipt_path = case_dir / "receipt.json"
        trace_path = case_dir / "trace.jsonl"

        if not receipt_path.is_file():
            failures.append(f"{suite_case.case_id}:missing_receipt")
            continue
        observed = R5ReferenceCaseReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        if observed == suite_case:
            receipt_matches += 1
        else:
            failures.append(f"{suite_case.case_id}:receipt_mismatch")

        if not trace_path.is_file():
            failures.append(f"{suite_case.case_id}:missing_trace")
            continue
        if _sha256_file(trace_path) == suite_case.trace_sha256:
            trace_matches += 1
        else:
            failures.append(f"{suite_case.case_id}:trace_hash_mismatch")

        if _trace_final_state(trace_path) == suite_case.final_state_sha256:
            final_state_matches += 1
        else:
            failures.append(f"{suite_case.case_id}:final_state_hash_mismatch")

    passes = tuple(case for case in summary.cases if case.score_passed)
    terminal_failures = tuple(
        case for case in summary.cases if not case.score_passed and case.terminal_reached
    )
    nonterminal_failures = tuple(
        case for case in summary.cases if not case.score_passed and not case.terminal_reached
    )
    terminal_passes = tuple(case for case in passes if case.terminal_reached)
    if any(not case.terminal_reached for case in passes):
        failures.append("nonterminal_score_pass_observed")

    usage_complete = tuple(case for case in summary.cases if case.usage_complete)
    usage_incomplete = tuple(case for case in summary.cases if not case.usage_complete)
    complete_passes = sum(case.score_passed for case in usage_complete)
    complete_tokens = sum(
        case.observed_input_tokens + case.observed_completion_tokens
        for case in usage_complete
    )

    signatures = Counter(
        _failure_signature(case)
        for case in summary.cases
        if not case.score_passed
    )

    return R5DAnalysisReceipt(
        status="PASS" if not failures else "FAIL",
        run_id=summary.run_id,
        candidate_commit=summary.candidate_commit,
        manifest_sha256=manifest_sha,
        summary_sha256=summary_sha,
        case_count=summary.case_count,
        per_case_receipt_match_count=receipt_matches,
        trace_hash_match_count=trace_matches,
        trace_final_state_match_count=final_state_matches,
        score_pass_count=summary.score_pass_count,
        score_fail_count=summary.case_count - summary.score_pass_count,
        terminal_pass_count=len(terminal_passes),
        terminal_failure_count=len(terminal_failures),
        nonterminal_failure_count=len(nonterminal_failures),
        usage_complete_case_count=len(usage_complete),
        usage_incomplete_case_count=len(usage_incomplete),
        usage_incomplete_case_ids=tuple(case.case_id for case in usage_incomplete),
        provider_error_case_ids=_ids_for_stop(summary.cases, "provider_error"),
        model_call_budget_case_ids=_ids_for_stop(
            summary.cases, "model_call_budget_exhausted"
        ),
        model_text_without_terminal_case_ids=_ids_for_stop(
            summary.cases, "model_text_without_terminal"
        ),
        observed_inference_tokens=summary.observed_inference_tokens,
        efficiency_status="QUALIFIED" if summary.usage_complete else "INCONCLUSIVE",
        complete_usage_subset_case_count=len(usage_complete),
        complete_usage_subset_pass_count=complete_passes,
        complete_usage_subset_inference_tokens=complete_tokens,
        complete_usage_subset_tokens_per_success=(
            complete_tokens / complete_passes if complete_passes else None
        ),
        family_metrics=_group_metrics(summary.cases, "family"),
        template_metrics=_group_metrics(summary.cases, "template_id"),
        failure_signature_counts=dict(sorted(signatures.items())),
        integrity_failures=tuple(failures),
    )


def render_markdown(receipt: R5DAnalysisReceipt) -> str:
    lines = [
        "# HarbourDesk R5D Reference Analysis",
        "",
        f"- Integrity: **{receipt.status}**",
        f"- Verified passes: **{receipt.score_pass_count}/{receipt.case_count}**",
        f"- Terminal failures: **{receipt.terminal_failure_count}**",
        f"- Nonterminal failures: **{receipt.nonterminal_failure_count}**",
        f"- Usage-incomplete cases: **{receipt.usage_incomplete_case_count}**",
        f"- Efficiency evidence: **{receipt.efficiency_status}**",
        "",
        "## Family breakdown",
        "",
        "| Family | Cases | Pass | Terminal fail | Nonterminal fail | "
        "Usage incomplete | Observed tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, metric in sorted(receipt.family_metrics.items()):
        lines.append(
            f"| {key} | {metric.case_count} | {metric.pass_count} | "
            f"{metric.terminal_failure_count} | {metric.nonterminal_failure_count} | "
            f"{metric.usage_incomplete_count} | {metric.observed_inference_tokens} |"
        )

    lines.extend(["", "## Template breakdown", ""])
    lines.extend(
        [
            "| Template | Cases | Pass | Terminal fail | Nonterminal fail | "
            "Usage incomplete | Observed tokens |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, metric in sorted(receipt.template_metrics.items()):
        lines.append(
            f"| {key} | {metric.case_count} | {metric.pass_count} | "
            f"{metric.terminal_failure_count} | {metric.nonterminal_failure_count} | "
            f"{metric.usage_incomplete_count} | {metric.observed_inference_tokens} |"
        )

    lines.extend(["", "## Failure signatures", ""])
    for signature, count in sorted(
        receipt.failure_signature_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"- `{signature}`: {count}")

    lines.extend(
        [
            "",
            "## Efficiency boundary",
            "",
            "Because the frozen R5C run has incomplete usage accounting, the overall "
            "efficiency baseline remains INCONCLUSIVE. Complete-usage subset metrics "
            "are diagnostic only and must not be used for the final >=20% efficiency gate.",
            "",
        ]
    )
    return "\n".join(lines)


def _group_metrics(
    cases: tuple[R5ReferenceCaseReceipt, ...],
    key: str,
) -> dict[str, GroupMetric]:
    grouped: dict[str, list[R5ReferenceCaseReceipt]] = defaultdict(list)
    for case in cases:
        grouped[str(getattr(case, key))].append(case)

    result: dict[str, GroupMetric] = {}
    for name, group in sorted(grouped.items()):
        result[name] = GroupMetric(
            case_count=len(group),
            pass_count=sum(case.score_passed for case in group),
            terminal_failure_count=sum(
                not case.score_passed and case.terminal_reached for case in group
            ),
            nonterminal_failure_count=sum(
                not case.score_passed and not case.terminal_reached for case in group
            ),
            usage_incomplete_count=sum(not case.usage_complete for case in group),
            observed_inference_tokens=sum(
                case.observed_input_tokens + case.observed_completion_tokens
                for case in group
            ),
            stop_counts=dict(
                sorted(Counter(case.stop_category.value for case in group).items())
            ),
            scoring_failure_counts=dict(
                sorted(
                    Counter(
                        failure
                        for case in group
                        for failure in case.scoring_failures
                    ).items()
                )
            ),
        )
    return result


def _failure_signature(case: R5ReferenceCaseReceipt) -> str:
    if case.score_passed:
        return "PASS"
    if not case.terminal_reached:
        return f"nonterminal:{case.stop_category.value}"
    if not case.scoring_failures:
        return "terminal:unclassified"
    return "terminal:" + "+".join(sorted(case.scoring_failures))


def _ids_for_stop(
    cases: tuple[R5ReferenceCaseReceipt, ...],
    stop: str,
) -> tuple[str, ...]:
    return tuple(case.case_id for case in cases if case.stop_category.value == stop)


def _trace_final_state(path: Path) -> str | None:
    result: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "run_finished":
            value = event.get("final_state_sha256")
            result = str(value) if value is not None else None
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
