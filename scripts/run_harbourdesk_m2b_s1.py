from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_m2b_s1 import (
    run_m2b_s1_audit,
    write_m2b_s1_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the offline HarbourDesk M2B-S1 structural audit."
    )
    parser.add_argument("--m2b-summary", type=Path, required=True)
    parser.add_argument("--reference-summary", type=Path, required=True)
    parser.add_argument("--alternative-summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd()
    evidence_dir = Path("runs") / "m2b-s1" / args.run_id
    receipt_path = evidence_dir / "summary.json"

    receipt = run_m2b_s1_audit(
        repo_root=repo_root,
        m2b_summary_path=args.m2b_summary,
        reference_summary_path=args.reference_summary,
        alternative_summary_path=args.alternative_summary,
    )
    write_m2b_s1_receipt(receipt_path, receipt)

    print("M2B_S1_STATUS=complete")
    print(f"M2B_S1_CASES={receipt.case_count}")
    print(
        "M2B_S1_SIGNATURE_GROUPS="
        f"{receipt.signature_group_count}"
    )
    print(
        "M2B_S1_MIXED_SIGNATURE_GROUPS="
        f"{receipt.mixed_signature_group_count}"
    )
    print(
        "M2B_S1_EXACT_SIGNATURE_SEPARABLE="
        f"{str(receipt.exact_signature_separable).upper()}"
    )
    print(f"M2B_S1_PREDICATES={receipt.predicate_count}")
    print(
        "M2B_S1_PASSING_PREDICATES="
        f"{receipt.passing_predicate_count}"
    )
    print(f"M2B_S1_DECISION={receipt.decision.value}")

    best = receipt.best_passing_predicate
    if best is not None:
        print(f"M2B_S1_BEST_RULE={best.rule_id}")
        print(f"M2B_S1_BEST_PASSES={best.verified_passes}")
        print(f"M2B_S1_BEST_TOKENS={best.inference_tokens}")
        print(
            "M2B_S1_BEST_TOKENS_PER_SUCCESS="
            f"{best.tokens_per_verified_success:.6f}"
        )
        print(
            "M2B_S1_BEST_ALTERNATIVE_CASES="
            f"{','.join(best.alternative_case_ids)}"
        )

    for evaluation in receipt.all_passing_predicates:
        print(
            "M2B_S1_PASSING_RULE="
            f"{evaluation.rule_id}|passes={evaluation.verified_passes}|"
            f"tokens={evaluation.inference_tokens}|"
            f"tokens_per_success="
            f"{evaluation.tokens_per_verified_success:.6f}|"
            f"alternative_cases="
            f"{','.join(evaluation.alternative_case_ids)}"
        )

    print(f"M2B_S1_EVIDENCE_DIR={evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
