from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

R10_PARENT_R7B_COMMIT = "644c27e757760d1ab7ced0f27b7297377670a454"
R10_REQUIRED_COMMITS: tuple[str, ...] = (
    "0c741192e52916de2330462b9c95bbd31e004924",
    "67d841527d5fb12f9ee1d108b95729ebe6113bcd",
    "1a5253d48b6323bbc21ad012832c2f4f5b6919f2",
    "610e7a03818e0ba8c8b726abb43f3816ef27c933",
    "e990ac34b8893bf59f52c5c02e0613ada0b066df",
    "5fcb3ec2175d8b10c2708b3a45a7e1b4e7e2a56d",
    R10_PARENT_R7B_COMMIT,
)

R5_REFERENCE_DIR = Path("runs/r5_reference/r5-glm52-development-reference-20260928-01")
R5_ANALYSIS_DIR = Path("runs/r5_analysis/r5d-20260928-01")
R5EC_DIR = Path("runs/r5e_screen/r5ec-glm51-challenger-screen-20260928-01")
R6B_DIR = Path("runs/r6_faults/r6b-deterministic-faults-20260929-01")
R7A_DIR = Path("runs/r7a_feasibility")
R7B_DIR = Path("runs/r7b_policy_discovery/r7b-policy-discovery-20260929-01")

R10_EVIDENCE_ROOTS: tuple[Path, ...] = (
    Path("docs/checkpoints/2026-09-28-r4-benchmark-and-final-acceptance-contract.md"),
    Path("benchmarks/harbourdesk/r5/development_reference_manifest_v1.json"),
    Path("benchmarks/harbourdesk/r5/challenger_screen_manifest_v1.json"),
    Path("benchmarks/harbourdesk/r5/challenger_screen_contract_v1.json"),
    Path("benchmarks/harbourdesk/r6/fault_program_v1.json"),
    Path("benchmarks/harbourdesk/r7/policy_discovery_contract_v1.json"),
    Path("benchmarks/harbourdesk/r10/no_candidate_closeout_contract_v1.json"),
    R5_REFERENCE_DIR,
    R5_ANALYSIS_DIR,
    R5EC_DIR,
    Path("runs/r6_contract/summary.json"),
    R6B_DIR,
    R7A_DIR,
    R7B_DIR,
)

R10_KNOWN_HASHES: dict[Path, str] = {
    R5_REFERENCE_DIR / "manifest.json": (
        "e9eab99e4833387285a580dc212405581121f9907c5d9b3b2a7f0572016a0e84"
    ),
    R5_REFERENCE_DIR / "summary.json": (
        "b9525bd704df83f66e6fd9a5083b48412b20882e574edb415d8bf17a237a12f7"
    ),
    R5_ANALYSIS_DIR / "summary.json": (
        "742d8e536ccea12ad957d40390f774dfde88d3a0eb2d374f83925874c0663357"
    ),
    R5_ANALYSIS_DIR / "report.md": (
        "8694ba81eb1d765b31b14f06a56918464d7eb48d3929ad17587a73769acb17b2"
    ),
    R5EC_DIR / "manifest.json": (
        "ddc6840eda426af02c77745475fcc9aecbe7aead06391b12ca91f1a3a29539d7"
    ),
    R5EC_DIR / "summary.json": ("c8e88eaa38e349b73d4be1c7233261e129b9f75c1b7c1b372a9b4d2ba0345e0c"),
    Path("benchmarks/harbourdesk/r6/fault_program_v1.json"): (
        "a33c9dcd118125b68bea375c760e2cf63b1d36cd9defa0bec6e093bd191feb73"
    ),
    R7A_DIR / "summary.json": ("c2e96c66147eca9dc284358e071478d40b6428291944ed4e3e9d4f143c989752"),
    R7B_DIR / "summary.json": ("e9f5939c46e85c6848c2350407854669ffd2f4ffe6e9b6d02b7cc66fa0cc2ada"),
    R7B_DIR / "report.md": ("b0ad8489ff586b09a507ec77b42783ff5f7dfb8cdafebb5d23284b9a0fbe8f52"),
}


class R10Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R10EvidenceFile(R10Contract):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class R10EvidenceIndex(R10Contract):
    schema_version: Literal["harbourdesk-r10-evidence-index-v1"] = (
        "harbourdesk-r10-evidence-index-v1"
    )
    file_count: int = Field(ge=1)
    total_bytes: int = Field(ge=0)
    files: tuple[R10EvidenceFile, ...]


