from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_harbourdesk_space_public_evidence_boundary() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "validate_harbourdesk_space_evidence.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "H3_STATUS=PASS" in completed.stdout
    assert "H3_FAILURES=[]" in completed.stdout
