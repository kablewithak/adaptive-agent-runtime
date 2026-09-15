from __future__ import annotations

from importlib import import_module
from typing import Any

from adaptive_runtime.environment.business_rules import (
    CancellationRules,
    HarbourDeskBusinessRules,
)
from adaptive_runtime.environment.domain import (
    Account,
    Approval,
    ApprovalAction,
    ApprovalIssuerType,
    Entitlement,
    HarbourDeskVisibleState,
    OperationRecord,
    OperationStatus,
    PolicyDocument,
    Subscription,
    SubscriptionStatus,
    Tenant,
    Ticket,
    TicketStatus,
)
from adaptive_runtime.environment.end_to_end import (
    ScriptedEnvironmentStep,
    ScriptedEnvironmentStepResult,
    ScriptedEnvironmentTrace,
    ScriptedEnvironmentTrajectory,
    load_trajectory_json,
    run_scripted_environment,
)
from adaptive_runtime.environment.mutation_rehearsal import (
    MutationRehearsalSummary,
    MutationScenarioResult,
    run_manual_mutation_rehearsal,
)
from adaptive_runtime.environment.read_rehearsal import (
    CaseReadRehearsalResult,
    ReadRehearsalSummary,
    RehearsalStatus,
    run_manual_read_rehearsal,
)
from adaptive_runtime.environment.read_tools import (
    ReadToolErrorCode,
    ReadToolName,
    ReadToolResult,
    ReadToolStatus,
    execute_read_tool,
)
from adaptive_runtime.environment.runtime import (
    EnvironmentCall,
    EnvironmentResult,
    HarbourDeskEnvironment,
    ReadEnvironmentCall,
    WriteEnvironmentCall,
)
from adaptive_runtime.environment.scripted import (
    ScriptedReadStep,
    ScriptedReadTrace,
    ScriptedReadTrajectory,
    run_scripted_reads,
)
from adaptive_runtime.environment.sqlite_store import (
    HarbourDeskStore,
    StoreError,
    StoreIdempotencyConflict,
    StoreRevisionConflict,
)
from adaptive_runtime.environment.write_tools import (
    EntitlementWriteObservation,
    ReconcileEntitlementArgs,
    ScheduleCancellationArgs,
    SubscriptionWriteObservation,
    TicketWriteObservation,
    UpdateTicketArgs,
    WriteToolErrorCode,
    WriteToolName,
    WriteToolResult,
    WriteToolStatus,
    execute_write_tool,
)

_LAZY_EXPORTS = {
    "EndToEndCaseResult": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "EndToEndCaseResult",
    ),
    "EndToEndRehearsalError": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "EndToEndRehearsalError",
    ),
    "EndToEndRehearsalStatus": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "EndToEndRehearsalStatus",
    ),
    "EndToEndRehearsalSummary": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "EndToEndRehearsalSummary",
    ),
    "PrivateEvaluationDataMissing": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "PrivateEvaluationDataMissing",
    ),
    "run_end_to_end_case": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "run_end_to_end_case",
    ),
    "run_manual_end_to_end_rehearsal": (
        "adaptive_runtime.environment.end_to_end_rehearsal",
        "run_manual_end_to_end_rehearsal",
    ),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "Account",
    "Approval",
    "ApprovalAction",
    "ApprovalIssuerType",
    "CancellationRules",
    "CaseReadRehearsalResult",
    "EndToEndCaseResult",
    "EndToEndRehearsalError",
    "EndToEndRehearsalStatus",
    "EndToEndRehearsalSummary",
    "Entitlement",
    "EntitlementWriteObservation",
    "EnvironmentCall",
    "EnvironmentResult",
    "HarbourDeskBusinessRules",
    "HarbourDeskEnvironment",
    "HarbourDeskStore",
    "HarbourDeskVisibleState",
    "MutationRehearsalSummary",
    "MutationScenarioResult",
    "OperationRecord",
    "OperationStatus",
    "PolicyDocument",
    "PrivateEvaluationDataMissing",
    "ReadEnvironmentCall",
    "ReadRehearsalSummary",
    "ReadToolErrorCode",
    "ReadToolName",
    "ReadToolResult",
    "ReadToolStatus",
    "ReconcileEntitlementArgs",
    "RehearsalStatus",
    "ScheduleCancellationArgs",
    "ScriptedEnvironmentStep",
    "ScriptedEnvironmentStepResult",
    "ScriptedEnvironmentTrace",
    "ScriptedEnvironmentTrajectory",
    "ScriptedReadStep",
    "ScriptedReadTrace",
    "ScriptedReadTrajectory",
    "StoreError",
    "StoreIdempotencyConflict",
    "StoreRevisionConflict",
    "Subscription",
    "SubscriptionStatus",
    "SubscriptionWriteObservation",
    "Tenant",
    "Ticket",
    "TicketStatus",
    "TicketWriteObservation",
    "UpdateTicketArgs",
    "WriteEnvironmentCall",
    "WriteToolErrorCode",
    "WriteToolName",
    "WriteToolResult",
    "WriteToolStatus",
    "execute_read_tool",
    "execute_write_tool",
    "load_trajectory_json",
    "run_end_to_end_case",
    "run_manual_end_to_end_rehearsal",
    "run_manual_mutation_rehearsal",
    "run_manual_read_rehearsal",
    "run_scripted_environment",
    "run_scripted_reads",
]