class R10FinalVerdict(R10Contract):
    schema_version: Literal["harbourdesk-r10-final-verdict-v1"] = "harbourdesk-r10-final-verdict-v1"
    final_verdict: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"
    development_disposition: Literal["NO_ADAPTIVE_CANDIDATE_ADMITTED"] = (
        "NO_ADAPTIVE_CANDIDATE_ADMITTED"
    )
    adaptive_runtime_promotion: Literal["REJECTED"] = "REJECTED"
    locked_paired_evaluation: Literal["NOT_RUN"] = "NOT_RUN"
    locked_cases_accessed_for_r7_or_closeout: Literal[0] = 0
    quality_gate: Literal["NOT_RUN"] = "NOT_RUN"
    family_regression_gate: Literal["NOT_RUN"] = "NOT_RUN"
    efficiency_gate: Literal["NOT_RUN"] = "NOT_RUN"
    candidate_safety_gate: Literal["NOT_RUN"] = "NOT_RUN"
    deterministic_fault_program: Literal["PASS"] = "PASS"
    evidence_closeout: Literal["PASS"] = "PASS"
    fixed_reference_development_passes: Literal[43] = 43
    fixed_reference_development_cases: Literal[90] = 90
    challenger_decision: Literal["DO_NOT_PROMOTE"] = "DO_NOT_PROMOTE"
    challenger_passes: Literal[15] = 15
    challenger_cases: Literal[36] = 36
    challenger_baseline_passes: Literal[16] = 16
    fault_cases_passed: Literal[24] = 24
    fault_cases_total: Literal[24] = 24
    r7a_failure_only_oracle_reduction: float
    r7a_best_zero_pass_loss_reduction: float
    r7b_best_nontrivial_reduction: float
    r7b_best_nontrivial_pass_loss: int
    reason_codes: tuple[str, ...] = (
        "NO_QUALIFIED_ADAPTIVE_CANDIDATE",
        "LOCKED_PAIRED_COMPARISON_NOT_EXECUTED",
    )


class R10CloseoutReceipt(R10Contract):
    schema_version: Literal["harbourdesk-r10-closeout-v1"] = "harbourdesk-r10-closeout-v1"
    status: Literal["PASS", "FAIL"]
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    parent_r7b_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    known_hashes_verified: bool
    r6b_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    r6b_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_file_count: int = Field(ge=1)
    evidence_total_bytes: int = Field(ge=0)
    final_verdict: R10FinalVerdict
    integrity_failures: tuple[str, ...]


def validate_and_build_closeout(
    *,
    repo_root: Path,
    candidate_commit: str,
    expected_r6b_manifest_sha256: str,
    expected_r6b_summary_sha256: str,
) -> tuple[R10CloseoutReceipt, R10EvidenceIndex]:
    failures: list[str] = []
    expected_hashes = dict(R10_KNOWN_HASHES)
    expected_hashes[R6B_DIR / "manifest.json"] = expected_r6b_manifest_sha256.lower()
    expected_hashes[R6B_DIR / "summary.json"] = expected_r6b_summary_sha256.lower()

    for relative_path, expected_hash in expected_hashes.items():
        path = repo_root / relative_path
        if not path.is_file():
            failures.append(f"missing_evidence:{relative_path.as_posix()}")
        elif _sha256_file(path) != expected_hash:
            failures.append(f"sha256_mismatch:{relative_path.as_posix()}")

    r5 = _read_json(repo_root / R5_REFERENCE_DIR / "summary.json")
    r5d = _read_json(repo_root / R5_ANALYSIS_DIR / "summary.json")
    r5ec = _read_json(repo_root / R5EC_DIR / "summary.json")
    r6b = _read_json(repo_root / R6B_DIR / "summary.json")
    r7a = _read_json(repo_root / R7A_DIR / "summary.json")
    r7b = _read_json(repo_root / R7B_DIR / "summary.json")

    _validate_receipts(r5=r5, r5d=r5d, r5ec=r5ec, r6b=r6b, r7a=r7a, r7b=r7b, failures=failures)
    evidence_index = build_evidence_index(repo_root)
    verdict = _derive_verdict(r7a, r7b)

    receipt = R10CloseoutReceipt(
        status="PASS" if not failures else "FAIL",
        candidate_commit=candidate_commit,
        parent_r7b_commit=R10_PARENT_R7B_COMMIT,
        known_hashes_verified=not any(
            failure.startswith("missing_evidence:") or failure.startswith("sha256_mismatch:")
            for failure in failures
        ),
        r6b_manifest_sha256=_sha256_file(repo_root / R6B_DIR / "manifest.json"),
        r6b_summary_sha256=_sha256_file(repo_root / R6B_DIR / "summary.json"),
        evidence_file_count=evidence_index.file_count,
        evidence_total_bytes=evidence_index.total_bytes,
        final_verdict=verdict,
        integrity_failures=tuple(failures),
    )
    return receipt, evidence_index


