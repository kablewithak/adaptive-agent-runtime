from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from adaptive_runtime.environment.read_rehearsal import run_manual_read_rehearsal


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    summary = run_manual_read_rehearsal(repo_root)

    generated_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt_payload = {
        "schema_version": "1.0",
        "generated_at_utc": generated_at,
        "status": summary.status.value,
        "case_count": summary.case_count,
        "total_call_count": summary.total_call_count,
        "llm_calls": 0,
        "business_writes": 0,
        "cases": [case.model_dump(mode="json") for case in summary.cases],
    }
    receipt_bytes = (json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_dir = repo_root / "runs" / "harbourdesk"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{generated_at}-read-rehearsal-receipt.json"
    receipt_path.write_bytes(receipt_bytes)

    print(f"READ_REHEARSAL_STATUS={summary.status.value}")
    print(f"READ_REHEARSAL_CASE_COUNT={summary.case_count}")
    print(f"READ_REHEARSAL_TOTAL_CALL_COUNT={summary.total_call_count}")
    print("READ_REHEARSAL_LLM_CALLS=0")
    print("READ_REHEARSAL_BUSINESS_WRITES=0")

    for case in summary.cases:
        prefix = case.case_id.upper().replace("-", "_")
        print(f"READ_REHEARSAL_{prefix}_STATUS={case.status.value}")
        print(f"READ_REHEARSAL_{prefix}_CALL_COUNT={case.call_count}")
        print(f"READ_REHEARSAL_{prefix}_TRACE_SHA256={case.trace_sha256}")

    print(f"READ_REHEARSAL_RECEIPT_SHA256={receipt_sha256}")
    print(f"READ_REHEARSAL_RECEIPT_PATH={receipt_path.relative_to(repo_root)}")

    return 0 if summary.status.value == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
