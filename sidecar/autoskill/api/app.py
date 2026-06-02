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
from autoskill.core.skillir import EffectSignature
from autoskill.db.activation import (
    ActivationGateStore,
    AsyncpgActivationGateStore,
    NullActivationGateStore,
)
from autoskill.db.attribution import AsyncpgAttributionStore, AttributionStore, NullAttributionStore
from autoskill.db.audit import AsyncpgAuditStore, AuditStore, NullAuditStore
from autoskill.db.candidates import AsyncpgCandidateStore, CandidateStore, NullCandidateStore
from autoskill.db.compatibility import (
    AsyncpgCompatibilityStore,
    CompatibilityStore,
    NullCompatibilityStore,
)
from autoskill.db.context import (
    AsyncpgContextGovernanceStore,
    ContextGovernanceStore,
    NullContextGovernanceStore,
)
from autoskill.db.contracts import AsyncpgContractStore, ContractStore, NullContractStore
from autoskill.db.diagnostics import (
    AsyncpgDiagnosticMomentumStore,
    DiagnosticMomentumStore,
    NullDiagnosticMomentumStore,
)
from autoskill.db.embeddings import AsyncpgEmbeddingStore, EmbeddingStore, NullEmbeddingStore
from autoskill.db.evaluations import AsyncpgEvaluationStore, EvaluationStore, NullEvaluationStore
from autoskill.db.events import AsyncpgEventStore, EventStore, NullEventStore
from autoskill.db.evidence import AsyncpgEvidenceStore, EvidenceStore, NullEvidenceStore
from autoskill.db.external_skills import (
    AsyncpgExternalSkillStore,
    ExternalSkillInput,
    ExternalSkillStore,
    NullExternalSkillStore,
)
from autoskill.db.governance import AsyncpgGovernanceStore, GovernanceStore, NullGovernanceStore
from autoskill.db.jobs import AsyncpgJobStore, JobStore, NullJobStore
from autoskill.db.lifecycle import AsyncpgLifecycleStore, LifecycleStore, NullLifecycleStore
from autoskill.db.llm_invocations import (
    AsyncpgLLMInvocationStore,
    LLMInvocationStore,
    NullLLMInvocationStore,
)
from autoskill.db.observability import (
    AsyncpgObservabilityStore,
    NullObservabilityStore,
    ObservabilityStore,
)
from autoskill.db.profile_qualifications import (
    AsyncpgProfileQualificationStore,
    NullProfileQualificationStore,
    ProfileQualificationStore,
)
from autoskill.db.profiles import AsyncpgProfileStore, NullProfileStore, ProfileStore
from autoskill.db.retrieval import AsyncpgRetrievalStore, NullRetrievalStore, RetrievalStore
from autoskill.db.scheduler import AsyncpgSchedulerStore, NullSchedulerStore, SchedulerStore
from autoskill.db.skills import AsyncpgSkillStore, NullSkillStore, SkillStore
from autoskill.db.topology import AsyncpgTopologyStore, NullTopologyStore, TopologyStore
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
    HashingTextEmbedder,
    OpenAICompatibleTextEmbedder,
    build_text_embedder_from_settings,
    generate_pending_embeddings,
)
from autoskill.services.evaluation_runner import run_pending_proposal_gates_with_trace
from autoskill.services.llm import LLMClient
from autoskill.services.matching import SkillMatchRequest, match_existing_skills
from autoskill.services.opportunity import mine_opportunities
from autoskill.services.profile_qualification import (
    ProfileQualificationError,
    qualify_embedding_profile,
    qualify_text_profile,
)
from autoskill.services.shadowing import detect_shadowing_events
from autoskill.services.topology import (
    ComposeTopologyRequest,
    DecomposeTopologyRequest,
    ImproveTopologyRequest,
    TopologySkill,
    persist_topology_proposal,
    propose_composition,
    propose_decomposition,
    propose_improvement,
)
from autoskill.services.worker import (
    WorkerRunResult,
    WorkerStores,
    build_worker_health,
    run_worker_once,
)
from autoskill.services.writer import (
    apply_staged_manifest_with_governance,
    resolve_contained,
    rollback_active_skill_with_governance,
)
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field


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
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None
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


class JobRenewLeaseRequest(BaseModel):
    worker_id: str
    lease_seconds: int = 300


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


class TraceSpanStartRequest(BaseModel):
    workspace_id: str
    operation_name: str
    operation_kind: str
    trace_id: UUID | None = None
    parent_span_id: UUID | None = None
    safe_attributes: dict[str, object] = Field(default_factory=dict)
    object_refs: list[dict[str, object]] = Field(default_factory=list)


class TraceSpanFinishRequest(BaseModel):
    status: str = "ok"
    safe_attributes: dict[str, object] = Field(default_factory=dict)
    object_refs: list[dict[str, object]] = Field(default_factory=list)


class TraceSpanResponse(BaseModel):
    span: dict[str, object] | None


class TraceListResponse(BaseModel):
    spans: list[dict[str, object]]


class DiagnosticSignalRequest(BaseModel):
    workspace_id: str
    diagnostic_kind: str
    root_cause_hypothesis: str
    suggested_change_direction: str
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    executor_profile_id: UUID | None = None
    evidence_delta: int = 1
    contrastive_support_delta: int = 0
    counterevidence_delta: int = 0
    risk_score: float = 0.0
    issue_signature: dict[str, object] = Field(default_factory=dict)


