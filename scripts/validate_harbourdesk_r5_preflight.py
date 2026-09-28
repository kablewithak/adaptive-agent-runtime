from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r5 import run_r5_preflight


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the frozen HarbourDesk R5 90-case development reference "
            "boundary without making provider calls."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/account.local.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    receipt = run_r5_preflight(
        repo_root,
        config_path=args.config,
    )

    receipt_dir = repo_root / "runs" / "r5_preflight"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "summary.json"
    receipt_path.write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"R5_PREFLIGHT_STATUS={receipt.status}")
    print(f"R5_PREFLIGHT_R4_COMMIT={receipt.r4_qualified_commit}")
    print(f"R5_PREFLIGHT_HEAD={receipt.current_head}")
    print(f"R5_PREFLIGHT_R4_ANCESTOR={str(receipt.r4_is_ancestor_of_head).upper()}")
    print(f"R5_PREFLIGHT_CASES={receipt.case_count}")
    print(f"R5_PREFLIGHT_PUBLIC_HASH_MATCHES={receipt.public_hash_match_count}")
    print(f"R5_PREFLIGHT_PRIVATE_EXPECTED_HASH_MATCHES={receipt.private_expected_hash_match_count}")
    print(f"R5_PREFLIGHT_CATALOG_ORDER_MATCH={str(receipt.catalog_case_order_matches).upper()}")
    print(f"R5_PREFLIGHT_PROFILE_MATCH={str(receipt.profile_matches).upper()}")
    print(f"R5_PREFLIGHT_M3D_BUDGET_MATCH={str(receipt.m3d_budget_matches).upper()}")
    print(f"R5_PREFLIGHT_R4_QUALITY_RECEIPT={str(receipt.r4_quality_receipt_matches).upper()}")
    print(f"R5_PREFLIGHT_VALIDATION_CASES_SELECTED={receipt.validation_cases_selected}")
    print(f"R5_PREFLIGHT_LOCKED_CASES_SELECTED={receipt.locked_cases_selected}")
    print("R5_PREFLIGHT_FAILURES=" + json.dumps(receipt.failures, separators=(",", ":")))
    print(f"R5_PREFLIGHT_RECEIPT={receipt_path.relative_to(repo_root)}")

    return 0 if receipt.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
