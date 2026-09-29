from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

R11_PARENT_R10_COMMIT = "4bd1b8c36202611d5503abb8536cc8e138056ce8"
R11_R10_RUN_ID = "r10-no-candidate-closeout-20260929-01"
R11_R10_BUNDLE_SHA256 = "bfc2b8304481f8c3b61331f0e273343cc0d3f2eef054f2d3120f9ff26a02a300"
R11_R10_DIR = Path("runs/r10_closeout") / R11_R10_RUN_ID


class R11Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R11PublicMetrics(R11Contract):
    schema_version: Literal["harbourdesk-r11-public-metrics-v1"] = (
        "harbourdesk-r11-public-metrics-v1"
    )
    fixed_reference_model: Literal["glm-5.2"] = "glm-5.2"
    fixed_reference_development_passes: Literal[43] = 43
    fixed_reference_development_cases: Literal[90] = 90
    fixed_reference_development_pass_rate: float
    fixed_reference_efficiency_status: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"
    fixed_reference_usage_incomplete_case_count: Literal[1] = 1
    challenger_model: Literal["glm-5.1"] = "glm-5.1"
    challenger_screen_passes: Literal[15] = 15
    challenger_screen_cases: Literal[36] = 36
    challenger_screen_pass_rate: float
    challenger_screen_baseline_passes: Literal[16] = 16
    challenger_screen_baseline_pass_rate: float
    challenger_decision: Literal["DO_NOT_PROMOTE"] = "DO_NOT_PROMOTE"
    deterministic_fault_passes: Literal[24] = 24
    deterministic_fault_cases: Literal[24] = 24
    deterministic_fault_pass_rate: float
    r7a_failure_only_oracle_reduction: float
    r7a_best_zero_pass_loss_fixed_cap_reduction: float
    r7b_best_nontrivial_policy_reduction: float
    r7b_best_nontrivial_policy_observed_pass_loss: int = Field(ge=0)
    r7b_policy_decision: Literal["NO_POLICY_QUALIFIED"] = "NO_POLICY_QUALIFIED"
    final_verdict: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"
    development_disposition: Literal["NO_ADAPTIVE_CANDIDATE_ADMITTED"] = (
        "NO_ADAPTIVE_CANDIDATE_ADMITTED"
    )
    adaptive_runtime_promotion: Literal["REJECTED"] = "REJECTED"
    locked_paired_evaluation: Literal["NOT_RUN"] = "NOT_RUN"
    locked_cases_accessed: Literal[0] = 0


class R11Provenance(R11Contract):
    schema_version: Literal["harbourdesk-r11-provenance-v1"] = "harbourdesk-r11-provenance-v1"
    release_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    parent_r10_commit: Literal["4bd1b8c36202611d5503abb8536cc8e138056ce8"] = (
        "4bd1b8c36202611d5503abb8536cc8e138056ce8"
    )
    r10_run_id: Literal["r10-no-candidate-closeout-20260929-01"] = (
        "r10-no-candidate-closeout-20260929-01"
    )
    r10_bundle_sha256: Literal[
        "bfc2b8304481f8c3b61331f0e273343cc0d3f2eef054f2d3120f9ff26a02a300"
    ] = "bfc2b8304481f8c3b61331f0e273343cc0d3f2eef054f2d3120f9ff26a02a300"
    r6b_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    r6b_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    r7b_summary_sha256: Literal[
        "e9f5939c46e85c6848c2350407854669ffd2f4ffe6e9b6d02b7cc66fa0cc2ada"
    ] = "e9f5939c46e85c6848c2350407854669ffd2f4ffe6e9b6d02b7cc66fa0cc2ada"
    source_evidence_file_count: Literal[312] = 312
    source_evidence_total_bytes: Literal[2153217] = 2153217


class R11PublicFile(R11Contract):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class R11ReleaseReceipt(R11Contract):
    schema_version: Literal["harbourdesk-r11-release-v1"] = "harbourdesk-r11-release-v1"
    status: Literal["PASS", "FAIL"]
    release_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    public_file_count: int = Field(ge=1)
    public_total_bytes: int = Field(ge=0)
    release_zip_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_files: tuple[R11PublicFile, ...]
    raw_traces_included: Literal[False] = False
    private_expected_outcomes_included: Literal[False] = False
    validation_cases_included: Literal[False] = False
    locked_cases_included: Literal[False] = False
    development_case_payloads_included: Literal[False] = False
    integrity_failures: tuple[str, ...]