class DiagnosticMomentumResponse(BaseModel):
    momentum: dict[str, object]


class DiagnosticMomentumListResponse(BaseModel):
    momentum: list[dict[str, object]]


class ExecutorProfileUpsertRequest(BaseModel):
    workspace_id: str
    profile_key: str
    model_family: str | None = None
    agent_backend: str | None = None
    sandbox: str | None = None
    os_name: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    available_binaries: list[str] = Field(default_factory=list)
    permissions: dict[str, object] = Field(default_factory=dict)
    api_contracts: dict[str, object] = Field(default_factory=dict)
    status: str = "active"


class ExecutorProfileResponse(BaseModel):
    profile: dict[str, object]


class ExecutorProfileListResponse(BaseModel):
    profiles: list[dict[str, object]]


class ModelProfileUpsertRequest(BaseModel):
    workspace_id: str
    profile_key: str
    provider: str
    model: str
    route_kind: str
    endpoint_ref: str | None = None
    timeout_seconds: float = 60.0
    thinking_level: str = "off"
    thinking_fallback_policy: str = "omit"
    status: str = "candidate"
    qualification: dict[str, object] = Field(default_factory=dict)


class EmbeddingProfileUpsertRequest(ModelProfileUpsertRequest):
    embedding_dim: int = 1536
    timeout_seconds: float = 30.0


class ModelProfileResponse(BaseModel):
    profile: dict[str, object]


class ProfileQualificationRunRequest(BaseModel):
    workspace_id: str
    profile_key: str
    probe_set_version: str | None = None


class ProfileQualificationRunResponse(BaseModel):
    run: dict[str, object]


class SkillProfileCompatibilityUpsertRequest(BaseModel):
    workspace_id: str
    skill_version_id: UUID
    executor_profile_id: UUID
    status: str
    evidence: dict[str, object] = Field(default_factory=dict)


class SkillProfileCompatibilityResponse(BaseModel):
    compatibility: dict[str, object]


class ContextArtifactRecordRequest(BaseModel):
    workspace_id: str
    artifact_kind: str
    source_object_type: str
    text: str
    max_tokens: int
    source_object_id: UUID | None = None
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    broker_policy_version_id: UUID | None = None
    safety_status: str = "pending"
    equivalence_status: str = "pending"
    shadowing_status: str = "pending"
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextArtifactResponse(BaseModel):
    artifact: dict[str, object]


class ContextTokenLedgerRequest(BaseModel):
    workspace_id: str
    visibility_state: str
    token_count: int
    context_artifact_id: UUID | None = None
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    broker_policy_version_id: UUID | None = None
    session_id: str | None = None
    turn_id: str | None = None
    outcome: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextTokenLedgerResponse(BaseModel):
    ledger: dict[str, object]


class ContextTokenLedgerOutcomeRequest(BaseModel):
    workspace_id: str
    outcome: str
    utility_delta: float = 0.0
    task_success: bool | None = None
    token_savings: int | None = None
    latency_delta_ms: float | None = None
    tool_call_delta: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TopologySkillPayload(BaseModel):
    slug: str
    skill_id: UUID | None = None
    effects: dict[str, object] = Field(default_factory=dict)


class TopologyProposalRequest(BaseModel):
    workspace_id: str
    operation_kind: str
    subject: TopologySkillPayload | None = None
    proposed: TopologySkillPayload | None = None
    components: list[TopologySkillPayload] = Field(default_factory=list)
    composed_output: TopologySkillPayload | None = None
    successors: list[TopologySkillPayload] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    improvement_reasons: list[str] = Field(default_factory=list)
    required_effects_by_component: dict[str, list[str]] | None = None
    coverage_requirements: list[str] | None = None
    persist: bool = True


class TopologyProposalResponse(BaseModel):
    proposal: dict[str, object]
    persistence: dict[str, object] | None = None


class TopologyApplyRequest(BaseModel):
    workspace_id: str
    skill_graph_operation_id: UUID
    activation_gate_required: bool = False
    skill_version_ids: list[UUID] = []
    executor_profile_id: UUID | None = None
    applied_by: str = "autoskill-sidecar"


class TopologyApplyResponse(BaseModel):
    allowed: bool
    operation: dict[str, object] | None = None
    blockers: list[str]
    downstream_actions: list[dict[str, object]] = []


class ContextCacheInvalidateRequest(BaseModel):
    workspace_id: str | None = None
    skill_ids: list[str] = []


class ContextCacheInvalidateResponse(BaseModel):
    removed: int


class SkillListResponse(BaseModel):
    skills: list[dict[str, object]]


class ExternalSkillInventoryItem(BaseModel):
    source: str
    root_path_hash: str
    slug: str
    file_hash: str
    name: str | None = None
    description: str | None = None
    frontmatter: dict[str, object] = {}
    status: str = "visible"
    risk_summary: dict[str, object] = {}


class ExternalSkillInventoryUpsertRequest(BaseModel):
    workspace_id: str
    skills: list[ExternalSkillInventoryItem]


class ExternalSkillInventoryUpsertResponse(BaseModel):
    created: int
    updated: int
    skills: list[dict[str, object]]


