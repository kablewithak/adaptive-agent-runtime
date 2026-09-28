from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    HarbourDeskEnvironment,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.evaluation.expected import ExpectedCaseOutcome
from adaptive_runtime.evaluation.scorer import score_case

_CALL_ADAPTER: TypeAdapter[EnvironmentCall] = TypeAdapter(EnvironmentCall)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    visible_root = repo_root / "benchmarks" / "harbourdesk" / "r4"
    private_root = repo_root / "evaluation_private" / "harbourdesk" / "r4"
    rules = HarbourDeskBusinessRules.load(
        repo_root / "benchmarks" / "harbourdesk" / "business_rules_v1.json"
    )

    results: list[dict[str, object]] = []
    failures: list[str] = []

    for partition in ("development", "validation"):
        visible_partition = visible_root / partition
        private_partition = private_root / partition
        if not visible_partition.exists() or not private_partition.exists():
            raise SystemExit(f"missing R4 {partition} public/private materialization")

        for case_dir in sorted(path for path in visible_partition.iterdir() if path.is_dir()):
            case_id = case_dir.name
            private_case = private_partition / case_id
            expected_path = private_case / "expected.json"
            rehearsal_path = private_case / "rehearsal.json"
            authoring_path = private_case / "authoring.json"

            if (
                not expected_path.exists()
                or not rehearsal_path.exists()
                or not authoring_path.exists()
            ):
                failures.append(f"{case_id}: missing private authoring artifact")
                continue

            initial = HarbourDeskVisibleState.model_validate_json(
                (case_dir / "initial_state.json").read_text(encoding="utf-8")
            )
            expected = ExpectedCaseOutcome.model_validate_json(
                expected_path.read_text(encoding="utf-8")
            )
            rehearsal = json.loads(rehearsal_path.read_text(encoding="utf-8"))
            authoring = json.loads(authoring_path.read_text(encoding="utf-8"))

            if expected.case_id != case_id or rehearsal["case_id"] != case_id:
                failures.append(f"{case_id}: case identity mismatch")
                continue
            if len(rehearsal["steps"]) > 10:
                failures.append(f"{case_id}: exceeds 10-action rehearsal budget")
                continue
            if authoring["planned_action_count"] != len(rehearsal["steps"]):
                failures.append(f"{case_id}: planned action count drift")
                continue

            with HarbourDeskStore.in_memory() as store:
                store.initialize(initial)
                env = HarbourDeskEnvironment(
                    store=store,
                    rules=rules,
                    tenant_id=rehearsal["tenant_id"],
                    ticket_id=rehearsal["ticket_id"],
                )
                step_failure: str | None = None
                for index, step in enumerate(rehearsal["steps"], 1):
                    call = _CALL_ADAPTER.validate_python(step["call"])
                    observed = env.execute(call)
                    observed_status = observed.status.value
                    observed_error = (
                        None if observed.error_code is None else observed.error_code.value
                    )
                    if observed_status != step["expected_status"]:
                        step_failure = (
                            f"step {index} status {observed_status} != {step['expected_status']}"
                        )
                        break
                    if observed_error != step["expected_error_code"]:
                        step_failure = (
                            f"step {index} error {observed_error} != {step['expected_error_code']}"
                        )
                        break

                if step_failure is not None:
                    failures.append(f"{case_id}: {step_failure}")
                    continue

                final = env.snapshot()

            score = score_case(initial, final, expected)
            if not score.passed:
                codes = sorted(
                    {
                        failure.value
                        for predicate in score.predicate_scores
                        for failure in predicate.failures
                    }
                )
                failures.append(f"{case_id}: scorer failed ({','.join(codes) or 'unknown'})")
                continue

            results.append(
                {
                    "case_id": case_id,
                    "partition": partition,
                    "template_id": authoring["template_id"],
                    "family": authoring["family"],
                    "mechanism_key": authoring["mechanism_key"],
                    "action_count": len(rehearsal["steps"]),
                    "score_passed": True,
                }
            )

    summary = {
        "schema_version": "harbourdesk-r4-materialization-validation-v1",
        "status": "PASS" if not failures and len(results) == 120 else "FAIL",
        "validated_case_count": len(results),
        "expected_case_count": 120,
        "failure_count": len(failures),
        "failures": failures,
        "results": results,
    }
    receipt_dir = repo_root / "runs" / "r4_materialization_validation"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / "summary.json"
    receipt.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"R4_MATERIALIZATION_STATUS={summary['status']}")
    print(f"R4_MATERIALIZATION_VALIDATED_CASES={len(results)}")
    print(f"R4_MATERIALIZATION_FAILURES={len(failures)}")
    print(f"R4_MATERIALIZATION_RECEIPT={receipt.relative_to(repo_root)}")
    if failures:
        for failure in failures:
            print(f"R4_MATERIALIZATION_FAILURE={failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