def build_public_release(
    *,
    repo_root: Path,
    release_commit: str,
    expected_r10_bundle_sha256: str,
    output_dir: Path,
) -> R11ReleaseReceipt:
    failures: list[str] = []
    if output_dir.exists():
        raise FileExistsError(f"R11 output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    r10_dir = repo_root / R11_R10_DIR
    summary_path = r10_dir / "summary.json"
    verdict_path = r10_dir / "final_verdict.json"
    bundle_path = r10_dir / "r10_evidence_bundle.zip"
    bundle_hash_path = r10_dir / "r10_evidence_bundle.sha256"

    for path in (summary_path, verdict_path, bundle_path, bundle_hash_path):
        if not path.is_file():
            failures.append(f"missing_r10_artifact:{path.relative_to(repo_root)}")

    actual_bundle_sha = _sha256_file(bundle_path)
    expected_bundle_sha = expected_r10_bundle_sha256.lower()
    if actual_bundle_sha != expected_bundle_sha:
        failures.append("r10_bundle_sha256_mismatch")
    if actual_bundle_sha != R11_R10_BUNDLE_SHA256:
        failures.append("r10_bundle_not_authoritative")

    declared_hash = bundle_hash_path.read_text(encoding="utf-8").split()[0].lower()
    if declared_hash != actual_bundle_sha:
        failures.append("r10_bundle_sidecar_mismatch")

    summary = _read_json(summary_path)
    verdict = _read_json(verdict_path)
    _validate_r10(summary=summary, verdict=verdict, failures=failures)

    metrics = _public_metrics(verdict)
    provenance = R11Provenance(
        release_commit=release_commit,
        r6b_manifest_sha256=_as_str(summary["r6b_manifest_sha256"]),
        r6b_summary_sha256=_as_str(summary["r6b_summary_sha256"]),
    )

    release_root = output_dir / "huggingface_release"
    charts_dir = release_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=False)

    results_path = release_root / "results.json"
    provenance_path = release_root / "provenance.json"
    readme_path = release_root / "README.md"
    notes_path = release_root / "PUBLICATION_NOTES.md"

    results_path.write_text(
        metrics.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    provenance_path.write_text(
        provenance.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        render_huggingface_readme(metrics, provenance),
        encoding="utf-8",
    )
    notes_path.write_text(
        render_publication_notes(metrics),
        encoding="utf-8",
    )

    _write_single_bar_svg(
        charts_dir / "fixed_reference_development.svg",
        title="GLM-5.2 development reference",
        label="Verified success",
        value=metrics.fixed_reference_development_pass_rate,
        detail="43 / 90 development cases",
    )
    _write_two_bar_svg(
        charts_dir / "challenger_screen.svg",
        title="Frozen 36-case challenger screen",
        first_label="GLM-5.1",
        first_value=metrics.challenger_screen_pass_rate,
        second_label="GLM-5.2 baseline subset",
        second_value=metrics.challenger_screen_baseline_pass_rate,
        detail="DO_NOT_PROMOTE",
    )
    _write_single_bar_svg(
        charts_dir / "deterministic_faults.svg",
        title="Deterministic fault programme",
        label="Invariant-safe cases",
        value=metrics.deterministic_fault_pass_rate,
        detail="24 / 24 PASS",
    )
    _write_adaptation_svg(
        charts_dir / "adaptation_screen.svg",
        oracle=metrics.r7a_failure_only_oracle_reduction,
        bounded=metrics.r7b_best_nontrivial_policy_reduction,
        target=0.20,
        pass_loss=metrics.r7b_best_nontrivial_policy_observed_pass_loss,
    )

    release_files = tuple(path for path in sorted(release_root.rglob("*")) if path.is_file())
    _scan_public_surface(release_files, release_root, failures)

    checksums_path = release_root / "SHA256SUMS"
    checksum_lines = [
        f"{_sha256_file(path)}  {path.relative_to(release_root).as_posix()}"
        for path in release_files
    ]
    checksums_path.write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
    )

    public_files = tuple(
        R11PublicFile(
            path=path.relative_to(release_root).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=_sha256_file(path),
        )
        for path in sorted(release_root.rglob("*"))
        if path.is_file()
    )

    zip_path = output_dir / "harbourdesk_r11_huggingface_release.zip"
    zip_sha = _write_deterministic_zip(
        source_root=release_root,
        output_path=zip_path,
    )

    receipt = R11ReleaseReceipt(
        status="PASS" if not failures else "FAIL",
        release_commit=release_commit,
        public_file_count=len(public_files),
        public_total_bytes=sum(item.size_bytes for item in public_files),
        release_zip_sha256=zip_sha,
        public_files=public_files,
        integrity_failures=tuple(failures),
    )
    (output_dir / "summary.json").write_text(
        receipt.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def render_huggingface_readme(
    metrics: R11PublicMetrics,
    provenance: R11Provenance,
) -> str:
    fixed_rate = metrics.fixed_reference_development_pass_rate * 100
    challenger_rate = metrics.challenger_screen_pass_rate * 100
    baseline_rate = metrics.challenger_screen_baseline_pass_rate * 100
    oracle_reduction = metrics.r7a_failure_only_oracle_reduction * 100
    fixed_cap_reduction = metrics.r7a_best_zero_pass_loss_fixed_cap_reduction * 100
    bounded_reduction = metrics.r7b_best_nontrivial_policy_reduction * 100
    bounded_pass_loss = metrics.r7b_best_nontrivial_policy_observed_pass_loss

    return f"""---
pretty_name: HarbourDesk Adaptive Runtime Reliability Study
tags:
- ai-reliability
- agents
- evaluation
- tool-use
- safety
- reproducibility
---

# HarbourDesk Adaptive Runtime Reliability Study

This release packages the public results of a bounded AI reliability investigation
over the HarbourDesk task environment.

The project asked whether an adaptive runtime could preserve task quality and
deterministic safety while materially reducing inference use versus a fixed reference.

## Result

**Final R4-contract verdict: INCONCLUSIVE.**

The reason is specific: no adaptive candidate earned development admission, so the
required candidate-versus-reference comparison on the 60 locked cases was not run.

The development decision itself is not ambiguous:

**NO_ADAPTIVE_CANDIDATE_ADMITTED. Adaptive runtime promotion: REJECTED.**

The locked benchmark remained untouched.

## Evidence summary

| Evidence | Result |
| --- | ---: |
| GLM-5.2 fixed reference, development | 43 / 90 verified successes ({fixed_rate:.2f}%) |
| GLM-5.1 challenger, frozen 36-case screen | 15 / 36 ({challenger_rate:.2f}%) |
| GLM-5.2 baseline on same 36-case screen | 16 / 36 ({baseline_rate:.2f}%) |
| Challenger decision | DO_NOT_PROMOTE |
| Deterministic fault programme | 24 / 24 PASS |
| Failure-only oracle diagnostic reduction | {oracle_reduction:.2f}% |
| Best zero-pass-loss universal fixed-cap reduction | {fixed_cap_reduction:.2f}% |
| Best nontrivial bounded policy reduction | {bounded_reduction:.2f}% |
| Observed pass losses for that bounded policy | {bounded_pass_loss} |
| R7B policy decision | NO_POLICY_QUALIFIED |
| Locked paired evaluation | NOT_RUN |

The R7A and R7B token-reduction figures are **development diagnostics**, not final
efficiency claims. The frozen fixed-reference run had one provider-error case with
incomplete usage accounting, so final efficiency was never qualified.

## What this demonstrates

The deterministic reliability substrate survived the predeclared 24-case fault
programme with zero invariant failures and zero unexpected effective writes.

A second fixed model did not earn promotion in the frozen challenger screen.

The development evidence contained theoretical early-stop headroom, but the bounded
runtime-visible policy class tested in template-held-out evaluation could not capture
that headroom safely or materially. The best nontrivial candidate saved only
{bounded_reduction:.2f}% diagnostically and lost
{bounded_pass_loss} previously observed successes.

The project therefore rejected extra adaptive complexity rather than promoting it
without evidence.

## What this does not claim

This release does **not** claim that:

- the adaptive runtime passed the project north star;
- a 20% final efficiency improvement was demonstrated;
- locked-set candidate quality was measured;
- GLM-5.2 universally outperforms GLM-5.1;
- 24 deterministic fault cases establish complete production safety.

## Public release boundary

This package contains only derived metrics, methodology, provenance, hashes, and
charts. It intentionally excludes raw traces, private expected outcomes, validation
cases, locked cases, and development case payloads.

## Provenance

- R10 freeze commit: `{provenance.parent_r10_commit}`
- R10 evidence bundle SHA256: `{provenance.r10_bundle_sha256}`
- R6B manifest SHA256: `{provenance.r6b_manifest_sha256}`
- R6B summary SHA256: `{provenance.r6b_summary_sha256}`
- R7B summary SHA256: `{provenance.r7b_summary_sha256}`
- R11 release commit: `{provenance.release_commit}`

See `results.json`, `provenance.json`, `PUBLICATION_NOTES.md`, and `SHA256SUMS` for
machine-readable and release-bound evidence.
"""


def render_publication_notes(metrics: R11PublicMetrics) -> str:
    oracle_reduction = metrics.r7a_failure_only_oracle_reduction * 100
    bounded_reduction = metrics.r7b_best_nontrivial_policy_reduction * 100
    bounded_pass_loss = metrics.r7b_best_nontrivial_policy_observed_pass_loss

    return f"""# Publication Notes

## Safe headline

A production-shaped AI reliability study rejected its adaptive layer after development
evidence failed to justify the added complexity, while the deterministic runtime
passed all 24 predeclared fault cases.

## Precise result language

- Development fixed reference: 43/90 verified successes.
- Challenger screen: GLM-5.1 15/36 versus GLM-5.2 16/36 on the same frozen subset;
  `DO_NOT_PROMOTE`.
- Deterministic fault programme: 24/24 PASS.
- Theoretical failure-only oracle reduction:
  {oracle_reduction:.2f}% diagnostic.
- Best nontrivial bounded runtime-visible policy:
  {bounded_reduction:.2f}% diagnostic reduction with
  {bounded_pass_loss} observed pass losses.
- Adaptive candidate admission: none.
- Locked paired evaluation: not run.
- Final frozen-contract verdict: INCONCLUSIVE.

## Non-claims

Do not rewrite `INCONCLUSIVE` as PASS or FAIL.

Do not describe R7A/R7B token reductions as final efficiency results.

Do not claim a model ranking beyond the exact frozen challenger screen.

Do not claim universal production safety from the 24 deterministic faults.

Do not imply that the locked set was opened.
"""


def _public_metrics(verdict: dict[str, object]) -> R11PublicMetrics:
    return R11PublicMetrics(
        fixed_reference_development_pass_rate=43 / 90,
        challenger_screen_pass_rate=15 / 36,
        challenger_screen_baseline_pass_rate=16 / 36,
        deterministic_fault_pass_rate=1.0,
        r7a_failure_only_oracle_reduction=_as_float(verdict["r7a_failure_only_oracle_reduction"]),
        r7a_best_zero_pass_loss_fixed_cap_reduction=_as_float(
            verdict["r7a_best_zero_pass_loss_reduction"]
        ),
        r7b_best_nontrivial_policy_reduction=_as_float(verdict["r7b_best_nontrivial_reduction"]),
        r7b_best_nontrivial_policy_observed_pass_loss=_as_int(
            verdict["r7b_best_nontrivial_pass_loss"]
        ),
    )


def _validate_r10(
    *,
    summary: dict[str, object],
    verdict: dict[str, object],
    failures: list[str],
) -> None:
    if not (
        summary.get("status") == "PASS"
        and summary.get("candidate_commit") == R11_PARENT_R10_COMMIT
        and summary.get("known_hashes_verified") is True
        and summary.get("evidence_file_count") == 312
        and summary.get("evidence_total_bytes") == 2153217
        and summary.get("integrity_failures") == []
    ):
        failures.append("r10_summary_state_mismatch")

    if not (
        verdict.get("final_verdict") == "INCONCLUSIVE"
        and verdict.get("development_disposition") == "NO_ADAPTIVE_CANDIDATE_ADMITTED"
        and verdict.get("adaptive_runtime_promotion") == "REJECTED"
        and verdict.get("locked_paired_evaluation") == "NOT_RUN"
        and verdict.get("locked_cases_accessed_for_r7_or_closeout") == 0
        and verdict.get("deterministic_fault_program") == "PASS"
        and verdict.get("evidence_closeout") == "PASS"
        and verdict.get("reason_codes")
        == [
            "NO_QUALIFIED_ADAPTIVE_CANDIDATE",
            "LOCKED_PAIRED_COMPARISON_NOT_EXECUTED",
        ]
    ):
        failures.append("r10_final_verdict_state_mismatch")


def _scan_public_surface(
    paths: tuple[Path, ...],
    release_root: Path,
    failures: list[str],
) -> None:
    forbidden_fragments = (
        "trace.jsonl",
        "expected.json",
        "evaluation_private",
        "/validation/",
        "/locked/",
        "\\validation\\",
        "\\locked\\",
    )
    for path in paths:
        relative = path.relative_to(release_root).as_posix()
        lowered = relative.lower()
        if any(fragment in lowered for fragment in forbidden_fragments):
            failures.append(f"forbidden_public_file:{relative}")

    allowed_names = {
        "README.md",
        "PUBLICATION_NOTES.md",
        "results.json",
        "provenance.json",
        "fixed_reference_development.svg",
        "challenger_screen.svg",
        "deterministic_faults.svg",
        "adaptation_screen.svg",
    }
    observed = {path.name for path in paths}
    if observed != allowed_names:
        failures.append("public_file_set_mismatch")


def _write_single_bar_svg(
    path: Path,
    *,
    title: str,
    label: str,
    value: float,
    detail: str,
) -> None:
    width = 760
    bar_width = round(560 * value)
    pct = value * 100
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="220" viewBox="0 0 {width} 220">\n'
        f'  <text x="24" y="36" font-size="24">{_xml(title)}</text>\n'
        f'  <text x="24" y="82" font-size="18">{_xml(label)}</text>\n'
        f'  <rect x="170" y="62" width="{bar_width}" height="28"/>\n'
        f'  <text x="170" y="120" font-size="18">{pct:.2f}%</text>\n'
        f'  <text x="24" y="170" font-size="16">{_xml(detail)}</text>\n'
        "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")


