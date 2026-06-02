from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from autoskill.core.hashing import sha256_json
from autoskill.core.skillir import SkillIR
from autoskill.db.activation import ActivationGateStore
from autoskill.db.attribution import AttributionStore
from autoskill.db.context import ContextGovernanceStore
from autoskill.db.contracts import ContractStore
from autoskill.db.embeddings import EmbeddingStore
from autoskill.db.evaluations import EvaluationStore
from autoskill.db.evidence import EvidenceStore
from autoskill.db.external_skills import ExternalSkillStore
from autoskill.db.governance import GovernanceStore, RevocationRequestRecord
from autoskill.db.historical import HistoricalImportStore
from autoskill.db.jobs import JobRecord, JobStore
from autoskill.db.memory import MemoryGovernanceStore
from autoskill.db.observability import NullObservabilityStore, ObservabilityStore
from autoskill.db.profiles import ProfileStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.db.scheduler import SchedulerStore
from autoskill.db.topology import TopologyStore
from autoskill.db.usage import UsageStore
from autoskill.db.utility import UtilityStore
from autoskill.services.compiler import (
    CONTEXT_COMPILER_VERSION,
    compile_skill_with_context_governance,
)
from autoskill.services.embedding_generation import (
    TextEmbedder,
    build_text_embedder_from_profile,
    generate_pending_embeddings,
)
from autoskill.services.evaluation_runner import run_pending_proposal_gates_with_trace
from autoskill.services.external_import import materialize_external_skill_import
from autoskill.services.external_inventory import scan_external_skill_roots
from autoskill.services.historical_discovery import discover_historical_sources
from autoskill.services.opportunity import mine_opportunities
from autoskill.services.writer import (
    apply_staged_manifest_with_governance,
    delete_active_skill_with_governance,
    resolve_contained,
    rollback_active_skill_with_governance,
    stage_compiled_skill,
)

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
    workers: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "pools": [pool.to_json() for pool in self.pools],
            "jobs_by_status": self.jobs_by_status,
            "jobs_by_kind": self.jobs_by_kind,
            "jobs_by_pool": self.jobs_by_pool,
            "workers": self.workers,
        }


@dataclass(frozen=True)
class WorkerStores:
    jobs: JobStore
    scheduler: SchedulerStore
    evidence: EvidenceStore
    embeddings: EmbeddingStore
    external_skills: ExternalSkillStore | None = None
    historical_import: HistoricalImportStore | None = None
    retrieval: RetrievalStore | None = None
    evaluations: EvaluationStore | None = None
    governance: GovernanceStore | None = None
    utility: UtilityStore | None = None
    contracts: ContractStore | None = None
    context_governance: ContextGovernanceStore | None = None
    topology: TopologyStore | None = None
    usage: UsageStore | None = None
    observability: ObservabilityStore | None = None
    attribution: AttributionStore | None = None
    activation_gate: ActivationGateStore | None = None
    profiles: ProfileStore | None = None
    memory_governance: MemoryGovernanceStore | None = None
    embedder: TextEmbedder | None = None
    embedding_api_key: str | None = None
    embedding_api_base_url: str | None = None
    workspace_root: Path | None = None
    archive_root: Path | None = None
    external_skill_roots: list[Path] | None = None
    historical_import_roots: list[Path] | None = None


