from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import subprocess
from pathlib import Path

from adaptive_runtime.contracts.config import (
    get_profile,
    load_account_config,
    save_account_config,
)
from adaptive_runtime.experiments.harbourdesk_r5e import run_r5e_precheck
from adaptive_runtime.experiments.harbourdesk_r5e_qualification import (
    R5EB_MAX_COMPLETION_TOKENS,
    R5EB_PROFILE_NAME,
    run_glm51_r5e_qualification,
)
from adaptive_runtime.providers.huawei_openai import HuaweiOpenAIAdapter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--run-id",
        default="r5eb-glm51-capability-20260928-01",
    )
    parser.add_argument(
        "--confirm-live-qualification",
        action="store_true",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if not args.confirm_live_qualification:
        raise SystemExit("explicit --confirm-live-qualification is required")

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
        raise SystemExit("tracked working tree is not clean; refusing live qualification")

    precheck = run_r5e_precheck(
        repo_root,
        config_path=args.config,
    )
    if precheck.status != "PASS":
        raise SystemExit("R5E-A precheck is not PASS")

    config_file = repo_root / args.config
    config = load_account_config(config_file)
    profile = get_profile(config, R5EB_PROFILE_NAME)

    output_dir = repo_root / "runs" / "r5e_qualification" / args.run_id
    if output_dir.exists():
        raise SystemExit(f"qualification output exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    api_key = _api_key()
    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_glm51_r5e_qualification(
            provider=provider,
            profile=profile,
            candidate_commit=current_head,
        )

    receipt_path = output_dir / "summary.json"
    receipt_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    receipt_sha = _sha256_file(receipt_path)

    metadata_applied = False
    if receipt.status == "PASS":
        if _is_tracked(repo_root, args.config):
            raise SystemExit(
                "qualification passed, but account.local.json is tracked; "
                "refusing automatic local metadata mutation"
            )

        profile.max_tested_completion_tokens = R5EB_MAX_COMPLETION_TOKENS
        profile.capability_receipt_sha256 = receipt_sha
        save_account_config(config_file, config)
        metadata_applied = True

    print(f"R5EB_STATUS={receipt.status}")
    print(f"R5EB_COMMIT={receipt.candidate_commit}")
    print(f"R5EB_PROFILE={receipt.profile_name}")
    print(f"R5EB_MODEL={receipt.model_id}")
    print(f"R5EB_REQUESTED_MAX_COMPLETION_TOKENS={receipt.requested_max_completion_tokens}")
    print(f"R5EB_RETURNED_MODEL={receipt.returned_model or ''}")
    print(f"R5EB_HTTP_STATUS={'' if receipt.http_status is None else receipt.http_status}")
    print(f"R5EB_USAGE_PRESENT={str(receipt.usage_present).upper()}")
    print(f"R5EB_EXACT_OUTPUT_MATCH={str(receipt.exact_output_match).upper()}")
    print("R5EB_FAILURES=" + ",".join(receipt.failures))
    print(f"R5EB_RECEIPT_SHA256={receipt_sha}")
    print(f"R5EB_LOCAL_PROFILE_METADATA_APPLIED={str(metadata_applied).upper()}")
    print(f"R5EB_RECEIPT={receipt_path.relative_to(repo_root)}")

    return 0 if receipt.status == "PASS" else 1


def _api_key() -> str:
    value = os.environ.get("HUAWEI_MAAS_API_KEY", "").strip()
    if value:
        return value

    entered = getpass.getpass("Huawei MaaS API key (hidden): ").strip()
    if not entered:
        raise ValueError("Huawei MaaS API key is required")
    return entered


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _is_tracked(repo_root: Path, path: Path) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
