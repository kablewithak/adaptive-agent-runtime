from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Literal, TypeVar

from pydantic import BaseModel

from adaptive_runtime.environment.domain import (
    Account,
    Approval,
    Entitlement,
    HarbourDeskVisibleState,
    OperationRecord,
    PolicyDocument,
    Subscription,
    Tenant,
    Ticket,
)

_MODEL = TypeVar("_MODEL", bound=BaseModel)
_TABLE_NAME = Literal[
    "tenants",
    "accounts",
    "subscriptions",
    "entitlements",
    "tickets",
    "policies",
    "approvals",
    "operations",
]
_READ_ALL_SQL: dict[_TABLE_NAME, str] = {
    "tenants": "SELECT payload_json FROM tenants ORDER BY ordinal",
    "accounts": "SELECT payload_json FROM accounts ORDER BY ordinal",
    "subscriptions": "SELECT payload_json FROM subscriptions ORDER BY ordinal",
    "entitlements": "SELECT payload_json FROM entitlements ORDER BY ordinal",
    "tickets": "SELECT payload_json FROM tickets ORDER BY ordinal",
    "policies": "SELECT payload_json FROM policies ORDER BY ordinal",
    "approvals": "SELECT payload_json FROM approvals ORDER BY ordinal",
    "operations": "SELECT payload_json FROM operations ORDER BY ordinal",
}


class StoreError(RuntimeError):
    """Raised when the local HarbourDesk state store cannot be used safely."""


