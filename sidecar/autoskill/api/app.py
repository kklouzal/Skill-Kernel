from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from hmac import compare_digest
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from autoskill import __version__
from autoskill.core.audit import AuditRecord
from autoskill.core.config import effective_skillkernel_config, get_settings
from autoskill.core.events import IngestRequest, IngestResult
from autoskill.core.hashing import sha256_text
from autoskill.core.skillir import EffectSignature, SkillIR
from autoskill.db.activation import (
    ActivationGateStore,
    AsyncpgActivationGateStore,
    NullActivationGateStore,
)
from autoskill.db.attribution import AsyncpgAttributionStore, AttributionStore, NullAttributionStore
from autoskill.db.audit import AsyncpgAuditStore, AuditStore, NullAuditStore
from autoskill.db.broker_policy import (
    AsyncpgBrokerPolicyStore,
    BrokerPolicyStore,
    NullBrokerPolicyStore,
)
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
from autoskill.db.historical import (
    AsyncpgHistoricalImportStore,
    HistoricalChunkInput,
    HistoricalImportStore,
    HistoricalSourceInput,
    NullHistoricalImportStore,
)
from autoskill.db.jobs import AsyncpgJobStore, JobStore, NullJobStore
from autoskill.db.lifecycle import AsyncpgLifecycleStore, LifecycleStore, NullLifecycleStore
from autoskill.db.llm_invocations import (
    AsyncpgLLMInvocationStore,
    LLMInvocationStore,
    NullLLMInvocationStore,
)
from autoskill.db.memory import (
    AsyncpgMemoryGovernanceStore,
    MemoryGovernanceStore,
    NullMemoryGovernanceStore,
)
from autoskill.db.observability import (
    AsyncpgObservabilityStore,
    NullObservabilityStore,
    ObservabilityStore,
)
from autoskill.db.observatory_admin import (
    AsyncpgObservatoryAdminStore,
    NullObservatoryAdminStore,
    ObservatoryAdminStore,
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
from autoskill.db.usage import (
    AsyncpgUsageStore,
    NullUsageStore,
    UsageStore,
    UsageTopologyRecommendation,
)
from autoskill.db.utility import AsyncpgUtilityStore, NullUtilityStore, UtilityStore
from autoskill.services.broker import (
    BrokerCanaryFeedback,
    BrokerPolicy,
    BrokerReplayEpisode,
    BrokerReplayResult,
    ContextHintCache,
    ContextHintRequest,
    ContextHintResponse,
    bootstrap_context_hint,
    build_context_hint,
    evaluate_broker_canary_feedback,
    replay_broker_policy,
)
from autoskill.services.candidates import propose_candidate_skills
from autoskill.services.compiler import (
    DEFAULT_DESCRIPTION_MAX_CHARS,
    DEFAULT_MAX_CONTEXT_TOKENS,
    compile_skill_with_context_governance,
)
from autoskill.services.embedding_generation import (
    build_text_embedder_from_profile,
    build_text_embedder_from_settings,
    generate_pending_embeddings,
)
from autoskill.services.evaluation_runner import run_pending_proposal_gates_with_trace
from autoskill.services.historical_bootstrap import consolidate_historical_bootstrap
from autoskill.services.historical_discovery import discover_historical_sources
from autoskill.services.historical_import import import_historical_sources
from autoskill.services.llm import LLMClient
from autoskill.services.matching import SkillMatchRequest, match_existing_skills
from autoskill.services.observatory import (
    action_receipt,
    build_live_envelope,
    build_observatory_snapshot,
    object_microscope,
    search_observatory,
)
from autoskill.services.opportunity import mine_opportunities
from autoskill.services.profile_qualification import (
    ProfileQualificationError,
    qualify_embedding_profile,
    qualify_text_profile,
)
from autoskill.services.shadowing import detect_shadowing_events
from autoskill.services.skillir_migration import propose_skill_ir_migration
from autoskill.services.topology import (
    ComposeTopologyRequest,
    CreateTopologyRequest,
    DecomposeTopologyRequest,
    ImproveTopologyRequest,
    TopologySkill,
    persist_topology_proposal,
    propose_composition,
    propose_creation,
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
from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
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


class DeploymentReadinessResponse(BaseModel):
    workspace_id: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    checks: dict[str, object]


class EffectiveConfigResponse(BaseModel):
    skillkernel: dict[str, object]


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
    misfire_policy: str = "coalesce"


class ScheduleUpsertResponse(BaseModel):
    created: bool
    schedule: dict[str, object]


class SchedulerTickResponse(BaseModel):
    due: int
    enqueued: int
    jobs: list[dict[str, object]]
    skipped: int = 0
    misfires_coalesced: int = 0
    lock_acquired: bool = True


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


class ObservabilityMetricsResponse(BaseModel):
    workspace_id: str | None
    captured_at: str
    window_minutes: int
    metrics: dict[str, object]
    dashboards: dict[str, object]


class ObservatoryConfigResponse(BaseModel):
    config: dict[str, object]


class ObservatorySnapshotResponse(BaseModel):
    snapshot: dict[str, object]


class ObservatorySearchResponse(BaseModel):
    query: str
    limit: int
    results: list[dict[str, object]]


class ObservatoryObjectResponse(BaseModel):
    object: dict[str, object]


class ObservatoryActionRequest(BaseModel):
    workspace_id: str
    action: str
    idempotency_key: str
    target: dict[str, object] = Field(default_factory=dict)
    reason: str | None = None
    confirmation: str | None = None
    dry_run: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)


class ObservatoryActionResponse(BaseModel):
    receipt: dict[str, object]


class ObservatoryCollectionResponse(BaseModel):
    collection: dict[str, object]


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
    endpoint_kind: str = "chat_completions"
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


class ModelProfileListResponse(BaseModel):
    profiles: list[dict[str, object]]


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


class HistoricalImportSourceItem(BaseModel):
    source_kind: str
    source_key: str
    fingerprint: str
    parser_version: str
    redaction_policy_version: str
    trust_level: str = "tainted"
    taint: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "discovered"


class HistoricalImportSourceUpsertRequest(BaseModel):
    workspace_id: str
    sources: list[HistoricalImportSourceItem]


class HistoricalImportSourceUpsertResponse(BaseModel):
    created: int
    updated: int
    sources: list[dict[str, object]]


class HistoricalImportSourceListResponse(BaseModel):
    sources: list[dict[str, object]]


class HistoricalImportChunkItem(BaseModel):
    source_kind: str
    source_key: str
    fingerprint: str
    item_key: str
    chunk_index: int
    redacted_text: str
    parser_version: str
    redaction_policy_version: str
    chunk_kind: str = "redacted_text"
    token_estimate: int = 0
    trust_level: str = "tainted"
    taint: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class HistoricalImportChunkRecordRequest(BaseModel):
    workspace_id: str
    chunks: list[HistoricalImportChunkItem]


class HistoricalImportChunkRecordResponse(BaseModel):
    created: int
    skipped: int
    chunks: list[dict[str, object]]


class HistoricalImportDiscoverRequest(BaseModel):
    workspace_id: str
    roots: list[Path]
    source_allowlist: list[str] | None = None
    source_denylist: list[str] | None = None
    max_files: int = 500
    max_bytes: int = 25_000_000
    preview_only: bool = True


class HistoricalImportDiscoverResponse(BaseModel):
    scanned_roots: int
    scanned_files: int
    skipped_files: int
    estimated_bytes: int
    oldest_mtime: str | None
    newest_mtime: str | None
    risk_classes: dict[str, int]
    source_counts: dict[str, int]
    items: list[dict[str, object]]
    upsert: dict[str, object] | None = None


class HistoricalImportParseRequest(BaseModel):
    workspace_id: str
    roots: list[Path]
    source_allowlist: list[str] | None = None
    source_denylist: list[str] | None = None
    max_files: int = 100
    max_bytes: int = 10_000_000
    max_chunks: int = 500
    idempotency_key: str = "historical-import:manual"


class HistoricalImportParseResponse(BaseModel):
    discovery: dict[str, object]
    run: dict[str, object]
    chunks: dict[str, object]
    parsed_sources: int
    skipped_sources: int
    parse_errors: list[dict[str, object]]


class HistoricalImportSourceRevokeRequest(BaseModel):
    workspace_id: str
    historical_import_source_id: UUID


class HistoricalImportSourceRevokeResponse(BaseModel):
    source: dict[str, object] | None
    sources_revoked: int
    chunks_revoked: int
    traversal: dict[str, object] | None = None
    revocation: dict[str, object] | None = None
    job: dict[str, object] | None = None


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


class ContextSkillIRCompileRequest(BaseModel):
    workspace_id: str
    skillir: SkillIR
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    candidate_id: UUID | None = None
    source_object_type: str = "skill_version"
    source_object_id: UUID | None = None
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    target_runtime_tokens: int = 350
    description_max_chars: int = DEFAULT_DESCRIPTION_MAX_CHARS
    require_probe_evidence: bool = False
    routing_equivalence_evidence: dict[str, object] = Field(default_factory=dict)
    regression_evidence: dict[str, object] = Field(default_factory=dict)


class ContextSkillIRCompileResponse(BaseModel):
    result: dict[str, object]


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


class ContextCompileRunRequest(BaseModel):
    workspace_id: str
    compiler_version: str
    input_skillir_hash: str
    output_manifest_hash: str
    actual_runtime_tokens: int
    status: str
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    candidate_id: UUID | None = None
    context_artifact_id: UUID | None = None
    model_assist_used: bool = False
    target_runtime_tokens: int | None = None
    compression_ratio: float | None = None
    semantic_equivalence_score: float | None = None
    reject_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextCompileRunResponse(BaseModel):
    run: dict[str, object]


class ContextBudgetEventRequest(BaseModel):
    workspace_id: str
    event_type: str
    decision: str
    skill_id: UUID | None = None
    skill_version_id: UUID | None = None
    context_artifact_id: UUID | None = None
    tokens_delta: int | None = None
    marginal_success_delta: float | None = None
    false_positive_load_delta: float | None = None
    ignored_load_delta: float | None = None
    shadowing_delta: float | None = None
    evidence: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextBudgetEventResponse(BaseModel):
    event: dict[str, object]


class SemanticCompressionTrialRequest(BaseModel):
    workspace_id: str
    source_tokens: int
    candidate_tokens: int
    preserved_requirements: int
    lost_requirements: int
    added_unsupported_requirements: int
    equivalence_score: float
    status: str
    skill_id: UUID | None = None
    source_revision_id: UUID | None = None
    candidate_revision_id: UUID | None = None
    source_context_artifact_id: UUID | None = None
    candidate_context_artifact_id: UUID | None = None
    target_probe_pass_rate: float | None = None
    regression_probe_pass_rate: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SemanticCompressionTrialResponse(BaseModel):
    trial: dict[str, object]


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
    creation_reasons: list[str] = Field(default_factory=list)
    improvement_reasons: list[str] = Field(default_factory=list)
    required_effects_by_component: dict[str, list[str]] | None = None
    coverage_requirements: list[str] | None = None
    persist: bool = True


class TopologyProposalResponse(BaseModel):
    proposal: dict[str, object]
    persistence: dict[str, object] | None = None


class TopologyUsageProposalRequest(BaseModel):
    workspace_id: str
    limit: int = 10
    min_support: int = 3
    min_success_count: int = 1
    max_failure_ratio: float = 0.25
    min_sequence_count: int = 1
    persist: bool = True


class TopologyUsageProposalResponse(BaseModel):
    recommendations_scanned: int
    proposals: list[dict[str, object]]
    skipped: list[dict[str, object]]


class TopologyMetricsResponse(BaseModel):
    workspace_id: str | None = None
    operations_by_kind: dict[str, dict[str, int]]
    trials_by_kind: dict[str, dict[str, int]]
    trials_by_operation_kind: dict[str, dict[str, dict[str, int]]]
    recent_operations: list[dict[str, object]]


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


class SkillIRMigrationProposalRequest(BaseModel):
    workspace_id: str
    source_revision_id: UUID
    source_skill_ir: dict[str, object]
    migration_reason: str
    compiler_version: str = "autoskill-compiler.v1.migration"
    persist: bool = True
    evolution_transaction_id: UUID | None = None


class SkillIRMigrationProposalResponse(BaseModel):
    scanned: int
    proposed: int
    skipped: int
    proposals: list[dict[str, object]]
    persistence: dict[str, object] | None = None


class HistoricalBootstrapConsolidateRequest(BaseModel):
    workspace_id: str
    limit: int = 250
    min_support: int = 2
    persist: bool = False
    evolution_transaction_id: UUID | None = None


class HistoricalBootstrapConsolidateResponse(BaseModel):
    scanned: int
    historical_scanned: int
    opportunities: dict[str, object]
    proposals: dict[str, object]
    activation_allowed: bool
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


class ProposalReviewResponse(BaseModel):
    workspace_id: str | None
    candidate_revisions: list[dict[str, object]]
    topology_operations: list[dict[str, object]]
    evaluations: list[dict[str, object]]
    summary: dict[str, object]


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
    contract_preflight: bool = True
    contract_preflight_limit: int = 250


class CurationRunResponse(BaseModel):
    scanned: int
    archived: int
    promoted: int
    merged: int
    planned: int = 0
    actions: list[dict[str, object]]
    contract_preflight: dict[str, object] | None = None


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


class BrokerPolicyUpsertRequest(BaseModel):
    workspace_id: str
    version: str
    policy: dict[str, object]
    status: str = "candidate"
    broker_policy_version_id: UUID | None = None


class BrokerPolicyResponse(BaseModel):
    policy_version: dict[str, object] | None


class BrokerPolicyActivateRequest(BaseModel):
    workspace_id: str
    broker_policy_version_id: UUID


class BrokerPolicyReplayRequest(BaseModel):
    workspace_id: str
    episodes: list[BrokerReplayEpisode] = Field(default_factory=list)
    policy: dict[str, object] | None = None
    version: str | None = None
    broker_policy_version_id: UUID | None = None
    executor_profile_id: UUID | None = None
    max_tokens: int = 800
    include_stored_episodes: bool = False
    stored_episode_tags: list[str] = Field(default_factory=list)
    stored_episode_limit: int = 100


class BrokerPolicyReplayResponse(BaseModel):
    replay: BrokerReplayResult


class BrokerReplayEpisodeRecordRequest(BaseModel):
    workspace_id: str
    episode_key: str
    redacted_user_intent: str
    expected_decision: str | None = None
    expected_skill_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    source_retrieval_log_id: UUID | None = None


class BrokerReplayEpisodeRecordResponse(BaseModel):
    episode: dict[str, object]


class BrokerReplayEpisodeListResponse(BaseModel):
    episodes: list[dict[str, object]]


class BrokerPolicyCanaryRequest(BaseModel):
    workspace_id: str
    broker_policy_version_id: UUID
    status: str | None = None
    reason: str | None = None
    metrics: dict[str, object] = {}
    replay: BrokerReplayResult | None = None


class BrokerPolicyCanaryResponse(BaseModel):
    feedback: BrokerCanaryFeedback
    policy_version: dict[str, object] | None


class BrokerPolicyReviewResponse(BaseModel):
    workspace_id: str
    review_status: str
    blockers: list[str]
    warnings: list[str]
    active_policy: dict[str, object] | None
    replay_corpus: dict[str, object]
    audit: dict[str, object]


class BrokerPolicyUsageProposalRequest(BaseModel):
    workspace_id: str
    limit: int = 10
    min_support: int = 3
    min_success_count: int = 1
    max_failure_ratio: float = 0.25
    min_sequence_count: int = 1
    persist: bool = False
    version_prefix: str = "usage-broker-policy"


class BrokerPolicyUsageProposalResponse(BaseModel):
    recommendations_scanned: int
    proposals: list[dict[str, object]]
    skipped: list[dict[str, object]]
    policy_version: dict[str, object] | None = None


class ActionAttributionCheckRequest(BaseModel):
    workspace_id: str
    session_id: str | None = None
    turn_id: str | None = None
    tool_call_id: str | None = None
    action_kind: str
    risk_tier: str
    verdict: str
    metrics: dict[str, object] = {}
    user_intent_hash: str | None = None
    contributing_skill_ids: list[UUID] = []
    contributing_memory_ids: list[UUID] = []
    contributing_evidence_ids: list[UUID] = []
    broker_policy_version_id: UUID | None = None
    counterfactual_kind: str | None = None


class ActionAttributionCheckResponse(BaseModel):
    check: dict[str, object]


class MemoryQuarantineRequest(BaseModel):
    workspace_id: str
    source_object_type: str
    source_object_id: UUID
    proposed_memory: dict[str, object]
    taint: dict[str, object] = Field(default_factory=dict)
    scanner_findings: dict[str, object] = Field(default_factory=dict)


class MemoryQuarantineDecisionRequest(BaseModel):
    workspace_id: str
    status: str
    operator_id: str | None = None
    rationale: str | None = None


class MemoryQuarantineResponse(BaseModel):
    memory: dict[str, object] | None


class MemoryQuarantineListResponse(BaseModel):
    memories: list[dict[str, object]]


class ControlFlowEventRequest(BaseModel):
    workspace_id: str
    source_kind: str
    influence_kind: str
    decision: dict[str, object]
    run_id: str | None = None
    source_id: UUID | None = None


class ControlFlowEventResponse(BaseModel):
    event: dict[str, object]


class ControlFlowEventListResponse(BaseModel):
    events: list[dict[str, object]]


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
    transaction_kind: str = "candidate_proposal",
) -> str:
    plan_hash = _candidate_transaction_plan_hash(
        workspace_key=workspace_key,
        proposals=proposals,
        transaction_kind=transaction_kind,
    )
    return f"{transaction_kind}:{plan_hash}"


