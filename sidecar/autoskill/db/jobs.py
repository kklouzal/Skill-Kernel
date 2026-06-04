from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

JobStatus = Literal["queued", "leased", "succeeded", "failed"]


@dataclass(frozen=True)
class JobRecord:
    job_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    trace_id: UUID | None
    span_id: UUID | None
    parent_span_id: UUID | None
    job_kind: str
    status: str
    idempotency_key: str
    payload: dict[str, Any]
    priority: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    attempts: int
    max_attempts: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> JobRecord:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            job_id=row["job_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            trace_id=_row_get(row, "trace_id"),
            span_id=_row_get(row, "span_id"),
            parent_span_id=_row_get(row, "parent_span_id"),
            job_kind=row["job_kind"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            payload=payload,
            priority=row["priority"],
            lease_owner=_row_get(row, "lease_owner"),
            lease_expires_at=_row_get(row, "lease_expires_at"),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            available_at=row["available_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "job_id": str(self.job_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "trace_id": str(self.trace_id) if self.trace_id else None,
            "span_id": str(self.span_id) if self.span_id else None,
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "job_kind": self.job_kind,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "priority": self.priority,
            "lease_owner": self.lease_owner,
            "lease_expires_at": _iso_or_none(self.lease_expires_at),
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "available_at": self.available_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class JobEnqueueResult:
    job: JobRecord
    created: bool


@dataclass(frozen=True)
class JobQueueSummary:
    counts: dict[str, int]
    by_kind: dict[str, dict[str, int]]


@dataclass(frozen=True)
class WorkerHeartbeatRecord:
    worker_id: str
    pool: str
    concurrency: int
    status: str
    current_job_id: UUID | None
    summary: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> WorkerHeartbeatRecord:
        summary = row["summary"]
        if isinstance(summary, str):
            summary = json.loads(summary)
        return cls(
            worker_id=row["worker_id"],
            pool=row["pool"],
            concurrency=row["concurrency"],
            status=row["status"],
            current_job_id=_row_get(row, "current_job_id"),
            summary=summary,
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "pool": self.pool,
            "concurrency": self.concurrency,
            "status": self.status,
            "current_job_id": str(self.current_job_id) if self.current_job_id else None,
            "summary": self.summary,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }


class JobStore(Protocol):
    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> JobEnqueueResult:
        """Create or return an idempotent job."""

    async def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        job_kinds: Sequence[str] | None = None,
    ) -> JobRecord | None:
        """Lease the next runnable job."""

    async def complete_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        status: Literal["succeeded", "failed"],
        error: str | None = None,
    ) -> JobRecord | None:
        """Finish a leased job."""

    async def renew_job_lease(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> JobRecord | None:
        """Extend a currently held lease."""

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        """List recent jobs."""

    async def summary(self, *, workspace_key: str | None = None) -> JobQueueSummary:
        """Return queue counts by status."""

    async def record_worker_heartbeat(
        self,
        *,
        worker_id: str,
        pool: str,
        concurrency: int,
        status: str,
        current_job_id: UUID | None = None,
        summary: dict[str, Any] | None = None,
    ) -> WorkerHeartbeatRecord:
        """Upsert one persistent worker heartbeat."""

    async def list_worker_heartbeats(
        self,
        *,
        active_within_seconds: int = 600,
        limit: int = 50,
    ) -> list[WorkerHeartbeatRecord]:
        """List recently observed workers."""


class NullJobStore:
    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> JobEnqueueResult:
        now = datetime.now(UTC)
        job = JobRecord(
            job_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            trace_id=trace_id or uuid4(),
            span_id=span_id or uuid4(),
            parent_span_id=parent_span_id,
            job_kind=job_kind,
            status="queued",
            idempotency_key=idempotency_key,
            payload=payload or {},
            priority=priority,
            lease_owner=None,
            lease_expires_at=None,
            attempts=0,
            max_attempts=max_attempts,
            available_at=available_at or now,
            created_at=now,
            updated_at=now,
        )
        return JobEnqueueResult(job=job, created=True)

    async def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        job_kinds: Sequence[str] | None = None,
    ) -> JobRecord | None:
        return None

    async def complete_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        status: Literal["succeeded", "failed"],
        error: str | None = None,
    ) -> JobRecord | None:
        return None

    async def renew_job_lease(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> JobRecord | None:
        return None

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        return []

    async def summary(self, *, workspace_key: str | None = None) -> JobQueueSummary:
        return JobQueueSummary(counts={}, by_kind={})

    async def record_worker_heartbeat(
        self,
        *,
        worker_id: str,
        pool: str,
        concurrency: int,
        status: str,
        current_job_id: UUID | None = None,
        summary: dict[str, Any] | None = None,
    ) -> WorkerHeartbeatRecord:
        now = datetime.now(UTC)
        return WorkerHeartbeatRecord(
            worker_id=worker_id,
            pool=pool,
            concurrency=max(1, concurrency),
            status=status,
            current_job_id=current_job_id,
            summary=summary or {},
            first_seen_at=now,
            last_seen_at=now,
        )

    async def list_worker_heartbeats(
        self,
        *,
        active_within_seconds: int = 600,
        limit: int = 50,
    ) -> list[WorkerHeartbeatRecord]:
        return []


class AsyncpgJobStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> JobEnqueueResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.jobs (
                  job_id,
                  workspace_id,
                  trace_id,
                  span_id,
                  parent_span_id,
                  job_kind,
                  idempotency_key,
                  payload,
                  priority,
                  max_attempts,
                  available_at
                )
                VALUES (
                  gen_random_uuid(), $1, COALESCE($2, gen_random_uuid()),
                  COALESCE($3, gen_random_uuid()), $4, $5, $6, $7::jsonb, $8, $9,
                  COALESCE($10, now())
                )
                ON CONFLICT (workspace_id, idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING *, (xmax = 0) AS created
                """,
                workspace_id,
                trace_id,
                span_id,
                parent_span_id,
                job_kind,
                idempotency_key,
                _json(payload or {}),
                priority,
                max_attempts,
                available_at,
            )
            return JobEnqueueResult(
                job=JobRecord.from_row({**dict(row), "workspace_key": workspace_key}),
                created=bool(row["created"]),
            )

    async def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        job_kinds: Sequence[str] | None = None,
    ) -> JobRecord | None:
        pool = await self._get_pool()
        lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        async with pool.acquire() as conn, conn.transaction():
            await _recover_expired_leases(conn)
            row = await conn.fetchrow(
                """
                WITH candidate AS (
                  SELECT job_id
                  FROM autoskill.jobs
                  WHERE status = 'queued'
                    AND available_at <= now()
                    AND ($1::text[] IS NULL OR job_kind = ANY($1::text[]))
                  ORDER BY priority ASC, available_at ASC, created_at ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                UPDATE autoskill.jobs j
                SET status = 'leased',
                    lease_owner = $2,
                    lease_expires_at = $3,
                    attempts = attempts + 1,
                    updated_at = now()
                FROM candidate
                WHERE j.job_id = candidate.job_id
                RETURNING j.*
                """,
                list(job_kinds) if job_kinds else None,
                worker_id,
                lease_expires_at,
            )
            if row is None:
                return None
            await conn.execute(
                """
                INSERT INTO autoskill.job_attempts (
                  job_attempt_id, job_id, attempt_number, worker_id, status
                )
                VALUES (gen_random_uuid(), $1, $2, $3, 'leased')
                """,
                row["job_id"],
                row["attempts"],
                worker_id,
            )
            workspace_key = await _workspace_key(conn, row["workspace_id"])
            return JobRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def complete_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        status: Literal["succeeded", "failed"],
        error: str | None = None,
    ) -> JobRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE autoskill.jobs
                SET status = CASE
                      WHEN $3 = 'succeeded' THEN 'succeeded'
                      WHEN attempts < max_attempts THEN 'queued'
                      ELSE 'failed'
                    END,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    available_at = CASE
                      WHEN $3 = 'failed' AND attempts < max_attempts
                        THEN now() + make_interval(
                          secs => LEAST(3600, (30 * POWER(2, GREATEST(attempts - 1, 0)))::int)
                        )
                      ELSE available_at
                    END,
                    updated_at = now()
                WHERE job_id = $1
                  AND lease_owner = $2
                  AND status = 'leased'
                RETURNING *
                """,
                job_id,
                worker_id,
                status,
            )
            if row is None:
                return None
            await conn.execute(
                """
                UPDATE autoskill.job_attempts
                SET finished_at = now(),
                    status = $3,
                    error = $4
                WHERE job_id = $1
                  AND worker_id = $2
                  AND finished_at IS NULL
                """,
                job_id,
                worker_id,
                status,
                error,
            )
            workspace_key = await _workspace_key(conn, row["workspace_id"])
            return JobRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def renew_job_lease(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> JobRecord | None:
        pool = await self._get_pool()
        lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE autoskill.jobs
                SET lease_expires_at = $3,
                    updated_at = now()
                WHERE job_id = $1
                  AND lease_owner = $2
                  AND status = 'leased'
                  AND lease_expires_at >= now()
                RETURNING *
                """,
                job_id,
                worker_id,
                lease_expires_at,
            )
            if row is None:
                return None
            await conn.execute(
                """
                UPDATE autoskill.job_attempts
                SET status = 'leased'
                WHERE job_id = $1
                  AND worker_id = $2
                  AND finished_at IS NULL
                """,
                job_id,
                worker_id,
            )
            workspace_key = await _workspace_key(conn, row["workspace_id"])
            return JobRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT j.*, w.external_key AS workspace_key
                FROM autoskill.jobs j
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR j.status = $1)
                ORDER BY j.created_at DESC
                LIMIT $2
                """,
                status,
                limit,
            )
            return [JobRecord.from_row(row) for row in rows]

    async def summary(self, *, workspace_key: str | None = None) -> JobQueueSummary:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            status_rows = await conn.fetch(
                """
                SELECT status, count(*)::int AS count
                FROM autoskill.jobs j
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND NOT (
                    j.status = 'failed'
                    AND EXISTS (
                      SELECT 1
                      FROM autoskill.jobs newer
                      WHERE newer.workspace_id = j.workspace_id
                        AND newer.job_kind = j.job_kind
                        AND newer.status = 'succeeded'
                        AND newer.updated_at > j.updated_at
                    )
                  )
                GROUP BY status
                """,
                workspace_key,
            )
            kind_rows = await conn.fetch(
                """
                SELECT job_kind, status, count(*)::int AS count
                FROM autoskill.jobs j
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND NOT (
                    j.status = 'failed'
                    AND EXISTS (
                      SELECT 1
                      FROM autoskill.jobs newer
                      WHERE newer.workspace_id = j.workspace_id
                        AND newer.job_kind = j.job_kind
                        AND newer.status = 'succeeded'
                        AND newer.updated_at > j.updated_at
                    )
                  )
                GROUP BY job_kind, status
                ORDER BY job_kind, status
                """,
                workspace_key,
            )
            by_kind: dict[str, dict[str, int]] = {}
            for row in kind_rows:
                by_kind.setdefault(row["job_kind"], {})[row["status"]] = row["count"]
            return JobQueueSummary(
                counts={row["status"]: row["count"] for row in status_rows},
                by_kind=by_kind,
            )

    async def record_worker_heartbeat(
        self,
        *,
        worker_id: str,
        pool: str,
        concurrency: int,
        status: str,
        current_job_id: UUID | None = None,
        summary: dict[str, Any] | None = None,
    ) -> WorkerHeartbeatRecord:
        db_pool = await self._get_pool()
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.worker_heartbeats (
                  worker_id,
                  pool,
                  concurrency,
                  status,
                  current_job_id,
                  summary
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (worker_id) DO UPDATE
                SET pool = EXCLUDED.pool,
                    concurrency = EXCLUDED.concurrency,
                    status = EXCLUDED.status,
                    current_job_id = EXCLUDED.current_job_id,
                    summary = EXCLUDED.summary,
                    last_seen_at = now()
                RETURNING *
                """,
                worker_id,
                pool,
                max(1, concurrency),
                status,
                current_job_id,
                _json(summary or {}),
            )
            return WorkerHeartbeatRecord.from_row(row)

    async def list_worker_heartbeats(
        self,
        *,
        active_within_seconds: int = 600,
        limit: int = 50,
    ) -> list[WorkerHeartbeatRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM autoskill.worker_heartbeats
                WHERE last_seen_at >= now() - make_interval(secs => $1)
                ORDER BY last_seen_at DESC, worker_id ASC
                LIMIT $2
                """,
                max(1, active_within_seconds),
                max(1, min(limit, 500)),
            )
            return [WorkerHeartbeatRecord.from_row(row) for row in rows]


async def _recover_expired_leases(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        UPDATE autoskill.jobs
        SET status = 'queued',
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = now()
        WHERE status = 'leased'
          AND lease_expires_at < now()
          AND attempts < max_attempts
        """
    )
    await conn.execute(
        """
        UPDATE autoskill.jobs
        SET status = 'failed',
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = now()
        WHERE status = 'leased'
          AND lease_expires_at < now()
          AND attempts >= max_attempts
        """
    )


async def _workspace_key(conn: asyncpg.Connection, workspace_id: UUID) -> str:
    return await conn.fetchval(
        "SELECT external_key FROM autoskill.workspaces WHERE workspace_id = $1",
        workspace_id,
    )


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
