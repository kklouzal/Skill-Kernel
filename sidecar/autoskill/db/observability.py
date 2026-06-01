from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

TraceStatus = Literal["running", "ok", "error", "timeout", "denied", "quarantined", "rolled_back"]


@dataclass(frozen=True)
class TraceSpanRecord:
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None
    workspace_id: UUID | None
    workspace_key: str | None
    operation_name: str
    operation_kind: str
    status: str
    safe_attributes: dict[str, Any]
    object_refs: list[dict[str, Any]]
    started_at: datetime
    ended_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> TraceSpanRecord:
        return cls(
            trace_id=row["trace_id"],
            span_id=row["span_id"],
            parent_span_id=_row_get(row, "parent_span_id"),
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            operation_name=row["operation_name"],
            operation_kind=row["operation_kind"],
            status=row["status"],
            safe_attributes=_json_dict(row["safe_attributes"]),
            object_refs=_json_list(row["object_refs"]),
            started_at=row["started_at"],
            ended_at=_row_get(row, "ended_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "trace_id": str(self.trace_id),
            "span_id": str(self.span_id),
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "operation_name": self.operation_name,
            "operation_kind": self.operation_kind,
            "status": self.status,
            "safe_attributes": self.safe_attributes,
            "object_refs": self.object_refs,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class ObservabilityStore(Protocol):
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        """Start a content-safe trace span."""

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        """Close a trace span."""

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        """Record a trace span link."""

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        """Return spans for one trace."""


class NullObservabilityStore:
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        from uuid import uuid4

        now = datetime.now(UTC)
        return TraceSpanRecord(
            trace_id=trace_id or uuid4(),
            span_id=uuid4(),
            parent_span_id=parent_span_id,
            workspace_id=None,
            workspace_key=workspace_key,
            operation_name=operation_name,
            operation_kind=operation_kind,
            status="running",
            safe_attributes=safe_attributes or {},
            object_refs=object_refs or [],
            started_at=now,
            ended_at=None,
        )

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        return None

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        return True

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        return []


class AsyncpgObservabilityStore(AsyncpgPoolOwner):
    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.trace_spans (
                  trace_id,
                  span_id,
                  parent_span_id,
                  workspace_id,
                  operation_name,
                  operation_kind,
                  status,
                  safe_attributes,
                  object_refs
                )
                VALUES (
                  COALESCE($1, gen_random_uuid()),
                  gen_random_uuid(),
                  (
                    SELECT span_id
                    FROM autoskill.trace_spans
                    WHERE span_id = $2
                  ),
                  $3,
                  $4,
                  $5,
                  'running',
                  $6::jsonb,
                  $7::jsonb
                )
                RETURNING *, $8::text AS workspace_key
                """,
                trace_id,
                parent_span_id,
                workspace_id,
                operation_name,
                operation_kind,
                _json(safe_attributes or {}),
                _json(object_refs or []),
                workspace_key,
            )
        return TraceSpanRecord.from_row(row)

    async def finish_span(
        self,
        *,
        span_id: UUID,
        status: TraceStatus = "ok",
        safe_attributes: dict[str, Any] | None = None,
        object_refs: list[dict[str, Any]] | None = None,
    ) -> TraceSpanRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE autoskill.trace_spans ts
                SET ended_at = now(),
                    status = $2,
                    safe_attributes = ts.safe_attributes || $3::jsonb,
                    object_refs = ts.object_refs || $4::jsonb
                FROM autoskill.workspaces w
                WHERE ts.span_id = $1
                  AND w.workspace_id = ts.workspace_id
                RETURNING ts.*, w.external_key AS workspace_key
                """,
                span_id,
                status,
                _json(safe_attributes or {}),
                _json(object_refs or []),
            )
        return TraceSpanRecord.from_row(row) if row else None

    async def link_spans(
        self,
        *,
        from_span_id: UUID,
        to_span_id: UUID,
        link_type: str,
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO autoskill.trace_span_links (from_span_id, to_span_id, link_type)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                from_span_id,
                to_span_id,
                link_type,
            )
        return result.endswith("1")

    async def list_trace(
        self,
        *,
        workspace_key: str,
        trace_id: UUID,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT ts.*, $3::text AS workspace_key
                FROM autoskill.trace_spans ts
                WHERE ts.workspace_id = $1
                  AND ts.trace_id = $2
                ORDER BY ts.started_at ASC
                LIMIT $4
                """,
                workspace_id,
                trace_id,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [TraceSpanRecord.from_row(row) for row in rows]


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        return _json_list(parsed)
    return []


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
