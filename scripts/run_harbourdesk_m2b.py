from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_m2b import (
    run_m2b_oracle,
    write_m2b_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the offline HarbourDesk M2B routing oracle analysis."
    )
    parser.add_argument(
        "--reference-summary",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--alternative-summary",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--run-id",
        required=True,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    evidence_dir = Path("runs") / "m2b" / args.run_id
    receipt_path = evidence_dir / "summary.json"

    receipt = run_m2b_oracle(
        reference_summary_path=args.reference_summary,
        alternative_summary_path=args.alternative_summary,
    )
    write_m2b_receipt(receipt_path, receipt)

    best = receipt.best_passing_assignment
    minimum = receipt.minimum_tokens_at_quality_floor

    print("M2B_STATUS=complete")
    print(f"M2B_ORACLE_FEASIBLE={str(receipt.oracle_feasible).upper()}")
    print(f"M2B_ASSIGNMENTS={receipt.candidate_assignment_count}")
    print(f"M2B_MAX_VERIFIED_PASSES={receipt.max_verified_passes}")
    print(
        "M2B_COMPLEMENTARITY="
        f"reference_only:{receipt.complementarity.reference_only_passes},"
        f"alternative_only:{receipt.complementarity.alternative_only_passes},"
        f"both:{receipt.complementarity.both_pass},"
        f"neither:{receipt.complementarity.neither_pass}"
    )

    if best is not None:
        print(f"M2B_BEST_PASSES={best.verified_passes}")
        print(f"M2B_BEST_INFERENCE_TOKENS={best.observed_inference_tokens}")
        print(f"M2B_BEST_TOKENS_PER_SUCCESS={best.observed_tokens_per_verified_success:.6f}")
        print(f"M2B_BEST_GATE={best.overall_status.value}")
        for choice in best.choices:
            print(
                "M2B_CASE_CHOICE="
                f"{choice.case_id}|{choice.selected_model_id}|"
                f"pass={str(choice.score_passed).upper()}|"
                f"tokens={choice.inference_tokens}"
            )

    if minimum is not None:
        print(f"M2B_MIN_QUALITY_FLOOR_TOKENS={minimum.observed_inference_tokens}")
        print(
            "M2B_MIN_QUALITY_FLOOR_TOKENS_PER_SUCCESS="
            f"{minimum.observed_tokens_per_verified_success:.6f}"
        )

    print(f"M2B_EVIDENCE_DIR={evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
