import asyncio
from dataclasses import dataclass
from uuid import uuid4

from autoskill.api.app import WorkerRunOnceRequest, create_app
from autoskill.db.contracts import ContractExtractResult, DriftCheckResult
from autoskill.db.evaluations import EvaluationRunResult
from autoskill.db.evidence import EvidenceDeriveResult
from autoskill.db.observability import TraceSpanRecord
from autoskill.db.scheduler import SchedulerTickResult
from autoskill.db.utility import CurationRunResult, UtilityRollupResult
from autoskill.services.worker import (
    WorkerLoopConfig,
    WorkerStores,
    build_worker_health,
    run_worker_loop,
    run_worker_once,
)
from autoskill.services.writer import apply_staged_manifest_with_governance, stage_compiled_skill
from autoskill.tests.test_embedding_generation import MemoryPendingEmbeddingStore
from autoskill.tests.test_external_skills import MemoryExternalSkillStore
from autoskill.tests.test_governance import MemoryGovernanceStore
from autoskill.tests.test_jobs_api import MemoryJobStore


class MemoryEvidenceWorkerStore:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.calls: list[dict[str, object]] = []
        self.delay_seconds = delay_seconds

    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
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
        trace_id=None,
        span_id=None,
        parent_span_id=None,
    ) -> EvaluationRunResult:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "limit": limit,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
            }
        )
        return EvaluationRunResult(
            scanned=1,
            evaluated=1,
            blocked=0,
            failed=0,
            needs_intervention=1,
            passed=0,
            evaluations=[],
        )

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "objects": objects,
                "operation": "invalidate_objects",
            }
        )
        return len(objects)


class MemoryInvalidationStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        self.calls.append({"workspace_key": workspace_key, "objects": objects})
        return len(objects)


class MemoryRetrievalInvalidationStore(MemoryInvalidationStore):
    def __init__(self) -> None:
        super().__init__()
        self.log_calls: list[dict[str, object]] = []

    async def invalidate_logs(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        self.log_calls.append({"workspace_key": workspace_key, "objects": objects})
        return len(objects)


class MemoryObservabilityStore:
    def __init__(self) -> None:
        self.started: list[TraceSpanRecord] = []
        self.finished: list[dict[str, object]] = []

    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id=None,
        parent_span_id=None,
        safe_attributes=None,
        object_refs=None,
    ) -> TraceSpanRecord:
        from datetime import UTC, datetime
        from uuid import uuid4

        span = TraceSpanRecord(
            trace_id=trace_id or uuid4(),
            span_id=uuid4(),
            parent_span_id=parent_span_id,
            workspace_id=None,
            workspace_key=workspace_key,
            operation_name=operation_name,
            operation_kind=operation_kind,
            status="running",
            safe_attributes=safe_attributes or {},
            object_refs=object_refs or [],
            started_at=datetime.now(UTC),
            ended_at=None,
        )
        self.started.append(span)
        return span

    async def finish_span(
        self,
        *,
        span_id,
        status="ok",
        safe_attributes=None,
        object_refs=None,
    ) -> TraceSpanRecord | None:
        self.finished.append(
            {
                "span_id": span_id,
                "status": status,
                "safe_attributes": safe_attributes or {},
                "object_refs": object_refs or [],
            }
        )
        return None

    async def link_spans(self, **_kwargs) -> bool:
        return True

    async def list_trace(self, **_kwargs) -> list[TraceSpanRecord]:
        return []


