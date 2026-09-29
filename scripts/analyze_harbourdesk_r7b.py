from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r7b import (
    analyze_r7b,
    render_r7b_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-r7a-summary-sha256", required=True)
    parser.add_argument(
        "--run-id",
        default="r7b-policy-discovery-20260929-01",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    current_head = _git(repo_root, "rev-parse", "HEAD")
    if current_head != args.expected_head:
        raise SystemExit("HEAD does not match --expected-head")

    dirty = _git(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
    )
    if dirty:
        raise SystemExit("tracked working tree is not clean; refusing R7B analysis")

    output_dir = repo_root / "runs" / "r7b_policy_discovery" / args.run_id
    if output_dir.exists():
        raise SystemExit(f"R7B output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    receipt = analyze_r7b(
        repo_root,
        candidate_commit=current_head,
        expected_r7a_summary_sha256=(args.expected_r7a_summary_sha256.lower()),
    )

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_r7b_markdown(receipt),
        encoding="utf-8",
    )

    candidate_path: Path | None = None
    if receipt.selected_policy is not None:
        candidate_path = output_dir / "candidate_policy.json"
        candidate_path.write_text(
            receipt.selected_policy.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"R7B_STATUS={receipt.status}")
    print(f"R7B_DECISION={receipt.decision}")
    print(f"R7B_COMMIT={receipt.candidate_commit}")
    print(f"R7B_R7A_SUMMARY_SHA256={receipt.r7a_summary_sha256}")
    print(f"R7B_CASES={receipt.case_count}")
    print(f"R7B_TEMPLATES={receipt.template_count}")
    print(f"R7B_PASSES={receipt.pass_count}")
    print(f"R7B_USAGE_COMPLETE_CASES={receipt.usage_complete_case_count}")
    print("R7B_USAGE_INCOMPLETE_CASE_IDS=" + ",".join(receipt.usage_incomplete_case_ids))
    print(
        "R7B_CANDIDATES="
        + json.dumps(
            [
                {
                    "policy": candidate.policy_name,
                    "signals": list(candidate.signals),
                    "pass_loss": candidate.observed_pass_loss_count,
                    "reduction": round(
                        candidate.diagnostic_token_reduction_fraction,
                        6,
                    ),
                    "adapted_cases": candidate.adapted_case_count,
                    "qualifies": candidate.qualifies,
                }
                for candidate in receipt.candidates
            ],
            separators=(",", ":"),
        )
    )
    print("R7B_SELECTED_POLICY=" + (receipt.selected_policy_name or ""))
    print(
        "R7B_SELECTED_POLICY_CV_REDUCTION="
        + (
            ""
            if receipt.selected_policy_cv_reduction_fraction is None
            else (f"{receipt.selected_policy_cv_reduction_fraction:.6f}")
        )
    )
    print(
        "R7B_SELECTED_POLICY_CV_PASS_LOSS="
        + (
            ""
            if receipt.selected_policy_cv_pass_loss_count is None
            else str(receipt.selected_policy_cv_pass_loss_count)
        )
    )
    print(
        "R7B_SELECTED_POLICY_ENTRIES="
        + ("0" if receipt.selected_policy is None else str(len(receipt.selected_policy.entries)))
    )
    print(f"R7B_VALIDATION_CASES_ACCESSED={receipt.validation_cases_accessed}")
    print(f"R7B_LOCKED_CASES_ACCESSED={receipt.locked_cases_accessed}")
    print(f"R7B_PRIVATE_EXPECTED_FILES_ACCESSED={receipt.private_expected_files_accessed}")
    print(f"R7B_EXTERNAL_PROVIDER_CALLS={receipt.external_provider_calls}")
    print(f"R7B_LIVE_MODEL_CALLS={receipt.live_model_calls}")
    print(f"R7B_RUNTIME_MUTATIONS={receipt.runtime_mutations}")
    print(
        "R7B_INTEGRITY_FAILURES="
        + json.dumps(
            receipt.integrity_failures,
            separators=(",", ":"),
        )
    )
    print(f"R7B_SUMMARY={summary_path.relative_to(repo_root)}")
    print(f"R7B_REPORT={report_path.relative_to(repo_root)}")
    print(
        "R7B_CANDIDATE_POLICY="
        + ("" if candidate_path is None else str(candidate_path.relative_to(repo_root)))
    )
    return 0 if receipt.status == "PASS" else 1


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
