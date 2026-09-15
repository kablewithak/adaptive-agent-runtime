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
from adaptive_runtime.experiments.harbourdesk_m1a import (
    M1AEnvelopeStatus,
    M1AExperimentStatus,
    load_public_case,
    run_m1a_experiment,
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


def _text_result(text: str, input_tokens: int) -> ModelResult:
    return ModelResult(
        request_id="placeholder",
        outcome=ProviderOutcome.SUCCESS,
        returned_model="glm-5.1",
        text=text,
        stop_reason="stop",
        usage=UsageAccounting(
            input_tokens=input_tokens,
            completion_tokens=12,
        ),
        http_status=200,
        latency_ms=10,
    )


def _tool_result() -> ModelResult:
    arguments = {
        "expected_ticket_revision": 1,
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
                id="call-update-ticket",
                function=ToolCallFunction(
                    name="update_ticket",
                    arguments=json.dumps(arguments),
                ),
            ),
        ),
        stop_reason="tool_calls",
        usage=UsageAccounting(
            input_tokens=1800,
            completion_tokens=80,
        ),
        http_status=200,
        latency_ms=10,
    )


def _expected() -> ExpectedCaseOutcome:
    return ExpectedCaseOutcome(
        case_id="hdm-001",
        terminal_ticket_id="ticket-001",
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.ESCALATION,
                reason_code="OPERATION_OUTCOME_UNCERTAIN",
                expected_effective_write_count=0,
                max_effective_write_count=0,
            ),
        ),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_load_public_case_uses_public_hdm001_only() -> None:
    case = load_public_case(_repo_root(), "hdm-001")
    assert case.case_id == "hdm-001"
    assert case.tenant_id == "tenant-001"
    assert case.ticket_id == "ticket-001"
    assert case.task_ref == "task-001"


def test_m1a_writes_sanitized_evidence_and_independent_score(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            _text_result("I will inspect the ticket.", 1500),
            _text_result("Continuation accepted.", 1650),
            _tool_result(),
        ]
    )
    evidence_dir = tmp_path / "m1a-run"
    receipt = run_m1a_experiment(
        case=load_public_case(_repo_root(), "hdm-001"),
        expected=_expected(),
        provider=provider,
        profile=_profile(),
        run_id="m1a-test",
        evidence_dir=evidence_dir,
    )

    assert receipt.status is M1AExperimentStatus.PASS
    assert receipt.gate_passed
    assert receipt.envelope.status is M1AEnvelopeStatus.VERIFIED_SUFFICIENT
    assert receipt.canary.score_passed
    assert receipt.canary.tool_action_count == 1
    assert receipt.within_stage_token_cap is True

    trace = (evidence_dir / "canary-trace.jsonl").read_text(encoding="utf-8")
    summary = (evidence_dir / "summary.json").read_text(encoding="utf-8")
    assert "reasoning_content" not in trace
    assert "HUAWEI_MAAS_API_KEY" not in trace
    assert "acceptable_terminal_predicates" not in summary


def test_existing_evidence_directory_is_rejected(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "existing"
    evidence_dir.mkdir()
    provider = FakeProvider([])

    with pytest.raises(FileExistsError):
        run_m1a_experiment(
            case=load_public_case(_repo_root(), "hdm-001"),
            expected=_expected(),
            provider=provider,
            profile=_profile(),
            run_id="m1a-existing",
            evidence_dir=evidence_dir,
        )
