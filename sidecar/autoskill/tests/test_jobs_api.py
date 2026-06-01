import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from autoskill.api.app import JobClaimRequest, JobEnqueueRequest, _require_control_auth, create_app
from autoskill.core.config import get_settings
from autoskill.db.jobs import JobEnqueueResult, JobQueueSummary, JobRecord
from fastapi import HTTPException


class MemoryJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, JobRecord] = {}
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def enqueue_job(
        self,
        *,
        workspace_key: str,
        job_kind: str,
        idempotency_key: str,
        payload: dict[str, object] | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> JobEnqueueResult:
        now = datetime.now(UTC)
        existing = self.jobs.get(idempotency_key)
        if existing:
            return JobEnqueueResult(job=existing, created=False)
        job = JobRecord(
            job_id=uuid4(),
            workspace_id=uuid4(),
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
        self.jobs[idempotency_key] = job
        return JobEnqueueResult(job=job, created=True)

    async def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        job_kinds: list[str] | None = None,
    ) -> JobRecord | None:
        now = datetime.now(UTC)
        for key, job in list(self.jobs.items()):
            if job.status == "leased" and job.lease_expires_at and job.lease_expires_at < now:
                self.jobs[key] = _replace_job(
                    job,
                    status="queued",
                    lease_owner=None,
                    lease_expires_at=None,
                )

        queued = [
            job
            for job in self.jobs.values()
            if job.status == "queued"
            and job.available_at <= now
            and (not job_kinds or job.job_kind in job_kinds)
        ]
        if not queued:
            return None
        job = sorted(queued, key=lambda item: (item.priority, item.available_at))[0]
        leased = _replace_job(
            job,
            status="leased",
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            attempts=job.attempts + 1,
        )
        self.jobs[job.idempotency_key] = leased
        return leased

    async def complete_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        status: str,
        error: str | None = None,
    ) -> JobRecord | None:
        for key, job in list(self.jobs.items()):
            if job.job_id == job_id and job.lease_owner == worker_id and job.status == "leased":
                completed = _replace_job(
                    job,
                    status=status,
                    lease_owner=None,
                    lease_expires_at=None,
                )
                self.jobs[key] = completed
                return completed
        return None

    async def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobRecord]:
        jobs = list(self.jobs.values())
        if status:
            jobs = [job for job in jobs if job.status == status]
        return jobs[:limit]

    async def summary(self) -> JobQueueSummary:
        counts: dict[str, int] = {}
        by_kind: dict[str, dict[str, int]] = {}
        for job in self.jobs.values():
            counts[job.status] = counts.get(job.status, 0) + 1
            kind_counts = by_kind.setdefault(job.job_kind, {})
            kind_counts[job.status] = kind_counts.get(job.status, 0) + 1
        return JobQueueSummary(counts=counts, by_kind=by_kind)


def _replace_job(job: JobRecord, **updates: object) -> JobRecord:
    values = job.__dict__ | updates | {"updated_at": datetime.now(UTC)}
    return JobRecord(**values)


def test_control_auth_rejects_invalid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOSKILL_CONTROL_TOKEN", "expected")
    get_settings.cache_clear()

    with pytest.raises(HTTPException):
        _require_control_auth("Bearer wrong")

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_job_store_enqueue_claim_complete_cycle() -> None:
    store = MemoryJobStore()

    first = await store.enqueue_job(
        workspace_key="dev-01",
        job_kind="evidence_extraction",
        idempotency_key="event:one",
        payload={"event_id": "one"},
    )
    duplicate = await store.enqueue_job(
        workspace_key="dev-01",
        job_kind="evidence_extraction",
        idempotency_key="event:one",
    )
    leased = await store.claim_next_job(worker_id="worker-1", lease_seconds=30)
    assert leased is not None
    completed = await store.complete_job(
        job_id=leased.job_id,
        worker_id="worker-1",
        status="succeeded",
    )

    assert first.created is True
    assert duplicate.created is False
    assert leased.status == "leased"
    assert leased.attempts == 1
    assert completed is not None
    assert completed.status == "succeeded"


def test_jobs_api_uses_job_store() -> None:
    store = MemoryJobStore()
    app = create_app(job_store=store)
    enqueue_route = next(route for route in app.routes if route.path == "/v1/jobs/enqueue")
    claim_route = next(route for route in app.routes if route.path == "/v1/jobs/claim")
    list_route = next(route for route in app.routes if route.path == "/v1/jobs")

    async def run() -> tuple[object, object, dict[str, object]]:
        enqueued = await enqueue_route.endpoint(
            request=JobEnqueueRequest(
                workspace_id="dev-01",
                job_kind="evidence_extraction",
                idempotency_key="event:two",
                payload={},
            )
        )
        claimed = await claim_route.endpoint(request=JobClaimRequest(worker_id="worker-1"))
        listed = await list_route.endpoint()
        return enqueued, claimed, listed

    enqueued, claimed, listed = asyncio.run(run())
    assert enqueued.created is True
    assert claimed.job is not None
    assert claimed.job["status"] == "leased"
    assert listed["jobs"][0]["idempotency_key"] == "event:two"


def test_jobs_api_rejects_invalid_control_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOSKILL_CONTROL_TOKEN", "expected")
    get_settings.cache_clear()

    app = create_app(job_store=MemoryJobStore())
    enqueue_route = next(route for route in app.routes if route.path == "/v1/jobs/enqueue")

    async def run() -> None:
        await enqueue_route.endpoint(
            request=JobEnqueueRequest(
                workspace_id="dev-01",
                job_kind="evidence_extraction",
                idempotency_key="event:three",
            ),
            authorization="Bearer wrong",
        )

    with pytest.raises(HTTPException):
        asyncio.run(run())
    get_settings.cache_clear()