def _write_two_bar_svg(
    path: Path,
    *,
    title: str,
    first_label: str,
    first_value: float,
    second_label: str,
    second_value: float,
    detail: str,
) -> None:
    first_width = round(430 * first_value)
    second_width = round(430 * second_value)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" '
        'height="280" viewBox="0 0 760 280">\n'
        f'  <text x="24" y="36" font-size="24">{_xml(title)}</text>\n'
        f'  <text x="24" y="88" font-size="16">{_xml(first_label)}</text>\n'
        f'  <rect x="230" y="68" width="{first_width}" height="24"/>\n'
        f'  <text x="670" y="88" font-size="16">{first_value * 100:.2f}%</text>\n'
        f'  <text x="24" y="142" font-size="16">{_xml(second_label)}</text>\n'
        f'  <rect x="230" y="122" width="{second_width}" height="24"/>\n'
        f'  <text x="670" y="142" font-size="16">{second_value * 100:.2f}%</text>\n'
        f'  <text x="24" y="214" font-size="16">{_xml(detail)}</text>\n'
        "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")


def _write_adaptation_svg(
    path: Path,
    *,
    oracle: float,
    bounded: float,
    target: float,
    pass_loss: int,
) -> None:
    oracle_width = round(430 * oracle)
    bounded_width = round(430 * bounded)
    target_width = round(430 * target)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="780" '
        'height="340" viewBox="0 0 780 340">\n'
        '  <text x="24" y="36" font-size="24">'
        "Adaptation feasibility diagnostics</text>\n"
        '  <text x="24" y="92" font-size="16">Failure-only oracle</text>\n'
        f'  <rect x="250" y="72" width="{oracle_width}" height="24"/>\n'
        f'  <text x="700" y="92" font-size="16">{oracle * 100:.2f}%</text>\n'
        '  <text x="24" y="148" font-size="16">Best bounded policy</text>\n'
        f'  <rect x="250" y="128" width="{bounded_width}" height="24"/>\n'
        f'  <text x="700" y="148" font-size="16">{bounded * 100:.2f}%</text>\n'
        '  <text x="24" y="204" font-size="16">Project efficiency target</text>\n'
        f'  <rect x="250" y="184" width="{target_width}" height="24"/>\n'
        f'  <text x="700" y="204" font-size="16">{target * 100:.2f}%</text>\n'
        '  <text x="24" y="270" font-size="16">'
        f"Best bounded policy also lost {pass_loss} observed successes.</text>\n"
        '  <text x="24" y="304" font-size="14">'
        "Development diagnostic only; not a final efficiency result.</text>\n"
        "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")


def _write_deterministic_zip(
    *,
    source_root: Path,
    output_path: Path,
) -> str:
    if output_path.exists():
        raise FileExistsError(f"R11 release ZIP exists: {output_path}")

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(
                filename=relative,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    return _sha256_file(output_path)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer, got {type(value).__name__}")
    return value


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected number, got {type(value).__name__}")
    return float(value)


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected string, got {type(value).__name__}")
    return value


def _xml(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
