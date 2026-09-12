from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from adaptive_runtime.environment.read_tools import ReadToolErrorCode, ReadToolResult
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    EnvironmentResult,
    HarbourDeskEnvironment,
)
from adaptive_runtime.environment.write_tools import WriteToolErrorCode, WriteToolResult


class EndToEndContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ScriptedEnvironmentStep(EndToEndContract):
    call: EnvironmentCall
    expected_status: Literal["ok", "error"]
    expected_error_code: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_expected_error(self) -> ScriptedEnvironmentStep:
        if self.expected_status == "ok" and self.expected_error_code is not None:
            raise ValueError("successful step cannot declare expected_error_code")
        if self.expected_status == "error" and self.expected_error_code is None:
            raise ValueError("error step requires expected_error_code")
        return self


class ScriptedEnvironmentTrajectory(EndToEndContract):
    case_id: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(min_length=1, max_length=100)
    ticket_id: str = Field(min_length=1, max_length=100)
    steps: tuple[ScriptedEnvironmentStep, ...] = Field(min_length=1, max_length=40)


class ScriptedEnvironmentStepResult(EndToEndContract):
    step_index: int = Field(ge=0)
    call_id: str
    tool: str
    observed_status: str
    observed_error_code: str | None
    matched_expectation: bool


class ScriptedEnvironmentTrace(EndToEndContract):
    case_id: str
    results: tuple[ScriptedEnvironmentStepResult, ...]

    @property
    def all_steps_matched(self) -> bool:
        return all(result.matched_expectation for result in self.results)


_CALL_ADAPTER: TypeAdapter[EnvironmentCall] = TypeAdapter(EnvironmentCall)


def load_trajectory_json(payload: str) -> ScriptedEnvironmentTrajectory:
    return ScriptedEnvironmentTrajectory.model_validate_json(payload)


def run_scripted_environment(
    environment: HarbourDeskEnvironment,
    trajectory: ScriptedEnvironmentTrajectory,
) -> ScriptedEnvironmentTrace:
    if trajectory.tenant_id != environment.tenant_id:
        raise ValueError("trajectory tenant does not match environment tenant")
    if trajectory.ticket_id != environment.ticket_id:
        raise ValueError("trajectory ticket does not match environment ticket")

    results: list[ScriptedEnvironmentStepResult] = []
    for index, step in enumerate(trajectory.steps):
        call = _CALL_ADAPTER.validate_python(step.call)
        observed = environment.execute(call)
        observed_status = observed.status.value
        observed_error_code = _error_code_value(observed)
        matched = observed_status == step.expected_status
        if matched and step.expected_status == "error":
            matched = observed_error_code == step.expected_error_code

        results.append(
            ScriptedEnvironmentStepResult(
                step_index=index,
                call_id=observed.call_id,
                tool=observed.tool.value,
                observed_status=observed_status,
                observed_error_code=observed_error_code,
                matched_expectation=matched,
            )
        )

    return ScriptedEnvironmentTrace(case_id=trajectory.case_id, results=tuple(results))


def _error_code_value(result: EnvironmentResult) -> str | None:
    if isinstance(result, ReadToolResult):
        code: ReadToolErrorCode | None = result.error_code
        return None if code is None else code.value

    if isinstance(result, WriteToolResult):
        write_code: WriteToolErrorCode | None = result.error_code
        return None if write_code is None else write_code.value

    raise AssertionError("unknown environment result")  # pragma: no cover
