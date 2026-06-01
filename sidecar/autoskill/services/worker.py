from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal

from autoskill.db.embeddings import EmbeddingStore
from autoskill.db.evidence import EvidenceStore
from autoskill.db.jobs import JobRecord, JobStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.db.scheduler import SchedulerStore
from autoskill.services.embedding_generation import TextEmbedder, generate_pending_embeddings
from autoskill.services.opportunity import mine_opportunities

WorkerPool = Literal["scheduler", "maintenance", "mutation"]


@dataclass(frozen=True)
class WorkerRunResult:
    claimed: bool
    job: JobRecord | None
    status: str
    output: dict[str, Any] | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "claimed": self.claimed,
            "job": self.job.to_json() if self.job else None,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class WorkerLoopConfig:
    worker_id: str
    pool: WorkerPool = "maintenance"
    concurrency: int = 1
    lease_seconds: int = 300
    idle_sleep_seconds: float = 1.0
    max_iterations: int | None = None


@dataclass(frozen=True)
class WorkerLoopSummary:
    iterations: int
    claimed: int
    succeeded: int
    failed: int
    idle: int
    stopped: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "idle": self.idle,
            "stopped": self.stopped,
        }


@dataclass(frozen=True)
class WorkerPoolConfig:
    pool: WorkerPool
    concurrency: int
    job_kinds: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "pool": self.pool,
            "concurrency": self.concurrency,
            "job_kinds": self.job_kinds,
        }


@dataclass(frozen=True)
class WorkerHealthSummary:
    pools: list[WorkerPoolConfig]
    jobs_by_status: dict[str, int]
    jobs_by_kind: dict[str, dict[str, int]]
    jobs_by_pool: dict[str, dict[str, int]]

    def to_json(self) -> dict[str, Any]:
        return {
            "pools": [pool.to_json() for pool in self.pools],
            "jobs_by_status": self.jobs_by_status,
            "jobs_by_kind": self.jobs_by_kind,
            "jobs_by_pool": self.jobs_by_pool,
        }


@dataclass(frozen=True)
class WorkerStores:
    jobs: JobStore
    scheduler: SchedulerStore
    evidence: EvidenceStore
    embeddings: EmbeddingStore
    retrieval: RetrievalStore | None = None
    embedder: TextEmbedder | None = None


@dataclass(frozen=True)
class JobDefinition:
    kind: str
    pool: WorkerPool
    handler: Callable[[WorkerStores, JobRecord], Awaitable[dict[str, Any]]]


async def run_worker_once(
    stores: WorkerStores,
    *,
    worker_id: str,
    pool: WorkerPool = "maintenance",
    lease_seconds: int = 300,
) -> WorkerRunResult:
    allowed_kinds = _job_kinds_for_pool(pool)
    job = await stores.jobs.claim_next_job(
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        job_kinds=allowed_kinds,
    )
    if job is None:
        return WorkerRunResult(claimed=False, job=None, status="idle")

    definition = JOB_DEFINITIONS.get(job.job_kind)
    if definition is None:
        error = f"unsupported job kind: {job.job_kind}"
        completed = await stores.jobs.complete_job(
            job_id=job.job_id,
            worker_id=worker_id,
            status="failed",
            error=error,
        )
        return WorkerRunResult(claimed=True, job=completed or job, status="failed", error=error)

    try:
        output = await definition.handler(stores, job)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        completed = await stores.jobs.complete_job(
            job_id=job.job_id,
            worker_id=worker_id,
            status="failed",
            error=message,
        )
        return WorkerRunResult(claimed=True, job=completed or job, status="failed", error=message)

    completed = await stores.jobs.complete_job(
        job_id=job.job_id,
        worker_id=worker_id,
        status="succeeded",
    )
    return WorkerRunResult(
        claimed=True,
        job=completed or job,
        status="succeeded",
        output=output,
    )


