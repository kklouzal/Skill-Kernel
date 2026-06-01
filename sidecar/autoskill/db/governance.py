from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class EvolutionTransactionRecord:
    evolution_transaction_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    transaction_kind: str
    status: str
    idempotency_key: str
    plan_hash: str
    actor: str
    cause: dict[str, Any]
    source_evidence_ids: list[UUID]
    source_memory_ids: list[UUID]
    policy_snapshot: dict[str, Any]
    metrics: dict[str, Any]
    rollback_of_transaction_id: UUID | None
    started_at: datetime
    committed_at: datetime | None
    rolled_back_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> EvolutionTransactionRecord:
        return cls(
            evolution_transaction_id=row["evolution_transaction_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            transaction_kind=row["transaction_kind"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            plan_hash=row["plan_hash"],
            actor=row["actor"],
            cause=_json_dict(row["cause"]),
            source_evidence_ids=list(row["source_evidence_ids"]),
            source_memory_ids=list(row["source_memory_ids"]),
            policy_snapshot=_json_dict(row["policy_snapshot"]),
            metrics=_json_dict(row["metrics"]),
            rollback_of_transaction_id=_row_get(row, "rollback_of_transaction_id"),
            started_at=row["started_at"],
            committed_at=_row_get(row, "committed_at"),
            rolled_back_at=_row_get(row, "rolled_back_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "evolution_transaction_id": str(self.evolution_transaction_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "transaction_kind": self.transaction_kind,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "plan_hash": self.plan_hash,
            "actor": self.actor,
            "cause": self.cause,
            "source_evidence_ids": [str(item) for item in self.source_evidence_ids],
            "source_memory_ids": [str(item) for item in self.source_memory_ids],
            "policy_snapshot": self.policy_snapshot,
            "metrics": self.metrics,
            "rollback_of_transaction_id": (
                str(self.rollback_of_transaction_id)
                if self.rollback_of_transaction_id
                else None
            ),
            "started_at": self.started_at.isoformat(),
            "committed_at": _iso_or_none(self.committed_at),
            "rolled_back_at": _iso_or_none(self.rolled_back_at),
        }


@dataclass(frozen=True)
class TransactionStartResult:
    transaction: EvolutionTransactionRecord
    created: bool

    def to_json(self) -> dict[str, Any]:
        return {"created": self.created, "transaction": self.transaction.to_json()}


@dataclass(frozen=True)
class EvolutionTransactionItemRecord:
    transaction_item_id: UUID
    evolution_transaction_id: UUID
    item_kind: str
    item_id: UUID | None
    relative_path: str | None
    before_hash: str | None
    after_hash: str | None
    activation_state: str
    rollback_action: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> EvolutionTransactionItemRecord:
        return cls(
            transaction_item_id=row["transaction_item_id"],
            evolution_transaction_id=row["evolution_transaction_id"],
            item_kind=row["item_kind"],
            item_id=_row_get(row, "item_id"),
            relative_path=_row_get(row, "relative_path"),
            before_hash=_row_get(row, "before_hash"),
            after_hash=_row_get(row, "after_hash"),
            activation_state=row["activation_state"],
            rollback_action=_json_dict(row["rollback_action"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "transaction_item_id": str(self.transaction_item_id),
            "evolution_transaction_id": str(self.evolution_transaction_id),
            "item_kind": self.item_kind,
            "item_id": str(self.item_id) if self.item_id else None,
            "relative_path": self.relative_path,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "activation_state": self.activation_state,
            "rollback_action": self.rollback_action,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class RevocationRequestRecord:
    revocation_request_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    request_kind: str
    root_object_type: str
    root_object_id: UUID
    status: str
    traversal_summary: dict[str, Any]
    created_by_job_id: UUID | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> RevocationRequestRecord:
        return cls(
            revocation_request_id=row["revocation_request_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            request_kind=row["request_kind"],
            root_object_type=row["root_object_type"],
            root_object_id=row["root_object_id"],
            status=row["status"],
            traversal_summary=_json_dict(row["traversal_summary"]),
            created_by_job_id=_row_get(row, "created_by_job_id"),
            created_at=row["created_at"],
            completed_at=_row_get(row, "completed_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "revocation_request_id": str(self.revocation_request_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "request_kind": self.request_kind,
            "root_object_type": self.root_object_type,
            "root_object_id": str(self.root_object_id),
            "status": self.status,
            "traversal_summary": self.traversal_summary,
            "created_by_job_id": str(self.created_by_job_id) if self.created_by_job_id else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": _iso_or_none(self.completed_at),
        }


class GovernanceStore(Protocol):
    async def start_transaction(
        self,
        *,
        workspace_key: str,
        transaction_kind: str,
        idempotency_key: str,
        plan_hash: str,
        actor: str = "autoskill-sidecar",
        cause: dict[str, Any] | None = None,
        source_evidence_ids: list[UUID] | None = None,
        source_memory_ids: list[UUID] | None = None,
        policy_snapshot: dict[str, Any] | None = None,
        rollback_of_transaction_id: UUID | None = None,
    ) -> TransactionStartResult:
        """Create or return an idempotent evolution transaction."""

    async def update_transaction_status(
        self,
        *,
        evolution_transaction_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> EvolutionTransactionRecord | None:
        """Move an evolution transaction through a deterministic state transition."""

    async def record_transaction_item(
        self,
        *,
        evolution_transaction_id: UUID,
        item_kind: str,
        activation_state: str,
        item_id: UUID | None = None,
        relative_path: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        rollback_action: dict[str, Any] | None = None,
    ) -> EvolutionTransactionItemRecord:
        """Record a transaction item with rollback metadata."""

    async def request_revocation(
        self,
        *,
        workspace_key: str,
        request_kind: str,
        root_object_type: str,
        root_object_id: UUID,
        traversal_summary: dict[str, Any] | None = None,
        created_by_job_id: UUID | None = None,
    ) -> RevocationRequestRecord:
        """Queue a rollback/retention/quarantine revocation traversal."""


class NullGovernanceStore:
    async def start_transaction(
        self,
        *,
        workspace_key: str,
        transaction_kind: str,
        idempotency_key: str,
        plan_hash: str,
        actor: str = "autoskill-sidecar",
        cause: dict[str, Any] | None = None,
        source_evidence_ids: list[UUID] | None = None,
        source_memory_ids: list[UUID] | None = None,
        policy_snapshot: dict[str, Any] | None = None,
        rollback_of_transaction_id: UUID | None = None,
    ) -> TransactionStartResult:
        now = datetime.now(UTC)
        record = EvolutionTransactionRecord(
            evolution_transaction_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            transaction_kind=transaction_kind,
            status="planned",
            idempotency_key=idempotency_key,
            plan_hash=plan_hash,
            actor=actor,
            cause=cause or {},
            source_evidence_ids=source_evidence_ids or [],
            source_memory_ids=source_memory_ids or [],
            policy_snapshot=policy_snapshot or {},
            metrics={},
            rollback_of_transaction_id=rollback_of_transaction_id,
            started_at=now,
            committed_at=None,
            rolled_back_at=None,
        )
        return TransactionStartResult(transaction=record, created=True)

    async def update_transaction_status(
        self,
        *,
        evolution_transaction_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> EvolutionTransactionRecord | None:
        now = datetime.now(UTC)
        return EvolutionTransactionRecord(
            evolution_transaction_id=evolution_transaction_id,
            workspace_id=None,
            workspace_key=None,
            transaction_kind="unknown",
            status=status,
            idempotency_key=str(evolution_transaction_id),
            plan_hash="",
            actor="autoskill-sidecar",
            cause={},
            source_evidence_ids=[],
            source_memory_ids=[],
            policy_snapshot={},
            metrics=metrics or {},
            rollback_of_transaction_id=None,
            started_at=now,
            committed_at=now if status in {"active", "committed"} else None,
            rolled_back_at=now if status == "rolled_back" else None,
        )

    async def record_transaction_item(
        self,
        *,
        evolution_transaction_id: UUID,
        item_kind: str,
        activation_state: str,
        item_id: UUID | None = None,
        relative_path: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        rollback_action: dict[str, Any] | None = None,
    ) -> EvolutionTransactionItemRecord:
        return EvolutionTransactionItemRecord(
            transaction_item_id=UUID("00000000-0000-0000-0000-000000000000"),
            evolution_transaction_id=evolution_transaction_id,
            item_kind=item_kind,
            item_id=item_id,
            relative_path=relative_path,
            before_hash=before_hash,
            after_hash=after_hash,
            activation_state=activation_state,
            rollback_action=rollback_action or {},
            created_at=datetime.now(UTC),
        )

    async def request_revocation(
        self,
        *,
        workspace_key: str,
        request_kind: str,
        root_object_type: str,
        root_object_id: UUID,
        traversal_summary: dict[str, Any] | None = None,
        created_by_job_id: UUID | None = None,
    ) -> RevocationRequestRecord:
        return RevocationRequestRecord(
            revocation_request_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            request_kind=request_kind,
            root_object_type=root_object_type,
            root_object_id=root_object_id,
            status="queued",
            traversal_summary=traversal_summary or {},
            created_by_job_id=created_by_job_id,
            created_at=datetime.now(UTC),
            completed_at=None,
        )


class AsyncpgGovernanceStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def start_transaction(
        self,
        *,
        workspace_key: str,
        transaction_kind: str,
        idempotency_key: str,
        plan_hash: str,
        actor: str = "autoskill-sidecar",
        cause: dict[str, Any] | None = None,
        source_evidence_ids: list[UUID] | None = None,
        source_memory_ids: list[UUID] | None = None,
        policy_snapshot: dict[str, Any] | None = None,
        rollback_of_transaction_id: UUID | None = None,
    ) -> TransactionStartResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.evolution_transactions (
                  evolution_transaction_id,
                  workspace_id,
                  action,
                  transaction_kind,
                  idempotency_key,
                  plan_hash,
                  actor,
                  status,
                  cause,
                  source_evidence_ids,
                  source_memory_ids,
                  policy_snapshot,
                  rollback_of_transaction_id
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $2, $3, $4, $5, 'planned', $6::jsonb,
                  $7::uuid[], $8::uuid[], $9::jsonb, $10
                )
                ON CONFLICT (workspace_id, idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING *, (xmax = 0) AS created
                """,
                workspace_id,
                transaction_kind,
                idempotency_key,
                plan_hash,
                actor,
                _json(cause or {}),
                source_evidence_ids or [],
                source_memory_ids or [],
                _json(policy_snapshot or {}),
                rollback_of_transaction_id,
            )
            return TransactionStartResult(
                transaction=EvolutionTransactionRecord.from_row(
                    {**dict(row), "workspace_key": workspace_key}
                ),
                created=bool(row["created"]),
            )

    async def update_transaction_status(
        self,
        *,
        evolution_transaction_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> EvolutionTransactionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE autoskill.evolution_transactions tx
                SET status = $2,
                    metrics = $3::jsonb,
                    committed_at = CASE
                      WHEN $2 IN ('active', 'committed') THEN COALESCE(committed_at, now())
                      ELSE committed_at
                    END,
                    rolled_back_at = CASE
                      WHEN $2 IN ('rolled_back', 'revoked') THEN COALESCE(rolled_back_at, now())
                      ELSE rolled_back_at
                    END
                FROM autoskill.workspaces w
                WHERE tx.workspace_id = w.workspace_id
                  AND tx.evolution_transaction_id = $1
                RETURNING tx.*, w.external_key AS workspace_key
                """,
                evolution_transaction_id,
                status,
                _json(metrics or {}),
            )
            if row is None:
                return None
            return EvolutionTransactionRecord.from_row(row)

    async def record_transaction_item(
        self,
        *,
        evolution_transaction_id: UUID,
        item_kind: str,
        activation_state: str,
        item_id: UUID | None = None,
        relative_path: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        rollback_action: dict[str, Any] | None = None,
    ) -> EvolutionTransactionItemRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.evolution_transaction_items (
                  transaction_item_id,
                  evolution_transaction_id,
                  item_kind,
                  item_id,
                  relative_path,
                  before_hash,
                  after_hash,
                  activation_state,
                  rollback_action
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                RETURNING *
                """,
                evolution_transaction_id,
                item_kind,
                item_id,
                relative_path,
                before_hash,
                after_hash,
                activation_state,
                _json(rollback_action or {}),
            )
            return EvolutionTransactionItemRecord.from_row(row)

    async def request_revocation(
        self,
        *,
        workspace_key: str,
        request_kind: str,
        root_object_type: str,
        root_object_id: UUID,
        traversal_summary: dict[str, Any] | None = None,
        created_by_job_id: UUID | None = None,
    ) -> RevocationRequestRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.revocation_requests (
                  revocation_request_id,
                  workspace_id,
                  request_kind,
                  root_object_type,
                  root_object_id,
                  status,
                  traversal_summary,
                  created_by_job_id
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, 'queued', $5::jsonb, $6)
                RETURNING *
                """,
                workspace_id,
                request_kind,
                root_object_type,
                root_object_id,
                _json(traversal_summary or {}),
                created_by_job_id,
            )
            return RevocationRequestRecord.from_row({**dict(row), "workspace_key": workspace_key})


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