class HarbourDeskStore:
    """SQLite-backed case store with read-only runtime-facing methods."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row

    @classmethod
    def in_memory(cls) -> HarbourDeskStore:
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open(cls, path: Path) -> HarbourDeskStore:
        return cls(sqlite3.connect(path))

    def __enter__(self) -> HarbourDeskStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def initialize(self, state: HarbourDeskVisibleState) -> None:
        """Replace store contents with one validated frozen case state."""
        self._connection.executescript(
            """
            PRAGMA foreign_keys = OFF;

            DROP TABLE IF EXISTS metadata;
            DROP TABLE IF EXISTS tenants;
            DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS subscriptions;
            DROP TABLE IF EXISTS entitlements;
            DROP TABLE IF EXISTS tickets;
            DROP TABLE IF EXISTS policies;
            DROP TABLE IF EXISTS approvals;
            DROP TABLE IF EXISTS operations;

            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE tenants (
                ordinal INTEGER NOT NULL,
                tenant_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE accounts (
                ordinal INTEGER NOT NULL,
                account_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE subscriptions (
                ordinal INTEGER NOT NULL,
                subscription_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE entitlements (
                ordinal INTEGER NOT NULL,
                account_id TEXT NOT NULL,
                feature_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (account_id, feature_id)
            );

            CREATE TABLE tickets (
                ordinal INTEGER NOT NULL,
                ticket_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE policies (
                ordinal INTEGER NOT NULL,
                document_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                authority TEXT NOT NULL,
                body TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE approvals (
                ordinal INTEGER NOT NULL,
                approval_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE operations (
                ordinal INTEGER NOT NULL,
                operation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )

        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    ("frozen_at", state.frozen_at.isoformat()),
                )
                self._insert_tenants(state.tenants)
                self._insert_accounts(state.accounts)
                self._insert_subscriptions(state.subscriptions)
                self._insert_entitlements(state.entitlements)
                self._insert_tickets(state.tickets)
                self._insert_policies(state.policies)
                self._insert_approvals(state.approvals)
                self._insert_operations(state.operations)
        except sqlite3.IntegrityError as exc:
            raise StoreError("case state violates a store uniqueness invariant") from exc

    def frozen_at_iso(self) -> str:
        row = self._connection.execute(
            "SELECT value FROM metadata WHERE key = 'frozen_at'"
        ).fetchone()
        if row is None:
            raise StoreError("store is not initialized")
        return str(row["value"])

    def get_ticket(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        payload = self._fetch_payload(
            "SELECT payload_json FROM tickets WHERE tenant_id = ? AND ticket_id = ?",
            (tenant_id, ticket_id),
        )
        return None if payload is None else Ticket.model_validate_json(payload)

    def get_account(self, tenant_id: str, account_id: str) -> Account | None:
        payload = self._fetch_payload(
            "SELECT payload_json FROM accounts WHERE tenant_id = ? AND account_id = ?",
            (tenant_id, account_id),
        )
        return None if payload is None else Account.model_validate_json(payload)

    def get_subscription(self, tenant_id: str, subscription_id: str) -> Subscription | None:
        # Scope by the subscription reference held by an account in the current tenant.
        # This deliberately still exposes an internally contradictory subscription.account_id
        # so F4 ownership-conflict cases remain diagnosable rather than disappearing as 404s.
        payload = self._fetch_payload(
            """
            SELECT s.payload_json
            FROM subscriptions AS s
            WHERE s.subscription_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM accounts AS a
                  WHERE a.tenant_id = ?
                    AND a.subscription_id = s.subscription_id
              )
            """,
            (subscription_id, tenant_id),
        )
        return None if payload is None else Subscription.model_validate_json(payload)

    def get_entitlements(self, tenant_id: str, account_id: str) -> tuple[Entitlement, ...] | None:
        account = self.get_account(tenant_id, account_id)
        if account is None:
            return None
        rows = self._connection.execute(
            """
            SELECT payload_json
            FROM entitlements
            WHERE account_id = ?
            ORDER BY ordinal
            """,
            (account_id,),
        ).fetchall()
        return tuple(Entitlement.model_validate_json(row["payload_json"]) for row in rows)

    def read_policy(self, document_id: str) -> PolicyDocument | None:
        payload = self._fetch_payload(
            "SELECT payload_json FROM policies WHERE document_id = ?",
            (document_id,),
        )
        return None if payload is None else PolicyDocument.model_validate_json(payload)

    def search_policy_rows(self) -> tuple[sqlite3.Row, ...]:
        rows = self._connection.execute(
            """
            SELECT document_id, version, valid_from, valid_to, authority, body, payload_json
            FROM policies
            ORDER BY ordinal
            """
        ).fetchall()
        return tuple(rows)

    def get_operation(self, tenant_id: str, operation_id: str) -> OperationRecord | None:
        payload = self._fetch_payload(
            """
            SELECT payload_json
            FROM operations
            WHERE tenant_id = ? AND operation_id = ?
            """,
            (tenant_id, operation_id),
        )
        return None if payload is None else OperationRecord.model_validate_json(payload)

    def snapshot(self) -> HarbourDeskVisibleState:
        from datetime import datetime

        frozen_at = datetime.fromisoformat(self.frozen_at_iso())
        return HarbourDeskVisibleState(
            frozen_at=frozen_at,
            tenants=self._read_all("tenants", Tenant),
            accounts=self._read_all("accounts", Account),
            subscriptions=self._read_all("subscriptions", Subscription),
            entitlements=self._read_all("entitlements", Entitlement),
            tickets=self._read_all("tickets", Ticket),
            policies=self._read_all("policies", PolicyDocument),
            approvals=self._read_all("approvals", Approval),
            operations=self._read_all("operations", OperationRecord),
        )

    def _insert_tenants(self, records: tuple[Tenant, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO tenants(ordinal, tenant_id, payload_json)
                VALUES (?, ?, ?)
                """,
                (ordinal, record.tenant_id, record.model_dump_json()),
            )

    def _insert_accounts(self, records: tuple[Account, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO accounts(
                    ordinal, account_id, tenant_id, subscription_id, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.account_id,
                    record.tenant_id,
                    record.subscription_id,
                    record.model_dump_json(),
                ),
            )

    def _insert_subscriptions(self, records: tuple[Subscription, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO subscriptions(ordinal, subscription_id, account_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.subscription_id,
                    record.account_id,
                    record.model_dump_json(),
                ),
            )

    def _insert_entitlements(self, records: tuple[Entitlement, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO entitlements(ordinal, account_id, feature_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.account_id,
                    record.feature_id,
                    record.model_dump_json(),
                ),
            )

    def _insert_tickets(self, records: tuple[Ticket, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO tickets(ordinal, ticket_id, tenant_id, account_id, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.ticket_id,
                    record.tenant_id,
                    record.account_id,
                    record.model_dump_json(),
                ),
            )

    def _insert_policies(self, records: tuple[PolicyDocument, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO policies(
                    ordinal, document_id, version, valid_from, valid_to,
                    authority, body, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.document_id,
                    record.version,
                    record.valid_from.isoformat(),
                    None if record.valid_to is None else record.valid_to.isoformat(),
                    record.authority,
                    record.body,
                    record.model_dump_json(),
                ),
            )

    def _insert_approvals(self, records: tuple[Approval, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO approvals(ordinal, approval_id, tenant_id, account_id, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.approval_id,
                    record.tenant_id,
                    record.account_id,
                    record.model_dump_json(),
                ),
            )

    def _insert_operations(self, records: tuple[OperationRecord, ...]) -> None:
        for ordinal, record in enumerate(records):
            self._connection.execute(
                """
                INSERT INTO operations(
                    ordinal, operation_id, tenant_id, account_id, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ordinal,
                    record.operation_id,
                    record.tenant_id,
                    record.account_id,
                    record.model_dump_json(),
                ),
            )

    def _fetch_payload(self, sql: str, parameters: tuple[str, ...]) -> str | None:
        row = self._connection.execute(sql, parameters).fetchone()
        return None if row is None else str(row["payload_json"])

    def _read_all(
        self,
        table: _TABLE_NAME,
        model: type[_MODEL],
    ) -> tuple[_MODEL, ...]:
        rows = self._connection.execute(_READ_ALL_SQL[table]).fetchall()
        return tuple(model.model_validate_json(str(row["payload_json"])) for row in rows)