def _candidate_transaction_plan_hash(
    *,
    workspace_key: str,
    proposals: list[dict[str, object]],
    transaction_kind: str = "candidate_proposal",
) -> str:
    payload = {
        "workspace_key": workspace_key,
        "transaction_kind": transaction_kind,
        "proposals": [
            {
                "candidate_slug": proposal.get("candidate_slug"),
                "compiled_sha256": proposal.get("compiled_sha256"),
                "evidence_ids": proposal.get("evidence_ids", []),
                "metadata": proposal.get("metadata", {}),
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


async def _persist_candidate_proposal_payload(
    candidates: CandidateStore,
    governance: GovernanceStore,
    *,
    workspace_key: str,
    proposals: list[object],
    proposal_payload: dict[str, object],
    transaction_kind: str,
    endpoint: str,
    evolution_transaction_id: UUID | None = None,
    policy_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    proposal_rows = proposal_payload.get("proposals", [])
    if not isinstance(proposal_rows, list):
        proposal_rows = []
    transaction = None
    transaction_id = evolution_transaction_id
    proposed_count = int(proposal_payload.get("proposed", 0) or 0)
    if proposed_count > 0 and transaction_id is None:
        started = await governance.start_transaction(
            workspace_key=workspace_key,
            transaction_kind=transaction_kind,
            idempotency_key=_candidate_transaction_idempotency_key(
                workspace_key=workspace_key,
                proposals=proposal_rows,
                transaction_kind=transaction_kind,
            ),
            plan_hash=_candidate_transaction_plan_hash(
                workspace_key=workspace_key,
                proposals=proposal_rows,
                transaction_kind=transaction_kind,
            ),
            actor="autoskill-sidecar",
            cause={
                "endpoint": endpoint,
                "mode": "propose_only",
            },
            source_evidence_ids=_candidate_source_evidence_ids(proposal_rows),
            policy_snapshot=policy_snapshot
            or {
                "runtime_file_writes": "forbidden",
                "candidate_state": "inactive",
                "activation_gate": "disabled",
            },
        )
        transaction = started.transaction
        transaction_id = started.transaction.evolution_transaction_id
    persistence = await candidates.persist_candidate_proposals(
        workspace_key=workspace_key,
        proposals=proposals,  # type: ignore[arg-type]
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
    return persistence_payload


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


class EmbeddingProductionValidationRequest(BaseModel):
    workspace_id: str
    profile_key: str
    probe_set_version: str | None = None
    generate_embeddings: bool = False
    generate_limit: int = 25


class EmbeddingProductionValidationResponse(BaseModel):
    qualified: bool
    qualification: dict[str, object]
    generation: dict[str, object] | None = None


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


def _build_historical_import_store() -> HistoricalImportStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgHistoricalImportStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullHistoricalImportStore()


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


def _build_utility_store(writer_workspace_root: Path | None = None) -> UtilityStore:
    settings = get_settings()
    if settings.database_url:
        workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
        return AsyncpgUtilityStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
            workspace_root=workspace_root,
            archive_root=archive_root,
        )
    return NullUtilityStore()


def _build_usage_store() -> UsageStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgUsageStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullUsageStore()


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


def _build_observatory_admin_store() -> ObservatoryAdminStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgObservatoryAdminStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullObservatoryAdminStore()


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


def _build_memory_governance_store() -> MemoryGovernanceStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgMemoryGovernanceStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullMemoryGovernanceStore()


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


def _build_broker_policy_store() -> BrokerPolicyStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgBrokerPolicyStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullBrokerPolicyStore()


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


def _require_admin_auth(
    authorization: str | None,
    roles_header: str | None = None,
    *,
    required_roles: set[str] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    token = settings.web_admin_token or settings.control_token
    if token:
        expected = f"Bearer {token}"
        if authorization is None or not compare_digest(authorization, expected):
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="invalid admin authorization",
            )
    roles = _admin_roles(roles_header)
    if required_roles and not required_roles.intersection(roles):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="admin role is not authorized for this action",
        )
    return {
        "subject": "observatory-admin",
        "roles": sorted(roles),
        "role": _dominant_role(roles),
        "auth_configured": bool(token),
    }


async def _require_admin_websocket_auth(websocket: WebSocket) -> dict[str, object]:
    settings = get_settings()
    token = settings.web_admin_token or settings.control_token
    if token:
        supplied = websocket.query_params.get("token")
        if supplied is None or not compare_digest(supplied, token):
            await websocket.close(code=1008)
            raise WebSocketDisconnect(code=1008)
    return {
        "subject": "observatory-admin",
        "roles": ["admin", "auditor", "operator", "viewer"],
        "role": "admin",
        "auth_configured": bool(token),
    }


def _admin_roles(roles_header: str | None) -> set[str]:
    allowed = {"viewer", "auditor", "operator", "admin"}
    if not roles_header:
        return set(allowed)
    parsed = {role.strip().lower() for role in roles_header.split(",") if role.strip()}
    roles = parsed.intersection(allowed)
    return roles or {"viewer"}


def _dominant_role(roles: set[str]) -> str:
    for role in ("admin", "operator", "auditor", "viewer"):
        if role in roles:
            return role
    return "viewer"


def _admin_static_dir() -> Path:
    settings = get_settings()
    configured = settings.web_admin_static_dir
    if configured.is_absolute():
        return configured
    cwd_candidate = (Path.cwd() / configured).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (Path(__file__).resolve().parents[1] / "observatory" / "dist").resolve()


def _admin_base_path() -> str:
    value = get_settings().web_admin_base_path.strip() or "/admin"
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/") or "/admin"


def _count_by(items: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        label = str(value) if value is not None else "none"
        counts[label] = counts.get(label, 0) + 1
    return counts


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


def _readiness_check(
    checks: dict[str, object],
    blockers: list[str],
    warnings: list[str],
    name: str,
    *,
    passed: bool,
    required: bool = True,
    detail: dict[str, object] | None = None,
) -> None:
    status = "passed" if passed else ("blocked" if required else "warning")
    checks[name] = {"status": status, **(detail or {})}
    if passed:
        return
    if required:
        blockers.append(name)
    else:
        warnings.append(name)


async def _deployment_readiness_report(
    *,
    workspace_id: str,
    jobs: JobStore,
    profiles: ProfileStore,
    broker_policies: BrokerPolicyStore,
    writer_workspace_root: Path | None = None,
    replay_tag: str = "production",
) -> DeploymentReadinessResponse:
    settings = get_settings()
    checks: dict[str, object] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    _readiness_check(
        checks,
        blockers,
        warnings,
        "database_configured",
        passed=bool(settings.database_url),
        detail={"configured": bool(settings.database_url)},
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "control_auth_configured",
        passed=bool(settings.control_token),
        detail={"configured": bool(settings.control_token)},
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "ingest_auth_configured",
        passed=bool(settings.ingest_token),
        detail={"configured": bool(settings.ingest_token)},
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "redaction_before_storage_and_embedding",
        passed=settings.redact_before_store and settings.redact_before_embed,
        detail={
            "redact_before_store": settings.redact_before_store,
            "redact_before_embed": settings.redact_before_embed,
        },
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "runtime_context_broker_enabled",
        passed=settings.runtime_context_broker_enabled,
        detail={
            "enabled": settings.runtime_context_broker_enabled,
            "timeout_ms": settings.runtime_context_timeout_ms,
            "max_tokens": settings.max_context_hint_tokens,
        },
    )

    try:
        _writer_roots(writer_workspace_root)
        _readiness_check(
            checks,
            blockers,
            warnings,
            "writer_roots_contained",
            passed=True,
            detail={
                "active_root": str(settings.active_root),
                "staging_root": str(settings.staging_root),
                "archive_root": str(settings.archive_root),
            },
        )
    except HTTPException as error:
        _readiness_check(
            checks,
            blockers,
            warnings,
            "writer_roots_contained",
            passed=False,
            detail={"error": str(error.detail)},
        )

    executor_profiles = await profiles.list_executor_profiles(
        workspace_key=workspace_id,
        status="active",
        limit=500,
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "active_executor_profile",
        passed=bool(executor_profiles),
        detail={"count": len(executor_profiles)},
    )

    model_profiles = await profiles.list_model_profiles(
        workspace_key=workspace_id,
        limit=500,
    )
    qualified_model_profiles = [
        profile
        for profile in model_profiles
        if profile.status in {"active", "qualified", "qualified_autonomous"}
    ]
    _readiness_check(
        checks,
        blockers,
        warnings,
        "qualified_text_model_profile",
        passed=bool(qualified_model_profiles),
        detail={
            "count": len(qualified_model_profiles),
            "profile_keys": [profile.profile_key for profile in qualified_model_profiles],
        },
    )

    embedding_profiles = await profiles.list_embedding_profiles(
        workspace_key=workspace_id,
        limit=500,
    )
    active_embedding_profiles = [
        profile for profile in embedding_profiles if profile.status == "active"
    ]
    _readiness_check(
        checks,
        blockers,
        warnings,
        "active_embedding_profile",
        passed=bool(active_embedding_profiles),
        detail={
            "count": len(active_embedding_profiles),
            "profile_keys": [profile.profile_key for profile in active_embedding_profiles],
            "dimensions": [profile.embedding_dim for profile in active_embedding_profiles],
        },
    )

    active_policy = await broker_policies.get_active_policy(workspace_key=workspace_id)
    _readiness_check(
        checks,
        blockers,
        warnings,
        "active_broker_policy",
        passed=active_policy is not None,
        detail={
            "version": active_policy.version if active_policy else None,
            "broker_policy_version_id": (
                str(active_policy.broker_policy_version_id) if active_policy else None
            ),
        },
    )

    replay_tags = [replay_tag] if replay_tag else []
    replay_episodes = await broker_policies.list_replay_episodes(
        workspace_key=workspace_id,
        tags=replay_tags,
        limit=1,
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "broker_replay_corpus",
        passed=bool(replay_episodes),
        detail={"tag": replay_tag, "sampled": len(replay_episodes)},
    )

    job_summary = await jobs.summary(workspace_key=workspace_id)
    _readiness_check(
        checks,
        blockers,
        warnings,
        "job_queue_has_no_failed_jobs",
        passed=job_summary.counts.get("failed", 0) == 0,
        required=False,
        detail={"counts": job_summary.counts, "by_kind": job_summary.by_kind},
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "worker_concurrency_configured",
        passed=(
            settings.worker_scheduler_concurrency > 0
            and settings.worker_maintenance_concurrency > 0
            and settings.worker_mutation_concurrency > 0
        ),
        detail={
            "scheduler": settings.worker_scheduler_concurrency,
            "maintenance": settings.worker_maintenance_concurrency,
            "mutation": settings.worker_mutation_concurrency,
        },
    )

    return DeploymentReadinessResponse(
        workspace_id=workspace_id,
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )


def _embedder_from_profile(profile: object, settings: object):
    try:
        return build_text_embedder_from_profile(
            profile,
            embedding_api_key=getattr(settings, "embedding_api_key", None),
            embedding_api_base_url=getattr(settings, "embedding_api_base_url", None),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


async def _broker_semantic_embedder(
    profiles: ProfileStore,
    settings: object,
    *,
    workspace_id: str,
):
    active_profile = await profiles.get_active_embedding_profile(workspace_key=workspace_id)
    if active_profile is not None:
        return _embedder_from_profile(active_profile, settings), active_profile.profile_id
    if getattr(settings, "embedding_provider", "hash") == "hash":
        return build_text_embedder_from_settings(settings), None
    return None, None


def _worker_stores(
    *,
    jobs: JobStore,
    scheduler: SchedulerStore,
    evidence: EvidenceStore,
    external_skills: ExternalSkillStore,
    candidates: CandidateStore,
    embeddings: EmbeddingStore,
    retrieval: RetrievalStore,
    evaluations: EvaluationStore,
    audit: AuditStore,
    governance: GovernanceStore,
    utility: UtilityStore,
    usage: UsageStore,
    contracts: ContractStore,
    diagnostics: DiagnosticMomentumStore,
    attribution: AttributionStore,
    observability: ObservabilityStore,
    context_governance: ContextGovernanceStore,
    topology: TopologyStore,
    activation_gate: ActivationGateStore,
    profiles: ProfileStore,
    memory_governance: MemoryGovernanceStore,
    historical_import: HistoricalImportStore,
    writer_workspace_root: Path | None = None,
    external_skill_roots: list[Path] | None = None,
    historical_import_roots: list[Path] | None = None,
) -> WorkerStores:
    settings = get_settings()
    workspace_root, _staging_root, archive_root = _writer_roots(writer_workspace_root)
    return WorkerStores(
        jobs=jobs,
        scheduler=scheduler,
        evidence=evidence,
        external_skills=external_skills,
        candidates=candidates,
        historical_import=historical_import,
        embeddings=embeddings,
        retrieval=retrieval,
        evaluations=evaluations,
        audit=audit,
        governance=governance,
        utility=utility,
        usage=usage,
        contracts=contracts,
        diagnostics=diagnostics,
        attribution=attribution,
        context_governance=context_governance,
        topology=topology,
        activation_gate=activation_gate,
        observability=observability,
        profiles=profiles,
        memory_governance=memory_governance,
        embedding_api_key=getattr(settings, "embedding_api_key", None),
        embedding_api_base_url=getattr(settings, "embedding_api_base_url", None),
        workspace_root=workspace_root,
        archive_root=archive_root,
        external_skill_roots=external_skill_roots,
        historical_import_roots=historical_import_roots,
    )


def _topology_skill(payload: TopologySkillPayload) -> TopologySkill:
    return TopologySkill(
        slug=payload.slug,
        skill_id=payload.skill_id,
        effects=EffectSignature.model_validate(payload.effects),
    )


def _build_topology_proposal(request: TopologyProposalRequest):
    if request.operation_kind == "create":
        if request.proposed is None:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="create requires proposed skill",
            )
        return propose_creation(
            CreateTopologyRequest(
                proposed=_topology_skill(request.proposed),
                evidence_ids=request.evidence_ids,
                creation_reasons=request.creation_reasons or request.improvement_reasons,
            )
        )
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
                decomposition_reasons=request.improvement_reasons,
                coverage_requirements=request.coverage_requirements,
            )
        )
    raise HTTPException(
        status_code=http_status.HTTP_400_BAD_REQUEST,
        detail="operation_kind must be create, improve, compose, or decompose",
    )


def _topology_skill_from_usage_id(
    skill_id: UUID,
    recommendation: UsageTopologyRecommendation | None = None,
) -> TopologySkill:
    snapshot = _usage_skill_snapshot_for(recommendation, skill_id)
    if snapshot:
        effects = _effect_payload_from_usage_snapshot(snapshot)
        if effects:
            return TopologySkill(
                slug=str(snapshot.get("slug") or _usage_skill_fallback_slug(skill_id)),
                skill_id=skill_id,
                effects=EffectSignature(**effects),
            )
    short_id = str(skill_id)[:8]
    return TopologySkill(
        slug=_usage_skill_fallback_slug(skill_id),
        skill_id=skill_id,
        effects=EffectSignature(
            outputs=[f"usage-observed-output:{short_id}"],
            effects=[f"usage-observed-effect:{short_id}"],
        ),
    )


def _usage_skill_fallback_slug(skill_id: UUID) -> str:
    return f"usage-observed-skill-{str(skill_id)[:8]}"


def _usage_skill_snapshot_for(
    recommendation: UsageTopologyRecommendation | None,
    skill_id: UUID,
) -> dict[str, object]:
    if recommendation is None:
        return {}
    snapshots = recommendation.metadata.get("skill_snapshots", [])
    if not isinstance(snapshots, list):
        return {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        if snapshot.get("skill_id") == str(skill_id):
            return snapshot
    return {}


def _effect_payload_from_usage_snapshot(
    snapshot: dict[str, object],
) -> dict[str, object]:
    effects = snapshot.get("effects")
    if not isinstance(effects, dict):
        return {}
    payload: dict[str, object] = {}
    for key in (
        "outputs",
        "effects",
        "state_delta",
        "side_effects",
        "termination",
        "unsafe_when",
        "failure_modes",
    ):
        values = (
            [value for value in effects.get(key, []) if isinstance(value, str) and value.strip()]
            if isinstance(effects.get(key), list)
            else []
        )
        if values:
            payload[key] = values
    idempotency = effects.get("idempotency")
    if isinstance(idempotency, str) and idempotency:
        payload["idempotency"] = idempotency
    return payload


def _effect_payload_with_extra(
    effects: dict[str, object],
    *,
    extra_effects: list[str],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in (
        "outputs",
        "effects",
        "state_delta",
        "side_effects",
        "termination",
        "unsafe_when",
        "failure_modes",
    ):
        values = _string_values(effects.get(key))
        if key == "effects":
            values = [*values, *extra_effects]
        if values:
            payload[key] = values
    idempotency = effects.get("idempotency")
    if isinstance(idempotency, str) and idempotency:
        payload["idempotency"] = idempotency
    return payload


def _topology_skill_payload_from_usage(
    skill: TopologySkill,
) -> TopologySkillPayload:
    return TopologySkillPayload(
        slug=skill.slug,
        skill_id=skill.skill_id,
        effects=skill.effects.model_dump(mode="json"),
    )


def _usage_skill_snapshots(
    recommendation: UsageTopologyRecommendation,
) -> list[dict[str, object]]:
    snapshots = recommendation.metadata.get("skill_snapshots", [])
    return [snapshot for snapshot in snapshots if isinstance(snapshot, dict)]


def _usage_snapshot_signal_reasons(
    recommendation: UsageTopologyRecommendation,
) -> list[str]:
    reasons: list[str] = []
    for snapshot in _usage_skill_snapshots(recommendation):
        if snapshot.get("description"):
            reasons.append("current_skillir_description_present")
        contracts = snapshot.get("contracts")
        if isinstance(contracts, dict):
            for key in (
                "environment_contract_count",
                "runtime_guard_count",
                "support_artifact_count",
            ):
                count = contracts.get(key)
                if isinstance(count, int) and count > 0:
                    reasons.append(f"{key}:{count}")
        body_index = snapshot.get("body_index")
        if isinstance(body_index, dict):
            document_count = body_index.get("document_count")
            if isinstance(document_count, int) and document_count > 0:
                reasons.append(f"body_index_document_count:{document_count}")
            for kind in body_index.get("document_kinds", []):
                if isinstance(kind, str) and kind.strip():
                    reasons.append(f"body_index_kind:{kind.strip()}")
    return reasons


def _usage_signal_reasons(recommendation: UsageTopologyRecommendation) -> list[str]:
    reasons = [
        value
        for value in (
            recommendation.metadata.get("topology_signal"),
            *recommendation.metadata.get("suggested_context_actions", []),
        )
        if isinstance(value, str) and value.strip()
    ]
    if recommendation.failure_count:
        reasons.append(f"failure_count:{recommendation.failure_count}")
    context_signal_count = recommendation.metadata.get("context_signal_count")
    if context_signal_count:
        reasons.append(f"context_signal_count:{context_signal_count}")
    token_waste = recommendation.metadata.get("token_waste")
    if token_waste:
        reasons.append(f"token_waste:{token_waste}")
    avg_context_value = recommendation.metadata.get("avg_context_value_per_token")
    if isinstance(avg_context_value, int | float):
        reasons.append(f"avg_context_value_per_token:{avg_context_value:.6g}")
    min_context_value = recommendation.metadata.get("min_context_value_per_token")
    if isinstance(min_context_value, int | float):
        reasons.append(f"min_context_value_per_token:{min_context_value:.6g}")
    reasons.extend(_usage_snapshot_signal_reasons(recommendation))
    return sorted(set(reasons)) or ["usage-backed topology signal"]


def _usage_broker_policy_review_actions(
    recommendation: UsageTopologyRecommendation,
) -> list[dict[str, object]]:
    context_actions = [
        action
        for action in recommendation.metadata.get("suggested_context_actions", [])
        if action in {"broker_abstain", "tighten_description"}
    ]
    if not context_actions:
        return []
    subject_skill_ids = recommendation.metadata.get("subject_skill_ids")
    if not isinstance(subject_skill_ids, list) or not subject_skill_ids:
        subject_skill_ids = [str(skill_id) for skill_id in recommendation.skill_ids]
    reason_codes = _usage_signal_reasons(recommendation)
    common = {
        "schema": "autoskill.broker_policy_usage_review.v1",
        "status": "operator_review_required",
        "source": "usage.aggregate",
        "cluster_key_hash": sha256_text(recommendation.cluster_key),
        "skill_usage_cluster_id": (
            str(recommendation.skill_usage_cluster_id)
            if recommendation.skill_usage_cluster_id
            else None
        ),
        "subject_skill_ids": [str(skill_id) for skill_id in subject_skill_ids],
        "evidence_ids": [str(evidence_id) for evidence_id in recommendation.evidence_ids],
        "recommended_operation": recommendation.recommended_operation,
        "support_count": recommendation.support_count,
        "failure_count": recommendation.failure_count,
        "sequence_count": recommendation.sequence_count,
        "operation_score": recommendation.operation_score,
        "context_signal_count": recommendation.metadata.get("context_signal_count", 0),
        "token_waste": recommendation.metadata.get("token_waste", 0),
        "avg_context_value_per_token": recommendation.metadata.get("avg_context_value_per_token"),
        "min_context_value_per_token": recommendation.metadata.get("min_context_value_per_token"),
        "reason_codes": reason_codes,
    }
    return [{**common, "action": action} for action in context_actions]


def _broker_policy_with_usage_review_actions(
    base_policy: dict[str, object],
    *,
    review_actions: list[dict[str, object]],
) -> dict[str, object]:
    policy = json.loads(json.dumps(base_policy)) if base_policy else {}
    broker = policy.get("runtime_context_broker")
    if not isinstance(broker, dict):
        broker = {}
    existing = broker.get("usage_context_action_reviews", [])
    if not isinstance(existing, list):
        existing = []
    broker["usage_context_action_reviews"] = [*existing, *review_actions]
    policy["runtime_context_broker"] = broker
    return policy


def _usage_broker_policy_skip(
    recommendation: UsageTopologyRecommendation,
    *,
    reason: str,
) -> dict[str, object]:
    payload = recommendation.to_json()
    payload["skipped_reason"] = reason
    return payload


def _usage_subject_terms(subject_effects: dict[str, object]) -> list[str]:
    return [
        term
        for key in ("outputs", "effects", "state_delta", "termination")
        for term in _string_values(subject_effects.get(key))
    ]


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _usage_improvement_proposal_request(
    recommendation: UsageTopologyRecommendation,
) -> TopologyProposalRequest | None:
    if len(recommendation.skill_ids) != 1:
        return None
    subject = _topology_skill_from_usage_id(recommendation.skill_ids[0], recommendation)
    subject_effects = subject.effects.model_dump(mode="json")
    proposed_slug = (
        subject.slug[:36].strip("-") + "-improved-" + sha256_text(recommendation.cluster_key)[:12]
    )
    proposed_effects = _effect_payload_with_extra(
        subject_effects,
        extra_effects=[
            "usage-backed improvement candidate",
            "preserve current SkillIR contract while reducing negative outcomes",
        ],
    )
    return TopologyProposalRequest(
        workspace_id="",
        operation_kind="improve",
        subject=_topology_skill_payload_from_usage(subject),
        proposed=TopologySkillPayload(
            slug=proposed_slug,
            effects=proposed_effects,
        ),
        evidence_ids=[str(evidence_id) for evidence_id in recommendation.evidence_ids],
        improvement_reasons=_usage_signal_reasons(recommendation),
        persist=True,
    )


def _usage_decomposition_proposal_request(
    recommendation: UsageTopologyRecommendation,
) -> TopologyProposalRequest | None:
    if len(recommendation.skill_ids) != 1:
        return None
    subject = _topology_skill_from_usage_id(recommendation.skill_ids[0], recommendation)
    subject_effects = subject.effects.model_dump(mode="json")
    subject_terms = _usage_subject_terms(subject_effects)
    if not subject_terms:
        return None
    slug_suffix = sha256_text(recommendation.cluster_key)[:12]
    successors = [
        TopologySkillPayload(
            slug=f"usage-focused-{slug_suffix}",
            effects=_effect_payload_with_extra(
                subject_effects,
                extra_effects=[
                    "focused successor for confirmed matching contexts",
                    "preserve current SkillIR contract for positive routing cases",
                ],
            ),
        ),
        TopologySkillPayload(
            slug=f"usage-boundary-{slug_suffix}",
            effects=_effect_payload_with_extra(
                subject_effects,
                extra_effects=[
                    "broker abstain boundary for false-positive contexts",
                    "preserve current SkillIR contract while reducing context waste",
                ],
            ),
        ),
    ]
    return TopologyProposalRequest(
        workspace_id="",
        operation_kind="decompose",
        subject=_topology_skill_payload_from_usage(subject),
        successors=successors,
        coverage_requirements=subject_terms,
        evidence_ids=[str(evidence_id) for evidence_id in recommendation.evidence_ids],
        improvement_reasons=_usage_signal_reasons(recommendation),
        persist=True,
    )


def _usage_topology_proposal_request(
    recommendation: UsageTopologyRecommendation,
) -> TopologyProposalRequest | None:
    if not recommendation.accepted:
        return None
    if recommendation.recommended_operation == "improve":
        return _usage_improvement_proposal_request(recommendation)
    if recommendation.recommended_operation == "decompose":
        return _usage_decomposition_proposal_request(recommendation)
    if recommendation.recommended_operation != "compose":
        return None
    if len(recommendation.skill_ids) < 2:
        return None
    components = [
        _topology_skill_from_usage_id(skill_id, recommendation)
        for skill_id in recommendation.skill_ids
    ]
    output_terms = [
        term
        for component in components
        for term in (component.effects.outputs + component.effects.effects)
    ]
    composed_slug = "usage-composed-" + sha256_text(recommendation.cluster_key)[:12]
    return TopologyProposalRequest(
        workspace_id="",
        operation_kind="compose",
        components=[
            TopologySkillPayload(
                slug=component.slug,
                skill_id=component.skill_id,
                effects=component.effects.model_dump(mode="json"),
            )
            for component in components
        ],
        composed_output=TopologySkillPayload(
            slug=composed_slug,
            effects={
                "outputs": output_terms,
                "effects": [
                    "usage-backed composed workflow candidate",
                    f"usage support count: {recommendation.support_count}",
                ],
            },
        ),
        evidence_ids=[str(evidence_id) for evidence_id in recommendation.evidence_ids],
        required_effects_by_component={},
        persist=True,
    )


def _usage_recommendation_skip(
    recommendation: UsageTopologyRecommendation,
    *,
    reason: str,
) -> dict[str, object]:
    payload = recommendation.to_json()
    payload["skipped_reason"] = reason
    return payload


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
        require_context_compile_proof=True,
        context_compile_run_id=_uuid_from_json_object(
            manifest.get("context_gate"),
            "context_compile_run_id",
        ),
        context_artifact_id=_uuid_from_json_object(
            manifest.get("context_gate"),
            "context_artifact_id",
        ),
        compiled_text_hash=_string_from_json_object(manifest.get("context_gate"), "text_hash"),
        context_output_manifest_hash=_string_from_json_object(
            manifest.get("context_gate"),
            "context_output_manifest_hash",
        ),
    )
    if not readiness.allowed:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "message": "activation gate blocked writer apply",
                "readiness": readiness.to_json(),
            },
        )


async def _check_writer_activation_window_for_api(
    activation_window: object | None,
    *,
    governance: GovernanceStore,
    request: WriterApplyRequest,
    staging_root: Path,
) -> None:
    if activation_window is None:
        return
    manifest = _read_staged_writer_manifest_for_api(
        staging_root,
        request.manifest_relative_path,
    )
    active_relative_path = f"skills/autoskill/{manifest['slug']}"
    window = await _call_activation_window_store(
        activation_window,
        workspace_key=request.workspace_id or "default",
        active_relative_path=active_relative_path,
        manifest_relative_path=request.manifest_relative_path,
        evolution_transaction_id=request.evolution_transaction_id,
    )
    if bool(window.get("allowed", False)):
        return
    await governance.update_transaction_status(
        evolution_transaction_id=request.evolution_transaction_id,
        status="staged",
        metrics={
            "activation_deferred": True,
            "activation_window": window,
            "manifest_relative_path": request.manifest_relative_path,
            "active_relative_path": active_relative_path,
        },
    )
    raise HTTPException(
        status_code=http_status.HTTP_409_CONFLICT,
        detail={
            "message": "activation window unavailable; writer apply deferred",
            "activation_window": window,
            "active_relative_path": active_relative_path,
        },
    )


def _read_staged_writer_manifest_for_api(
    staging_root: Path,
    manifest_relative_path: str,
) -> dict[str, object]:
    try:
        manifest_path = resolve_contained(staging_root, manifest_relative_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        slug = str(manifest["slug"])
        if not slug:
            raise ValueError("missing slug")
        return manifest
    except (KeyError, ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"activation window could not read staged manifest: {error}",
        ) from error


async def _call_activation_window_store(
    activation_window: object,
    *,
    workspace_key: str,
    active_relative_path: str,
    manifest_relative_path: str,
    evolution_transaction_id: UUID,
) -> dict[str, object]:
    check = getattr(activation_window, "check_activation_window", None)
    if check is None:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="activation window store lacks check_activation_window",
        )
    result = await check(
        workspace_key=workspace_key,
        active_relative_path=active_relative_path,
        manifest_relative_path=manifest_relative_path,
        evolution_transaction_id=evolution_transaction_id,
    )
    if isinstance(result, dict):
        window = dict(result)
    else:
        to_json = getattr(result, "to_json", None)
        if to_json is not None:
            window = dict(to_json())
        else:
            window = {
                "allowed": bool(getattr(result, "allowed", False)),
                "reason": str(getattr(result, "reason", "")),
            }
    window["allowed"] = bool(window.get("allowed", False))
    return window


def _json_object(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _uuid_from_json_object(payload: object, key: str) -> UUID | None:
    value = _json_object(payload).get(key)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _string_from_json_object(payload: object, key: str) -> str | None:
    value = _json_object(payload).get(key)
    if value is None:
        return None
    return str(value)


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


async def _active_broker_policy(
    broker_policies: BrokerPolicyStore,
    workspace_id: str,
) -> BrokerPolicy:
    active = await broker_policies.get_active_policy(workspace_key=workspace_id)
    if active is None:
        return BrokerPolicy()
    return BrokerPolicy.from_artifact(
        version=active.version,
        policy=active.policy,
        broker_policy_version_id=active.broker_policy_version_id,
    )


async def _request_broker_policy(
    broker_policies: BrokerPolicyStore,
    request: BrokerPolicyReplayRequest,
) -> BrokerPolicy:
    if request.policy is not None:
        return BrokerPolicy.from_artifact(
            version=request.version or "inline.replay",
            policy=request.policy,
            broker_policy_version_id=request.broker_policy_version_id,
        )
    if request.broker_policy_version_id is not None:
        record = await broker_policies.get_policy_version(
            workspace_key=request.workspace_id,
            broker_policy_version_id=request.broker_policy_version_id,
        )
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker policy version not found",
            )
        return BrokerPolicy.from_artifact(
            version=record.version,
            policy=record.policy,
            broker_policy_version_id=record.broker_policy_version_id,
        )
    active = await broker_policies.get_active_policy(workspace_key=request.workspace_id)
    if active is None:
        return BrokerPolicy()
    return BrokerPolicy.from_artifact(
        version=active.version,
        policy=active.policy,
        broker_policy_version_id=active.broker_policy_version_id,
    )


async def _broker_replay_episodes(
    broker_policies: BrokerPolicyStore,
    request: BrokerPolicyReplayRequest,
) -> list[BrokerReplayEpisode]:
    episodes = list(request.episodes)
    if request.include_stored_episodes:
        stored = await broker_policies.list_replay_episodes(
            workspace_key=request.workspace_id,
            tags=request.stored_episode_tags,
            limit=max(1, min(request.stored_episode_limit, 500)),
        )
        episodes.extend(
            BrokerReplayEpisode(
                episode_id=record.episode_key,
                user_intent=record.redacted_user_intent,
                expected_decision=record.expected_decision,
                expected_skill_ids=[str(item) for item in record.expected_skill_ids],
                max_tokens=request.max_tokens,
            )
            for record in stored
        )
    if not episodes:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="broker replay requires explicit episodes or include_stored_episodes=true",
        )
    return episodes


