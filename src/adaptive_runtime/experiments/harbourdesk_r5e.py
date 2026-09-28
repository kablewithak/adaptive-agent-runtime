from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.contracts.config import EndpointProfile, load_account_config
from adaptive_runtime.contracts.provider import ProviderProtocol
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5ReferenceRunReceipt,
)

R5E_BASELINE_RUN_ID = "r5-glm52-development-reference-20260928-01"
R5E_BASELINE_MANIFEST_SHA256 = (
    "e9eab99e4833387285a580dc212405581121f9907c5d9b3b2a7f0572016a0e84"
)
R5E_BASELINE_SUMMARY_SHA256 = (
    "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"
)
R5E_COMPLETION_TOKENS = 1536


class R5EContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R5EScreenManifest(R5EContract):
    schema_version: Literal["harbourdesk-r5e-challenger-screen-v1"]
    source_r5_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_rule: Literal[
        "first_two_cases_per_development_template_in_frozen_r5_manifest_order"
    ]
    case_count: int
    template_count: int
    cases_per_template: int
    family_case_counts: dict[str, int]
    case_order: tuple[str, ...]
    entries: tuple[dict[str, object], ...]


class R5EProfileQualification(R5EContract):
    profile_name: str
    model_id: str
    protocol: str
    max_tested_completion_tokens: int | None
    capability_receipt_present: bool
    eligible_for_openai_screen: bool
    reasons: tuple[str, ...]


class R5EBaselineSubset(R5EContract):
    case_count: int
    pass_count: int
    pass_rate: float
    usage_complete: bool
    observed_inference_tokens: int
    stop_counts: dict[str, int]
    scoring_failure_counts: dict[str, int]
    family_pass_counts: dict[str, int]
    template_pass_counts: dict[str, int]


class R5EPrecheckReceipt(R5EContract):
    schema_version: Literal["harbourdesk-r5e-precheck-v1"] = (
        "harbourdesk-r5e-precheck-v1"
    )
    status: Literal["PASS", "FAIL"]
    screen_case_count: int
    screen_template_count: int
    screen_family_case_counts: dict[str, int]
    baseline_subset: R5EBaselineSubset
    profiles: tuple[R5EProfileQualification, ...]
    eligible_profile_names: tuple[str, ...]
    r5d_status_pass: bool
    r5d_summary_sha256: str | None
    r5d_report_sha256: str | None
    failures: tuple[str, ...]


def load_r5e_screen_manifest(repo_root: Path) -> R5EScreenManifest:
    path = (
        repo_root
        / "benchmarks"
        / "harbourdesk"
        / "r5"
        / "challenger_screen_manifest_v1.json"
    )
    return R5EScreenManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def run_r5e_precheck(
    repo_root: Path,
    *,
    config_path: Path = Path("configs/account.local.json"),
) -> R5EPrecheckReceipt:
    failures: list[str] = []
    screen = load_r5e_screen_manifest(repo_root)

    if screen.case_count != 36:
        failures.append("screen_case_count_mismatch")
    if screen.template_count != 18:
        failures.append("screen_template_count_mismatch")
    if screen.cases_per_template != 2:
        failures.append("screen_cases_per_template_mismatch")
    if screen.family_case_counts != {f"F{i}": 6 for i in range(1, 7)}:
        failures.append("screen_family_balance_mismatch")
    if len(screen.case_order) != 36 or len(set(screen.case_order)) != 36:
        failures.append("screen_case_identity_mismatch")

    template_counts = Counter(
        str(entry.get("template_id")) for entry in screen.entries
    )
    if set(template_counts.values()) != {2} or len(template_counts) != 18:
        failures.append("screen_template_balance_mismatch")

    baseline = _load_frozen_baseline(repo_root, failures)
    baseline_subset = _baseline_subset(baseline, screen, failures)

    config = load_account_config(repo_root / config_path)
    profiles = tuple(
        _qualify_profile(profile)
        for profile in config.profiles
    )
    eligible = tuple(
        profile.profile_name
        for profile in profiles
        if profile.eligible_for_openai_screen
    )

    r5d_summary = (
        repo_root
        / "runs"
        / "r5_analysis"
        / "r5d-20260928-01"
        / "summary.json"
    )
    r5d_report = r5d_summary.with_name("report.md")
    r5d_status_pass = False
    r5d_summary_sha: str | None = None
    r5d_report_sha: str | None = None

    if r5d_summary.is_file():
        r5d_summary_sha = _sha256_file(r5d_summary)
        payload = json.loads(r5d_summary.read_text(encoding="utf-8"))
        r5d_status_pass = (
            isinstance(payload, dict)
            and payload.get("status") == "PASS"
            and payload.get("case_count") == 90
            and payload.get("integrity_failures") == []
        )
    if r5d_report.is_file():
        r5d_report_sha = _sha256_file(r5d_report)

    if not r5d_status_pass:
        failures.append("r5d_pass_receipt_missing_or_invalid")
    if r5d_report_sha is None:
        failures.append("r5d_report_missing")

    return R5EPrecheckReceipt(
        status="PASS" if not failures else "FAIL",
        screen_case_count=screen.case_count,
        screen_template_count=screen.template_count,
        screen_family_case_counts=screen.family_case_counts,
        baseline_subset=baseline_subset,
        profiles=profiles,
        eligible_profile_names=eligible,
        r5d_status_pass=r5d_status_pass,
        r5d_summary_sha256=r5d_summary_sha,
        r5d_report_sha256=r5d_report_sha,
        failures=tuple(failures),
    )


