\
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EXPECTED_RESULTS_SHA256 = "afbb56a7a399a71dc30cb82a57d831b850aeb35894fd76c03b975470758736da"
EXPECTED_PROVENANCE_SHA256 = "2955ede8138f40e32cf8fb5f21da3cef75c88eee136dbc25036b692709d2d58e"
EXPECTED_RELEASE_ZIP_SHA256 = "1ced6ea0cbec2039a41b1bd4974fbc2f400b7bc936ad3b05cfc6788fbd3a7449"

EXPECTED_SOURCE_HASHES = {
    "charts/adaptation_screen.svg": "3c9dd699135c9a4570dafea93cff975ce6d9aeca696fcdc078a5f7702d8b970c",
    "charts/challenger_screen.svg": "5ef74be2c5f4eeac5aabfd4679c0ae8b0def72952579543096bbc0b640b9e976",
    "charts/deterministic_faults.svg": "c6951f75c804bf273f779b860c75587f1e6c16bd8ffd4967f0dcdf9df6b4f5e8",
    "charts/fixed_reference_development.svg": "23452a2132be27541cca620e5237733b4a214c60ad8d237ba68db63fa5f126d4",
    "provenance.json": EXPECTED_PROVENANCE_SHA256,
    "PUBLICATION_NOTES.md": "d34c0133ecefa3d3ccd34438e306d5521a42e21d7e977df4a3b7c7caef97e0a8",
    "README.md": "b9681165e19e8f0f354542cfa702f3b21d5d0431b428827d77d115f5494761c2",
    "results.json": EXPECTED_RESULTS_SHA256,
}

