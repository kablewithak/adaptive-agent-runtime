from __future__ import annotations

import json
from pathlib import Path

from adaptive_runtime.experiments.harbourdesk_r6 import (
    load_r6_fault_program,
    r6_contract_summary,
    write_r6_contract_receipt,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    program = load_r6_fault_program(repo_root)
    summary = r6_contract_summary(program)

    receipt_path = repo_root / "runs" / "r6_contract" / "summary.json"
    write_r6_contract_receipt(
        repo_root,
        output_path=receipt_path,
    )

    print(f"R6A_STATUS={summary['status']}")
    print(f"R6A_CASES={summary['case_count']}")
    print(f"R6A_FAMILIES={summary['family_count']}")
    print(
        "R6A_FAMILY_COUNTS="
        + json.dumps(
            summary["family_counts"],
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R6A_PROVIDER_CALLS={summary['provider_calls']}")
    print(f"R6A_LIVE_MODEL_CALLS={summary['live_model_calls']}")
    print(
        "R6A_ACCEPTANCE="
        + json.dumps(
            summary["acceptance"],
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"R6A_RECEIPT={receipt_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