def build_evidence_index(repo_root: Path) -> R10EvidenceIndex:
    files: dict[str, Path] = {}
    for relative_root in R10_EVIDENCE_ROOTS:
        path = repo_root / relative_root
        if path.is_file():
            files[relative_root.as_posix()] = path
            continue
        if not path.is_dir():
            raise FileNotFoundError(f"R10 evidence root missing: {relative_root}")
        for item in sorted(path.rglob("*")):
            if item.is_file():
                files[item.relative_to(repo_root).as_posix()] = item

    indexed = tuple(
        R10EvidenceFile(
            path=relative,
            size_bytes=path.stat().st_size,
            sha256=_sha256_file(path),
        )
        for relative, path in sorted(files.items())
    )
    return R10EvidenceIndex(
        file_count=len(indexed),
        total_bytes=sum(item.size_bytes for item in indexed),
        files=indexed,
    )


def write_deterministic_bundle(
    *,
    repo_root: Path,
    output_path: Path,
    evidence_index: R10EvidenceIndex,
    generated_files: tuple[Path, ...],
) -> str:
    if output_path.exists():
        raise FileExistsError(f"R10 bundle exists: {output_path}")

    entries: dict[str, bytes] = {
        f"evidence/{item.path}": (repo_root / item.path).read_bytes()
        for item in evidence_index.files
    }
    for path in generated_files:
        entries[f"closeout/{path.name}"] = path.read_bytes()

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(
                filename=name,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)
    return _sha256_file(output_path)


def render_closeout_report(receipt: R10CloseoutReceipt) -> str:
    verdict = receipt.final_verdict
    lines = [
        "# HarbourDesk R10 No-Candidate Closeout",
        "",
        f"- Integrity: **{receipt.status}**",
        f"- Final north-star verdict: **{verdict.final_verdict}**",
        f"- Development disposition: **{verdict.development_disposition}**",
        f"- Adaptive runtime promotion: **{verdict.adaptive_runtime_promotion}**",
        f"- Locked paired evaluation: **{verdict.locked_paired_evaluation}**",
        "",
        "## Why the final verdict is INCONCLUSIVE",
        "",
        (
            "The frozen R4 acceptance contract requires a selected fixed "
            "reference and a frozen adaptive candidate to run the same 60 "
            "locked cases. R7B admitted no adaptive candidate. The required "
            "paired locked evidence therefore does not exist, so the R4 "
            "INCONCLUSIVE branch applies."
        ),
        "",
        (
            "This does not make the development decision ambiguous. The "
            "bounded adaptive policy class did not earn implementation or "
            "promotion."
        ),
        "",
        "## Development evidence",
        "",
        (
            "- Fixed GLM-5.2 reference: 43/90 verified development passes; "
            "overall efficiency remained unqualified because hdb-037 had "
            "incomplete usage after a provider error."
        ),
        (
            "- GLM-5.1 challenger: 15/36 versus 16/36 for the frozen "
            "baseline subset; decision DO_NOT_PROMOTE."
        ),
        (
            "- Deterministic fault programme: "
            f"{verdict.fault_cases_passed}/{verdict.fault_cases_total} PASS."
        ),
        (
            "- R7A failure-only oracle diagnostic reduction: "
            f"{verdict.r7a_failure_only_oracle_reduction * 100:.2f}%."
        ),
        (
            "- R7A best zero-observed-pass-loss universal-cap reduction: "
            f"{verdict.r7a_best_zero_pass_loss_reduction * 100:.2f}%."
        ),
        (
            "- R7B best nontrivial bounded-policy reduction: "
            f"{verdict.r7b_best_nontrivial_reduction * 100:.2f}% with "
            f"{verdict.r7b_best_nontrivial_pass_loss} observed pass losses."
        ),
        "",
        "## Gate state",
        "",
        "| Gate | State |",
        "| --- | --- |",
        f"| Quality | {verdict.quality_gate} |",
        f"| Family regression | {verdict.family_regression_gate} |",
        f"| Efficiency | {verdict.efficiency_gate} |",
        f"| Candidate safety | {verdict.candidate_safety_gate} |",
        (f"| Deterministic fault programme | {verdict.deterministic_fault_program} |"),
        f"| Evidence closeout | {verdict.evidence_closeout} |",
        "",
        (
            "The locked benchmark remains unconsumed by R7 or R10. A future "
            "adaptive claim requires a new candidate that earns admission "
            "without using locked outcomes for tuning."
        ),
        "",
    ]
    return "\n".join(lines)