class ExternalSkillInventoryListResponse(BaseModel):
    skills: list[dict[str, object]]


class ExternalSkillReviewActionRequest(BaseModel):
    workspace_id: str
    external_skill_id: UUID
    action: str
    status: str = "requested"
    operator_id: str | None = None
    rationale: str | None = None
    metadata: dict[str, object] = {}


class ExternalSkillReviewActionResponse(BaseModel):
    review_action: dict[str, object]


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
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None
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
    planned: int = 0
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
    probes_created: int = 0
    probes_retired: int = 0
    false_positive: int = 0
    events: list[dict[str, object]]


class DriftFalsePositiveRequest(BaseModel):
    workspace_id: str
    environment_contract_id: UUID
    operator_id: str | None = None
    rationale: str | None = None


class DriftFalsePositiveResponse(BaseModel):
    result: dict[str, object]


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
    workspace_id: str | None = None
    activation_gate_required: bool = False
    executor_profile_id: UUID | None = None
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None


class WriterRollbackRequest(BaseModel):
    evolution_transaction_id: UUID
    archive_manifest_relative_path: str
    workspace_id: str | None = None
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None


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
    min_support: int = 2


class ShadowingDetectResponse(BaseModel):
    scanned: int
    detected: int
    events: list[dict[str, object]]
    controls: list[dict[str, object]] = []


class RetrievalQueryRequest(BaseModel):
    workspace_id: str
    query: str
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None
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
    external_matches: list[dict[str, object]] = []


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
    embedding_profile_id: UUID | None = None


class EmbeddingUpsertResponse(BaseModel):
    created: bool
    embedding: dict[str, object]


class EmbeddingSearchRequest(BaseModel):
    workspace_id: str
    embedding_model: str
    embedding: list[float]
    embedding_profile_id: UUID | None = None
    object_type: str | None = None
    limit: int = 10


class EmbeddingSearchResponse(BaseModel):
    candidates: list[dict[str, object]]


class EmbeddingRecallAuditRequest(BaseModel):
    workspace_id: str
    embedding_model: str = "autoskill-hash-embedding"
    embedding_profile_id: UUID | None = None
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
    embedding_profile_key: str | None = None
    embedding_model: str | None = None
    limit: int = 100


class EmbeddingGenerateResponse(BaseModel):
    scanned: int
    generated: int
    created: int
    updated: int
    embedding_model: str
    embedding_profile_id: str | None = None
    embedding_dim: int
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


def _build_external_skill_store() -> ExternalSkillStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgExternalSkillStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullExternalSkillStore()


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


def _build_observability_store() -> ObservabilityStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgObservabilityStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullObservabilityStore()


def _build_diagnostic_store() -> DiagnosticMomentumStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgDiagnosticMomentumStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullDiagnosticMomentumStore()


def _build_profile_store() -> ProfileStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgProfileStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullProfileStore()


def _build_llm_invocation_store() -> LLMInvocationStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgLLMInvocationStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullLLMInvocationStore()


def _build_profile_qualification_store() -> ProfileQualificationStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgProfileQualificationStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullProfileQualificationStore()


def _build_compatibility_store() -> CompatibilityStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgCompatibilityStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullCompatibilityStore()


def _build_context_governance_store() -> ContextGovernanceStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgContextGovernanceStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullContextGovernanceStore()


def _build_topology_store() -> TopologyStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgTopologyStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullTopologyStore()


def _build_activation_gate_store() -> ActivationGateStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgActivationGateStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullActivationGateStore()


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


def _embedder_from_profile(profile: object, settings: object):
    if getattr(profile, "status", None) != "qualified":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="embedding profile is not qualified",
        )
    route_kind = str(getattr(profile, "route_kind", ""))
    model = str(profile.model)
    embedding_dim = int(getattr(profile, "embedding_dim", 1536))
    if route_kind == "hash":
        return HashingTextEmbedder(model=model, embedding_dim=embedding_dim)
    if route_kind == "openai_compatible":
        base_url = getattr(profile, "endpoint_ref", None) or getattr(
            settings,
            "embedding_api_base_url",
            None,
        )
        api_key = getattr(settings, "embedding_api_key", None)
        if not base_url or not api_key:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="qualified openai_compatible profile requires endpoint and API key",
            )
        return OpenAICompatibleTextEmbedder(
            base_url=str(base_url),
            api_key=str(api_key),
            model=model,
            embedding_dim=embedding_dim,
            timeout_seconds=float(getattr(profile, "timeout_seconds", 30.0)),
        )
    raise HTTPException(
        status_code=http_status.HTTP_409_CONFLICT,
        detail=f"embedding profile route_kind is not supported for generation: {route_kind}",
    )


