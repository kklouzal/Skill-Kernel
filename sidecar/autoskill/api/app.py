from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from hmac import compare_digest
from pathlib import Path
from typing import Annotated
from uuid import UUID

from autoskill import __version__
from autoskill.core.config import get_settings
from autoskill.core.events import IngestRequest, IngestResult
from autoskill.core.hashing import sha256_text
from autoskill.db.attribution import AsyncpgAttributionStore, AttributionStore, NullAttributionStore
from autoskill.db.audit import AsyncpgAuditStore, AuditStore, NullAuditStore
from autoskill.db.candidates import AsyncpgCandidateStore, CandidateStore, NullCandidateStore
from autoskill.db.contracts import AsyncpgContractStore, ContractStore, NullContractStore
from autoskill.db.embeddings import AsyncpgEmbeddingStore, EmbeddingStore, NullEmbeddingStore
from autoskill.db.evaluations import AsyncpgEvaluationStore, EvaluationStore, NullEvaluationStore
from autoskill.db.events import AsyncpgEventStore, EventStore, NullEventStore
from autoskill.db.evidence import AsyncpgEvidenceStore, EvidenceStore, NullEvidenceStore
from autoskill.db.governance import AsyncpgGovernanceStore, GovernanceStore, NullGovernanceStore
from autoskill.db.jobs import AsyncpgJobStore, JobStore, NullJobStore
from autoskill.db.lifecycle import AsyncpgLifecycleStore, LifecycleStore, NullLifecycleStore
from autoskill.db.retrieval import AsyncpgRetrievalStore, NullRetrievalStore, RetrievalStore
from autoskill.db.scheduler import AsyncpgSchedulerStore, NullSchedulerStore, SchedulerStore
from autoskill.db.skills import AsyncpgSkillStore, NullSkillStore, SkillStore
from autoskill.db.utility import AsyncpgUtilityStore, NullUtilityStore, UtilityStore
from autoskill.services.broker import (
    ContextHintCache,
    ContextHintRequest,
    ContextHintResponse,
    bootstrap_context_hint,
    build_context_hint,
)
from autoskill.services.candidates import propose_candidate_skills
from autoskill.services.embedding_generation import (
    build_text_embedder_from_settings,
    generate_pending_embeddings,
)
from autoskill.services.matching import SkillMatchRequest, match_existing_skills
from autoskill.services.opportunity import mine_opportunities
from autoskill.services.shadowing import detect_shadowing_events
from autoskill.services.worker import (
    WorkerRunResult,
    WorkerStores,
    build_worker_health,
    run_worker_once,
)
from autoskill.services.writer import (
    apply_staged_manifest_with_governance,
    rollback_active_skill_with_governance,
)
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class StatusResponse(BaseModel):
    mode: str
    database_configured: bool
    ingest_auth_configured: bool
    control_auth_configured: bool
    runtime_context_broker: dict[str, object]
    jobs: dict[str, int]
    workers: dict[str, object]


class JobEnqueueRequest(BaseModel):
    workspace_id: str
    job_kind: str
    idempotency_key: str
    payload: dict[str, object] = {}
    priority: int = 100
    max_attempts: int = 5


class JobEnqueueResponse(BaseModel):
    created: bool
    job: dict[str, object]


class JobClaimRequest(BaseModel):
    worker_id: str
    lease_seconds: int = 300
    job_kinds: list[str] | None = None


class JobClaimResponse(BaseModel):
    job: dict[str, object] | None


class JobCompleteRequest(BaseModel):
    worker_id: str
    status: str
    error: str | None = None


class ScheduleUpsertRequest(BaseModel):
    workspace_id: str
    name: str
    job_kind: str
    interval_seconds: int
    next_run_at: str
    payload: dict[str, object] = {}
    enabled: bool = True


class ScheduleUpsertResponse(BaseModel):
    created: bool
    schedule: dict[str, object]


class SchedulerTickResponse(BaseModel):
    due: int
    enqueued: int
    jobs: list[dict[str, object]]


class WorkerRunOnceRequest(BaseModel):
    worker_id: str
    pool: str = "maintenance"
    lease_seconds: int = 300


class WorkerRunOnceResponse(BaseModel):
    claimed: bool
    job: dict[str, object] | None
    status: str
    output: dict[str, object] | None = None
    error: str | None = None


class WorkerHealthResponse(BaseModel):
    pools: list[dict[str, object]]
    jobs_by_status: dict[str, int]
    jobs_by_kind: dict[str, dict[str, int]]
    jobs_by_pool: dict[str, dict[str, int]]
    workers: list[dict[str, object]]


class SkillListResponse(BaseModel):
    skills: list[dict[str, object]]


class AuditRecentResponse(BaseModel):
    audit: list[dict[str, object]]
    chain_valid: bool


class EvidenceDeriveRequest(BaseModel):
    workspace_id: str | None = None
    limit: int = 100


class EvidenceDeriveResponse(BaseModel):
    scanned: int
    created: int
    duplicate: int
    evidence: list[dict[str, object]]


class OpportunityMineRequest(BaseModel):
    workspace_id: str
    limit: int = 100
    min_support: int = 2


class OpportunityMineResponse(BaseModel):
    scanned: int
    candidates: list[dict[str, object]]


class CandidateProposalRequest(BaseModel):
    workspace_id: str
    limit: int = 100
    min_support: int = 2
    persist: bool = True
    evolution_transaction_id: UUID | None = None


