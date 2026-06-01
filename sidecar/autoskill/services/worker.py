from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from autoskill.db.embeddings import EmbeddingStore
from autoskill.db.evidence import EvidenceStore
from autoskill.db.jobs import JobRecord, JobStore
from autoskill.db.scheduler import SchedulerStore
from autoskill.services.embedding_generation import generate_pending_embeddings

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
class WorkerStores:
    jobs: JobStore
    scheduler: SchedulerStore
    evidence: EvidenceStore
    embeddings: EmbeddingStore


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
        workspace_key=_payload_workspace(job),
        embedding_model=_payload_str(job.payload, "embedding_model"),
        limit=limit,
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
}
