import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from autoskill.api.app import ScheduleUpsertRequest, create_app
from autoskill.db.jobs import JobRecord
from autoskill.db.scheduler import (
    ScheduleRecord,
    SchedulerTickResult,
    ScheduleUpsertResult,
    _has_active_scheduled_job,
    _json_object,
    _missed_run_count,
    _next_run_after,
    _should_enqueue_misfire,
)


class MemorySchedulerStore:
    def __init__(self) -> None:
        self.schedules: dict[str, ScheduleRecord] = {}
        self.jobs: list[JobRecord] = []

    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, object] | None = None,
        enabled: bool = True,
        misfire_policy: str = "coalesce",
    ) -> ScheduleUpsertResult:
        created = name not in self.schedules
        schedule = ScheduleRecord(
            schedule_id=uuid4(),
            workspace_key=workspace_key,
            name=name,
            job_kind=job_kind,
            enabled=enabled,
            interval_seconds=interval_seconds,
            next_run_at=next_run_at,
            payload=payload or {},
            misfire_policy=misfire_policy,
        )
        self.schedules[name] = schedule
        return ScheduleUpsertResult(schedule=schedule, created=created)

    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        now = datetime.now(UTC)
        due = [schedule for schedule in self.schedules.values() if schedule.next_run_at <= now]
        jobs = []
        skipped = 0
        misfires_coalesced = 0
        for schedule in due[:limit]:
            missed_runs = _missed_run_count(
                schedule.next_run_at,
                schedule.interval_seconds,
                now,
            )
            if _should_enqueue_misfire(
                schedule.next_run_at,
                schedule.misfire_policy,
                missed_runs,
            ):
                job = _job_for_schedule(schedule)
                if job.idempotency_key not in {
                    existing.idempotency_key for existing in self.jobs
                }:
                    self.jobs.append(job)
                    jobs.append(job)
            else:
                skipped += 1
            misfires_coalesced += max(0, missed_runs - 1)
            self.schedules[schedule.name] = ScheduleRecord(
                schedule_id=schedule.schedule_id,
                workspace_key=schedule.workspace_key,
                name=schedule.name,
                job_kind=schedule.job_kind,
                enabled=schedule.enabled,
                interval_seconds=schedule.interval_seconds,
                next_run_at=_next_run_after(
                    schedule.next_run_at,
                    schedule.interval_seconds,
                    now,
                    schedule.misfire_policy,
                ),
                payload=schedule.payload,
                misfire_policy=schedule.misfire_policy,
            )
        return SchedulerTickResult(
            due=len(due[:limit]),
            enqueued=len(jobs),
            jobs=jobs,
            skipped=skipped,
            misfires_coalesced=misfires_coalesced,
        )

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        return list(self.schedules.values())[:limit]


class FakeSchedulerConnection:
    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.calls: list[tuple[object, ...]] = []

    async def fetchval(self, _query: str, *args):
        self.calls.append(args)
        return self.active


def _job_for_schedule(schedule: ScheduleRecord) -> JobRecord:
    now = datetime.now(UTC)
    return JobRecord(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key=schedule.workspace_key,
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        job_kind=schedule.job_kind,
        status="queued",
        idempotency_key=f"schedule:{schedule.schedule_id}:{schedule.next_run_at.isoformat()}",
        payload=schedule.payload,
        priority=100,
        lease_owner=None,
        lease_expires_at=None,
        attempts=0,
        max_attempts=5,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


def test_active_scheduled_job_probe_scopes_workspace_and_kind() -> None:
    schedule = {
        "workspace_id": uuid4(),
        "job_kind": "embeddings.generate",
    }
    conn = FakeSchedulerConnection(active=True)

    result = asyncio.run(_has_active_scheduled_job(conn, schedule))

    assert result is True
    assert conn.calls == [(schedule["workspace_id"], "embeddings.generate")]


def test_scheduler_api_upserts_and_ticks_due_schedules() -> None:
    scheduler = MemorySchedulerStore()
    app = create_app(scheduler_store=scheduler)
    upsert_route = next(route for route in app.routes if route.path == "/v1/schedules/upsert")
    tick_route = next(route for route in app.routes if route.path == "/v1/scheduler/tick")
    list_route = next(route for route in app.routes if route.path == "/v1/schedules")

    async def run() -> tuple[object, object, dict[str, object]]:
        upserted = await upsert_route.endpoint(
            request=ScheduleUpsertRequest(
                workspace_id="dev-01",
                name="evidence",
                job_kind="evidence_extraction",
                interval_seconds=300,
                next_run_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                payload={"source": "test"},
            )
        )
        ticked = await tick_route.endpoint()
        listed = await list_route.endpoint()
        return upserted, ticked, listed

    upserted, ticked, listed = asyncio.run(run())
    assert upserted.created is True
    assert ticked.due == 1
    assert ticked.enqueued == 1
    assert ticked.lock_acquired is True
    assert ticked.jobs[0]["job_kind"] == "evidence_extraction"
    assert listed["schedules"][0]["misfire_policy"] == "coalesce"
    assert listed["schedules"][0]["name"] == "evidence"


def test_scheduler_normalizes_asyncpg_jsonb_string_payloads() -> None:
    assert _json_object('{"limit": 500, "workspace_id": "dev-01"}') == {
        "limit": 500,
        "workspace_id": "dev-01",
    }
    assert _json_object('"not-an-object"') == {}


def test_scheduler_api_skips_stale_schedule_by_misfire_policy() -> None:
    scheduler = MemorySchedulerStore()
    app = create_app(scheduler_store=scheduler)
    upsert_route = next(route for route in app.routes if route.path == "/v1/schedules/upsert")
    tick_route = next(route for route in app.routes if route.path == "/v1/scheduler/tick")
    list_route = next(route for route in app.routes if route.path == "/v1/schedules")

    async def run() -> tuple[object, object, dict[str, object]]:
        upserted = await upsert_route.endpoint(
            request=ScheduleUpsertRequest(
                workspace_id="dev-01",
                name="expensive-audit",
                job_kind="retrieval.recall_audit",
                interval_seconds=60,
                next_run_at=(datetime.now(UTC) - timedelta(seconds=180)).isoformat(),
                payload={"source": "test"},
                misfire_policy="skip",
            )
        )
        ticked = await tick_route.endpoint()
        listed = await list_route.endpoint()
        return upserted, ticked, listed

    upserted, ticked, listed = asyncio.run(run())

    assert upserted.schedule["misfire_policy"] == "skip"
    assert ticked.due == 1
    assert ticked.enqueued == 0
    assert ticked.skipped == 1
    assert ticked.misfires_coalesced >= 1
    assert listed["schedules"][0]["misfire_policy"] == "skip"