def _load_frozen_baseline(
    repo_root: Path,
    failures: list[str],
) -> R5ReferenceRunReceipt:
    run_dir = (
        repo_root
        / "runs"
        / "r5_reference"
        / R5E_BASELINE_RUN_ID
    )
    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.json"

    if _sha256_file(manifest_path) != R5E_BASELINE_MANIFEST_SHA256:
        failures.append("baseline_manifest_sha256_mismatch")
    if _sha256_file(summary_path) != R5E_BASELINE_SUMMARY_SHA256:
        failures.append("baseline_summary_sha256_mismatch")

    return R5ReferenceRunReceipt.model_validate_json(
        summary_path.read_text(encoding="utf-8")
    )


def _baseline_subset(
    baseline: R5ReferenceRunReceipt,
    screen: R5EScreenManifest,
    failures: list[str],
) -> R5EBaselineSubset:
    selected = set(screen.case_order)
    cases = tuple(
        case for case in baseline.cases if case.case_id in selected
    )
    if len(cases) != 36:
        failures.append("baseline_screen_case_count_mismatch")

    pass_count = sum(case.score_passed for case in cases)
    usage_complete = bool(cases) and all(case.usage_complete for case in cases)
    inference_tokens = sum(
        case.observed_input_tokens + case.observed_completion_tokens
        for case in cases
    )

    family_passes: Counter[str] = Counter()
    template_passes: Counter[str] = Counter()
    for case in cases:
        if case.score_passed:
            family_passes[case.family] += 1
            template_passes[case.template_id] += 1

    return R5EBaselineSubset(
        case_count=len(cases),
        pass_count=pass_count,
        pass_rate=(pass_count / len(cases) if cases else 0.0),
        usage_complete=usage_complete,
        observed_inference_tokens=inference_tokens,
        stop_counts=dict(
            sorted(Counter(case.stop_category.value for case in cases).items())
        ),
        scoring_failure_counts=dict(
            sorted(
                Counter(
                    failure
                    for case in cases
                    for failure in case.scoring_failures
                ).items()
            )
        ),
        family_pass_counts={
            family: family_passes.get(family, 0)
            for family in sorted(screen.family_case_counts)
        },
        template_pass_counts={
            template: template_passes.get(template, 0)
            for template in sorted(
                {str(entry.get("template_id")) for entry in screen.entries}
            )
        },
    )


def _qualify_profile(profile: EndpointProfile) -> R5EProfileQualification:
    profile_name = profile.profile_name
    model_id = profile.model_id
    protocol = profile.protocol
    max_completion = profile.max_tested_completion_tokens
    receipt = profile.capability_receipt_sha256

    reasons: list[str] = []
    if protocol is not ProviderProtocol.OPENAI_COMPATIBLE:
        reasons.append("protocol_not_openai_compatible")
    if model_id == "glm-5.2":
        reasons.append("baseline_model_excluded")
    if max_completion is None:
        reasons.append("completion_capacity_unproven")
    elif int(max_completion) < R5E_COMPLETION_TOKENS:
        reasons.append("completion_capacity_below_1536")
    if receipt is None:
        reasons.append("capability_receipt_missing")

    return R5EProfileQualification(
        profile_name=profile_name,
        model_id=model_id,
        protocol=str(protocol.value),
        max_tested_completion_tokens=(
            None if max_completion is None else int(max_completion)
        ),
        capability_receipt_present=receipt is not None,
        eligible_for_openai_screen=not reasons,
        reasons=tuple(reasons),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
