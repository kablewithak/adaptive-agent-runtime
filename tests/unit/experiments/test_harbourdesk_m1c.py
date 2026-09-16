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
    M1B_MAX_COMPLETION_TOKENS,
    M1B_MAX_MODEL_CALLS,
    M1B_MAX_TOOL_ACTIONS,
    M1B_REQUEST_DEADLINE_SECONDS,
    M1B_TRAJECTORY_DEADLINE_SECONDS,
)
from adaptive_runtime.experiments.harbourdesk_m1c import (
    M1C_IDENTITY,
    M1CCaseInput,
    M1CExperimentStatus,
    load_m1c_public_cases,
    run_m1c_experiment,
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
        profile_name="glm-5-2-openai",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        full_endpoint_url=(
            "https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"
        ),
        region_label="ap-southeast-1",
        model_id="glm-5.2",
        observed_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
    )


def _wrong_profile() -> EndpointProfile:
    return _profile().model_copy(
        update={
            "profile_name": "primary-openai",
            "model_id": "glm-5.1",
        }
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _inputs() -> tuple[M1CCaseInput, ...]:
    cases = load_m1c_public_cases(_repo_root())
    result: list[M1CCaseInput] = []

    for case in cases:
        result.append(
            M1CCaseInput(
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


def _result_for_case(item: M1CCaseInput, index: int) -> ModelResult:
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
        returned_model="glm-5.2",
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


def test_m1c_identity_is_frozen_to_glm52_profile() -> None:
    assert M1C_IDENTITY.profile_name == "glm-5-2-openai"
    assert M1C_IDENTITY.model_id == "glm-5.2"
    assert M1C_IDENTITY.stage_label == "M1C"


def test_m1c_runs_same_frozen_suite_with_glm52(tmp_path: Path) -> None:
    inputs = _inputs()
    provider = FakeProvider([_result_for_case(item, index) for index, item in enumerate(inputs, 1)])

    receipt = run_m1c_experiment(
        inputs=inputs,
        provider=provider,
        profile=_profile(),
        run_id="m1c-test",
        evidence_dir=tmp_path / "m1c-test",
    )

    assert receipt.status is M1CExperimentStatus.COMPLETE
    assert receipt.baseline_complete
    assert receipt.case_count == 12
    assert receipt.score_pass_count == 12
    assert receipt.usage_complete
    assert len(provider.requests) == 12
    assert receipt.frozen_configuration.profile_name == "glm-5-2-openai"
    assert receipt.frozen_configuration.model_id == "glm-5.2"
    assert receipt.frozen_configuration.case_order == M1B_CASE_IDS
    assert receipt.frozen_configuration.max_model_calls == M1B_MAX_MODEL_CALLS
    assert receipt.frozen_configuration.max_tool_actions == M1B_MAX_TOOL_ACTIONS
    assert (
        receipt.frozen_configuration.trajectory_deadline_seconds == M1B_TRAJECTORY_DEADLINE_SECONDS
    )
    assert receipt.frozen_configuration.request_deadline_seconds == M1B_REQUEST_DEADLINE_SECONDS
    assert receipt.frozen_configuration.max_completion_tokens == M1B_MAX_COMPLETION_TOKENS
    assert receipt.schema_version == "m1c-v1"
    assert receipt.frozen_configuration.schema_version == "m1c-glm52-baseline-v1"

    summary = (tmp_path / "m1c-test" / "summary.json").read_text(encoding="utf-8")
    assert "acceptable_terminal_predicates" not in summary


def test_m1c_rejects_wrong_profile_before_provider_or_evidence(
    tmp_path: Path,
) -> None:
    provider = FakeProvider([])
    evidence_dir = tmp_path / "wrong-profile"

    with pytest.raises(
        RuntimeError,
        match="M1C is frozen to profile glm-5-2-openai",
    ):
        run_m1c_experiment(
            inputs=_inputs(),
            provider=provider,
            profile=_wrong_profile(),
            run_id="m1c-wrong-profile",
            evidence_dir=evidence_dir,
        )

    assert provider.requests == []
    assert not evidence_dir.exists()
