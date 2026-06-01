from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from autoskill.core.hashing import sha256_json
from autoskill.db.attribution import AttributionStore
from autoskill.db.context import ContextGovernanceStore
from autoskill.db.contracts import ContractStore
from autoskill.db.embeddings import EmbeddingStore
from autoskill.db.evaluations import EvaluationStore
from autoskill.db.evidence import EvidenceStore
from autoskill.db.external_skills import ExternalSkillStore
from autoskill.db.governance import GovernanceStore, RevocationRequestRecord
from autoskill.db.jobs import JobRecord, JobStore
from autoskill.db.observability import NullObservabilityStore, ObservabilityStore
from autoskill.db.retrieval import RetrievalStore
from autoskill.db.scheduler import SchedulerStore
from autoskill.db.topology import TopologyStore
from autoskill.db.utility import UtilityStore
from autoskill.services.embedding_generation import TextEmbedder, generate_pending_embeddings
from autoskill.services.evaluation_runner import run_pending_proposal_gates_with_trace
from autoskill.services.external_inventory import scan_external_skill_roots
from autoskill.services.opportunity import mine_opportunities
from autoskill.services.writer import (
    apply_staged_manifest_with_governance,
    delete_active_skill_with_governance,
    rollback_active_skill_with_governance,
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
    retrieval: RetrievalStore | None = None
    evaluations: EvaluationStore | None = None
    governance: GovernanceStore | None = None
    utility: UtilityStore | None = None
    contracts: ContractStore | None = None
    context_governance: ContextGovernanceStore | None = None
    topology: TopologyStore | None = None
    observability: ObservabilityStore | None = None
    attribution: AttributionStore | None = None
    embedder: TextEmbedder | None = None
    workspace_root: Path | None = None
    archive_root: Path | None = None
    external_skill_roots: list[Path] | None = None


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
    span = await _start_job_span(stores, job, worker_id=worker_id, pool=pool)
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
    result = await stores.utility.run_curation(
        workspace_key=workspace,
        archive_threshold=float(job.payload.get("archive_threshold", -1.0)),
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
            if job.payload.get("active_budget") is None
            else _payload_int(job.payload, "active_budget", default=100, minimum=1, maximum=1000)
        ),
        max_merge=_payload_int(job.payload, "max_merge", default=5, minimum=0, maximum=100),
    )
    return result.to_json()


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


async def _run_revocations_rollback(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.governance is None:
        raise ValueError("governance store is required for rollback revocations")
    if stores.workspace_root is None or stores.archive_root is None:
        raise ValueError("writer roots are required for rollback revocations")

    limit = _payload_int(job.payload, "limit", default=10, minimum=1, maximum=25)
    workspace = _payload_workspace(job)
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
    return {
        "scanned": len(processed),
        "completed": completed,
        "failed": failed,
        "revocations": processed,
    }


async def _run_writer_apply(stores: WorkerStores, job: JobRecord) -> dict[str, Any]:
    if stores.governance is None:
        raise ValueError("governance store is required for writer apply")
    if stores.workspace_root is None or stores.archive_root is None:
        raise ValueError("writer roots are required for writer apply")
    if not bool(job.payload.get("policy_approved")):
        raise ValueError("writer apply requires explicit policy_approved=true")
    transaction_id = _payload_uuid(job.payload, "evolution_transaction_id")
    manifest_relative_path = _payload_str(job.payload, "manifest_relative_path")
    if transaction_id is None or not manifest_relative_path:
        raise ValueError(
            "writer apply requires evolution_transaction_id and manifest_relative_path"
        )
    staging_root = stores.workspace_root / ".autoskill" / "staging"
    artifact = await apply_staged_manifest_with_governance(
        stores.governance,
        evolution_transaction_id=transaction_id,
        staging_root=staging_root,
        workspace_root=stores.workspace_root,
        archive_root=stores.archive_root,
        manifest_relative_path=manifest_relative_path,
    )
    return {
        "artifact": artifact.to_json(),
        "policy_approved": True,
    }


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
        }
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


def _payload_uuid(payload: dict[str, Any], key: str) -> UUID | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


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
    "external_skills.scan": JobDefinition(
        "external_skills.scan",
        "maintenance",
        _run_external_skill_scan,
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
