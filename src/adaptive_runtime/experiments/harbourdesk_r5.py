from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.contracts.provider import ProviderProtocol
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.evaluation.benchmark_authoring import load_r4_template_catalog
from adaptive_runtime.evaluation.benchmark_program import BenchmarkPartition
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.experiments.harbourdesk_m3d import (
    M3D_BUDGET,
    M3D_IDENTITY,
)

R5_R4_QUALIFIED_COMMIT = "0c741192e52916de2330462b9c95bbd31e004924"
R5_MODEL_ID = "glm-5.2"
R5_PROFILE_NAME = "glm-5-2-openai"
R5_DEVELOPMENT_CASE_COUNT = 90
R5_VALIDATION_CASE_COUNT = 0
R5_LOCKED_CASE_COUNT = 0


class R5PreflightError(RuntimeError):
    """Raised when the R5 fixed-reference boundary is not safe to execute."""


class R5Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class R5DevelopmentCaseBinding(R5Contract):
    case_id: str = Field(pattern=r"^hdb-\d{3}$")
    template_id: str = Field(min_length=1, max_length=100)
    family: str = Field(pattern=r"^F[1-6]$")
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    documents_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class R5DevelopmentReferenceManifest(R5Contract):
    schema_version: Literal["harbourdesk-r5-development-reference-v1"]
    r4_qualified_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    r4_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_root: Literal["benchmarks/harbourdesk/r4/development"]
    private_expected_root: Literal["evaluation_private/harbourdesk/r4/development"]
    model_id: Literal["glm-5.2"]
    profile_name: Literal["glm-5-2-openai"]
    max_model_calls: int
    max_tool_actions: int
    trajectory_deadline_seconds: float
    request_deadline_seconds: float
    max_completion_tokens: int
    development_case_count: int
    validation_case_count: int
    locked_case_count: int
    case_order: tuple[str, ...]
    entries: tuple[R5DevelopmentCaseBinding, ...]

    @model_validator(mode="after")
    def validate_frozen_contract(self) -> R5DevelopmentReferenceManifest:
        if self.r4_qualified_commit != R5_R4_QUALIFIED_COMMIT:
            raise ValueError("R5 manifest is bound to the wrong R4 qualified commit")
        if self.model_id != R5_MODEL_ID or self.profile_name != R5_PROFILE_NAME:
            raise ValueError("R5 model/profile identity drifted")
        if (
            self.max_model_calls != M3D_BUDGET.max_model_calls
            or self.max_tool_actions != M3D_BUDGET.max_tool_actions
            or self.trajectory_deadline_seconds != M3D_BUDGET.trajectory_deadline_seconds
            or self.request_deadline_seconds != M3D_BUDGET.request_deadline_seconds
            or self.max_completion_tokens != M3D_BUDGET.max_completion_tokens
        ):
            raise ValueError("R5 budget must exactly preserve qualified M3D budget")
        if self.development_case_count != R5_DEVELOPMENT_CASE_COUNT:
            raise ValueError("R5 requires exactly 90 development cases")
        if self.validation_case_count != R5_VALIDATION_CASE_COUNT:
            raise ValueError("R5 must not include validation cases")
        if self.locked_case_count != R5_LOCKED_CASE_COUNT:
            raise ValueError("R5 must not include locked cases")
        if len(self.case_order) != 90 or len(set(self.case_order)) != 90:
            raise ValueError("R5 case order must contain 90 unique cases")
        if tuple(item.case_id for item in self.entries) != self.case_order:
            raise ValueError("R5 entry order must exactly match case_order")
        if Counter(item.family for item in self.entries) != Counter(
            {f"F{index}": 15 for index in range(1, 7)}
        ):
            raise ValueError("R5 requires exactly 15 development cases per family")
        return self


