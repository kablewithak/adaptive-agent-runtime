from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from adaptive_runtime.environment.domain import (
    Account,
    Entitlement,
    OperationRecord,
    PolicyDocument,
    Subscription,
    Ticket,
)
from adaptive_runtime.environment.sqlite_store import HarbourDeskStore


class ToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReadToolName(StrEnum):
    GET_TICKET = "get_ticket"
    GET_ACCOUNT = "get_account"
    GET_SUBSCRIPTION = "get_subscription"
    GET_ENTITLEMENTS = "get_entitlements"
    SEARCH_POLICIES = "search_policies"
    READ_POLICY = "read_policy"
    GET_OPERATION = "get_operation"


class ReadToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class ReadToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_FOUND = "not_found"


class GetTicketArgs(ToolContract):
    ticket_id: str = Field(min_length=1, max_length=100)


class GetAccountArgs(ToolContract):
    account_id: str = Field(min_length=1, max_length=100)


class GetSubscriptionArgs(ToolContract):
    subscription_id: str = Field(min_length=1, max_length=100)


class GetEntitlementsArgs(ToolContract):
    account_id: str = Field(min_length=1, max_length=100)


class SearchPoliciesArgs(ToolContract):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=5, ge=1, le=20)


class ReadPolicyArgs(ToolContract):
    document_id: str = Field(min_length=1, max_length=100)


class GetOperationArgs(ToolContract):
    operation_id: str = Field(min_length=1, max_length=100)


class TicketObservation(ToolContract):
    kind: Literal["ticket"] = "ticket"
    ticket: Ticket


class AccountObservation(ToolContract):
    kind: Literal["account"] = "account"
    account: Account


class SubscriptionObservation(ToolContract):
    kind: Literal["subscription"] = "subscription"
    subscription: Subscription


class EntitlementsObservation(ToolContract):
    kind: Literal["entitlements"] = "entitlements"
    account_id: str
    entitlements: tuple[Entitlement, ...]


class PolicySearchHit(ToolContract):
    document_id: str
    version: int
    authority: str
    valid_from: datetime
    valid_to: datetime | None
    active_at_frozen_time: bool
    match_score: int = Field(ge=1)
    excerpt: str = Field(max_length=240)


class PolicySearchObservation(ToolContract):
    kind: Literal["policy_search"] = "policy_search"
    query: str
    hits: tuple[PolicySearchHit, ...]


class PolicyObservation(ToolContract):
    kind: Literal["policy"] = "policy"
    policy: PolicyDocument
    active_at_frozen_time: bool


class OperationObservation(ToolContract):
    kind: Literal["operation"] = "operation"
    operation: OperationRecord


ReadToolData = Annotated[
    TicketObservation
    | AccountObservation
    | SubscriptionObservation
    | EntitlementsObservation
    | PolicySearchObservation
    | PolicyObservation
    | OperationObservation,
    Field(discriminator="kind"),
]

_DATA_ADAPTER: TypeAdapter[ReadToolData] = TypeAdapter(ReadToolData)


class ReadToolResult(ToolContract):
    call_id: str = Field(min_length=1, max_length=100)
    tool: ReadToolName
    status: ReadToolStatus
    data: ReadToolData | None = None
    error_code: ReadToolErrorCode | None = None
    message: str | None = Field(default=None, max_length=300)


