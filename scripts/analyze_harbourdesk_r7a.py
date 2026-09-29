from __future__ import annotations

import json
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r7a import (
    analyze_r7a,
    render_r7a_markdown,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    receipt = analyze_r7a(repo_root)

    output_dir = repo_root / "runs" / "r7a_feasibility"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"

    summary_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_r7a_markdown(receipt),
        encoding="utf-8",
    )

    oracle = receipt.failure_only_oracle
    family_oracle = receipt.family_oracle
    best = receipt.best_zero_observed_pass_loss_cap

    print(f"R7A_STATUS={receipt.status}")
    print(f"R7A_FEASIBILITY={receipt.feasibility}")
    print(f"R7A_CASES={receipt.case_count}")
    print(f"R7A_PASSES={receipt.score_pass_count}")
    print(f"R7A_USAGE_COMPLETE_CASES={receipt.usage_complete_case_count}")
    print("R7A_USAGE_INCOMPLETE_CASE_IDS=" + ",".join(receipt.usage_incomplete_case_ids))
    print(f"R7A_FAILURE_ONLY_ORACLE_REDUCTION={oracle.diagnostic_token_reduction_fraction:.6f}")
    print(f"R7A_FAMILY_ORACLE_REDUCTION={family_oracle.diagnostic_token_reduction_fraction:.6f}")
    print("R7A_BEST_ZERO_PASS_LOSS_CAP=" + ("" if best is None else str(best.max_model_calls)))
    print(
        "R7A_BEST_ZERO_PASS_LOSS_REDUCTION="
        + ("" if best is None else f"{best.diagnostic_token_reduction_fraction:.6f}")
    )
    print("R7A_QUALIFYING_SIGNALS=" + ",".join(receipt.qualifying_signal_names))
    print(
        "R7A_FAMILY_PASS_ATTEMPT_MAXIMA="
        + json.dumps(
            receipt.family_attempt_maxima_for_observed_passes,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "R7A_FAMILY_CASE_COUNTS="
        + json.dumps(
            receipt.family_case_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "R7A_FAMILY_PASS_COUNTS="
        + json.dumps(
            receipt.family_pass_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R7A_VALIDATION_CASES_ACCESSED={receipt.validation_cases_accessed}")
    print(f"R7A_LOCKED_CASES_ACCESSED={receipt.locked_cases_accessed}")
    print(f"R7A_PRIVATE_EXPECTED_FILES_ACCESSED={receipt.private_expected_files_accessed}")
    print(
        "R7A_INTEGRITY_FAILURES="
        + json.dumps(
            receipt.integrity_failures,
            separators=(",", ":"),
        )
    )
    print(f"R7A_SUMMARY={summary_path.relative_to(repo_root)}")
    print(f"R7A_REPORT={report_path.relative_to(repo_root)}")
    return 0 if receipt.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
