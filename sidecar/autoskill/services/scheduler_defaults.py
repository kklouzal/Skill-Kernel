from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from autoskill.db.scheduler import SchedulerStore, ScheduleUpsertResult


@dataclass(frozen=True)
class DefaultSchedule:
    name: str
    job_kind: str
    interval_seconds: int
    misfire_policy: str
    payload: dict[str, Any]


CORE_DEFAULT_SCHEDULES = (
    DefaultSchedule(
        name="evidence.derive",
        job_kind="evidence.derive",
        interval_seconds=10 * 60,
        misfire_policy="coalesce",
        payload={"limit": 100},
    ),
    DefaultSchedule(
        name="audit.verify",
        job_kind="audit.verify",
        interval_seconds=24 * 60 * 60,
        misfire_policy="coalesce",
        payload={"limit": 1000},
    ),
    DefaultSchedule(
        name="embeddings.generate",
        job_kind="embeddings.generate",
        interval_seconds=5 * 60,
        misfire_policy="coalesce",
        payload={"limit": 100},
    ),
    DefaultSchedule(
        name="opportunities.mine",
        job_kind="opportunities.mine",
        interval_seconds=2 * 60 * 60,
        misfire_policy="coalesce",
        payload={"limit": 100},
    ),
    DefaultSchedule(
        name="usage.aggregate",
        job_kind="usage.aggregate",
        interval_seconds=15 * 60,
        misfire_policy="coalesce",
        payload={},
    ),
    DefaultSchedule(
        name="utility.rollup",
        job_kind="utility.rollup",
        interval_seconds=12 * 60 * 60,
        misfire_policy="coalesce",
        payload={"limit": 500},
    ),
    DefaultSchedule(
        name="curation.run",
        job_kind="curation.run",
        interval_seconds=24 * 60 * 60,
        misfire_policy="coalesce",
        payload={},
    ),
    DefaultSchedule(
        name="contracts.extract",
        job_kind="contracts.extract",
        interval_seconds=24 * 60 * 60,
        misfire_policy="coalesce",
        payload={"limit": 250},
    ),
    DefaultSchedule(
        name="drift.check",
        job_kind="drift.check",
        interval_seconds=24 * 60 * 60,
        misfire_policy="catch_up_limited",
        payload={"limit": 250},
    ),
    DefaultSchedule(
        name="historical_import.parse",
        job_kind="historical_import.parse",
        interval_seconds=30 * 60,
        misfire_policy="coalesce",
        payload={"limit": 25},
    ),
    DefaultSchedule(
        name="historical_bootstrap.consolidate",
        job_kind="historical_bootstrap.consolidate",
        interval_seconds=24 * 60 * 60,
        misfire_policy="coalesce",
        payload={"persist": True, "limit": 25},
    ),
    DefaultSchedule(
        name="evaluations.run",
        job_kind="evaluations.run",
        interval_seconds=60 * 60,
        misfire_policy="coalesce",
        payload={"limit": 100},
    ),
    DefaultSchedule(
        name="repair.execute",
        job_kind="repair.execute",
        interval_seconds=60 * 60,
        misfire_policy="skip",
        payload={"limit": 25},
    ),
)


async def ensure_core_schedules(
    scheduler: SchedulerStore,
    *,
    workspace_key: str,
    enabled: bool = True,
    now: datetime | None = None,
) -> list[ScheduleUpsertResult]:
    """Register handler-backed core schedules from the implementation spec."""

    scheduled_at = now or datetime.now(UTC)
    results: list[ScheduleUpsertResult] = []
    for schedule in CORE_DEFAULT_SCHEDULES:
        payload = {"workspace_id": workspace_key, **schedule.payload}
        result = await scheduler.upsert_schedule(
            workspace_key=workspace_key,
            name=schedule.name,
            job_kind=schedule.job_kind,
            interval_seconds=schedule.interval_seconds,
            next_run_at=scheduled_at,
            payload=payload,
            enabled=enabled,
            misfire_policy=schedule.misfire_policy,
        )
        results.append(result)
    return results