_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def execute_read_tool(
    store: HarbourDeskStore,
    tenant_id: str,
    call_id: str,
    tool: ReadToolName,
    arguments: dict[str, object],
) -> ReadToolResult:
    data: ReadToolData

    try:
        if tool is ReadToolName.GET_TICKET:
            ticket_args = GetTicketArgs.model_validate(arguments)
            ticket = store.get_ticket(tenant_id, ticket_args.ticket_id)
            if ticket is None:
                return _not_found(call_id, tool, "ticket not found in tenant scope")
            data = TicketObservation(ticket=ticket)

        elif tool is ReadToolName.GET_ACCOUNT:
            account_args = GetAccountArgs.model_validate(arguments)
            account = store.get_account(tenant_id, account_args.account_id)
            if account is None:
                return _not_found(call_id, tool, "account not found in tenant scope")
            data = AccountObservation(account=account)

        elif tool is ReadToolName.GET_SUBSCRIPTION:
            subscription_args = GetSubscriptionArgs.model_validate(arguments)
            subscription = store.get_subscription(
                tenant_id,
                subscription_args.subscription_id,
            )
            if subscription is None:
                return _not_found(
                    call_id,
                    tool,
                    "subscription not referenced by an account in tenant scope",
                )
            data = SubscriptionObservation(subscription=subscription)

        elif tool is ReadToolName.GET_ENTITLEMENTS:
            entitlements_args = GetEntitlementsArgs.model_validate(arguments)
            entitlements = store.get_entitlements(
                tenant_id,
                entitlements_args.account_id,
            )
            if entitlements is None:
                return _not_found(call_id, tool, "account not found in tenant scope")
            data = EntitlementsObservation(
                account_id=entitlements_args.account_id,
                entitlements=entitlements,
            )

        elif tool is ReadToolName.SEARCH_POLICIES:
            search_args = SearchPoliciesArgs.model_validate(arguments)
            data = _search_policies(store, search_args)

        elif tool is ReadToolName.READ_POLICY:
            policy_args = ReadPolicyArgs.model_validate(arguments)
            policy = store.read_policy(policy_args.document_id)
            if policy is None:
                return _not_found(call_id, tool, "policy document not found")
            data = PolicyObservation(
                policy=policy,
                active_at_frozen_time=_is_active(
                    policy.valid_from,
                    policy.valid_to,
                    datetime.fromisoformat(store.frozen_at_iso()),
                ),
            )

        elif tool is ReadToolName.GET_OPERATION:
            operation_args = GetOperationArgs.model_validate(arguments)
            operation = store.get_operation(
                tenant_id,
                operation_args.operation_id,
            )
            if operation is None:
                return _not_found(call_id, tool, "operation not found in tenant scope")
            data = OperationObservation(operation=operation)

        else:  # pragma: no cover - enum exhaustiveness guard
            raise AssertionError(f"unhandled read tool: {tool}")

    except ValidationError:
        return ReadToolResult(
            call_id=call_id,
            tool=tool,
            status=ReadToolStatus.ERROR,
            error_code=ReadToolErrorCode.INVALID_ARGUMENTS,
            message="tool arguments failed schema validation",
        )

    return ReadToolResult(
        call_id=call_id,
        tool=tool,
        status=ReadToolStatus.OK,
        data=_DATA_ADAPTER.validate_python(data),
    )


def _not_found(
    call_id: str,
    tool: ReadToolName,
    message: str,
) -> ReadToolResult:
    return ReadToolResult(
        call_id=call_id,
        tool=tool,
        status=ReadToolStatus.ERROR,
        error_code=ReadToolErrorCode.NOT_FOUND,
        message=message,
    )


def _search_policies(
    store: HarbourDeskStore,
    args: SearchPoliciesArgs,
) -> PolicySearchObservation:
    query_tokens = tuple(dict.fromkeys(_TOKEN_RE.findall(args.query.lower())))
    frozen_at = datetime.fromisoformat(store.frozen_at_iso())
    hits: list[PolicySearchHit] = []

    for row in store.search_policy_rows():
        searchable = " ".join(
            (
                str(row["document_id"]),
                str(row["authority"]),
                str(row["body"]),
            )
        ).lower()
        score = sum(1 for token in query_tokens if token in searchable)
        if score == 0:
            continue

        valid_from = datetime.fromisoformat(str(row["valid_from"]))
        valid_to_raw = row["valid_to"]
        valid_to = None if valid_to_raw is None else datetime.fromisoformat(str(valid_to_raw))
        body = str(row["body"])
        excerpt = body if len(body) <= 240 else body[:237].rstrip() + "..."

        hits.append(
            PolicySearchHit(
                document_id=str(row["document_id"]),
                version=int(row["version"]),
                authority=str(row["authority"]),
                valid_from=valid_from,
                valid_to=valid_to,
                active_at_frozen_time=_is_active(valid_from, valid_to, frozen_at),
                match_score=score,
                excerpt=excerpt,
            )
        )

    hits.sort(
        key=lambda hit: (
            -hit.match_score,
            -int(hit.active_at_frozen_time),
            -hit.version,
            hit.document_id,
        )
    )

    return PolicySearchObservation(
        query=args.query,
        hits=tuple(hits[: args.max_results]),
    )


def _is_active(
    valid_from: datetime,
    valid_to: datetime | None,
    frozen_at: datetime,
) -> bool:
    return valid_from <= frozen_at and (valid_to is None or frozen_at < valid_to)