class MemoryUtilityWorkerStore:
    def __init__(self) -> None:
        self.rollup_calls: list[dict[str, object]] = []
        self.curation_calls: list[dict[str, object]] = []

    async def run_utility_rollup(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> UtilityRollupResult:
        self.rollup_calls.append({"workspace_key": workspace_key, "limit": limit})
        return UtilityRollupResult(scanned=1, rollups=[])

    async def run_curation(
        self,
        *,
        workspace_key: str,
        archive_threshold: float = -1.0,
        max_archive: int = 5,
        promotion_min_retrieval: int = 3,
        max_promote: int = 3,
        active_budget: int | None = None,
        max_merge: int = 5,
    ) -> CurationRunResult:
        self.curation_calls.append(
            {
                "workspace_key": workspace_key,
                "archive_threshold": archive_threshold,
                "max_archive": max_archive,
                "promotion_min_retrieval": promotion_min_retrieval,
                "max_promote": max_promote,
                "active_budget": active_budget,
                "max_merge": max_merge,
            }
        )
        return CurationRunResult(
            scanned=2,
            archived=1,
            promoted=1,
            merged=0,
            planned=0,
            actions=[],
        )


class MemoryContractWorkerStore:
    def __init__(self) -> None:
        self.extract_calls: list[dict[str, object]] = []
        self.drift_calls: list[dict[str, object]] = []

    async def extract_contracts(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> ContractExtractResult:
        self.extract_calls.append({"workspace_key": workspace_key, "limit": limit})
        return ContractExtractResult(scanned_versions=1, extracted=2)

    async def run_drift_checks(
        self,
        *,
        workspace_key: str,
        limit: int = 250,
    ) -> DriftCheckResult:
        self.drift_calls.append({"workspace_key": workspace_key, "limit": limit})
        return DriftCheckResult(scanned=2, valid=1, violated=1, unknown=0, events=[])


@dataclass
class WorkerTestStores:
    jobs: MemoryJobStore
    scheduler: MemorySchedulerWorkerStore
    evidence: MemoryEvidenceWorkerStore
    embeddings: MemoryPendingEmbeddingStore
    evaluations: MemoryEvaluationWorkerStore | None = None
    observability: MemoryObservabilityStore | None = None

    def as_worker_stores(self) -> WorkerStores:
        return WorkerStores(
            jobs=self.jobs,
            scheduler=self.scheduler,
            evidence=self.evidence,
            embeddings=self.embeddings,
            evaluations=self.evaluations,
            observability=self.observability,
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


def test_worker_run_once_records_trace_span_for_job_execution() -> None:
    jobs = MemoryJobStore()
    observability = MemoryObservabilityStore()

    async def run():
        enqueued = await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:traced",
            payload={"workspace_id": "dev-01", "limit": 3},
        )
        result = await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=MemoryPendingEmbeddingStore(),
                observability=observability,
            ),
            worker_id="worker-1",
            pool="maintenance",
        )
        return enqueued.job, result

    job, result = asyncio.run(run())

    assert result.status == "succeeded"
    assert len(observability.started) == 1
    span = observability.started[0]
    assert span.trace_id == job.trace_id
    assert span.parent_span_id == job.span_id
    assert span.operation_name == "evidence.derive"
    assert span.operation_kind == "job"
    assert span.safe_attributes["job_id"] == str(job.job_id)
    assert span.safe_attributes["worker_id"] == "worker-1"
    assert observability.finished == [
        {
            "span_id": span.span_id,
            "status": "ok",
            "safe_attributes": {"output_keys": ["created", "duplicate", "evidence_ids", "scanned"]},
            "object_refs": [],
        }
    ]


def test_worker_run_once_records_error_trace_span() -> None:
    jobs = MemoryJobStore()
    observability = MemoryObservabilityStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="writer.apply",
            idempotency_key="writer-apply:traced-error",
            max_attempts=1,
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=MemoryPendingEmbeddingStore(),
                governance=MemoryGovernanceStore(),
                observability=observability,
            ),
            worker_id="worker-1",
            pool="mutation",
        )

    result = asyncio.run(run())

    assert result.status == "failed"
    assert len(observability.started) == 1
    assert observability.started[0].operation_name == "writer.apply"
    assert observability.finished[0]["status"] == "error"
    assert "writer roots are required" in observability.finished[0]["safe_attributes"]["error"]


