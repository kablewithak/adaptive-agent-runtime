from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class R6Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R6Acceptance(R6Contract):
    all_cases_complete: Literal[True]
    invariant_failures_required: Literal[0]
    unexpected_effective_writes_required: Literal[0]
    evidence_complete_required: Literal[True]
    partial_program_result: Literal["INCONCLUSIVE"]


class R6FaultCase(R6Contract):
    case_id: str = Field(pattern=r"^r6-p[1-6]-0[1-4]$")
    family: str = Field(pattern=r"^P[1-6]_[A-Z_]+$")
    fault: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    invariants: tuple[str, ...] = Field(min_length=2)


class R6FaultProgram(R6Contract):
    schema_version: Literal["harbourdesk-r6-fault-program-v1"]
    stage: Literal["R6A"]
    provider_calls: Literal[0]
    live_model_calls: Literal[0]
    case_count: Literal[24]
    family_count: Literal[6]
    cases_per_family: Literal[4]
    acceptance: R6Acceptance
    cases: tuple[R6FaultCase, ...]

    @model_validator(mode="after")
    def validate_program_shape(self) -> R6FaultProgram:
        if len(self.cases) != self.case_count:
            raise ValueError("R6 fault case count mismatch")

        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("R6 fault case IDs must be unique")

        family_counts = Counter(case.family for case in self.cases)
        if len(family_counts) != self.family_count:
            raise ValueError("R6 family count mismatch")
        if set(family_counts.values()) != {self.cases_per_family}:
            raise ValueError("R6 requires four cases per family")

        expected_families = {
            "P1_PROVIDER_PROTOCOL",
            "P2_TOOL_REALIZATION",
            "P3_BUDGET_DEADLINE",
            "P4_STORE_IDEMPOTENCY",
            "P5_AUTHORIZATION_POLICY",
            "P6_EVIDENCE_INTEGRITY",
        }
        if set(family_counts) != expected_families:
            raise ValueError("R6 family identities mismatch")

        return self


def load_r6_fault_program(repo_root: Path) -> R6FaultProgram:
    path = repo_root / "benchmarks" / "harbourdesk" / "r6" / "fault_program_v1.json"
    return R6FaultProgram.model_validate_json(path.read_text(encoding="utf-8"))


def r6_contract_summary(program: R6FaultProgram) -> dict[str, object]:
    family_counts = Counter(case.family for case in program.cases)
    return {
        "status": "PASS",
        "case_count": len(program.cases),
        "family_count": len(family_counts),
        "family_counts": dict(sorted(family_counts.items())),
        "provider_calls": program.provider_calls,
        "live_model_calls": program.live_model_calls,
        "acceptance": program.acceptance.model_dump(mode="json"),
    }


def write_r6_contract_receipt(
    repo_root: Path,
    *,
    output_path: Path,
) -> dict[str, object]:
    program = load_r6_fault_program(repo_root)
    summary = r6_contract_summary(program)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
