import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from autoskill.api.app import ScheduleUpsertRequest, create_app
from autoskill.db.jobs import JobRecord
from autoskill.db.scheduler import ScheduleRecord, SchedulerTickResult, ScheduleUpsertResult


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
        )
        self.schedules[name] = schedule
        return ScheduleUpsertResult(schedule=schedule, created=created)

    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        now = datetime.now(UTC)
        due = [schedule for schedule in self.schedules.values() if schedule.next_run_at <= now]
        jobs = []
        for schedule in due[:limit]:
            job = _job_for_schedule(schedule)
            if job.idempotency_key not in {existing.idempotency_key for existing in self.jobs}:
                self.jobs.append(job)
                jobs.append(job)
            self.schedules[schedule.name] = ScheduleRecord(
                schedule_id=schedule.schedule_id,
                workspace_key=schedule.workspace_key,
                name=schedule.name,
                job_kind=schedule.job_kind,
                enabled=schedule.enabled,
                interval_seconds=schedule.interval_seconds,
                next_run_at=now + timedelta(seconds=schedule.interval_seconds),
                payload=schedule.payload,
            )
        return SchedulerTickResult(due=len(due[:limit]), enqueued=len(jobs), jobs=jobs)

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        return list(self.schedules.values())[:limit]


def _job_for_schedule(schedule: ScheduleRecord) -> JobRecord:
    now = datetime.now(UTC)
    return JobRecord(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key=schedule.workspace_key,
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
    assert ticked.jobs[0]["job_kind"] == "evidence_extraction"
    assert listed["schedules"][0]["name"] == "evidence"