class CandidateProposalResponse(BaseModel):
    scanned: int
    proposed: int
    skipped: int
    proposals: list[dict[str, object]]
    persistence: dict[str, object] | None = None


class EvaluationRunRequest(BaseModel):
    workspace_id: str | None = None
    limit: int = 50


class EvaluationRunResponse(BaseModel):
    scanned: int
    evaluated: int
    blocked: int
    failed: int
    needs_intervention: int
    passed: int
    evaluations: list[dict[str, object]]


class UtilityRollupRequest(BaseModel):
    workspace_id: str
    limit: int = 250


class UtilityRollupResponse(BaseModel):
    scanned: int
    rollups: list[dict[str, object]]


class CurationRunRequest(BaseModel):
    workspace_id: str
    archive_threshold: float = -1.0
    max_archive: int = 5
    promotion_min_retrieval: int = 3
    max_promote: int = 3
    active_budget: int | None = None
    max_merge: int = 5


class CurationRunResponse(BaseModel):
    scanned: int
    archived: int
    promoted: int
    merged: int
    actions: list[dict[str, object]]


class ContractExtractRequest(BaseModel):
    workspace_id: str
    limit: int = 250


class ContractExtractResponse(BaseModel):
    scanned_versions: int
    extracted: int


class DriftCheckRequest(BaseModel):
    workspace_id: str
    limit: int = 250


class DriftCheckResponse(BaseModel):
    scanned: int
    valid: int
    violated: int
    unknown: int
    events: list[dict[str, object]]


class EvolutionTransactionStartRequest(BaseModel):
    workspace_id: str
    transaction_kind: str
    idempotency_key: str
    plan_hash: str
    actor: str = "autoskill-sidecar"
    cause: dict[str, object] = {}
    source_evidence_ids: list[UUID] = []
    source_memory_ids: list[UUID] = []
    policy_snapshot: dict[str, object] = {}
    rollback_of_transaction_id: UUID | None = None


class EvolutionTransactionStartResponse(BaseModel):
    created: bool
    transaction: dict[str, object]


class EvolutionTransactionStatusRequest(BaseModel):
    status: str
    metrics: dict[str, object] = {}


class EvolutionTransactionStatusResponse(BaseModel):
    transaction: dict[str, object] | None


class EvolutionTransactionItemRequest(BaseModel):
    item_kind: str
    activation_state: str
    item_id: UUID | None = None
    relative_path: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    rollback_action: dict[str, object] = {}


class EvolutionTransactionItemResponse(BaseModel):
    item: dict[str, object]


class WriterApplyRequest(BaseModel):
    evolution_transaction_id: UUID
    manifest_relative_path: str


class WriterRollbackRequest(BaseModel):
    evolution_transaction_id: UUID
    archive_manifest_relative_path: str


class WriterArtifactResponse(BaseModel):
    artifact: dict[str, object]


class ProvenanceEdgeCreateRequest(BaseModel):
    workspace_id: str
    source_kind: str
    source_id: UUID
    derived_kind: str
    derived_id: UUID
    relation: str


class ProvenanceEdgeCreateResponse(BaseModel):
    created: bool
    edge: dict[str, object]


class RevocationTraversalPreviewRequest(BaseModel):
    workspace_id: str
    root_object_type: str
    root_object_id: UUID
    max_depth: int = 8
    max_nodes: int = 500


class RevocationTraversalPreviewResponse(BaseModel):
    traversal: dict[str, object]


class RevocationRequestCreateRequest(BaseModel):
    workspace_id: str
    request_kind: str
    root_object_type: str
    root_object_id: UUID
    traversal_summary: dict[str, object] = {}
    created_by_job_id: UUID | None = None


class RevocationRequestCreateResponse(BaseModel):
    revocation: dict[str, object]


class CanaryResultRequest(BaseModel):
    workspace_id: str
    skill_id: UUID
    status: str
    critical: bool = False
    reason: str | None = None
    metrics: dict[str, object] = {}
    skill_version_id: UUID | None = None
    evolution_transaction_id: UUID | None = None


class CanaryResultResponse(BaseModel):
    canary: dict[str, object]
    skill: dict[str, object] | None
    revocation: dict[str, object] | None = None


class FreezeSkillRequest(BaseModel):
    workspace_id: str
    skill_id: UUID
    reason: str
    evolution_transaction_id: UUID | None = None


class UnfreezeSkillRequest(BaseModel):
    workspace_id: str
    skill_id: UUID
    target_state: str = "candidate"
    reason: str | None = None
    evolution_transaction_id: UUID | None = None


class SkillLifecycleResponse(BaseModel):
    skill: dict[str, object] | None


class ShadowingDetectRequest(BaseModel):
    workspace_id: str
    limit: int = 100


class ShadowingDetectResponse(BaseModel):
    scanned: int
    detected: int
    events: list[dict[str, object]]


class RetrievalQueryRequest(BaseModel):
    workspace_id: str
    query: str
    session_id: str | None = None
    turn_id: str | None = None
    limit: int = 10


class RetrievalQueryResponse(BaseModel):
    retrieval_log_id: str | None
    decision: str
    candidates: list[dict[str, object]]


class SkillMatchApiRequest(BaseModel):
    workspace_id: str
    candidate_slug: str
    candidate_description: str
    candidate_runtime_text: str = ""
    limit: int = 10


class SkillMatchApiResponse(BaseModel):
    decision: str
    retrieval_log_id: str | None
    active_matches: list[dict[str, object]]
    archived_matches: list[dict[str, object]]


