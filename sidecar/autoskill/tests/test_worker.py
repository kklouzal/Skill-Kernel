import asyncio
from dataclasses import dataclass

from autoskill.api.app import WorkerRunOnceRequest, create_app
from autoskill.db.evidence import EvidenceDeriveResult
from autoskill.db.scheduler import SchedulerTickResult
from autoskill.services.worker import WorkerStores, run_worker_once
from autoskill.tests.test_embedding_generation import MemoryPendingEmbeddingStore
from autoskill.tests.test_jobs_api import MemoryJobStore


class MemoryEvidenceWorkerStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        self.calls.append({"workspace_key": workspace_key, "limit": limit})
        return EvidenceDeriveResult(scanned=1, created=1, duplicate=0, evidence=[])

    async def list_evidence(self, *, workspace_key: str | None = None, limit: int = 50):
        return []


class MemorySchedulerWorkerStore:
    async def run_due_schedules(self, *, limit: int = 25) -> SchedulerTickResult:
        return SchedulerTickResult(due=0, enqueued=0, jobs=[])

    async def upsert_schedule(self, **_kwargs):
        raise NotImplementedError

    async def list_schedules(self, *, limit: int = 50):
        return []


@dataclass
class WorkerTestStores:
    jobs: MemoryJobStore
    scheduler: MemorySchedulerWorkerStore
    evidence: MemoryEvidenceWorkerStore
    embeddings: MemoryPendingEmbeddingStore

    def as_worker_stores(self) -> WorkerStores:
        return WorkerStores(
            jobs=self.jobs,
            scheduler=self.scheduler,
            evidence=self.evidence,
            embeddings=self.embeddings,
        )


def test_worker_run_once_dispatches_maintenance_job() -> None:
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(),
        embeddings=MemoryPendingEmbeddingStore(),
    )

    async def run():
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:one",
            payload={"workspace_id": "dev-01", "limit": 7},
        )
        return await run_worker_once(
            stores.as_worker_stores(),
            worker_id="worker-1",
            pool="maintenance",
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output == {"scanned": 1, "created": 1, "duplicate": 0, "evidence_ids": []}
    assert stores.evidence.calls == [{"workspace_key": "dev-01", "limit": 7}]


def test_worker_pool_does_not_claim_other_pool_jobs() -> None:
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(),
        embeddings=MemoryPendingEmbeddingStore(),
    )

    async def run():
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="scheduler.tick",
            idempotency_key="tick:one",
        )
        return await run_worker_once(
            stores.as_worker_stores(),
            worker_id="worker-1",
            pool="maintenance",
        )

    result = asyncio.run(run())

    assert result.status == "idle"
    assert result.claimed is False


def test_worker_run_once_api_uses_configured_stores() -> None:
    jobs = MemoryJobStore()
    evidence = MemoryEvidenceWorkerStore()
    app = create_app(
        job_store=jobs,
        scheduler_store=MemorySchedulerWorkerStore(),
        evidence_store=evidence,
        embedding_store=MemoryPendingEmbeddingStore(),
    )
    route = next(route for route in app.routes if route.path == "/v1/workers/run-once")

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:api",
        )
        return await route.endpoint(request=WorkerRunOnceRequest(worker_id="worker-api"))

    response = asyncio.run(run())

    assert response.claimed is True
    assert response.status == "succeeded"
    assert response.output["created"] == 1
