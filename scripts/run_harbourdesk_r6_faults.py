from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r6_faults import (
    R6A_FROZEN_COMMIT,
    run_r6_fault_program,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--run-id",
        default="r6b-deterministic-faults-20260929-01",
    )
    parser.add_argument(
        "--confirm-r6-fault-execution",
        action="store_true",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if not args.confirm_r6_fault_execution:
        raise SystemExit("explicit --confirm-r6-fault-execution is required")

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
        raise SystemExit("tracked working tree is not clean; refusing R6B execution")

    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            R6A_FROZEN_COMMIT,
            "HEAD",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise SystemExit("frozen R6A commit is not an ancestor of HEAD")

    evidence_dir = repo_root / "runs" / "r6_faults" / args.run_id
    receipt = run_r6_fault_program(
        repo_root=repo_root,
        run_id=args.run_id,
        candidate_commit=current_head,
        evidence_dir=evidence_dir,
    )

    print(f"R6B_EXECUTION_STATUS={receipt.execution_status}")
    print(f"R6B_DECISION={receipt.decision}")
    print(f"R6B_COMMIT={receipt.candidate_commit}")
    print(f"R6B_CASES={receipt.case_count}")
    print(f"R6B_COMPLETE_CASES={receipt.complete_case_count}")
    print(f"R6B_PASS_CASES={receipt.pass_case_count}")
    print(f"R6B_FAILED_CASES={receipt.failed_case_count}")
    print(f"R6B_ERROR_CASES={receipt.error_case_count}")
    print(f"R6B_INVARIANT_FAILURES={receipt.invariant_failure_count}")
    print(f"R6B_UNEXPECTED_EFFECTIVE_WRITES={receipt.unexpected_effective_writes}")
    print(f"R6B_EVIDENCE_COMPLETE={str(receipt.evidence_complete).upper()}")
    print(f"R6B_EXTERNAL_PROVIDER_CALLS={receipt.external_provider_calls}")
    print(f"R6B_LIVE_MODEL_CALLS={receipt.live_model_calls}")
    print(
        "R6B_FAMILY_PASS_COUNTS="
        + json.dumps(
            receipt.family_pass_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R6B_FAULT_PROGRAM_SHA256={receipt.fault_program_sha256}")
    print(f"R6B_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0 if receipt.decision == "PASS" else 1


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