def test_worker_run_once_renews_lease_while_handler_runs() -> None:
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(delay_seconds=0.6),
        embeddings=MemoryPendingEmbeddingStore(),
    )

    async def run():
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evidence.derive",
            idempotency_key="derive:slow",
        )
        return await run_worker_once(
            stores.as_worker_stores(),
            worker_id="worker-1",
            pool="maintenance",
            lease_seconds=1,
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert stores.jobs.renewals
    assert stores.jobs.renewals[0]["worker_id"] == "worker-1"


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
    assert stores.jobs.heartbeats["loop-worker"].status == "idle"
    assert stores.jobs.heartbeats["loop-worker"].summary["claimed"] == 2


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
        await jobs.record_worker_heartbeat(
            worker_id="maintenance-1",
            pool="maintenance",
            concurrency=2,
            status="running",
            summary={"claimed": 3},
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
    assert health["workers"][0]["worker_id"] == "maintenance-1"
    assert health["workers"][0]["summary"] == {"claimed": 3}


def test_mutation_worker_rolls_back_queued_revocation_request(tmp_path) -> None:
    jobs = MemoryJobStore()
    governance = MemoryGovernanceStore()
    retrieval = MemoryInvalidationStore()
    embeddings = MemoryInvalidationStore()
    workspace_root = tmp_path / "workspace"
    staging_root = workspace_root / ".autoskill" / "staging"
    archive_root = workspace_root / ".autoskill" / "archive"
    active_root = workspace_root / "skills" / "autoskill" / "canary-skill"
    active_root.mkdir(parents=True)
    (active_root / "SKILL.md").write_text("WHEN old\nDO stable behavior\n", encoding="utf-8")

    async def run():
        apply_transaction = await governance.start_transaction(
            workspace_key="dev-01",
            transaction_kind="compile",
            idempotency_key="apply:canary-skill",
            plan_hash="apply-plan",
        )
        staged = stage_compiled_skill(
            staging_root,
            staging_id=uuid4(),
            skill_version_id=uuid4(),
            slug="canary-skill",
            compiled_skill_md="WHEN new\nDO regressed behavior\n",
        )
        await apply_staged_manifest_with_governance(
            governance,
            evolution_transaction_id=apply_transaction.transaction.evolution_transaction_id,
            staging_root=staging_root,
            workspace_root=workspace_root,
            archive_root=archive_root,
            manifest_relative_path=staged.manifest_relative_path,
        )
        revocation = await governance.request_revocation(
            workspace_key="dev-01",
            request_kind="rollback",
            root_object_type="evolution_transaction",
            root_object_id=apply_transaction.transaction.evolution_transaction_id,
            traversal_summary={
                "source": "critical_canary",
                "impacted_objects": [
                    {
                        "object_type": "skill_version",
                        "object_id": str(staged.skill_version_id),
                    }
                ],
            },
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="revocations.rollback",
            idempotency_key="rollback:canary-skill",
            payload={"workspace_id": "dev-01"},
        )
        result = await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=embeddings,
                retrieval=retrieval,
                governance=governance,
                workspace_root=workspace_root,
                archive_root=archive_root,
            ),
            worker_id="mutation-worker",
            pool="mutation",
        )
        return result, revocation

    result, revocation = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["completed"] == 1
    assert (active_root / "SKILL.md").read_text(encoding="utf-8") == (
        "WHEN old\nDO stable behavior\n"
    )
    completed = next(
        request
        for request in governance.revocations
        if request.revocation_request_id == revocation.revocation_request_id
    )
    assert completed.status == "completed"
    assert completed.traversal_summary["source"] == "critical_canary"
    assert "rollback_transaction_id" in completed.traversal_summary
    assert completed.traversal_summary["invalidation"] == {
        "objects": 1,
        "body_index_documents_deleted": 1,
        "embeddings_deleted": 1,
        "retrieval_logs_invalidated": 0,
        "context_records_invalidated": 0,
        "topology_records_invalidated": 0,
        "evaluation_records_invalidated": 0,
    }
    assert retrieval.calls == embeddings.calls
    assert retrieval.calls[0]["workspace_key"] == "dev-01"


