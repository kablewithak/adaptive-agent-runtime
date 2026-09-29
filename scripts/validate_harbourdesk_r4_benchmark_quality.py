from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import (
    ApprovalAction,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
    TicketResolutionReasonCode,
    TicketStatus,
)
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    HarbourDeskEnvironment,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.evaluation.benchmark_quality import (
    analyze_r4_public_benchmark,
)
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import ScoringFailureCode, score_case

_CALL_ADAPTER: TypeAdapter[EnvironmentCall] = TypeAdapter(EnvironmentCall)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    private_root = repo_root / "evaluation_private" / "harbourdesk" / "r4"
    visible_root = repo_root / "benchmarks" / "harbourdesk" / "r4"

    coverage = analyze_r4_public_benchmark(repo_root)
    rules = HarbourDeskBusinessRules.load(
        repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    )

    negative_control_counts: Counter[str] = Counter()
    negative_control_failures: list[str] = []
    replay_failures: list[str] = []
    validated_cases = 0

    for partition in ("development", "validation"):
        for case_dir in sorted(
            path for path in (visible_root / partition).iterdir() if path.is_dir()
        ):
            case_id = case_dir.name
            private_case = private_root / partition / case_id

            initial = HarbourDeskVisibleState.model_validate_json(
                (case_dir / "initial_state.json").read_text(encoding="utf-8")
            )
            expected = ExpectedCaseOutcome.model_validate_json(
                (private_case / "expected.json").read_text(encoding="utf-8")
            )
            rehearsal = json.loads((private_case / "rehearsal.json").read_text(encoding="utf-8"))

            final, replay_failure = _replay_case(
                initial=initial,
                rehearsal=rehearsal,
                rules=rules,
            )
            if replay_failure is not None:
                replay_failures.append(f"{case_id}: {replay_failure}")
                continue

            good_score = score_case(initial, final, expected)
            if not good_score.passed:
                replay_failures.append(f"{case_id}: canonical rehearsal no longer passes scorer")
                continue

            validated_cases += 1

            controls = _negative_controls(
                initial=initial,
                final=final,
                expected=expected,
            )
            for control_name, mutated, required_failure in controls:
                negative_control_counts[control_name] += 1
                score = score_case(initial, mutated, expected)
                observed_failures = {
                    failure
                    for predicate_score in score.predicate_scores
                    for failure in predicate_score.failures
                }

                if score.passed or required_failure not in observed_failures:
                    negative_control_failures.append(
                        f"{case_id}:{control_name}: expected {required_failure.value}"
                    )

    expected_negative_controls = {
        "wrong_disposition": 120,
        "wrong_reason_code": 120,
        "missing_required_policy": 90,
        "missing_required_operation": 20,
        "wrong_entitlement_state": 40,
        "wrong_subscription_state": 10,
        "wrong_effective_write_count": 120,
    }

    quality_pass = (
        coverage.passed
        and validated_cases == 120
        and not replay_failures
        and not negative_control_failures
        and dict(negative_control_counts) == expected_negative_controls
    )

    summary = {
        "schema_version": "harbourdesk-r4-benchmark-quality-v1",
        "status": "PASS" if quality_pass else "FAIL",
        "coverage": coverage.model_dump(mode="json"),
        "validated_case_count": validated_cases,
        "expected_case_count": 120,
        "negative_control_count": sum(negative_control_counts.values()),
        "negative_control_counts": dict(negative_control_counts),
        "expected_negative_control_counts": expected_negative_controls,
        "replay_failure_count": len(replay_failures),
        "negative_control_failure_count": len(negative_control_failures),
        "replay_failures": replay_failures,
        "negative_control_failures": negative_control_failures,
    }

    receipt_dir = repo_root / "runs" / "r4_benchmark_quality"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / "summary.json"
    receipt.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"R4_QUALITY_STATUS={summary['status']}")
    print(f"R4_QUALITY_CASES={validated_cases}")
    print(f"R4_QUALITY_EXPOSED_TEMPLATES={coverage.exposed_template_count}")
    print(f"R4_QUALITY_UNIQUE_MECHANISMS={coverage.unique_mechanism_count}")
    print(
        "R4_QUALITY_MIN_TEMPLATE_STRUCTURAL_DIVERSITY="
        f"{coverage.minimum_template_structural_diversity}"
    )
    print(
        "R4_QUALITY_FAMILY_CASE_COUNTS=" + json.dumps(coverage.family_case_counts, sort_keys=True)
    )
    print(f"R4_QUALITY_NEGATIVE_CONTROLS={sum(negative_control_counts.values())}")
    print(f"R4_QUALITY_REPLAY_FAILURES={len(replay_failures)}")
    print(f"R4_QUALITY_NEGATIVE_CONTROL_FAILURES={len(negative_control_failures)}")
    print(f"R4_QUALITY_RECEIPT={receipt.relative_to(repo_root)}")

    return 0 if quality_pass else 1