def _candidate_transaction_idempotency_key(
    *,
    workspace_key: str,
    proposals: list[dict[str, object]],
) -> str:
    plan_hash = _candidate_transaction_plan_hash(
        workspace_key=workspace_key,
        proposals=proposals,
    )
    return f"candidate-proposal:{plan_hash}"


def _candidate_transaction_plan_hash(
    *,
    workspace_key: str,
    proposals: list[dict[str, object]],
) -> str:
    payload = {
        "workspace_key": workspace_key,
        "transaction_kind": "candidate_proposal",
        "proposals": [
            {
                "candidate_slug": proposal.get("candidate_slug"),
                "compiled_sha256": proposal.get("compiled_sha256"),
                "evidence_ids": proposal.get("evidence_ids", []),
                "recommendation": proposal.get("recommendation"),
            }
            for proposal in proposals
            if proposal.get("skillir") is not None
        ],
    }
    return sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _candidate_source_evidence_ids(
    proposals: list[dict[str, object]],
) -> list[UUID]:
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for proposal in proposals:
        evidence_ids = proposal.get("evidence_ids", [])
        if not isinstance(evidence_ids, list):
            continue
        for evidence_id in evidence_ids:
            if not isinstance(evidence_id, str):
                continue
            try:
                parsed = UUID(evidence_id)
            except ValueError:
                continue
            if parsed in seen:
                continue
            seen.add(parsed)
            ordered.append(parsed)
    return ordered


class EmbeddingUpsertRequest(BaseModel):
    workspace_id: str
    object_type: str
    object_id: UUID
    embedding_model: str
    embedding: list[float]
    text: str
    skill_id: UUID | None = None


class EmbeddingUpsertResponse(BaseModel):
    created: bool
    embedding: dict[str, object]


class EmbeddingSearchRequest(BaseModel):
    workspace_id: str
    embedding_model: str
    embedding: list[float]
    object_type: str | None = None
    limit: int = 10


class EmbeddingSearchResponse(BaseModel):
    candidates: list[dict[str, object]]


class EmbeddingRecallAuditRequest(BaseModel):
    workspace_id: str
    embedding_model: str = "autoskill-hash-embedding"
    object_type: str | None = None
    sample_size: int = 10
    k: int = 10
    min_recall: float = 0.95


class EmbeddingRecallAuditResponse(BaseModel):
    sampled: int
    k: int
    min_recall: float
    avg_recall: float
    failures: list[dict[str, object]]


class EmbeddingGenerateRequest(BaseModel):
    workspace_id: str | None = None
    embedding_model: str | None = None
    limit: int = 100


class EmbeddingGenerateResponse(BaseModel):
    scanned: int
    generated: int
    created: int
    updated: int
    embedding_model: str
    sources: list[dict[str, object]]


def _build_event_store() -> EventStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgEventStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullEventStore()


def _build_job_store() -> JobStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgJobStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullJobStore()


def _build_scheduler_store() -> SchedulerStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgSchedulerStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullSchedulerStore()


def _build_evidence_store() -> EvidenceStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgEvidenceStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullEvidenceStore()


def _build_retrieval_store() -> RetrievalStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgRetrievalStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullRetrievalStore()


def _build_skill_store() -> SkillStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgSkillStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullSkillStore()


def _build_audit_store() -> AuditStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgAuditStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullAuditStore()


def _build_embedding_store() -> EmbeddingStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgEmbeddingStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullEmbeddingStore()


def _build_attribution_store() -> AttributionStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgAttributionStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullAttributionStore()


def _build_candidate_store() -> CandidateStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgCandidateStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullCandidateStore()


def _build_evaluation_store() -> EvaluationStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgEvaluationStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullEvaluationStore()


def _build_utility_store() -> UtilityStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgUtilityStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullUtilityStore()


def _build_contract_store() -> ContractStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgContractStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullContractStore()


def _build_governance_store() -> GovernanceStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgGovernanceStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullGovernanceStore()


def _build_lifecycle_store(governance: GovernanceStore) -> LifecycleStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgLifecycleStore(
            settings.database_url,
            governance=governance,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullLifecycleStore()


def _require_ingest_auth(authorization: str | None) -> None:
    settings = get_settings()
    if not settings.ingest_token:
        return

    expected = f"Bearer {settings.ingest_token}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="invalid ingest authorization",
        )


def _require_control_auth(authorization: str | None) -> None:
    settings = get_settings()
    if not settings.control_token:
        return

    expected = f"Bearer {settings.control_token}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="invalid control authorization",
        )


def _resolve_workspace_child(workspace_root: Path, configured_path: Path) -> Path:
    path = configured_path if configured_path.is_absolute() else workspace_root / configured_path
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="writer roots must stay under the workspace root",
        ) from error
    return resolved


def _writer_roots(workspace_root: Path | None = None) -> tuple[Path, Path, Path]:
    settings = get_settings()
    root = (workspace_root or Path.cwd()).resolve()
    active_root = _resolve_workspace_child(root, settings.active_root)
    expected_active_root = (root / "skills" / "autoskill").resolve()
    if active_root != expected_active_root:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="writer endpoints require active_root=skills/autoskill",
        )
    staging_root = _resolve_workspace_child(root, settings.staging_root)
    archive_root = _resolve_workspace_child(root, settings.archive_root)
    return root, staging_root, archive_root


