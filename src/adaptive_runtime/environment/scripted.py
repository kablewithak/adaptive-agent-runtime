from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.read_tools import (
    ReadToolName,
    ReadToolResult,
    execute_read_tool,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore


class ScriptContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ScriptedReadStep(ScriptContract):
    call_id: str = Field(min_length=1, max_length=100)
    tool: ReadToolName
    arguments: dict[str, object]


class ScriptedReadTrajectory(ScriptContract):
    case_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    steps: tuple[ScriptedReadStep, ...] = Field(min_length=1, max_length=20)


class ScriptedReadTrace(ScriptContract):
    case_id: str
    results: tuple[ReadToolResult, ...]

    @property
    def all_calls_succeeded(self) -> bool:
        return all(result.status.value == "ok" for result in self.results)


def run_scripted_reads(
    store: HarbourDeskStore,
    trajectory: ScriptedReadTrajectory,
) -> ScriptedReadTrace:
    results = tuple(
        execute_read_tool(
            store=store,
            tenant_id=trajectory.tenant_id,
            call_id=step.call_id,
            tool=step.tool,
            arguments=step.arguments,
        )
        for step in trajectory.steps
    )
    return ScriptedReadTrace(case_id=trajectory.case_id, results=results)
