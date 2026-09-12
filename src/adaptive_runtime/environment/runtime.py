from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.business_rules import HarbourDeskBusinessRules
from adaptive_runtime.environment.domain import HarbourDeskVisibleState
from adaptive_runtime.environment.model_observation import (
    ModelVisibleInitialObservation,
    build_initial_model_observation,
)
from adaptive_runtime.environment.read_tools import (
    ReadToolName,
    ReadToolResult,
    execute_read_tool,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore
from adaptive_runtime.environment.write_tools import (
    WriteToolName,
    WriteToolResult,
    execute_write_tool,
)


class EnvironmentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReadEnvironmentCall(EnvironmentContract):
    kind: Literal["read"] = "read"
    call_id: str = Field(min_length=1, max_length=100)
    tool: ReadToolName
    arguments: dict[str, object]


class WriteEnvironmentCall(EnvironmentContract):
    kind: Literal["write"] = "write"
    call_id: str = Field(min_length=1, max_length=100)
    tool: WriteToolName
    idempotency_key: str = Field(min_length=1, max_length=200)
    arguments: dict[str, object]


EnvironmentCall = Annotated[
    ReadEnvironmentCall | WriteEnvironmentCall,
    Field(discriminator="kind"),
]
EnvironmentResult = ReadToolResult | WriteToolResult


class HarbourDeskEnvironment:
    """One deterministic execution boundary for HarbourDesk read and write tools."""

    def __init__(
        self,
        *,
        store: HarbourDeskStore,
        rules: HarbourDeskBusinessRules,
        tenant_id: str,
        ticket_id: str,
    ) -> None:
        self._store = store
        self._rules = rules
        self._tenant_id = tenant_id
        self._ticket_id = ticket_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def ticket_id(self) -> str:
        return self._ticket_id

    def execute(self, call: EnvironmentCall) -> EnvironmentResult:
        if isinstance(call, ReadEnvironmentCall):
            return execute_read_tool(
                store=self._store,
                tenant_id=self._tenant_id,
                call_id=call.call_id,
                tool=call.tool,
                arguments=call.arguments,
            )

        return execute_write_tool(
            store=self._store,
            rules=self._rules,
            tenant_id=self._tenant_id,
            ticket_id=self._ticket_id,
            call_id=call.call_id,
            idempotency_key=call.idempotency_key,
            tool=call.tool,
            arguments=call.arguments,
        )

    def initial_observation(self) -> ModelVisibleInitialObservation:
        """Return the frozen model-visible projection for the current task scope."""
        return build_initial_model_observation(
            state=self._store.snapshot(),
            tenant_id=self._tenant_id,
            ticket_id=self._ticket_id,
        )

    def snapshot(self) -> HarbourDeskVisibleState:
        return self._store.snapshot()