def test_mutation_worker_deletes_initial_create_on_rollback(tmp_path) -> None:
    jobs = MemoryJobStore()
    governance = MemoryGovernanceStore()
    retrieval = MemoryInvalidationStore()
    embeddings = MemoryInvalidationStore()
    workspace_root = tmp_path / "workspace"
    staging_root = workspace_root / ".autoskill" / "staging"
    archive_root = workspace_root / ".autoskill" / "archive"
    active_root = workspace_root / "skills" / "autoskill" / "new-skill"

    async def run():
        apply_transaction = await governance.start_transaction(
            workspace_key="dev-01",
            transaction_kind="compile",
            idempotency_key="apply:new-skill",
            plan_hash="apply-plan",
        )
        staged = stage_compiled_skill(
            staging_root,
            staging_id=uuid4(),
            skill_version_id=uuid4(),
            slug="new-skill",
            compiled_skill_md="WHEN new\nDO useful behavior\n",
        )
        await apply_staged_manifest_with_governance(
            governance,
            evolution_transaction_id=apply_transaction.transaction.evolution_transaction_id,
            staging_root=staging_root,
            workspace_root=workspace_root,
            archive_root=archive_root,
            manifest_relative_path=staged.manifest_relative_path,
        )
        revocation = await governance.request_revocation(
            workspace_key="dev-01",
            request_kind="rollback",
            root_object_type="evolution_transaction",
            root_object_id=apply_transaction.transaction.evolution_transaction_id,
            traversal_summary={
                "impacted_objects": [
                    {
                        "object_type": "skill_version",
                        "object_id": str(staged.skill_version_id),
                    }
                ],
            },
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="revocations.rollback",
            idempotency_key="rollback:new-skill",
            payload={"workspace_id": "dev-01"},
        )
        result = await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=embeddings,
                retrieval=retrieval,
                governance=governance,
                workspace_root=workspace_root,
                archive_root=archive_root,
            ),
            worker_id="mutation-worker",
            pool="mutation",
        )
        return result, revocation

    result, revocation = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["completed"] == 1
    assert not active_root.exists()
    completed = next(
        request
        for request in governance.revocations
        if request.revocation_request_id == revocation.revocation_request_id
    )
    assert completed.status == "completed"
    assert completed.traversal_summary["artifact"]["operation"] == "delete_active_path"
    assert completed.traversal_summary["invalidation"] == {
        "objects": 1,
        "body_index_documents_deleted": 1,
        "embeddings_deleted": 1,
        "retrieval_logs_invalidated": 0,
        "context_records_invalidated": 0,
        "topology_records_invalidated": 0,
        "evaluation_records_invalidated": 0,
    }


def test_mutation_worker_invalidates_retrieval_logs_and_context_records(tmp_path) -> None:
    jobs = MemoryJobStore()
    governance = MemoryGovernanceStore()
    retrieval = MemoryRetrievalInvalidationStore()
    embeddings = MemoryInvalidationStore()
    context = MemoryInvalidationStore()
    topology = MemoryInvalidationStore()
    evaluations = MemoryEvaluationWorkerStore()
    workspace_root = tmp_path / "workspace"
    staging_root = workspace_root / ".autoskill" / "staging"
    archive_root = workspace_root / ".autoskill" / "archive"

    async def run():
        apply_transaction = await governance.start_transaction(
            workspace_key="dev-01",
            transaction_kind="compile",
            idempotency_key="apply:derived-state",
            plan_hash="apply-plan",
        )
        staged = stage_compiled_skill(
            staging_root,
            staging_id=uuid4(),
            skill_version_id=uuid4(),
            slug="derived-state-skill",
            compiled_skill_md="WHEN new\nDO useful behavior\n",
        )
        await apply_staged_manifest_with_governance(
            governance,
            evolution_transaction_id=apply_transaction.transaction.evolution_transaction_id,
            staging_root=staging_root,
            workspace_root=workspace_root,
            archive_root=archive_root,
            manifest_relative_path=staged.manifest_relative_path,
        )
        await governance.request_revocation(
            workspace_key="dev-01",
            request_kind="rollback",
            root_object_type="evolution_transaction",
            root_object_id=apply_transaction.transaction.evolution_transaction_id,
            traversal_summary={
                "impacted_objects": [
                    {
                        "object_type": "skill_version",
                        "object_id": str(staged.skill_version_id),
                    },
                    {
                        "object_type": "context_artifact",
                        "object_id": str(uuid4()),
                    },
                    {
                        "object_type": "skill_graph_operation",
                        "object_id": str(uuid4()),
                    },
                    {
                        "object_type": "planned_topology_trial",
                        "object_id": str(uuid4()),
                    },
                ],
            },
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="revocations.rollback",
            idempotency_key="rollback:derived-state",
            payload={"workspace_id": "dev-01"},
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=embeddings,
                retrieval=retrieval,
                governance=governance,
                evaluations=evaluations,
                context_governance=context,
                topology=topology,
                workspace_root=workspace_root,
                archive_root=archive_root,
            ),
            worker_id="mutation-worker",
            pool="mutation",
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["revocations"][0]["invalidation"] == {
        "objects": 4,
        "body_index_documents_deleted": 4,
        "embeddings_deleted": 4,
        "retrieval_logs_invalidated": 4,
        "context_records_invalidated": 4,
        "topology_records_invalidated": 4,
        "evaluation_records_invalidated": 4,
    }
    assert retrieval.log_calls[0]["workspace_key"] == "dev-01"
    assert context.calls[0]["workspace_key"] == "dev-01"
    assert topology.calls[0]["workspace_key"] == "dev-01"
    assert evaluations.calls[0]["operation"] == "invalidate_objects"


