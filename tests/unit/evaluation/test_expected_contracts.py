import pytest
from pydantic import ValidationError

from adaptive_runtime.evaluation.expected import (
    ExpectedCaseOutcome,
    ExpectedDisposition,
    ExpectedEntitlementState,
    ExpectedTerminalPredicate,
)


def test_expected_case_accepts_multiple_valid_terminal_predicates() -> None:
    outcome = ExpectedCaseOutcome(
        case_id="HD-MANUAL-001",
        terminal_ticket_id="ticket-001",
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.RESOLUTION,
                expected_entitlements=(
                    ExpectedEntitlementState(
                        account_id="acct-001",
                        feature_id="exports",
                        enabled=True,
                    ),
                ),
                expected_effective_write_count=1,
                max_effective_write_count=1,
            ),
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.ESCALATION,
                reason_code="STATE_CONFLICT_REQUIRES_HUMAN",
                expected_effective_write_count=0,
                max_effective_write_count=0,
            ),
        ),
    )

    assert len(outcome.acceptable_terminal_predicates) == 2


def test_expected_case_requires_at_least_one_terminal_predicate() -> None:
    with pytest.raises(ValidationError):
        ExpectedCaseOutcome(
            case_id="HD-MANUAL-002",
            terminal_ticket_id="ticket-002",
            acceptable_terminal_predicates=(),
        )


def test_write_bounds_cannot_contradict_each_other() -> None:
    with pytest.raises(ValidationError):
        ExpectedTerminalPredicate(
            disposition=ExpectedDisposition.RESOLUTION,
            expected_effective_write_count=2,
            max_effective_write_count=1,
        )
