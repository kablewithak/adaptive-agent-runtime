from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.evaluation.benchmark_authoring import load_r4_template_catalog
from adaptive_runtime.evaluation.benchmark_program import (
    BenchmarkPartition,
    HarbourDeskFailureFamily,
)


class BenchmarkQualityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TemplateDiversity(BenchmarkQualityContract):
    template_id: str
    family: HarbourDeskFailureFamily
    partition: BenchmarkPartition
    case_count: int
    unique_structural_fingerprint_count: int


class R4PublicCoverageSummary(BenchmarkQualityContract):
    case_count: int
    development_case_count: int
    validation_case_count: int
    exposed_template_count: int
    family_case_counts: dict[str, int]
    family_development_counts: dict[str, int]
    family_validation_counts: dict[str, int]
    unique_mechanism_count: int
    minimum_template_structural_diversity: int
    templates: tuple[TemplateDiversity, ...]
    passed: bool


def analyze_r4_public_benchmark(repo_root: Path) -> R4PublicCoverageSummary:
    catalog = load_r4_template_catalog(repo_root)
    visible_root = repo_root / "benchmarks" / "harbourdesk" / "r4"

    templates = tuple(
        template
        for template in catalog.templates
        if template.partition is not BenchmarkPartition.LOCKED
    )

    family_case_counts: Counter[str] = Counter()
    family_development_counts: Counter[str] = Counter()
    family_validation_counts: Counter[str] = Counter()
    mechanism_keys: set[str] = set()
    diversity: list[TemplateDiversity] = []

    observed_case_ids: set[str] = set()

    for template in templates:
        if template.mechanism_key is None:
            raise ValueError("materialized template is missing mechanism_key")
        mechanism_keys.add(template.mechanism_key)

        fingerprints: set[str] = set()
        partition_root = visible_root / template.partition.value

        for case_id in template.instance_ids:
            case_dir = partition_root / case_id
            if not case_dir.is_dir():
                raise ValueError(f"missing public case directory: {case_dir}")
            if case_id in observed_case_ids:
                raise ValueError(f"duplicate public case identity: {case_id}")
            observed_case_ids.add(case_id)

            state = HarbourDeskVisibleState.model_validate_json(
                (case_dir / "initial_state.json").read_text(encoding="utf-8")
            )
            fingerprints.add(structural_fingerprint(state))

            family_case_counts[template.family.value] += 1
            if template.partition is BenchmarkPartition.DEVELOPMENT:
                family_development_counts[template.family.value] += 1
            elif template.partition is BenchmarkPartition.VALIDATION:
                family_validation_counts[template.family.value] += 1

        diversity.append(
            TemplateDiversity(
                template_id=template.template_id,
                family=template.family,
                partition=template.partition,
                case_count=len(template.instance_ids),
                unique_structural_fingerprint_count=len(fingerprints),
            )
        )

    development_count = sum(family_development_counts.values())
    validation_count = sum(family_validation_counts.values())
    minimum_diversity = min(item.unique_structural_fingerprint_count for item in diversity)

    expected_family_counts = {family.value: 20 for family in HarbourDeskFailureFamily}
    expected_development_counts = {family.value: 15 for family in HarbourDeskFailureFamily}
    expected_validation_counts = {family.value: 5 for family in HarbourDeskFailureFamily}

    passed = (
        len(observed_case_ids) == 120
        and development_count == 90
        and validation_count == 30
        and len(templates) == 24
        and len(mechanism_keys) == 24
        and dict(family_case_counts) == expected_family_counts
        and dict(family_development_counts) == expected_development_counts
        and dict(family_validation_counts) == expected_validation_counts
        and minimum_diversity == 5
        and not (visible_root / "locked").exists()
    )

    return R4PublicCoverageSummary(
        case_count=len(observed_case_ids),
        development_case_count=development_count,
        validation_case_count=validation_count,
        exposed_template_count=len(templates),
        family_case_counts=dict(family_case_counts),
        family_development_counts=dict(family_development_counts),
        family_validation_counts=dict(family_validation_counts),
        unique_mechanism_count=len(mechanism_keys),
        minimum_template_structural_diversity=minimum_diversity,
        templates=tuple(diversity),
        passed=passed,
    )


def structural_fingerprint(state: HarbourDeskVisibleState) -> str:
    account_order = {
        account.account_id: index
        for index, account in enumerate(sorted(state.accounts, key=lambda item: item.account_id))
    }

    subscriptions = tuple(
        (
            account_order.get(item.account_id, -1),
            item.plan_id,
            item.status.value,
            item.revision,
            _relative_hours(state.frozen_at, item.cancellation_effective_at),
        )
        for item in sorted(
            state.subscriptions,
            key=lambda record: record.subscription_id,
        )
    )
    entitlements = tuple(
        sorted(
            (
                account_order.get(item.account_id, -1),
                item.feature_id,
                item.source_subscription_revision,
                item.enabled,
                item.revision,
            )
            for item in state.entitlements
        )
    )
    approvals = tuple(
        sorted(
            (
                account_order.get(item.account_id, -1),
                item.permitted_action.value,
                _relative_hours(state.frozen_at, item.issued_at),
                _relative_hours(state.frozen_at, item.expires_at),
            )
            for item in state.approvals
        )
    )
    operations = tuple(
        sorted(
            (
                account_order.get(item.account_id, -1),
                item.action.value,
                item.status.value,
                item.before_revision,
                item.after_revision,
                item.effective_write,
            )
            for item in state.operations
        )
    )
    tickets = tuple(
        (
            account_order.get(item.account_id, -1),
            _requester_is_authorised(state, item.account_id, item.requesting_contact),
            len(item.notes),
        )
        for item in sorted(state.tickets, key=lambda record: record.ticket_id)
    )
    policies = tuple(
        sorted(
            (
                item.version,
                _relative_hours(state.frozen_at, item.valid_from),
                _relative_hours(state.frozen_at, item.valid_to),
            )
            for item in state.policies
        )
    )

    canonical = repr(
        (
            subscriptions,
            entitlements,
            approvals,
            operations,
            tickets,
            policies,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _requester_is_authorised(
    state: HarbourDeskVisibleState,
    account_id: str,
    requesting_contact: str,
) -> bool:
    account = next(
        (item for item in state.accounts if item.account_id == account_id),
        None,
    )
    return account is not None and requesting_contact in account.authorised_contacts


def _relative_hours(
    frozen_at: datetime,
    value: datetime | None,
) -> int | None:
    if value is None:
        return None
    return round((value - frozen_at).total_seconds() / 3600)
