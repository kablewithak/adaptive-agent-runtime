from __future__ import annotations

from pathlib import Path

from adaptive_runtime.environment.end_to_end_rehearsal import (
    EndToEndRehearsalStatus,
    run_manual_end_to_end_rehearsal,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    summary = run_manual_end_to_end_rehearsal(repo_root)
    receipt_dir = repo_root / "runs" / "p1_5_end_to_end_rehearsal"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "summary.json"
    receipt_path.write_text(
        summary.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"END_TO_END_REHEARSAL_STATUS={summary.status.value}")
    print(f"END_TO_END_REHEARSAL_CASE_COUNT={summary.case_count}")
    print(f"END_TO_END_REHEARSAL_PASSED_CASE_COUNT={summary.passed_case_count}")
    print(f"END_TO_END_REHEARSAL_TRACE_PASSED_COUNT={summary.trace_passed_count}")
    print(f"END_TO_END_REHEARSAL_SCORER_PASSED_COUNT={summary.scorer_passed_count}")
    print(f"END_TO_END_REHEARSAL_TOTAL_STEP_COUNT={summary.total_step_count}")
    print(
        "END_TO_END_REHEARSAL_EFFECTIVE_BUSINESS_WRITE_COUNT="
        f"{summary.effective_business_write_count}"
    )
    print(f"END_TO_END_REHEARSAL_LLM_CALLS={summary.llm_call_count}")
    print(f"END_TO_END_REHEARSAL_RECEIPT={receipt_path.relative_to(repo_root)}")

    for case in summary.cases:
        print(
            "CASE="
            f"{case.case_id} "
            f"trace_passed={str(case.trace_passed).lower()} "
            f"score_passed={str(case.score_passed).lower()} "
            f"effective_writes={case.new_effective_write_count} "
            f"failures={','.join(case.scoring_failures) or 'none'}"
        )

    return 0 if summary.status is EndToEndRehearsalStatus.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