def _worker_stores(
    *,
    jobs: JobStore,
    scheduler: SchedulerStore,
    evidence: EvidenceStore,
    external_skills: ExternalSkillStore,
    embeddings: EmbeddingStore,
    retrieval: RetrievalStore,
    evaluations: EvaluationStore,
    governance: GovernanceStore,
    utility: UtilityStore,
    contracts: ContractStore,
    attribution: AttributionStore,
    observability: ObservabilityStore,
    context_governance: ContextGovernanceStore,
    topology: TopologyStore,
    activation_gate: ActivationGateStore,
    writer_workspace_root: Path | None = None,
    external_skill_roots: list[Path] | None = None,
) -> WorkerStores:
    workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
    return WorkerStores(
        jobs=jobs,
        scheduler=scheduler,
        evidence=evidence,
        external_skills=external_skills,
        embeddings=embeddings,
        retrieval=retrieval,
        evaluations=evaluations,
        governance=governance,
        utility=utility,
        contracts=contracts,
        attribution=attribution,
        context_governance=context_governance,
        topology=topology,
        activation_gate=activation_gate,
        observability=observability,
        workspace_root=workspace_root,
        archive_root=archive_root,
        external_skill_roots=external_skill_roots,
    )


def _topology_skill(payload: TopologySkillPayload) -> TopologySkill:
    return TopologySkill(
        slug=payload.slug,
        skill_id=payload.skill_id,
        effects=EffectSignature.model_validate(payload.effects),
    )


def _build_topology_proposal(request: TopologyProposalRequest):
    if request.operation_kind == "improve":
        if request.subject is None or request.proposed is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="improve requires subject and proposed skills",
            )
        return propose_improvement(
            ImproveTopologyRequest(
                subject=_topology_skill(request.subject),
                proposed=_topology_skill(request.proposed),
                evidence_ids=request.evidence_ids,
                improvement_reasons=request.improvement_reasons,
            )
        )
    if request.operation_kind == "compose":
        if request.composed_output is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="compose requires composed_output",
            )
        return propose_composition(
            ComposeTopologyRequest(
                components=[_topology_skill(component) for component in request.components],
                composed_output=_topology_skill(request.composed_output),
                evidence_ids=request.evidence_ids,
                required_effects_by_component=request.required_effects_by_component,
            )
        )
    if request.operation_kind == "decompose":
        if request.subject is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="decompose requires subject",
            )
        return propose_decomposition(
            DecomposeTopologyRequest(
                subject=_topology_skill(request.subject),
                successors=[_topology_skill(successor) for successor in request.successors],
                evidence_ids=request.evidence_ids,
                coverage_requirements=request.coverage_requirements,
            )
        )
    raise HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail="operation_kind must be improve, compose, or decompose",
    )


async def _check_writer_activation_gate_for_api(
    activation_gate: ActivationGateStore,
    *,
    request: WriterApplyRequest,
    staging_root: Path,
) -> None:
    if not request.activation_gate_required:
        return
    if not request.workspace_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="activation gate requires workspace_id",
        )
    try:
        manifest_path = resolve_contained(staging_root, request.manifest_relative_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_version_id = UUID(str(manifest["skill_version_id"]))
    except (KeyError, ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"activation gate could not read staged manifest: {error}",
        ) from error
    readiness = await activation_gate.check_activation_readiness(
        workspace_key=request.workspace_id,
        skill_version_id=skill_version_id,
        executor_profile_id=request.executor_profile_id,
    )
    if not readiness.allowed:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "message": "activation gate blocked writer apply",
                "readiness": readiness.to_json(),
            },
        )


async def _check_topology_activation_gate_for_api(
    activation_gate: ActivationGateStore,
    *,
    request: TopologyApplyRequest,
) -> None:
    if not request.activation_gate_required:
        return
    if not request.skill_version_ids:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="topology apply activation gate requires skill_version_ids",
        )
    blockers: list[dict[str, object]] = []
    for skill_version_id in request.skill_version_ids:
        readiness = await activation_gate.check_activation_readiness(
            workspace_key=request.workspace_id,
            skill_version_id=skill_version_id,
            executor_profile_id=request.executor_profile_id,
        )
        if not readiness.allowed:
            blockers.append(readiness.to_json())
    if blockers:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "message": "activation gate blocked topology apply",
                "readiness": blockers,
            },
        )


