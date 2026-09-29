from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r5e import run_r5e_precheck


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    receipt = run_r5e_precheck(
        repo_root,
        config_path=args.config,
    )

    out_dir = repo_root / "runs" / "r5e_precheck"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "summary.json"
    out_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"R5E_PRECHECK_STATUS={receipt.status}")
    print(f"R5E_SCREEN_CASES={receipt.screen_case_count}")
    print(f"R5E_SCREEN_TEMPLATES={receipt.screen_template_count}")
    print(
        "R5E_SCREEN_FAMILY_COUNTS="
        + json.dumps(
            receipt.screen_family_case_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R5E_BASELINE_SUBSET_PASSES={receipt.baseline_subset.pass_count}")
    print(f"R5E_BASELINE_SUBSET_PASS_RATE={receipt.baseline_subset.pass_rate:.6f}")
    print(
        f"R5E_BASELINE_SUBSET_USAGE_COMPLETE={str(receipt.baseline_subset.usage_complete).upper()}"
    )
    print(
        f"R5E_BASELINE_SUBSET_INFERENCE_TOKENS={receipt.baseline_subset.observed_inference_tokens}"
    )
    print(
        "R5E_BASELINE_SUBSET_FAMILY_PASSES="
        + json.dumps(
            receipt.baseline_subset.family_pass_counts,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print("R5E_ELIGIBLE_PROFILES=" + ",".join(receipt.eligible_profile_names))
    print(
        "R5E_PROFILE_QUALIFICATIONS="
        + json.dumps(
            [profile.model_dump(mode="json") for profile in receipt.profiles],
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R5E_R5D_STATUS_PASS={str(receipt.r5d_status_pass).upper()}")
    print("R5E_R5D_SUMMARY_SHA256=" + str(receipt.r5d_summary_sha256 or ""))
    print("R5E_R5D_REPORT_SHA256=" + str(receipt.r5d_report_sha256 or ""))
    print("R5E_PRECHECK_FAILURES=" + json.dumps(receipt.failures, separators=(",", ":")))
    print(f"R5E_PRECHECK_RECEIPT={out_path.relative_to(repo_root)}")

    return 0 if receipt.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
