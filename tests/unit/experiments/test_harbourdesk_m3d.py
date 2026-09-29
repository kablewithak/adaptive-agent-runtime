from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
from adaptive_runtime.experiments.harbourdesk_m3d import (
    M3D_BASELINE_DECISION_SHA256,
    M3D_BASELINE_MANIFEST_SHA256,
    M3D_BASELINE_RUN_ID,
    M3D_BASELINE_SUMMARY_SHA256,
    M3D_BUDGET,
    M3D_IDENTITY,
    M3DBaselineReference,
    M3DCaseInput,
    M3DGateStatus,
    M3DInterventionMetrics,
    evaluate_m3d_gate,
    load_m3d_public_cases,
    run_m3d_experiment,
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _inputs() -> tuple[M3DCaseInput, ...]:
    cases = load_m3d_public_cases(_repo_root())
    result: list[M3DCaseInput] = []
    for case in cases:
        result.append(
            M3DCaseInput(
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


def _result_for_case(item: M3DCaseInput, index: int) -> ModelResult:
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


def _baseline() -> M3DBaselineReference:
    return M3DBaselineReference(
        run_id=M3D_BASELINE_RUN_ID,
        manifest_sha256=M3D_BASELINE_MANIFEST_SHA256,
        summary_sha256=M3D_BASELINE_SUMMARY_SHA256,
        decision_sha256=M3D_BASELINE_DECISION_SHA256,
        case_count=12,
        verified_pass_case_ids=(
            "hdm-001",
            "hdm-002",
            "hdm-004",
            "hdm-005",
            "hdm-006",
        ),
        length_limited_case_ids=("hdm-003", "hdm-008", "hdm-012"),
        max_completion_tokens=768,
        observed_inference_tokens=204080,
        usage_complete=True,
    )


def test_m3d_identity_and_budget_are_frozen() -> None:
    assert M3D_IDENTITY.stage_label == "M3D"
    assert M3D_IDENTITY.profile_name == "glm-5-2-openai"
    assert M3D_IDENTITY.model_id == "glm-5.2"
    assert M3D_IDENTITY.experiment_receipt_schema_version == "m3d-run-v1"
    assert M3D_BUDGET.max_model_calls == 8
    assert M3D_BUDGET.max_tool_actions == 10
    assert M3D_BUDGET.max_completion_tokens == 1536


def test_m3d_runs_with_1536_and_writes_its_own_decision(tmp_path: Path) -> None:
    inputs = _inputs()
    provider = FakeProvider([_result_for_case(item, index) for index, item in enumerate(inputs, 1)])
    evidence_dir = tmp_path / "m3d-test"

    receipt = run_m3d_experiment(
        inputs=inputs,
        provider=provider,
        profile=_profile(),
        run_id="m3d-test",
        evidence_dir=evidence_dir,
        baseline=_baseline(),
    )

    assert receipt.intervention_run.case_count == 12
    assert receipt.intervention_run.score_pass_count == 12
    assert receipt.intervention_run.frozen_configuration.max_completion_tokens == 1536
    assert receipt.gate.overall_status == M3DGateStatus.PASS
    assert receipt.gate.safety_status == M3DGateStatus.PASS
    assert receipt.gate.baseline_pass_preservation_status == M3DGateStatus.PASS
    assert receipt.gate.completion_envelope_status == M3DGateStatus.PASS
    assert receipt.gate.target_length_stop_count == 0
    assert receipt.gate.target_terminal_count == 3
    assert len(provider.requests) == 12

    decision = (evidence_dir / "m3d_decision.json").read_text(encoding="utf-8")
    assert "acceptable_terminal_predicates" not in decision
    assert M3D_BASELINE_RUN_ID in decision

    first_event = json.loads(
        (evidence_dir / "hdm-001" / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert first_event["budget"]["max_completion_tokens"] == 1536


def test_m3d_gate_fails_on_baseline_pass_regression() -> None:
    metrics = M3DInterventionMetrics(
        case_ids=tuple(f"hdm-{index:03d}" for index in range(1, 13)),
        baseline_verified_pass_case_ids=(
            "hdm-001",
            "hdm-002",
            "hdm-004",
            "hdm-005",
            "hdm-006",
        ),
        verified_pass_case_ids=(
            "hdm-001",
            "hdm-004",
            "hdm-005",
            "hdm-006",
            "hdm-003",
        ),
        target_case_ids=("hdm-003", "hdm-008", "hdm-012"),
        target_length_stop_case_ids=(),
        target_terminal_case_ids=("hdm-003",),
        deterministic_control_violation_count=0,
        realized_write_from_multi_tool_batch_count=0,
        usage_complete=True,
    )

    gate = evaluate_m3d_gate(metrics)

    assert gate.baseline_pass_preservation_status == M3DGateStatus.FAIL
    assert gate.preservation_fail_case_ids == ("hdm-002",)
    assert gate.overall_status == M3DGateStatus.FAIL