def create_app(
    event_store: EventStore | None = None,
    job_store: JobStore | None = None,
    scheduler_store: SchedulerStore | None = None,
    evidence_store: EvidenceStore | None = None,
    external_skill_store: ExternalSkillStore | None = None,
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
    observability_store: ObservabilityStore | None = None,
    diagnostic_store: DiagnosticMomentumStore | None = None,
    profile_store: ProfileStore | None = None,
    llm_invocation_store: LLMInvocationStore | None = None,
    profile_qualification_store: ProfileQualificationStore | None = None,
    llm_client: LLMClient | None = None,
    compatibility_store: CompatibilityStore | None = None,
    context_governance_store: ContextGovernanceStore | None = None,
    topology_store: TopologyStore | None = None,
    activation_gate_store: ActivationGateStore | None = None,
    writer_workspace_root: Path | None = None,
    external_skill_roots: list[Path] | None = None,
) -> FastAPI:
    store = event_store or _build_event_store()
    jobs = job_store or _build_job_store()
    scheduler = scheduler_store or _build_scheduler_store()
    evidence = evidence_store or _build_evidence_store()
    external_skills = external_skill_store or _build_external_skill_store()
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
    observability = observability_store or _build_observability_store()
    diagnostics = diagnostic_store or _build_diagnostic_store()
    profiles = profile_store or _build_profile_store()
    llm_invocations = llm_invocation_store or _build_llm_invocation_store()
    profile_qualifications = (
        profile_qualification_store or _build_profile_qualification_store()
    )
    text_llm = llm_client or LLMClient(
        profiles=profiles,
        invocations=llm_invocations,
        settings=get_settings(),
        observability=observability,
    )
    compatibility = compatibility_store or _build_compatibility_store()
    context_governance = context_governance_store or _build_context_governance_store()
    topology = topology_store or _build_topology_store()
    activation_gate = activation_gate_store or _build_activation_gate_store()
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
                external_skills,
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
                observability,
                diagnostics,
                profiles,
                llm_invocations,
                profile_qualifications,
                compatibility,
                context_governance,
                topology,
                activation_gate,
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
        settings = get_settings()
        if not settings.runtime_context_broker_enabled:
            return bootstrap_context_hint(request)
        return await build_context_hint(
            retrieval,
            request,
            cache=broker_cache,
            context_governance=context_governance,
            compatibility=compatibility,
            semantic_embedder=(
                build_text_embedder_from_settings(settings)
                if settings.embedding_provider == "hash"
                else None
            ),
        )

    @app.post(
        "/v1/runtime/context-hint/cache/invalidate",
        response_model=ContextCacheInvalidateResponse,
    )
    async def invalidate_context_hint_cache(
        request: ContextCacheInvalidateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextCacheInvalidateResponse:
        _require_control_auth(authorization)
        removed = broker_cache.invalidate(
            workspace_id=request.workspace_id,
            skill_ids=request.skill_ids,
        )
        return ContextCacheInvalidateResponse(removed=removed)

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

    @app.get("/v1/external-skills", response_model=ExternalSkillInventoryListResponse)
    async def list_external_skills(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> ExternalSkillInventoryListResponse:
        _require_control_auth(authorization)
        try:
            listed = await external_skills.list_external_skills(
                workspace_key=workspace_id,
                status=status,
                limit=max(1, min(limit, 500)),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return ExternalSkillInventoryListResponse(skills=[skill.to_json() for skill in listed])

    @app.post(
        "/v1/external-skills/upsert",
        response_model=ExternalSkillInventoryUpsertResponse,
    )
    async def upsert_external_skills(
        request: ExternalSkillInventoryUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ExternalSkillInventoryUpsertResponse:
        _require_control_auth(authorization)
        try:
            result = await external_skills.upsert_external_skills(
                workspace_key=request.workspace_id,
                skills=[
                    ExternalSkillInput(
                        source=item.source,
                        root_path_hash=item.root_path_hash,
                        slug=item.slug,
                        file_hash=item.file_hash,
                        name=item.name,
                        description=item.description,
                        frontmatter=item.frontmatter,
                        status=item.status,
                        risk_summary=item.risk_summary,
                    )
                    for item in request.skills
                ],
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return ExternalSkillInventoryUpsertResponse(**result.to_json())

    @app.post(
        "/v1/external-skills/review-actions",
        response_model=ExternalSkillReviewActionResponse,
    )
    async def record_external_skill_review_action(
        request: ExternalSkillReviewActionRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ExternalSkillReviewActionResponse:
        _require_control_auth(authorization)
        try:
            review_action = await external_skills.record_review_action(
                workspace_key=request.workspace_id,
                external_skill_id=request.external_skill_id,
                action=request.action,
                status=request.status,
                operator_id=request.operator_id,
                rationale=request.rationale,
                metadata=request.metadata,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return ExternalSkillReviewActionResponse(review_action=review_action.to_json())

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
            trace_id=request.trace_id,
            span_id=request.span_id,
            parent_span_id=request.parent_span_id,
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

    @app.post("/v1/jobs/{job_id}/renew-lease")
    async def renew_job_lease(
        job_id: UUID,
        request: JobRenewLeaseRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object | None]:
        _require_control_auth(authorization)
        job = await jobs.renew_job_lease(
            job_id=job_id,
            worker_id=request.worker_id,
            lease_seconds=max(1, min(request.lease_seconds, 3600)),
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
                external_skills=external_skills,
                embeddings=embeddings,
                retrieval=retrieval,
                evaluations=evaluations,
                governance=governance,
                utility=utility,
                contracts=contracts,
                attribution=attribution,
                observability=observability,
                context_governance=context_governance,
                topology=topology,
                activation_gate=activation_gate,
                writer_workspace_root=writer_workspace_root,
                external_skill_roots=external_skill_roots,
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

    @app.post("/v1/trace/spans", response_model=TraceSpanResponse)
    async def start_trace_span(
        request: TraceSpanStartRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> TraceSpanResponse:
        _require_control_auth(authorization)
        span = await observability.start_span(
            workspace_key=request.workspace_id,
            operation_name=request.operation_name,
            operation_kind=request.operation_kind,
            trace_id=request.trace_id,
            parent_span_id=request.parent_span_id,
            safe_attributes=request.safe_attributes,
            object_refs=request.object_refs,
        )
        return TraceSpanResponse(span=span.to_json())

    @app.post("/v1/trace/spans/{span_id}/finish", response_model=TraceSpanResponse)
    async def finish_trace_span(
        span_id: UUID,
        request: TraceSpanFinishRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> TraceSpanResponse:
        _require_control_auth(authorization)
        span = await observability.finish_span(
            span_id=span_id,
            status=request.status,  # type: ignore[arg-type]
            safe_attributes=request.safe_attributes,
            object_refs=request.object_refs,
        )
        return TraceSpanResponse(span=span.to_json() if span else None)

    @app.get("/v1/trace/{trace_id}", response_model=TraceListResponse)
    async def list_trace_spans(
        trace_id: UUID,
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        limit: int = 100,
    ) -> TraceListResponse:
        _require_control_auth(authorization)
        spans = await observability.list_trace(
            workspace_key=workspace_id,
            trace_id=trace_id,
            limit=max(1, min(limit, 500)),
        )
        return TraceListResponse(spans=[span.to_json() for span in spans])

    @app.post("/v1/diagnostics/momentum", response_model=DiagnosticMomentumResponse)
    async def record_diagnostic_signal(
        request: DiagnosticSignalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> DiagnosticMomentumResponse:
        _require_control_auth(authorization)
        momentum = await diagnostics.record_signal(
            workspace_key=request.workspace_id,
            diagnostic_kind=request.diagnostic_kind,
            root_cause_hypothesis=request.root_cause_hypothesis,
            suggested_change_direction=request.suggested_change_direction,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            executor_profile_id=request.executor_profile_id,
            evidence_delta=request.evidence_delta,
            contrastive_support_delta=request.contrastive_support_delta,
            counterevidence_delta=request.counterevidence_delta,
            risk_score=request.risk_score,
            issue_signature=request.issue_signature,
        )
        return DiagnosticMomentumResponse(momentum=momentum.to_json())

    @app.get("/v1/diagnostics/momentum", response_model=DiagnosticMomentumListResponse)
    async def list_diagnostic_momentum(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        min_momentum_score: float = 2.0,
        limit: int = 100,
    ) -> DiagnosticMomentumListResponse:
        _require_control_auth(authorization)
        records = await diagnostics.list_ready(
            workspace_key=workspace_id,
            min_momentum_score=min_momentum_score,
            limit=max(1, min(limit, 500)),
        )
        return DiagnosticMomentumListResponse(momentum=[record.to_json() for record in records])

    @app.post("/v1/profiles/executors", response_model=ExecutorProfileResponse)
    async def upsert_executor_profile(
        request: ExecutorProfileUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ExecutorProfileResponse:
        _require_control_auth(authorization)
        profile = await profiles.upsert_executor_profile(
            workspace_key=request.workspace_id,
            profile_key=request.profile_key,
            model_family=request.model_family,
            agent_backend=request.agent_backend,
            sandbox=request.sandbox,
            os_name=request.os_name,
            available_tools=request.available_tools,
            available_binaries=request.available_binaries,
            permissions=request.permissions,
            api_contracts=request.api_contracts,
            status=request.status,
        )
        return ExecutorProfileResponse(profile=profile.to_json())

    @app.get("/v1/profiles/executors", response_model=ExecutorProfileListResponse)
    async def list_executor_profiles(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> ExecutorProfileListResponse:
        _require_control_auth(authorization)
        listed = await profiles.list_executor_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 500)),
        )
        return ExecutorProfileListResponse(profiles=[profile.to_json() for profile in listed])

    @app.post("/v1/profiles/models", response_model=ModelProfileResponse)
    async def upsert_model_profile(
        request: ModelProfileUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ModelProfileResponse:
        _require_control_auth(authorization)
        profile = await profiles.upsert_model_profile(
            workspace_key=request.workspace_id,
            profile_key=request.profile_key,
            provider=request.provider,
            model=request.model,
            route_kind=request.route_kind,
            endpoint_ref=request.endpoint_ref,
            timeout_seconds=request.timeout_seconds,
            thinking_level=request.thinking_level,
            thinking_fallback_policy=request.thinking_fallback_policy,
            status=request.status,
            qualification=request.qualification,
        )
        return ModelProfileResponse(profile=profile.to_json())

    @app.post("/v1/profiles/embeddings", response_model=ModelProfileResponse)
    async def upsert_embedding_profile(
        request: EmbeddingProfileUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ModelProfileResponse:
        _require_control_auth(authorization)
        profile = await profiles.upsert_embedding_profile(
            workspace_key=request.workspace_id,
            profile_key=request.profile_key,
            provider=request.provider,
            model=request.model,
            route_kind=request.route_kind,
            embedding_dim=request.embedding_dim,
            endpoint_ref=request.endpoint_ref,
            timeout_seconds=request.timeout_seconds,
            status=request.status,
            qualification=request.qualification,
        )
        return ModelProfileResponse(profile=profile.to_json())

    @app.post(
        "/v1/profiles/models/qualify",
        response_model=ProfileQualificationRunResponse,
    )
    async def run_model_profile_qualification(
        request: ProfileQualificationRunRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ProfileQualificationRunResponse:
        _require_control_auth(authorization)
        try:
            result = await qualify_text_profile(
                profiles=profiles,
                qualifications=profile_qualifications,
                llm_client=text_llm,
                workspace_key=request.workspace_id,
                profile_key=request.profile_key,
                probe_set_version=request.probe_set_version
                or "autoskill-text-profile-probes.v1",
            )
        except ProfileQualificationError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return ProfileQualificationRunResponse(run=result.to_json())

    @app.post(
        "/v1/profiles/embeddings/qualify",
        response_model=ProfileQualificationRunResponse,
    )
    async def run_embedding_profile_qualification(
        request: ProfileQualificationRunRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ProfileQualificationRunResponse:
        _require_control_auth(authorization)
        try:
            result = await qualify_embedding_profile(
                profiles=profiles,
                qualifications=profile_qualifications,
                workspace_key=request.workspace_id,
                profile_key=request.profile_key,
                probe_set_version=request.probe_set_version
                or "autoskill-embedding-profile-probes.v1",
            )
        except ProfileQualificationError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return ProfileQualificationRunResponse(run=result.to_json())

    @app.post(
        "/v1/profiles/compatibility",
        response_model=SkillProfileCompatibilityResponse,
    )
    async def upsert_skill_profile_compatibility(
        request: SkillProfileCompatibilityUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SkillProfileCompatibilityResponse:
        _require_control_auth(authorization)
        record = await compatibility.upsert_compatibility(
            workspace_key=request.workspace_id,
            skill_version_id=request.skill_version_id,
            executor_profile_id=request.executor_profile_id,
            status=request.status,
            evidence=request.evidence,
        )
        return SkillProfileCompatibilityResponse(compatibility=record.to_json())

    @app.post("/v1/context/artifacts", response_model=ContextArtifactResponse)
    async def record_context_artifact(
        request: ContextArtifactRecordRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextArtifactResponse:
        _require_control_auth(authorization)
        artifact = await context_governance.record_artifact(
            workspace_key=request.workspace_id,
            artifact_kind=request.artifact_kind,
            source_object_type=request.source_object_type,
            text=request.text,
            max_tokens=request.max_tokens,
            source_object_id=request.source_object_id,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            broker_policy_version_id=request.broker_policy_version_id,
            safety_status=request.safety_status,
            equivalence_status=request.equivalence_status,
            shadowing_status=request.shadowing_status,
            metadata=request.metadata,
        )
        return ContextArtifactResponse(artifact=artifact.to_json())

    @app.post("/v1/context/token-ledger", response_model=ContextTokenLedgerResponse)
    async def record_context_token_ledger(
        request: ContextTokenLedgerRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextTokenLedgerResponse:
        _require_control_auth(authorization)
        ledger = await context_governance.record_token_ledger(
            workspace_key=request.workspace_id,
            visibility_state=request.visibility_state,
            token_count=request.token_count,
            context_artifact_id=request.context_artifact_id,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            broker_policy_version_id=request.broker_policy_version_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            outcome=request.outcome,
            metadata=request.metadata,
        )
        return ContextTokenLedgerResponse(ledger=ledger.to_json())

    @app.post(
        "/v1/context/token-ledger/{ledger_id}/outcome",
        response_model=ContextTokenLedgerResponse,
    )
    async def record_context_token_ledger_outcome(
        ledger_id: UUID,
        request: ContextTokenLedgerOutcomeRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextTokenLedgerResponse:
        _require_control_auth(authorization)
        try:
            ledger = await context_governance.record_token_ledger_outcome(
                workspace_key=request.workspace_id,
                context_token_ledger_id=ledger_id,
                outcome=request.outcome,
                utility_delta=request.utility_delta,
                task_success=request.task_success,
                token_savings=request.token_savings,
                latency_delta_ms=request.latency_delta_ms,
                tool_call_delta=request.tool_call_delta,
                metadata=request.metadata,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return ContextTokenLedgerResponse(ledger=ledger.to_json())

    @app.post("/v1/topology/propose", response_model=TopologyProposalResponse)
    async def propose_topology_operation(
        request: TopologyProposalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> TopologyProposalResponse:
        _require_control_auth(authorization)
        proposal = _build_topology_proposal(request)
        persistence = None
        if request.persist:
            persisted = await persist_topology_proposal(
                topology,
                governance,
                workspace_key=request.workspace_id,
                proposal=proposal,
            )
            persistence = persisted.to_json()
        return TopologyProposalResponse(
            proposal=proposal.to_json(),
            persistence=persistence,
        )

    @app.post("/v1/topology/apply", response_model=TopologyApplyResponse)
    async def apply_topology_operation(
        request: TopologyApplyRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> TopologyApplyResponse:
        _require_control_auth(authorization)
        await _check_topology_activation_gate_for_api(
            activation_gate,
            request=request,
        )
        result = await topology.apply_operation(
            workspace_key=request.workspace_id,
            skill_graph_operation_id=request.skill_graph_operation_id,
            applied_by=request.applied_by,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=result.to_json(),
            )
        return TopologyApplyResponse(**result.to_json())

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
        result = await run_pending_proposal_gates_with_trace(
            evaluations,
            observability=observability,
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 250)),
            trace_id=request.trace_id,
            parent_span_id=request.span_id or request.parent_span_id,
            source="api",
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

    @app.post("/v1/drift/false-positive", response_model=DriftFalsePositiveResponse)
    async def mark_drift_false_positive(
        request: DriftFalsePositiveRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> DriftFalsePositiveResponse:
        _require_control_auth(authorization)
        result = await contracts.mark_drift_false_positive(
            workspace_key=request.workspace_id,
            environment_contract_id=request.environment_contract_id,
            operator_id=request.operator_id,
            rationale=request.rationale,
        )
        if result.status == "not_found":
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=result.to_json(),
            )
        return DriftFalsePositiveResponse(result=result.to_json())

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
        span = await observability.start_span(
            workspace_key=request.workspace_id or "default",
            operation_name="writer.apply",
            operation_kind="writer",
            trace_id=request.trace_id,
            parent_span_id=request.span_id or request.parent_span_id,
            safe_attributes={
                "source": "api",
                "activation_gate_required": request.activation_gate_required,
                "manifest_relative_path": request.manifest_relative_path,
            },
            object_refs=[
                {
                    "object_type": "evolution_transaction",
                    "object_id": str(request.evolution_transaction_id),
                }
            ],
        )
        try:
            await _check_writer_activation_gate_for_api(
                activation_gate,
                request=request,
                staging_root=staging_root,
            )
            artifact = await apply_staged_manifest_with_governance(
                governance,
                evolution_transaction_id=request.evolution_transaction_id,
                staging_root=staging_root,
                workspace_root=workspace_root,
                archive_root=archive_root,
                manifest_relative_path=request.manifest_relative_path,
            )
        except HTTPException as error:
            await observability.finish_span(
                span_id=span.span_id,
                status="error",
                safe_attributes={
                    "status_code": error.status_code,
                    "error": str(error.detail)[:500],
                },
            )
            raise
        except (ValueError, FileExistsError, FileNotFoundError) as error:
            await observability.finish_span(
                span_id=span.span_id,
                status="error",
                safe_attributes={"error": str(error)[:500]},
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        await observability.finish_span(
            span_id=span.span_id,
            status="ok",
            safe_attributes={
                "slug": artifact.slug,
                "file_count": len(artifact.files),
                "previous_snapshot": artifact.previous_snapshot is not None,
            },
            object_refs=[
                {
                    "object_type": "evolution_transaction",
                    "object_id": str(request.evolution_transaction_id),
                },
                {
                    "object_type": "compiled_skill_file",
                    "relative_path": artifact.active_relative_path,
                },
            ],
        )
        return WriterArtifactResponse(artifact=artifact.to_json())

    @app.post("/v1/writer/rollback", response_model=WriterArtifactResponse)
    async def rollback_writer_manifest(
        request: WriterRollbackRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> WriterArtifactResponse:
        _require_control_auth(authorization)
        workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
        span = await observability.start_span(
            workspace_key=request.workspace_id or "default",
            operation_name="writer.rollback",
            operation_kind="writer",
            trace_id=request.trace_id,
            parent_span_id=request.span_id or request.parent_span_id,
            safe_attributes={
                "source": "api",
                "archive_manifest_relative_path": request.archive_manifest_relative_path,
            },
            object_refs=[
                {
                    "object_type": "evolution_transaction",
                    "object_id": str(request.evolution_transaction_id),
                }
            ],
        )
        try:
            artifact = await rollback_active_skill_with_governance(
                governance,
                evolution_transaction_id=request.evolution_transaction_id,
                workspace_root=workspace_root,
                archive_root=archive_root,
                archive_manifest_relative_path=request.archive_manifest_relative_path,
            )
        except (ValueError, FileExistsError, FileNotFoundError) as error:
            await observability.finish_span(
                span_id=span.span_id,
                status="error",
                safe_attributes={"error": str(error)[:500]},
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        await observability.finish_span(
            span_id=span.span_id,
            status="ok",
            safe_attributes={
                "slug": artifact.slug,
                "file_count": len(artifact.files),
            },
            object_refs=[
                {
                    "object_type": "evolution_transaction",
                    "object_id": str(request.evolution_transaction_id),
                },
                {
                    "object_type": "compiled_skill_file",
                    "relative_path": artifact.active_relative_path,
                },
            ],
        )
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
        if request.critical or request.status == "critical":
            broker_cache.invalidate(
                workspace_id=request.workspace_id,
                skill_ids=[str(request.skill_id)],
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
        broker_cache.invalidate(
            workspace_id=request.workspace_id,
            skill_ids=[str(request.skill_id)],
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
            min_support=max(2, min(request.min_support, 25)),
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
            trace_id=request.trace_id,
            span_id=request.span_id,
            parent_span_id=request.parent_span_id,
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
                embedding_profile_id=request.embedding_profile_id,
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
                embedding_profile_id=request.embedding_profile_id,
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
            embedding_profile_id=request.embedding_profile_id,
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
        if request.embedding_profile_key:
            if not request.workspace_id:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="workspace_id is required with embedding_profile_key",
                )
            profile = await profiles.get_embedding_profile(
                workspace_key=request.workspace_id,
                profile_key=request.embedding_profile_key,
            )
            if profile is None:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail="embedding profile not found",
                )
            embedder = _embedder_from_profile(profile, settings)
            embedding_model = profile.model
            embedding_profile_id = profile.profile_id
        else:
            try:
                embedder = build_text_embedder_from_settings(settings)
            except ValueError as error:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=str(error),
                ) from error
            embedding_model = request.embedding_model
            embedding_profile_id = None
        result = await generate_pending_embeddings(
            embeddings,
            embedder=embedder,
            workspace_key=request.workspace_id,
            embedding_model=embedding_model,
            embedding_profile_id=embedding_profile_id,
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
