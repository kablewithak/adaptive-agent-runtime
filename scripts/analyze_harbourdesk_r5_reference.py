from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r5_analysis import (
    analyze_r5_reference,
    render_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("runs/r5_reference/r5-glm52-development-reference-20260928-01"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/r5_analysis/r5d-20260928-01"),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    receipt = analyze_r5_reference(repo_root / args.run_dir)

    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(receipt), encoding="utf-8")

    print(f"R5D_STATUS={receipt.status}")
    print(f"R5D_CASES={receipt.case_count}")
    print(f"R5D_PER_CASE_RECEIPT_MATCHES={receipt.per_case_receipt_match_count}")
    print(f"R5D_TRACE_HASH_MATCHES={receipt.trace_hash_match_count}")
    print(f"R5D_TRACE_FINAL_STATE_MATCHES={receipt.trace_final_state_match_count}")
    print(f"R5D_SCORE_PASSES={receipt.score_pass_count}")
    print(f"R5D_SCORE_FAILURES={receipt.score_fail_count}")
    print(f"R5D_TERMINAL_FAILURES={receipt.terminal_failure_count}")
    print(f"R5D_NONTERMINAL_FAILURES={receipt.nonterminal_failure_count}")
    print(f"R5D_USAGE_INCOMPLETE_CASES={receipt.usage_incomplete_case_count}")
    print("R5D_USAGE_INCOMPLETE_CASE_IDS=" + ",".join(receipt.usage_incomplete_case_ids))
    print("R5D_PROVIDER_ERROR_CASE_IDS=" + ",".join(receipt.provider_error_case_ids))
    print("R5D_MODEL_CALL_BUDGET_CASE_IDS=" + ",".join(receipt.model_call_budget_case_ids))
    print(
        "R5D_MODEL_TEXT_WITHOUT_TERMINAL_CASE_IDS="
        + ",".join(receipt.model_text_without_terminal_case_ids)
    )
    print(f"R5D_EFFICIENCY_STATUS={receipt.efficiency_status}")
    print(
        "R5D_FAILURE_SIGNATURE_COUNTS="
        + json.dumps(receipt.failure_signature_counts, sort_keys=True, separators=(",", ":"))
    )
    print(
        "R5D_FAMILY_METRICS="
        + json.dumps(
            {k: v.model_dump(mode="json") for k, v in receipt.family_metrics.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(
        "R5D_TEMPLATE_METRICS="
        + json.dumps(
            {k: v.model_dump(mode="json") for k, v in receipt.template_metrics.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print("R5D_INTEGRITY_FAILURES=" + json.dumps(receipt.integrity_failures, separators=(",", ":")))
    print(f"R5D_SUMMARY={summary_path.relative_to(repo_root)}")
    print(f"R5D_REPORT={report_path.relative_to(repo_root)}")
    return 0 if receipt.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