def _derive_verdict(
    r7a: dict[str, object],
    r7b: dict[str, object],
) -> R10FinalVerdict:
    oracle = cast(dict[str, object], r7a["failure_only_oracle"])
    best_cap = cast(
        dict[str, object] | None,
        r7a.get("best_zero_observed_pass_loss_cap"),
    )
    candidates = cast(list[dict[str, object]], r7b["candidates"])
    nontrivial = [
        candidate for candidate in candidates if _as_int(candidate["adapted_case_count"]) > 0
    ]
    if not nontrivial:
        raise ValueError("R7B contains no nontrivial candidate metrics")
    best = max(
        nontrivial,
        key=lambda candidate: (
            _as_float(candidate["diagnostic_token_reduction_fraction"]),
            -_as_int(candidate["observed_pass_loss_count"]),
        ),
    )
    return R10FinalVerdict(
        r7a_failure_only_oracle_reduction=_as_float(oracle["diagnostic_token_reduction_fraction"]),
        r7a_best_zero_pass_loss_reduction=(
            0.0 if best_cap is None else _as_float(best_cap["diagnostic_token_reduction_fraction"])
        ),
        r7b_best_nontrivial_reduction=_as_float(best["diagnostic_token_reduction_fraction"]),
        r7b_best_nontrivial_pass_loss=_as_int(best["observed_pass_loss_count"]),
    )


def _validate_receipts(
    *,
    r5: dict[str, object],
    r5d: dict[str, object],
    r5ec: dict[str, object],
    r6b: dict[str, object],
    r7a: dict[str, object],
    r7b: dict[str, object],
    failures: list[str],
) -> None:
    if not (
        r5.get("status") == "COMPLETE"
        and r5.get("case_count") == 90
        and r5.get("score_pass_count") == 43
        and r5.get("usage_complete") is False
    ):
        failures.append("r5_reference_state_mismatch")

    if not (
        r5d.get("status") == "PASS"
        and r5d.get("case_count") == 90
        and r5d.get("usage_incomplete_case_ids") == ["hdb-037"]
        and r5d.get("integrity_failures") == []
    ):
        failures.append("r5d_state_mismatch")

    if not (
        r5ec.get("status") == "COMPLETE"
        and r5ec.get("decision") == "DO_NOT_PROMOTE"
        and r5ec.get("case_count") == 36
        and r5ec.get("pass_count") == 15
        and r5ec.get("baseline_pass_count") == 16
        and r5ec.get("usage_complete") is True
        and r5ec.get("provider_error_count") == 0
    ):
        failures.append("r5ec_state_mismatch")

    if not (
        r6b.get("execution_status") == "COMPLETE"
        and r6b.get("decision") == "PASS"
        and r6b.get("case_count") == 24
        and r6b.get("pass_case_count") == 24
        and r6b.get("invariant_failure_count") == 0
        and r6b.get("unexpected_effective_writes") == 0
        and r6b.get("evidence_complete") is True
        and r6b.get("external_provider_calls") == 0
        and r6b.get("live_model_calls") == 0
    ):
        failures.append("r6b_state_mismatch")

    if not (
        r7a.get("status") == "PASS"
        and r7a.get("feasibility") == "ADAPTATION_WORTH_INVESTIGATING"
        and r7a.get("case_count") == 90
        and r7a.get("score_pass_count") == 43
        and r7a.get("validation_cases_accessed") == 0
        and r7a.get("locked_cases_accessed") == 0
        and r7a.get("private_expected_files_accessed") == 0
        and r7a.get("integrity_failures") == []
    ):
        failures.append("r7a_state_mismatch")

    if not (
        r7b.get("status") == "PASS"
        and r7b.get("decision") == "NO_POLICY_QUALIFIED"
        and r7b.get("case_count") == 90
        and r7b.get("template_count") == 18
        and r7b.get("pass_count") == 43
        and r7b.get("selected_policy") is None
        and r7b.get("validation_cases_accessed") == 0
        and r7b.get("locked_cases_accessed") == 0
        and r7b.get("private_expected_files_accessed") == 0
        and r7b.get("external_provider_calls") == 0
        and r7b.get("live_model_calls") == 0
        and r7b.get("runtime_mutations") == 0
        and r7b.get("integrity_failures") == []
    ):
        failures.append("r7b_state_mismatch")


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer, got {type(value).__name__}")
    return value


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected number, got {type(value).__name__}")
    return float(value)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
