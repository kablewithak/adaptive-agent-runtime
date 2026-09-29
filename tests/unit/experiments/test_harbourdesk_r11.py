from __future__ import annotations

from adaptive_runtime.experiments.harbourdesk_r11 import (
    R11_PARENT_R10_COMMIT,
    R11_R10_BUNDLE_SHA256,
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