def test_mutation_worker_applies_staged_manifest_when_policy_approved(tmp_path) -> None:
    jobs = MemoryJobStore()
    governance = MemoryGovernanceStore()
    workspace_root = tmp_path / "workspace"
    staging_root = workspace_root / ".autoskill" / "staging"
    archive_root = workspace_root / ".autoskill" / "archive"
    active_root = workspace_root / "skills" / "autoskill" / "approved-skill"

    async def run():
        transaction = await governance.start_transaction(
            workspace_key="dev-01",
            transaction_kind="compile",
            idempotency_key="apply:approved-skill",
            plan_hash="apply-plan",
        )
        staged = stage_compiled_skill(
            staging_root,
            staging_id=uuid4(),
            skill_version_id=uuid4(),
            slug="approved-skill",
            compiled_skill_md="WHEN approved\nDO safe behavior\n",
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="writer.apply",
            idempotency_key="writer-apply:approved-skill",
            payload={
                "policy_approved": True,
                "evolution_transaction_id": str(transaction.transaction.evolution_transaction_id),
                "manifest_relative_path": staged.manifest_relative_path,
            },
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=MemoryPendingEmbeddingStore(),
                governance=governance,
                workspace_root=workspace_root,
                archive_root=archive_root,
            ),
            worker_id="mutation-worker",
            pool="mutation",
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["policy_approved"] is True
    assert result.output["artifact"]["active_relative_path"] == "skills/autoskill/approved-skill"
    assert (active_root / "SKILL.md").read_text(encoding="utf-8") == (
        "WHEN approved\nDO safe behavior\n"
    )


def test_mutation_worker_apply_fails_closed_without_policy_approval(tmp_path) -> None:
    jobs = MemoryJobStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="writer.apply",
            idempotency_key="writer-apply:blocked",
            payload={},
            max_attempts=1,
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                embeddings=MemoryPendingEmbeddingStore(),
                governance=MemoryGovernanceStore(),
                workspace_root=tmp_path / "workspace",
                archive_root=tmp_path / "workspace" / ".autoskill" / "archive",
            ),
            worker_id="mutation-worker",
            pool="mutation",
        )

    result = asyncio.run(run())

    assert result.status == "failed"
    assert "policy_approved=true" in result.error


def test_worker_run_once_dispatches_evaluation_job() -> None:
    evaluations = MemoryEvaluationWorkerStore()
    observability = MemoryObservabilityStore()
    stores = WorkerTestStores(
        jobs=MemoryJobStore(),
        scheduler=MemorySchedulerWorkerStore(),
        evidence=MemoryEvidenceWorkerStore(),
        embeddings=MemoryPendingEmbeddingStore(),
        evaluations=evaluations,
        observability=observability,
    )
    trace_id = uuid4()
    span_id = uuid4()

    async def run():
        await stores.jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="evaluations.run",
            idempotency_key="eval:one",
            payload={"workspace_id": "dev-01", "limit": 7},
            trace_id=trace_id,
            span_id=span_id,
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
    assert [span.operation_kind for span in observability.started] == ["job", "evaluator"]
    assert observability.started[1].trace_id == trace_id
    assert observability.started[1].parent_span_id == span_id
    assert evaluations.calls == [
        {
            "workspace_key": "dev-01",
            "limit": 7,
            "trace_id": trace_id,
            "span_id": observability.started[1].span_id,
            "parent_span_id": span_id,
        }
    ]
    assert observability.started[1].safe_attributes["source"] == "worker"
    assert observability.started[1].safe_attributes["job_kind"] == "evaluations.run"
    assert observability.finished[0]["status"] == "ok"
    assert observability.finished[0]["safe_attributes"]["needs_intervention"] == 1


