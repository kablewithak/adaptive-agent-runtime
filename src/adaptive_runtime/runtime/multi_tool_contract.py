from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaptive_runtime.environment.read_tools import ReadToolName


class MultiToolContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class MultiToolRealizationMode(StrEnum):
    READ_ONLY_SEQUENTIAL = "read_only_sequential"


class MultiToolBatchRejectionReason(StrEnum):
    CONTAINS_WRITE = "contains_write"
    UNKNOWN_TOOL = "unknown_tool"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    DUPLICATE_PROVIDER_CALL_ID = "duplicate_provider_call_id"
    DUPLICATE_READ_CALL = "duplicate_read_call"
    ACTION_BUDGET_EXCEEDED = "action_budget_exceeded"


class MultiToolRealizationPolicy(MultiToolContract):
    schema_version: Literal["m3a-multi-tool-policy-v1"] = "m3a-multi-tool-policy-v1"
    mode: Literal[MultiToolRealizationMode.READ_ONLY_SEQUENTIAL] = (
        MultiToolRealizationMode.READ_ONLY_SEQUENTIAL
    )
    require_full_preflight: Literal[True] = True
    preserve_provider_order: Literal[True] = True
    allow_write_calls: Literal[False] = False
    allow_parallel_execution: Literal[False] = False
    allow_semantic_reordering: Literal[False] = False
    allow_model_retry: Literal[False] = False
    allow_model_switch: Literal[False] = False
    allow_provider_retry: Literal[False] = False
    bound_by_remaining_tool_action_budget: Literal[True] = True
    validate_deadline_before_each_realized_action: Literal[True] = True


M3A_POLICY = MultiToolRealizationPolicy()

M3A_REALIZABLE_READ_TOOLS: tuple[ReadToolName, ...] = tuple(ReadToolName)
M3A_REALIZABLE_READ_TOOL_NAMES: tuple[str, ...] = tuple(
    tool.value for tool in M3A_REALIZABLE_READ_TOOLS
)
