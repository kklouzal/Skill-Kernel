import asyncio
from dataclasses import dataclass

from autoskill.api.app import WorkerRunOnceRequest, create_app
from autoskill.db.evaluations import EvaluationRunResult
from autoskill.db.evidence import EvidenceDeriveResult
from autoskill.db.scheduler import SchedulerTickResult
from autoskill.services.worker import (
    WorkerLoopConfig,
    WorkerStores,
    build_worker_health,
    run_worker_loop,
    run_worker_once,
)
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


class MemoryEvaluationWorkerStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> EvaluationRunResult:
        self.calls.append({"workspace_key": workspace_key, "limit": limit})
        return EvaluationRunResult(
            scanned=1,
            evaluated=1,
            blocked=0,
            failed=0,
            needs_intervention=1,
            passed=0,
            evaluations=[],
        )


@dataclass
class WorkerTestStores:
    jobs: MemoryJobStore
    scheduler: MemorySchedulerWorkerStore
    evidence: MemoryEvidenceWorkerStore
    embeddings: MemoryPendingEmbeddingStore
    evaluations: MemoryEvaluationWorkerStore | None = None

    def as_worker_stores(self) -> WorkerStores:
        return WorkerStores(
            jobs=self.jobs,
            scheduler=self.scheduler,
            evidence=self.evidence,
            embeddings=self.embeddings,
            evaluations=self.evaluations,
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


def test_worker_loop_runs_bounded_concurrent_iterations() -> None:
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
            idempotency_key="derive:loop-1",
        )
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:loop-2",
        )
        return await run_worker_loop(
            stores.as_worker_stores(),
            WorkerLoopConfig(
                worker_id="loop-worker",
                pool="maintenance",
                concurrency=2,
                idle_sleep_seconds=0,
                max_iterations=2,
            ),
        )

    summary = asyncio.run(run())

    assert summary.iterations == 2
    assert summary.claimed == 2
    assert summary.succeeded == 2
    assert summary.failed == 0
    assert summary.idle == 1


def test_worker_loop_stops_on_event_while_idle() -> None:
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(),
        embeddings=MemoryPendingEmbeddingStore(),
    )

    async def run():
        stop_event = asyncio.Event()
        stop_event.set()
        return await run_worker_loop(
            stores.as_worker_stores(),
            WorkerLoopConfig(worker_id="loop-worker", idle_sleep_seconds=0),
            stop_event=stop_event,
        )

    summary = asyncio.run(run())

    assert summary.iterations == 0
    assert summary.stopped is True


def test_worker_health_reports_pool_concurrency_and_job_counts() -> None:
    jobs = MemoryJobStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:health",
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="scheduler.tick",
            idempotency_key="tick:health",
        )
        return await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": 1,
                "maintenance": 4,
                "mutation": 1,
            },
        )

    health = asyncio.run(run()).to_json()

    maintenance = next(pool for pool in health["pools"] if pool["pool"] == "maintenance")
    assert maintenance["concurrency"] == 4
    assert "evidence.derive" in maintenance["job_kinds"]
    assert health["jobs_by_status"] == {"queued": 2}
    assert health["jobs_by_kind"]["evidence.derive"] == {"queued": 1}
    assert health["jobs_by_pool"]["maintenance"] == {"queued": 1}
    assert health["jobs_by_pool"]["scheduler"] == {"queued": 1}


def test_worker_run_once_dispatches_evaluation_job() -> None:
    evaluations = MemoryEvaluationWorkerStore()
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(),
        embeddings=MemoryPendingEmbeddingStore(),
        evaluations=evaluations,
    )

    async def run():
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evaluations.run",
            idempotency_key="eval:one",
            payload={"workspace_id": "dev-01", "limit": 7},
        )
        return await run_worker_once(
            stores.as_worker_stores(),
            worker_id="worker-1",
            pool="maintenance",
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["evaluated"] == 1
    assert result.output["needs_intervention"] == 1
    assert evaluations.calls == [{"workspace_key": "dev-01", "limit": 7}]


def test_worker_health_api_uses_configured_pool_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_WORKER_MAINTENANCE_CONCURRENCY", "5")
    from autoskill.core.config import get_settings

    get_settings.cache_clear()
    jobs = MemoryJobStore()
    app = create_app(job_store=jobs)
    route = next(route for route in app.routes if route.path == "/v1/workers/health")

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="opportunities.mine",
            idempotency_key="mine:health",
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evaluations.run",
            idempotency_key="eval:health",
        )
        return await route.endpoint()

    response = asyncio.run(run())
    maintenance = next(pool for pool in response.pools if pool["pool"] == "maintenance")

    assert maintenance["concurrency"] == 5
    assert response.jobs_by_pool["maintenance"] == {"queued": 2}
    get_settings.cache_clear()