def _worker_stores(
    *,
    jobs: JobStore,
    scheduler: SchedulerStore,
    evidence: EvidenceStore,
    embeddings: EmbeddingStore,
    retrieval: RetrievalStore,
    evaluations: EvaluationStore,
    governance: GovernanceStore,
    utility: UtilityStore,
    contracts: ContractStore,
    writer_workspace_root: Path | None = None,
) -> WorkerStores:
    workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
    return WorkerStores(
        jobs=jobs,
        scheduler=scheduler,
        evidence=evidence,
        embeddings=embeddings,
        retrieval=retrieval,
        evaluations=evaluations,
        governance=governance,
        utility=utility,
        contracts=contracts,
        workspace_root=workspace_root,
        archive_root=archive_root,
    )


def create_app(
    event_store: EventStore | None = None,
    job_store: JobStore | None = None,
    scheduler_store: SchedulerStore | None = None,
    evidence_store: EvidenceStore | None = None,
    retrieval_store: RetrievalStore | None = None,
    skill_store: SkillStore | None = None,
    embedding_store: EmbeddingStore | None = None,
    audit_store: AuditStore | None = None,
    attribution_store: AttributionStore | None = None,
    candidate_store: CandidateStore | None = None,
    evaluation_store: EvaluationStore | None = None,
    utility_store: UtilityStore | None = None,
    contract_store: ContractStore | None = None,
    governance_store: GovernanceStore | None = None,
    lifecycle_store: LifecycleStore | None = None,
    writer_workspace_root: Path | None = None,
) -> FastAPI:
    store = event_store or _build_event_store()
    jobs = job_store or _build_job_store()
    scheduler = scheduler_store or _build_scheduler_store()
    evidence = evidence_store or _build_evidence_store()
    retrieval = retrieval_store or _build_retrieval_store()
    skills = skill_store or _build_skill_store()
    embeddings = embedding_store or _build_embedding_store()
    audit = audit_store or _build_audit_store()
    attribution = attribution_store or _build_attribution_store()
    candidates = candidate_store or _build_candidate_store()
    evaluations = evaluation_store or _build_evaluation_store()
    utility = utility_store or _build_utility_store()
    contracts = contract_store or _build_contract_store()
    governance = governance_store or _build_governance_store()
    lifecycle = lifecycle_store or _build_lifecycle_store(governance)
    broker_cache = ContextHintCache()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            for closeable in (
                store,
                jobs,
                scheduler,
                evidence,
                retrieval,
                skills,
                embeddings,
                audit,
                attribution,
                candidates,
                evaluations,
                utility,
                contracts,
                governance,
                lifecycle,
            ):
                close = getattr(closeable, "close", None)
                if close is not None:
                    await close()

    app = FastAPI(
        title="SkillKernel AutoSkill Sidecar",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service="autoskill-sidecar", version=__version__)

    @app.get("/v1/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        settings = get_settings()
        job_summary = await jobs.summary()
        worker_health = await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": settings.worker_scheduler_concurrency,
                "maintenance": settings.worker_maintenance_concurrency,
                "mutation": settings.worker_mutation_concurrency,
            },
        )
        return StatusResponse(
            mode=settings.mode.value,
            database_configured=bool(settings.database_url),
            ingest_auth_configured=bool(settings.ingest_token),
            control_auth_configured=bool(settings.control_token),
            runtime_context_broker={
                "enabled": settings.runtime_context_broker_enabled,
                "timeout_ms": settings.runtime_context_timeout_ms,
                "max_tokens": settings.max_context_hint_tokens,
            },
            jobs=job_summary.counts,
            workers=worker_health.to_json(),
        )

    @app.post("/v1/ingest/events", response_model=IngestResult)
    async def ingest_events(
        request: IngestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> IngestResult:
        _require_ingest_auth(authorization)
        redacted = [event.redacted() for event in request.events]
        summary = await store.ingest_events(redacted)
        return IngestResult(
            accepted=summary.accepted,
            duplicate=summary.duplicate,
            rejected=summary.rejected,
        )

    @app.post("/v1/runtime/context-hint", response_model=ContextHintResponse)
    async def context_hint(request: ContextHintRequest) -> ContextHintResponse:
        if not get_settings().runtime_context_broker_enabled:
            return bootstrap_context_hint(request)
        return await build_context_hint(retrieval, request, cache=broker_cache)

    @app.get("/v1/skills", response_model=SkillListResponse)
    async def list_skills(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> SkillListResponse:
        _require_control_auth(authorization)
        listed = await skills.list_skills(
            workspace_key=workspace_id,
            lifecycle_state=lifecycle_state,
            limit=max(1, min(limit, 500)),
        )
        return SkillListResponse(skills=[skill.to_json() for skill in listed])

    @app.get("/v1/jobs")
    async def list_jobs(
        authorization: Annotated[str | None, Header()] = None,
        status_filter: Annotated[str | None, Query(alias="status")] = None,
        limit: int = 50,
    ) -> dict[str, list[dict[str, object]]]:
        _require_control_auth(authorization)
        listed = await jobs.list_jobs(status=status_filter, limit=max(1, min(limit, 250)))
        return {"jobs": [job.to_json() for job in listed]}

    @app.post("/v1/jobs/enqueue", response_model=JobEnqueueResponse)
    async def enqueue_job(
        request: JobEnqueueRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JobEnqueueResponse:
        _require_control_auth(authorization)
        result = await jobs.enqueue_job(
            workspace_key=request.workspace_id,
            job_kind=request.job_kind,
            idempotency_key=request.idempotency_key,
            payload=request.payload,
            priority=request.priority,
            max_attempts=request.max_attempts,
        )
        return JobEnqueueResponse(created=result.created, job=result.job.to_json())

    @app.post("/v1/jobs/claim", response_model=JobClaimResponse)
    async def claim_job(
        request: JobClaimRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JobClaimResponse:
        _require_control_auth(authorization)
        job = await jobs.claim_next_job(
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            job_kinds=request.job_kinds,
        )
        return JobClaimResponse(job=job.to_json() if job else None)

    @app.post("/v1/jobs/{job_id}/complete")
    async def complete_job(
        job_id: UUID,
        request: JobCompleteRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object | None]:
        _require_control_auth(authorization)
        if request.status not in {"succeeded", "failed"}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="status must be succeeded or failed",
            )
        job = await jobs.complete_job(
            job_id=job_id,
            worker_id=request.worker_id,
            status=request.status,
            error=request.error,
        )
        return {"job": job.to_json() if job else None}

    @app.get("/v1/schedules")
    async def list_schedules(
        authorization: Annotated[str | None, Header()] = None,
        limit: int = 50,
    ) -> dict[str, list[dict[str, object]]]:
        _require_control_auth(authorization)
        schedules = await scheduler.list_schedules(limit=max(1, min(limit, 250)))
        return {"schedules": [schedule.to_json() for schedule in schedules]}

    @app.post("/v1/schedules/upsert", response_model=ScheduleUpsertResponse)
    async def upsert_schedule(
        request: ScheduleUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ScheduleUpsertResponse:
        _require_control_auth(authorization)
        result = await scheduler.upsert_schedule(
            workspace_key=request.workspace_id,
            name=request.name,
            job_kind=request.job_kind,
            interval_seconds=request.interval_seconds,
            next_run_at=datetime.fromisoformat(request.next_run_at),
            payload=request.payload,
            enabled=request.enabled,
        )
        return ScheduleUpsertResponse(
            created=result.created,
            schedule=result.schedule.to_json(),
        )

    @app.post("/v1/scheduler/tick", response_model=SchedulerTickResponse)
    async def scheduler_tick(
        authorization: Annotated[str | None, Header()] = None,
        limit: int = 25,
    ) -> SchedulerTickResponse:
        _require_control_auth(authorization)
        result = await scheduler.run_due_schedules(limit=max(1, min(limit, 250)))
        return SchedulerTickResponse(
            due=result.due,
            enqueued=result.enqueued,
            jobs=[job.to_json() for job in result.jobs],
        )

    @app.post("/v1/workers/run-once", response_model=WorkerRunOnceResponse)
    async def worker_run_once(
        request: WorkerRunOnceRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> WorkerRunOnceResponse:
        _require_control_auth(authorization)
        if request.pool not in {"scheduler", "maintenance", "mutation"}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="pool must be scheduler, maintenance, or mutation",
            )
        result: WorkerRunResult = await run_worker_once(
            _worker_stores(
                jobs=jobs,
                scheduler=scheduler,
                evidence=evidence,
                embeddings=embeddings,
                retrieval=retrieval,
                evaluations=evaluations,
                governance=governance,
                utility=utility,
                contracts=contracts,
                writer_workspace_root=writer_workspace_root,
            ),
            worker_id=request.worker_id,
            pool=request.pool,
            lease_seconds=max(1, min(request.lease_seconds, 3600)),
        )
        return WorkerRunOnceResponse(**result.to_json())

    @app.get("/v1/workers/health", response_model=WorkerHealthResponse)
    async def worker_health(
        authorization: Annotated[str | None, Header()] = None,
    ) -> WorkerHealthResponse:
        _require_control_auth(authorization)
        settings = get_settings()
        summary = await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": settings.worker_scheduler_concurrency,
                "maintenance": settings.worker_maintenance_concurrency,
                "mutation": settings.worker_mutation_concurrency,
            },
        )
        return WorkerHealthResponse(**summary.to_json())

    @app.get("/v1/evidence")
    async def list_evidence(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, list[dict[str, object]]]:
        _require_control_auth(authorization)
        records = await evidence.list_evidence(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 250)),
        )
        return {"evidence": [record.to_json() for record in records]}

    @app.post("/v1/evidence/derive", response_model=EvidenceDeriveResponse)
    async def derive_evidence(
        request: EvidenceDeriveRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EvidenceDeriveResponse:
        _require_control_auth(authorization)
        result = await evidence.derive_from_raw_events(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 500)),
        )
        return EvidenceDeriveResponse(
            scanned=result.scanned,
            created=result.created,
            duplicate=result.duplicate,
            evidence=[record.to_json() for record in result.evidence],
        )

    @app.post("/v1/opportunities/mine", response_model=OpportunityMineResponse)
    async def mine_opportunity_candidates(
        request: OpportunityMineRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> OpportunityMineResponse:
        _require_control_auth(authorization)
        result = await mine_opportunities(
            evidence,
            retrieval,
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 500)),
            min_support=max(2, min(request.min_support, 25)),
        )
        return OpportunityMineResponse(**result.to_json())

    @app.post("/v1/candidates/propose", response_model=CandidateProposalResponse)
    async def propose_candidates(
        request: CandidateProposalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> CandidateProposalResponse:
        _require_control_auth(authorization)
        opportunities = await mine_opportunities(
            evidence,
            retrieval,
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 500)),
            min_support=max(2, min(request.min_support, 25)),
        )
        result = propose_candidate_skills(opportunities)
        payload = result.to_json()
        if request.persist:
            transaction = None
            transaction_id = request.evolution_transaction_id
            if result.proposed > 0 and transaction_id is None:
                started = await governance.start_transaction(
                    workspace_key=request.workspace_id,
                    transaction_kind="candidate_proposal",
                    idempotency_key=_candidate_transaction_idempotency_key(
                        workspace_key=request.workspace_id,
                        proposals=payload["proposals"],
                    ),
                    plan_hash=_candidate_transaction_plan_hash(
                        workspace_key=request.workspace_id,
                        proposals=payload["proposals"],
                    ),
                    actor="autoskill-sidecar",
                    cause={
                        "endpoint": "/v1/candidates/propose",
                        "mode": "propose_only",
                    },
                    source_evidence_ids=_candidate_source_evidence_ids(
                        payload["proposals"],
                    ),
                    policy_snapshot={
                        "runtime_file_writes": "forbidden",
                        "candidate_state": "inactive",
                        "activation_gate": "disabled",
                    },
                )
                transaction = started.transaction
                transaction_id = started.transaction.evolution_transaction_id
            persistence = await candidates.persist_candidate_proposals(
                workspace_key=request.workspace_id,
                proposals=result.proposals,
                evolution_transaction_id=transaction_id,
            )
            persistence_payload = persistence.to_json()
            if transaction_id is not None and persistence.persisted > 0:
                transaction = await governance.update_transaction_status(
                    evolution_transaction_id=transaction_id,
                    status="staged",
                    metrics={
                        "persisted_candidates": persistence.persisted,
                        "skipped_candidates": persistence.skipped,
                    },
                )
            if transaction is not None:
                persistence_payload["transaction"] = transaction.to_json()
            payload["persistence"] = persistence_payload
        return CandidateProposalResponse(**payload)

    @app.post("/v1/evaluations/run", response_model=EvaluationRunResponse)
    async def run_evaluations(
        request: EvaluationRunRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EvaluationRunResponse:
        _require_control_auth(authorization)
        result = await evaluations.run_pending_proposal_gates(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 250)),
        )
        return EvaluationRunResponse(**result.to_json())

    @app.post("/v1/utility/rollup", response_model=UtilityRollupResponse)
    async def utility_rollup(
        request: UtilityRollupRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> UtilityRollupResponse:
        _require_control_auth(authorization)
        result = await utility.run_utility_rollup(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 1000)),
        )
        return UtilityRollupResponse(**result.to_json())

    @app.post("/v1/curation/run", response_model=CurationRunResponse)
    async def run_curation(
        request: CurationRunRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> CurationRunResponse:
        _require_control_auth(authorization)
        result = await utility.run_curation(
            workspace_key=request.workspace_id,
            archive_threshold=request.archive_threshold,
            max_archive=max(0, min(request.max_archive, 100)),
            promotion_min_retrieval=max(1, min(request.promotion_min_retrieval, 1000)),
            max_promote=max(0, min(request.max_promote, 100)),
            active_budget=(
                None if request.active_budget is None else max(1, min(request.active_budget, 1000))
            ),
            max_merge=max(0, min(request.max_merge, 100)),
        )
        return CurationRunResponse(**result.to_json())

    @app.post("/v1/contracts/extract", response_model=ContractExtractResponse)
    async def extract_contracts(
        request: ContractExtractRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContractExtractResponse:
        _require_control_auth(authorization)
        result = await contracts.extract_contracts(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 1000)),
        )
        return ContractExtractResponse(**result.to_json())

    @app.post("/v1/drift/check", response_model=DriftCheckResponse)
    async def check_drift(
        request: DriftCheckRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> DriftCheckResponse:
        _require_control_auth(authorization)
        result = await contracts.run_drift_checks(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 1000)),
        )
        return DriftCheckResponse(**result.to_json())

    @app.post("/v1/evolution/transactions/start", response_model=EvolutionTransactionStartResponse)
    async def start_evolution_transaction(
        request: EvolutionTransactionStartRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EvolutionTransactionStartResponse:
        _require_control_auth(authorization)
        result = await governance.start_transaction(
            workspace_key=request.workspace_id,
            transaction_kind=request.transaction_kind,
            idempotency_key=request.idempotency_key,
            plan_hash=request.plan_hash,
            actor=request.actor,
            cause=request.cause,
            source_evidence_ids=request.source_evidence_ids,
            source_memory_ids=request.source_memory_ids,
            policy_snapshot=request.policy_snapshot,
            rollback_of_transaction_id=request.rollback_of_transaction_id,
        )
        return EvolutionTransactionStartResponse(**result.to_json())

    @app.post(
        "/v1/evolution/transactions/{transaction_id}/status",
        response_model=EvolutionTransactionStatusResponse,
    )
    async def update_evolution_transaction_status(
        transaction_id: UUID,
        request: EvolutionTransactionStatusRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EvolutionTransactionStatusResponse:
        _require_control_auth(authorization)
        transaction = await governance.update_transaction_status(
            evolution_transaction_id=transaction_id,
            status=request.status,
            metrics=request.metrics,
        )
        return EvolutionTransactionStatusResponse(
            transaction=transaction.to_json() if transaction else None,
        )

    @app.post(
        "/v1/evolution/transactions/{transaction_id}/items",
        response_model=EvolutionTransactionItemResponse,
    )
    async def record_evolution_transaction_item(
        transaction_id: UUID,
        request: EvolutionTransactionItemRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EvolutionTransactionItemResponse:
        _require_control_auth(authorization)
        item = await governance.record_transaction_item(
            evolution_transaction_id=transaction_id,
            item_kind=request.item_kind,
            activation_state=request.activation_state,
            item_id=request.item_id,
            relative_path=request.relative_path,
            before_hash=request.before_hash,
            after_hash=request.after_hash,
            rollback_action=request.rollback_action,
        )
        return EvolutionTransactionItemResponse(item=item.to_json())

    @app.post("/v1/writer/apply", response_model=WriterArtifactResponse)
    async def apply_writer_manifest(
        request: WriterApplyRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> WriterArtifactResponse:
        _require_control_auth(authorization)
        workspace_root, staging_root, archive_root = _writer_roots(writer_workspace_root)
        try:
            artifact = await apply_staged_manifest_with_governance(
                governance,
                evolution_transaction_id=request.evolution_transaction_id,
                staging_root=staging_root,
                workspace_root=workspace_root,
                archive_root=archive_root,
                manifest_relative_path=request.manifest_relative_path,
            )
        except (ValueError, FileExistsError, FileNotFoundError) as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return WriterArtifactResponse(artifact=artifact.to_json())

    @app.post("/v1/writer/rollback", response_model=WriterArtifactResponse)
    async def rollback_writer_manifest(
        request: WriterRollbackRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> WriterArtifactResponse:
        _require_control_auth(authorization)
        workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
        try:
            artifact = await rollback_active_skill_with_governance(
                governance,
                evolution_transaction_id=request.evolution_transaction_id,
                workspace_root=workspace_root,
                archive_root=archive_root,
                archive_manifest_relative_path=request.archive_manifest_relative_path,
            )
        except (ValueError, FileExistsError, FileNotFoundError) as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return WriterArtifactResponse(artifact=artifact.to_json())

    @app.post("/v1/provenance/edges", response_model=ProvenanceEdgeCreateResponse)
    async def record_provenance_edge(
        request: ProvenanceEdgeCreateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ProvenanceEdgeCreateResponse:
        _require_control_auth(authorization)
        result = await governance.record_provenance_edge(
            workspace_key=request.workspace_id,
            source_kind=request.source_kind,
            source_id=request.source_id,
            derived_kind=request.derived_kind,
            derived_id=request.derived_id,
            relation=request.relation,
        )
        return ProvenanceEdgeCreateResponse(**result.to_json())

    @app.post("/v1/revocations/preview", response_model=RevocationTraversalPreviewResponse)
    async def preview_revocation_traversal(
        request: RevocationTraversalPreviewRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> RevocationTraversalPreviewResponse:
        _require_control_auth(authorization)
        traversal = await governance.preview_revocation_traversal(
            workspace_key=request.workspace_id,
            root_object_type=request.root_object_type,
            root_object_id=request.root_object_id,
            max_depth=request.max_depth,
            max_nodes=request.max_nodes,
        )
        return RevocationTraversalPreviewResponse(traversal=traversal.to_json())

    @app.post("/v1/revocations/request", response_model=RevocationRequestCreateResponse)
    async def request_revocation(
        request: RevocationRequestCreateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> RevocationRequestCreateResponse:
        _require_control_auth(authorization)
        traversal_summary: dict[str, object] = request.traversal_summary
        if not traversal_summary:
            traversal = await governance.preview_revocation_traversal(
                workspace_key=request.workspace_id,
                root_object_type=request.root_object_type,
                root_object_id=request.root_object_id,
            )
            traversal_payload = traversal.to_json()
            traversal_summary = {
                "root_object_type": traversal_payload["root_object_type"],
                "root_object_id": traversal_payload["root_object_id"],
                "impacted_count": traversal_payload["impacted_count"],
                "impacted_objects": traversal_payload["impacted_objects"],
                "truncated": traversal_payload["truncated"],
            }
        revocation = await governance.request_revocation(
            workspace_key=request.workspace_id,
            request_kind=request.request_kind,
            root_object_type=request.root_object_type,
            root_object_id=request.root_object_id,
            traversal_summary=traversal_summary,
            created_by_job_id=request.created_by_job_id,
        )
        return RevocationRequestCreateResponse(revocation=revocation.to_json())

    @app.post("/v1/canary/results", response_model=CanaryResultResponse)
    async def record_canary_result(
        request: CanaryResultRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> CanaryResultResponse:
        _require_control_auth(authorization)
        if request.status not in {"passed", "failed", "critical"}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="status must be passed, failed, or critical",
            )
        result = await lifecycle.record_canary_result(
            workspace_key=request.workspace_id,
            skill_id=request.skill_id,
            status=request.status,
            critical=request.critical or request.status == "critical",
            reason=request.reason,
            metrics=request.metrics,
            skill_version_id=request.skill_version_id,
            evolution_transaction_id=request.evolution_transaction_id,
        )
        return CanaryResultResponse(**result.to_json())

    @app.post("/v1/control/freeze", response_model=SkillLifecycleResponse)
    async def freeze_skill(
        request: FreezeSkillRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SkillLifecycleResponse:
        _require_control_auth(authorization)
        skill = await lifecycle.freeze_skill(
            workspace_key=request.workspace_id,
            skill_id=request.skill_id,
            reason=request.reason,
            evolution_transaction_id=request.evolution_transaction_id,
        )
        return SkillLifecycleResponse(skill=skill.to_json() if skill else None)

    @app.post("/v1/control/unfreeze", response_model=SkillLifecycleResponse)
    async def unfreeze_skill(
        request: UnfreezeSkillRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SkillLifecycleResponse:
        _require_control_auth(authorization)
        if request.target_state == "frozen":
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="target_state must not be frozen",
            )
        try:
            skill = await lifecycle.unfreeze_skill(
                workspace_key=request.workspace_id,
                skill_id=request.skill_id,
                target_state=request.target_state,
                reason=request.reason,
                evolution_transaction_id=request.evolution_transaction_id,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return SkillLifecycleResponse(skill=skill.to_json() if skill else None)

    @app.post("/v1/shadowing/detect", response_model=ShadowingDetectResponse)
    async def detect_shadowing(
        request: ShadowingDetectRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ShadowingDetectResponse:
        _require_control_auth(authorization)
        result = await detect_shadowing_events(
            evidence,
            attribution,
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 500)),
        )
        return ShadowingDetectResponse(**result.to_json())

    @app.post("/v1/retrieval/query", response_model=RetrievalQueryResponse)
    async def retrieval_query(
        request: RetrievalQueryRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> RetrievalQueryResponse:
        _require_control_auth(authorization)
        result = await retrieval.lexical_query(
            workspace_key=request.workspace_id,
            query=request.query,
            session_id=request.session_id,
            turn_id=request.turn_id,
            limit=max(1, min(request.limit, 50)),
        )
        return RetrievalQueryResponse(
            retrieval_log_id=str(result.retrieval_log_id) if result.retrieval_log_id else None,
            decision=result.decision,
            candidates=[candidate.to_json() for candidate in result.candidates],
        )

    @app.post("/v1/skills/match", response_model=SkillMatchApiResponse)
    async def match_skills(
        request: SkillMatchApiRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SkillMatchApiResponse:
        _require_control_auth(authorization)
        result = await match_existing_skills(
            retrieval,
            SkillMatchRequest(
                workspace_key=request.workspace_id,
                candidate_slug=request.candidate_slug,
                candidate_description=request.candidate_description,
                candidate_runtime_text=request.candidate_runtime_text,
                limit=request.limit,
            ),
        )
        return SkillMatchApiResponse(**result.to_json())

    @app.post("/v1/embeddings/upsert", response_model=EmbeddingUpsertResponse)
    async def upsert_embedding(
        request: EmbeddingUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EmbeddingUpsertResponse:
        _require_control_auth(authorization)
        try:
            result = await embeddings.upsert_embedding(
                workspace_key=request.workspace_id,
                object_type=request.object_type,
                object_id=request.object_id,
                embedding_model=request.embedding_model,
                embedding=request.embedding,
                text=request.text,
                skill_id=request.skill_id,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return EmbeddingUpsertResponse(
            created=result.created,
            embedding=result.embedding.to_json(),
        )

    @app.post("/v1/embeddings/search", response_model=EmbeddingSearchResponse)
    async def search_embeddings(
        request: EmbeddingSearchRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EmbeddingSearchResponse:
        _require_control_auth(authorization)
        try:
            candidates = await embeddings.search_embeddings(
                workspace_key=request.workspace_id,
                embedding_model=request.embedding_model,
                embedding=request.embedding,
                object_type=request.object_type,
                limit=max(1, min(request.limit, 50)),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return EmbeddingSearchResponse(
            candidates=[candidate.to_json() for candidate in candidates],
        )

    @app.post("/v1/embeddings/recall-audit", response_model=EmbeddingRecallAuditResponse)
    async def audit_embedding_recall(
        request: EmbeddingRecallAuditRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EmbeddingRecallAuditResponse:
        _require_control_auth(authorization)
        result = await embeddings.audit_recall(
            workspace_key=request.workspace_id,
            embedding_model=request.embedding_model,
            object_type=request.object_type,
            sample_size=max(1, min(request.sample_size, 100)),
            k=max(1, min(request.k, 100)),
            min_recall=max(0.0, min(request.min_recall, 1.0)),
        )
        return EmbeddingRecallAuditResponse(**result.to_json())

    @app.post("/v1/embeddings/generate", response_model=EmbeddingGenerateResponse)
    async def generate_embeddings(
        request: EmbeddingGenerateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EmbeddingGenerateResponse:
        _require_control_auth(authorization)
        settings = get_settings()
        try:
            embedder = build_text_embedder_from_settings(settings)
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        result = await generate_pending_embeddings(
            embeddings,
            embedder=embedder,
            workspace_key=request.workspace_id,
            embedding_model=request.embedding_model,
            limit=max(1, min(request.limit, 500)),
        )
        return EmbeddingGenerateResponse(**result.to_json())

    @app.get("/v1/audit/recent", response_model=AuditRecentResponse)
    async def recent_audit(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> AuditRecentResponse:
        _require_control_auth(authorization)
        bounded_limit = max(1, min(limit, 1000))
        records = await audit.list_recent(workspace_key=workspace_id, limit=bounded_limit)
        return AuditRecentResponse(
            audit=[record.model_dump(mode="json") for record in records],
            chain_valid=await audit.verify_chain(workspace_key=workspace_id, limit=bounded_limit),
        )

    return app
