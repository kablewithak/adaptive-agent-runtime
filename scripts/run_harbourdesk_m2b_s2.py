from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_m2b_s2 import (
    run_m2b_s2_audit,
    write_m2b_s2_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-summary", type=Path, required=True)
    parser.add_argument("--alternative-summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    evidence_dir = Path("runs") / "m2b-s2" / args.run_id
    receipt = run_m2b_s2_audit(
        repo_root=Path.cwd(),
        reference_summary_path=args.reference_summary,
        alternative_summary_path=args.alternative_summary,
    )
    write_m2b_s2_receipt(evidence_dir / "summary.json", receipt)

    print("M2B_S2_STATUS=complete")
    print(f"M2B_S2_CASES={receipt.case_count}")
    print(f"M2B_S2_SIGNATURE_GROUPS={receipt.signature_group_count}")
    print(f"M2B_S2_ASSIGNMENTS={receipt.candidate_assignment_count}")
    print(f"M2B_S2_MAX_VERIFIED_PASSES={receipt.max_verified_passes}")
    print(f"M2B_S2_FEATURE_CEILING_FEASIBLE={str(receipt.feature_ceiling_feasible).upper()}")

    best = receipt.best_passing_assignment
    if best is not None:
        print(f"M2B_S2_BEST_PASSES={best.verified_passes}")
        print(f"M2B_S2_BEST_TOKENS={best.observed_inference_tokens}")
        print(f"M2B_S2_BEST_TOKENS_PER_SUCCESS={best.observed_tokens_per_verified_success:.6f}")
        for choice in best.choices:
            print(
                "M2B_S2_SIGNATURE_CHOICE="
                f"{choice.signature_id}|{choice.selected_model_id}|"
                f"cases={','.join(choice.case_ids)}"
            )

    minimum = receipt.minimum_tokens_at_quality_floor
    if minimum is not None:
        print(f"M2B_S2_MIN_QUALITY_FLOOR_TOKENS={minimum.observed_inference_tokens}")
        print(
            "M2B_S2_MIN_QUALITY_FLOOR_TOKENS_PER_SUCCESS="
            f"{minimum.observed_tokens_per_verified_success:.6f}"
        )
        print(f"M2B_S2_MIN_QUALITY_FLOOR_GATE={minimum.overall_status.value}")

    print(f"M2B_S2_EVIDENCE_DIR={evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
