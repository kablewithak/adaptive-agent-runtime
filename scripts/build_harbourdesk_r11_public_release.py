from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r11 import (
    R11_PARENT_R10_COMMIT,
    build_public_release,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--expected-r10-bundle-sha256",
        required=True,
    )
    parser.add_argument(
        "--run-id",
        default="r11-public-release-20260929-01",
    )
    parser.add_argument(
        "--confirm-public-release",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.confirm_public_release:
        raise SystemExit("explicit --confirm-public-release is required")

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
        raise SystemExit("tracked working tree is not clean; refusing R11 release build")

    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            R11_PARENT_R10_COMMIT,
            "HEAD",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise SystemExit("frozen R10 commit is not an ancestor of HEAD")

    output_dir = repo_root / "runs" / "r11_public_release" / args.run_id
    receipt = build_public_release(
        repo_root=repo_root,
        release_commit=current_head,
        expected_r10_bundle_sha256=(args.expected_r10_bundle_sha256.lower()),
        output_dir=output_dir,
    )

    print(f"R11_STATUS={receipt.status}")
    print(f"R11_COMMIT={receipt.release_commit}")
    print(f"R11_PUBLIC_FILE_COUNT={receipt.public_file_count}")
    print(f"R11_PUBLIC_TOTAL_BYTES={receipt.public_total_bytes}")
    print(f"R11_RELEASE_ZIP_SHA256={receipt.release_zip_sha256}")
    print(f"R11_RAW_TRACES_INCLUDED={str(receipt.raw_traces_included).upper()}")
    print(
        "R11_PRIVATE_EXPECTED_OUTCOMES_INCLUDED="
        f"{str(receipt.private_expected_outcomes_included).upper()}"
    )
    print(f"R11_VALIDATION_CASES_INCLUDED={str(receipt.validation_cases_included).upper()}")
    print(f"R11_LOCKED_CASES_INCLUDED={str(receipt.locked_cases_included).upper()}")
    print(
        "R11_DEVELOPMENT_CASE_PAYLOADS_INCLUDED="
        f"{str(receipt.development_case_payloads_included).upper()}"
    )
    print(
        "R11_PUBLIC_FILES="
        + json.dumps(
            [item.path for item in receipt.public_files],
            separators=(",", ":"),
        )
    )
    print(
        "R11_INTEGRITY_FAILURES="
        + json.dumps(
            receipt.integrity_failures,
            separators=(",", ":"),
        )
    )
    print(f"R11_OUTPUT_DIR={output_dir.relative_to(repo_root)}")
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
