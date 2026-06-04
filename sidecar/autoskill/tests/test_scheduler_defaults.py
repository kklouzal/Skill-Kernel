import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.db.scheduler import ScheduleRecord, ScheduleUpsertResult
from autoskill.services.scheduler_defaults import (
    CORE_DEFAULT_SCHEDULES,
    ensure_core_schedules,
)


class MemorySchedulerStore:
    def __init__(self, schedules: list[ScheduleRecord] | None = None) -> None:
        self.upserts: list[dict[str, object]] = []
        self.schedules = schedules or []

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
        self.upserts.append(
            {
                "workspace_key": workspace_key,
                "name": name,
                "job_kind": job_kind,
                "interval_seconds": interval_seconds,
                "next_run_at": next_run_at,
                "payload": payload or {},
                "enabled": enabled,
                "misfire_policy": misfire_policy,
            }
        )
        return ScheduleUpsertResult(
            schedule=ScheduleRecord(
                schedule_id=uuid4(),
                workspace_key=workspace_key,
                name=name,
                job_kind=job_kind,
                enabled=enabled,
                interval_seconds=interval_seconds,
                next_run_at=next_run_at,
                payload=payload or {},
                misfire_policy=misfire_policy,
            ),
            created=True,
        )

    async def run_due_schedules(self, *, limit: int = 25):
        raise NotImplementedError

    async def list_schedules(self, *, limit: int = 50):
        return self.schedules[:limit]


def test_core_schedule_defaults_register_handler_backed_jobs() -> None:
    scheduler = MemorySchedulerStore()
    now = datetime(2026, 6, 3, tzinfo=UTC)

    results = asyncio.run(
        ensure_core_schedules(
            scheduler,
            workspace_key="dev-01",
            now=now,
        )
    )

    assert len(results) == len(CORE_DEFAULT_SCHEDULES)
    upserts_by_name = {entry["name"]: entry for entry in scheduler.upserts}
    assert set(upserts_by_name) == {schedule.name for schedule in CORE_DEFAULT_SCHEDULES}
    assert upserts_by_name["evidence.derive"]["interval_seconds"] == 10 * 60
    assert upserts_by_name["evidence.derive"]["payload"] == {
        "workspace_id": "dev-01",
        "limit": 500,
    }
    assert upserts_by_name["embeddings.generate"]["payload"] == {
        "workspace_id": "dev-01",
        "limit": 500,
    }
    assert upserts_by_name["audit.verify"]["interval_seconds"] == 24 * 60 * 60
    assert upserts_by_name["audit.verify"]["payload"] == {
        "workspace_id": "dev-01",
        "limit": 1000,
    }
    assert upserts_by_name["drift.check"]["misfire_policy"] == "catch_up_limited"
    assert upserts_by_name["repair.execute"]["misfire_policy"] == "skip"
    assert upserts_by_name["historical_import.parse"]["payload"] == {
        "workspace_id": "dev-01",
        "max_files": 10_000,
        "max_bytes": 536_870_912,
        "max_chunks": 20_000,
    }
    assert upserts_by_name["historical_bootstrap.consolidate"]["payload"] == {
        "workspace_id": "dev-01",
        "persist": True,
        "limit": 1000,
        "min_support": 2,
    }
    assert all(entry["next_run_at"] == now for entry in scheduler.upserts)


def test_core_schedule_defaults_preserve_existing_schedule_cadence() -> None:
    now = datetime(2026, 6, 3, tzinfo=UTC)
    existing_next_run_at = datetime(2026, 6, 3, 1, 30, tzinfo=UTC)
    scheduler = MemorySchedulerStore(
        schedules=[
            ScheduleRecord(
                schedule_id=uuid4(),
                workspace_key="dev-01",
                name="embeddings.generate",
                job_kind="embeddings.generate",
                enabled=True,
                interval_seconds=300,
                next_run_at=existing_next_run_at,
                payload={"workspace_id": "dev-01", "limit": 500},
                misfire_policy="coalesce",
            )
        ]
    )

    asyncio.run(
        ensure_core_schedules(
            scheduler,
            workspace_key="dev-01",
            now=now,
        )
    )

    upserts_by_name = {entry["name"]: entry for entry in scheduler.upserts}
    assert upserts_by_name["embeddings.generate"]["next_run_at"] == existing_next_run_at
    assert upserts_by_name["evidence.derive"]["next_run_at"] == now
