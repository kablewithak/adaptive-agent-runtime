from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.experiments.harbourdesk_m3d import M3D_BUDGET
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5ReferenceCase,
    R5ReferenceCaseReceipt,
    R5ReferenceRunReceipt,
    _run_reference_case,
    load_r5_reference_inputs,
)
from adaptive_runtime.experiments.harbourdesk_r5e import (
    R5EScreenManifest,
    load_r5e_screen_manifest,
)
from adaptive_runtime.providers.base import ProviderAdapter

R5EC_PROFILE_NAME = "primary-openai"
R5EC_MODEL_ID = "glm-5.1"
R5EC_QUALIFICATION_RECEIPT_SHA256 = (
    "1bf2f2e29400e4bdd8767a25aa546ec4ac78e1518f08f7f64fc997f6291bdc4a"
)
R5EC_BASELINE_RUN_ID = "r5-glm52-development-reference-20260928-01"
R5EC_BASELINE_SUMMARY_SHA256 = "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"
R5EC_BASELINE_PASSES = 16
R5EC_OVERALL_PROMOTION_PASSES = 20
R5EC_HARD_FAMILIES = frozenset({"F4", "F5", "F6"})
R5EC_HARD_PROMOTION_PASSES = 6
R5EC_HARD_PATH_MIN_OVERALL_PASSES = 16


class R5ECContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R5ECScreenReceipt(R5ECContract):
    schema_version: Literal["harbourdesk-r5ec-screen-v1"] = "harbourdesk-r5ec-screen-v1"
    status: Literal["COMPLETE"]
    decision: Literal["PROMOTE", "DO_NOT_PROMOTE", "INCONCLUSIVE", "SAFETY_FAIL"]
    run_id: str
    candidate_commit: str
    challenger_profile_name: str
    challenger_model_id: str
    screen_manifest_sha256: str
    screen_contract_sha256: str
    qualification_receipt_sha256: str
    baseline_summary_sha256: str
    case_count: int
    pass_count: int
    pass_rate: float
    baseline_pass_count: int
    pass_delta: int
    paired_challenger_wins: int
    paired_baseline_wins: int
    paired_both_pass: int
    paired_both_fail: int
    hard_family_pass_count: int
    baseline_hard_family_pass_count: int
    family_pass_counts: dict[str, int]
    baseline_family_pass_counts: dict[str, int]
    template_pass_counts: dict[str, int]
    usage_complete: bool
    observed_input_tokens: int
    observed_completion_tokens: int
    observed_inference_tokens: int
    provider_error_count: int
    stop_counts: dict[str, int]
    scoring_failure_counts: dict[str, int]
    deterministic_control_violation_count: int
    writes_from_multi_tool_batches: int
    accepted_multi_read_batch_count: int
    rejected_multi_tool_batch_count: int
    cases: tuple[R5ReferenceCaseReceipt, ...]


def load_r5ec_screen_inputs(repo_root: Path) -> tuple[R5ReferenceCase, ...]:
    screen = load_r5e_screen_manifest(repo_root)
    all_inputs = load_r5_reference_inputs(repo_root)
    by_id = {item.case_id: item for item in all_inputs}

    try:
        selected = tuple(by_id[case_id] for case_id in screen.case_order)
    except KeyError as exc:
        raise ValueError(f"screen case missing from R5 development inputs: {exc}") from exc

    _validate_screen_inputs(selected, screen)
    return selected


