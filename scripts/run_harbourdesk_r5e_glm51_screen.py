from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import subprocess
from pathlib import Path

from adaptive_runtime.contracts.config import get_profile, load_account_config
from adaptive_runtime.experiments.harbourdesk_r5e import run_r5e_precheck
from adaptive_runtime.experiments.harbourdesk_r5e_screen import (
    R5EC_PROFILE_NAME,
    R5EC_QUALIFICATION_RECEIPT_SHA256,
    load_r5ec_screen_inputs,
    run_r5ec_screen,
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
        default="r5ec-glm51-challenger-screen-20260928-01",
    )
    parser.add_argument("--confirm-live-screen", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if not args.confirm_live_screen:
        raise SystemExit("explicit --confirm-live-screen is required")

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
        raise SystemExit("tracked working tree is not clean")

    precheck = run_r5e_precheck(repo_root, config_path=args.config)
    if precheck.status != "PASS":
        raise SystemExit("R5E precheck is not PASS")
    if R5EC_PROFILE_NAME not in precheck.eligible_profile_names:
        raise SystemExit("primary-openai is not an eligible R5E challenger")

    qualification_path = (
        repo_root
        / "runs"
        / "r5e_qualification"
        / "r5eb-glm51-capability-20260928-01"
        / "summary.json"
    )
    if _sha256_file(qualification_path) != R5EC_QUALIFICATION_RECEIPT_SHA256:
        raise SystemExit("R5EB qualification receipt hash mismatch")

    config = load_account_config(repo_root / args.config)
    profile = get_profile(config, R5EC_PROFILE_NAME)
    inputs = load_r5ec_screen_inputs(repo_root)

    evidence_dir = repo_root / "runs" / "r5e_screen" / args.run_id

    api_key = _api_key()
    with HuaweiOpenAIAdapter(profile=profile, api_key=api_key) as provider:
        receipt = run_r5ec_screen(
            repo_root=repo_root,
            inputs=inputs,
            provider=provider,
            profile=profile,
            run_id=args.run_id,
            candidate_commit=current_head,
            evidence_dir=evidence_dir,
        )

    print(f"R5EC_STATUS={receipt.status}")
    print(f"R5EC_DECISION={receipt.decision}")
    print(f"R5EC_COMMIT={receipt.candidate_commit}")
    print(f"R5EC_PROFILE={receipt.challenger_profile_name}")
    print(f"R5EC_MODEL={receipt.challenger_model_id}")
    print(f"R5EC_CASES={receipt.case_count}")
    print(f"R5EC_PASSES={receipt.pass_count}")
    print(f"R5EC_PASS_RATE={receipt.pass_rate:.6f}")
    print(f"R5EC_BASELINE_PASSES={receipt.baseline_pass_count}")
    print(f"R5EC_PASS_DELTA={receipt.pass_delta}")
    print(f"R5EC_PAIRED_CHALLENGER_WINS={receipt.paired_challenger_wins}")
    print(f"R5EC_PAIRED_BASELINE_WINS={receipt.paired_baseline_wins}")
    print(f"R5EC_PAIRED_BOTH_PASS={receipt.paired_both_pass}")
    print(f"R5EC_PAIRED_BOTH_FAIL={receipt.paired_both_fail}")
    print(f"R5EC_HARD_FAMILY_PASSES={receipt.hard_family_pass_count}")
    print(f"R5EC_BASELINE_HARD_FAMILY_PASSES={receipt.baseline_hard_family_pass_count}")
    print("R5EC_FAMILY_PASSES=" + _compact_json(receipt.family_pass_counts))
    print("R5EC_BASELINE_FAMILY_PASSES=" + _compact_json(receipt.baseline_family_pass_counts))
    print(f"R5EC_USAGE_COMPLETE={str(receipt.usage_complete).upper()}")
    print(f"R5EC_INFERENCE_TOKENS={receipt.observed_inference_tokens}")
    print(f"R5EC_PROVIDER_ERRORS={receipt.provider_error_count}")
    print("R5EC_STOP_COUNTS=" + _compact_json(receipt.stop_counts))
    print("R5EC_SCORING_FAILURE_COUNTS=" + _compact_json(receipt.scoring_failure_counts))
    print(f"R5EC_DETERMINISTIC_CONTROL_VIOLATIONS={receipt.deterministic_control_violation_count}")
    print(f"R5EC_WRITES_FROM_MULTI_TOOL_BATCHES={receipt.writes_from_multi_tool_batches}")
    print(f"R5EC_EVIDENCE_DIR={evidence_dir.relative_to(repo_root)}")
    return 0


def _compact_json(value: object) -> str:
    import json

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
