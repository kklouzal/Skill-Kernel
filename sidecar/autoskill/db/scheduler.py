from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.jobs import JobRecord
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ScheduleRecord:
    schedule_id: UUID
    workspace_key: str | None
    name: str
    job_kind: str
    enabled: bool
    interval_seconds: int
    next_run_at: datetime
    payload: dict[str, Any]

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ScheduleRecord:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            schedule_id=row["schedule_id"],
            workspace_key=_row_get(row, "workspace_key"),
            name=row["name"],
            job_kind=row["job_kind"],
            enabled=row["enabled"],
            interval_seconds=row["interval_seconds"],
            next_run_at=row["next_run_at"],
            payload=payload,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "schedule_id": str(self.schedule_id),
            "workspace_key": self.workspace_key,
            "name": self.name,
            "job_kind": self.job_kind,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "next_run_at": self.next_run_at.isoformat(),
            "payload": self.payload,
        }


@dataclass(frozen=True)
class ScheduleUpsertResult:
    schedule: ScheduleRecord
    created: bool


@dataclass(frozen=True)
class SchedulerTickResult:
    due: int
    enqueued: int
    jobs: list[JobRecord]


class SchedulerStore(Protocol):
    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ScheduleUpsertResult:
        """Create or update a schedule."""

    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        """Enqueue jobs for due schedules."""

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        """List schedules."""


class NullSchedulerStore:
    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ScheduleUpsertResult:
        schedule = ScheduleRecord(
            schedule_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_key=workspace_key,
            name=name,
            job_kind=job_kind,
            enabled=enabled,
            interval_seconds=interval_seconds,
            next_run_at=next_run_at,
            payload=payload or {},
        )
        return ScheduleUpsertResult(schedule=schedule, created=True)

    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        return SchedulerTickResult(due=0, enqueued=0, jobs=[])

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        return []


class AsyncpgSchedulerStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ScheduleUpsertResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.schedules (
                  schedule_id,
                  workspace_id,
                  name,
                  job_kind,
                  enabled,
                  interval_seconds,
                  next_run_at,
                  payload
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (workspace_id, name) DO UPDATE
                SET job_kind = EXCLUDED.job_kind,
                    enabled = EXCLUDED.enabled,
                    interval_seconds = EXCLUDED.interval_seconds,
                    next_run_at = EXCLUDED.next_run_at,
                    payload = EXCLUDED.payload
                RETURNING *, (xmax = 0) AS created
                """,
                workspace_id,
                name,
                job_kind,
                enabled,
                interval_seconds,
                next_run_at,
                _json(payload or {}),
            )
            return ScheduleUpsertResult(
                schedule=ScheduleRecord.from_row({**dict(row), "workspace_key": workspace_key}),
                created=bool(row["created"]),
            )

    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        pool = await self._get_pool()
        jobs: list[JobRecord] = []
        due = 0
        async with pool.acquire() as conn, conn.transaction():
            schedules = await conn.fetch(
                """
                SELECT s.*, w.external_key AS workspace_key
                FROM autoskill.schedules s
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE s.enabled = true
                  AND s.next_run_at <= now()
                ORDER BY s.next_run_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT $1
                """,
                limit,
            )
            due = len(schedules)
            now = datetime.now(UTC)
            for schedule in schedules:
                idempotency_key = _schedule_job_key(schedule)
                job = await _enqueue_scheduled_job(conn, schedule, idempotency_key)
                if job is not None:
                    jobs.append(job)
                await conn.execute(
                    """
                    UPDATE autoskill.schedules
                    SET next_run_at = $2
                    WHERE schedule_id = $1
                    """,
                    schedule["schedule_id"],
                    _next_run_after(schedule["next_run_at"], schedule["interval_seconds"], now),
                )

        return SchedulerTickResult(due=due, enqueued=len(jobs), jobs=jobs)

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.*, w.external_key AS workspace_key
                FROM autoskill.schedules s
                JOIN autoskill.workspaces w USING (workspace_id)
                ORDER BY s.next_run_at ASC
                LIMIT $1
                """,
                limit,
            )
            return [ScheduleRecord.from_row(row) for row in rows]


async def _enqueue_scheduled_job(
    conn: asyncpg.Connection,
    schedule: asyncpg.Record,
    idempotency_key: str,
) -> JobRecord | None:
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.jobs (
          job_id,
          workspace_id,
          job_kind,
          idempotency_key,
          payload
        )
        VALUES (gen_random_uuid(), $1, $2, $3, $4::jsonb)
        ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
        RETURNING *
        """,
        schedule["workspace_id"],
        schedule["job_kind"],
        idempotency_key,
        _json(schedule["payload"]),
    )
    if row is None:
        return None
    return JobRecord.from_row({**dict(row), "workspace_key": schedule["workspace_key"]})


def _schedule_job_key(schedule: asyncpg.Record) -> str:
    due_at = schedule["next_run_at"].astimezone(UTC).isoformat()
    return f"schedule:{schedule['schedule_id']}:{due_at}"


def _next_run_after(previous: datetime, interval_seconds: int, now: datetime) -> datetime:
    next_run = previous
    interval = timedelta(seconds=interval_seconds)
    while next_run <= now:
        next_run += interval
    return next_run


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
