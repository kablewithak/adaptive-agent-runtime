from __future__ import annotations

import subprocess
import sys


def _run_import(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )


def test_evaluation_scorer_imports_in_fresh_interpreter() -> None:
    result = _run_import(
        "from adaptive_runtime.evaluation.scorer import CaseScore, score_case; "
        "print(CaseScore.__name__, score_case.__name__)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CaseScore score_case"


def test_environment_rehearsal_reexports_remain_available() -> None:
    result = _run_import(
        "from adaptive_runtime.environment import "
        "EndToEndCaseResult, run_manual_end_to_end_rehearsal; "
        "print(EndToEndCaseResult.__name__, run_manual_end_to_end_rehearsal.__name__)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("EndToEndCaseResult run_manual_end_to_end_rehearsal")
