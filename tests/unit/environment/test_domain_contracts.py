from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptive_runtime.environment.domain import (
    Approval,
    ApprovalAction,
    ApprovalIssuerType,
    PolicyDocument,
    Subscription,
    SubscriptionStatus,
    Tenant,
)


def test_domain_records_are_frozen() -> None:
    tenant = Tenant(
        tenant_id="tenant-001",
        display_name="Harbour Demo",
        active=True,
    )

    with pytest.raises(ValidationError):
        tenant.active = False


def test_subscription_requires_utc_dates() -> None:
    with pytest.raises(ValidationError):
        Subscription(
            subscription_id="sub-001",
            account_id="acct-001",
            plan_id="team",
            status=SubscriptionStatus.ACTIVE,
            start_at=datetime(2026, 1, 1),
            revision=1,
        )


def test_scheduled_cancellation_requires_effective_date() -> None:
    with pytest.raises(ValidationError):
        Subscription(
            subscription_id="sub-001",
            account_id="acct-001",
            plan_id="team",
            status=SubscriptionStatus.SCHEDULED_CANCELLATION,
            start_at=datetime(2026, 1, 1, tzinfo=UTC),
            revision=2,
        )


def test_policy_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        PolicyDocument(
            document_id="policy-001",
            version=1,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            authority="HarbourDesk Operations",
            body="Current policy text.",
            content_hash="not-a-sha256",
        )


def test_approval_requires_positive_validity_window() -> None:
    issued_at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValidationError):
        Approval(
            approval_id="approval-001",
            tenant_id="tenant-001",
            account_id="acct-001",
            permitted_action=ApprovalAction.RECONCILE_ENTITLEMENT,
            issued_at=issued_at,
            expires_at=issued_at - timedelta(seconds=1),
            issuer_type=ApprovalIssuerType.SYSTEM,
        )
