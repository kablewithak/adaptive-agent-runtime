from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptive_runtime.contracts.config import EndpointProfile
from adaptive_runtime.contracts.provider import (
    ModelRequest,
    ModelResult,
    ProviderOutcome,
    ProviderProtocol,
    ToolCall,
    ToolCallFunction,
    UsageAccounting,
)
from adaptive_runtime.evaluation.expected import (
    ExpectedCaseOutcome,
    ExpectedDisposition,
    ExpectedTerminalPredicate,
)
from adaptive_runtime.experiments.harbourdesk_m1b import (
    M1B_CASE_IDS,
    M1BCaseInput,
    M1BExperimentStatus,
    load_m1b_public_cases,
    run_m1b_experiment,
)


class FakeProvider:
    def __init__(self, results: list[ModelResult]) -> None:
        self._results = iter(results)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        result = next(self._results)
        return result.model_copy(update={"request_id": request.request_id})


def _profile() -> EndpointProfile:
    return EndpointProfile(
        profile_name="primary-openai",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        full_endpoint_url=(
            "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
        ),
        region_label="ap-southeast-1",
        model_id="glm-5.1",
        observed_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _inputs() -> tuple[M1BCaseInput, ...]:
    cases = load_m1b_public_cases(_repo_root())
    result: list[M1BCaseInput] = []

    for case in cases:
        result.append(
            M1BCaseInput(
                case=case,
                expected=ExpectedCaseOutcome(
                    case_id=case.case_id,
                    terminal_ticket_id=case.ticket_id,
                    acceptable_terminal_predicates=(
                        ExpectedTerminalPredicate(
                            disposition=ExpectedDisposition.ESCALATION,
                            reason_code="OPERATION_OUTCOME_UNCERTAIN",
                            expected_effective_write_count=0,
                            max_effective_write_count=0,
                        ),
                    ),
                ),
            )
        )

    return tuple(result)


def _result_for_case(item: M1BCaseInput, index: int) -> ModelResult:
    ticket = next(
        ticket for ticket in item.case.initial.tickets if ticket.ticket_id == item.case.ticket_id
    )
    arguments = {
        "expected_ticket_revision": ticket.revision,
        "status": "escalated",
        "resolution_reason_code": "OPERATION_OUTCOME_UNCERTAIN",
        "evidence_document_ids": [],
        "operation_ids": [],
    }
    return ModelResult(
        request_id="placeholder",
        outcome=ProviderOutcome.SUCCESS,
        returned_model="glm-5.1",
        tool_calls=(
            ToolCall(
                id=f"call-update-{index:02d}",
                function=ToolCallFunction(
                    name="update_ticket",
                    arguments=json.dumps(arguments),
                ),
            ),
        ),
        stop_reason="tool_calls",
        usage=UsageAccounting(
            input_tokens=1000 + index,
            completion_tokens=50,
        ),
        http_status=200,
        latency_ms=10,
    )


def test_public_case_order_is_frozen_to_all_twelve_diagnostics() -> None:
    cases = load_m1b_public_cases(_repo_root())

    assert tuple(case.case_id for case in cases) == M1B_CASE_IDS
    assert len(cases) == 12


def test_m1b_runs_frozen_suite_and_writes_sanitized_evidence(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    provider = FakeProvider([_result_for_case(item, index) for index, item in enumerate(inputs, 1)])
    evidence_dir = tmp_path / "m1b-run"

    receipt = run_m1b_experiment(
        inputs=inputs,
        provider=provider,
        profile=_profile(),
        run_id="m1b-test",
        evidence_dir=evidence_dir,
    )

    assert receipt.status is M1BExperimentStatus.COMPLETE
    assert receipt.baseline_complete
    assert receipt.case_count == 12
    assert receipt.score_pass_count == 12
    assert receipt.score_pass_rate == 1.0
    assert receipt.usage_complete
    assert receipt.observed_tokens_per_verified_success is not None
    assert len(provider.requests) == 12

    summary = (evidence_dir / "summary.json").read_text(encoding="utf-8")
    assert "acceptable_terminal_predicates" not in summary

    for case_id in M1B_CASE_IDS:
        case_dir = evidence_dir / case_id
        trace = (case_dir / "trace.jsonl").read_text(encoding="utf-8")
        assert (case_dir / "receipt.json").is_file()
        assert "reasoning_content" not in trace
        assert "HUAWEI_MAAS_API_KEY" not in trace


def test_missing_usage_stays_explicit_and_blocks_efficiency_metric(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    results = [_result_for_case(item, index) for index, item in enumerate(inputs, 1)]
    results[4] = results[4].model_copy(update={"usage": None})
    provider = FakeProvider(results)

    receipt = run_m1b_experiment(
        inputs=inputs,
        provider=provider,
        profile=_profile(),
        run_id="m1b-missing-usage",
        evidence_dir=tmp_path / "m1b-missing-usage",
    )

    assert receipt.baseline_complete
    assert receipt.score_pass_count == 12
    assert receipt.usage_complete is False
    assert receipt.cases[4].usage_complete is False
    assert receipt.observed_tokens_per_verified_success is None


def test_existing_evidence_directory_is_rejected_before_provider_calls(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "existing"
    evidence_dir.mkdir()
    provider = FakeProvider([])

    with pytest.raises(FileExistsError):
        run_m1b_experiment(
            inputs=_inputs(),
            provider=provider,
            profile=_profile(),
            run_id="m1b-existing",
            evidence_dir=evidence_dir,
        )

    assert provider.requests == []
