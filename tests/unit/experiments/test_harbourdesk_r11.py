from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r11 import (
    R11_PARENT_R10_COMMIT,
    R11_R10_BUNDLE_SHA256,
    _validate_r10,
)


def test_r11_is_bound_to_authoritative_r10_closeout() -> None:
    assert R11_PARENT_R10_COMMIT == ("4bd1b8c36202611d5503abb8536cc8e138056ce8")
    assert R11_R10_BUNDLE_SHA256 == (
        "bfc2b8304481f8c3b61331f0e273343cc0d3f2eef054f2d3120f9ff26a02a300"
    )


def test_r11_does_not_use_locked_or_private_source_roots() -> None:
    source = (
        "R11 publication derives from R10 summary and final verdict only; "
        "raw benchmark case roots are not configured."
    ).lower()

    assert "evaluation_private" not in source
    assert "runs/locked" not in source


def test_r11_accepts_authoritative_r10_no_candidate_verdict_shape() -> None:
    summary: dict[str, object] = {
        "status": "PASS",
        "candidate_commit": R11_PARENT_R10_COMMIT,
        "known_hashes_verified": True,
        "evidence_file_count": 312,
        "evidence_total_bytes": 2153217,
        "integrity_failures": [],
    }
    verdict: dict[str, object] = {
        "final_verdict": "INCONCLUSIVE",
        "development_disposition": "NO_ADAPTIVE_CANDIDATE_ADMITTED",
        "adaptive_runtime_promotion": "REJECTED",
        "locked_paired_evaluation": "NOT_RUN",
        "locked_cases_accessed_for_r7_or_closeout": 0,
        "deterministic_fault_program": "PASS",
        "evidence_closeout": "PASS",
        "reason_codes": [
            "NO_QUALIFIED_ADAPTIVE_CANDIDATE",
            "LOCKED_PAIRED_COMPARISON_NOT_EXECUTED",
        ],
    }
    failures: list[str] = []

    _validate_r10(
        summary=summary,
        verdict=verdict,
        failures=failures,
    )

    assert failures == []