def _replay_case(
    *,
    initial: HarbourDeskVisibleState,
    rehearsal: dict[str, object],
    rules: HarbourDeskBusinessRules,
) -> tuple[HarbourDeskVisibleState, str | None]:
    with HarbourDeskStore.in_memory() as store:
        store.initialize(initial)
        env = HarbourDeskEnvironment(
            store=store,
            rules=rules,
            tenant_id=str(rehearsal["tenant_id"]),
            ticket_id=str(rehearsal["ticket_id"]),
        )

        steps = rehearsal["steps"]
        if not isinstance(steps, list):
            return initial, "rehearsal steps are not a list"

        for index, raw_step in enumerate(steps, 1):
            if not isinstance(raw_step, dict):
                return initial, f"step {index} is not an object"

            call = _CALL_ADAPTER.validate_python(raw_step["call"])
            observed = env.execute(call)
            observed_status = observed.status.value
            observed_error = None if observed.error_code is None else observed.error_code.value

            if observed_status != raw_step["expected_status"]:
                return (
                    env.snapshot(),
                    f"step {index} status mismatch",
                )
            if observed_error != raw_step["expected_error_code"]:
                return (
                    env.snapshot(),
                    f"step {index} error mismatch",
                )

        return env.snapshot(), None


def _negative_controls(
    *,
    initial: HarbourDeskVisibleState,
    final: HarbourDeskVisibleState,
    expected: ExpectedCaseOutcome,
) -> list[tuple[str, HarbourDeskVisibleState, ScoringFailureCode]]:
    predicate = expected.acceptable_terminal_predicates[0]
    controls: list[tuple[str, HarbourDeskVisibleState, ScoringFailureCode]] = []

    terminal_ticket = next(
        ticket for ticket in final.tickets if ticket.ticket_id == expected.terminal_ticket_id
    )

    wrong_status = next(
        status
        for status in (
            TicketStatus.RESOLVED,
            TicketStatus.PENDING_CLARIFICATION,
            TicketStatus.ESCALATED,
        )
        if status is not terminal_ticket.status
    )
    controls.append(
        (
            "wrong_disposition",
            _replace_ticket(
                final,
                terminal_ticket.model_copy(update={"status": wrong_status}),
            ),
            ScoringFailureCode.DISPOSITION_MISMATCH,
        )
    )

    if predicate.reason_code is not None:
        wrong_reason = next(
            reason for reason in TicketResolutionReasonCode if reason.value != predicate.reason_code
        )
        controls.append(
            (
                "wrong_reason_code",
                _replace_ticket(
                    final,
                    terminal_ticket.model_copy(update={"resolution_reason_code": wrong_reason}),
                ),
                ScoringFailureCode.REASON_CODE_MISMATCH,
            )
        )

    if predicate.required_policy_document_ids:
        controls.append(
            (
                "missing_required_policy",
                _replace_ticket(
                    final,
                    terminal_ticket.model_copy(update={"evidence_document_ids": ()}),
                ),
                ScoringFailureCode.REQUIRED_POLICY_REFERENCE_MISSING,
            )
        )

    if predicate.required_operation_ids:
        controls.append(
            (
                "missing_required_operation",
                _replace_ticket(
                    final,
                    terminal_ticket.model_copy(update={"operation_ids": ()}),
                ),
                ScoringFailureCode.REQUIRED_OPERATION_REFERENCE_MISSING,
            )
        )

    if predicate.expected_entitlements:
        target = predicate.expected_entitlements[0]
        mutated_entitlements = tuple(
            (
                item.model_copy(update={"enabled": not item.enabled})
                if item.account_id == target.account_id and item.feature_id == target.feature_id
                else item
            )
            for item in final.entitlements
        )
        controls.append(
            (
                "wrong_entitlement_state",
                final.model_copy(update={"entitlements": mutated_entitlements}),
                ScoringFailureCode.ENTITLEMENT_MISMATCH,
            )
        )

    if predicate.expected_subscription is not None:
        subscription_id = predicate.expected_subscription.subscription_id
        mutated_subscriptions = tuple(
            (
                item.model_copy(update={"revision": item.revision + 1})
                if item.subscription_id == subscription_id
                else item
            )
            for item in final.subscriptions
        )
        controls.append(
            (
                "wrong_subscription_state",
                final.model_copy(update={"subscriptions": mutated_subscriptions}),
                ScoringFailureCode.SUBSCRIPTION_MISMATCH,
            )
        )

    if predicate.expected_effective_write_count is not None:
        expected_count = predicate.expected_effective_write_count
        if expected_count > 0:
            initial_operation_ids = {item.operation_id for item in initial.operations}
            mutated_operations = tuple(
                item
                for item in final.operations
                if item.operation_id in initial_operation_ids or not item.effective_write
            )
        else:
            account_id = terminal_ticket.account_id
            extra = OperationRecord(
                operation_id=f"mutation-extra-{expected.case_id}",
                tenant_id=terminal_ticket.tenant_id,
                account_id=account_id,
                action=ApprovalAction.RECONCILE_ENTITLEMENT,
                idempotency_key=f"mutation-extra-{expected.case_id}",
                arguments_hash="0" * 64,
                status=OperationStatus.COMMITTED,
                before_revision=1,
                after_revision=2,
                effective_write=True,
            )
            mutated_operations = (*final.operations, extra)

        controls.append(
            (
                "wrong_effective_write_count",
                final.model_copy(update={"operations": mutated_operations}),
                ScoringFailureCode.EFFECTIVE_WRITE_COUNT_MISMATCH,
            )
        )

    return controls


def _replace_ticket(
    state: HarbourDeskVisibleState,
    replacement: object,
) -> HarbourDeskVisibleState:
    if not hasattr(replacement, "ticket_id"):
        raise TypeError("replacement must be a Ticket")
    ticket_id = replacement.ticket_id
    tickets = tuple(replacement if item.ticket_id == ticket_id else item for item in state.tickets)
    return state.model_copy(update={"tickets": tickets})


if __name__ == "__main__":
    raise SystemExit(main())