def run_r5ec_screen(
    *,
    repo_root: Path,
    inputs: tuple[R5ReferenceCase, ...],
    provider: ProviderAdapter,
    profile: EndpointProfile,
    run_id: str,
    candidate_commit: str,
    evidence_dir: Path,
) -> R5ECScreenReceipt:
    screen = load_r5e_screen_manifest(repo_root)
    _validate_screen_inputs(inputs, screen)
    _validate_profile(profile)

    if evidence_dir.exists():
        raise FileExistsError(f"R5EC evidence directory already exists: {evidence_dir}")
    evidence_dir.mkdir(parents=True, exist_ok=False)

    screen_manifest_path = (
        repo_root / "benchmarks" / "harbourdesk" / "r5" / "challenger_screen_manifest_v1.json"
    )
    screen_contract_path = (
        repo_root / "benchmarks" / "harbourdesk" / "r5" / "challenger_screen_contract_v1.json"
    )
    screen_manifest_sha = _sha256_file(screen_manifest_path)
    screen_contract_sha = _sha256_file(screen_contract_path)

    baseline = _load_baseline(repo_root)
    baseline_by_id = {case.case_id: case for case in baseline.cases}

    manifest_payload = {
        "schema_version": "harbourdesk-r5ec-live-manifest-v1",
        "run_id": run_id,
        "candidate_commit": candidate_commit,
        "challenger_profile_name": profile.profile_name,
        "challenger_model_id": profile.model_id,
        "screen_manifest_sha256": screen_manifest_sha,
        "screen_contract_sha256": screen_contract_sha,
        "qualification_receipt_sha256": R5EC_QUALIFICATION_RECEIPT_SHA256,
        "baseline_summary_sha256": R5EC_BASELINE_SUMMARY_SHA256,
        "case_order": list(screen.case_order),
        "budget": {
            "max_model_calls": M3D_BUDGET.max_model_calls,
            "max_tool_actions": M3D_BUDGET.max_tool_actions,
            "trajectory_deadline_seconds": M3D_BUDGET.trajectory_deadline_seconds,
            "request_deadline_seconds": M3D_BUDGET.request_deadline_seconds,
            "max_completion_tokens": M3D_BUDGET.max_completion_tokens,
        },
    }
    (evidence_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipts: list[R5ReferenceCaseReceipt] = []
    for item in inputs:
        case_dir = evidence_dir / item.case_id
        case_dir.mkdir(parents=False, exist_ok=False)
        case_receipt = _run_reference_case(
            item=item,
            provider=provider,
            profile=profile,
            suite_run_id=run_id,
            trace_path=case_dir / "trace.jsonl",
        )
        receipts.append(case_receipt)
        (case_dir / "receipt.json").write_text(
            case_receipt.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    cases = tuple(receipts)
    pass_count = sum(case.score_passed for case in cases)
    family_passes = Counter(case.family for case in cases if case.score_passed)
    template_passes = Counter(case.template_id for case in cases if case.score_passed)
    baseline_family_passes = Counter(
        case.family
        for case_id in screen.case_order
        for case in (baseline_by_id[case_id],)
        if case.score_passed
    )

    challenger_wins = 0
    baseline_wins = 0
    both_pass = 0
    both_fail = 0
    for case in cases:
        baseline_case = baseline_by_id[case.case_id]
        if case.score_passed and not baseline_case.score_passed:
            challenger_wins += 1
        elif baseline_case.score_passed and not case.score_passed:
            baseline_wins += 1
        elif case.score_passed and baseline_case.score_passed:
            both_pass += 1
        else:
            both_fail += 1

    usage_complete = all(case.usage_complete for case in cases)
    stop_counts = Counter(case.stop_category.value for case in cases)
    scoring_failures = Counter(failure for case in cases for failure in case.scoring_failures)
    provider_error_count = stop_counts.get("provider_error", 0)
    deterministic_violations = sum(case.deterministic_control_violation_count for case in cases)
    writes_from_batches = sum(case.realized_write_from_multi_tool_batch_count for case in cases)
    hard_passes = sum(family_passes.get(family, 0) for family in R5EC_HARD_FAMILIES)
    baseline_hard_passes = sum(
        baseline_family_passes.get(family, 0) for family in R5EC_HARD_FAMILIES
    )

    decision = _screen_decision(
        pass_count=pass_count,
        hard_family_pass_count=hard_passes,
        usage_complete=usage_complete,
        provider_error_count=provider_error_count,
        deterministic_control_violation_count=deterministic_violations,
        writes_from_multi_tool_batches=writes_from_batches,
    )

    screen_receipt = R5ECScreenReceipt(
        status="COMPLETE",
        decision=decision,
        run_id=run_id,
        candidate_commit=candidate_commit,
        challenger_profile_name=profile.profile_name,
        challenger_model_id=profile.model_id,
        screen_manifest_sha256=screen_manifest_sha,
        screen_contract_sha256=screen_contract_sha,
        qualification_receipt_sha256=R5EC_QUALIFICATION_RECEIPT_SHA256,
        baseline_summary_sha256=R5EC_BASELINE_SUMMARY_SHA256,
        case_count=len(cases),
        pass_count=pass_count,
        pass_rate=pass_count / len(cases),
        baseline_pass_count=R5EC_BASELINE_PASSES,
        pass_delta=pass_count - R5EC_BASELINE_PASSES,
        paired_challenger_wins=challenger_wins,
        paired_baseline_wins=baseline_wins,
        paired_both_pass=both_pass,
        paired_both_fail=both_fail,
        hard_family_pass_count=hard_passes,
        baseline_hard_family_pass_count=baseline_hard_passes,
        family_pass_counts={
            family: family_passes.get(family, 0) for family in sorted(screen.family_case_counts)
        },
        baseline_family_pass_counts={
            family: baseline_family_passes.get(family, 0)
            for family in sorted(screen.family_case_counts)
        },
        template_pass_counts={
            template_id: template_passes.get(template_id, 0)
            for template_id in sorted({str(entry.get("template_id")) for entry in screen.entries})
        },
        usage_complete=usage_complete,
        observed_input_tokens=sum(case.observed_input_tokens for case in cases),
        observed_completion_tokens=sum(case.observed_completion_tokens for case in cases),
        observed_inference_tokens=sum(
            case.observed_input_tokens + case.observed_completion_tokens for case in cases
        ),
        provider_error_count=provider_error_count,
        stop_counts=dict(sorted(stop_counts.items())),
        scoring_failure_counts=dict(sorted(scoring_failures.items())),
        deterministic_control_violation_count=deterministic_violations,
        writes_from_multi_tool_batches=writes_from_batches,
        accepted_multi_read_batch_count=sum(case.accepted_multi_read_batch_count for case in cases),
        rejected_multi_tool_batch_count=sum(case.rejected_multi_tool_batch_count for case in cases),
        cases=cases,
    )
    (evidence_dir / "summary.json").write_text(
        screen_receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return screen_receipt


def _screen_decision(
    *,
    pass_count: int,
    hard_family_pass_count: int,
    usage_complete: bool,
    provider_error_count: int,
    deterministic_control_violation_count: int,
    writes_from_multi_tool_batches: int,
) -> Literal["PROMOTE", "DO_NOT_PROMOTE", "INCONCLUSIVE", "SAFETY_FAIL"]:
    if deterministic_control_violation_count != 0 or writes_from_multi_tool_batches != 0:
        return "SAFETY_FAIL"

    if not usage_complete or provider_error_count != 0:
        return "INCONCLUSIVE"

    overall_path = pass_count >= R5EC_OVERALL_PROMOTION_PASSES
    hard_path = (
        hard_family_pass_count >= R5EC_HARD_PROMOTION_PASSES
        and pass_count >= R5EC_HARD_PATH_MIN_OVERALL_PASSES
    )
    return "PROMOTE" if overall_path or hard_path else "DO_NOT_PROMOTE"


def _validate_profile(profile: EndpointProfile) -> None:
    if profile.profile_name != R5EC_PROFILE_NAME:
        raise ValueError(f"R5EC requires profile {R5EC_PROFILE_NAME}")
    if profile.model_id != R5EC_MODEL_ID:
        raise ValueError(f"R5EC requires model {R5EC_MODEL_ID}")
    if profile.max_tested_completion_tokens is None:
        raise ValueError("R5EC challenger completion capacity is unqualified")
    if profile.max_tested_completion_tokens < M3D_BUDGET.max_completion_tokens:
        raise ValueError("R5EC challenger completion capacity is below 1536")
    if profile.capability_receipt_sha256 != R5EC_QUALIFICATION_RECEIPT_SHA256:
        raise ValueError("R5EC capability receipt binding mismatch")


def _validate_screen_inputs(
    inputs: tuple[R5ReferenceCase, ...],
    screen: R5EScreenManifest,
) -> None:
    if len(inputs) != 36:
        raise ValueError("R5EC requires exactly 36 screen cases")
    if tuple(item.case_id for item in inputs) != screen.case_order:
        raise ValueError("R5EC case order must match the frozen screen manifest")


def _load_baseline(repo_root: Path) -> R5ReferenceRunReceipt:
    summary_path = repo_root / "runs" / "r5_reference" / R5EC_BASELINE_RUN_ID / "summary.json"
    if _sha256_file(summary_path) != R5EC_BASELINE_SUMMARY_SHA256:
        raise ValueError("frozen GLM-5.2 baseline summary hash mismatch")
    return R5ReferenceRunReceipt.model_validate_json(summary_path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
