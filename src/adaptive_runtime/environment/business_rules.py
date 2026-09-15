from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adaptive_runtime.environment.domain import TicketResolutionReasonCode


class RuleContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CancellationRules(RuleContract):
    minimum_notice_days: int = Field(ge=0, le=365)


class HarbourDeskBusinessRules(RuleContract):
    schema_version: str
    organisation: str
    synthetic_only: bool
    plans: dict[str, tuple[str, ...]]
    deterministic_controls: dict[str, str]
    terminal_reason_codes: tuple[TicketResolutionReasonCode, ...] = Field(min_length=1)
    benchmark_families: dict[str, str]
    cancellation: CancellationRules

    @classmethod
    def load(cls, path: Path) -> HarbourDeskBusinessRules:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def desired_entitlement_state(self, plan_id: str, feature_id: str) -> bool:
        if plan_id not in self.plans:
            raise KeyError(plan_id)
        return feature_id in self.plans[plan_id]

    def allows_terminal_reason(
        self,
        reason_code: TicketResolutionReasonCode,
    ) -> bool:
        return reason_code in self.terminal_reason_codes

    def minimum_cancellation_effective_at(self, frozen_at: datetime) -> datetime:
        return frozen_at + timedelta(days=self.cancellation.minimum_notice_days)