async def run_worker_loop(
    stores: WorkerStores,
    config: WorkerLoopConfig,
    *,
    stop_event: asyncio.Event | None = None,
) -> WorkerLoopSummary:
    concurrency = max(1, min(config.concurrency, 32))
    iterations = 0
    claimed = 0
    succeeded = 0
    failed = 0
    idle = 0

    while stop_event is None or not stop_event.is_set():
        if config.max_iterations is not None and iterations >= config.max_iterations:
            break
        iterations += 1
        results = await asyncio.gather(
            *[
                run_worker_once(
                    stores,
                    worker_id=f"{config.worker_id}-{index + 1}",
                    pool=config.pool,
                    lease_seconds=config.lease_seconds,
                )
                for index in range(concurrency)
            ]
        )
        claimed_now = [result for result in results if result.claimed]
        claimed += len(claimed_now)
        succeeded += sum(1 for result in claimed_now if result.status == "succeeded")
        failed += sum(1 for result in claimed_now if result.status == "failed")

        if not claimed_now:
            idle += 1
            if stop_event is None:
                await asyncio.sleep(config.idle_sleep_seconds)
            else:
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=config.idle_sleep_seconds)

    return WorkerLoopSummary(
        iterations=iterations,
        claimed=claimed,
        succeeded=succeeded,
        failed=failed,
        idle=idle,
        stopped=bool(stop_event and stop_event.is_set()),
    )


async def build_worker_health(
    jobs: JobStore,
    *,
    concurrency_by_pool: dict[WorkerPool, int],
) -> WorkerHealthSummary:
    summary = await jobs.summary()
    pools = [
        WorkerPoolConfig(
            pool=pool,
            concurrency=max(1, concurrency_by_pool.get(pool, 1)),
            job_kinds=_job_kinds_for_pool(pool),
        )
        for pool in ("scheduler", "maintenance", "mutation")
    ]
    jobs_by_pool: dict[str, dict[str, int]] = {pool.pool: {} for pool in pools}
    kind_to_pool = {
        definition.kind: definition.pool for definition in JOB_DEFINITIONS.values()
    }
    for job_kind, status_counts in summary.by_kind.items():
        pool = kind_to_pool.get(job_kind, "unknown")
        pool_counts = jobs_by_pool.setdefault(pool, {})
        for status, count in status_counts.items():
            pool_counts[status] = pool_counts.get(status, 0) + count
    return WorkerHealthSummary(
        pools=pools,
        jobs_by_status=summary.counts,
        jobs_by_kind=summary.by_kind,
        jobs_by_pool=jobs_by_pool,
    )


async def _run_scheduler_tick(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    limit = _payload_int(job.payload, "limit", default=25, minimum=1, maximum=250)
    result = await stores.scheduler.run_due_schedules(limit=limit)
    return {
        "due": result.due,
        "enqueued": result.enqueued,
        "job_ids": [str(enqueued.job_id) for enqueued in result.jobs],
    }


async def _run_evidence_derive(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    limit = _payload_int(job.payload, "limit", default=100, minimum=1, maximum=500)
    result = await stores.evidence.derive_from_raw_events(
        workspace_key=_payload_workspace(job),
        limit=limit,
    )
    return {
        "scanned": result.scanned,
        "created": result.created,
        "duplicate": result.duplicate,
        "evidence_ids": [str(record.evidence_id) for record in result.evidence],
    }


async def _run_embedding_generate(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    limit = _payload_int(job.payload, "limit", default=100, minimum=1, maximum=500)
    result = await generate_pending_embeddings(
        stores.embeddings,
        embedder=stores.embedder,
        workspace_key=_payload_workspace(job),
        embedding_model=_payload_str(job.payload, "embedding_model"),
        limit=limit,
    )
    return result.to_json()


async def _run_opportunity_mine(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.retrieval is None:
        raise ValueError("retrieval store is required for opportunity mining")
    limit = _payload_int(job.payload, "limit", default=100, minimum=1, maximum=500)
    min_support = _payload_int(job.payload, "min_support", default=2, minimum=2, maximum=25)
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("workspace_id is required for opportunity mining")
    result = await mine_opportunities(
        stores.evidence,
        stores.retrieval,
        workspace_key=workspace,
        limit=limit,
        min_support=min_support,
    )
    return result.to_json()


def _job_kinds_for_pool(pool: WorkerPool) -> list[str]:
    return [
        definition.kind
        for definition in JOB_DEFINITIONS.values()
        if definition.pool == pool
    ]


def _payload_workspace(job: JobRecord) -> str | None:
    return _payload_str(job.payload, "workspace_id") or job.workspace_key


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _payload_int(
    payload: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


JOB_DEFINITIONS: dict[str, JobDefinition] = {
    "scheduler.tick": JobDefinition("scheduler.tick", "scheduler", _run_scheduler_tick),
    "evidence.derive": JobDefinition("evidence.derive", "maintenance", _run_evidence_derive),
    "embeddings.generate": JobDefinition(
        "embeddings.generate",
        "maintenance",
        _run_embedding_generate,
    ),
    "opportunities.mine": JobDefinition(
        "opportunities.mine",
        "maintenance",
        _run_opportunity_mine,
    ),
}
