from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.environment.mutation_rehearsal import (
    run_manual_mutation_rehearsal,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    summary = run_manual_mutation_rehearsal(repo_root)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt_dir = repo_root / "runs" / "harbourdesk"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{timestamp}-mutation-rehearsal-receipt.json"
    receipt_path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("MUTATION_REHEARSAL_STATUS=" + ("pass" if summary.passed else "fail"))
    print(f"MUTATION_REHEARSAL_SCENARIO_COUNT={summary.scenario_count}")
    print(f"MUTATION_REHEARSAL_PASSED_COUNT={summary.passed_count}")
    print(f"MUTATION_REHEARSAL_EXPECTED_REJECTIONS={summary.expected_rejection_count}")
    print(f"MUTATION_REHEARSAL_EFFECTIVE_BUSINESS_WRITES={summary.effective_business_write_count}")
    print(f"MUTATION_REHEARSAL_TICKET_UPDATES={summary.ticket_update_count}")
    print(f"MUTATION_REHEARSAL_LLM_CALLS={summary.llm_call_count}")
    print(f"MUTATION_REHEARSAL_RECEIPT={receipt_path}")

    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
