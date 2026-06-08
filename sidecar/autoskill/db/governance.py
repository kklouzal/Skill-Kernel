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
class ProvenanceEdgeRecord:
    provenance_edge_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_kind: str
    source_id: UUID
    derived_kind: str
    derived_id: UUID
    relation: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ProvenanceEdgeRecord:
        return cls(
            provenance_edge_id=row["provenance_edge_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            derived_kind=row["derived_kind"],
            derived_id=row["derived_id"],
            relation=row["relation"],
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "provenance_edge_id": str(self.provenance_edge_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_kind": self.source_kind,
            "source_id": str(self.source_id),
            "derived_kind": self.derived_kind,
            "derived_id": str(self.derived_id),
            "relation": self.relation,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ProvenanceEdgeCreateResult:
    edge: ProvenanceEdgeRecord
    created: bool

    def to_json(self) -> dict[str, Any]:
        return {"created": self.created, "edge": self.edge.to_json()}


@dataclass(frozen=True)
class RevocationTraversalRecord:
    workspace_id: UUID | None
    workspace_key: str | None
    root_object_type: str
    root_object_id: UUID
    impacted_objects: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool
    max_depth: int
    max_nodes: int

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "root_object_type": self.root_object_type,
            "root_object_id": str(self.root_object_id),
            "impacted_count": len(self.impacted_objects),
            "impacted_objects": self.impacted_objects,
            "edges": self.edges,
            "truncated": self.truncated,
            "max_depth": self.max_depth,
            "max_nodes": self.max_nodes,
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

    async def list_transaction_items(
        self,
        *,
        evolution_transaction_id: UUID,
    ) -> list[EvolutionTransactionItemRecord]:
        """Return transaction items newest-first for rollback planning."""

    async def list_transactions(
        self,
        *,
        workspace_key: str | None = None,
        transaction_kind_prefix: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionTransactionRecord]:
        """Return recent evolution transactions for content-safe read models."""

    async def get_transaction(
        self,
        *,
        workspace_key: str | None = None,
        evolution_transaction_id: UUID,
    ) -> EvolutionTransactionRecord | None:
        """Return one evolution transaction for a content-safe object microscope."""

    async def record_provenance_edge(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        source_id: UUID,
        derived_kind: str,
        derived_id: UUID,
        relation: str,
    ) -> ProvenanceEdgeCreateResult:
        """Record an idempotent provenance edge between source and derived objects."""

    async def preview_revocation_traversal(
        self,
        *,
        workspace_key: str,
        root_object_type: str,
        root_object_id: UUID,
        max_depth: int = 8,
        max_nodes: int = 500,
    ) -> RevocationTraversalRecord:
        """Return a bounded derived-object traversal for rollback/revocation planning."""

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

    async def get_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        revocation_request_id: UUID,
    ) -> RevocationRequestRecord | None:
        """Return one revocation request for a content-safe object microscope."""

    async def list_revocation_requests(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[RevocationRequestRecord]:
        """Return recent revocation requests for content-safe read models."""

    async def claim_next_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str = "rollback",
        root_object_type: str | None = None,
        worker_id: str | None = None,
    ) -> RevocationRequestRecord | None:
        """Claim one queued revocation request for deterministic worker processing."""

    async def complete_revocation_request(
        self,
        *,
        revocation_request_id: UUID,
        status: str,
        traversal_summary: dict[str, Any],
    ) -> RevocationRequestRecord | None:
        """Mark a claimed revocation request completed or failed."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Revoke governance-owned derived state for impacted objects."""

    async def expand_writer_item_impacts(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Map writer transaction items to revocable compiled artifact objects."""


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

    async def list_transaction_items(
        self,
        *,
        evolution_transaction_id: UUID,
    ) -> list[EvolutionTransactionItemRecord]:
        return []

    async def list_transactions(
        self,
        *,
        workspace_key: str | None = None,
        transaction_kind_prefix: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionTransactionRecord]:
        return []

    async def get_transaction(
        self,
        *,
        workspace_key: str | None = None,
        evolution_transaction_id: UUID,
    ) -> EvolutionTransactionRecord | None:
        return None

    async def record_provenance_edge(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        source_id: UUID,
        derived_kind: str,
        derived_id: UUID,
        relation: str,
    ) -> ProvenanceEdgeCreateResult:
        return ProvenanceEdgeCreateResult(
            edge=ProvenanceEdgeRecord(
                provenance_edge_id=UUID("00000000-0000-0000-0000-000000000000"),
                workspace_id=None,
                workspace_key=workspace_key,
                source_kind=source_kind,
                source_id=source_id,
                derived_kind=derived_kind,
                derived_id=derived_id,
                relation=relation,
                created_at=datetime.now(UTC),
            ),
            created=True,
        )

    async def preview_revocation_traversal(
        self,
        *,
        workspace_key: str,
        root_object_type: str,
        root_object_id: UUID,
        max_depth: int = 8,
        max_nodes: int = 500,
    ) -> RevocationTraversalRecord:
        return RevocationTraversalRecord(
            workspace_id=None,
            workspace_key=workspace_key,
            root_object_type=root_object_type,
            root_object_id=root_object_id,
            impacted_objects=[
                {
                    "object_type": root_object_type,
                    "object_id": str(root_object_id),
                    "depth": 0,
                }
            ],
            edges=[],
            truncated=False,
            max_depth=max_depth,
            max_nodes=max_nodes,
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

    async def get_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        revocation_request_id: UUID,
    ) -> RevocationRequestRecord | None:
        return None

    async def list_revocation_requests(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[RevocationRequestRecord]:
        return []

    async def claim_next_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str = "rollback",
        root_object_type: str | None = None,
        worker_id: str | None = None,
    ) -> RevocationRequestRecord | None:
        return None

    async def complete_revocation_request(
        self,
        *,
        revocation_request_id: UUID,
        status: str,
        traversal_summary: dict[str, Any],
    ) -> RevocationRequestRecord | None:
        return None

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def expand_writer_item_impacts(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return []


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

    async def list_transaction_items(
        self,
        *,
        evolution_transaction_id: UUID,
    ) -> list[EvolutionTransactionItemRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM autoskill.evolution_transaction_items
                WHERE evolution_transaction_id = $1
                ORDER BY created_at DESC, transaction_item_id DESC
                """,
                evolution_transaction_id,
            )
            return [EvolutionTransactionItemRecord.from_row(row) for row in rows]

    async def list_transactions(
        self,
        *,
        workspace_key: str | None = None,
        transaction_kind_prefix: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionTransactionRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tx.*, w.external_key AS workspace_key
                FROM autoskill.evolution_transactions tx
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR tx.transaction_kind LIKE $2 || '%')
                ORDER BY tx.started_at DESC, tx.evolution_transaction_id DESC
                LIMIT $3
                """,
                workspace_key,
                transaction_kind_prefix,
                max(1, min(limit, 250)),
            )
            return [EvolutionTransactionRecord.from_row(row) for row in rows]

    async def get_transaction(
        self,
        *,
        workspace_key: str | None = None,
        evolution_transaction_id: UUID,
    ) -> EvolutionTransactionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tx.*, w.external_key AS workspace_key
                FROM autoskill.evolution_transactions tx
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE tx.evolution_transaction_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                evolution_transaction_id,
                workspace_key,
            )
            if row is None:
                return None
            return EvolutionTransactionRecord.from_row(row)

    async def record_provenance_edge(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        source_id: UUID,
        derived_kind: str,
        derived_id: UUID,
        relation: str,
    ) -> ProvenanceEdgeCreateResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                WITH inserted AS (
                  INSERT INTO autoskill.provenance_edges (
                    provenance_edge_id,
                    workspace_id,
                    source_kind,
                    source_id,
                    derived_kind,
                    derived_id,
                    relation
                  )
                  SELECT gen_random_uuid(), $1, $2, $3, $4, $5, $6
                  WHERE NOT EXISTS (
                    SELECT 1
                    FROM autoskill.provenance_edges
                    WHERE workspace_id = $1
                      AND source_kind = $2
                      AND source_id = $3
                      AND derived_kind = $4
                      AND derived_id = $5
                      AND relation = $6
                  )
                  RETURNING *, true AS created
                )
                SELECT *, $7::text AS workspace_key
                FROM inserted
                UNION ALL
                SELECT provenance_edges.*, false AS created, $7::text AS workspace_key
                FROM autoskill.provenance_edges
                WHERE workspace_id = $1
                  AND source_kind = $2
                  AND source_id = $3
                  AND derived_kind = $4
                  AND derived_id = $5
                  AND relation = $6
                LIMIT 1
                """,
                workspace_id,
                source_kind,
                source_id,
                derived_kind,
                derived_id,
                relation,
                workspace_key,
            )
            return ProvenanceEdgeCreateResult(
                edge=ProvenanceEdgeRecord.from_row(row),
                created=bool(row["created"]),
            )

    async def preview_revocation_traversal(
        self,
        *,
        workspace_key: str,
        root_object_type: str,
        root_object_id: UUID,
        max_depth: int = 8,
        max_nodes: int = 500,
    ) -> RevocationTraversalRecord:
        max_depth = max(0, min(max_depth, 32))
        max_nodes = max(1, min(max_nodes, 5_000))
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                WITH RECURSIVE traversal AS (
                  SELECT
                    0 AS depth,
                    $2::text AS object_type,
                    $3::uuid AS object_id,
                    ARRAY[$2::text || ':' || $3::text] AS path
                  UNION ALL
                  SELECT
                    traversal.depth + 1,
                    edge.derived_kind,
                    edge.derived_id,
                    traversal.path || (edge.derived_kind || ':' || edge.derived_id::text)
                  FROM traversal
                  JOIN autoskill.provenance_edges edge
                    ON edge.workspace_id = $1
                   AND edge.source_kind = traversal.object_type
                   AND edge.source_id = traversal.object_id
                  WHERE traversal.depth < $4
                    AND NOT edge.derived_kind || ':' || edge.derived_id::text = ANY(traversal.path)
                )
                SELECT depth, object_type, object_id
                FROM traversal
                ORDER BY depth, object_type, object_id
                LIMIT $5 + 1
                """,
                workspace_id,
                root_object_type,
                root_object_id,
                max_depth,
                max_nodes,
            )
            edge_rows = await conn.fetch(
                """
                WITH RECURSIVE traversal AS (
                  SELECT
                    0 AS depth,
                    $2::text AS object_type,
                    $3::uuid AS object_id,
                    ARRAY[$2::text || ':' || $3::text] AS path
                  UNION ALL
                  SELECT
                    traversal.depth + 1,
                    edge.derived_kind,
                    edge.derived_id,
                    traversal.path || (edge.derived_kind || ':' || edge.derived_id::text)
                  FROM traversal
                  JOIN autoskill.provenance_edges edge
                    ON edge.workspace_id = $1
                   AND edge.source_kind = traversal.object_type
                   AND edge.source_id = traversal.object_id
                  WHERE traversal.depth < $4
                    AND NOT edge.derived_kind || ':' || edge.derived_id::text = ANY(traversal.path)
                )
                SELECT DISTINCT
                  edge.provenance_edge_id,
                  edge.source_kind,
                  edge.source_id,
                  edge.derived_kind,
                  edge.derived_id,
                  edge.relation
                FROM traversal
                JOIN autoskill.provenance_edges edge
                  ON edge.workspace_id = $1
                 AND edge.source_kind = traversal.object_type
                 AND edge.source_id = traversal.object_id
                ORDER BY edge.source_kind, edge.derived_kind, edge.provenance_edge_id
                LIMIT $5
                """,
                workspace_id,
                root_object_type,
                root_object_id,
                max_depth,
                max_nodes,
            )
        truncated = len(rows) > max_nodes
        impacted_rows = rows[:max_nodes]
        return RevocationTraversalRecord(
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            root_object_type=root_object_type,
            root_object_id=root_object_id,
            impacted_objects=[
                {
                    "object_type": row["object_type"],
                    "object_id": str(row["object_id"]),
                    "depth": row["depth"],
                }
                for row in impacted_rows
            ],
            edges=[
                {
                    "provenance_edge_id": str(row["provenance_edge_id"]),
                    "source_kind": row["source_kind"],
                    "source_id": str(row["source_id"]),
                    "derived_kind": row["derived_kind"],
                    "derived_id": str(row["derived_id"]),
                    "relation": row["relation"],
                }
                for row in edge_rows
            ],
            truncated=truncated,
            max_depth=max_depth,
            max_nodes=max_nodes,
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

    async def get_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        revocation_request_id: UUID,
    ) -> RevocationRequestRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT rr.*, w.external_key AS workspace_key
                FROM autoskill.revocation_requests rr
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE rr.revocation_request_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                revocation_request_id,
                workspace_key,
            )
            if row is None:
                return None
            return RevocationRequestRecord.from_row(row)

    async def list_revocation_requests(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[RevocationRequestRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rr.*, w.external_key AS workspace_key
                FROM autoskill.revocation_requests rr
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR rr.request_kind = $2)
                  AND ($3::text IS NULL OR rr.status = $3)
                ORDER BY rr.created_at DESC, rr.revocation_request_id DESC
                LIMIT $4
                """,
                workspace_key,
                request_kind,
                status,
                max(1, min(limit, 250)),
            )
            return [RevocationRequestRecord.from_row(row) for row in rows]

    async def claim_next_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        request_kind: str = "rollback",
        root_object_type: str | None = None,
        worker_id: str | None = None,
    ) -> RevocationRequestRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                WITH candidate AS (
                  SELECT rr.revocation_request_id
                  FROM autoskill.revocation_requests rr
                  JOIN autoskill.workspaces w ON w.workspace_id = rr.workspace_id
                  WHERE rr.status = 'queued'
                    AND rr.request_kind = $2
                    AND ($1::text IS NULL OR w.external_key = $1)
                    AND ($3::text IS NULL OR rr.root_object_type = $3)
                  ORDER BY rr.created_at ASC, rr.revocation_request_id ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                UPDATE autoskill.revocation_requests rr
                SET status = 'processing',
                    traversal_summary = rr.traversal_summary || $4::jsonb
                FROM candidate, autoskill.workspaces w
                WHERE rr.revocation_request_id = candidate.revocation_request_id
                  AND w.workspace_id = rr.workspace_id
                RETURNING rr.*, w.external_key AS workspace_key
                """,
                workspace_key,
                request_kind,
                root_object_type,
                _json({"claimed_by": worker_id} if worker_id else {}),
            )
            return RevocationRequestRecord.from_row(row) if row else None

    async def expand_writer_item_impacts(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        object_keys = _object_keys(objects)
        transaction_item_ids = [
            object_id
            for object_type, object_id in object_keys
            if object_type == "transaction_item"
        ]
        if not transaction_item_ids:
            return []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                  item.transaction_item_id,
                  item.item_id
                FROM autoskill.evolution_transaction_items item
                JOIN autoskill.evolution_transactions tx
                  ON tx.evolution_transaction_id = item.evolution_transaction_id
                JOIN autoskill.workspaces w
                  ON w.workspace_id = tx.workspace_id
                WHERE w.external_key = $1
                  AND item.transaction_item_id = ANY($2::uuid[])
                  AND item.item_kind IN (
                    'compiled_skill_file',
                    'support_artifact',
                    'artifact_manifest',
                    'archive_snapshot'
                  )
                ORDER BY item.transaction_item_id
                """,
                workspace_key,
                transaction_item_ids,
            )
        expanded: list[dict[str, str]] = []
        for row in rows:
            item_id = row["item_id"]
            if item_id is not None:
                expanded.append({"object_type": "skill_version", "object_id": str(item_id)})
        return _objects_to_json(_object_keys(expanded))

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        object_keys = _object_keys(objects)
        if not object_keys:
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            result = await conn.fetchval(
                """
                WITH targets AS (
                  SELECT *
                  FROM unnest($2::text[], $3::uuid[]) AS target(object_type, object_id)
                ),
                skill_targets AS (
                  SELECT object_id AS skill_id
                  FROM targets
                  WHERE object_type = 'skill'
                  UNION
                  SELECT sv.skill_id
                  FROM autoskill.skill_versions sv
                  JOIN autoskill.skills s
                    ON s.skill_id = sv.skill_id
                   AND s.active_version_id = sv.skill_version_id
                  JOIN targets t
                    ON t.object_type = 'skill_version'
                   AND t.object_id = sv.skill_version_id
                  WHERE s.workspace_id = $1
                ),
                revoked_edges AS (
                  UPDATE autoskill.skill_edges edge
                  SET revoked_at = COALESCE(edge.revoked_at, now()),
                      revocation_metadata = edge.revocation_metadata || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked'
                      )
                  WHERE edge.workspace_id = $1
                    AND edge.revoked_at IS NULL
                    AND (
                      edge.edge_id IN (
                        SELECT object_id FROM targets WHERE object_type = 'skill_edge'
                      )
                      OR edge.from_skill_id IN (SELECT skill_id FROM skill_targets)
                      OR edge.to_skill_id IN (SELECT skill_id FROM skill_targets)
                    )
                  RETURNING edge.edge_id
                ),
                revoked_skills AS (
                  UPDATE autoskill.skills skill
                  SET lifecycle_state = 'revoked',
                      freeze_reason = COALESCE(freeze_reason, 'derived object revoked'),
                      updated_at = now()
                  WHERE skill.workspace_id = $1
                    AND skill.skill_id IN (SELECT skill_id FROM skill_targets)
                    AND skill.lifecycle_state <> 'revoked'
                  RETURNING skill.skill_id
                ),
                revoked_maturity AS (
                  UPDATE autoskill.evidence_maturity maturity
                  SET maturity = 'revoked',
                      basis = maturity.basis || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked',
                        'previous_maturity', maturity.maturity
                      ),
                      updated_at = now()
                  WHERE maturity.workspace_id = $1
                    AND maturity.maturity <> 'revoked'
                    AND (
                      (maturity.object_type, maturity.object_id) IN (
                        SELECT object_type, object_id FROM targets
                      )
                      OR (
                        maturity.object_type = 'skill'
                        AND maturity.object_id IN (SELECT skill_id FROM skill_targets)
                      )
                      OR (
                        maturity.object_type = 'skill_version'
                        AND maturity.object_id IN (
                          SELECT object_id
                          FROM targets
                          WHERE object_type = 'skill_version'
                        )
                      )
                    )
                  RETURNING maturity.evidence_maturity_id
                )
                SELECT
                  (SELECT count(*) FROM revoked_edges)
                  + (SELECT count(*) FROM revoked_skills)
                  + (SELECT count(*) FROM revoked_maturity) AS invalidated
                """,
                workspace_id,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
        return int(result or 0)

    async def complete_revocation_request(
        self,
        *,
        revocation_request_id: UUID,
        status: str,
        traversal_summary: dict[str, Any],
    ) -> RevocationRequestRecord | None:
        if status not in {"completed", "failed"}:
            raise ValueError("revocation status must be completed or failed")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE autoskill.revocation_requests rr
                SET status = $2,
                    traversal_summary = $3::jsonb,
                    completed_at = now()
                FROM autoskill.workspaces w
                WHERE rr.workspace_id = w.workspace_id
                  AND rr.revocation_request_id = $1
                RETURNING rr.*, w.external_key AS workspace_key
                """,
                revocation_request_id,
                status,
                _json(traversal_summary),
            )
            return RevocationRequestRecord.from_row(row) if row else None


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


def _object_keys(objects: list[dict[str, str]]) -> list[tuple[str, UUID]]:
    keys: list[tuple[str, UUID]] = []
    for item in objects:
        object_type = str(item.get("object_type") or "")
        object_id = item.get("object_id")
        if not object_type or object_id is None:
            continue
        try:
            keys.append((object_type, UUID(str(object_id))))
        except ValueError:
            continue
    return keys


def _objects_to_json(objects: list[tuple[str, UUID]]) -> list[dict[str, str]]:
    seen: set[tuple[str, UUID]] = set()
    output: list[dict[str, str]] = []
    for object_type, object_id in objects:
        key = (object_type, object_id)
        if key in seen:
            continue
        seen.add(key)
        output.append({"object_type": object_type, "object_id": str(object_id)})
    return output