@dataclass(frozen=True)
class JobDefinition:
    kind: str
    pool: WorkerPool
    handler: Callable[[WorkerStores, JobRecord], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RepairExecutionSource:
    source_kind: Literal["curation_action", "drift_event"]
    source_id: UUID
    skill_id: UUID | None
    skill_version_id: UUID | None
    proposal: dict[str, Any]
    reason: str


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
    span = await _start_job_span(stores, job, worker_id=worker_id, pool=pool)
    await _record_job_progress(
        stores,
        job,
        worker_id=worker_id,
        pool=pool,
        phase="claimed",
        summary=_job_progress_summary(job, phase="claimed"),
    )
    if definition is None:
        error = f"unsupported job kind: {job.job_kind}"
        completed = await stores.jobs.complete_job(
            job_id=job.job_id,
            worker_id=worker_id,
            status="failed",
            error=error,
        )
        await _finish_job_span(
            stores,
            span_id=span.span_id,
            status="error",
            error=error,
        )
        await _record_job_progress(
            stores,
            completed or job,
            worker_id=worker_id,
            pool=pool,
            phase="failed",
            summary=_job_progress_summary(
                completed or job,
                phase="failed",
                error=error,
            ),
            clear_current_job=True,
        )
        return WorkerRunResult(claimed=True, job=completed or job, status="failed", error=error)

    try:
        output = await _run_with_lease_renewal(
            stores,
            job,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            handler=definition.handler,
        )
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        completed = await stores.jobs.complete_job(
            job_id=job.job_id,
            worker_id=worker_id,
            status="failed",
            error=message,
        )
        await _finish_job_span(
            stores,
            span_id=span.span_id,
            status="error",
            error=message,
        )
        await _record_job_progress(
            stores,
            completed or job,
            worker_id=worker_id,
            pool=pool,
            phase="failed",
            summary=_job_progress_summary(
                completed or job,
                phase="failed",
                error=message,
            ),
            clear_current_job=True,
        )
        return WorkerRunResult(claimed=True, job=completed or job, status="failed", error=message)

    completed = await stores.jobs.complete_job(
        job_id=job.job_id,
        worker_id=worker_id,
        status="succeeded",
    )
    await _finish_job_span(
        stores,
        span_id=span.span_id,
        status="ok",
        output=output,
    )
    await _record_job_progress(
        stores,
        completed or job,
        worker_id=worker_id,
        pool=pool,
        phase="succeeded",
        summary=_job_progress_summary(
            completed or job,
            phase="succeeded",
            output=output,
        ),
        clear_current_job=True,
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
        await stores.jobs.record_worker_heartbeat(
            worker_id=config.worker_id,
            pool=config.pool,
            concurrency=concurrency,
            status="running",
            summary={
                "iterations": iterations,
                "claimed": claimed,
                "succeeded": succeeded,
                "failed": failed,
                "idle": idle,
            },
        )
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

    await stores.jobs.record_worker_heartbeat(
        worker_id=config.worker_id,
        pool=config.pool,
        concurrency=concurrency,
        status="stopped" if stop_event and stop_event.is_set() else "idle",
        summary={
            "iterations": iterations,
            "claimed": claimed,
            "succeeded": succeeded,
            "failed": failed,
            "idle": idle,
        },
    )
    return WorkerLoopSummary(
        iterations=iterations,
        claimed=claimed,
        succeeded=succeeded,
        failed=failed,
        idle=idle,
        stopped=bool(stop_event and stop_event.is_set()),
    )


async def _run_with_lease_renewal(
    stores: WorkerStores,
    job: JobRecord,
    *,
    worker_id: str,
    lease_seconds: int,
    handler: Callable[[WorkerStores, JobRecord], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    interval = max(0.1, min(float(lease_seconds) / 2.0, 60.0))
    task = asyncio.create_task(handler(stores, job))
    while True:
        done, _pending = await asyncio.wait({task}, timeout=interval)
        if task in done:
            return await task
        renewed = await stores.jobs.renew_job_lease(
            job_id=job.job_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if renewed is None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise RuntimeError("job lease renewal failed")
        await _record_job_progress(
            stores,
            renewed,
            worker_id=worker_id,
            pool=JOB_DEFINITIONS[job.job_kind].pool,
            phase="lease_renewed",
            summary=_job_progress_summary(
                renewed,
                phase="lease_renewed",
                lease_seconds=lease_seconds,
            ),
        )


async def build_worker_health(
    jobs: JobStore,
    *,
    concurrency_by_pool: dict[WorkerPool, int],
) -> WorkerHealthSummary:
    summary = await jobs.summary()
    heartbeats = await jobs.list_worker_heartbeats()
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
        workers=[heartbeat.to_json() for heartbeat in heartbeats],
    )


async def _start_job_span(
    stores: WorkerStores,
    job: JobRecord,
    *,
    worker_id: str,
    pool: WorkerPool,
):
    observability = stores.observability or NullObservabilityStore()
    workspace = _payload_workspace(job) or job.workspace_key or "unknown"
    return await observability.start_span(
        workspace_key=workspace,
        trace_id=job.trace_id,
        parent_span_id=job.span_id or job.parent_span_id,
        operation_name=job.job_kind,
        operation_kind="job",
        safe_attributes={
            "job_id": str(job.job_id),
            "job_kind": job.job_kind,
            "worker_id": worker_id,
            "pool": pool,
            "attempt": job.attempts,
        },
        object_refs=[
            {
                "object_type": "job",
                "object_id": str(job.job_id),
            }
        ],
    )


async def _finish_job_span(
    stores: WorkerStores,
    *,
    span_id: UUID,
    status: str,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    observability = stores.observability or NullObservabilityStore()
    attributes: dict[str, Any] = {}
    if error:
        attributes["error"] = error[:500]
    if output is not None:
        attributes["output_keys"] = sorted(output.keys())
    await observability.finish_span(
        span_id=span_id,
        status=status,  # type: ignore[arg-type]
        safe_attributes=attributes,
    )


async def _record_job_progress(
    stores: WorkerStores,
    job: JobRecord,
    *,
    worker_id: str,
    pool: WorkerPool,
    phase: str,
    summary: dict[str, Any],
    clear_current_job: bool = False,
) -> None:
    """Persist content-safe worker progress through the existing heartbeat surface."""
    await stores.jobs.record_worker_heartbeat(
        worker_id=worker_id,
        pool=pool,
        concurrency=1,
        status=phase,
        current_job_id=None if clear_current_job else job.job_id,
        summary=summary,
    )


def _job_progress_summary(
    job: JobRecord,
    *,
    phase: str,
    lease_seconds: int | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload = _payload_dict(job.payload)
    summary: dict[str, Any] = {
        "phase": phase,
        "job_id": str(job.job_id),
        "job_kind": job.job_kind,
        "attempt": job.attempts,
        "max_attempts": job.max_attempts,
        "workspace_key": _payload_workspace(job) or job.workspace_key,
        "payload_controls": _payload_progress_controls(payload),
    }
    if lease_seconds is not None:
        summary["lease_seconds"] = lease_seconds
    if output is not None:
        summary["output"] = _output_progress_summary(output)
    if error:
        summary["error"] = error[:500]
    return summary


def _payload_progress_controls(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "limit",
        "min_support",
        "max_archive",
        "archive_threshold",
        "embedding_profile_key",
        "embedding_model",
        "executor_profile_key",
        "policy_version",
        "operation_id",
        "decision_id",
        "request_id",
        "workspace_id",
    }
    controls: dict[str, Any] = {}
    for key in sorted(allowed):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, str):
            controls[key] = value[:200]
        elif isinstance(value, int | float | bool) or value is None:
            controls[key] = value
        elif isinstance(value, list):
            controls[key] = [str(item)[:100] for item in value[:10]]
    return controls


def _output_progress_summary(output: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {"keys": sorted(output.keys())[:50]}
    for key, value in output.items():
        if isinstance(value, bool | int | float) or value is None:
            safe[key] = value
        elif isinstance(value, str) and key.endswith(
            ("_id", "_ids", "_status", "_state", "_model")
        ):
            safe[key] = value[:200]
        elif isinstance(value, list):
            safe[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            safe[f"{key}_keys"] = sorted(str(item) for item in value)[:25]
    return safe


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
    workspace = _payload_workspace(job)
    profile_key = _payload_str(job.payload, "embedding_profile_key")
    embedder = stores.embedder
    embedding_model = _payload_str(job.payload, "embedding_model")
    embedding_profile_id = None
    if profile_key:
        if stores.profiles is None:
            raise ValueError("profile store is required for embedding_profile_key jobs")
        if workspace is None:
            raise ValueError("workspace_id is required for embedding_profile_key jobs")
        profile = await stores.profiles.get_embedding_profile(
            workspace_key=workspace,
            profile_key=profile_key,
        )
        if profile is None:
            raise ValueError(f"embedding profile not found: {workspace}/{profile_key}")
        embedder = build_text_embedder_from_profile(
            profile,
            embedding_api_key=stores.embedding_api_key,
            embedding_api_base_url=stores.embedding_api_base_url,
        )
        embedding_model = profile.model
        embedding_profile_id = profile.profile_id
    elif workspace is not None and stores.profiles is not None:
        profile = await stores.profiles.get_active_embedding_profile(workspace_key=workspace)
        if profile is not None:
            embedder = build_text_embedder_from_profile(
                profile,
                embedding_api_key=stores.embedding_api_key,
                embedding_api_base_url=stores.embedding_api_base_url,
            )
            embedding_model = profile.model
            embedding_profile_id = profile.profile_id

    observability = stores.observability or NullObservabilityStore()
    span = await observability.start_span(
        workspace_key=workspace or job.workspace_key or "unknown",
        trace_id=job.trace_id,
        parent_span_id=job.span_id or job.parent_span_id,
        operation_name="embeddings.generate",
        operation_kind="embedding_call",
        safe_attributes={
            "source": "worker",
            "job_id": str(job.job_id),
            "job_kind": job.job_kind,
            "limit": limit,
            "embedding_profile_key": profile_key,
            "embedding_profile_id": str(embedding_profile_id)
            if embedding_profile_id
            else None,
            "embedding_model": embedding_model,
        },
        object_refs=[{"object_type": "job", "object_id": str(job.job_id)}],
    )
    try:
        result = await generate_pending_embeddings(
            stores.embeddings,
            embedder=embedder,
            workspace_key=workspace,
            embedding_model=embedding_model,
            embedding_profile_id=embedding_profile_id,
            limit=limit,
        )
    except Exception as error:
        await observability.finish_span(
            span_id=span.span_id,
            status="error",
            safe_attributes={"error": f"{type(error).__name__}: {error}"[:500]},
        )
        raise
    await observability.finish_span(
        span_id=span.span_id,
        status="ok",
        safe_attributes={
            "scanned": result.scanned,
            "generated": result.generated,
            "created": result.created,
            "updated": result.updated,
            "embedding_model": result.embedding_model,
            "embedding_dim": result.embedding_dim,
            "embedding_profile_id": result.embedding_profile_id,
        },
        object_refs=[
            {"object_type": "job", "object_id": str(job.job_id)},
            *[
                {"object_type": str(source["object_type"]), "object_id": str(source["object_id"])}
                for source in result.sources[:50]
            ],
        ],
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


async def _run_evaluation_proposal_gates(
    stores: WorkerStores,
    job: JobRecord,
) -> dict[str, Any]:
    if stores.evaluations is None:
        raise ValueError("evaluation store is required for proposal-gate evaluation")
    limit = _payload_int(job.payload, "limit", default=50, minimum=1, maximum=250)
    result = await run_pending_proposal_gates_with_trace(
        stores.evaluations,
        observability=stores.observability,
        workspace_key=_payload_workspace(job),
        limit=limit,
        trace_id=job.trace_id,
        parent_span_id=job.span_id or job.parent_span_id,
        source="worker",
        safe_attributes={
            "job_id": str(job.job_id),
            "job_kind": job.job_kind,
        },
    )
    return result.to_json()


async def _run_utility_rollup(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.utility is None:
        raise ValueError("utility store is required for utility rollups")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("utility rollup requires workspace_id")
    result = await stores.utility.run_utility_rollup(
        workspace_key=workspace,
        limit=_payload_int(job.payload, "limit", default=250, minimum=1, maximum=1000),
    )
    return result.to_json()


async def _run_curation(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.utility is None:
        raise ValueError("utility store is required for curation")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("curation requires workspace_id")
    payload = _payload_dict(job.payload)
    result = await stores.utility.run_curation(
        workspace_key=workspace,
        archive_threshold=float(payload.get("archive_threshold", -1.0)),
        max_archive=_payload_int(job.payload, "max_archive", default=5, minimum=0, maximum=100),
        promotion_min_retrieval=_payload_int(
            job.payload,
            "promotion_min_retrieval",
            default=3,
            minimum=1,
            maximum=1000,
        ),
        max_promote=_payload_int(job.payload, "max_promote", default=3, minimum=0, maximum=100),
        active_budget=(
            None
            if payload.get("active_budget") is None
            else _payload_int(job.payload, "active_budget", default=100, minimum=1, maximum=1000)
        ),
        max_merge=_payload_int(job.payload, "max_merge", default=5, minimum=0, maximum=100),
    )
    return result.to_json()


async def _run_usage_aggregate(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.usage is None:
        raise ValueError("usage store is required for usage aggregation")
    workspace = _payload_workspace(job) or job.workspace_key
    if workspace is None:
        raise ValueError("usage aggregation requires workspace_id")
    result = await stores.usage.aggregate_usage(
        workspace_key=workspace,
        limit=_payload_int(job.payload, "limit", default=500, minimum=1, maximum=5000),
        min_support=_payload_int(
            job.payload,
            "min_support",
            default=2,
            minimum=1,
            maximum=50,
        ),
    )
    min_support = _payload_int(
        job.payload,
        "recommendation_min_support",
        default=max(3, _payload_int(job.payload, "min_support", default=2, minimum=1, maximum=50)),
        minimum=1,
        maximum=50,
    )
    recommendations = await stores.usage.recommend_topology_operations(
        workspace_key=workspace,
        limit=_payload_int(
            job.payload,
            "recommendation_limit",
            default=5,
            minimum=0,
            maximum=50,
        ),
        min_support=min_support,
        min_success_count=_payload_int(
            job.payload,
            "recommendation_min_success_count",
            default=1,
            minimum=0,
            maximum=50,
        ),
        max_failure_ratio=float(_payload_dict(job.payload).get("max_failure_ratio", 0.25)),
        min_sequence_count=_payload_int(
            job.payload,
            "recommendation_min_sequence_count",
            default=1,
            minimum=0,
            maximum=50,
        ),
    )
    output = result.to_json()
    output["topology_recommendations"] = [
        recommendation.to_json() for recommendation in recommendations
    ]
    return output


async def _run_contract_extraction(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.contracts is None:
        raise ValueError("contract store is required for contract extraction")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("contract extraction requires workspace_id")
    result = await stores.contracts.extract_contracts(
        workspace_key=workspace,
        limit=_payload_int(job.payload, "limit", default=250, minimum=1, maximum=1000),
    )
    return result.to_json()


async def _run_drift_checks(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.contracts is None:
        raise ValueError("contract store is required for drift checks")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("drift checks require workspace_id")
    result = await stores.contracts.run_drift_checks(
        workspace_key=workspace,
        limit=_payload_int(job.payload, "limit", default=250, minimum=1, maximum=1000),
    )
    return result.to_json()


async def _run_repair_execute(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.governance is None:
        raise ValueError("governance store is required for repair execution")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("repair execution requires workspace_id")

    curation_limit = _payload_int(
        job.payload,
        "curation_limit",
        default=10,
        minimum=0,
        maximum=100,
    )
    drift_limit = _payload_int(job.payload, "drift_limit", default=10, minimum=0, maximum=100)
    sources = await _claim_repair_execution_sources(
        stores,
        workspace_key=workspace,
        curation_limit=curation_limit,
        drift_limit=drift_limit,
        worker_id=job.lease_owner,
        job_id=job.job_id,
    )
    processed: list[dict[str, Any]] = []
    queued = blocked = writer_apply_queued = gate_jobs_queued = 0
    for source in sources:
        try:
            execution = await _execute_repair_source(stores, job, workspace, source)
            status = "queued"
            queued += 1
            writer_apply_queued += int(execution.get("queued_job_kind") == "writer.apply")
            gate_jobs_queued += int(execution.get("queued_job_kind") != "writer.apply")
        except Exception as error:
            status = "blocked"
            blocked += 1
            execution = {
                "status": "blocked",
                "source_kind": source.source_kind,
                "source_id": str(source.source_id),
                "error": f"{type(error).__name__}: {error}",
            }
        await _complete_repair_execution_source(
            stores,
            workspace_key=workspace,
            source=source,
            status=status,
            execution=execution,
        )
        processed.append(execution)
    return {
        "claimed": len(sources),
        "queued": queued,
        "blocked": blocked,
        "writer_apply_queued": writer_apply_queued,
        "gate_jobs_queued": gate_jobs_queued,
        "repairs": processed,
    }


async def _claim_repair_execution_sources(
    stores: WorkerStores,
    *,
    workspace_key: str,
    curation_limit: int,
    drift_limit: int,
    worker_id: str | None,
    job_id: UUID,
) -> list[RepairExecutionSource]:
    sources: list[RepairExecutionSource] = []
    if curation_limit > 0 and stores.utility is not None:
        claim = getattr(stores.utility, "claim_planned_repair_actions", None)
        if claim is not None:
            actions = await claim(
                workspace_key=workspace_key,
                limit=curation_limit,
                worker_id=worker_id,
                job_id=job_id,
            )
            for action in actions:
                proposal = _json_object(action.features.get("repair_proposal"))
                if not proposal:
                    continue
                sources.append(
                    RepairExecutionSource(
                        source_kind="curation_action",
                        source_id=action.curation_action_id,
                        skill_id=action.skill_id,
                        skill_version_id=None,
                        proposal=proposal,
                        reason=action.reason,
                    )
                )
    if drift_limit > 0 and stores.contracts is not None:
        claim = getattr(stores.contracts, "claim_open_drift_repair_events", None)
        if claim is not None:
            events = await claim(
                workspace_key=workspace_key,
                limit=drift_limit,
                worker_id=worker_id,
                job_id=job_id,
            )
            for event in events:
                sources.append(
                    RepairExecutionSource(
                        source_kind="drift_event",
                        source_id=event.drift_event_id,
                        skill_id=event.skill_id,
                        skill_version_id=event.skill_version_id,
                        proposal=event.repair_candidate,
                        reason=event.reason,
                    )
                )
    return sources


async def _execute_repair_source(
    stores: WorkerStores,
    job: JobRecord,
    workspace_key: str,
    source: RepairExecutionSource,
) -> dict[str, Any]:
    memory_influence_ids = await _validate_memory_influence_for_mutation(
        stores,
        workspace_key=workspace_key,
        memory_ids=[
            *_payload_memory_influence_ids(job.payload),
            *_payload_memory_influence_ids(source.proposal),
        ],
        run_id=f"repair-execute:{source.source_kind}:{source.source_id}",
        control_surface="repair.execute",
        decision_context={
            "job_id": str(job.job_id),
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
            "proposal_kind": source.proposal.get("proposal_kind")
            or source.proposal.get("kind"),
        },
    )
    transaction = await stores.governance.start_transaction(
        workspace_key=workspace_key,
        transaction_kind="repair_proposal_execution",
        idempotency_key=f"repair-execute:{source.source_kind}:{source.source_id}",
        plan_hash=sha256_json(
            {
                "source_kind": source.source_kind,
                "source_id": str(source.source_id),
                "skill_id": str(source.skill_id) if source.skill_id else None,
                "skill_version_id": (
                    str(source.skill_version_id) if source.skill_version_id else None
                ),
                "proposal": source.proposal,
            }
        ),
        actor="autoskill-mutation-worker",
        cause={
            "source": "repair.execute",
            "job_id": str(job.job_id),
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
            "reason": source.reason,
        },
        policy_snapshot={
            "fail_closed": True,
            "writer_apply_requires_policy_approved": True,
            "writer_apply_requires_activation_gate": True,
            "repair_materialization_requires_policy_approved": True,
            "insufficient_source_data_action": "queue_gate_or_recheck_job",
        },
    )
    await stores.governance.update_transaction_status(
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        status="planning",
        metrics={
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
        },
    )
    item = await stores.governance.record_transaction_item(
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        item_kind=f"{source.source_kind}_repair_proposal",
        item_id=source.source_id,
        activation_state="planned",
        after_hash=sha256_json(source.proposal),
        rollback_action={
            "operation": "operator_review",
            "reason": "repair execution metadata only; no runtime artifact mutation recorded",
        },
    )
    await stores.governance.record_provenance_edge(
        workspace_key=workspace_key,
        source_kind="evolution_transaction",
        source_id=transaction.transaction.evolution_transaction_id,
        derived_kind="transaction_item",
        derived_id=item.transaction_item_id,
        relation="records_repair_execution_plan",
    )

    apply_payload = _writer_apply_payload_for_repair(
        source,
        transaction_id=transaction.transaction.evolution_transaction_id,
    )
    if apply_payload is None:
        apply_payload = await _materialized_writer_apply_payload_for_repair(
            stores,
            source,
            workspace_key=workspace_key,
            transaction_id=transaction.transaction.evolution_transaction_id,
        )
    if apply_payload is not None:
        queued_job = await stores.jobs.enqueue_job(
            workspace_key=workspace_key,
            job_kind="writer.apply",
            idempotency_key=f"repair-execute:{source.source_kind}:{source.source_id}:writer-apply",
            payload=apply_payload,
            trace_id=job.trace_id,
            parent_span_id=job.span_id or job.parent_span_id,
            priority=_payload_int(
                job.payload,
                "queued_priority",
                default=25,
                minimum=1,
                maximum=1000,
            ),
            max_attempts=1,
        )
        queued_kind = "writer.apply"
    else:
        queued_kind = (
            "evaluations.run"
            if source.source_kind == "curation_action"
            else "drift.check"
        )
        queued_job = await stores.jobs.enqueue_job(
            workspace_key=workspace_key,
            job_kind=queued_kind,
            idempotency_key=f"repair-execute:{source.source_kind}:{source.source_id}:{queued_kind}",
            payload={
                "workspace_id": workspace_key,
                "limit": 25,
                "repair_execution": {
                    "source_kind": source.source_kind,
                    "source_id": str(source.source_id),
                    "proposal_kind": source.proposal.get("proposal_kind")
                    or source.proposal.get("kind"),
                    "reason": "source data insufficient for autonomous writer apply",
                },
            },
            trace_id=job.trace_id,
            parent_span_id=job.span_id or job.parent_span_id,
            priority=_payload_int(
                job.payload,
                "queued_priority",
                default=50,
                minimum=1,
                maximum=1000,
            ),
            max_attempts=1,
        )

    await stores.governance.update_transaction_status(
        evolution_transaction_id=transaction.transaction.evolution_transaction_id,
        status="queued",
        metrics={
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
            "queued_job_kind": queued_kind,
            "queued_job_id": str(queued_job.job.job_id),
            "queued_job_created": queued_job.created,
        },
    )
    await _record_memory_influence_for_mutation(
        stores,
        workspace_key=workspace_key,
        memory_ids=memory_influence_ids,
        run_id=f"repair-execute:{source.source_kind}:{source.source_id}",
        decision={
            "control_surface": "repair.execute",
            "decision": "mutation_queued",
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
            "evolution_transaction_id": str(
                transaction.transaction.evolution_transaction_id
            ),
            "queued_job_kind": queued_kind,
            "queued_job_id": str(queued_job.job.job_id),
        },
    )
    return {
        "status": "queued",
        "source_kind": source.source_kind,
        "source_id": str(source.source_id),
        "repair_transaction_id": str(transaction.transaction.evolution_transaction_id),
        "transaction_created": transaction.created,
        "transaction_item_id": str(item.transaction_item_id),
        "queued_job_kind": queued_kind,
        "queued_job_id": str(queued_job.job.job_id),
        "queued_job_created": queued_job.created,
        "fail_closed": apply_payload is None,
    }


def _writer_apply_payload_for_repair(
    source: RepairExecutionSource,
    *,
    transaction_id: UUID,
) -> dict[str, Any] | None:
    execution = _json_object(source.proposal.get("execution"))
    writer_apply = _json_object(source.proposal.get("writer_apply"))
    payload = execution or writer_apply
    if not payload:
        return None
    if payload.get("policy_approved") is not True:
        return None
    manifest_relative_path = _string_value(payload.get("manifest_relative_path"))
    if not manifest_relative_path:
        return None
    payload_transaction_id = _uuid_value(payload.get("evolution_transaction_id")) or transaction_id
    return {
        "workspace_id": payload.get("workspace_id"),
        "policy_approved": True,
        "activation_gate_required": True,
        "evolution_transaction_id": str(payload_transaction_id),
        "manifest_relative_path": manifest_relative_path,
        "repair_execution": {
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
        },
    }


async def _materialized_writer_apply_payload_for_repair(
    stores: WorkerStores,
    source: RepairExecutionSource,
    *,
    workspace_key: str,
    transaction_id: UUID,
) -> dict[str, Any] | None:
    materialization = _json_object(source.proposal.get("materialization"))
    if not materialization:
        return None
    if materialization.get("policy_approved") is not True:
        return None
    if stores.workspace_root is None:
        return None
    skill_version_id = (
        source.skill_version_id
        or _uuid_value(materialization.get("skill_version_id"))
        or _uuid_value(source.proposal.get("skill_version_id"))
    )
    if skill_version_id is None:
        return None
    slug = _string_value(materialization.get("slug")) or (
        f"repair-{source.source_kind}-{source.source_id.hex[:8]}"
    )
    max_context_tokens = _payload_int(
        materialization,
        "max_context_tokens",
        default=900,
        minimum=100,
        maximum=2000,
    )
    if stores.context_governance is None:
        return None
    repair_skill = _repair_skillir(source, slug=slug, materialization=materialization)
    context_result = await compile_skill_with_context_governance(
        repair_skill,
        stores.context_governance,
        workspace_key=workspace_key,
        skill_id=source.skill_id,
        skill_version_id=skill_version_id,
        max_context_tokens=max_context_tokens,
        target_runtime_tokens=min(max_context_tokens, 350),
        source_object_type=f"{source.source_kind}_repair_proposal",
        source_object_id=source.source_id,
        compiler_version=f"{CONTEXT_COMPILER_VERSION}.repair",
        require_probe_evidence=True,
        routing_equivalence_evidence=_json_object(
            materialization.get("routing_equivalence_evidence")
        ),
        regression_evidence=_json_object(materialization.get("regression_evidence")),
    )
    if context_result.status != "passed":
        return None
    compiled_skill_md = context_result.compiled.skill_md
    context_compile_run_id = context_result.compile_run["context_compile_run_id"]
    context_artifact_id = context_result.context_artifact["context_artifact_id"]
    context_output_manifest_hash = context_result.compile_run["output_manifest_hash"]
    staged = stage_compiled_skill(
        stores.workspace_root,
        staging_id=uuid4(),
        skill_version_id=skill_version_id,
        slug=slug,
        compiled_skill_md=compiled_skill_md,
        max_context_tokens=max_context_tokens,
        context_compile_run_id=UUID(str(context_compile_run_id)),
        context_artifact_id=UUID(str(context_artifact_id)),
        context_output_manifest_hash=str(context_output_manifest_hash),
    )
    return {
        "workspace_id": workspace_key,
        "policy_approved": True,
        "activation_gate_required": True,
        "evolution_transaction_id": str(transaction_id),
        "manifest_relative_path": staged.manifest_relative_path,
        "repair_execution": {
            "source_kind": source.source_kind,
            "source_id": str(source.source_id),
            "materialization": {
                "mode": "generated_staged_manifest",
                "skill_version_id": str(skill_version_id),
                "slug": staged.slug,
                "manifest_sha256": staged.manifest_sha256,
                "context_compile_run_id": context_compile_run_id,
                "context_artifact_id": context_artifact_id,
                "context_output_manifest_hash": context_output_manifest_hash,
                "scanner_findings": [
                    finding.to_json() for finding in staged.scanner_findings
                ],
            },
        },
    }


def _repair_skillir(
    source: RepairExecutionSource,
    *,
    slug: str,
    materialization: dict[str, Any],
) -> SkillIR:
    skillir = _json_object(materialization.get("skillir"))
    if skillir:
        return SkillIR.model_validate(skillir)
    proposal_kind = (
        _string_value(source.proposal.get("proposal_kind"))
        or _string_value(source.proposal.get("kind"))
        or "repair"
    )
    objectives = _string_list(source.proposal.get("objectives")) or [source.reason]
    acceptance = _json_object(source.proposal.get("acceptance_gate"))
    verification = [
        f"{key}: {value}"
        for key, value in sorted(acceptance.items())
        if isinstance(key, str)
    ] or ["Run the proposal-specific evaluator or drift check before activation."]
    return SkillIR(
        slug=slug,
        name=slug,
        description=(
            f"Stage approved {proposal_kind} repair; use for SkillKernel guarded repair."
        ),
        applicability=[
            f"A SkillKernel repair proposal of type `{proposal_kind}` is approved."
        ],
        inputs=["repair proposal", "source evidence or drift context"],
        preconditions=[
            "materialization.policy_approved is true",
            "writer apply remains activation-gated",
        ],
        steps=objectives,
        outputs=["staged repair candidate manifest"],
        effects=["No active runtime files change until writer.apply succeeds."],
        verification=verification,
        failure_handling=[
            (
                "Fail closed to evaluator or drift recheck when compiler, scanner, "
                "or writer proof is missing."
            )
        ],
        do_not_use_when=[
            "repair proposal is not explicitly policy approved",
            "source lacks a skill version anchor",
        ],
        never=[
            "Do not bypass scanner, evaluator, activation, or rollback gates.",
            "Do not include raw secrets, credentials, or private source content.",
        ],
        evidence_ids=_string_list(source.proposal.get("evidence_ids")),
    )


async def _complete_repair_execution_source(
    stores: WorkerStores,
    *,
    workspace_key: str,
    source: RepairExecutionSource,
    status: str,
    execution: dict[str, Any],
) -> None:
    if source.source_kind == "curation_action" and stores.utility is not None:
        complete = getattr(stores.utility, "complete_repair_action_execution", None)
        if complete is not None:
            await complete(
                workspace_key=workspace_key,
                curation_action_id=source.source_id,
                status=status,
                execution=execution,
            )
    elif source.source_kind == "drift_event" and stores.contracts is not None:
        complete = getattr(stores.contracts, "complete_drift_repair_execution", None)
        if complete is not None:
            await complete(
                workspace_key=workspace_key,
                drift_event_id=source.source_id,
                status="repair_queued" if status == "queued" else status,
                execution=execution,
            )


async def _run_external_skill_scan(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.external_skills is None:
        raise ValueError("external skill store is required for external skill scans")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("external skill scan requires workspace_id")
    roots = stores.external_skill_roots or []
    result = await scan_external_skill_roots(
        stores.external_skills,
        workspace_key=workspace,
        roots=roots,
        source=_payload_str(job.payload, "source") or "workspace-skill-root",
        limit=_payload_int(job.payload, "limit", default=250, minimum=1, maximum=1000),
    )
    return result.to_json()


async def _run_historical_import_discover(
    stores: WorkerStores,
    job: JobRecord,
) -> dict[str, Any]:
    if stores.historical_import is None:
        raise ValueError("historical import store is required for historical discovery")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("historical discovery requires workspace_id")
    roots = stores.historical_import_roots or []
    payload = _payload_dict(job.payload)
    source_allowlist = _payload_string_set(payload.get("source_allowlist"))
    source_denylist = _payload_string_set(payload.get("source_denylist"))
    inventory = await discover_historical_sources(
        stores.historical_import,
        workspace_key=workspace,
        roots=roots,
        source_allowlist=source_allowlist,
        source_denylist=source_denylist,
        max_files=_payload_int(job.payload, "max_files", default=500, minimum=1, maximum=10_000),
        max_bytes=_payload_int(
            job.payload,
            "max_bytes",
            default=25_000_000,
            minimum=1,
            maximum=1_000_000_000,
        ),
        preview_only=bool(payload.get("preview_only", False)),
    )
    return inventory.to_json()


async def _run_external_skill_materialize_import(
    stores: WorkerStores,
    job: JobRecord,
) -> dict[str, Any]:
    if stores.external_skills is None:
        raise ValueError("external skill store is required for external skill import")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("external skill import requires workspace_id")
    external_skill_id = _payload_uuid(job.payload, "external_skill_id")
    if external_skill_id is None:
        raise ValueError("external skill import requires external_skill_id")
    result = await materialize_external_skill_import(
        stores.external_skills,
        workspace_key=workspace,
        external_skill_id=external_skill_id,
        operator_id=_payload_str(job.payload, "operator_id"),
    )
    if not result.allowed:
        raise ValueError("; ".join(result.blockers) or "external skill import blocked")
    return result.to_json()


async def _run_topology_score_broker_trials(
    stores: WorkerStores,
    job: JobRecord,
) -> dict[str, Any]:
    if stores.topology is None:
        raise ValueError("topology store is required for topology broker trial scoring")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("topology broker trial scoring requires workspace_id")
    operation_id = _payload_uuid(job.payload, "skill_graph_operation_id")
    if operation_id is None:
        raise ValueError(
            "topology broker trial scoring requires skill_graph_operation_id"
        )

    result = await stores.topology.record_broker_trial_scores(
        workspace_key=workspace,
        skill_graph_operation_id=operation_id,
        replay_result=_json_object(_payload_dict(job.payload).get("broker_replay")),
        canary_metrics=_json_object(_payload_dict(job.payload).get("broker_canary_metrics")),
        scored_by=job.lease_owner or "autoskill-worker",
    )
    return result.to_json()


async def _run_topology_apply_downstream(
    stores: WorkerStores,
    job: JobRecord,
) -> dict[str, Any]:
    if stores.topology is None:
        raise ValueError("topology store is required for topology downstream apply")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("topology downstream apply requires workspace_id")
    operation_id = _payload_uuid(job.payload, "skill_graph_operation_id")
    if operation_id is None:
        raise ValueError("topology downstream apply requires skill_graph_operation_id")

    result = await stores.topology.apply_downstream_actions(
        workspace_key=workspace,
        skill_graph_operation_id=operation_id,
        applied_by=job.lease_owner or "autoskill-worker",
    )
    if not result.allowed:
        raise ValueError("; ".join(result.blockers) or "topology downstream apply blocked")

    operation = result.operation
    invalidation = await _invalidate_topology_runtime_objects(
        stores,
        workspace_key=workspace,
        operation_id=operation_id,
        skill_ids=(
            [*operation.subject_skill_ids, *operation.output_skill_ids]
            if operation is not None
            else []
        ),
    )
    return {
        **result.to_json(),
        "runtime_invalidation": invalidation,
    }


async def _run_revocations_rollback(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.governance is None:
        raise ValueError("governance store is required for rollback revocations")
    if stores.workspace_root is None or stores.archive_root is None:
        raise ValueError("writer roots are required for rollback revocations")

    limit = _payload_int(job.payload, "limit", default=10, minimum=1, maximum=25)
    workspace = _payload_workspace(job)
    observability = stores.observability or NullObservabilityStore()
    span = await observability.start_span(
        workspace_key=workspace or job.workspace_key or "unknown",
        trace_id=job.trace_id,
        parent_span_id=job.span_id or job.parent_span_id,
        operation_name="revocations.rollback",
        operation_kind="rollback",
        safe_attributes={
            "source": "worker",
            "job_id": str(job.job_id),
            "job_kind": job.job_kind,
            "limit": limit,
        },
        object_refs=[{"object_type": "job", "object_id": str(job.job_id)}],
    )
    try:
        processed: list[dict[str, Any]] = []
        completed = 0
        failed = 0
        for _index in range(limit):
            request = await stores.governance.claim_next_revocation_request(
                workspace_key=workspace,
                request_kind="rollback",
                root_object_type="evolution_transaction",
                worker_id=job.lease_owner,
            )
            if request is None:
                break
            try:
                outcome = await _execute_rollback_revocation(stores, request)
            except Exception as error:
                failed += 1
                summary = request.traversal_summary | {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
                await stores.governance.complete_revocation_request(
                    revocation_request_id=request.revocation_request_id,
                    status="failed",
                    traversal_summary=summary,
                )
                processed.append(
                    {
                        "revocation_request_id": str(request.revocation_request_id),
                        "status": "failed",
                        "error": summary["error"],
                    }
                )
                continue
            completed += 1
            processed.append(outcome)
        output = {
            "scanned": len(processed),
            "completed": completed,
            "failed": failed,
            "revocations": processed,
        }
    except Exception as error:
        await observability.finish_span(
            span_id=span.span_id,
            status="error",
            safe_attributes={"error": f"{type(error).__name__}: {error}"[:500]},
        )
        raise
    await observability.finish_span(
        span_id=span.span_id,
        status="ok",
        safe_attributes={
            "scanned": output["scanned"],
            "completed": output["completed"],
            "failed": output["failed"],
        },
        object_refs=[
            {
                "object_type": "revocation_request",
                "object_id": str(item["revocation_request_id"]),
            }
            for item in processed
            if item.get("revocation_request_id")
        ],
    )
    return output


async def _run_writer_apply(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    observability = stores.observability or NullObservabilityStore()
    workspace = _payload_workspace(job) or job.workspace_key or "unknown"
    span = await observability.start_span(
        workspace_key=workspace,
        trace_id=job.trace_id,
        parent_span_id=job.span_id or job.parent_span_id,
        operation_name="writer.apply",
        operation_kind="writer",
        safe_attributes={
            "source": "worker",
            "job_id": str(job.job_id),
            "job_kind": job.job_kind,
            "policy_approved": bool(_payload_dict(job.payload).get("policy_approved")),
            "activation_gate_required": bool(
                _payload_dict(job.payload).get("activation_gate_required")
            ),
            "has_manifest_relative_path": bool(
                _payload_dict(job.payload).get("manifest_relative_path")
            ),
        },
        object_refs=[{"object_type": "job", "object_id": str(job.job_id)}],
    )
    try:
        if stores.governance is None:
            raise ValueError("governance store is required for writer apply")
        if stores.workspace_root is None or stores.archive_root is None:
            raise ValueError("writer roots are required for writer apply")
        if not bool(_payload_dict(job.payload).get("policy_approved")):
            raise ValueError("writer apply requires explicit policy_approved=true")
        transaction_id = _payload_uuid(job.payload, "evolution_transaction_id")
        manifest_relative_path = _payload_str(job.payload, "manifest_relative_path")
        if transaction_id is None or not manifest_relative_path:
            raise ValueError(
                "writer apply requires evolution_transaction_id and manifest_relative_path"
            )
        memory_influence_ids = await _validate_memory_influence_for_mutation(
            stores,
            workspace_key=workspace,
            memory_ids=_payload_memory_influence_ids(job.payload),
            run_id=f"writer-apply:{job.job_id}",
            control_surface="writer.apply",
            decision_context={
                "job_id": str(job.job_id),
                "evolution_transaction_id": str(transaction_id),
                "has_manifest_relative_path": True,
            },
        )
        staging_root = stores.workspace_root / ".autoskill" / "staging"
        activation_readiness = await _check_writer_activation_gate(
            stores,
            job,
            staging_root=staging_root,
            manifest_relative_path=manifest_relative_path,
        )
        artifact = await apply_staged_manifest_with_governance(
            stores.governance,
            evolution_transaction_id=transaction_id,
            staging_root=staging_root,
            workspace_root=stores.workspace_root,
            archive_root=stores.archive_root,
            manifest_relative_path=manifest_relative_path,
        )
        output = {
            "artifact": artifact.to_json(),
            "policy_approved": True,
            "activation_gate": (
                activation_readiness.to_json() if activation_readiness is not None else None
            ),
        }
        await _record_memory_influence_for_mutation(
            stores,
            workspace_key=workspace,
            memory_ids=memory_influence_ids,
            run_id=f"writer-apply:{job.job_id}",
            decision={
                "control_surface": "writer.apply",
                "decision": "mutation_applied",
                "job_id": str(job.job_id),
                "evolution_transaction_id": str(transaction_id),
                "manifest_sha256": output["artifact"]["manifest_sha256"],
                "active_relative_path": output["artifact"]["active_relative_path"],
            },
        )
    except Exception as error:
        await observability.finish_span(
            span_id=span.span_id,
            status="error",
            safe_attributes={"error": f"{type(error).__name__}: {error}"[:500]},
        )
        raise
    await observability.finish_span(
        span_id=span.span_id,
        status="ok",
        safe_attributes={
            "active_relative_path": output["artifact"]["active_relative_path"],
            "manifest_sha256": output["artifact"]["manifest_sha256"],
            "activation_gate_allowed": (
                output["activation_gate"]["allowed"]
                if output["activation_gate"] is not None
                else None
            ),
        },
        object_refs=[
            {"object_type": "job", "object_id": str(job.job_id)},
            {"object_type": "evolution_transaction", "object_id": str(transaction_id)},
        ],
    )
    return output


async def _check_writer_activation_gate(
    stores: WorkerStores,
    job: JobRecord,
    *,
    staging_root: Path,
    manifest_relative_path: str,
):
    if not bool(_payload_dict(job.payload).get("activation_gate_required")):
        return None
    if stores.activation_gate is None:
        raise ValueError("writer apply activation gate requires activation_gate store")
    workspace = _payload_workspace(job)
    if workspace is None:
        raise ValueError("writer apply activation gate requires workspace_id")
    manifest_path = resolve_contained(staging_root, manifest_relative_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_version_id = _payload_uuid(manifest, "skill_version_id")
    if skill_version_id is None:
        raise ValueError("writer apply activation gate requires manifest skill_version_id")
    context_gate_value = manifest.get("context_gate")
    context_gate = context_gate_value if isinstance(context_gate_value, dict) else {}
    readiness = await stores.activation_gate.check_activation_readiness(
        workspace_key=workspace,
        skill_version_id=skill_version_id,
        executor_profile_id=_payload_uuid(job.payload, "executor_profile_id"),
        require_context_compile_proof=True,
        context_compile_run_id=_payload_uuid(context_gate, "context_compile_run_id"),
        context_artifact_id=_payload_uuid(context_gate, "context_artifact_id"),
        compiled_text_hash=_payload_str(context_gate, "text_hash"),
        context_output_manifest_hash=_payload_str(
            context_gate,
            "context_output_manifest_hash",
        ),
    )
    if not readiness.allowed:
        raise ValueError(
            "writer apply activation gate blocked: " + ", ".join(readiness.blockers)
        )
    return readiness


async def _execute_rollback_revocation(
    stores: WorkerStores,
    request: RevocationRequestRecord,
) -> dict[str, Any]:
    if request.workspace_key is None:
        raise ValueError("revocation request is missing workspace key")
    if request.root_object_type != "evolution_transaction":
        raise ValueError("rollback revocations require an evolution_transaction root")

    rollback_action = await _rollback_action_for_transaction(
        stores.governance,
        request.root_object_id,
    )
    operation = rollback_action.get("operation")
    if operation not in {"restore_archive_manifest", "delete_active_path"}:
        raise ValueError("rollback action is not supported by the mutation worker")
    archive_manifest_relative_path = (
        str(rollback_action["archive_manifest_relative_path"])
        if operation == "restore_archive_manifest"
        else None
    )
    active_relative_path = str(rollback_action.get("active_relative_path") or "")
    started = await stores.governance.start_transaction(
        workspace_key=request.workspace_key,
        transaction_kind="rollback_skill",
        idempotency_key=f"revocation:{request.revocation_request_id}:rollback",
        plan_hash=sha256_json(
            {
                "revocation_request_id": str(request.revocation_request_id),
                "root_object_id": str(request.root_object_id),
                "archive_manifest_relative_path": archive_manifest_relative_path,
                "active_relative_path": active_relative_path,
                "operation": operation,
            }
        ),
        actor="autoskill-mutation-worker",
        cause={
            "source": "revocation_request",
            "revocation_request_id": str(request.revocation_request_id),
            "root_object_type": request.root_object_type,
            "root_object_id": str(request.root_object_id),
        },
        rollback_of_transaction_id=request.root_object_id,
    )
    if operation == "restore_archive_manifest":
        artifact = await rollback_active_skill_with_governance(
            stores.governance,
            evolution_transaction_id=started.transaction.evolution_transaction_id,
            workspace_root=stores.workspace_root,
            archive_root=stores.archive_root,
            archive_manifest_relative_path=str(archive_manifest_relative_path),
        )
        artifact_summary = artifact.to_json()
        active_relative_path = artifact.active_relative_path
    else:
        artifact_summary = await delete_active_skill_with_governance(
            stores.governance,
            evolution_transaction_id=started.transaction.evolution_transaction_id,
            workspace_root=stores.workspace_root,
            active_relative_path=active_relative_path,
        )
    invalidation = await _invalidate_revoked_objects(stores, request)
    summary = request.traversal_summary | {
        "status": "completed",
        "rollback_transaction_id": str(started.transaction.evolution_transaction_id),
        "archive_manifest_relative_path": archive_manifest_relative_path,
        "artifact": artifact_summary,
        "invalidation": invalidation,
    }
    await stores.governance.complete_revocation_request(
        revocation_request_id=request.revocation_request_id,
        status="completed",
        traversal_summary=summary,
    )
    return {
        "revocation_request_id": str(request.revocation_request_id),
        "status": "completed",
        "rollback_transaction_id": str(started.transaction.evolution_transaction_id),
        "active_relative_path": active_relative_path,
        "invalidation": invalidation,
    }


async def _invalidate_topology_runtime_objects(
    stores: WorkerStores,
    *,
    workspace_key: str,
    operation_id: UUID,
    skill_ids: list[UUID],
) -> dict[str, int]:
    objects = [
        {"object_type": "skill_graph_operation", "object_id": str(operation_id)},
        *[
            {"object_type": "skill", "object_id": str(skill_id)}
            for skill_id in sorted(set(skill_ids), key=str)
        ],
    ]
    retrieval_logs_invalidated = 0
    context_records_invalidated = 0
    embeddings_deleted = 0
    if stores.retrieval is not None:
        invalidate_logs = getattr(stores.retrieval, "invalidate_logs", None)
        if invalidate_logs is not None:
            retrieval_logs_invalidated = await invalidate_logs(
                workspace_key=workspace_key,
                objects=objects,
            )
    if stores.context_governance is not None:
        invalidate_context = getattr(stores.context_governance, "invalidate_objects", None)
        if invalidate_context is not None:
            context_records_invalidated = await invalidate_context(
                workspace_key=workspace_key,
                objects=objects,
            )
    invalidate_embeddings = getattr(stores.embeddings, "invalidate_objects", None)
    if invalidate_embeddings is not None:
        embeddings_deleted = await invalidate_embeddings(
            workspace_key=workspace_key,
            objects=objects,
        )
    return {
        "objects": len(objects),
        "retrieval_logs_invalidated": retrieval_logs_invalidated,
        "context_records_invalidated": context_records_invalidated,
        "embeddings_deleted": embeddings_deleted,
    }


async def _rollback_action_for_transaction(
    governance: GovernanceStore,
    evolution_transaction_id: UUID,
) -> dict[str, Any]:
    items = await governance.list_transaction_items(
        evolution_transaction_id=evolution_transaction_id,
    )
    for item in items:
        if item.item_kind != "compiled_skill_file":
            continue
        if item.activation_state != "active":
            continue
        operation = item.rollback_action.get("operation")
        if operation:
            return item.rollback_action
    raise ValueError("no active compiled skill rollback action found")


async def _invalidate_revoked_objects(
    stores: WorkerStores,
    request: RevocationRequestRecord,
) -> dict[str, int]:
    objects = _revocation_impacted_objects(request)
    body_index_deleted = 0
    embeddings_deleted = 0
    retrieval_logs_invalidated = 0
    context_records_invalidated = 0
    topology_records_invalidated = 0
    evaluation_records_invalidated = 0
    attribution_records_invalidated = 0
    governance_records_invalidated = 0
    if request.workspace_key is None or not objects:
        return {
            "objects": len(objects),
            "body_index_documents_deleted": body_index_deleted,
            "embeddings_deleted": embeddings_deleted,
            "retrieval_logs_invalidated": retrieval_logs_invalidated,
            "context_records_invalidated": context_records_invalidated,
            "topology_records_invalidated": topology_records_invalidated,
            "evaluation_records_invalidated": evaluation_records_invalidated,
            "attribution_records_invalidated": attribution_records_invalidated,
            "governance_records_invalidated": governance_records_invalidated,
        }
    invalidate_governance = getattr(stores.governance, "invalidate_objects", None)
    if invalidate_governance is not None:
        governance_records_invalidated = await invalidate_governance(
            workspace_key=request.workspace_key,
            objects=objects,
        )
    if stores.retrieval is not None:
        invalidate = getattr(stores.retrieval, "invalidate_objects", None)
        if invalidate is not None:
            body_index_deleted = await invalidate(
                workspace_key=request.workspace_key,
                objects=objects,
            )
        invalidate_logs = getattr(stores.retrieval, "invalidate_logs", None)
        if invalidate_logs is not None:
            retrieval_logs_invalidated = await invalidate_logs(
                workspace_key=request.workspace_key,
                objects=objects,
            )
    invalidate_embeddings = getattr(stores.embeddings, "invalidate_objects", None)
    if invalidate_embeddings is not None:
        embeddings_deleted = await invalidate_embeddings(
            workspace_key=request.workspace_key,
            objects=objects,
        )
    if stores.context_governance is not None:
        invalidate_context = getattr(stores.context_governance, "invalidate_objects", None)
        if invalidate_context is not None:
            context_records_invalidated = await invalidate_context(
                workspace_key=request.workspace_key,
                objects=objects,
            )
    if stores.topology is not None:
        invalidate_topology = getattr(stores.topology, "invalidate_objects", None)
        if invalidate_topology is not None:
            topology_records_invalidated = await invalidate_topology(
                workspace_key=request.workspace_key,
                objects=objects,
            )
    if stores.evaluations is not None:
        invalidate_evaluations = getattr(stores.evaluations, "invalidate_objects", None)
        if invalidate_evaluations is not None:
            evaluation_records_invalidated = await invalidate_evaluations(
                workspace_key=request.workspace_key,
                objects=objects,
            )
    if stores.attribution is not None:
        invalidate_attribution = getattr(stores.attribution, "invalidate_objects", None)
        if invalidate_attribution is not None:
            attribution_records_invalidated = await invalidate_attribution(
                workspace_key=request.workspace_key,
                objects=objects,
            )
    return {
        "objects": len(objects),
        "body_index_documents_deleted": body_index_deleted,
        "embeddings_deleted": embeddings_deleted,
        "retrieval_logs_invalidated": retrieval_logs_invalidated,
        "context_records_invalidated": context_records_invalidated,
        "topology_records_invalidated": topology_records_invalidated,
        "evaluation_records_invalidated": evaluation_records_invalidated,
        "attribution_records_invalidated": attribution_records_invalidated,
        "governance_records_invalidated": governance_records_invalidated,
    }


def _revocation_impacted_objects(request: RevocationRequestRecord) -> list[dict[str, str]]:
    objects = request.traversal_summary.get("impacted_objects")
    if not isinstance(objects, list):
        return [
            {
                "object_type": request.root_object_type,
                "object_id": str(request.root_object_id),
            }
        ]
    valid: list[dict[str, str]] = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        object_type = item.get("object_type")
        object_id = item.get("object_id")
        if object_type is None or object_id is None:
            continue
        valid.append({"object_type": str(object_type), "object_id": str(object_id)})
    return valid


def _job_kinds_for_pool(pool: WorkerPool) -> list[str]:
    return [
        definition.kind
        for definition in JOB_DEFINITIONS.values()
        if definition.pool == pool
    ]


async def _validate_memory_influence_for_mutation(
    stores: WorkerStores,
    *,
    workspace_key: str,
    memory_ids: list[UUID],
    run_id: str,
    control_surface: str,
    decision_context: dict[str, Any],
) -> list[UUID]:
    deduped = list(dict.fromkeys(memory_ids))[:20]
    if not deduped:
        return []
    if stores.memory_governance is None:
        raise ValueError("memory influence on mutation requires memory governance store")
    for memory_id in deduped:
        record = await stores.memory_governance.get_memory_quarantine(
            workspace_key=workspace_key,
            quarantine_id=memory_id,
        )
        if record is not None and record.status == "approved":
            continue
        status = record.status if record is not None else "missing"
        await stores.memory_governance.record_control_flow_event(
            workspace_key=workspace_key,
            source_kind="memory",
            source_id=memory_id,
            influence_kind="mutation",
            run_id=run_id,
            decision={
                **decision_context,
                "control_surface": control_surface,
                "decision": "blocked_memory_influenced_mutation",
                "memory_status": status,
                "reason_codes": ["memory-influence-not-approved"],
            },
        )
        raise ValueError(
            f"memory-influenced mutation requires approved memory: {memory_id}"
        )
    return deduped


async def _record_memory_influence_for_mutation(
    stores: WorkerStores,
    *,
    workspace_key: str,
    memory_ids: list[UUID],
    run_id: str,
    decision: dict[str, Any],
) -> None:
    if not memory_ids:
        return
    if stores.memory_governance is None:
        raise ValueError("memory influence on mutation requires memory governance store")
    for memory_id in memory_ids:
        await stores.memory_governance.record_control_flow_event(
            workspace_key=workspace_key,
            source_kind="memory",
            source_id=memory_id,
            influence_kind="mutation",
            run_id=run_id,
            decision=decision,
        )


def _payload_memory_influence_ids(payload: dict[str, Any] | str | None) -> list[UUID]:
    source = _payload_dict(payload)
    values = source.get("memory_influence_ids")
    if not isinstance(values, list):
        return []
    memory_ids: list[UUID] = []
    for value in values:
        parsed = _uuid_value(value)
        if parsed is not None:
            memory_ids.append(parsed)
    return memory_ids


def _estimate_context_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _payload_workspace(job: JobRecord) -> str | None:
    return _payload_str(job.payload, "workspace_id") or job.workspace_key


def _payload_dict(payload: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _payload_str(payload: dict[str, Any] | str | None, key: str) -> str | None:
    value = _payload_dict(payload).get(key)
    if value is None:
        return None
    return str(value)


def _payload_string_set(value: object) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return None
    strings = {str(item) for item in values if str(item).strip()}
    return strings or None


def _payload_int(
    payload: dict[str, Any] | str | None,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = _payload_dict(payload).get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _payload_uuid(payload: dict[str, Any] | str | None, key: str) -> UUID | None:
    value = _payload_dict(payload).get(key)
    return _uuid_value(value)


def _uuid_value(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    "evaluations.run": JobDefinition(
        "evaluations.run",
        "maintenance",
        _run_evaluation_proposal_gates,
    ),
    "utility.rollup": JobDefinition(
        "utility.rollup",
        "maintenance",
        _run_utility_rollup,
    ),
    "curation.run": JobDefinition(
        "curation.run",
        "maintenance",
        _run_curation,
    ),
    "usage.aggregate": JobDefinition(
        "usage.aggregate",
        "maintenance",
        _run_usage_aggregate,
    ),
    "contracts.extract": JobDefinition(
        "contracts.extract",
        "maintenance",
        _run_contract_extraction,
    ),
    "drift.check": JobDefinition(
        "drift.check",
        "maintenance",
        _run_drift_checks,
    ),
    "repair.execute": JobDefinition(
        "repair.execute",
        "mutation",
        _run_repair_execute,
    ),
    "external_skills.scan": JobDefinition(
        "external_skills.scan",
        "maintenance",
        _run_external_skill_scan,
    ),
    "external_skills.materialize_import": JobDefinition(
        "external_skills.materialize_import",
        "mutation",
        _run_external_skill_materialize_import,
    ),
    "historical_import.discover": JobDefinition(
        "historical_import.discover",
        "maintenance",
        _run_historical_import_discover,
    ),
    "topology.apply_downstream": JobDefinition(
        "topology.apply_downstream",
        "mutation",
        _run_topology_apply_downstream,
    ),
    "topology.score_broker_trials": JobDefinition(
        "topology.score_broker_trials",
        "mutation",
        _run_topology_score_broker_trials,
    ),
    "revocations.rollback": JobDefinition(
        "revocations.rollback",
        "mutation",
        _run_revocations_rollback,
    ),
    "writer.apply": JobDefinition(
        "writer.apply",
        "mutation",
        _run_writer_apply,
    ),
}
