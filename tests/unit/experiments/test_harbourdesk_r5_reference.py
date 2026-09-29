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
from adaptive_runtime.experiments.harbourdesk_m1b import load_m1b_public_cases
from adaptive_runtime.experiments.harbourdesk_m3d import M3D_BUDGET
from adaptive_runtime.experiments.harbourdesk_r5 import load_r5_manifest
from adaptive_runtime.experiments.harbourdesk_r5_reference import (
    R5ReferenceCase,
    _run_reference_case,
)


class FakeProvider:
    def __init__(self, result: ModelResult) -> None:
        self.result = result
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self.result.model_copy(update={"request_id": request.request_id})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def test_r5_manifest_selects_exactly_90_development_cases() -> None:
    manifest = load_r5_manifest(_repo_root())

    assert len(manifest.case_order) == 90
    assert len(set(manifest.case_order)) == 90
    assert len(manifest.entries) == 90
    assert {entry.family for entry in manifest.entries} == {
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
        "F6",
    }


def test_r5_single_case_uses_m3d_budget_and_independent_scorer(
    tmp_path: Path,
) -> None:
    public = next(case for case in load_m1b_public_cases(_repo_root()) if case.case_id == "hdm-003")
    expected = ExpectedCaseOutcome(
        case_id=public.case_id,
        terminal_ticket_id=public.ticket_id,
        acceptable_terminal_predicates=(
            ExpectedTerminalPredicate(
                disposition=ExpectedDisposition.CLARIFICATION,
                reason_code="ACCOUNT_OR_FEATURE_AMBIGUOUS",
                expected_effective_write_count=0,
                max_effective_write_count=0,
            ),
        ),
    )
    item = R5ReferenceCase(
        case_id=public.case_id,
        family="F2",
        template_id="synthetic-test",
        task_ref=public.task_ref,
        tenant_id=public.tenant_id,
        ticket_id=public.ticket_id,
        initial=public.initial,
        rules=public.rules,
        expected=expected,
    )

    provider = FakeProvider(
        ModelResult(
            request_id="placeholder",
            outcome=ProviderOutcome.SUCCESS,
            returned_model="glm-5.2",
            tool_calls=(
                ToolCall(
                    id="update-ticket",
                    function=ToolCallFunction(
                        name="update_ticket",
                        arguments=json.dumps(
                            {
                                "expected_ticket_revision": 1,
                                "status": "pending_clarification",
                                "resolution_reason_code": ("ACCOUNT_OR_FEATURE_AMBIGUOUS"),
                                "evidence_document_ids": [],
                                "operation_ids": [],
                            }
                        ),
                    ),
                ),
            ),
            stop_reason="tool_calls",
            usage=UsageAccounting(
                input_tokens=1000,
                completion_tokens=50,
            ),
            http_status=200,
            latency_ms=10,
        )
    )

    receipt = _run_reference_case(
        item=item,
        provider=provider,
        profile=_profile(),
        suite_run_id="r5-test",
        trace_path=tmp_path / "trace.jsonl",
    )

    assert receipt.score_passed is True
    assert receipt.stop_category.value == "ticket_terminal"
    assert receipt.usage_complete is True
    assert receipt.deterministic_control_violation_count == 0
    assert len(provider.requests) == 1
    assert provider.requests[0].max_completion_tokens == (M3D_BUDGET.max_completion_tokens)
    assert M3D_BUDGET.max_completion_tokens == 1536