class R5PreflightReceipt(R5Contract):
    schema_version: Literal["harbourdesk-r5-preflight-v1"] = "harbourdesk-r5-preflight-v1"
    status: Literal["PASS", "FAIL"]
    r4_qualified_commit: str
    current_head: str
    r4_is_ancestor_of_head: bool
    case_count: int
    public_hash_match_count: int
    private_expected_hash_match_count: int
    catalog_case_order_matches: bool
    profile_matches: bool
    m3d_budget_matches: bool
    r4_quality_receipt_matches: bool
    validation_cases_selected: int
    locked_cases_selected: int
    failures: tuple[str, ...]


def load_r5_manifest(repo_root: Path) -> R5DevelopmentReferenceManifest:
    path = (
        repo_root / "benchmarks" / "harbourdesk" / "r5" / "development_reference_manifest_v1.json"
    )
    return R5DevelopmentReferenceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def validate_r5_public_contract(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    manifest = load_r5_manifest(repo_root)
    catalog_path = repo_root / "benchmarks" / "harbourdesk" / "r4" / "template_catalog_v2.json"

    if _sha256_file(catalog_path) != manifest.r4_catalog_sha256:
        failures.append("R4 template catalog hash mismatch")

    catalog = load_r4_template_catalog(repo_root)
    development_ids = tuple(
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.DEVELOPMENT
        for case_id in template.instance_ids
    )
    if development_ids != manifest.case_order:
        failures.append("R5 case order differs from R4 development catalog order")

    validation_ids = {
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.VALIDATION
        for case_id in template.instance_ids
    }
    locked_ids = {
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.LOCKED
        for case_id in template.instance_ids
    }
    selected = set(manifest.case_order)
    if selected & validation_ids:
        failures.append("R5 selected one or more validation cases")
    if selected & locked_ids:
        failures.append("R5 selected one or more locked cases")

    benchmark_root = repo_root / Path(manifest.benchmark_root)
    for entry in manifest.entries:
        case_dir = benchmark_root / entry.case_id
        expected_files = {
            "case.json": entry.case_sha256,
            "initial_state.json": entry.initial_state_sha256,
            "documents.jsonl": entry.documents_sha256,
        }
        for name, digest in expected_files.items():
            path = case_dir / name
            if not path.is_file():
                failures.append(f"{entry.case_id}: missing public file {name}")
                continue
            if _sha256_file(path) != digest:
                failures.append(f"{entry.case_id}: public hash mismatch for {name}")

        if (case_dir / "expected.json").exists():
            failures.append(f"{entry.case_id}: evaluator expectation leaked publicly")

        state_path = case_dir / "initial_state.json"
        case_path = case_dir / "case.json"
        if state_path.is_file() and case_path.is_file():
            state = HarbourDeskVisibleState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            payload = json.loads(case_path.read_text(encoding="utf-8"))
            ticket_ids = {ticket.ticket_id for ticket in state.tickets}
            if payload["ticket_id"] not in ticket_ids:
                failures.append(f"{entry.case_id}: public case ticket missing from initial state")

    return tuple(failures)


def run_r5_preflight(
    repo_root: Path,
    *,
    config_path: Path = Path("configs/account.local.json"),
) -> R5PreflightReceipt:
    failures = list(validate_r5_public_contract(repo_root))
    manifest = load_r5_manifest(repo_root)

    head = _git_output(repo_root, "rev-parse", "HEAD")
    ancestor = _git_is_ancestor(
        repo_root,
        R5_R4_QUALIFIED_COMMIT,
        head,
    )
    if not ancestor:
        failures.append("qualified R4 commit is not an ancestor of current HEAD")

    private_root = repo_root / Path(manifest.private_expected_root)
    public_hash_matches = 0
    private_hash_matches = 0

    for entry in manifest.entries:
        case_dir = repo_root / Path(manifest.benchmark_root) / entry.case_id
        if (
            _sha256_file(case_dir / "case.json") == entry.case_sha256
            and _sha256_file(case_dir / "initial_state.json") == entry.initial_state_sha256
            and _sha256_file(case_dir / "documents.jsonl") == entry.documents_sha256
        ):
            public_hash_matches += 1

        expected_path = private_root / entry.case_id / "expected.json"
        if not expected_path.is_file():
            failures.append(f"{entry.case_id}: missing private expected.json")
            continue
        if _sha256_file(expected_path) != entry.expected_sha256:
            failures.append(f"{entry.case_id}: private expected hash mismatch")
            continue

        case_payload = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        expected = ExpectedCaseOutcome.model_validate_json(
            expected_path.read_text(encoding="utf-8")
        )
        if expected.case_id != entry.case_id:
            failures.append(f"{entry.case_id}: expected case identity mismatch")
            continue
        if expected.terminal_ticket_id != case_payload["ticket_id"]:
            failures.append(f"{entry.case_id}: expected terminal ticket mismatch")
            continue
        private_hash_matches += 1

    config = load_account_config(repo_root / config_path)
    profile = get_profile(config, R5_PROFILE_NAME)
    profile_matches = (
        profile.profile_name == R5_PROFILE_NAME
        and profile.model_id == R5_MODEL_ID
        and profile.protocol is ProviderProtocol.OPENAI_COMPATIBLE
    )
    if not profile_matches:
        failures.append("R5 selected endpoint profile does not match frozen identity")

    m3d_budget_matches = (
        M3D_IDENTITY.model_id == R5_MODEL_ID
        and M3D_IDENTITY.profile_name == R5_PROFILE_NAME
        and M3D_BUDGET.max_model_calls == manifest.max_model_calls
        and M3D_BUDGET.max_tool_actions == manifest.max_tool_actions
        and M3D_BUDGET.trajectory_deadline_seconds == manifest.trajectory_deadline_seconds
        and M3D_BUDGET.request_deadline_seconds == manifest.request_deadline_seconds
        and M3D_BUDGET.max_completion_tokens == manifest.max_completion_tokens
    )
    if not m3d_budget_matches:
        failures.append("M3D runtime/budget identity drifted from R5 manifest")

    r4_quality_matches = _validate_r4_quality_receipt(repo_root)
    if not r4_quality_matches:
        failures.append("local R4 quality receipt is missing or does not prove PASS")

    catalog = load_r4_template_catalog(repo_root)
    validation_ids = {
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.VALIDATION
        for case_id in template.instance_ids
    }
    locked_ids = {
        case_id
        for template in catalog.templates
        if template.partition is BenchmarkPartition.LOCKED
        for case_id in template.instance_ids
    }
    selected = set(manifest.case_order)

    return R5PreflightReceipt(
        status="PASS" if not failures else "FAIL",
        r4_qualified_commit=R5_R4_QUALIFIED_COMMIT,
        current_head=head,
        r4_is_ancestor_of_head=ancestor,
        case_count=len(manifest.case_order),
        public_hash_match_count=public_hash_matches,
        private_expected_hash_match_count=private_hash_matches,
        catalog_case_order_matches=not any("case order differs" in failure for failure in failures),
        profile_matches=profile_matches,
        m3d_budget_matches=m3d_budget_matches,
        r4_quality_receipt_matches=r4_quality_matches,
        validation_cases_selected=len(selected & validation_ids),
        locked_cases_selected=len(selected & locked_ids),
        failures=tuple(failures),
    )


def _validate_r4_quality_receipt(repo_root: Path) -> bool:
    path = repo_root / "runs" / "r4_benchmark_quality" / "summary.json"
    if not path.is_file():
        return False

    payload_raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload_raw, dict):
        return False

    payload: dict[str, object] = {str(key): value for key, value in payload_raw.items()}
    return (
        payload.get("status") == "PASS"
        and payload.get("validated_case_count") == 120
        and payload.get("negative_control_count") == 520
        and payload.get("replay_failure_count") == 0
        and payload.get("negative_control_failure_count") == 0
    )


def _git_output(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
