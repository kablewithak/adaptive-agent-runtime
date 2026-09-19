from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class PreparedMultiToolRead(MultiToolContract):
    provider_tool_call_id: str = Field(min_length=1, max_length=300)
    tool: ReadToolName
    arguments: dict[str, object]
    normalized_signature: str = Field(min_length=1)


class MultiToolBatchPreflight(MultiToolContract):
    accepted: bool
    prepared_reads: tuple[PreparedMultiToolRead, ...] = ()
    rejection_reason: MultiToolBatchRejectionReason | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> MultiToolBatchPreflight:
        if self.accepted:
            if not self.prepared_reads:
                raise ValueError("accepted preflight requires prepared reads")
            if self.rejection_reason is not None:
                raise ValueError("accepted preflight cannot have a rejection reason")
            return self

        if self.prepared_reads:
            raise ValueError("rejected preflight cannot expose executable reads")
        if self.rejection_reason is None:
            raise ValueError("rejected preflight requires a rejection reason")
        return self


M3A_POLICY = MultiToolRealizationPolicy()

M3A_REALIZABLE_READ_TOOLS: tuple[ReadToolName, ...] = tuple(ReadToolName)
M3A_REALIZABLE_READ_TOOL_NAMES: tuple[str, ...] = tuple(
    tool.value for tool in M3A_REALIZABLE_READ_TOOLS
)