FORBIDDEN_FRONTEND_TOKENS = (
    "evaluation_private/",
    "evaluation_private\\",
    "runs/",
    "runs\\",
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicMetrics(FrozenModel):
    schema_version: Literal["harbourdesk-r11-public-metrics-v1"]
    fixed_reference_model: Literal["glm-5.2"]
    fixed_reference_development_passes: Literal[43]
    fixed_reference_development_cases: Literal[90]
    fixed_reference_development_pass_rate: float
    fixed_reference_efficiency_status: Literal["INCONCLUSIVE"]
    fixed_reference_usage_incomplete_case_count: Literal[1]
    challenger_model: Literal["glm-5.1"]
    challenger_screen_passes: Literal[15]
    challenger_screen_cases: Literal[36]
    challenger_screen_pass_rate: float
    challenger_screen_baseline_passes: Literal[16]
    challenger_screen_baseline_pass_rate: float
    challenger_decision: Literal["DO_NOT_PROMOTE"]
    deterministic_fault_passes: Literal[24]
    deterministic_fault_cases: Literal[24]
    deterministic_fault_pass_rate: float
    r7a_failure_only_oracle_reduction: float
    r7a_best_zero_pass_loss_fixed_cap_reduction: float
    r7b_best_nontrivial_policy_reduction: float
    r7b_best_nontrivial_policy_observed_pass_loss: Literal[2]
    r7b_policy_decision: Literal["NO_POLICY_QUALIFIED"]
    final_verdict: Literal["INCONCLUSIVE"]
    development_disposition: Literal["NO_ADAPTIVE_CANDIDATE_ADMITTED"]
    adaptive_runtime_promotion: Literal["REJECTED"]
    locked_paired_evaluation: Literal["NOT_RUN"]
    locked_cases_accessed: Literal[0]


class PublicProvenance(FrozenModel):
    schema_version: Literal["harbourdesk-r11-provenance-v1"]
    release_commit: Literal["2a0c0977a39dffc7ed75be8f3915ef129649875f"]
    parent_r10_commit: Literal["4bd1b8c36202611d5503abb8536cc8e138056ce8"]
    r10_run_id: Literal["r10-no-candidate-closeout-20260929-01"]
    r10_bundle_sha256: Literal[
        "bfc2b8304481f8c3b61331f0e273343cc0d3f2eef054f2d3120f9ff26a02a300"
    ]
    r6b_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    r6b_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    r7b_summary_sha256: Literal[
        "e9f5939c46e85c6848c2350407854669ffd2f4ffe6e9b6d02b7cc66fa0cc2ada"
    ]
    source_evidence_file_count: Literal[312]
    source_evidence_total_bytes: Literal[2153217]


class MethodologyConstants(FrozenModel):
    efficiency_target_reduction: Literal[0.20]
    source: Literal[
        "docs/checkpoints/2026-09-28-r4-benchmark-and-final-acceptance-contract.md"
    ]
    source_section: Literal["Efficiency gate"]


class SourceRelease(FrozenModel):
    run_id: Literal["r11-public-release-20260929-02"]
    release_zip_sha256: Literal[
        "1ced6ea0cbec2039a41b1bd4974fbc2f400b7bc936ad3b05cfc6788fbd3a7449"
    ]
    public_file_count: Literal[9]
    sha256sums_entries: dict[str, str]


class PublicEvidenceManifest(FrozenModel):
    schema_version: Literal["harbourdesk-space-public-evidence-manifest-v1"]
    source_release: SourceRelease
    checked_in_public_sources: dict[str, str]
    methodology_constants: MethodologyConstants
    display_metric_sources: dict[str, str]
    non_claims: list[str]
    forbidden_source_roots: list[str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def render_typescript(
    metrics: PublicMetrics,
    provenance: PublicProvenance,
    manifest: PublicEvidenceManifest,
) -> str:
    payload = {
        "source": {
            "r11RunId": manifest.source_release.run_id,
            "releaseZipSha256": manifest.source_release.release_zip_sha256,
            "resultsSha256": EXPECTED_RESULTS_SHA256,
            "provenanceSha256": EXPECTED_PROVENANCE_SHA256,
            "releaseCommit": provenance.release_commit,
            "parentR10Commit": provenance.parent_r10_commit,
        },
        "metrics": {
            "fixedReference": {
                "model": metrics.fixed_reference_model,
                "passes": metrics.fixed_reference_development_passes,
                "cases": metrics.fixed_reference_development_cases,
                "passRate": metrics.fixed_reference_development_pass_rate,
                "efficiencyStatus": metrics.fixed_reference_efficiency_status,
                "usageIncompleteCaseCount": metrics.fixed_reference_usage_incomplete_case_count,
            },
            "challenger": {
                "model": metrics.challenger_model,
                "passes": metrics.challenger_screen_passes,
                "cases": metrics.challenger_screen_cases,
                "passRate": metrics.challenger_screen_pass_rate,
                "baselinePasses": metrics.challenger_screen_baseline_passes,
                "baselinePassRate": metrics.challenger_screen_baseline_pass_rate,
                "decision": metrics.challenger_decision,
            },
            "deterministicFaults": {
                "passes": metrics.deterministic_fault_passes,
                "cases": metrics.deterministic_fault_cases,
                "passRate": metrics.deterministic_fault_pass_rate,
            },
            "adaptation": {
                "theoreticalReduction": metrics.r7a_failure_only_oracle_reduction,
                "requiredTargetReduction": (
                    manifest.methodology_constants.efficiency_target_reduction
                ),
                "zeroPassLossFixedCapReduction": (
                    metrics.r7a_best_zero_pass_loss_fixed_cap_reduction
                ),
                "bestPracticalReduction": metrics.r7b_best_nontrivial_policy_reduction,
                "observedPassLosses": (
                    metrics.r7b_best_nontrivial_policy_observed_pass_loss
                ),
                "policyDecision": metrics.r7b_policy_decision,
            },
            "decision": {
                "finalVerdict": metrics.final_verdict,
                "developmentDisposition": metrics.development_disposition,
                "adaptiveRuntimePromotion": metrics.adaptive_runtime_promotion,
                "lockedPairedEvaluation": metrics.locked_paired_evaluation,
                "lockedCasesAccessed": metrics.locked_cases_accessed,
            },
        },
        "nonClaims": manifest.non_claims,
    }

    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return (
        "// Generated by scripts/validate_harbourdesk_space_evidence.py --write-generated\n"
        "// Do not edit metric values in this file by hand.\n"
        f"export const publicEvidence = {body} as const\n"
    )


def parse_sha256sums(path: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        sha, relative = raw_line.split(None, 1)
        observed[relative.strip()] = sha.lower()
    return observed


def verify_source_release(source_release: Path, failures: list[str]) -> None:
    if not source_release.is_dir():
        failures.append(f"source_release_missing:{source_release}")
        return

    expected_names = set(EXPECTED_SOURCE_HASHES) | {"SHA256SUMS"}
    observed_names = {
        path.relative_to(source_release).as_posix()
        for path in source_release.rglob("*")
        if path.is_file()
    }
    if observed_names != expected_names:
        failures.append("source_release_file_set_mismatch")

    sums_path = source_release / "SHA256SUMS"
    if not sums_path.is_file():
        failures.append("source_release_missing_sha256sums")
        return

    declared = parse_sha256sums(sums_path)
    if declared != EXPECTED_SOURCE_HASHES:
        failures.append("source_release_sha256sums_mismatch")

    for relative, expected_sha in EXPECTED_SOURCE_HASHES.items():
        path = source_release / Path(relative)
        if not path.is_file():
            failures.append(f"source_release_missing:{relative}")
            continue
        if sha256_file(path) != expected_sha:
            failures.append(f"source_release_hash_mismatch:{relative}")


def scan_frontend(frontend_src: Path, failures: list[str]) -> None:
    for path in frontend_src.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for token in FORBIDDEN_FRONTEND_TOKENS:
            if token.lower() in lowered:
                failures.append(
                    f"forbidden_frontend_source_reference:"
                    f"{path.relative_to(frontend_src).as_posix()}:{token}"
                )


def validate(repo_root: Path, source_release: Path | None, write_generated: bool) -> list[str]:
    failures: list[str] = []
    evidence_dir = repo_root / "space" / "evidence"
    results_path = evidence_dir / "results.json"
    provenance_path = evidence_dir / "provenance.json"
    manifest_path = evidence_dir / "public_evidence_manifest.json"
    generated_path = repo_root / "space" / "src" / "data" / "publicEvidence.generated.ts"

    for path in (results_path, provenance_path, manifest_path):
        if not path.is_file():
            failures.append(f"missing_public_source:{path.relative_to(repo_root)}")

    if failures:
        return failures

    if sha256_file(results_path) != EXPECTED_RESULTS_SHA256:
        failures.append("checked_in_results_sha256_mismatch")
    if sha256_file(provenance_path) != EXPECTED_PROVENANCE_SHA256:
        failures.append("checked_in_provenance_sha256_mismatch")

    metrics = PublicMetrics.model_validate(read_json(results_path))
    provenance = PublicProvenance.model_validate(read_json(provenance_path))
    manifest = PublicEvidenceManifest.model_validate(read_json(manifest_path))

    if manifest.source_release.sha256sums_entries != EXPECTED_SOURCE_HASHES:
        failures.append("manifest_source_hash_set_mismatch")
    if manifest.checked_in_public_sources != {
        "results.json": EXPECTED_RESULTS_SHA256,
        "provenance.json": EXPECTED_PROVENANCE_SHA256,
    }:
        failures.append("manifest_checked_in_source_hash_mismatch")

    expected_metric_keys = {
        "fixed_reference_development",
        "challenger_screen",
        "challenger_baseline",
        "deterministic_faults",
        "theoretical_saving",
        "required_target",
        "practical_saving",
        "practical_regressions",
        "final_verdict",
        "adaptive_decision",
        "locked_cases_accessed",
    }
    if set(manifest.display_metric_sources) != expected_metric_keys:
        failures.append("display_metric_source_mapping_incomplete")

    if not (
        abs(metrics.fixed_reference_development_pass_rate - 43 / 90) < 1e-12
        and abs(metrics.challenger_screen_pass_rate - 15 / 36) < 1e-12
        and abs(metrics.challenger_screen_baseline_pass_rate - 16 / 36) < 1e-12
        and metrics.deterministic_fault_pass_rate == 1.0
        and metrics.r7a_failure_only_oracle_reduction > 0.20
        and metrics.r7b_best_nontrivial_policy_reduction < 0.20
    ):
        failures.append("public_metric_semantics_mismatch")

    generated = render_typescript(metrics, provenance, manifest)
    generated_path.parent.mkdir(parents=True, exist_ok=True)
    if write_generated:
        generated_path.write_text(generated, encoding="utf-8", newline="\n")
    elif not generated_path.is_file():
        failures.append("generated_typescript_missing")
    elif generated_path.read_text(encoding="utf-8") != generated:
        failures.append("generated_typescript_drift")

    scan_frontend(repo_root / "space" / "src", failures)

    if source_release is not None:
        verify_source_release(source_release, failures)

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-release",
        type=Path,
        help="Optional local R11 huggingface_release directory to verify byte-for-byte.",
    )
    parser.add_argument(
        "--write-generated",
        action="store_true",
        help="Regenerate the typed frontend evidence module after validation.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    failures = validate(
        repo_root=repo_root,
        source_release=args.source_release,
        write_generated=args.write_generated,
    )

    status = "PASS" if not failures else "FAIL"
    print(f"H3_STATUS={status}")
    print(f"H3_RESULTS_SHA256={EXPECTED_RESULTS_SHA256}")
    print(f"H3_PROVENANCE_SHA256={EXPECTED_PROVENANCE_SHA256}")
    print(f"H3_RELEASE_ZIP_SHA256={EXPECTED_RELEASE_ZIP_SHA256}")
    print("H3_FRONTEND_FORBIDDEN_SOURCE_REFERENCES=0" if not failures else "")
    print("H3_FAILURES=" + json.dumps(failures, separators=(",", ":")))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
