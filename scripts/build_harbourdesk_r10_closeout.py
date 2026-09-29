from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r10 import (
    R10_REQUIRED_COMMITS,
    render_closeout_report,
    validate_and_build_closeout,
    write_deterministic_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-r6b-manifest-sha256", required=True)
    parser.add_argument("--expected-r6b-summary-sha256", required=True)
    parser.add_argument(
        "--run-id",
        default="r10-no-candidate-closeout-20260929-01",
    )
    parser.add_argument(
        "--confirm-no-candidate-closeout",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_no_candidate_closeout:
        raise SystemExit("explicit --confirm-no-candidate-closeout is required")

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
        raise SystemExit("tracked working tree is not clean; refusing R10 closeout")

    for required_commit in R10_REQUIRED_COMMITS:
        completed = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                required_commit,
                "HEAD",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise SystemExit(f"required commit is not an ancestor: {required_commit}")

    output_dir = repo_root / "runs" / "r10_closeout" / args.run_id
    if output_dir.exists():
        raise SystemExit(f"R10 output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    receipt, evidence_index = validate_and_build_closeout(
        repo_root=repo_root,
        candidate_commit=current_head,
        expected_r6b_manifest_sha256=(args.expected_r6b_manifest_sha256),
        expected_r6b_summary_sha256=(args.expected_r6b_summary_sha256),
    )

    manifest_path = output_dir / "manifest.json"
    index_path = output_dir / "evidence_index.json"
    verdict_path = output_dir / "final_verdict.json"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"

    manifest = {
        "schema_version": "harbourdesk-r10-manifest-v1",
        "run_id": args.run_id,
        "candidate_commit": current_head,
        "required_ancestor_commits": list(R10_REQUIRED_COMMITS),
        "expected_r6b_manifest_sha256": (args.expected_r6b_manifest_sha256.lower()),
        "expected_r6b_summary_sha256": (args.expected_r6b_summary_sha256.lower()),
        "locked_paired_evaluation": "NOT_RUN",
        "locked_cases_accessed_for_closeout": 0,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_path.write_text(
        evidence_index.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    verdict_path.write_text(
        receipt.final_verdict.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_closeout_report(receipt),
        encoding="utf-8",
    )

    bundle_path = output_dir / "r10_evidence_bundle.zip"
    bundle_sha = write_deterministic_bundle(
        repo_root=repo_root,
        output_path=bundle_path,
        evidence_index=evidence_index,
        generated_files=(
            manifest_path,
            index_path,
            verdict_path,
            summary_path,
            report_path,
        ),
    )
    (output_dir / "r10_evidence_bundle.sha256").write_text(
        f"{bundle_sha}  {bundle_path.name}\n",
        encoding="utf-8",
    )

    print(f"R10_STATUS={receipt.status}")
    print(f"R10_FINAL_VERDICT={receipt.final_verdict.final_verdict}")
    print(f"R10_DEVELOPMENT_DISPOSITION={receipt.final_verdict.development_disposition}")
    print(f"R10_ADAPTIVE_RUNTIME_PROMOTION={receipt.final_verdict.adaptive_runtime_promotion}")
    print(f"R10_LOCKED_PAIRED_EVALUATION={receipt.final_verdict.locked_paired_evaluation}")
    print(
        "R10_LOCKED_CASES_ACCESSED="
        f"{receipt.final_verdict.locked_cases_accessed_for_r7_or_closeout}"
    )
    print(
        "R10_REASON_CODES="
        + json.dumps(
            receipt.final_verdict.reason_codes,
            separators=(",", ":"),
        )
    )
    print(f"R10_EVIDENCE_FILE_COUNT={receipt.evidence_file_count}")
    print(f"R10_EVIDENCE_TOTAL_BYTES={receipt.evidence_total_bytes}")
    print(f"R10_R6B_MANIFEST_SHA256={receipt.r6b_manifest_sha256}")
    print(f"R10_R6B_SUMMARY_SHA256={receipt.r6b_summary_sha256}")
    print(f"R10_BUNDLE_SHA256={bundle_sha}")
    print(
        "R10_INTEGRITY_FAILURES="
        + json.dumps(
            receipt.integrity_failures,
            separators=(",", ":"),
        )
    )
    print(f"R10_OUTPUT_DIR={output_dir.relative_to(repo_root)}")
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
