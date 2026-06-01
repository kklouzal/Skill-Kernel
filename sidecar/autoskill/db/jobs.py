from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

JobStatus = Literal["queued", "leased", "succeeded", "failed"]


@dataclass(frozen=True)
class JobRecord:
    job_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
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


class JobStore(Protocol):
    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
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

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        """List recent jobs."""

    async def summary(self) -> JobQueueSummary:
        """Return queue counts by status."""


class NullJobStore:
    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> JobEnqueueResult:
        now = datetime.now(UTC)
        job = JobRecord(
            job_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
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

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        return []

    async def summary(self) -> JobQueueSummary:
        return JobQueueSummary(counts={})


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
                  job_kind,
                  idempotency_key,
                  payload,
                  priority,
                  max_attempts,
                  available_at
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4::jsonb, $5, $6, COALESCE($7, now())
                )
                ON CONFLICT (workspace_id, idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING *, (xmax = 0) AS created
                """,
                workspace_id,
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

    async def summary(self) -> JobQueueSummary:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, count(*)::int AS count
                FROM autoskill.jobs
                GROUP BY status
                """
            )
            return JobQueueSummary(counts={row["status"]: row["count"] for row in rows})


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