def test_worker_run_once_dispatches_external_skill_scan(tmp_path) -> None:
    root = tmp_path / "external-skills"
    skill_dir = root / "pdf-table-cleanup"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: PDF table cleanup\n---\n\n## WHEN\n- Tables need cleanup.\n",
        encoding="utf-8",
    )
    jobs = MemoryJobStore()
    external_skills = MemoryExternalSkillStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="external_skills.scan",
            idempotency_key="external-scan:one",
            payload={"workspace_id": "dev-01", "source": "test-root"},
        )
        return await run_worker_once(
            WorkerStores(
                jobs=jobs,
                scheduler=MemorySchedulerWorkerStore(),
                evidence=MemoryEvidenceWorkerStore(),
                external_skills=external_skills,
                embeddings=MemoryPendingEmbeddingStore(),
                external_skill_roots=[root],
            ),
            worker_id="worker-1",
            pool="maintenance",
        )

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["discovered"] == 1
    assert external_skills.upserts[0]["workspace_key"] == "dev-01"
    assert external_skills.records[0].slug == "pdf-table-cleanup"
    assert str(root) not in str(external_skills.records[0].to_json())


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


def test_worker_dispatches_utility_and_curation_jobs() -> None:
    jobs = MemoryJobStore()
    utility = MemoryUtilityWorkerStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="utility.rollup",
            idempotency_key="utility:one",
            payload={"workspace_id": "dev-01", "limit": 17},
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="curation.run",
            idempotency_key="curation:one",
            payload={
                "workspace_id": "dev-01",
                "archive_threshold": -2.5,
                "max_archive": 3,
                "promotion_min_retrieval": 4,
                "max_promote": 2,
                "active_budget": 12,
                "max_merge": 1,
            },
        )
        stores = WorkerStores(
            jobs=jobs,
            scheduler=MemorySchedulerWorkerStore(),
            evidence=MemoryEvidenceWorkerStore(),
            embeddings=MemoryPendingEmbeddingStore(),
            utility=utility,
        )
        first = await run_worker_once(stores, worker_id="worker-1", pool="maintenance")
        second = await run_worker_once(stores, worker_id="worker-1", pool="maintenance")
        return first, second

    first, second = asyncio.run(run())

    assert first.status == "succeeded"
    assert first.output["scanned"] == 1
    assert second.status == "succeeded"
    assert second.output["archived"] == 1
    assert second.output["promoted"] == 1
    assert utility.rollup_calls == [{"workspace_key": "dev-01", "limit": 17}]
    assert utility.curation_calls == [
        {
            "workspace_key": "dev-01",
            "archive_threshold": -2.5,
            "max_archive": 3,
            "promotion_min_retrieval": 4,
            "max_promote": 2,
            "active_budget": 12,
            "max_merge": 1,
        }
    ]


def test_worker_dispatches_contract_and_drift_jobs() -> None:
    jobs = MemoryJobStore()
    contracts = MemoryContractWorkerStore()

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="contracts.extract",
            idempotency_key="contracts:one",
            payload={"workspace_id": "dev-01", "limit": 11},
        )
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="drift.check",
            idempotency_key="drift:one",
            payload={"workspace_id": "dev-01", "limit": 13},
        )
        stores = WorkerStores(
            jobs=jobs,
            scheduler=MemorySchedulerWorkerStore(),
            evidence=MemoryEvidenceWorkerStore(),
            embeddings=MemoryPendingEmbeddingStore(),
            contracts=contracts,
        )
        first = await run_worker_once(stores, worker_id="worker-1", pool="maintenance")
        second = await run_worker_once(stores, worker_id="worker-1", pool="maintenance")
        return first, second

    first, second = asyncio.run(run())

    assert first.status == "succeeded"
    assert first.output == {"scanned_versions": 1, "extracted": 2}
    assert second.status == "succeeded"
    assert second.output["violated"] == 1
    assert contracts.extract_calls == [{"workspace_key": "dev-01", "limit": 11}]
    assert contracts.drift_calls == [{"workspace_key": "dev-01", "limit": 13}]
