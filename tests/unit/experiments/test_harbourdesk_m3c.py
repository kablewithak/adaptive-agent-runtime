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
from adaptive_runtime.experiments.harbourdesk_m1b import M1BExperimentReceipt
from adaptive_runtime.experiments.harbourdesk_m3a import M3CGateStatus
from adaptive_runtime.experiments.harbourdesk_m3c import (
    M3C_BASELINE_MANIFEST_SHA256,
    M3C_BASELINE_RUN_ID,
    M3C_BASELINE_SUMMARY_SHA256,
    M3C_IDENTITY,
    M3CBaselineReference,
    M3CCaseInput,
    collect_m3c_batch_evidence,
    load_m3c_public_cases,
    run_m3c_experiment,
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


def _inputs() -> tuple[M3CCaseInput, ...]:
    cases = load_m3c_public_cases(_repo_root())
    result: list[M3CCaseInput] = []
    for case in cases:
        result.append(
            M3CCaseInput(
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


def _result_for_case(item: M3CCaseInput, index: int) -> ModelResult:
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
        usage=UsageAccounting(input_tokens=1000 + index, completion_tokens=50),
        http_status=200,
        latency_ms=10,
    )


def _baseline() -> M3CBaselineReference:
    return M3CBaselineReference(
        run_id=M3C_BASELINE_RUN_ID,
        manifest_sha256=M3C_BASELINE_MANIFEST_SHA256,
        summary_sha256=M3C_BASELINE_SUMMARY_SHA256,
        case_count=12,
        verified_pass_case_ids=("hdm-001", "hdm-004"),
        multi_tool_incompatibility_stop_count=8,
        observed_inference_tokens=104741,
        usage_complete=True,
    )


def test_m3c_identity_is_separate_from_m1c_baseline_identity() -> None:
    assert M3C_IDENTITY.stage_label == "M3C"
    assert M3C_IDENTITY.profile_name == "glm-5-2-openai"
    assert M3C_IDENTITY.model_id == "glm-5.2"
    assert M3C_IDENTITY.experiment_receipt_schema_version == "m3c-run-v1"
    assert M3C_IDENTITY.frozen_configuration_schema_version == "m3c-glm52-compatibility-v1"


def test_m3c_runs_existing_engine_and_writes_explicit_gate_decision(tmp_path: Path) -> None:
    inputs = _inputs()
    provider = FakeProvider([_result_for_case(item, index) for index, item in enumerate(inputs, 1)])
    evidence_dir = tmp_path / "m3c-test"

    receipt = run_m3c_experiment(
        inputs=inputs,
        provider=provider,
        profile=_profile(),
        run_id="m3c-test",
        evidence_dir=evidence_dir,
        baseline=_baseline(),
    )

    assert receipt.intervention_run.case_count == 12
    assert receipt.intervention_run.score_pass_count == 12
    assert receipt.intervention_run.usage_complete
    assert receipt.intervention_run.schema_version == "m3c-run-v1"
    assert (
        receipt.intervention_run.frozen_configuration.schema_version == "m3c-glm52-compatibility-v1"
    )
    assert receipt.gate.overall_status is M3CGateStatus.PASS
    assert receipt.batch_evidence.realized_write_from_multi_tool_batch_count == 0
    assert receipt.batch_evidence.deterministic_control_violation_count == 0
    assert len(provider.requests) == 12

    decision = (evidence_dir / "m3c_decision.json").read_text(encoding="utf-8")
    assert "acceptable_terminal_predicates" not in decision
    assert M3C_BASELINE_RUN_ID in decision


def test_batch_evidence_counts_accepted_and_rejected_batches(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "run"
    case_dir = evidence_dir / "hdm-001"
    case_dir.mkdir(parents=True)
    trace_path = case_dir / "trace.jsonl"
    events = [
        {
            "event": "attempt_started",
            "attempt_index": 1,
        },
        {
            "event": "multi_tool_batch_preflight",
            "attempt_index": 1,
            "accepted": True,
            "tool_names": ["get_ticket", "get_account"],
            "provider_tool_call_ids": ["a", "b"],
            "rejection_reason": None,
        },
        {
            "event": "tool_action_finished",
            "action": {"tool": "get_ticket"},
        },
        {
            "event": "tool_action_finished",
            "action": {"tool": "get_account"},
        },
        {
            "event": "attempt_started",
            "attempt_index": 2,
        },
        {
            "event": "multi_tool_batch_preflight",
            "attempt_index": 2,
            "accepted": False,
            "tool_names": ["get_ticket", "update_ticket"],
            "provider_tool_call_ids": ["c", "d"],
            "rejection_reason": "contains_write",
        },
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    run = M1BExperimentReceipt.model_validate(
        {
            "schema_version": "m3c-run-v1",
            "status": "complete",
            "baseline_complete": True,
            "run_id": "m3c-test",
            "frozen_configuration": {
                "schema_version": "m3c-glm52-compatibility-v1",
                "profile_name": "glm-5-2-openai",
                "model_id": "glm-5.2",
                "protocol": "openai_compatible",
                "thinking": None,
                "max_model_calls": 8,
                "max_tool_actions": 10,
                "trajectory_deadline_seconds": 300.0,
                "request_deadline_seconds": 60.0,
                "max_completion_tokens": 768,
                "case_order": [f"hdm-{index:03d}" for index in range(1, 13)],
            },
            "case_count": 1,
            "cases": [
                {
                    "schema_version": "m3c-case-v1",
                    "case_id": "hdm-001",
                    "task_ref": "test",
                    "ticket_id": "t-1",
                    "run_id": "m3c-test-hdm-001",
                    "model_id": "glm-5.2",
                    "stop_category": "ticket_terminal",
                    "terminal_reached": True,
                    "attempt_count": 2,
                    "tool_action_count": 2,
                    "usage_complete": True,
                    "observed_input_tokens": 1,
                    "observed_completion_tokens": 1,
                    "observed_reasoning_tokens": 0,
                    "observed_cached_input_tokens": 0,
                    "observed_provider_latency_ms": 1,
                    "independent_score_recorded": True,
                    "score_passed": True,
                    "matched_predicate_index": 0,
                    "scoring_failures": [],
                    "final_state_sha256": "0" * 64,
                    "trace_sha256": "1" * 64,
                }
            ],
            "score_pass_count": 1,
            "score_pass_rate": 1.0,
            "usage_complete": True,
            "observed_input_tokens": 1,
            "observed_completion_tokens": 1,
            "observed_reasoning_tokens": 0,
            "observed_cached_input_tokens": 0,
            "observed_inference_tokens": 2,
            "observed_provider_latency_ms": 1,
            "observed_tokens_per_verified_success": 2.0,
            "stop_category_counts": {"ticket_terminal": 1},
            "scoring_failure_counts": {},
        }
    )

    evidence = collect_m3c_batch_evidence(evidence_dir, run)

    assert evidence.accepted_batch_count == 1
    assert evidence.rejected_batch_count == 1
    assert evidence.accepted_read_call_count == 2
    assert evidence.rejection_reason_counts == {"contains_write": 1}
    assert evidence.deterministic_control_violation_count == 0
    assert evidence.realized_write_from_multi_tool_batch_count == 0


def test_batch_evidence_flags_write_realized_inside_accepted_batch(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "run"
    case_dir = evidence_dir / "hdm-001"
    case_dir.mkdir(parents=True)
    (case_dir / "trace.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "attempt_started", "attempt_index": 1}),
                json.dumps(
                    {
                        "event": "multi_tool_batch_preflight",
                        "attempt_index": 1,
                        "accepted": True,
                        "tool_names": ["get_ticket", "update_ticket"],
                    }
                ),
                json.dumps(
                    {
                        "event": "tool_action_finished",
                        "action": {"tool": "update_ticket"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = M1BExperimentReceipt.model_validate(
        {
            "schema_version": "m3c-run-v1",
            "status": "complete",
            "baseline_complete": True,
            "run_id": "m3c-test",
            "frozen_configuration": {
                "schema_version": "m3c-glm52-compatibility-v1",
                "profile_name": "glm-5-2-openai",
                "model_id": "glm-5.2",
                "protocol": "openai_compatible",
                "thinking": None,
                "max_model_calls": 8,
                "max_tool_actions": 10,
                "trajectory_deadline_seconds": 300.0,
                "request_deadline_seconds": 60.0,
                "max_completion_tokens": 768,
                "case_order": [f"hdm-{index:03d}" for index in range(1, 13)],
            },
            "case_count": 1,
            "cases": [
                {
                    "schema_version": "m3c-case-v1",
                    "case_id": "hdm-001",
                    "task_ref": "test",
                    "ticket_id": "t-1",
                    "run_id": "m3c-test-hdm-001",
                    "model_id": "glm-5.2",
                    "stop_category": "ticket_terminal",
                    "terminal_reached": True,
                    "attempt_count": 1,
                    "tool_action_count": 1,
                    "usage_complete": True,
                    "observed_input_tokens": 1,
                    "observed_completion_tokens": 1,
                    "observed_reasoning_tokens": 0,
                    "observed_cached_input_tokens": 0,
                    "observed_provider_latency_ms": 1,
                    "independent_score_recorded": True,
                    "score_passed": True,
                    "matched_predicate_index": 0,
                    "scoring_failures": [],
                    "final_state_sha256": "0" * 64,
                    "trace_sha256": "1" * 64,
                }
            ],
            "score_pass_count": 1,
            "score_pass_rate": 1.0,
            "usage_complete": True,
            "observed_input_tokens": 1,
            "observed_completion_tokens": 1,
            "observed_reasoning_tokens": 0,
            "observed_cached_input_tokens": 0,
            "observed_inference_tokens": 2,
            "observed_provider_latency_ms": 1,
            "observed_tokens_per_verified_success": 2.0,
            "stop_category_counts": {"ticket_terminal": 1},
            "scoring_failure_counts": {},
        }
    )

    evidence = collect_m3c_batch_evidence(evidence_dir, run)

    assert evidence.realized_write_from_multi_tool_batch_count == 1
    assert evidence.deterministic_control_violation_count >= 1