def create_app(
    event_store: EventStore | None = None,
    job_store: JobStore | None = None,
    scheduler_store: SchedulerStore | None = None,
    evidence_store: EvidenceStore | None = None,
    external_skill_store: ExternalSkillStore | None = None,
    historical_import_store: HistoricalImportStore | None = None,
    retrieval_store: RetrievalStore | None = None,
    skill_store: SkillStore | None = None,
    embedding_store: EmbeddingStore | None = None,
    audit_store: AuditStore | None = None,
    attribution_store: AttributionStore | None = None,
    candidate_store: CandidateStore | None = None,
    evaluation_store: EvaluationStore | None = None,
    utility_store: UtilityStore | None = None,
    usage_store: UsageStore | None = None,
    contract_store: ContractStore | None = None,
    governance_store: GovernanceStore | None = None,
    lifecycle_store: LifecycleStore | None = None,
    observability_store: ObservabilityStore | None = None,
    observatory_admin_store: ObservatoryAdminStore | None = None,
    diagnostic_store: DiagnosticMomentumStore | None = None,
    profile_store: ProfileStore | None = None,
    llm_invocation_store: LLMInvocationStore | None = None,
    memory_governance_store: MemoryGovernanceStore | None = None,
    profile_qualification_store: ProfileQualificationStore | None = None,
    llm_client: LLMClient | None = None,
    compatibility_store: CompatibilityStore | None = None,
    context_governance_store: ContextGovernanceStore | None = None,
    broker_policy_store: BrokerPolicyStore | None = None,
    topology_store: TopologyStore | None = None,
    activation_gate_store: ActivationGateStore | None = None,
    activation_window_store: object | None = None,
    writer_workspace_root: Path | None = None,
    external_skill_roots: list[Path] | None = None,
    historical_import_roots: list[Path] | None = None,
) -> FastAPI:
    store = event_store or _build_event_store()
    jobs = job_store or _build_job_store()
    scheduler = scheduler_store or _build_scheduler_store()
    evidence = evidence_store or _build_evidence_store()
    external_skills = external_skill_store or _build_external_skill_store()
    historical_import = historical_import_store or _build_historical_import_store()
    retrieval = retrieval_store or _build_retrieval_store()
    skills = skill_store or _build_skill_store()
    embeddings = embedding_store or _build_embedding_store()
    audit = audit_store or _build_audit_store()
    attribution = attribution_store or _build_attribution_store()
    candidates = candidate_store or _build_candidate_store()
    evaluations = evaluation_store or _build_evaluation_store()
    utility = utility_store or _build_utility_store(writer_workspace_root)
    usage = usage_store or _build_usage_store()
    contracts = contract_store or _build_contract_store()
    governance = governance_store or _build_governance_store()
    lifecycle = lifecycle_store or _build_lifecycle_store(governance)
    observability = observability_store or _build_observability_store()
    observatory_admin = observatory_admin_store or _build_observatory_admin_store()
    diagnostics = diagnostic_store or _build_diagnostic_store()
    profiles = profile_store or _build_profile_store()
    llm_invocations = llm_invocation_store or _build_llm_invocation_store()
    memory_governance = memory_governance_store or _build_memory_governance_store()
    profile_qualifications = profile_qualification_store or _build_profile_qualification_store()
    text_llm = llm_client or LLMClient(
        profiles=profiles,
        invocations=llm_invocations,
        settings=get_settings(),
        observability=observability,
    )
    compatibility = compatibility_store or _build_compatibility_store()
    context_governance = context_governance_store or _build_context_governance_store()
    broker_policies = broker_policy_store or _build_broker_policy_store()
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
                historical_import,
                retrieval,
                skills,
                embeddings,
                audit,
                attribution,
                candidates,
                evaluations,
                utility,
                usage,
                contracts,
                governance,
                lifecycle,
                observability,
                diagnostics,
                profiles,
                llm_invocations,
                memory_governance,
                profile_qualifications,
                compatibility,
                context_governance,
                broker_policies,
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

    @app.get("/v1/deployment/readiness", response_model=DeploymentReadinessResponse)
    async def deployment_readiness(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        replay_tag: str = "production",
    ) -> DeploymentReadinessResponse:
        _require_control_auth(authorization)
        return await _deployment_readiness_report(
            workspace_id=workspace_id,
            jobs=jobs,
            profiles=profiles,
            broker_policies=broker_policies,
            writer_workspace_root=writer_workspace_root,
            replay_tag=replay_tag,
        )

    @app.get("/v1/config/effective", response_model=EffectiveConfigResponse)
    async def effective_config(
        authorization: Annotated[str | None, Header()] = None,
    ) -> EffectiveConfigResponse:
        _require_control_auth(authorization)
        return EffectiveConfigResponse(skillkernel=effective_skillkernel_config(get_settings()))

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

    @app.post(
        "/v1/attribution/action-checks",
        response_model=ActionAttributionCheckResponse,
    )
    async def record_action_attribution_check(
        request: ActionAttributionCheckRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ActionAttributionCheckResponse:
        _require_ingest_auth(authorization)
        record = await attribution.record_action_check(
            workspace_key=request.workspace_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            tool_call_id=request.tool_call_id,
            action_kind=request.action_kind,
            risk_tier=request.risk_tier,
            verdict=request.verdict,
            metrics=request.metrics,
            user_intent_hash=request.user_intent_hash,
            contributing_skill_ids=request.contributing_skill_ids,
            contributing_memory_ids=request.contributing_memory_ids,
            contributing_evidence_ids=request.contributing_evidence_ids,
            broker_policy_version_id=request.broker_policy_version_id,
            counterfactual_kind=request.counterfactual_kind,
        )
        return ActionAttributionCheckResponse(check=record.to_json())

    @app.post("/v1/memory/quarantine", response_model=MemoryQuarantineResponse)
    async def quarantine_memory_candidate(
        request: MemoryQuarantineRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> MemoryQuarantineResponse:
        _require_control_auth(authorization)
        record = await memory_governance.quarantine_memory(
            workspace_key=request.workspace_id,
            source_object_type=request.source_object_type,
            source_object_id=request.source_object_id,
            proposed_memory=request.proposed_memory,
            taint=request.taint,
            scanner_findings=request.scanner_findings,
        )
        return MemoryQuarantineResponse(memory=record.to_json())

    @app.get("/v1/memory/quarantine", response_model=MemoryQuarantineListResponse)
    async def list_memory_quarantine(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> MemoryQuarantineListResponse:
        _require_control_auth(authorization)
        try:
            records = await memory_governance.list_memory_quarantine(
                workspace_key=workspace_id,
                status=status,
                limit=max(1, min(limit, 500)),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return MemoryQuarantineListResponse(
            memories=[record.to_json() for record in records],
        )

    @app.post(
        "/v1/memory/quarantine/{quarantine_id}/decision",
        response_model=MemoryQuarantineResponse,
    )
    async def decide_memory_quarantine(
        quarantine_id: UUID,
        request: MemoryQuarantineDecisionRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> MemoryQuarantineResponse:
        _require_control_auth(authorization)
        try:
            record = await memory_governance.decide_memory_quarantine(
                workspace_key=request.workspace_id,
                quarantine_id=quarantine_id,
                status=request.status,
                operator_id=request.operator_id,
                rationale=request.rationale,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="memory quarantine record not found",
            )
        return MemoryQuarantineResponse(memory=record.to_json())

    @app.post("/v1/control-flow/events", response_model=ControlFlowEventResponse)
    async def record_control_flow_event(
        request: ControlFlowEventRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ControlFlowEventResponse:
        _require_control_auth(authorization)
        try:
            event = await memory_governance.record_control_flow_event(
                workspace_key=request.workspace_id,
                source_kind=request.source_kind,
                influence_kind=request.influence_kind,
                decision=request.decision,
                run_id=request.run_id,
                source_id=request.source_id,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return ControlFlowEventResponse(event=event.to_json())

    @app.get("/v1/control-flow/events", response_model=ControlFlowEventListResponse)
    async def list_control_flow_events(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        source_kind: str | None = None,
        influence_kind: str | None = None,
        limit: int = 100,
    ) -> ControlFlowEventListResponse:
        _require_control_auth(authorization)
        try:
            events = await memory_governance.list_control_flow_events(
                workspace_key=workspace_id,
                source_kind=source_kind,
                influence_kind=influence_kind,
                limit=max(1, min(limit, 500)),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return ControlFlowEventListResponse(
            events=[event.to_json() for event in events],
        )

    @app.post("/v1/runtime/context-hint", response_model=ContextHintResponse)
    async def context_hint(request: ContextHintRequest) -> ContextHintResponse:
        settings = get_settings()
        if not settings.runtime_context_broker_enabled:
            return bootstrap_context_hint(request)
        policy = await _active_broker_policy(broker_policies, request.workspace_id)
        semantic_embedder, semantic_profile_id = await _broker_semantic_embedder(
            profiles,
            settings,
            workspace_id=request.workspace_id,
        )
        return await build_context_hint(
            retrieval,
            request,
            cache=broker_cache,
            context_governance=context_governance,
            compatibility=compatibility,
            semantic_embedder=semantic_embedder,
            semantic_embedding_profile_id=semantic_profile_id,
            policy=policy,
            memory_governance=memory_governance,
        )

    @app.get(
        "/v1/broker/policies/active",
        response_model=BrokerPolicyResponse,
    )
    async def get_active_broker_policy(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
    ) -> BrokerPolicyResponse:
        _require_control_auth(authorization)
        active = await broker_policies.get_active_policy(workspace_key=workspace_id)
        return BrokerPolicyResponse(
            policy_version=active.to_json() if active else None,
        )

    @app.post(
        "/v1/broker/policies",
        response_model=BrokerPolicyResponse,
    )
    async def upsert_broker_policy(
        request: BrokerPolicyUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerPolicyResponse:
        _require_control_auth(authorization)
        if request.status not in {"candidate", "active"}:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="status must be candidate or active",
            )
        record = await broker_policies.upsert_policy_version(
            workspace_key=request.workspace_id,
            version=request.version,
            policy=request.policy,
            status=request.status,
            broker_policy_version_id=request.broker_policy_version_id,
        )
        broker_cache.invalidate(workspace_id=request.workspace_id)
        return BrokerPolicyResponse(policy_version=record.to_json())

    @app.post(
        "/v1/broker/policies/activate",
        response_model=BrokerPolicyResponse,
    )
    async def activate_broker_policy(
        request: BrokerPolicyActivateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerPolicyResponse:
        _require_control_auth(authorization)
        record = await broker_policies.activate_policy_version(
            workspace_key=request.workspace_id,
            broker_policy_version_id=request.broker_policy_version_id,
        )
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker policy version not found",
            )
        broker_cache.invalidate(workspace_id=request.workspace_id)
        return BrokerPolicyResponse(policy_version=record.to_json())

    @app.post(
        "/v1/broker/policies/replay",
        response_model=BrokerPolicyReplayResponse,
    )
    async def replay_broker_policy_route(
        request: BrokerPolicyReplayRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerPolicyReplayResponse:
        _require_control_auth(authorization)
        policy = await _request_broker_policy(broker_policies, request)
        episodes = await _broker_replay_episodes(broker_policies, request)
        settings = get_settings()
        semantic_embedder, semantic_profile_id = await _broker_semantic_embedder(
            profiles,
            settings,
            workspace_id=request.workspace_id,
        )
        replay = await replay_broker_policy(
            retrieval,
            ContextHintRequest(
                workspace_id=request.workspace_id,
                executor_profile_id=request.executor_profile_id,
                max_tokens=request.max_tokens,
            ),
            episodes=episodes,
            policy=policy,
            compatibility=compatibility,
            semantic_embedder=semantic_embedder,
            semantic_embedding_profile_id=semantic_profile_id,
        )
        return BrokerPolicyReplayResponse(replay=replay)

    @app.post(
        "/v1/broker/replay-episodes",
        response_model=BrokerReplayEpisodeRecordResponse,
    )
    async def record_broker_replay_episode(
        request: BrokerReplayEpisodeRecordRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerReplayEpisodeRecordResponse:
        _require_control_auth(authorization)
        episode = await broker_policies.record_replay_episode(
            workspace_key=request.workspace_id,
            episode_key=request.episode_key,
            redacted_user_intent=request.redacted_user_intent,
            expected_decision=request.expected_decision,
            expected_skill_ids=request.expected_skill_ids,
            tags=request.tags,
            metadata=request.metadata,
            source_retrieval_log_id=request.source_retrieval_log_id,
        )
        return BrokerReplayEpisodeRecordResponse(episode=episode.to_json())

    @app.get(
        "/v1/broker/replay-episodes",
        response_model=BrokerReplayEpisodeListResponse,
    )
    async def list_broker_replay_episodes(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        tags: Annotated[list[str] | None, Query()] = None,
        limit: int = 100,
    ) -> BrokerReplayEpisodeListResponse:
        _require_control_auth(authorization)
        episodes = await broker_policies.list_replay_episodes(
            workspace_key=workspace_id,
            tags=tags or [],
            limit=max(1, min(limit, 500)),
        )
        return BrokerReplayEpisodeListResponse(
            episodes=[episode.to_json() for episode in episodes],
        )

    @app.post(
        "/v1/broker/policies/canary",
        response_model=BrokerPolicyCanaryResponse,
    )
    async def record_broker_policy_canary(
        request: BrokerPolicyCanaryRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerPolicyCanaryResponse:
        _require_control_auth(authorization)
        feedback = evaluate_broker_canary_feedback(
            replay=request.replay,
            metrics=request.metrics,
            status=request.status,
        )
        record = await broker_policies.record_canary_feedback(
            workspace_key=request.workspace_id,
            broker_policy_version_id=request.broker_policy_version_id,
            status=feedback.status,
            metrics=feedback.metrics,
            reason=request.reason or ",".join(feedback.reason_codes) or None,
        )
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker policy version not found",
            )
        broker_cache.invalidate(workspace_id=request.workspace_id)
        return BrokerPolicyCanaryResponse(
            feedback=feedback,
            policy_version=record.to_json(),
        )

    @app.get(
        "/v1/broker/policies/review",
        response_model=BrokerPolicyReviewResponse,
    )
    async def review_broker_policy(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        replay_limit: int = 100,
        audit_limit: int = 100,
    ) -> BrokerPolicyReviewResponse:
        _require_control_auth(authorization)
        bounded_replay_limit = max(1, min(replay_limit, 500))
        bounded_audit_limit = max(1, min(audit_limit, 1000))
        active_policy = await broker_policies.get_active_policy(workspace_key=workspace_id)
        replay_episodes = await broker_policies.list_replay_episodes(
            workspace_key=workspace_id,
            tags=[],
            limit=bounded_replay_limit,
        )
        production_replay_episodes = await broker_policies.list_replay_episodes(
            workspace_key=workspace_id,
            tags=["production"],
            limit=bounded_replay_limit,
        )
        audit_records = await audit.list_recent(
            workspace_key=workspace_id,
            limit=bounded_audit_limit,
        )
        audit_chain_valid = await audit.verify_chain(
            workspace_key=workspace_id,
            limit=bounded_audit_limit,
        )

        blockers: list[str] = []
        warnings: list[str] = []
        if active_policy is None:
            blockers.append("active broker policy is missing")
        elif active_policy.status != "active":
            blockers.append("active broker policy is not active")
        policy_feedback = active_policy.policy.get("runtime_feedback", {}) if active_policy else {}
        last_canary = (
            policy_feedback.get("last_canary", {}) if isinstance(policy_feedback, dict) else {}
        )
        if isinstance(last_canary, dict) and last_canary.get("status") == "critical":
            blockers.append("latest broker policy canary is critical")
        if not replay_episodes:
            warnings.append("broker replay corpus is empty")
        if not production_replay_episodes:
            warnings.append("production-tagged broker replay corpus is empty")
        if not audit_chain_valid:
            blockers.append("audit hash chain failed bounded verification")

        review_status = "blocked" if blockers else "warning" if warnings else "pass"
        return BrokerPolicyReviewResponse(
            workspace_id=workspace_id,
            review_status=review_status,
            blockers=blockers,
            warnings=warnings,
            active_policy=active_policy.to_json() if active_policy else None,
            replay_corpus={
                "sampled_total": len(replay_episodes),
                "sampled_production": len(production_replay_episodes),
                "limit": bounded_replay_limit,
                "episode_keys": [episode.episode_key for episode in replay_episodes[:25]],
            },
            audit={
                "sampled_records": len(audit_records),
                "limit": bounded_audit_limit,
                "chain_valid": audit_chain_valid,
            },
        )

    @app.post(
        "/v1/broker/policies/propose-from-usage",
        response_model=BrokerPolicyUsageProposalResponse,
    )
    async def propose_broker_policy_from_usage(
        request: BrokerPolicyUsageProposalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerPolicyUsageProposalResponse:
        _require_control_auth(authorization)
        recommendations = await usage.recommend_topology_operations(
            workspace_key=request.workspace_id,
            limit=request.limit,
            min_support=request.min_support,
            min_success_count=request.min_success_count,
            max_failure_ratio=request.max_failure_ratio,
            min_sequence_count=request.min_sequence_count,
        )
        proposals: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        review_actions: list[dict[str, object]] = []
        for recommendation in recommendations:
            if not recommendation.accepted:
                skipped.append(
                    _usage_broker_policy_skip(
                        recommendation,
                        reason="recommendation blocked by usage thresholds",
                    )
                )
                continue
            actions = _usage_broker_policy_review_actions(recommendation)
            if not actions:
                skipped.append(
                    _usage_broker_policy_skip(
                        recommendation,
                        reason="usage recommendation has no broker policy action",
                    )
                )
                continue
            review_actions.extend(actions)
            proposals.append(
                {
                    "recommendation": recommendation.to_json(),
                    "review_actions": actions,
                }
            )

        policy_version = None
        if request.persist and review_actions:
            active_policy = await broker_policies.get_active_policy(
                workspace_key=request.workspace_id,
            )
            base_policy = active_policy.policy if active_policy else {}
            candidate_policy = _broker_policy_with_usage_review_actions(
                base_policy,
                review_actions=review_actions,
            )
            policy_hash = sha256_text(json.dumps(candidate_policy, sort_keys=True))[:12]
            record = await broker_policies.upsert_policy_version(
                workspace_key=request.workspace_id,
                version=f"{request.version_prefix}.{policy_hash}",
                policy=candidate_policy,
                status="candidate",
            )
            policy_version = record.to_json()

        return BrokerPolicyUsageProposalResponse(
            recommendations_scanned=len(recommendations),
            proposals=proposals,
            skipped=skipped,
            policy_version=policy_version,
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

    @app.get(
        "/v1/historical-import/sources",
        response_model=HistoricalImportSourceListResponse,
    )
    async def list_historical_import_sources(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> HistoricalImportSourceListResponse:
        _require_control_auth(authorization)
        try:
            listed = await historical_import.list_sources(
                workspace_key=workspace_id,
                status=status,
                limit=max(1, min(limit, 500)),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return HistoricalImportSourceListResponse(sources=[source.to_json() for source in listed])

    @app.post(
        "/v1/historical-import/sources",
        response_model=HistoricalImportSourceUpsertResponse,
    )
    async def upsert_historical_import_sources(
        request: HistoricalImportSourceUpsertRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalImportSourceUpsertResponse:
        _require_control_auth(authorization)
        try:
            result = await historical_import.upsert_sources(
                workspace_key=request.workspace_id,
                sources=[
                    HistoricalSourceInput(
                        source_kind=item.source_kind,
                        source_key=item.source_key,
                        fingerprint=item.fingerprint,
                        parser_version=item.parser_version,
                        redaction_policy_version=item.redaction_policy_version,
                        trust_level=item.trust_level,
                        taint=item.taint,
                        metadata=item.metadata,
                        status=item.status,
                    )
                    for item in request.sources
                ],
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return HistoricalImportSourceUpsertResponse(**result.to_json())

    @app.post(
        "/v1/historical-import/discover",
        response_model=HistoricalImportDiscoverResponse,
    )
    async def discover_historical_import_sources(
        request: HistoricalImportDiscoverRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalImportDiscoverResponse:
        _require_control_auth(authorization)
        try:
            inventory = await discover_historical_sources(
                historical_import,
                workspace_key=request.workspace_id,
                roots=request.roots,
                source_allowlist=(
                    set(request.source_allowlist) if request.source_allowlist is not None else None
                ),
                source_denylist=(
                    set(request.source_denylist) if request.source_denylist is not None else None
                ),
                max_files=max(1, min(request.max_files, 10_000)),
                max_bytes=max(1, min(request.max_bytes, 1_000_000_000)),
                preview_only=request.preview_only,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return HistoricalImportDiscoverResponse(**inventory.to_json())

    @app.post(
        "/v1/historical-import/parse",
        response_model=HistoricalImportParseResponse,
    )
    async def parse_historical_import_sources(
        request: HistoricalImportParseRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalImportParseResponse:
        _require_control_auth(authorization)
        try:
            result = await import_historical_sources(
                historical_import,
                workspace_key=request.workspace_id,
                roots=request.roots,
                source_allowlist=(
                    set(request.source_allowlist) if request.source_allowlist is not None else None
                ),
                source_denylist=(
                    set(request.source_denylist) if request.source_denylist is not None else None
                ),
                max_files=max(1, min(request.max_files, 10_000)),
                max_bytes=max(1, min(request.max_bytes, 1_000_000_000)),
                max_chunks=max(1, min(request.max_chunks, 20_000)),
                idempotency_key=request.idempotency_key,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return HistoricalImportParseResponse(**result.to_json())

    @app.post(
        "/v1/historical-import/sources/revoke",
        response_model=HistoricalImportSourceRevokeResponse,
    )
    async def revoke_historical_import_source(
        request: HistoricalImportSourceRevokeRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalImportSourceRevokeResponse:
        _require_control_auth(authorization)
        result = await historical_import.revoke_source(
            workspace_key=request.workspace_id,
            historical_import_source_id=request.historical_import_source_id,
        )
        payload = result.to_json()
        if result.source is not None:
            traversal = await governance.preview_revocation_traversal(
                workspace_key=request.workspace_id,
                root_object_type="historical_import_source",
                root_object_id=request.historical_import_source_id,
                max_depth=8,
                max_nodes=500,
            )
            traversal_json = traversal.to_json()
            revocation = await governance.request_revocation(
                workspace_key=request.workspace_id,
                request_kind="operator_revoke",
                root_object_type="historical_import_source",
                root_object_id=request.historical_import_source_id,
                traversal_summary={
                    **traversal_json,
                    "source": "historical_import_source_revoke",
                    "source_status": "revoked",
                    "chunks_revoked": result.chunks_revoked,
                },
            )
            queued = await jobs.enqueue_job(
                workspace_key=request.workspace_id,
                job_kind="revocations.invalidate",
                idempotency_key=(
                    "revocations.invalidate:historical_import_source:"
                    f"{request.historical_import_source_id}"
                ),
                payload={
                    "workspace_id": request.workspace_id,
                    "request_kind": "operator_revoke",
                    "limit": 10,
                },
                priority=20,
                max_attempts=3,
            )
            payload["traversal"] = traversal_json
            payload["revocation"] = revocation.to_json()
            payload["job"] = {
                "created": queued.created,
                "job": queued.job.to_json(),
            }
            await audit.append_record(
                AuditRecord(
                    action="historical_import.source_revoke",
                    subject_type="historical_import_source",
                    subject_id=str(request.historical_import_source_id),
                    details={
                        "chunks_revoked": result.chunks_revoked,
                        "impacted_count": traversal_json.get("impacted_count"),
                        "revocation_request_id": str(revocation.revocation_request_id),
                        "job_id": str(queued.job.job_id),
                    },
                ),
                workspace_key=request.workspace_id,
            )
        return HistoricalImportSourceRevokeResponse(**payload)

    @app.post(
        "/v1/historical-import/chunks",
        response_model=HistoricalImportChunkRecordResponse,
    )
    async def record_historical_import_chunks(
        request: HistoricalImportChunkRecordRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalImportChunkRecordResponse:
        _require_control_auth(authorization)
        try:
            result = await historical_import.record_chunks(
                workspace_key=request.workspace_id,
                chunks=[
                    HistoricalChunkInput(
                        source_kind=item.source_kind,
                        source_key=item.source_key,
                        fingerprint=item.fingerprint,
                        item_key=item.item_key,
                        chunk_index=item.chunk_index,
                        redacted_text=item.redacted_text,
                        parser_version=item.parser_version,
                        redaction_policy_version=item.redaction_policy_version,
                        chunk_kind=item.chunk_kind,
                        token_estimate=item.token_estimate,
                        trust_level=item.trust_level,
                        taint=item.taint,
                        metadata=item.metadata,
                    )
                    for item in request.chunks
                ],
            )
        except ValueError as error:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return HistoricalImportChunkRecordResponse(**result.to_json())

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
            misfire_policy=request.misfire_policy,
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
            skipped=result.skipped,
            misfires_coalesced=result.misfires_coalesced,
            lock_acquired=result.lock_acquired,
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
                candidates=candidates,
                embeddings=embeddings,
                retrieval=retrieval,
                evaluations=evaluations,
                audit=audit,
                governance=governance,
                utility=utility,
                usage=usage,
                contracts=contracts,
                diagnostics=diagnostics,
                attribution=attribution,
                observability=observability,
                context_governance=context_governance,
                topology=topology,
                activation_gate=activation_gate,
                profiles=profiles,
                memory_governance=memory_governance,
                historical_import=historical_import,
                writer_workspace_root=writer_workspace_root,
                external_skill_roots=external_skill_roots,
                historical_import_roots=historical_import_roots,
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

    @app.get("/v1/observability/metrics", response_model=ObservabilityMetricsResponse)
    async def observability_metrics(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        storage_limit: int = 25,
        audit_limit: int = 1000,
    ) -> ObservabilityMetricsResponse:
        _require_control_auth(authorization)
        bounded_window = max(1, min(window_minutes, 24 * 60))
        bounded_storage = max(1, min(storage_limit, 100))
        bounded_audit = max(1, min(audit_limit, 10_000))
        snapshot = await observability.operator_metrics(
            workspace_key=workspace_id,
            window_minutes=bounded_window,
            storage_limit=bounded_storage,
        )
        chain_valid = await audit.verify_chain(
            workspace_key=workspace_id,
            limit=bounded_audit,
        )
        dashboards = dict(snapshot["dashboards"])
        audit_integrity = dict(dashboards.get("audit_integrity", {}))
        audit_integrity.update({"chain_valid": chain_valid, "verify_limit": bounded_audit})
        dashboards["audit_integrity"] = audit_integrity
        return ObservabilityMetricsResponse(
            workspace_id=snapshot["workspace_id"],  # type: ignore[arg-type]
            captured_at=snapshot["captured_at"],  # type: ignore[arg-type]
            window_minutes=snapshot["window_minutes"],  # type: ignore[arg-type]
            metrics=snapshot["metrics"],  # type: ignore[arg-type]
            dashboards=dashboards,
        )

    async def _observatory_snapshot(
        *,
        workspace_id: str | None,
        window_minutes: int,
        audit_limit: int = 1000,
    ) -> dict[str, object]:
        settings = get_settings()
        bounded_window = max(1, min(window_minutes, 24 * 60))
        job_summary = await jobs.summary(workspace_key=workspace_id)
        worker_health = await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": settings.worker_scheduler_concurrency,
                "maintenance": settings.worker_maintenance_concurrency,
                "mutation": settings.worker_mutation_concurrency,
            },
        )
        status_payload = {
            "mode": settings.mode.value,
            "database_configured": bool(settings.database_url),
            "ingest_auth_configured": bool(settings.ingest_token),
            "control_auth_configured": bool(settings.control_token),
            "runtime_context_broker": {
                "enabled": settings.runtime_context_broker_enabled,
                "timeout_ms": settings.runtime_context_timeout_ms,
                "max_tokens": settings.max_context_hint_tokens,
            },
            "jobs": job_summary.counts,
            "workers": worker_health.to_json(),
        }
        metrics_snapshot = await observability.operator_metrics(
            workspace_key=workspace_id,
            window_minutes=bounded_window,
            storage_limit=100,
        )
        audit_chain_valid = await audit.verify_chain(
            workspace_key=workspace_id,
            limit=max(1, min(audit_limit, 10_000)),
        )
        static_available = (_admin_static_dir() / "index.html").exists()
        return build_observatory_snapshot(
            settings=settings,
            status=status_payload,
            operator_metrics=metrics_snapshot,
            worker_health=worker_health.to_json(),
            audit_chain_valid=audit_chain_valid,
            static_available=static_available,
            workspace_id=workspace_id,
            window_minutes=bounded_window,
        )

    def _missing_read_model(
        object_type: str,
        *,
        supporting_component: str | None = None,
    ) -> dict[str, Any]:
        return {
            "health": "unknown",
            "reason_codes": ["missing-required-signal"],
            "supporting_component": supporting_component,
            "summary": (
                "No bounded Observatory read model exists for this object class yet."
            ),
        }

    def _observatory_collection(
        *,
        object_type: str,
        title: str,
        items: list[dict[str, Any]],
        limit: int,
        source: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> ObservatoryCollectionResponse:
        bounded_limit = max(1, min(limit, 500))
        visible_items = items[:bounded_limit]
        return ObservatoryCollectionResponse(
            collection={
                "schema_version": "skillkernel.observatory.collection.v1",
                "object_type": object_type,
                "title": title,
                "items": visible_items,
                "count": len(visible_items),
                "limit": bounded_limit,
                "has_more": len(items) > bounded_limit,
                "source": source,
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                    "redaction_state": "redacted_or_not_applicable",
                },
                "diagnostics": diagnostics or {},
            }
        )

    def _find_by_id(
        items: list[dict[str, Any]],
        object_id: str,
        keys: tuple[str, ...],
    ) -> dict[str, Any] | None:
        for item in items:
            if any(str(item.get(key)) == object_id for key in keys):
                return item
        return None

    async def _record_observatory_action(
        request: ObservatoryActionRequest,
        authorization: str | None,
        roles_header: str | None,
    ) -> ObservatoryActionResponse:
        principal = _require_admin_auth(
            authorization,
            roles_header,
            required_roles={"operator", "admin"},
        )
        allowed_actions = {
            "noop.audit",
            "refresh_snapshot",
            "verify_audit_chain",
            "retry_job",
            "cancel_job",
            "pause_schedule",
            "resume_schedule",
            "historical_discover_dry_run",
            "historical_import",
            "quarantine_candidate",
            "freeze_skill",
            "unfreeze_skill",
            "rollback_skill",
            "rollback_transaction",
            "rerun_evaluation",
            "rescan_scanner",
            "calibrate_broker",
            "qualify_model_profile",
            "qualify_embedding_profile",
            "storage_health_check",
            "storage_retention_dry_run",
            "refresh_read_models",
            "verify_live_stream",
            "revoke_source",
        }
        high_impact_actions = {
            "historical_import",
            "quarantine_candidate",
            "freeze_skill",
            "unfreeze_skill",
            "rollback_skill",
            "rollback_transaction",
            "revoke_source",
        }
        accepted = request.action in allowed_actions
        reason_codes: list[str] = [] if accepted else ["unsupported-observatory-action"]
        if (
            request.action == "reveal_raw_content"
            and not get_settings().web_admin_raw_content_enabled
        ):
            accepted = False
            reason_codes = ["raw-content-disabled"]
        confirmation_required = request.action in high_impact_actions
        if (
            accepted
            and confirmation_required
            and not request.dry_run
            and request.confirmation != "confirm"
        ):
            accepted = False
            reason_codes = ["confirmation-required"]
        audit_record = await audit.append_record(
            AuditRecord(
                action=f"observatory.{request.action}",
                actor=str(principal["subject"]),
                subject_type="observatory_action",
                subject_id=request.idempotency_key,
                details={
                    "target": request.target,
                    "reason": request.reason,
                    "dry_run": request.dry_run,
                    "accepted": accepted,
                    "reason_codes": reason_codes,
                    "metadata": request.metadata,
                    "confirmation_required": confirmation_required,
                },
            ),
            workspace_key=request.workspace_id,
        )
        return ObservatoryActionResponse(
            receipt=action_receipt(
                action=request.action,
                role=str(principal["role"]),
                idempotency_key=request.idempotency_key,
                accepted=accepted,
                reason_codes=reason_codes,
                audit=audit_record.model_dump(mode="json"),
            )
        )

    def _register_observatory_action_route(path: str, action: str) -> None:
        @app.post(path, response_model=ObservatoryActionResponse)
        async def observatory_action_alias(
            request: Request,
            authorization: Annotated[str | None, Header()] = None,
            x_skillkernel_roles: Annotated[
                str | None, Header(alias="X-SkillKernel-Roles")
            ] = None,
            workspace_id: str = "dev-01",
            idempotency_key: str | None = None,
            reason: str | None = None,
            confirmation: str | None = None,
            dry_run: bool = True,
        ) -> ObservatoryActionResponse:
            if not idempotency_key:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="idempotency_key is required",
                )
            return await _record_observatory_action(
                ObservatoryActionRequest(
                    workspace_id=workspace_id,
                    action=action,
                    idempotency_key=idempotency_key,
                    target=dict(request.path_params),
                    reason=reason,
                    confirmation=confirmation,
                    dry_run=dry_run,
                ),
                authorization,
                x_skillkernel_roles,
            )

    @app.get("/admin/api/v1/config", response_model=ObservatoryConfigResponse)
    async def observatory_config(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryConfigResponse:
        principal = _require_admin_auth(authorization, x_skillkernel_roles)
        settings = get_settings()
        static_dir = _admin_static_dir()
        return ObservatoryConfigResponse(
            config={
                "base_path": _admin_base_path(),
                "api_base_path": f"{_admin_base_path()}/api/v1",
                "live_path": f"{_admin_base_path()}/live",
                "enabled": settings.web_admin_enabled,
                "static_available": (static_dir / "index.html").exists(),
                "static_dir": str(static_dir),
                "principal": principal,
                "raw_content": {"enabled": settings.web_admin_raw_content_enabled},
                "diagnostics": {
                    "issue_board_enabled": settings.web_admin_issue_board_enabled,
                    "subsystem_lenses_enabled": settings.web_admin_subsystem_lenses_enabled,
                    "playbooks_enabled": settings.web_admin_playbooks_enabled,
                    "telemetry_staleness_warning_seconds": (
                        settings.web_admin_telemetry_staleness_warning_seconds
                    ),
                    "telemetry_staleness_degraded_seconds": (
                        settings.web_admin_telemetry_staleness_degraded_seconds
                    ),
                },
            }
        )

    @app.get("/admin/api/v1/health/live", response_model=HealthResponse)
    async def observatory_health_live() -> HealthResponse:
        return HealthResponse(ok=True, service="skillkernel-observatory", version=__version__)

    @app.get("/admin/api/v1/health/ready", response_model=ObservatoryObjectResponse)
    async def observatory_health_ready(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.ready.v1",
                "ready": snapshot["global_health"] not in {"blocked", "offline"},
                "global_health": snapshot["global_health"],
                "data_quality": snapshot["data_quality"],
                "issues": snapshot["issue_board"],
                "self_health": object_microscope(
                    snapshot,
                    object_type="component",
                    object_id="observatory_admin",
                ),
            }
        )

    @app.get("/admin/api/v1/config/effective", response_model=EffectiveConfigResponse)
    async def observatory_effective_config(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> EffectiveConfigResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        return EffectiveConfigResponse(skillkernel=effective_skillkernel_config())

    @app.get("/admin/api/v1/summary", response_model=ObservatorySnapshotResponse)
    async def observatory_summary(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatorySnapshotResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        return ObservatorySnapshotResponse(
            snapshot=await _observatory_snapshot(
                workspace_id=workspace_id,
                window_minutes=window_minutes,
            )
        )

    @app.get("/admin/api/v1/pipeline", response_model=ObservatorySnapshotResponse)
    async def observatory_pipeline(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatorySnapshotResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatorySnapshotResponse(
            snapshot={
                "schema_version": snapshot["schema_version"],
                "snapshot_seq": snapshot["snapshot_seq"],
                "captured_at": snapshot["captured_at"],
                "workspace_id": snapshot["workspace_id"],
                "pipeline": snapshot["pipeline"],
                "data_quality": snapshot["data_quality"],
                "issue_board": snapshot["issue_board"],
            }
        )

    @app.get("/admin/api/v1/components", response_model=ObservatoryCollectionResponse)
    async def observatory_components(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        stations = list(snapshot["pipeline"]["stations"])  # type: ignore[index]
        return _observatory_collection(
            object_type="component",
            title="Observatory components",
            items=stations,
            limit=limit,
            source="observatory_snapshot.pipeline.stations",
        )

    @app.get("/admin/api/v1/subsystems", response_model=ObservatorySnapshotResponse)
    async def observatory_subsystems(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatorySnapshotResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatorySnapshotResponse(
            snapshot={
                "schema_version": snapshot["schema_version"],
                "snapshot_seq": snapshot["snapshot_seq"],
                "captured_at": snapshot["captured_at"],
                "workspace_id": snapshot["workspace_id"],
                "subsystems": snapshot["subsystems"],
                "issue_board": snapshot["issue_board"],
            }
        )

    @app.get("/admin/api/v1/subsystems/{subsystem_id}", response_model=ObservatoryObjectResponse)
    async def observatory_subsystem(
        subsystem_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(
                snapshot,
                object_type="subsystem",
                object_id=subsystem_id,
            )
        )

    @app.get("/admin/api/v1/components/{component_id}", response_model=ObservatoryObjectResponse)
    async def observatory_component(
        component_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(
                snapshot,
                object_type="component",
                object_id=component_id,
            )
        )

    @app.get(
        "/admin/api/v1/components/{component_id}/metrics",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_component_metrics(
        component_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        component = _find_by_id(
            list(snapshot["pipeline"]["stations"]),  # type: ignore[index]
            component_id,
            ("component_id",),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.component-metrics.v1",
                "object_type": "component_metrics",
                "object_id": component_id,
                "metrics": component.get("signal_contract", {}) if component else {},
                "records": component.get("records", []) if component else [],
                "diagnostics": component
                or _missing_read_model("component_metrics", supporting_component=component_id),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/issues", response_model=ObservatorySnapshotResponse)
    async def observatory_issues(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatorySnapshotResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatorySnapshotResponse(
            snapshot={
                "schema_version": snapshot["schema_version"],
                "snapshot_seq": snapshot["snapshot_seq"],
                "captured_at": snapshot["captured_at"],
                "workspace_id": snapshot["workspace_id"],
                "issue_board": snapshot["issue_board"],
                "reason_code_catalog": snapshot["reason_code_catalog"],
            }
        )

    @app.get("/admin/api/v1/issues/{issue_id}", response_model=ObservatoryObjectResponse)
    async def observatory_issue_detail(
        issue_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(snapshot, object_type="issue", object_id=issue_id)
        )

    @app.get("/admin/api/v1/reason-codes", response_model=ObservatoryCollectionResponse)
    async def observatory_reason_codes(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return _observatory_collection(
            object_type="reason_code",
            title="Diagnostic reason-code catalog",
            items=list(snapshot["reason_code_catalog"]),  # type: ignore[arg-type]
            limit=limit,
            source="observatory_snapshot.reason_code_catalog",
        )

    @app.get("/admin/api/v1/playbooks", response_model=ObservatoryCollectionResponse)
    async def observatory_playbooks(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        playbooks = [
            {**playbook, "subsystem_id": subsystem["subsystem_id"]}
            for subsystem in snapshot["subsystems"]  # type: ignore[index]
            for playbook in subsystem.get("playbooks", [])
        ]
        return _observatory_collection(
            object_type="playbook",
            title="Guided diagnostic playbooks",
            items=playbooks,
            limit=limit,
            source="observatory_snapshot.subsystems.playbooks",
        )

    @app.get("/admin/api/v1/playbooks/{playbook_id}", response_model=ObservatoryObjectResponse)
    async def observatory_playbook_detail(
        playbook_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        playbooks = [
            {**playbook, "subsystem_id": subsystem["subsystem_id"]}
            for subsystem in snapshot["subsystems"]  # type: ignore[index]
            for playbook in subsystem.get("playbooks", [])
        ]
        playbook = _find_by_id(playbooks, playbook_id, ("playbook_id",))
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.playbook.v1",
                "object_type": "playbook",
                "object_id": playbook_id,
                "title": playbook.get("playbook_id", playbook_id) if playbook else playbook_id,
                "summary": playbook.get("summary") if playbook else "No playbook read model found.",
                "current_signal_state": playbook
                or _missing_read_model("playbook", supporting_component="observatory_admin"),
                "supporting_records": [
                    issue
                    for issue in snapshot["issue_board"]  # type: ignore[index]
                    if playbook
                    and issue.get("subsystem_id") == playbook.get("subsystem_id")
                ],
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/invariants", response_model=ObservatoryCollectionResponse)
    async def observatory_invariants(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return _observatory_collection(
            object_type="pipeline_invariant",
            title="Pipeline invariant status",
            items=list(snapshot["pipeline"]["invariants"]),  # type: ignore[index]
            limit=limit,
            source="observatory_snapshot.pipeline.invariants",
        )

    @app.get("/admin/api/v1/observatory", response_model=ObservatoryObjectResponse)
    async def observatory_self_health(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(
                snapshot,
                object_type="component",
                object_id="observatory_admin",
            )
        )

    @app.get("/admin/api/v1/search", response_model=ObservatorySearchResponse)
    async def observatory_search(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        query: str = "",
        limit: int = 25,
    ) -> ObservatorySearchResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(workspace_id=workspace_id, window_minutes=60)
        payload = search_observatory(snapshot, query, limit=limit)
        return ObservatorySearchResponse(**payload)

    @app.get(
        "/admin/api/v1/objects/{object_type}/{object_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_object(
        object_type: str,
        object_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(
                snapshot,
                object_type=object_type,
                object_id=object_id,
            )
        )

    @app.get("/admin/api/v1/events", response_model=ObservatoryCollectionResponse)
    async def observatory_events(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        event_type: str | None = None,
        trace_id: UUID | None = None,
        window_minutes: int = 60,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await store.list_events(
            workspace_key=workspace_id,
            event_type=event_type,
            trace_id=trace_id,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="captured_event",
            title="Redacted captured events",
            items=[record.to_json() for record in records],
            limit=limit,
            source="event_store.list_events",
            diagnostics={
                "supporting_component": "spool_ingest",
                "event_type": event_type,
                "trace_id": str(trace_id) if trace_id else None,
                "raw_payload_available": False,
            },
        )

    @app.get("/admin/api/v1/traces", response_model=ObservatoryCollectionResponse)
    async def observatory_traces(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        traces = await observability.list_traces(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="trace",
            title="Trace search",
            items=[trace.to_json() for trace in traces],
            limit=limit,
            source="observability_store.list_traces",
            diagnostics={
                "supporting_component": "audit_trace",
                "raw_content_available": False,
            },
        )

    @app.get("/admin/api/v1/traces/{trace_id}", response_model=ObservatoryObjectResponse)
    async def observatory_trace_detail(
        trace_id: UUID,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "dev-01",
        limit: int = 100,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        spans = await observability.list_trace(
            workspace_key=workspace_id,
            trace_id=trace_id,
            limit=max(1, min(limit, 500)),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.trace-detail.v1",
                "object_type": "trace",
                "object_id": str(trace_id),
                "title": f"Trace {trace_id}",
                "summary": "Content-safe trace detail assembled from recorded spans.",
                "timeline": [span.to_json() for span in spans],
                "provenance": {
                    "upstream": [],
                    "downstream": [
                        ref
                        for span in spans
                        for ref in span.to_json().get("object_refs", [])
                        if isinstance(ref, dict)
                    ],
                },
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
                "diagnostics": {
                    "span_count": len(spans),
                    "replay_reexecutes_work": False,
                },
                "audit": {"links": []},
            }
        )

    @app.get("/admin/api/v1/jobs", response_model=ObservatoryCollectionResponse)
    async def observatory_jobs(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        status_filter: Annotated[str | None, Query(alias="status")] = None,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await jobs.list_jobs(status=status_filter, limit=max(1, min(limit, 250)))
        return _observatory_collection(
            object_type="job",
            title="Sidecar jobs",
            items=[job.to_json() for job in listed],
            limit=limit,
            source="job_store.list_jobs",
        )

    @app.get("/admin/api/v1/jobs/{job_id}", response_model=ObservatoryObjectResponse)
    async def observatory_job_detail(
        job_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        limit: int = 500,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = [job.to_json() for job in await jobs.list_jobs(limit=max(1, min(limit, 500)))]
        job = _find_by_id(listed, job_id, ("job_id", "idempotency_key"))
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.job.v1",
                "object_type": "job",
                "object_id": job_id,
                "title": f"Job {job_id}",
                "summary": "Sidecar scheduler job detail.",
                "diagnostics": job
                or _missing_read_model("job", supporting_component="scheduler_jobs"),
                "timeline": [],
                "provenance": {"upstream": [], "downstream": []},
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
                "audit": {"links": []},
            }
        )

    @app.get("/admin/api/v1/schedules", response_model=ObservatoryCollectionResponse)
    async def observatory_schedules(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await scheduler.list_schedules(limit=max(1, min(limit, 250)))
        return _observatory_collection(
            object_type="schedule",
            title="Sidecar schedules",
            items=[schedule.to_json() for schedule in listed],
            limit=limit,
            source="scheduler_store.list_schedules",
        )

    @app.get("/admin/api/v1/skills", response_model=ObservatoryCollectionResponse)
    async def observatory_skills(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await skills.list_skills(
            workspace_key=workspace_id,
            lifecycle_state=lifecycle_state,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="skill",
            title="Skill library",
            items=[skill.to_json() for skill in listed],
            limit=limit,
            source="skill_store.list_skills",
        )

    @app.get("/admin/api/v1/skills/{skill_id}", response_model=ObservatoryObjectResponse)
    async def observatory_skill_detail(
        skill_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 500,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = [
            skill.to_json()
            for skill in await skills.list_skills(
                workspace_key=workspace_id,
                lifecycle_state=None,
                limit=max(1, min(limit, 500)),
            )
        ]
        skill = _find_by_id(listed, skill_id, ("skill_id", "slug", "active_version_id"))
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.skill.v1",
                "object_type": "skill",
                "object_id": skill_id,
                "title": skill.get("name", skill_id) if skill else skill_id,
                "summary": (
                    "Skill lifecycle, active version, scanner/evaluator state, "
                    "and manifest metadata."
                ),
                "diagnostics": skill
                or _missing_read_model("skill", supporting_component="skill_ir_graph_ir"),
                "timeline": [],
                "provenance": {"upstream": [], "downstream": []},
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
                "audit": {"links": []},
            }
        )

    @app.get(
        "/admin/api/v1/skills/{skill_id}/versions/{version_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_skill_version_detail(
        skill_id: str,
        version_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        return await observatory_skill_detail(
            skill_id=version_id or skill_id,
            authorization=authorization,
            x_skillkernel_roles=x_skillkernel_roles,
            workspace_id=workspace_id,
        )

    @app.get("/admin/api/v1/topology", response_model=ObservatoryObjectResponse)
    async def observatory_topology(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.topology.v1",
                "object_type": "skill_topology",
                "object_id": "current",
                "title": "Skill topology",
                "summary": "Current topology-related stations and flow edges.",
                "nodes": [
                    station
                    for station in snapshot["pipeline"]["stations"]  # type: ignore[index]
                    if "topology_design" in station.get("subsystem_ids", [])
                    or "runtime_context" in station.get("subsystem_ids", [])
                ],
                "edges": [
                    edge
                    for edge in snapshot["pipeline"]["edges"]  # type: ignore[index]
                    if "skill" in str(edge.get("dominant_item_kind", ""))
                    or "candidate" in str(edge.get("dominant_item_kind", ""))
                ],
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/candidates", response_model=ObservatoryCollectionResponse)
    async def observatory_candidates(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        lifecycle_state: str | None = "candidate",
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await candidates.list_candidate_reviews(
            workspace_key=workspace_id,
            lifecycle_state=lifecycle_state,
            limit=max(1, min(limit, 250)),
        )
        return _observatory_collection(
            object_type="candidate",
            title="Candidate reviews",
            items=[candidate.to_json() for candidate in listed],
            limit=limit,
            source="candidate_store.list_candidate_reviews",
        )

    @app.get("/admin/api/v1/candidates/{candidate_id}", response_model=ObservatoryObjectResponse)
    async def observatory_candidate_detail(
        candidate_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 250,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = [
            candidate.to_json()
            for candidate in await candidates.list_candidate_reviews(
                workspace_key=workspace_id,
                lifecycle_state=None,
                limit=max(1, min(limit, 250)),
            )
        ]
        candidate = _find_by_id(
            listed,
            candidate_id,
            ("skill_id", "skill_version_id", "slug", "name"),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.candidate.v1",
                "object_type": "candidate",
                "object_id": candidate_id,
                "title": candidate.get("name", candidate_id) if candidate else candidate_id,
                "summary": "Candidate SkillIR/proposal review state.",
                "diagnostics": candidate
                or _missing_read_model("candidate", supporting_component="opportunity_mining"),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/evaluations", response_model=ObservatoryCollectionResponse)
    async def observatory_evaluations(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await evaluations.list_evaluation_reviews(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 250)),
        )
        return _observatory_collection(
            object_type="evaluation",
            title="Evaluation reviews",
            items=[evaluation.to_json() for evaluation in listed],
            limit=limit,
            source="evaluation_store.list_evaluation_reviews",
        )

    @app.get("/admin/api/v1/evaluations/{evaluation_id}", response_model=ObservatoryObjectResponse)
    async def observatory_evaluation_detail(
        evaluation_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 250,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = [
            evaluation.to_json()
            for evaluation in await evaluations.list_evaluation_reviews(
                workspace_key=workspace_id,
                status=None,
                limit=max(1, min(limit, 250)),
            )
        ]
        evaluation = _find_by_id(
            listed,
            evaluation_id,
            ("evaluation_id", "skill_id", "skill_version_id"),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.evaluation.v1",
                "object_type": "evaluation",
                "object_id": evaluation_id,
                "title": f"Evaluation {evaluation_id}",
                "summary": "Evaluation/probe review state.",
                "diagnostics": evaluation
                or _missing_read_model("evaluation", supporting_component="evaluator_probes"),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/scanner-findings", response_model=ObservatoryCollectionResponse)
    async def observatory_scanner_findings(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        scanner = _find_by_id(
            list(snapshot["pipeline"]["stations"]),  # type: ignore[index]
            "scanner_security",
            ("component_id",),
        )
        items = list(scanner.get("records", [])) if scanner else []
        return _observatory_collection(
            object_type="scanner_finding",
            title="Scanner findings",
            items=items,
            limit=limit,
            source="observatory_snapshot.scanner_security.records",
            diagnostics=scanner
            or _missing_read_model("scanner_finding", supporting_component="scanner_security"),
        )

    @app.get("/admin/api/v1/artifacts/{artifact_id}", response_model=ObservatoryObjectResponse)
    async def observatory_artifact_detail(
        artifact_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.artifact.v1",
                "object_type": "artifact",
                "object_id": artifact_id,
                "title": f"Artifact {artifact_id}",
                "summary": (
                    "Redacted artifact preview is unavailable until a bounded artifact "
                    "read model is present."
                ),
                "diagnostics": _missing_read_model(
                    "artifact",
                    supporting_component="deterministic_writer",
                ),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/historical/imports", response_model=ObservatoryCollectionResponse)
    async def observatory_historical_imports(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        sources = await historical_import.list_sources(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 250)),
        )
        return _observatory_collection(
            object_type="historical_import",
            title="Historical import sources",
            items=[source.to_json() for source in sources],
            limit=limit,
            source="historical_import_store.list_sources",
        )

    @app.get(
        "/admin/api/v1/historical/imports/{historical_import_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_historical_import_detail(
        historical_import_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 250,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        sources = [
            source.to_json()
            for source in await historical_import.list_sources(
                workspace_key=workspace_id,
                limit=max(1, min(limit, 250)),
            )
        ]
        source = _find_by_id(
            sources,
            historical_import_id,
            ("historical_import_source_id", "external_source_id", "source_kind"),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.historical-import.v1",
                "object_type": "historical_import",
                "object_id": historical_import_id,
                "title": f"Historical import {historical_import_id}",
                "summary": "Historical source/import status.",
                "diagnostics": source
                or _missing_read_model(
                    "historical_import",
                    supporting_component="historical_ingestion",
                ),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        )

    @app.get("/admin/api/v1/broker/decisions", response_model=ObservatoryCollectionResponse)
    async def observatory_broker_decisions(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        logs = await retrieval.list_recent_logs(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="broker_decision",
            title="Broker decisions",
            items=[
                {
                    **log.to_json(),
                    "object_id": str(log.retrieval_log_id),
                    "object_type": "broker_decision",
                    "title": f"Broker decision {log.retrieval_log_id}",
                    "summary": (
                        f"{log.decision}; rendered={len(log.rendered_skill_ids)}; "
                        f"candidates={len(log.candidate_skill_ids)}"
                    ),
                    "details_url": f"/admin/broker/decisions/{log.retrieval_log_id}",
                }
                for log in logs
            ],
            limit=limit,
            source="retrieval_store.list_recent_logs",
            diagnostics={
                "supporting_component": "broker_runtime",
                "raw_query_available": False,
                "query_identity": "metadata.query_hash",
            },
        )

    @app.get(
        "/admin/api/v1/broker/decisions/{decision_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_broker_decision_detail(
        decision_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        try:
            retrieval_log_id = UUID(decision_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker decision not found",
            ) from exc
        log = await retrieval.get_log(
            workspace_key=workspace_id,
            retrieval_log_id=retrieval_log_id,
        )
        if log is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker decision not found",
            )
        payload = log.to_json()
        candidate_objects = [
            item
            for item in log.metadata.get("candidate_objects", [])
            if isinstance(item, dict)
        ]
        suppressed = [
            item for item in log.metadata.get("suppressed", []) if isinstance(item, dict)
        ]
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.broker-decision.v1",
                "object_type": "broker_decision",
                "object_id": str(log.retrieval_log_id),
                "title": f"Broker decision {log.retrieval_log_id}",
                "summary": (
                    f"{log.decision}; rendered={len(log.rendered_skill_ids)}; "
                    f"candidates={len(log.candidate_skill_ids)}"
                ),
                "timeline": [
                    {
                        "at": payload["created_at"],
                        "event": "retrieval_logged",
                        "decision": log.decision,
                    }
                ],
                "provenance": {
                    "upstream": [
                        {"object_type": "trace", "object_id": str(log.trace_id)}
                    ]
                    if log.trace_id
                    else [],
                    "downstream": [
                        {"object_type": "skill", "object_id": skill_id}
                        for skill_id in payload["rendered_skill_ids"]
                    ],
                    "candidate_objects": candidate_objects,
                },
                "effects": {
                    "rendered_skill_ids": payload["rendered_skill_ids"],
                    "candidate_skill_ids": payload["candidate_skill_ids"],
                    "no_skill_control": log.no_skill_control,
                    "suppressed": suppressed,
                },
                "diagnostics": {
                    "decision": log.decision,
                    "reason_codes": log.metadata.get("reason_codes", []),
                    "query_hash": log.metadata.get("query_hash"),
                    "candidate_count": log.metadata.get(
                        "candidate_count",
                        len(candidate_objects),
                    ),
                    "rendered_skill_count": len(log.rendered_skill_ids),
                    "broker_policy_version_id": payload["broker_policy_version_id"],
                    "trace_id": payload["trace_id"],
                    "span_id": payload["span_id"],
                    "metadata_keys": sorted(log.metadata.keys()),
                },
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                    "redaction_state": "redacted_or_not_applicable",
                    "raw_query_stored": False,
                },
                "audit": {"links": [], "chain_visible": True},
            }
        )

    @app.get("/admin/api/v1/context/artifacts", response_model=ObservatoryCollectionResponse)
    async def observatory_context_artifacts(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        context = _find_by_id(
            list(snapshot["pipeline"]["stations"]),  # type: ignore[index]
            "context_compiler",
            ("component_id",),
        )
        return _observatory_collection(
            object_type="context_artifact",
            title="Context artifacts",
            items=list(context.get("records", [])) if context else [],
            limit=limit,
            source="observatory_snapshot.context_compiler.records",
            diagnostics=context
            or _missing_read_model("context_artifact", supporting_component="context_compiler"),
        )

    @app.get("/admin/api/v1/model-profile", response_model=ObservatoryCollectionResponse)
    async def observatory_model_profile(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await profiles.list_model_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="model_profile",
            title="Text model profiles",
            items=[profile.to_json() for profile in listed],
            limit=limit,
            source="profile_store.list_model_profiles",
        )

    @app.get("/admin/api/v1/embedding-profile", response_model=ObservatoryCollectionResponse)
    async def observatory_embedding_profile(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await profiles.list_embedding_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="embedding_profile",
            title="Embedding profiles",
            items=[profile.to_json() for profile in listed],
            limit=limit,
            source="profile_store.list_embedding_profiles",
        )

    @app.get("/admin/api/v1/storage", response_model=ObservatoryObjectResponse)
    async def observatory_storage(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        return ObservatoryObjectResponse(
            object=object_microscope(snapshot, object_type="component", object_id="storage_db")
        )

    @app.get("/admin/api/v1/audit", response_model=ObservatoryCollectionResponse)
    async def observatory_audit(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        bounded_limit = max(1, min(limit, 500))
        records = await audit.list_recent(workspace_key=workspace_id, limit=bounded_limit)
        return _observatory_collection(
            object_type="audit_record",
            title="Audit trail",
            items=[record.model_dump(mode="json") for record in records],
            limit=bounded_limit,
            source="audit_store.list_recent",
            diagnostics={
                "chain_valid": await audit.verify_chain(
                    workspace_key=workspace_id,
                    limit=bounded_limit,
                )
            },
        )

    @app.get("/admin/api/v1/comparisons", response_model=ObservatoryCollectionResponse)
    async def observatory_comparisons(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        comparisons = await observatory_admin.list_comparisons(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 500)),
        )
        return _observatory_collection(
            object_type="baseline_comparison",
            title="Saved baseline comparisons",
            items=[comparison.to_json() for comparison in comparisons],
            limit=limit,
            source="observatory_admin_store.list_comparisons",
            diagnostics={
                "supporting_component": "observatory_admin",
                "mutates_policy": False,
            },
        )

    @app.post("/admin/api/v1/comparisons/query", response_model=ObservatoryObjectResponse)
    async def observatory_comparison_query(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        principal = _require_admin_auth(authorization, x_skillkernel_roles)
        workspace_key = workspace_id or "dev-01"
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_key,
            window_minutes=window_minutes,
        )
        comparison = await observatory_admin.create_comparison(
            workspace_key=workspace_key,
            actor_id=str(principal["subject"]),
            comparison_kind="snapshot",
            left_selector={
                "kind": "snapshot",
                "snapshot_seq": snapshot["snapshot_seq"],
                "captured_at": snapshot["captured_at"],
            },
            right_selector={
                "kind": "snapshot",
                "snapshot_seq": snapshot["snapshot_seq"],
                "captured_at": snapshot["captured_at"],
            },
            result_summary={
                "summary": "Bounded baseline comparison over the current Observatory snapshot.",
                "differences": [],
                "global_health": snapshot["global_health"],
                "issue_count": len(snapshot["issue_board"]),
                "mutates_policy": False,
            },
        )
        return ObservatoryObjectResponse(
            object=comparison.to_json()
        )

    @app.post("/admin/api/v1/diagnostics/bundles", response_model=ObservatoryObjectResponse)
    async def observatory_create_diagnostic_bundle(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "dev-01",
        window_minutes: int = 60,
    ) -> ObservatoryObjectResponse:
        principal = _require_admin_auth(
            authorization,
            x_skillkernel_roles,
            required_roles={"operator", "admin"},
        )
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        bundle = await observatory_admin.create_diagnostic_bundle(
            workspace_key=workspace_id,
            actor_id=str(principal["subject"]),
            scope={
                "workspace_id": workspace_id,
                "window_minutes": max(1, min(window_minutes, 24 * 60)),
                "snapshot_seq": snapshot["snapshot_seq"],
            },
            redaction_level="default",
            manifest={
                "schema_version": "skillkernel.observatory.diagnostic-bundle.manifest.v1",
                "global_health": snapshot["global_health"],
                "data_quality": snapshot["data_quality"],
                "issue_count": len(snapshot["issue_board"]),
                "component_count": len(snapshot["pipeline"]["stations"]),
                "subsystem_count": len(snapshot["subsystems"]),
            },
            storage_uri=f"db://autoskill.admin_diagnostic_bundles/{sha256_text(str(snapshot['snapshot_seq']))[:16]}",
        )
        audit_record = await audit.append_record(
            AuditRecord(
                action="observatory.create_diagnostic_bundle",
                actor=str(principal["subject"]),
                subject_type="diagnostic_bundle",
                subject_id=str(bundle.bundle_id),
                details={"workspace_id": workspace_id, "snapshot_seq": snapshot["snapshot_seq"]},
            ),
            workspace_key=workspace_id,
        )
        payload = bundle.to_json()
        payload["audit"] = audit_record.model_dump(mode="json")
        return ObservatoryObjectResponse(
            object=payload
        )

    @app.get(
        "/admin/api/v1/diagnostics/bundles/{bundle_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_diagnostic_bundle(
        bundle_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        try:
            parsed_bundle_id = UUID(bundle_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="diagnostic bundle not found",
            ) from exc
        bundle = await observatory_admin.get_diagnostic_bundle(
            bundle_id=parsed_bundle_id,
            workspace_key=workspace_id,
        )
        if bundle is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="diagnostic bundle not found",
            )
        return ObservatoryObjectResponse(
            object=bundle.to_json()
        )

    @app.get("/admin/api/v1/replay/traces/{trace_id}", response_model=ObservatoryObjectResponse)
    async def observatory_trace_replay(
        trace_id: UUID,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "dev-01",
        limit: int = 100,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        spans = await observability.list_trace(
            workspace_key=workspace_id,
            trace_id=trace_id,
            limit=max(1, min(limit, 500)),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.trace-replay.v1",
                "object_type": "trace",
                "object_id": str(trace_id),
                "workspace_id": workspace_id,
                "title": f"Trace {trace_id}",
                "summary": "Content-safe trace replay assembled from recorded spans.",
                "timeline": [span.to_json() for span in spans],
                "provenance": {
                    "upstream": [],
                    "downstream": [
                        ref
                        for span in spans
                        for ref in span.to_json().get("object_refs", [])
                        if isinstance(ref, dict)
                    ],
                },
                "replay_safety": {
                    "reexecutes_work": False,
                    "raw_content_included": False,
                },
            }
        )

    @app.post("/admin/api/v1/actions", response_model=ObservatoryActionResponse)
    async def observatory_action(
        request: ObservatoryActionRequest,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryActionResponse:
        return await _record_observatory_action(
            request,
            authorization,
            x_skillkernel_roles,
        )

    _register_observatory_action_route("/admin/api/v1/actions/jobs/{id}/retry", "retry_job")
    _register_observatory_action_route("/admin/api/v1/actions/jobs/{id}/cancel", "cancel_job")
    _register_observatory_action_route(
        "/admin/api/v1/actions/schedules/{id}/pause",
        "pause_schedule",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/schedules/{id}/resume",
        "resume_schedule",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/historical/discover-dry-run",
        "historical_discover_dry_run",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/historical/import",
        "historical_import",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/candidates/{id}/quarantine",
        "quarantine_candidate",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/skills/{id}/freeze",
        "freeze_skill",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/skills/{id}/unfreeze",
        "unfreeze_skill",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/skills/{id}/rollback",
        "rollback_skill",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/evaluations/{id}/rerun",
        "rerun_evaluation",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/scanner/rescan",
        "rescan_scanner",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/broker/calibrate",
        "calibrate_broker",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/model-profile/qualify",
        "qualify_model_profile",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/embedding-profile/qualify",
        "qualify_embedding_profile",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/storage/health-check",
        "storage_health_check",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/storage/retention-dry-run",
        "storage_retention_dry_run",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/audit/verify-chain",
        "verify_audit_chain",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/observatory/refresh-read-models",
        "refresh_read_models",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/observatory/verify-live-stream",
        "verify_live_stream",
    )
    _register_observatory_action_route(
        "/admin/api/v1/actions/revocation/revoke-source",
        "revoke_source",
    )

    @app.websocket("/admin/live")
    async def observatory_live(websocket: WebSocket) -> None:
        await _require_admin_websocket_auth(websocket)
        await websocket.accept()
        workspace_id = websocket.query_params.get("workspace_id")
        last_seq_param = websocket.query_params.get("last_seq")
        last_seq = int(last_seq_param) if last_seq_param and last_seq_param.isdigit() else None
        try:
            while True:
                snapshot = await _observatory_snapshot(
                    workspace_id=workspace_id,
                    window_minutes=60,
                )
                await websocket.send_json(build_live_envelope(snapshot, last_seq=last_seq))
                last_seq = int(snapshot["snapshot_seq"])
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            return

    @app.get("/admin/live-sse")
    async def observatory_live_sse(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        last_seq: int | None = None,
        token: str | None = None,
    ) -> StreamingResponse:
        _require_admin_auth(
            authorization or (f"Bearer {token}" if token else None),
            x_skillkernel_roles,
        )

        async def stream() -> AsyncIterator[str]:
            current_last_seq = last_seq
            while True:
                snapshot = await _observatory_snapshot(
                    workspace_id=workspace_id,
                    window_minutes=60,
                )
                payload = build_live_envelope(snapshot, last_seq=current_last_seq)
                yield f"event: {payload['event_type']}\n"
                yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
                current_last_seq = int(snapshot["snapshot_seq"])
                await asyncio.sleep(5)

        return StreamingResponse(stream(), media_type="text/event-stream")

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
            endpoint_kind=request.endpoint_kind,
            timeout_seconds=request.timeout_seconds,
            thinking_level=request.thinking_level,
            thinking_fallback_policy=request.thinking_fallback_policy,
            status=request.status,
            qualification=request.qualification,
        )
        return ModelProfileResponse(profile=profile.to_json())

    @app.get("/v1/profiles/models", response_model=ModelProfileListResponse)
    async def list_model_profiles(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> ModelProfileListResponse:
        _require_control_auth(authorization)
        listed = await profiles.list_model_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 500)),
        )
        return ModelProfileListResponse(profiles=[profile.to_json() for profile in listed])

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

    @app.get("/v1/profiles/embeddings", response_model=ModelProfileListResponse)
    async def list_embedding_profiles(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
    ) -> ModelProfileListResponse:
        _require_control_auth(authorization)
        listed = await profiles.list_embedding_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=max(1, min(limit, 500)),
        )
        return ModelProfileListResponse(profiles=[profile.to_json() for profile in listed])

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
                probe_set_version=request.probe_set_version or "autoskill-text-profile-probes.v1",
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
                embedding_api_key=getattr(get_settings(), "embedding_api_key", None),
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

    @app.post(
        "/v1/context/compile-skillir",
        response_model=ContextSkillIRCompileResponse,
    )
    async def compile_context_skillir(
        request: ContextSkillIRCompileRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextSkillIRCompileResponse:
        _require_control_auth(authorization)
        result = await compile_skill_with_context_governance(
            request.skillir,
            context_governance,
            workspace_key=request.workspace_id,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            candidate_id=request.candidate_id,
            source_object_type=request.source_object_type,
            source_object_id=request.source_object_id,
            max_context_tokens=max(1, min(request.max_context_tokens, 10_000)),
            target_runtime_tokens=max(1, min(request.target_runtime_tokens, 10_000)),
            description_max_chars=max(1, min(request.description_max_chars, 1_000)),
            require_probe_evidence=request.require_probe_evidence,
            routing_equivalence_evidence=request.routing_equivalence_evidence,
            regression_evidence=request.regression_evidence,
        )
        return ContextSkillIRCompileResponse(result=result.to_json())

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

    @app.post("/v1/context/compile-runs", response_model=ContextCompileRunResponse)
    async def record_context_compile_run(
        request: ContextCompileRunRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextCompileRunResponse:
        _require_control_auth(authorization)
        run = await context_governance.record_compile_run(
            workspace_key=request.workspace_id,
            compiler_version=request.compiler_version,
            input_skillir_hash=request.input_skillir_hash,
            output_manifest_hash=request.output_manifest_hash,
            actual_runtime_tokens=request.actual_runtime_tokens,
            status=request.status,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            candidate_id=request.candidate_id,
            context_artifact_id=request.context_artifact_id,
            model_assist_used=request.model_assist_used,
            target_runtime_tokens=request.target_runtime_tokens,
            compression_ratio=request.compression_ratio,
            semantic_equivalence_score=request.semantic_equivalence_score,
            reject_reason=request.reject_reason,
            metadata=request.metadata,
        )
        return ContextCompileRunResponse(run=run.to_json())

    @app.post("/v1/context/budget-events", response_model=ContextBudgetEventResponse)
    async def record_context_budget_event(
        request: ContextBudgetEventRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ContextBudgetEventResponse:
        _require_control_auth(authorization)
        event = await context_governance.record_budget_event(
            workspace_key=request.workspace_id,
            event_type=request.event_type,
            decision=request.decision,
            skill_id=request.skill_id,
            skill_version_id=request.skill_version_id,
            context_artifact_id=request.context_artifact_id,
            tokens_delta=request.tokens_delta,
            marginal_success_delta=request.marginal_success_delta,
            false_positive_load_delta=request.false_positive_load_delta,
            ignored_load_delta=request.ignored_load_delta,
            shadowing_delta=request.shadowing_delta,
            evidence=request.evidence,
            metadata=request.metadata,
        )
        return ContextBudgetEventResponse(event=event.to_json())

    @app.post(
        "/v1/context/semantic-compression-trials",
        response_model=SemanticCompressionTrialResponse,
    )
    async def record_semantic_compression_trial(
        request: SemanticCompressionTrialRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SemanticCompressionTrialResponse:
        _require_control_auth(authorization)
        trial = await context_governance.record_semantic_compression_trial(
            workspace_key=request.workspace_id,
            source_tokens=request.source_tokens,
            candidate_tokens=request.candidate_tokens,
            preserved_requirements=request.preserved_requirements,
            lost_requirements=request.lost_requirements,
            added_unsupported_requirements=request.added_unsupported_requirements,
            equivalence_score=request.equivalence_score,
            status=request.status,
            skill_id=request.skill_id,
            source_revision_id=request.source_revision_id,
            candidate_revision_id=request.candidate_revision_id,
            source_context_artifact_id=request.source_context_artifact_id,
            candidate_context_artifact_id=request.candidate_context_artifact_id,
            target_probe_pass_rate=request.target_probe_pass_rate,
            regression_probe_pass_rate=request.regression_probe_pass_rate,
            metadata=request.metadata,
        )
        return SemanticCompressionTrialResponse(trial=trial.to_json())

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
            await audit.append_record(
                AuditRecord(
                    action="topology.propose",
                    subject_type="skill_graph_operation",
                    subject_id=str(persisted.operation.skill_graph_operation_id),
                    details={
                        "operation_kind": proposal.operation_kind,
                        "status": proposal.status,
                        "plan_hash": proposal.plan_hash,
                        "trial_count": len(persisted.trials),
                    },
                ),
                workspace_key=request.workspace_id,
            )
        return TopologyProposalResponse(
            proposal=proposal.to_json(),
            persistence=persistence,
        )

    @app.post(
        "/v1/topology/propose-from-usage",
        response_model=TopologyUsageProposalResponse,
    )
    async def propose_topology_operations_from_usage(
        request: TopologyUsageProposalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> TopologyUsageProposalResponse:
        _require_control_auth(authorization)
        recommendations = await usage.recommend_topology_operations(
            workspace_key=request.workspace_id,
            limit=request.limit,
            min_support=request.min_support,
            min_success_count=request.min_success_count,
            max_failure_ratio=request.max_failure_ratio,
            min_sequence_count=request.min_sequence_count,
        )
        proposals: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        for recommendation in recommendations:
            if not recommendation.accepted:
                skipped.append(
                    _usage_recommendation_skip(
                        recommendation,
                        reason="recommendation blocked by usage thresholds",
                    )
                )
                continue
            proposal_request = _usage_topology_proposal_request(recommendation)
            if proposal_request is None:
                skipped.append(
                    _usage_recommendation_skip(
                        recommendation,
                        reason=(
                            "usage recommendation lacks enough structured data "
                            "for a propose-only topology operation"
                        ),
                    )
                )
                continue
            proposal = _build_topology_proposal(
                proposal_request.model_copy(
                    update={
                        "workspace_id": request.workspace_id,
                        "persist": request.persist,
                    }
                )
            )
            persistence = None
            if request.persist:
                persisted = await persist_topology_proposal(
                    topology,
                    governance,
                    workspace_key=request.workspace_id,
                    proposal=proposal,
                )
                persistence = persisted.to_json()
            proposals.append(
                {
                    "recommendation": recommendation.to_json(),
                    "proposal": proposal.to_json(),
                    "persistence": persistence,
                }
            )
        return TopologyUsageProposalResponse(
            recommendations_scanned=len(recommendations),
            proposals=proposals,
            skipped=skipped,
        )

    @app.get("/v1/topology/metrics", response_model=TopologyMetricsResponse)
    async def topology_metrics(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> TopologyMetricsResponse:
        _require_control_auth(authorization)
        metrics = await topology.metrics(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 250)),
        )
        return TopologyMetricsResponse(**metrics)

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

    @app.get("/v1/proposals/review", response_model=ProposalReviewResponse)
    async def review_proposals(
        authorization: Annotated[str | None, Header()] = None,
        workspace_id: str | None = None,
        candidate_lifecycle_state: str | None = "candidate",
        topology_status: str | None = None,
        evaluation_status: str | None = None,
        limit: int = 100,
    ) -> ProposalReviewResponse:
        _require_control_auth(authorization)
        bounded_limit = max(1, min(limit, 250))
        candidate_rows = await candidates.list_candidate_reviews(
            workspace_key=workspace_id,
            lifecycle_state=candidate_lifecycle_state,
            limit=bounded_limit,
        )
        topology_rows = await topology.list_operations(
            workspace_key=workspace_id,
            status=topology_status,
            limit=bounded_limit,
        )
        evaluation_rows = await evaluations.list_evaluation_reviews(
            workspace_key=workspace_id,
            status=evaluation_status,
            limit=bounded_limit,
        )
        candidate_payload = [row.to_json() for row in candidate_rows]
        topology_payload = [row.to_json() for row in topology_rows]
        evaluation_payload = [row.to_json() for row in evaluation_rows]
        return ProposalReviewResponse(
            workspace_id=workspace_id,
            candidate_revisions=candidate_payload,
            topology_operations=topology_payload,
            evaluations=evaluation_payload,
            summary={
                "candidate_revision_count": len(candidate_payload),
                "candidate_lifecycle_states": _count_by(
                    candidate_payload,
                    "lifecycle_state",
                ),
                "candidate_scanner_statuses": _count_by(
                    candidate_payload,
                    "scanner_status",
                ),
                "candidate_evaluator_statuses": _count_by(
                    candidate_payload,
                    "evaluator_status",
                ),
                "topology_operation_count": len(topology_payload),
                "topology_operation_kinds": _count_by(
                    topology_payload,
                    "operation_kind",
                ),
                "topology_statuses": _count_by(topology_payload, "status"),
                "evaluation_count": len(evaluation_payload),
                "evaluation_statuses": _count_by(evaluation_payload, "status"),
                "review_surface": "section_30_phase_12",
            },
        )

    @app.post(
        "/v1/skillir/migrations/propose",
        response_model=SkillIRMigrationProposalResponse,
    )
    async def propose_skillir_migration(
        request: SkillIRMigrationProposalRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> SkillIRMigrationProposalResponse:
        _require_control_auth(authorization)
        result = propose_skill_ir_migration(
            source_skill_ir=request.source_skill_ir,
            source_revision_id=request.source_revision_id,
            migration_reason=request.migration_reason,
            compiler_version=request.compiler_version,
        )
        payload = result.to_json()
        if request.persist:
            persistence = await _persist_candidate_proposal_payload(
                candidates,
                governance,
                workspace_key=request.workspace_id,
                proposals=result.proposals,
                proposal_payload=payload,
                transaction_kind="skill_ir_migration",
                endpoint="/v1/skillir/migrations/propose",
                evolution_transaction_id=request.evolution_transaction_id,
                policy_snapshot={
                    "runtime_file_writes": "forbidden",
                    "candidate_state": "inactive",
                    "activation_allowed": False,
                    "source_revision_preserved": True,
                    "rollback_required": True,
                },
            )
            payload["persistence"] = persistence
        return SkillIRMigrationProposalResponse(**payload)

    @app.post(
        "/v1/historical-bootstrap/consolidate",
        response_model=HistoricalBootstrapConsolidateResponse,
    )
    async def consolidate_historical_bootstrap_route(
        request: HistoricalBootstrapConsolidateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HistoricalBootstrapConsolidateResponse:
        _require_control_auth(authorization)
        result = await consolidate_historical_bootstrap(
            evidence,
            retrieval,
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 1000)),
            min_support=max(2, min(request.min_support, 25)),
        )
        payload = result.to_json()
        if request.persist:
            persistence = await _persist_candidate_proposal_payload(
                candidates,
                governance,
                workspace_key=request.workspace_id,
                proposals=result.proposals.proposals,
                proposal_payload=payload["proposals"],
                transaction_kind="historical_bootstrap_consolidation",
                endpoint="/v1/historical-bootstrap/consolidate",
                evolution_transaction_id=request.evolution_transaction_id,
                policy_snapshot={
                    "historical_evidence_only": True,
                    "activation_allowed": False,
                    "runtime_file_writes": "forbidden",
                    "candidate_state": "inactive",
                },
            )
            payload["persistence"] = persistence
        return HistoricalBootstrapConsolidateResponse(**payload)

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
        contract_preflight = None
        if request.contract_preflight:
            preflight = await contracts.run_drift_checks(
                workspace_key=request.workspace_id,
                limit=max(1, min(request.contract_preflight_limit, 1000)),
            )
            contract_preflight = preflight.to_json()
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
        payload = result.to_json()
        payload["contract_preflight"] = contract_preflight
        return CurationRunResponse(**payload)

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
            await _check_writer_activation_window_for_api(
                activation_window_store,
                governance=governance,
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
        elif request.workspace_id:
            active_profile = await profiles.get_active_embedding_profile(
                workspace_key=request.workspace_id,
            )
            if active_profile is not None:
                embedder = _embedder_from_profile(active_profile, settings)
                embedding_model = active_profile.model
                embedding_profile_id = active_profile.profile_id
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
        bounded_limit = max(1, min(request.limit, 500))
        span = await observability.start_span(
            workspace_key=request.workspace_id or "default",
            operation_name="embeddings.generate",
            operation_kind="embedding_call",
            safe_attributes={
                "source": "api",
                "limit": bounded_limit,
                "embedding_profile_key": request.embedding_profile_key,
                "embedding_profile_id": str(embedding_profile_id) if embedding_profile_id else None,
                "embedding_model": embedding_model,
            },
        )
        try:
            result = await generate_pending_embeddings(
                embeddings,
                embedder=embedder,
                workspace_key=request.workspace_id,
                embedding_model=embedding_model,
                embedding_profile_id=embedding_profile_id,
                limit=bounded_limit,
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
                {
                    "object_type": str(source["object_type"]),
                    "object_id": str(source["object_id"]),
                }
                for source in result.sources[:50]
            ],
        )
        return EmbeddingGenerateResponse(**result.to_json())

    @app.post(
        "/v1/profiles/embeddings/validate-production",
        response_model=EmbeddingProductionValidationResponse,
    )
    async def validate_production_embedding_profile(
        request: EmbeddingProductionValidationRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> EmbeddingProductionValidationResponse:
        _require_control_auth(authorization)
        try:
            qualified = await qualify_embedding_profile(
                profiles=profiles,
                qualifications=profile_qualifications,
                workspace_key=request.workspace_id,
                profile_key=request.profile_key,
                probe_set_version=request.probe_set_version
                or "autoskill-embedding-production-validation.v1",
                embedding_api_key=getattr(get_settings(), "embedding_api_key", None),
            )
        except ProfileQualificationError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        generation = None
        if request.generate_embeddings and qualified.run.verdict == "qualified":
            generated = await generate_embeddings(
                request=EmbeddingGenerateRequest(
                    workspace_id=request.workspace_id,
                    embedding_profile_key=request.profile_key,
                    limit=request.generate_limit,
                ),
                authorization=authorization,
            )
            generation = generated.model_dump(mode="json")
        return EmbeddingProductionValidationResponse(
            qualified=qualified.run.verdict == "qualified",
            qualification=qualified.to_json(),
            generation=generation,
        )

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

    settings = get_settings()
    if settings.web_admin_enabled:
        static_dir = _admin_static_dir()
        if static_dir.exists():
            app.mount(
                _admin_base_path(),
                StaticFiles(directory=static_dir, html=True),
                name="skillkernel-observatory",
            )

    # Some existing unit tests inspect app.routes directly and assume every
    # route-like object has .methods. Starlette WebSocket and Mount routes do
    # not need it at runtime, but setting it keeps those tests focused on the
    # route they are exercising.
    for route in app.routes:
        if not hasattr(route, "methods"):
            route.methods = {"WEBSOCKET"} if route.path == "/admin/live" else {"GET"}

    return app
