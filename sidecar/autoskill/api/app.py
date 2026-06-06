from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from pathlib import Path
from time import monotonic
from typing import Annotated, Any
from uuid import UUID, uuid4

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
from autoskill.db.attribution import (
    AsyncpgAttributionStore,
    AttributionStore,
    NullAttributionStore,
)
from autoskill.db.audit import AsyncpgAuditStore, AuditStore, NullAuditStore
from autoskill.db.broker_policy import (
    AsyncpgBrokerPolicyStore,
    BrokerPolicyStore,
    NullBrokerPolicyStore,
)
from autoskill.db.candidates import (
    AsyncpgCandidateStore,
    CandidateStore,
    NullCandidateStore,
)
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
from autoskill.db.contracts import (
    AsyncpgContractStore,
    ContractStore,
    NullContractStore,
)
from autoskill.db.diagnostics import (
    AsyncpgDiagnosticMomentumStore,
    DiagnosticMomentumStore,
    NullDiagnosticMomentumStore,
)
from autoskill.db.embeddings import (
    AsyncpgEmbeddingStore,
    EmbeddingStore,
    NullEmbeddingStore,
)
from autoskill.db.evaluations import (
    AsyncpgEvaluationStore,
    EvaluationStore,
    NullEvaluationStore,
)
from autoskill.db.events import AsyncpgEventStore, EventStore, NullEventStore
from autoskill.db.evidence import AsyncpgEvidenceStore, EvidenceStore, NullEvidenceStore
from autoskill.db.external_skills import (
    AsyncpgExternalSkillStore,
    ExternalSkillInput,
    ExternalSkillStore,
    NullExternalSkillStore,
)
from autoskill.db.governance import (
    AsyncpgGovernanceStore,
    GovernanceStore,
    NullGovernanceStore,
)
from autoskill.db.historical import (
    AsyncpgHistoricalImportStore,
    HistoricalChunkInput,
    HistoricalImportStore,
    HistoricalSourceInput,
    NullHistoricalImportStore,
)
from autoskill.db.jobs import AsyncpgJobStore, JobStore, NullJobStore
from autoskill.db.lifecycle import (
    AsyncpgLifecycleStore,
    LifecycleStore,
    NullLifecycleStore,
)
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
from autoskill.db.retrieval import (
    AsyncpgRetrievalStore,
    NullRetrievalStore,
    RetrievalStore,
)
from autoskill.db.scheduler import (
    AsyncpgSchedulerStore,
    NullSchedulerStore,
    SchedulerStore,
)
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
from autoskill.services.llm import (
    LLMClient,
    LLMClientError,
    LLMCompletionRequest,
    LLMMessage,
)
from autoskill.services.matching import SkillMatchRequest, match_existing_skills
from autoskill.services.observatory import (
    action_receipt,
    build_live_envelope,
    build_observatory_snapshot,
    object_microscope,
    playbook_detail,
    search_observatory,
    storage_microscope,
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
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

DEFAULT_OBSERVATORY_WORKSPACE_ID = "dev-01"
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _admin_response_meta() -> dict[str, object]:
    return {
        "request_id": f"req_{uuid4().hex}",
        "generated_at": datetime.now(UTC).isoformat(),
        "redaction_level": "default",
        "warnings": [],
    }


class AdminResponseEnvelope(BaseModel):
    ok: bool = True
    data: dict[str, object] = Field(default_factory=dict)
    meta: dict[str, object] = Field(default_factory=_admin_response_meta)

    @model_validator(mode="after")
    def populate_data(self) -> AdminResponseEnvelope:
        if self.data:
            return self
        for key in (
            "config",
            "skillkernel",
            "snapshot",
            "collection",
            "object",
            "receipt",
        ):
            if hasattr(self, key):
                self.data = {key: getattr(self, key)}
                return self
        model_data = self.__dict__
        if {"query", "limit", "results"}.issubset(model_data):
            self.data = {
                "query": model_data["query"],
                "limit": model_data["limit"],
                "results": model_data["results"],
            }
        return self


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class StatusResponse(BaseModel):
    workspace_id: str | None = None
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


class EffectiveConfigResponse(AdminResponseEnvelope):
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


class ObservatoryConfigResponse(AdminResponseEnvelope):
    config: dict[str, object]


class ObservatorySnapshotResponse(AdminResponseEnvelope):
    snapshot: dict[str, object]


class ObservatorySearchResponse(AdminResponseEnvelope):
    query: str
    limit: int
    results: list[dict[str, object]]


class ObservatoryObjectResponse(AdminResponseEnvelope):
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


class ObservatoryActionResponse(AdminResponseEnvelope):
    receipt: dict[str, object]


class ObservatoryCollectionResponse(AdminResponseEnvelope):
    collection: dict[str, object]


ADMIN_CSRF_HEADER = "X-SkillKernel-CSRF"
ADMIN_BROWSER_SESSION_HEADER = "X-SkillKernel-Browser-Session"
ADMIN_ACTION_RATE_LIMIT = 60
ADMIN_RAW_REVEAL_RATE_LIMIT = 10
OBSERVATORY_HIGH_IMPACT_ACTIONS = {
    "historical_import",
    "quarantine_candidate",
    "freeze_skill",
    "unfreeze_skill",
    "rollback_skill",
    "rollback_transaction",
    "reveal_raw_content",
    "revoke_source",
}


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


class BrokerReplayEpisodeSynthesizeRequest(BaseModel):
    workspace_id: str
    limit: int = 50
    tags: list[str] = Field(default_factory=list)
    min_intent_chars: int = 8
    synthesize_missing_intents: bool = True
    synthesis_profile_key: str = "default-text"
    synthesis_context_limit: int = 8
    repair_existing_telemetry_episodes: bool = True


class BrokerReplayEpisodeSynthesizeResponse(BaseModel):
    episodes: list[dict[str, object]]
    skipped: list[dict[str, object]]


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


def _admin_static_available() -> bool:
    return True


def _admin_base_path() -> str:
    value = get_settings().web_admin_base_path.strip() or "/admin"
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/") or "/admin"


def _admin_csrf_token(authorization: str | None) -> str:
    settings = get_settings()
    bearer = ""
    if authorization and authorization.startswith("Bearer "):
        bearer = authorization.removeprefix("Bearer ").strip()
    seed = bearer or settings.web_admin_token or settings.control_token or "local-dev-admin"
    return sha256_text(f"skillkernel-observatory-csrf:{seed}")[:32]


def _is_admin_browser_action(request: Request | None) -> bool:
    if request is None:
        return False
    return (
        request.headers.get(ADMIN_BROWSER_SESSION_HEADER, "").lower() == "true"
        or bool(request.headers.get("origin"))
        or bool(request.headers.get("referer"))
        or bool(request.headers.get("cookie"))
    )


def _require_admin_csrf(
    *,
    request: Request | None,
    authorization: str | None,
    csrf_token: str | None,
) -> None:
    if not get_settings().web_admin_csrf_enabled or not _is_admin_browser_action(request):
        return
    supplied = csrf_token
    if not supplied and request is not None:
        supplied = request.headers.get(ADMIN_CSRF_HEADER)
    expected = _admin_csrf_token(authorization)
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="invalid admin csrf token",
        )


def _source_identity(request: Request | None) -> dict[str, object]:
    if request is None:
        return {"ip": None, "proxy": None}
    client_ip = request.client.host if request.client else None
    proxy = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    return {"ip": client_ip, "proxy": proxy}


def _observatory_action_request_fingerprint(
    *,
    request: ObservatoryActionRequest,
    target_type: str,
    target_id: str,
    confirmation_hash: str | None,
) -> str:
    payload = {
        "workspace_id": request.workspace_id,
        "action": request.action,
        "target_type": target_type,
        "target_id": target_id,
        "dry_run": request.dry_run,
        "metadata_keys": sorted(str(key) for key in request.metadata),
        "confirmation_hash": confirmation_hash,
        "reason_hash": sha256_text(request.reason or ""),
    }
    return f"sha256:{sha256_text(json.dumps(payload, sort_keys=True))}"


def _observatory_action_intent_hash(
    *,
    request: ObservatoryActionRequest,
    target_type: str,
    target_id: str,
    confirmation_hash: str | None,
) -> str:
    payload = {
        "workspace_id": request.workspace_id,
        "action": request.action,
        "target_type": target_type,
        "target_id": target_id,
        "dry_run": request.dry_run,
        "reason_hash": sha256_text(request.reason or ""),
        "confirmation_hash": confirmation_hash,
    }
    return f"sha256:{sha256_text(json.dumps(payload, sort_keys=True))}"


def _observatory_action_risk_tier(action: str, *, dry_run: bool) -> str:
    if action == "reveal_raw_content" and not dry_run:
        return "critical"
    if action in OBSERVATORY_HIGH_IMPACT_ACTIONS and not dry_run:
        return "high"
    if action in OBSERVATORY_HIGH_IMPACT_ACTIONS:
        return "medium"
    return "low"


def _action_attribution_check_receipt(record: Any | None) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "schema_version": "skillkernel.observatory.action-attribution-link.v1",
        "action_attribution_check_id": str(record.action_attribution_check_id),
        "action_kind": record.action_kind,
        "risk_tier": record.risk_tier,
        "verdict": record.verdict,
        "counterfactual_kind": record.counterfactual_kind,
    }


def _encode_admin_cursor(item: dict[str, Any]) -> str | None:
    object_id = _admin_cursor_object_id(item)
    if not object_id:
        return None
    payload = {
        "id": object_id,
        "t": _admin_cursor_time(item),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_admin_cursor(cursor: str) -> dict[str, str]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="invalid admin pagination cursor",
        ) from exc
    if not isinstance(payload, dict) or not payload.get("id"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="invalid admin pagination cursor",
        )
    return {"id": str(payload["id"]), "t": str(payload.get("t") or "")}


def _admin_cursor_object_id(item: dict[str, Any]) -> str | None:
    for key in (
        "object_id",
        "event_id",
        "trace_id",
        "job_id",
        "schedule_id",
        "skill_id",
        "skill_version_id",
        "evaluation_id",
        "historical_import_source_id",
        "retrieval_log_id",
        "profile_id",
        "audit_id",
        "comparison_id",
        "bundle_id",
        "component_id",
        "subsystem_id",
        "reason_code",
        "playbook_id",
        "invariant_id",
    ):
        value = item.get(key)
        if value is not None:
            return str(value)
    return None


def _admin_cursor_time(item: dict[str, Any]) -> str:
    for key in ("created_at", "occurred_at", "last_event_at", "started_at", "captured_at"):
        value = item.get(key)
        if value is not None:
            return str(value)
    return ""


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


def _broker_replay_corpus_detail(
    episodes: list[Any],
    *,
    replay_tag: str,
) -> dict[str, object]:
    operator_reviewed = 0
    source_linked = 0
    telemetry_derived = 0
    degraded_fidelity = 0
    expected_decisions: dict[str, int] = {}
    episode_keys: list[str] = []
    distinct_episode_keys: set[str] = set()
    for episode in episodes:
        tags = set(getattr(episode, "tags", []) or [])
        metadata = getattr(episode, "metadata", {}) or {}
        if getattr(episode, "episode_key", None):
            episode_key = str(episode.episode_key)
            episode_keys.append(episode_key)
            distinct_episode_keys.add(episode_key)
        if "operator-reviewed" in tags:
            operator_reviewed += 1
        if getattr(episode, "source_retrieval_log_id", None):
            source_linked += 1
        if "telemetry-derived" in tags or metadata.get("source") == "automatic_replay_synthesis":
            telemetry_derived += 1
        if metadata.get("evidence_fidelity") in {"metadata_only", "hash_only"}:
            degraded_fidelity += 1
        decision = str(getattr(episode, "expected_decision", None) or "unspecified")
        expected_decisions[decision] = expected_decisions.get(decision, 0) + 1
    return {
        "tag": replay_tag,
        "sampled": len(episodes),
        "distinct_sampled": len(distinct_episode_keys),
        "operator_reviewed": operator_reviewed,
        "source_linked": source_linked,
        "telemetry_derived": telemetry_derived,
        "degraded_fidelity": degraded_fidelity,
        "expected_decisions": expected_decisions,
        "episode_keys": episode_keys[:25],
    }


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
        limit=100,
    )
    replay_detail = _broker_replay_corpus_detail(
        replay_episodes,
        replay_tag=replay_tag,
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "broker_replay_corpus",
        passed=bool(replay_episodes),
        detail=replay_detail,
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "operator_reviewed_broker_replay_corpus",
        passed=int(replay_detail["operator_reviewed"]) > 0,
        detail={
            "tag": replay_tag,
            "operator_reviewed": replay_detail["operator_reviewed"],
            "sampled": replay_detail["sampled"],
        },
    )
    _readiness_check(
        checks,
        blockers,
        warnings,
        "telemetry_linked_broker_replay_corpus",
        passed=int(replay_detail["source_linked"]) > 0,
        required=False,
        detail={
            "tag": replay_tag,
            "source_linked": replay_detail["source_linked"],
            "telemetry_derived": replay_detail["telemetry_derived"],
            "sampled": replay_detail["sampled"],
        },
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


REPLAY_SYNTHESIS_ALLOWED_FIDELITY = {
    "raw_vault_linked",
    "declassified_summary",
    "redacted_derivative",
}
REPLAY_SYNTHESIS_SECRET_MARKERS = (
    "sk-",
    "api_key",
    "apikey",
    "authorization:",
    "bearer ",
    "password",
    "token=",
    "secret",
)


def _broker_replay_synthesis_candidate(
    log: Any,
    *,
    min_intent_chars: int,
    metadata_overlay: dict[str, Any] | None = None,
) -> tuple[dict[str, object] | None, str]:
    metadata = log.metadata if isinstance(log.metadata, dict) else {}
    if metadata_overlay:
        metadata = {**metadata, **metadata_overlay}
    intent, intent_source = _redacted_replay_intent(metadata)
    if intent is None or len(intent) < min_intent_chars:
        return None, "missing-redacted-intent"
    lowered = intent.lower()
    if any(marker in lowered for marker in REPLAY_SYNTHESIS_SECRET_MARKERS):
        return None, "redacted-intent-secret-marker"

    evidence_fidelity = _metadata_text(
        metadata,
        "evidence_fidelity",
        "replay.evidence_fidelity",
        "semantic_adjudication.evidence_fidelity",
        "evidence.fidelity",
    )
    if evidence_fidelity not in REPLAY_SYNTHESIS_ALLOWED_FIDELITY:
        return None, f"unsupported-evidence-fidelity:{evidence_fidelity or 'missing'}"

    adjudication_source = _metadata_text(
        metadata,
        "redacted_intent_source",
        "replay.redacted_intent_source",
        "semantic_adjudication.source",
        "semantic_adjudication.adjudicator",
    )
    semantic_adjudication = _metadata_path(metadata, "semantic_adjudication")
    llm_backed = (
        isinstance(adjudication_source, str)
        and "llm" in adjudication_source.lower()
    ) or isinstance(semantic_adjudication, dict)
    if not llm_backed:
        return None, "missing-llm-adjudication"

    validation = _metadata_path(metadata, "deterministic_validation")
    validation_status = _metadata_text(
        metadata,
        "deterministic_validation.status",
        "replay.deterministic_validation.status",
        "semantic_adjudication.deterministic_validation.status",
    )
    if validation_status not in {"passed", "valid", "validated", "ok"}:
        return None, f"deterministic-validation-not-passed:{validation_status or 'missing'}"

    expected_skill_ids = list(log.rendered_skill_ids or log.candidate_skill_ids or [])
    expected_decision = _expected_replay_decision(log, metadata=metadata)
    metadata_payload = {
        "source": "automatic_replay_synthesis",
        "source_retrieval_log_id": str(log.retrieval_log_id),
        "trace_id": str(log.trace_id) if log.trace_id else None,
        "span_id": str(log.span_id) if log.span_id else None,
        "session_id": log.session_id,
        "turn_id": log.turn_id,
        "evidence_fidelity": evidence_fidelity,
        "redacted_intent_source": adjudication_source or intent_source,
        "deterministic_validation": validation if isinstance(validation, dict) else {},
        "raw_prompt_stored": False,
        "operator_plan_required": False,
        "normal_path": True,
    }
    if isinstance(metadata.get("candidate_count"), int):
        metadata_payload["candidate_count"] = metadata["candidate_count"]
    context_object_types = metadata.get("context_object_types")
    if isinstance(context_object_types, list):
        metadata_payload["context_object_types"] = context_object_types
    return (
        {
            "episode_key": f"telemetry-{str(log.retrieval_log_id)[:12]}",
            "redacted_user_intent": intent,
            "expected_decision": expected_decision,
            "expected_skill_ids": expected_skill_ids,
            "metadata": metadata_payload,
            "source_retrieval_log_id": log.retrieval_log_id,
        },
        "eligible",
    )


def _redacted_replay_intent(metadata: dict[str, Any]) -> tuple[str | None, str]:
    paths = (
        "redacted_user_intent",
        "redacted_intent",
        "replay.redacted_user_intent",
        "semantic_adjudication.redacted_user_intent",
        "semantic_adjudication.redacted_intent",
    )
    for path in paths:
        value = _metadata_path(metadata, path)
        if isinstance(value, str) and value.strip():
            return value.strip(), path
    return None, ""


def _metadata_text(metadata: dict[str, Any], *paths: str) -> str | None:
    for path in paths:
        value = _metadata_path(metadata, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metadata_path(metadata: dict[str, Any], path: str) -> Any:
    current: Any = metadata
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _expected_replay_decision(log: Any, *, metadata: dict[str, Any] | None = None) -> str:
    if log.rendered_skill_ids:
        return "skill_hint"
    decision = str(log.decision or "")
    if metadata is None:
        metadata = log.metadata if isinstance(log.metadata, dict) else {}
    candidate_count = metadata.get("candidate_count")
    if log.candidate_skill_ids:
        return "skill_hint"
    if isinstance(candidate_count, int) and candidate_count > 0:
        return "defer_skill"
    if log.no_skill_control or decision in {
        "no_skill",
        "no_candidates",
        "empty_query",
        "retrieval-empty",
    }:
        return "no_skill"
    if decision in {"defer_skill", "evidence_only", "evidence-only"}:
        return "defer_skill"
    return "no_skill"


async def _synthesize_redacted_replay_intent(
    *,
    log: Any,
    workspace_key: str,
    context: list[Any],
    text_llm: LLMClient,
    profile_key: str,
    min_intent_chars: int,
) -> tuple[dict[str, Any] | None, str]:
    safe_context = [
        candidate
        for candidate in context
        if str(getattr(candidate, "summary", "")).strip()
        and getattr(candidate, "object_type", "") in {
            "body_index_document",
            "evidence_item",
            "external_skill",
        }
    ]
    if not safe_context:
        return None, "missing-content-safe-replay-context"
    if not any(
        getattr(candidate, "object_type", "") in {"body_index_document", "evidence_item"}
        for candidate in safe_context
    ):
        return None, "unsupported-evidence-fidelity:metadata_only"

    context_lines = []
    for index, candidate in enumerate(safe_context[:8], start=1):
        summary = " ".join(str(candidate.summary).split())
        context_lines.append(
            json.dumps(
                {
                    "rank": index,
                    "object_type": candidate.object_type,
                    "skill_id": str(candidate.skill_id) if candidate.skill_id else None,
                    "summary": summary[:700],
                },
                sort_keys=True,
            )
        )
    prompt = (
        "You synthesize content-safe replay intents for SkillKernel broker canaries.\n"
        "Use only the redacted/derived retrieval context below. Do not infer or invent "
        "private raw content, names, secrets, or exact prompt wording. Return only JSON "
        "with this shape: {\"redacted_user_intent\":\"short safe operator intent\"}.\n\n"
        f"Broker decision: {getattr(log, 'decision', '')}\n"
        f"Reason metadata: {json.dumps(_replay_reason_metadata(log), sort_keys=True)}\n"
        "Content-safe retrieval context:\n"
        + "\n".join(context_lines)
    )
    try:
        response = await text_llm.complete(
            LLMCompletionRequest(
                workspace_key=workspace_key,
                profile_key=profile_key,
                purpose="broker_replay.redacted_intent_synthesis",
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "Return strict JSON only. Never include raw user text, "
                            "secrets, credentials, personal data, or markdown."
                        ),
                    ),
                    LLMMessage(role="user", content=prompt),
                ],
                max_output_tokens=160,
                temperature=0.0,
                trace_id=getattr(log, "trace_id", None),
                span_id=getattr(log, "span_id", None),
            )
        )
    except (LLMClientError, ValueError, OSError) as exc:
        return None, f"llm-synthesis-failed:{type(exc).__name__}"

    parsed = _json_object_from_text(response.text)
    intent = str(parsed.get("redacted_user_intent") or "").strip()
    validation = _validate_synthesized_replay_intent(
        intent,
        min_intent_chars=min_intent_chars,
        context_count=len(safe_context),
    )
    if validation["status"] != "passed":
        return None, f"deterministic-validation-not-passed:{validation['reason']}"
    context_metadata = _replay_context_metadata(safe_context)
    return (
        {
            "redacted_user_intent": intent,
            "redacted_intent_source": "llm_synthesized_from_content_safe_retrieval",
            "evidence_fidelity": "redacted_derivative",
            "deterministic_validation": validation,
            **context_metadata,
        },
        "eligible",
    )


def _replay_reason_metadata(log: Any) -> dict[str, Any]:
    metadata = log.metadata if isinstance(log.metadata, dict) else {}
    return {
        "reason_codes": metadata.get("reason_codes") or [],
        "candidate_count": metadata.get("candidate_count"),
        "rendered_skill_count": len(getattr(log, "rendered_skill_ids", []) or []),
        "no_skill_control": bool(getattr(log, "no_skill_control", False)),
    }


def _json_object_from_text(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return {}
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


def _validate_synthesized_replay_intent(
    intent: str,
    *,
    min_intent_chars: int,
    context_count: int,
) -> dict[str, Any]:
    lowered = intent.lower()
    if len(intent) < min_intent_chars:
        return {"status": "failed", "reason": "too-short", "context_count": context_count}
    if any(marker in lowered for marker in REPLAY_SYNTHESIS_SECRET_MARKERS):
        return {
            "status": "failed",
            "reason": "secret-marker",
            "context_count": context_count,
        }
    if "\n" in intent or "```" in intent:
        return {
            "status": "failed",
            "reason": "non-compact-output",
            "context_count": context_count,
        }
    return {
        "status": "passed",
        "schema": "redacted-intent.v1",
        "context_count": context_count,
        "checks": [
            "minimum_length",
            "secret_marker_absent",
            "single_line",
            "content_safe_context_only",
        ],
    }


def _replay_context_metadata(context: list[Any]) -> dict[str, Any]:
    object_types = [
        str(getattr(candidate, "object_type", ""))
        for candidate in context
        if str(getattr(candidate, "object_type", "")).strip()
    ]
    return {
        "candidate_count": len(object_types),
        "context_object_types": sorted(set(object_types)),
    }


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
    admin_rate_limit_events: dict[tuple[str, str], list[float]] = {}

    def _require_admin_rate_limit(
        principal: dict[str, object],
        *,
        bucket: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        actor = str(principal["subject"])
        now = monotonic()
        key = (actor, bucket)
        recent = [
            event_at
            for event_at in admin_rate_limit_events.get(key, [])
            if now - event_at < window_seconds
        ]
        if len(recent) >= limit:
            admin_rate_limit_events[key] = recent
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail="admin rate limit exceeded",
            )
        recent.append(now)
        admin_rate_limit_events[key] = recent

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

    @app.middleware("http")
    async def admin_browser_security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers.setdefault(
                "Content-Security-Policy",
                (
                    "default-src 'self'; "
                    "script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob:; "
                    "font-src 'self' data:; "
                    "connect-src 'self' ws: wss:; "
                    "worker-src 'self' blob:; "
                    "object-src 'none'; "
                    "base-uri 'none'; "
                    "form-action 'none'; "
                    "frame-ancestors 'none'"
                ),
            )
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service="autoskill-sidecar", version=__version__)

    @app.get("/v1/status", response_model=StatusResponse)
    async def status(workspace_id: str | None = None) -> StatusResponse:
        settings = get_settings()
        effective_workspace_id = (
            workspace_id
            or os.environ.get("AUTOSKILL_WORKSPACE_ID")
            or DEFAULT_OBSERVATORY_WORKSPACE_ID
        )
        job_summary = await jobs.summary(workspace_key=effective_workspace_id)
        worker_health = await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": settings.worker_scheduler_concurrency,
                "maintenance": settings.worker_maintenance_concurrency,
                "mutation": settings.worker_mutation_concurrency,
            },
            workspace_key=effective_workspace_id,
        )
        return StatusResponse(
            workspace_id=effective_workspace_id,
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

    @app.post(
        "/v1/broker/replay-episodes/synthesize",
        response_model=BrokerReplayEpisodeSynthesizeResponse,
    )
    async def synthesize_broker_replay_episodes(
        request: BrokerReplayEpisodeSynthesizeRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> BrokerReplayEpisodeSynthesizeResponse:
        _require_control_auth(authorization)
        logs = await retrieval.list_recent_logs(
            workspace_key=request.workspace_id,
            limit=max(1, min(request.limit, 250)),
        )
        base_tags = {
            "production",
            "redacted",
            "telemetry-derived",
            "llm-synthesized",
        }
        tags = sorted(base_tags | {tag for tag in request.tags if tag.strip()})
        episodes: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        processed_log_ids: set[UUID] = set()
        for log in logs:
            processed_log_ids.add(log.retrieval_log_id)
            candidate, reason = _broker_replay_synthesis_candidate(
                log,
                min_intent_chars=max(1, request.min_intent_chars),
            )
            if (
                candidate is None
                and reason == "missing-redacted-intent"
                and request.synthesize_missing_intents
            ):
                context = await retrieval.replay_context_for_log(
                    workspace_key=request.workspace_id,
                    retrieval_log_id=log.retrieval_log_id,
                    limit=max(1, min(request.synthesis_context_limit, 25)),
                )
                metadata_overlay, synthesis_reason = await _synthesize_redacted_replay_intent(
                    log=log,
                    workspace_key=request.workspace_id,
                    context=context,
                    text_llm=text_llm,
                    profile_key=request.synthesis_profile_key,
                    min_intent_chars=max(1, request.min_intent_chars),
                )
                if metadata_overlay is not None:
                    candidate, reason = _broker_replay_synthesis_candidate(
                        log,
                        min_intent_chars=max(1, request.min_intent_chars),
                        metadata_overlay=metadata_overlay,
                    )
                else:
                    reason = synthesis_reason
            if candidate is None:
                skipped.append(
                    {
                        "retrieval_log_id": str(log.retrieval_log_id),
                        "reason": reason,
                    }
                )
                continue
            episode = await broker_policies.record_replay_episode(
                workspace_key=request.workspace_id,
                episode_key=str(candidate["episode_key"]),
                redacted_user_intent=str(candidate["redacted_user_intent"]),
                expected_decision=str(candidate["expected_decision"]),
                expected_skill_ids=list(candidate["expected_skill_ids"]),
                tags=tags,
                metadata=dict(candidate["metadata"]),
                source_retrieval_log_id=candidate["source_retrieval_log_id"],
            )
            episodes.append(episode.to_json())
        if request.repair_existing_telemetry_episodes:
            existing = await broker_policies.list_replay_episodes(
                workspace_key=request.workspace_id,
                tags=["telemetry-derived"],
                limit=500,
            )
            for record in existing:
                if (
                    record.source_retrieval_log_id is None
                    or record.source_retrieval_log_id in processed_log_ids
                    or record.metadata.get("source") != "automatic_replay_synthesis"
                ):
                    continue
                processed_log_ids.add(record.source_retrieval_log_id)
                log = await retrieval.get_log(
                    workspace_key=request.workspace_id,
                    retrieval_log_id=record.source_retrieval_log_id,
                )
                if log is None:
                    skipped.append(
                        {
                            "retrieval_log_id": str(record.source_retrieval_log_id),
                            "episode_key": record.episode_key,
                            "reason": "source-retrieval-log-missing",
                        }
                    )
                    continue
                context = await retrieval.replay_context_for_log(
                    workspace_key=request.workspace_id,
                    retrieval_log_id=record.source_retrieval_log_id,
                    limit=max(1, min(request.synthesis_context_limit, 25)),
                )
                metadata_overlay = {
                    **record.metadata,
                    "redacted_user_intent": record.redacted_user_intent,
                    **_replay_context_metadata(context),
                }
                candidate, reason = _broker_replay_synthesis_candidate(
                    log,
                    min_intent_chars=max(1, request.min_intent_chars),
                    metadata_overlay=metadata_overlay,
                )
                if candidate is None:
                    skipped.append(
                        {
                            "retrieval_log_id": str(record.source_retrieval_log_id),
                            "episode_key": record.episode_key,
                            "reason": reason,
                        }
                    )
                    continue
                episode = await broker_policies.record_replay_episode(
                    workspace_key=request.workspace_id,
                    episode_key=str(candidate["episode_key"]),
                    redacted_user_intent=str(candidate["redacted_user_intent"]),
                    expected_decision=str(candidate["expected_decision"]),
                    expected_skill_ids=list(candidate["expected_skill_ids"]),
                    tags=tags,
                    metadata=dict(candidate["metadata"]),
                    source_retrieval_log_id=candidate["source_retrieval_log_id"],
                )
                episodes.append(episode.to_json())
        return BrokerReplayEpisodeSynthesizeResponse(
            episodes=episodes,
            skipped=skipped,
        )

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
        production_replay_detail = _broker_replay_corpus_detail(
            production_replay_episodes,
            replay_tag="production",
        )
        if production_replay_episodes and not production_replay_detail["operator_reviewed"]:
            warnings.append("operator-reviewed production broker replay corpus is empty")
        if production_replay_episodes and not production_replay_detail["source_linked"]:
            warnings.append("source-linked production broker replay corpus is empty")
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
                "sampled_operator_reviewed_production": production_replay_detail[
                    "operator_reviewed"
                ],
                "sampled_source_linked_production": production_replay_detail[
                    "source_linked"
                ],
                "sampled_telemetry_derived_production": production_replay_detail[
                    "telemetry_derived"
                ],
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
        workspace_id: str | None = None,
        status_filter: Annotated[str | None, Query(alias="status")] = None,
        limit: int = 50,
    ) -> dict[str, list[dict[str, object]]]:
        _require_control_auth(authorization)
        listed = await jobs.list_jobs(
            workspace_key=workspace_id,
            status=status_filter,
            limit=max(1, min(limit, 250)),
        )
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
        effective_workspace_id = (
            workspace_id
            or os.environ.get("AUTOSKILL_WORKSPACE_ID")
            or DEFAULT_OBSERVATORY_WORKSPACE_ID
        )
        bounded_window = max(1, min(window_minutes, 24 * 60))
        job_summary = await jobs.summary(workspace_key=effective_workspace_id)
        worker_health = await build_worker_health(
            jobs,
            concurrency_by_pool={
                "scheduler": settings.worker_scheduler_concurrency,
                "maintenance": settings.worker_maintenance_concurrency,
                "mutation": settings.worker_mutation_concurrency,
            },
            workspace_key=effective_workspace_id,
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
            workspace_key=effective_workspace_id,
            window_minutes=bounded_window,
            storage_limit=100,
        )
        audit_chain_valid = await audit.verify_chain(
            workspace_key=effective_workspace_id,
            limit=max(1, min(audit_limit, 10_000)),
        )
        static_available = _admin_static_available()
        return build_observatory_snapshot(
            settings=settings,
            status=status_payload,
            operator_metrics=metrics_snapshot,
            worker_health=worker_health.to_json(),
            audit_chain_valid=audit_chain_valid,
            static_available=static_available,
            workspace_id=effective_workspace_id,
            window_minutes=bounded_window,
        )

    def _missing_read_model(
        object_type: str,
        *,
        supporting_component: str | None = None,
    ) -> dict[str, Any]:
        return {
            "health": "unknown",
            "reason_codes": ["read-model-missing"],
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
        cursor: str | None = None,
        source: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> ObservatoryCollectionResponse:
        bounded_limit = max(1, min(limit, 500))
        start_index = 0
        decoded_cursor = _decode_admin_cursor(cursor) if cursor else None
        if decoded_cursor is not None:
            for index, item in enumerate(items):
                if _admin_cursor_object_id(item) == decoded_cursor["id"]:
                    start_index = index + 1
                    break
            else:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="admin pagination cursor is outside the bounded result window",
                )
        window = items[start_index : start_index + bounded_limit + 1]
        visible_items = window[:bounded_limit]
        has_more = len(window) > bounded_limit or len(items) > start_index + bounded_limit
        next_cursor = (
            _encode_admin_cursor(visible_items[-1]) if has_more and visible_items else None
        )
        meta = _admin_response_meta()
        meta["pagination"] = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "limit": bounded_limit,
            "has_more": has_more,
        }
        return ObservatoryCollectionResponse(
            collection={
                "schema_version": "skillkernel.observatory.collection.v1",
                "object_type": object_type,
                "title": title,
                "items": visible_items,
                "count": len(visible_items),
                "limit": bounded_limit,
                "cursor": cursor,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "source": source,
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                    "redaction_state": "redacted_or_not_applicable",
                },
                "diagnostics": diagnostics or {},
            },
            meta=meta,
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

    def _component_metrics_microscope(
        component_id: str,
        component: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "skillkernel.observatory.component-metrics.v1",
            "object_type": "component_metrics",
            "object_id": component_id,
            "title": f"{component_id} metrics",
            "summary": "Component signal contract, bounded records, and data-quality state.",
            "metrics": component.get("signal_contract", {}) if component else {},
            "records": component.get("records", []) if component else [],
            "diagnostics": component
            or _missing_read_model("component_metrics", supporting_component=component_id),
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
            "provenance": {
                "upstream": [{"object_type": "component", "object_id": component_id}],
                "downstream": [],
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _skill_microscope(
        skill_id: str,
        skill: dict[str, Any] | None,
        *,
        object_type: str = "skill",
    ) -> dict[str, Any]:
        upstream: list[dict[str, str]] = []
        downstream: list[dict[str, str]] = []
        if skill and object_type == "skill_version" and skill.get("skill_id"):
            upstream.append({"object_type": "skill", "object_id": str(skill["skill_id"])})
        if skill and object_type == "skill" and skill.get("active_version_id"):
            downstream.append(
                {
                    "object_type": "skill_version",
                    "object_id": str(skill["active_version_id"]),
                }
            )
        return {
            "schema_version": "skillkernel.observatory.skill.v1",
            "object_type": object_type,
            "object_id": skill_id,
            "title": skill.get("name", skill_id) if skill else skill_id,
            "summary": (
                "Skill lifecycle, active version, scanner/evaluator state, "
                "and manifest metadata."
            ),
            "diagnostics": skill
            or _missing_read_model("skill", supporting_component="skill_ir_graph_ir"),
            "timeline": [],
            "provenance": {"upstream": upstream, "downstream": downstream},
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "skillir_available": False,
                "compiled_text_available": False,
            },
            "audit": {"links": []},
        }

    def _candidate_microscope(
        candidate_id: str,
        candidate: dict[str, Any] | None,
    ) -> dict[str, Any]:
        upstream: list[dict[str, str]] = []
        downstream: list[dict[str, str]] = []
        if candidate:
            if candidate.get("created_by_transaction_id"):
                upstream.append(
                    {
                        "object_type": "evolution_transaction",
                        "object_id": str(candidate["created_by_transaction_id"]),
                    }
                )
            if candidate.get("skill_id"):
                downstream.append(
                    {"object_type": "skill", "object_id": str(candidate["skill_id"])}
                )
            if candidate.get("skill_version_id"):
                downstream.append(
                    {
                        "object_type": "skill_version",
                        "object_id": str(candidate["skill_version_id"]),
                    }
                )
        return {
            "schema_version": "skillkernel.observatory.candidate.v1",
            "object_type": "candidate",
            "object_id": candidate_id,
            "title": candidate.get("name", candidate_id) if candidate else candidate_id,
            "summary": "Candidate SkillIR/proposal review state.",
            "diagnostics": candidate
            or _missing_read_model("candidate", supporting_component="opportunity_mining"),
            "timeline": [],
            "provenance": {"upstream": upstream, "downstream": downstream},
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "skillir_available": False,
                "compiled_text_available": False,
            },
            "audit": {"links": []},
        }

    def _job_microscope(job_id: str, job: dict[str, Any] | None) -> dict[str, Any]:
        downstream: list[dict[str, str]] = []
        if job:
            if job.get("trace_id"):
                downstream.append(
                    {"object_type": "trace", "object_id": str(job["trace_id"])}
                )
            if job.get("span_id"):
                downstream.append(
                    {"object_type": "trace_span", "object_id": str(job["span_id"])}
                )
        return {
            "schema_version": "skillkernel.observatory.job.v1",
            "object_type": "job",
            "object_id": job_id,
            "title": f"Job {job_id}",
            "summary": "Sidecar scheduler job detail.",
            "diagnostics": job
            or _missing_read_model("job", supporting_component="scheduler_jobs"),
            "timeline": [],
            "provenance": {"upstream": [], "downstream": downstream},
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
            },
            "audit": {"links": []},
        }

    def _schedule_admin_record(schedule: dict[str, Any]) -> dict[str, Any]:
        payload = schedule.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        payload_keys = (
            sorted(str(key) for key in payload_dict)
            if payload_dict
            else sorted(str(key) for key in schedule.get("payload_keys", []))
            if isinstance(schedule.get("payload_keys"), list)
            else []
        )
        safe = {
            "schedule_id": str(schedule.get("schedule_id")),
            "workspace_key": schedule.get("workspace_key"),
            "name": schedule.get("name"),
            "job_kind": schedule.get("job_kind"),
            "enabled": bool(schedule.get("enabled")),
            "interval_seconds": schedule.get("interval_seconds"),
            "next_run_at": schedule.get("next_run_at"),
            "misfire_policy": schedule.get("misfire_policy"),
            "payload_keys": payload_keys,
            "payload_sha256": sha256_text(
                json.dumps(payload_dict, sort_keys=True, default=str)
            )
            if payload_dict
            else schedule.get("payload_sha256"),
            "payload_available": False,
            "payload_redaction": "metadata-only",
        }
        safe["object_type"] = "schedule"
        safe["object_id"] = safe["schedule_id"]
        safe["title"] = str(safe["name"] or safe["schedule_id"])
        safe["summary"] = (
            f"{safe['job_kind']}; every {safe['interval_seconds']}s; "
            f"enabled={safe['enabled']}; misfire={safe['misfire_policy']}"
        )
        return safe

    def _schedule_microscope(
        schedule_id: str,
        schedule: dict[str, Any] | None,
    ) -> dict[str, Any]:
        diagnostics = (
            _schedule_admin_record(schedule)
            if schedule
            else _missing_read_model("schedule", supporting_component="scheduler_jobs")
        )
        timeline = []
        if schedule:
            timeline.append(
                {
                    "at": schedule.get("next_run_at"),
                    "event": "next_run_scheduled",
                    "status": "enabled" if schedule.get("enabled") else "paused",
                    "job_kind": schedule.get("job_kind"),
                    "misfire_policy": schedule.get("misfire_policy"),
                }
            )
        return {
            "schema_version": "skillkernel.observatory.schedule.v1",
            "object_type": "schedule",
            "object_id": schedule_id,
            "title": (
                str(schedule.get("name"))
                if schedule and schedule.get("name")
                else f"Schedule {schedule_id}"
            ),
            "summary": "Sidecar-owned scheduler configuration and next-run state.",
            "diagnostics": diagnostics,
            "timeline": timeline,
            "provenance": {
                "upstream": [],
                "downstream": [],
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "payload_available": False,
            },
            "audit": {"links": []},
        }

    def _profile_configuration_payload(profile: Any) -> dict[str, Any]:
        payload = profile.to_json()
        endpoint_ref = payload.pop("endpoint_ref", None)
        payload["endpoint_ref_present"] = bool(endpoint_ref)
        payload["endpoint_ref_sha256"] = (
            sha256_text(str(endpoint_ref)) if endpoint_ref else None
        )
        payload.pop("qualification", None)
        return payload

    def _qualification_run_summary(run: Any) -> dict[str, Any]:
        payload = run.to_json()
        probe_results = payload.pop("probe_results", {})
        checks = (
            dict(probe_results.get("checks", {}))
            if isinstance(probe_results, dict)
            and isinstance(probe_results.get("checks"), dict)
            else {}
        )
        metrics: dict[str, Any] = {}
        if isinstance(probe_results, dict):
            for key in (
                "output_token_estimate",
                "positive_similarity",
                "negative_similarity",
                "distance_metric",
            ):
                if key in probe_results:
                    metrics[key] = probe_results[key]
            invocation_id = probe_results.get("invocation_id")
            if invocation_id:
                metrics["llm_invocation_ref"] = {
                    "object_type": "llm_invocation",
                    "object_id": str(invocation_id),
                }
        run_id = (
            payload.get("model_profile_qualification_run_id")
            or payload.get("embedding_profile_qualification_run_id")
        )
        return {
            "qualification_run_id": str(run_id) if run_id else None,
            "profile_key": payload.get("profile_key"),
            "route_kind": payload.get("route_kind"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "thinking_level": payload.get("thinking_level"),
            "embedding_dim": payload.get("embedding_dim"),
            "distance_metric": payload.get("distance_metric"),
            "probe_set_version": payload.get("probe_set_version"),
            "verdict": payload.get("verdict"),
            "checks": checks,
            "metrics": metrics,
            "created_at": payload.get("created_at"),
            "expires_at": payload.get("expires_at"),
            "raw_probe_results_returned": False,
            "raw_error_returned": False,
        }

    def _qualification_run_microscope(run: Any, *, object_type: str) -> dict[str, Any]:
        summary = _qualification_run_summary(run)
        run_id = str(summary["qualification_run_id"])
        profile_kind = "text model" if object_type.startswith("model") else "embedding"
        downstream = []
        invocation_ref = summary["metrics"].get("llm_invocation_ref")
        if invocation_ref:
            downstream.append(invocation_ref)
        return {
            "schema_version": "skillkernel.observatory.profile-qualification-run.v1",
            "object_type": object_type,
            "object_id": run_id,
            "title": f"{profile_kind.title()} qualification run {run_id}",
            "summary": (
                "Content-safe profile qualification run with deterministic check "
                "outcomes and bounded scalar metrics."
            ),
            "workspace_key": getattr(run, "workspace_key", None),
            "profile": {
                "object_type": (
                    "model_profile"
                    if object_type.startswith("model")
                    else "embedding_profile"
                ),
                "object_id": summary["profile_key"],
            },
            "profile_key": summary["profile_key"],
            "route_kind": summary["route_kind"],
            "provider": summary["provider"],
            "model": summary["model"],
            "thinking_level": summary["thinking_level"],
            "embedding_dim": summary["embedding_dim"],
            "distance_metric": summary["distance_metric"],
            "probe_set_version": summary["probe_set_version"],
            "verdict": summary["verdict"],
            "checks": summary["checks"],
            "metrics": summary["metrics"],
            "created_at": summary["created_at"],
            "expires_at": summary["expires_at"],
            "provenance": {
                "upstream": [],
                "downstream": downstream,
            },
            "diagnostics": {
                "supporting_component": "model_embedding_profiles",
                "profile_kind": profile_kind,
                "raw_probe_results_returned": False,
                "raw_error_returned": False,
                "endpoint_ref_returned": False,
                "api_key_available": False,
                "cost_analytics_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
            "audit": {"links": []},
        }

    def _profile_microscope(
        *,
        profile: Any,
        qualification_runs: list[Any],
        object_type: str,
    ) -> dict[str, Any]:
        latest_qualification = dict(profile.qualification or {})
        summarized_runs = [
            _qualification_run_summary(run) for run in qualification_runs
        ]
        profile_id = str(profile.profile_id)
        profile_kind = "Text model" if object_type == "model_profile" else "Embedding"
        return {
            "schema_version": "skillkernel.observatory.profile.v1",
            "object_type": object_type,
            "object_id": profile.profile_key,
            "profile_id": profile_id,
            "title": f"{profile_kind} profile {profile.profile_key}",
            "summary": (
                "Content-safe model/embedding profile configuration, latest "
                "qualification state, and recent qualification checklist outcomes."
            ),
            "configuration": _profile_configuration_payload(profile),
            "qualification": {
                "status": profile.status,
                "latest_qualification_run_id": latest_qualification.get(
                    "latest_qualification_run_id"
                ),
                "latest_qualification_verdict": latest_qualification.get(
                    "latest_qualification_verdict"
                ),
                "latest_probe_set_version": latest_qualification.get(
                    "latest_probe_set_version"
                ),
                "qualification_expires_at": latest_qualification.get(
                    "qualification_expires_at"
                ),
            },
            "qualification_runs": summarized_runs,
            "provenance": {
                "upstream": [],
                "downstream": [
                    run["metrics"]["llm_invocation_ref"]
                    for run in summarized_runs
                    if isinstance(run.get("metrics"), dict)
                    and run["metrics"].get("llm_invocation_ref")
                ],
            },
            "diagnostics": {
                "supporting_component": "model_embedding_profiles",
                "profile_kind": profile.kind,
                "route_kind": profile.route_kind,
                "endpoint_kind": profile.endpoint_kind,
                "qualification_run_count": len(summarized_runs),
                "raw_probe_results_returned": False,
                "endpoint_ref_returned": False,
                "api_key_available": False,
                "cost_analytics_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
            "audit": {"links": []},
        }

    def _llm_invocation_safe_audit(audit: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        endpoint_route = audit.get("endpoint_route")
        if endpoint_route:
            safe["endpoint_route"] = str(endpoint_route)
        finish_reason = audit.get("finish_reason")
        if finish_reason:
            safe["finish_reason"] = str(finish_reason)
        provider_request_id = audit.get("provider_request_id")
        if provider_request_id:
            safe["provider_request_id_sha256"] = sha256_text(str(provider_request_id))
        safe["raw_audit_payload_returned"] = False
        return safe

    def _llm_invocation_microscope(record: Any) -> dict[str, Any]:
        invocation_id = str(record.llm_invocation_id)
        trace_refs = []
        if record.trace_id is not None:
            trace_refs.append({"object_type": "trace", "object_id": str(record.trace_id)})
        if record.span_id is not None:
            trace_refs.append(
                {"object_type": "trace_span", "object_id": str(record.span_id)}
            )
        return {
            "schema_version": "skillkernel.observatory.llm-invocation.v1",
            "object_type": "llm_invocation",
            "object_id": invocation_id,
            "title": f"LLM invocation {invocation_id}",
            "summary": (
                "Content-safe LLM invocation audit metadata for semantic proposal "
                "and profile-qualification calls."
            ),
            "workspace_key": record.workspace_key,
            "purpose": record.purpose,
            "profile": {
                "profile_key": record.profile_key,
                "model_profile_id": (
                    str(record.model_profile_id) if record.model_profile_id else None
                ),
                "route_kind": record.route_kind,
                "provider": record.provider,
                "model": record.model,
            },
            "thinking": {
                "requested_level": record.requested_thinking_level,
                "effective_level": record.effective_thinking_level,
                "fallback_policy": record.thinking_fallback_policy,
                "downgraded": record.thinking_downgraded,
            },
            "token_estimates": {
                "prompt": record.prompt_token_estimate,
                "output": record.output_token_estimate,
            },
            "status": {
                "state": record.status,
                "error_present": record.error is not None,
                "error_sha256": sha256_text(record.error) if record.error else None,
                "raw_error_returned": False,
            },
            "audit": _llm_invocation_safe_audit(record.audit),
            "provenance": {
                "upstream": [
                    {
                        "object_type": "model_profile",
                        "object_id": record.profile_key,
                    }
                ],
                "downstream": trace_refs,
            },
            "diagnostics": {
                "supporting_component": "model_embedding_profiles",
                "trace_id": str(record.trace_id) if record.trace_id else None,
                "span_id": str(record.span_id) if record.span_id else None,
                "created_at": record.created_at.isoformat(),
                "endpoint_url_returned": False,
                "api_key_available": False,
                "prompt_returned": False,
                "response_returned": False,
                "cost_analytics_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
        }

    def _evaluation_microscope(
        evaluation_id: str,
        evaluation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if evaluation is None:
            return {
                "schema_version": "skillkernel.observatory.evaluation.v1",
                "object_type": "evaluation",
                "object_id": evaluation_id,
                "title": f"Evaluation {evaluation_id}",
                "summary": "Evaluation/probe review state.",
                "diagnostics": _missing_read_model(
                    "evaluation",
                    supporting_component="evaluator_probes",
                ),
                "content_policy": {
                    "raw_available": False,
                    "raw_reason": "raw-content-disabled",
                },
            }
        result_summary = evaluation.get("result_summary")
        if not isinstance(result_summary, dict):
            result_summary = {}
        assurance = result_summary.get("autonomy_assurance")
        if not isinstance(assurance, dict):
            assurance = {}
        hard_failures = [str(item) for item in assurance.get("hard_invariant_failures") or []]
        soft_misses = [str(item) for item in assurance.get("soft_threshold_misses") or []]
        fallback_actions = [
            str(item) for item in assurance.get("autonomous_fallback_actions") or []
        ]
        evidence_refs: list[dict[str, Any]] = [
            {
                "object_type": "evaluation",
                "object_id": str(evaluation.get("evaluation_id") or evaluation_id),
                "relationship": "subject",
            }
        ]
        skill_version_id = evaluation.get("skill_version_id")
        if skill_version_id:
            evidence_refs.append(
                {
                    "object_type": "skill_version",
                    "object_id": str(skill_version_id),
                    "relationship": "evaluated_artifact",
                }
            )
        evidence_refs.extend(
            {
                "object_type": "autonomy_invariant",
                "object_id": code,
                "relationship": "hard_invariant_failure",
            }
            for code in hard_failures
        )
        evidence_refs.extend(
            {
                "object_type": "soft_threshold",
                "object_id": code,
                "relationship": "calibrated_threshold_miss",
            }
            for code in soft_misses
        )
        decision_state = "passed"
        if hard_failures:
            decision_state = "hard_invariant_blocked"
        elif soft_misses:
            decision_state = "soft_threshold_stalled"
        elif evaluation.get("status") not in {"passed", "succeeded"}:
            decision_state = "pending_or_unknown"
        diagnostics = {
            **evaluation,
            "read_model": {
                "source": "evaluation_store.list_evaluation_reviews",
                "data_quality": "content-safe-derived",
                "raw_probe_payload_available": False,
            },
            "autonomy_decision": {
                "state": decision_state,
                "decision_family": assurance.get("decision_family"),
                "policy_version": assurance.get("policy_version"),
                "evidence_mode": assurance.get("evidence_mode"),
                "calibration_support_status": assurance.get(
                    "calibration_support_status"
                ),
                "threshold_deadlock_candidate": bool(
                    assurance.get("threshold_deadlock_candidate")
                ),
                "administrative_escalation_allowed": bool(
                    assurance.get("administrative_escalation_allowed")
                ),
            },
            "hard_invariant_failures": hard_failures,
            "soft_threshold_misses": soft_misses,
            "operator_next_actions": fallback_actions
            or ["inspect_probe_results", "collect_more_evidence"],
            "policy_blocked_actions": (
                []
                if assurance.get("administrative_escalation_allowed")
                else [
                    "raw_content_reveal_without_policy_reason",
                    "manual_override_of_hard_invariants",
                ]
            ),
        }
        return {
            "schema_version": "skillkernel.observatory.evaluation.v1",
            "object_type": "evaluation",
            "object_id": evaluation_id,
            "title": f"Evaluation {evaluation_id}",
            "summary": "Evaluation/probe review state and autonomy assurance.",
            "diagnostics": diagnostics,
            "provenance": {"upstream": evidence_refs, "downstream": []},
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
            },
        }

    def _uuid_or_404(value: str, object_label: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"{object_label} not found",
            ) from exc

    def _is_threshold_deadlock_decision(record: Any) -> bool:
        return (
            record.dominant_reason_code == "threshold_deadlock"
            or record.soft_threshold_state == "threshold_deadlock_candidate"
        )

    def _threshold_deadlock_payload(record: Any) -> dict[str, Any]:
        decision = record.to_json()
        return {
            "schema_version": "skillkernel.observatory.threshold-deadlock.v1",
            "object_type": "threshold_deadlock",
            "object_id": str(record.decision_id),
            "decision_id": str(record.decision_id),
            "workspace_id": record.workspace_key,
            "decision_family": record.decision_family,
            "target": decision["target"],
            "action_risk_tier": record.action_risk_tier,
            "hard_invariant_state": record.hard_invariant_state,
            "soft_threshold_state": record.soft_threshold_state,
            "selected_action": record.selected_action,
            "confidence_band": record.confidence_band,
            "evidence_fidelity": record.evidence_fidelity,
            "autonomy_support_state": record.autonomy_support_state,
            "dominant_reason_code": record.dominant_reason_code,
            "autonomy_decision": decision,
            "diagnostics": {
                "read_model": "admin_autonomy_decision_status",
                "derived_from_object_type": "autonomy_decision",
                "derived_from_object_id": str(record.decision_id),
                "threshold_deadlock_candidate": True,
                "raw_content_available": False,
                "safe_next_action": "inspect_adjudication_and_collect_more_evidence",
            },
            "provenance": {
                "upstream": [
                    {
                        "object_type": "autonomy_decision",
                        "object_id": str(record.decision_id),
                        "relationship": "source_decision_status",
                    },
                    {
                        "object_type": record.target_kind,
                        "object_id": record.target_id,
                        "relationship": "decision_target",
                    },
                ],
                "downstream": [],
            },
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "content_policy": {
                "raw_available": False,
                "raw_reason": "threshold-deadlock-status-read-model",
                "redaction_state": "status_only",
            },
        }

    def _context_artifact_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        object_id = str(payload["context_artifact_id"])
        return {
            "schema_version": "skillkernel.observatory.context-artifact.v1",
            "object_type": "context_artifact",
            "object_id": object_id,
            "context_artifact_id": object_id,
            "workspace_id": payload.get("workspace_key") or payload.get("workspace_id"),
            "artifact_kind": payload["artifact_kind"],
            "source_object_type": payload["source_object_type"],
            "source_object_id": payload.get("source_object_id"),
            "skill_id": payload.get("skill_id"),
            "skill_version_id": payload.get("skill_version_id"),
            "broker_policy_version_id": payload.get("broker_policy_version_id"),
            "text_hash": payload["text_hash"],
            "token_count": payload["token_count"],
            "max_tokens": payload["max_tokens"],
            "safety_status": payload["safety_status"],
            "equivalence_status": payload["equivalence_status"],
            "budget_status": payload["budget_status"],
            "shadowing_status": payload["shadowing_status"],
            "metadata_keys": sorted(str(key) for key in metadata),
            "created_at": payload["created_at"],
            "title": f"Context artifact {object_id}",
            "summary": (
                f"{payload['artifact_kind']} {payload['budget_status']} "
                f"{payload['token_count']}/{payload['max_tokens']} tokens"
            ),
            "timeline": [
                {"at": payload["created_at"], "event": "context_artifact_recorded"}
            ],
            "provenance": {
                "upstream": [
                    {
                        "object_type": payload["source_object_type"],
                        "object_id": payload.get("source_object_id"),
                        "relationship": "source_object",
                    }
                ]
                if payload.get("source_object_id")
                else [],
                "downstream": [],
            },
            "effects": {
                "context_loadability": {
                    "safety_status": payload["safety_status"],
                    "equivalence_status": payload["equivalence_status"],
                    "budget_status": payload["budget_status"],
                    "shadowing_status": payload["shadowing_status"],
                },
                "raw_text_returned": False,
            },
            "diagnostics": {
                "supporting_component": "context_compiler",
                "metadata_keys": sorted(str(key) for key in metadata),
                "token_budget": {
                    "token_count": payload["token_count"],
                    "max_tokens": payload["max_tokens"],
                    "status": payload["budget_status"],
                },
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "hashes_and_gate_status_only",
                "compiled_text_returned": False,
            },
        }

    def _context_compile_run_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        object_id = str(payload["context_compile_run_id"])
        return {
            "schema_version": "skillkernel.observatory.context-compile-run.v1",
            "object_type": "context_compile_run",
            "object_id": object_id,
            "context_compile_run_id": object_id,
            "workspace_id": payload.get("workspace_key") or payload.get("workspace_id"),
            "skill_id": payload.get("skill_id"),
            "skill_version_id": payload.get("skill_version_id"),
            "candidate_id": payload.get("candidate_id"),
            "context_artifact_id": payload.get("context_artifact_id"),
            "compiler_version": payload["compiler_version"],
            "model_assist_used": payload["model_assist_used"],
            "input_skillir_hash": payload["input_skillir_hash"],
            "output_manifest_hash": payload["output_manifest_hash"],
            "target_runtime_tokens": payload.get("target_runtime_tokens"),
            "actual_runtime_tokens": payload["actual_runtime_tokens"],
            "compression_ratio": payload.get("compression_ratio"),
            "semantic_equivalence_score": payload.get("semantic_equivalence_score"),
            "status": payload["status"],
            "reject_reason": payload.get("reject_reason"),
            "metadata_keys": sorted(str(key) for key in metadata),
            "created_at": payload["created_at"],
            "title": f"Context compile run {object_id}",
            "summary": (
                f"{payload['status']} compile; "
                f"{payload['actual_runtime_tokens']} runtime tokens"
            ),
            "timeline": [{"at": payload["created_at"], "event": "context_compile_run"}],
            "provenance": {
                "upstream": [
                    {
                        "object_type": "context_artifact",
                        "object_id": payload["context_artifact_id"],
                        "relationship": "compiled_artifact",
                    }
                ]
                if payload.get("context_artifact_id")
                else [],
                "downstream": [],
            },
            "effects": {
                "activation_proof_candidate": payload["status"] == "passed",
                "raw_skillir_returned": False,
                "compiled_text_returned": False,
            },
            "diagnostics": {
                "supporting_component": "context_compiler",
                "metadata_keys": sorted(str(key) for key in metadata),
                "semantic_equivalence_score": payload.get("semantic_equivalence_score"),
                "compression_ratio": payload.get("compression_ratio"),
                "reject_reason": payload.get("reject_reason"),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "hashes_and_metrics_only",
                "skillir_returned": False,
                "compiled_text_returned": False,
            },
        }

    def _context_budget_event_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        object_id = str(payload["context_budget_event_id"])
        return {
            "schema_version": "skillkernel.observatory.context-budget-event.v1",
            "object_type": "context_budget_event",
            "object_id": object_id,
            "context_budget_event_id": object_id,
            "workspace_id": payload.get("workspace_key") or payload.get("workspace_id"),
            "skill_id": payload.get("skill_id"),
            "skill_version_id": payload.get("skill_version_id"),
            "context_artifact_id": payload.get("context_artifact_id"),
            "event_type": payload["event_type"],
            "decision": payload["decision"],
            "tokens_delta": payload.get("tokens_delta"),
            "marginal_success_delta": payload.get("marginal_success_delta"),
            "false_positive_load_delta": payload.get("false_positive_load_delta"),
            "ignored_load_delta": payload.get("ignored_load_delta"),
            "shadowing_delta": payload.get("shadowing_delta"),
            "evidence_keys": sorted(str(key) for key in evidence),
            "metadata_keys": sorted(str(key) for key in metadata),
            "created_at": payload["created_at"],
            "title": f"Context budget event {object_id}",
            "summary": f"{payload['event_type']} -> {payload['decision']}",
            "timeline": [{"at": payload["created_at"], "event": "context_budget_event"}],
            "provenance": {
                "upstream": [
                    {
                        "object_type": "context_artifact",
                        "object_id": payload["context_artifact_id"],
                        "relationship": "budgeted_artifact",
                    }
                ]
                if payload.get("context_artifact_id")
                else [],
                "downstream": [],
            },
            "effects": {
                "decision": payload["decision"],
                "raw_evidence_returned": False,
            },
            "diagnostics": {
                "supporting_component": "context_compiler",
                "evidence_keys": sorted(str(key) for key in evidence),
                "metadata_keys": sorted(str(key) for key in metadata),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "metrics_and_key_summaries_only",
                "evidence_payload_returned": False,
            },
        }

    def _semantic_compression_trial_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        object_id = str(payload["semantic_compression_trial_id"])
        return {
            "schema_version": "skillkernel.observatory.semantic-compression-trial.v1",
            "object_type": "semantic_compression_trial",
            "object_id": object_id,
            "semantic_compression_trial_id": object_id,
            "workspace_id": payload.get("workspace_key") or payload.get("workspace_id"),
            "skill_id": payload.get("skill_id"),
            "source_revision_id": payload.get("source_revision_id"),
            "candidate_revision_id": payload.get("candidate_revision_id"),
            "source_context_artifact_id": payload.get("source_context_artifact_id"),
            "candidate_context_artifact_id": payload.get("candidate_context_artifact_id"),
            "source_tokens": payload["source_tokens"],
            "candidate_tokens": payload["candidate_tokens"],
            "preserved_requirements": payload["preserved_requirements"],
            "lost_requirements": payload["lost_requirements"],
            "added_unsupported_requirements": payload["added_unsupported_requirements"],
            "equivalence_score": payload["equivalence_score"],
            "target_probe_pass_rate": payload.get("target_probe_pass_rate"),
            "regression_probe_pass_rate": payload.get("regression_probe_pass_rate"),
            "status": payload["status"],
            "metadata_keys": sorted(str(key) for key in metadata),
            "created_at": payload["created_at"],
            "title": f"Semantic compression trial {object_id}",
            "summary": (
                f"{payload['status']} compression trial; "
                f"{payload['source_tokens']} -> {payload['candidate_tokens']} tokens"
            ),
            "timeline": [
                {"at": payload["created_at"], "event": "semantic_compression_trial"}
            ],
            "provenance": {
                "upstream": [
                    ref
                    for ref in (
                        {
                            "object_type": "context_artifact",
                            "object_id": payload.get("source_context_artifact_id"),
                            "relationship": "source_artifact",
                        },
                        {
                            "object_type": "context_artifact",
                            "object_id": payload.get("candidate_context_artifact_id"),
                            "relationship": "candidate_artifact",
                        },
                    )
                    if ref["object_id"]
                ],
                "downstream": [],
            },
            "effects": {
                "token_delta": payload["candidate_tokens"] - payload["source_tokens"],
                "raw_artifact_text_returned": False,
            },
            "diagnostics": {
                "supporting_component": "context_compiler",
                "metadata_keys": sorted(str(key) for key in metadata),
                "equivalence_score": payload["equivalence_score"],
                "lost_requirements": payload["lost_requirements"],
                "added_unsupported_requirements": payload[
                    "added_unsupported_requirements"
                ],
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "metrics_and_refs_only",
                "artifact_text_returned": False,
            },
        }

    def _event_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        upstream = []
        if payload.get("trace_id"):
            upstream.append({"object_type": "trace", "object_id": payload["trace_id"]})
        if payload.get("parent_span_id"):
            upstream.append({"object_type": "span", "object_id": payload["parent_span_id"]})
        downstream = []
        if payload.get("span_id"):
            downstream.append({"object_type": "span", "object_id": payload["span_id"]})
        return {
            **payload,
            "timeline": [
                {
                    "at": payload["occurred_at"],
                    "event": payload["event_type"],
                    "source": payload["source"],
                }
            ],
            "provenance": {
                "upstream": upstream,
                "downstream": downstream,
            },
            "effects": {
                "payload_hash": payload["payload_hash"],
                "payload_keys": payload["payload_keys"],
                "redaction_state": payload["redaction_state"],
            },
            "diagnostics": {
                "trust": payload["trust"],
                "taint": payload["taint"],
                "session_id": payload["session_id"],
                "turn_id": payload["turn_id"],
                "plugin_version": payload["plugin_version"],
                "openclaw_version": payload["openclaw_version"],
            },
            "audit": {"links": [], "chain_visible": False},
        }

    def _opportunity_admin_record(record: dict[str, Any]) -> dict[str, Any]:
        candidate_slug = str(record["candidate_slug"])
        opportunity_id = str(record["key"])
        evidence_ids = [str(evidence_id) for evidence_id in record.get("evidence_ids", [])]
        match = record.get("match") if isinstance(record.get("match"), dict) else {}
        active_matches = (
            match.get("active_matches") if isinstance(match.get("active_matches"), list) else []
        )
        archived_matches = (
            match.get("archived_matches")
            if isinstance(match.get("archived_matches"), list)
            else []
        )
        external_matches = (
            match.get("external_matches")
            if isinstance(match.get("external_matches"), list)
            else []
        )
        retrieval_log_id = match.get("retrieval_log_id")
        upstream = [
            {"object_type": "evidence", "object_id": evidence_id}
            for evidence_id in evidence_ids
        ]
        if retrieval_log_id:
            upstream.append(
                {
                    "object_type": "broker_decision",
                    "object_id": str(retrieval_log_id),
                    "relationship": "duplicate_search",
                }
            )
        downstream: list[dict[str, str]] = []
        for candidate_match in active_matches + archived_matches:
            if isinstance(candidate_match, dict) and candidate_match.get("skill_id"):
                downstream.append(
                    {
                        "object_type": "skill",
                        "object_id": str(candidate_match["skill_id"]),
                        "relationship": str(candidate_match.get("lifecycle_state", "match")),
                    }
                )
        for external_match in external_matches:
            if isinstance(external_match, dict) and external_match.get(
                "external_skill_id"
            ):
                downstream.append(
                    {
                        "object_type": "external_skill",
                        "object_id": str(external_match["external_skill_id"]),
                        "relationship": "collision_review",
                    }
                )
        description = str(record.get("candidate_description") or "")
        return {
            "schema_version": "skillkernel.observatory.opportunity.v1",
            "object_type": "opportunity",
            "object_id": opportunity_id,
            "opportunity_key": opportunity_id,
            "candidate_slug": candidate_slug,
            "title": candidate_slug,
            "summary": (
                f"{record['recommendation']} opportunity with "
                f"{record['support_count']} supporting evidence records"
            ),
            "support_count": int(record.get("support_count") or 0),
            "recommendation": record["recommendation"],
            "deduplication": {
                "decision": match.get("decision"),
                "retrieval_log_id": str(retrieval_log_id) if retrieval_log_id else None,
                "active_match_count": len(active_matches),
                "archived_match_count": len(archived_matches),
                "external_match_count": len(external_matches),
                "retrieval_decision_recorded": retrieval_log_id is not None,
            },
            "evidence_refs": upstream[:100],
            "description_sha256": "sha256:" + sha256_text(description),
            "description_returned": False,
            "details_url": f"/admin/opportunities/{opportunity_id}",
            "timeline": [],
            "provenance": {"upstream": upstream[:100], "downstream": downstream[:100]},
            "effects": {
                "candidate_created": False,
                "activation_allowed": False,
                "retrieval_log_created": retrieval_log_id is not None,
                "runtime_content_returned": False,
                "candidate_description_returned": False,
            },
            "diagnostics": {
                "supporting_component": "opportunity_mining",
                "evidence_count": len(evidence_ids),
                "match_decision": match.get("decision"),
                "retrieval_decision_recorded": retrieval_log_id is not None,
                "raw_evidence_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "metadata_refs_and_hashes",
                "candidate_description_returned": False,
                "match_summaries_returned": False,
            },
            "audit": {"links": [], "chain_visible": False},
        }

    def _memory_quarantine_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        proposed_memory = payload.get("proposed_memory")
        proposed_memory_keys = (
            sorted(str(key) for key in proposed_memory)
            if isinstance(proposed_memory, dict)
            else []
        )
        scanner_findings = payload.get("scanner_findings")
        scanner_finding_keys = (
            sorted(str(key) for key in scanner_findings)
            if isinstance(scanner_findings, dict)
            else []
        )
        source_ref = {
            "object_type": str(payload["source_object_type"]),
            "object_id": str(payload["source_object_id"]),
        }
        quarantine_id = str(payload["quarantine_id"])
        return {
            "schema_version": "skillkernel.observatory.memory-quarantine.v1",
            "object_type": "memory_quarantine",
            "object_id": quarantine_id,
            "quarantine_id": quarantine_id,
            "workspace_id": payload.get("workspace_id"),
            "workspace_key": payload.get("workspace_key"),
            "title": f"Memory quarantine {quarantine_id}",
            "summary": (
                f"{payload['status']} memory candidate from "
                f"{payload['source_object_type']}"
            ),
            "status": payload["status"],
            "source_object_type": payload["source_object_type"],
            "source_object_id": payload["source_object_id"],
            "proposed_memory_hash": (
                "sha256:"
                + sha256_text(json.dumps(proposed_memory, sort_keys=True, default=str))
            ),
            "proposed_memory_keys": proposed_memory_keys,
            "taint": payload.get("taint") or {},
            "scanner_finding_keys": scanner_finding_keys,
            "created_at": payload["created_at"],
            "decided_at": payload.get("decided_at"),
            "details_url": f"/admin/memory/quarantine/{quarantine_id}",
            "timeline": [
                {"at": payload["created_at"], "event": "memory_quarantined"},
                *(
                    [{"at": payload["decided_at"], "event": f"memory_{payload['status']}"}]
                    if payload.get("decided_at")
                    else []
                ),
            ],
            "provenance": {"upstream": [source_ref], "downstream": []},
            "effects": {
                "runtime_loaded": False,
                "embedded": False,
                "mutation_input": payload["status"] == "approved",
                "memory_content_returned": False,
            },
            "diagnostics": {
                "supporting_component": "evidence_memory",
                "scanner_finding_keys": scanner_finding_keys,
                "taint_keys": sorted(str(key) for key in (payload.get("taint") or {})),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
                "memory_content_returned": False,
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _control_flow_event_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        event_id = str(payload["control_flow_event_id"])
        upstream = []
        if payload.get("source_id"):
            upstream.append(
                {
                    "object_type": payload["source_kind"],
                    "object_id": payload["source_id"],
                }
            )
        decision = payload.get("decision") or {}
        return {
            "schema_version": "skillkernel.observatory.control-flow-event.v1",
            "object_type": "control_flow_event",
            "object_id": event_id,
            "control_flow_event_id": event_id,
            "workspace_id": payload.get("workspace_id"),
            "workspace_key": payload.get("workspace_key"),
            "title": f"Control-flow event {event_id}",
            "summary": (
                f"{payload['source_kind']} influenced {payload['influence_kind']}"
            ),
            "run_id": payload.get("run_id"),
            "source_kind": payload["source_kind"],
            "source_id": payload.get("source_id"),
            "influence_kind": payload["influence_kind"],
            "decision": decision,
            "decision_keys": sorted(str(key) for key in decision),
            "created_at": payload["created_at"],
            "details_url": f"/admin/control-flow/events/{event_id}",
            "timeline": [
                {"at": payload["created_at"], "event": "control_flow_recorded"}
            ],
            "provenance": {"upstream": upstream, "downstream": []},
            "effects": {
                "decision_recorded": True,
                "policy_mutated": False,
                "runtime_content_returned": False,
            },
            "diagnostics": {
                "supporting_component": "evidence_memory",
                "decision_keys": sorted(str(key) for key in decision),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_decision_metadata",
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _safe_canary_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        safe_values: dict[str, Any] = {}
        for key, value in metrics.items():
            key_text = str(key)
            if (
                isinstance(value, bool)
                or (
                    isinstance(value, int | float)
                    and not isinstance(value, bool)
                )
            ):
                safe_values[key_text] = value
            elif value is None:
                safe_values[key_text] = None
        return {
            "metric_keys": sorted(str(key) for key in metrics),
            "numeric_or_boolean_values": safe_values,
            "metrics_sha256": (
                "sha256:"
                + sha256_text(json.dumps(metrics, sort_keys=True, default=str))
            ),
            "raw_metrics_returned": False,
        }

    def _canary_result_admin_record(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        canary_result_id = str(payload["canary_result_id"])
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        upstream = [{"object_type": "skill", "object_id": str(payload["skill_id"])}]
        if payload.get("skill_version_id"):
            upstream.append(
                {
                    "object_type": "skill_version",
                    "object_id": str(payload["skill_version_id"]),
                }
            )
        if payload.get("evolution_transaction_id"):
            upstream.append(
                {
                    "object_type": "evolution_transaction",
                    "object_id": str(payload["evolution_transaction_id"]),
                }
            )
        reason = payload.get("reason")
        return {
            "schema_version": "skillkernel.observatory.canary-result.v1",
            "object_type": "canary_result",
            "object_id": canary_result_id,
            "canary_result_id": canary_result_id,
            "workspace_id": payload.get("workspace_id"),
            "workspace_key": payload.get("workspace_key"),
            "title": f"Canary result {canary_result_id}",
            "summary": (
                f"{payload['status']} canary for skill {payload['skill_id']}; "
                f"critical={payload['critical']}"
            ),
            "status": payload["status"],
            "critical": payload["critical"],
            "skill_id": payload["skill_id"],
            "skill_version_id": payload.get("skill_version_id"),
            "evolution_transaction_id": payload.get("evolution_transaction_id"),
            "reason_present": reason is not None,
            "reason_sha256": ("sha256:" + sha256_text(str(reason))) if reason else None,
            "metrics": _safe_canary_metrics(metrics),
            "observed_at": payload["observed_at"],
            "details_url": f"/admin/canary/results/{canary_result_id}",
            "timeline": [
                {
                    "at": payload["observed_at"],
                    "event": "canary_observed",
                    "status": payload["status"],
                    "critical": payload["critical"],
                }
            ],
            "provenance": {"upstream": upstream, "downstream": []},
            "effects": {
                "skill_lifecycle_checked": True,
                "freezes_skill": bool(payload["critical"]),
                "can_queue_rollback_revocation": bool(payload["critical"]),
                "raw_metrics_returned": False,
                "raw_reason_returned": False,
            },
            "diagnostics": {
                "supporting_component": "canary_rollback_freeze",
                "metric_keys": sorted(str(key) for key in metrics),
                "reason_present": reason is not None,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "metadata_and_hashes",
                "raw_metrics_returned": False,
                "raw_reason_returned": False,
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _comparison_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        return {
            **payload,
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "comparison_saved",
                    "comparison_kind": payload["comparison_kind"],
                }
            ],
            "provenance": {
                "upstream": [payload["left"], payload["right"]],
                "downstream": [],
            },
            "effects": {
                "differences": payload["differences"],
                "mutates_policy": False,
            },
            "diagnostics": {
                "actor_id": payload["actor_id"],
                "result_summary": payload["result_summary"],
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _diagnostic_bundle_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        return {
            **payload,
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "diagnostic_bundle_created",
                    "redaction_level": payload["redaction_level"],
                }
            ],
            "provenance": {
                "upstream": [payload["scope"]],
                "downstream": [
                    {
                        "object_type": "storage_uri",
                        "object_id": payload["storage_uri"],
                    }
                ],
            },
            "effects": {
                "manifest": payload["manifest"],
                "storage_uri": payload["storage_uri"],
            },
            "diagnostics": {
                "actor_id": payload["actor_id"],
                "expires_at": payload["expires_at"],
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _admin_action_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        request_payload = payload["request_payload_redacted"]
        upstream = []
        if payload.get("linked_audit_id"):
            upstream.append(
                {
                    "object_type": "audit_record",
                    "object_id": payload["linked_audit_id"],
                }
            )
        if payload.get("linked_job_id"):
            upstream.append({"object_type": "job", "object_id": payload["linked_job_id"]})
        action_attribution_check = request_payload.get("action_attribution_check")
        if isinstance(action_attribution_check, dict) and action_attribution_check.get(
            "action_attribution_check_id"
        ):
            upstream.append(
                {
                    "object_type": "action_attribution_check",
                    "object_id": action_attribution_check["action_attribution_check_id"],
                }
            )
        return {
            **payload,
            "title": f"Operator action {payload['action_kind']}",
            "summary": (
                "Content-safe Observatory operator action receipt with policy "
                "result and linked audit/job references."
            ),
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "operator_action_recorded",
                    "action_kind": payload["action_kind"],
                    "result": payload["result"],
                }
            ],
            "provenance": {
                "upstream": upstream,
                "downstream": [
                    {
                        "object_type": payload["target_type"],
                        "object_id": payload["target_id"],
                    }
                ],
            },
            "effects": {
                "result": payload["result"],
                "target_type": payload["target_type"],
                "target_id": payload["target_id"],
                "dry_run": request_payload.get("dry_run"),
                "confirmation_present": request_payload.get("confirmation_present"),
            },
            "diagnostics": {
                "actor_id": payload["actor_id"],
                "actor_roles": payload["actor_roles"],
                "request_id": request_payload.get("request_id"),
                "source": request_payload.get("source", {}),
                "metadata_keys": request_payload.get("metadata_keys", []),
                "has_confirmation_hash": bool(request_payload.get("confirmation_hash")),
                "action_attribution_check": action_attribution_check,
                "raw_content_included": False,
            },
            "audit": {
                "links": upstream,
                "chain_visible": payload.get("linked_audit_id") is not None,
            },
        }

    def _historical_import_source_admin_record(
        record: Any,
        *,
        requested_id: str | None = None,
    ) -> dict[str, Any]:
        payload = record.to_json() if hasattr(record, "to_json") else dict(record)
        source_id = str(payload["historical_import_source_id"])
        object_id = requested_id or source_id
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        taint = payload.get("taint") if isinstance(payload.get("taint"), dict) else {}
        source_key = str(payload.get("source_key") or "")
        fingerprint = str(payload.get("fingerprint") or "")
        return {
            "schema_version": "skillkernel.observatory.historical-import-source.v1",
            "object_type": "historical_import_source",
            "object_id": object_id,
            "historical_import_source_id": source_id,
            "workspace_id": payload.get("workspace_id"),
            "workspace_key": payload.get("workspace_key"),
            "title": f"Historical import source {source_id}",
            "summary": (
                f"{payload['status']} {payload['source_kind']} source; "
                f"trust={payload['trust_level']}"
            ),
            "source_kind": payload["source_kind"],
            "source_key_sha256": "sha256:" + sha256_text(source_key),
            "fingerprint": fingerprint,
            "fingerprint_sha256": "sha256:" + sha256_text(fingerprint),
            "parser_version": payload["parser_version"],
            "redaction_policy_version": payload["redaction_policy_version"],
            "trust_level": payload["trust_level"],
            "taint_keys": sorted(str(key) for key in taint),
            "metadata_keys": sorted(str(key) for key in metadata),
            "status": payload["status"],
            "last_seen_at": payload["last_seen_at"],
            "imported_at": payload.get("imported_at"),
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
            "details_url": f"/admin/historical/imports/{source_id}",
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "historical_import_source_observed",
                    "status": payload["status"],
                },
                {
                    "at": payload["updated_at"],
                    "event": "historical_import_source_updated",
                    "status": payload["status"],
                },
            ],
            "provenance": {"upstream": [], "downstream": []},
            "effects": {
                "revocation_root_type": "historical_import_source",
                "revocation_root_id": source_id,
                "source_revocation_supported": True,
                "derived_data_traversal_required": True,
                "raw_content_returned": False,
            },
            "diagnostics": {
                "supporting_component": "historical_ingestion",
                "source_key_returned": False,
                "metadata_values_returned": False,
                "taint_values_returned": False,
                "raw_content_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_historical_source_metadata",
            },
        }

    def _action_attribution_check_safe_metrics(
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        safe = {
            key: metrics.get(key)
            for key in (
                "schema_version",
                "request_id",
                "workspace_id",
                "action",
                "target_type",
                "target_id",
                "dry_run",
                "accepted",
                "reason_codes",
                "confirmation_required",
                "confirmation_hash_present",
                "idempotency_key_hash",
                "raw_content_included",
                "revoked",
                "revoked_at",
                "revocation_reason",
            )
            if key in metrics
        }
        source = metrics.get("source")
        if isinstance(source, dict):
            safe["source"] = {
                "ip_present": bool(source.get("ip")),
                "proxy_present": bool(source.get("proxy")),
            }
        return safe

    def _action_attribution_check_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        safe_metrics = _action_attribution_check_safe_metrics(metrics)
        upstream = [
            {
                "object_type": "skill",
                "object_id": skill_id,
                "relationship": "contributing_skill",
            }
            for skill_id in payload["contributing_skill_ids"]
        ]
        upstream.extend(
            {
                "object_type": "memory",
                "object_id": memory_id,
                "relationship": "contributing_memory",
            }
            for memory_id in payload["contributing_memory_ids"]
        )
        upstream.extend(
            {
                "object_type": "evidence",
                "object_id": evidence_id,
                "relationship": "contributing_evidence",
            }
            for evidence_id in payload["contributing_evidence_ids"]
        )
        if payload.get("broker_policy_version_id"):
            upstream.append(
                {
                    "object_type": "broker_policy_version",
                    "object_id": payload["broker_policy_version_id"],
                    "relationship": "policy_version",
                }
            )
        target_type = safe_metrics.get("target_type")
        target_id = safe_metrics.get("target_id")
        downstream = []
        if isinstance(target_type, str) and isinstance(target_id, str):
            downstream.append({"object_type": target_type, "object_id": target_id})
        return {
            "object_type": "action_attribution_check",
            "object_id": payload["action_attribution_check_id"],
            "workspace_id": payload["workspace_id"],
            "workspace_key": payload["workspace_key"],
            "title": f"Action attribution check {payload['action_kind']}",
            "summary": (
                "Content-safe deterministic boundary check for an Observatory "
                "operator action."
            ),
            "action_kind": payload["action_kind"],
            "risk_tier": payload["risk_tier"],
            "verdict": payload["verdict"],
            "counterfactual_kind": payload["counterfactual_kind"],
            "user_intent_hash": payload["user_intent_hash"],
            "session_id": payload["session_id"],
            "turn_id": payload["turn_id"],
            "tool_call_id": payload["tool_call_id"],
            "broker_policy_version_id": payload["broker_policy_version_id"],
            "created_at": payload["created_at"],
            "metrics": safe_metrics,
            "content_policy": {
                "raw_available": False,
                "redaction_level": "content_safe_boundary_check",
            },
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "action_attribution_checked",
                    "action_kind": payload["action_kind"],
                    "risk_tier": payload["risk_tier"],
                    "verdict": payload["verdict"],
                }
            ],
            "provenance": {"upstream": upstream, "downstream": downstream},
            "effects": {
                "target_type": target_type,
                "target_id": target_id,
                "accepted": safe_metrics.get("accepted"),
                "dry_run": safe_metrics.get("dry_run"),
                "raw_content_included": False,
            },
            "diagnostics": {
                "request_id": safe_metrics.get("request_id"),
                "reason_codes": safe_metrics.get("reason_codes", []),
                "confirmation_required": safe_metrics.get("confirmation_required"),
                "confirmation_hash_present": safe_metrics.get(
                    "confirmation_hash_present"
                ),
                "source": safe_metrics.get("source", {}),
                "metrics_keys": sorted(safe_metrics),
            },
            "audit": {
                "links": [
                    {
                        "object_type": "action_attribution_check",
                        "object_id": payload["action_attribution_check_id"],
                    }
                ],
                "chain_visible": False,
            },
        }

    def _admin_action_gateway_summary(
        records: list[Any],
        *,
        workspace_id: str | None,
        limit: int,
    ) -> dict[str, Any]:
        result_counts: dict[str, int] = {}
        action_counts: dict[str, dict[str, int]] = {}
        reason_counts: dict[str, int] = {}
        raw_reveal_counts: dict[str, int] = {}
        high_impact_history: list[dict[str, Any]] = []
        linked_jobs = 0
        linked_audits = 0
        confirmation_failures = 0
        role_failures = 0
        idempotency_collision_records = 0
        action_attribution_checks = 0
        blocked_attribution_checks = 0

        for record in records:
            payload = record.to_json()
            request_payload = payload["request_payload_redacted"]
            action_kind = str(payload["action_kind"])
            result = str(payload["result"])
            result_counts[result] = result_counts.get(result, 0) + 1
            action_bucket = action_counts.setdefault(action_kind, {})
            action_bucket[result] = action_bucket.get(result, 0) + 1
            if payload.get("linked_job_id"):
                linked_jobs += 1
            if payload.get("linked_audit_id"):
                linked_audits += 1
            if action_kind == "reveal_raw_content":
                raw_reveal_counts[result] = raw_reveal_counts.get(result, 0) + 1

            reason_codes = [
                str(reason)
                for reason in request_payload.get("reason_codes", [])
                if reason is not None
            ]
            for reason in reason_codes:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if "confirmation-required" in reason_codes:
                confirmation_failures += 1
            if "admin-role-required" in reason_codes:
                role_failures += 1
            if bool(request_payload.get("idempotency_collision")):
                idempotency_collision_records += 1
            action_attribution_check = request_payload.get("action_attribution_check")
            if isinstance(action_attribution_check, dict) and action_attribution_check.get(
                "action_attribution_check_id"
            ):
                action_attribution_checks += 1
                if action_attribution_check.get("verdict") == "blocked":
                    blocked_attribution_checks += 1
            if action_kind in OBSERVATORY_HIGH_IMPACT_ACTIONS:
                high_impact_history.append(
                    {
                        "action_id": payload["action_id"],
                        "action_kind": action_kind,
                        "target_type": payload["target_type"],
                        "target_id": payload["target_id"],
                        "result": result,
                        "created_at": payload["created_at"],
                        "reason_codes": reason_codes,
                        "confirmation_present": bool(
                            request_payload.get("confirmation_present")
                        ),
                        "confirmation_hash_present": bool(
                            request_payload.get("confirmation_hash")
                        ),
                    }
                )

        return {
            "schema_version": "skillkernel.observatory.admin-action-summary.v1",
            "object_type": "admin_action_gateway_summary",
            "object_id": workspace_id or "all-workspaces",
            "title": "Administrative action gateway summary",
            "summary": (
                "Content-safe aggregate view over persisted Observatory action "
                "audit receipts."
            ),
            "workspace_id": workspace_id,
            "sample": {
                "requested_limit": limit,
                "record_count": len(records),
                "bounded": True,
                "source": "observatory_admin_store.list_action_audits",
            },
            "counts": {
                "by_result": result_counts,
                "by_action_kind": action_counts,
                "linked_jobs": linked_jobs,
                "linked_audit_records": linked_audits,
                "action_attribution_checks": action_attribution_checks,
                "blocked_action_attribution_checks": blocked_attribution_checks,
                "high_impact_actions": len(high_impact_history),
                "raw_content_reveal": raw_reveal_counts,
            },
            "policy": {
                "blocked_by_reason": {
                    reason: count
                    for reason, count in sorted(reason_counts.items())
                    if reason != "idempotency-replay"
                },
                "confirmation_failures": confirmation_failures,
                "role_failures": role_failures,
                "idempotency_collision_records": idempotency_collision_records,
                "idempotency_replays_return_existing_receipts": True,
            },
            "high_impact_history": high_impact_history[:50],
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "aggregated_action_receipts",
            },
            "data_quality": {
                "derived_from_recent_bounded_receipts": True,
                "full_table_scan": False,
                "auth_failures_before_action_parsing_not_counted": True,
                "raw_confirmation_text_returned": False,
            },
            "diagnostics": {
                "supporting_component": "operator_action_gateway",
                "recent_action_ids": [str(record.action_id) for record in records[:10]],
                "reason_code_count": len(reason_counts),
            },
        }

    def _broker_replay_episode_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        source_log_id = payload.get("source_retrieval_log_id")
        expected_skill_ids = [
            str(item) for item in payload.get("expected_skill_ids", []) if item
        ]
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        return {
            **payload,
            "schema_version": "skillkernel.observatory.broker-replay-episode.v1",
            "object_type": "broker_replay_episode",
            "object_id": payload["broker_replay_episode_id"],
            "title": f"Broker replay episode {payload['episode_key']}",
            "summary": (
                f"{payload.get('expected_decision') or 'decision-unspecified'}; "
                f"expected_skills={len(expected_skill_ids)}; "
                f"tags={len(payload.get('tags', []))}"
            ),
            "timeline": [
                {
                    "at": payload["created_at"],
                    "event": "broker_replay_episode_recorded",
                    "episode_key": payload["episode_key"],
                }
            ],
            "provenance": {
                "upstream": [
                    {"object_type": "broker_decision", "object_id": str(source_log_id)}
                ]
                if source_log_id
                else [],
                "downstream": [
                    {"object_type": "skill", "object_id": skill_id}
                    for skill_id in expected_skill_ids
                ],
            },
            "effects": {
                "replay_tags": payload.get("tags", []),
                "expected_decision": payload.get("expected_decision"),
                "expected_skill_ids": expected_skill_ids,
            },
            "diagnostics": {
                "workspace_id": payload.get("workspace_key"),
                "episode_key": payload["episode_key"],
                "redacted_user_intent": payload.get("redacted_user_intent"),
                "redacted_intent_hash": sha256_text(
                    str(payload.get("redacted_user_intent") or "")
                ),
                "source_retrieval_log_id": source_log_id,
                "metadata_keys": sorted(str(key) for key in metadata),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "raw_prompt_stored": False,
                "redaction_state": "operator_redacted_replay_intent",
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _safe_broker_ref(item: Any) -> dict[str, object] | None:
        if not isinstance(item, dict):
            return None
        ref: dict[str, object] = {}
        for key in (
            "object_type",
            "object_id",
            "skill_id",
            "rank",
            "score",
            "reason",
            "scanner_codes",
        ):
            value = item.get(key)
            if value is None:
                continue
            if isinstance(value, str | int | float | bool):
                ref[key] = value
            elif isinstance(value, list):
                ref[key] = [
                    str(entry)
                    for entry in value
                    if isinstance(entry, str | int | float | bool)
                ][:10]
        return ref or None

    def _broker_decision_microscope(log: Any) -> dict[str, Any]:
        payload = log.to_json()
        metadata = log.metadata if isinstance(log.metadata, dict) else {}
        candidate_objects = [
            ref
            for item in metadata.get("candidate_objects", [])
            if (ref := _safe_broker_ref(item)) is not None
        ]
        suppressed = [
            ref
            for item in metadata.get("suppressed", [])
            if (ref := _safe_broker_ref(item)) is not None
        ]
        return {
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
                "reason_codes": [
                    str(code)
                    for code in metadata.get("reason_codes", [])
                    if isinstance(code, str | int | float | bool)
                ][:25],
                "query_hash": metadata.get("query_hash")
                if isinstance(metadata.get("query_hash"), str)
                else None,
                "candidate_count": metadata.get("candidate_count")
                if isinstance(metadata.get("candidate_count"), int)
                else len(candidate_objects),
                "rendered_skill_count": len(log.rendered_skill_ids),
                "broker_policy_version_id": payload["broker_policy_version_id"],
                "trace_id": payload["trace_id"],
                "span_id": payload["span_id"],
                "metadata_keys": sorted(str(key) for key in metadata),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
                "raw_query_stored": False,
                "metadata_values_returned": False,
            },
            "audit": {"links": [], "chain_visible": True},
        }

    def _topology_operation_microscope(detail: Any) -> dict[str, Any]:
        payload = detail.to_json()
        operation = payload["operation"]
        trials = payload["trials"]
        operation_id = str(operation["skill_graph_operation_id"])
        evidence_refs = [
            {"object_type": "evidence", "object_id": str(evidence_id)}
            for evidence_id in operation.get("evidence_ids", [])
        ]
        transaction_id = operation.get("evolution_transaction_id")
        transaction_refs = (
            [{"object_type": "evolution_transaction", "object_id": transaction_id}]
            if transaction_id
            else []
        )
        subject_refs = [
            {"object_type": "skill", "object_id": str(skill_id)}
            for skill_id in operation.get("subject_skill_ids", [])
        ]
        output_refs = [
            {"object_type": "skill", "object_id": str(skill_id)}
            for skill_id in operation.get("output_skill_ids", [])
        ]
        trial_refs = [
            {
                "object_type": "planned_topology_trial",
                "object_id": trial["planned_topology_trial_id"],
            }
            for trial in trials
        ]
        trial_statuses = _count_by(trials, "status")
        trial_kinds = _count_by(trials, "trial_kind")
        return {
            **operation,
            "schema_version": "skillkernel.observatory.topology-operation.v1",
            "object_type": "topology_operation",
            "object_id": operation_id,
            "title": (
                f"{operation['operation_kind']} topology operation "
                f"{operation_id}"
            ),
            "summary": (
                f"{operation['operation_kind']} / {operation['status']}; "
                f"trials={len(trials)}; evidence={len(evidence_refs)}"
            ),
            "details_url": f"/admin/topology/operations/{operation_id}",
            "timeline": [
                {
                    "at": operation["created_at"],
                    "event": "topology_operation_recorded",
                    "operation_kind": operation["operation_kind"],
                    "status": operation["status"],
                },
                {
                    "at": operation["updated_at"],
                    "event": "topology_operation_updated",
                    "status": operation["status"],
                },
            ],
            "provenance": {
                "upstream": [*evidence_refs, *transaction_refs, *subject_refs],
                "downstream": [*output_refs, *trial_refs],
            },
            "effects": {
                "subject_skill_ids": operation.get("subject_skill_ids", []),
                "output_skill_ids": operation.get("output_skill_ids", []),
                "effect_coverage": operation.get("effect_coverage", {}),
                "trial_summary": operation.get("trial_summary", {}),
            },
            "trials": trials,
            "diagnostics": {
                "supporting_component": "topology_operations",
                "operation_kind": operation["operation_kind"],
                "status": operation["status"],
                "trial_count": len(trials),
                "trial_statuses": trial_statuses,
                "trial_kinds": trial_kinds,
                "skill_graph_ir_keys": sorted(
                    str(key) for key in operation.get("skill_graph_ir", {})
                ),
                "effect_coverage_keys": sorted(
                    str(key) for key in operation.get("effect_coverage", {})
                ),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_topology_metadata",
            },
            "audit": {"links": transaction_refs, "chain_visible": True},
        }

    def _topology_transaction_review(transactions: list[Any]) -> dict[str, Any]:
        reviews: list[dict[str, Any]] = []
        for transaction in transactions:
            payload = transaction.to_json()
            metrics = payload.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            writes = metrics.get("writes", [])
            if not isinstance(writes, list):
                writes = []
            trial_kinds = metrics.get("trial_kinds", [])
            if not isinstance(trial_kinds, list):
                trial_kinds = []
            reviews.append(
                {
                    "evolution_transaction_id": payload["evolution_transaction_id"],
                    "workspace_key": payload.get("workspace_key"),
                    "transaction_kind": payload["transaction_kind"],
                    "status": payload["status"],
                    "plan_hash": payload["plan_hash"],
                    "topology_operation_kind": metrics.get("topology_operation_kind"),
                    "topology_status": metrics.get("topology_status"),
                    "evidence_count": metrics.get("evidence_count", 0),
                    "planned_trials": metrics.get("planned_trials", 0),
                    "trial_kinds": [str(kind) for kind in trial_kinds[:20]],
                    "blockers": metrics.get("blockers", 0),
                    "graph_node_count": metrics.get("graph_node_count", 0),
                    "graph_edge_count": metrics.get("graph_edge_count", 0),
                    "graph_node_roles": metrics.get("graph_node_roles", {}),
                    "graph_edge_kinds": metrics.get("graph_edge_kinds", {}),
                    "effect_coverage_count": metrics.get("effect_coverage_count", 0),
                    "rollback_blockers": metrics.get("rollback_blockers", 0),
                    "rollback_actions": metrics.get("rollback_actions", 0),
                    "rollback_actions_planned": bool(
                        metrics.get("rollback_actions_planned", False)
                    ),
                    "write_targets": [str(target) for target in writes[:20]],
                    "write_target_count": len(writes),
                    "requires_trial_before_apply": bool(
                        metrics.get("requires_trial_before_apply", False)
                    ),
                    "data_to_skill_trace": _safe_data_to_skill_trace(
                        metrics.get("data_to_skill_trace")
                    ),
                    "started_at": payload["started_at"],
                    "committed_at": payload.get("committed_at"),
                    "rolled_back_at": payload.get("rolled_back_at"),
                }
            )
        return {
            "source": "governance.evolution_transactions.metrics",
            "data_quality": "content-safe-transaction-metrics-only",
            "recent": reviews,
            "counts_by_transaction_kind": _count_by(reviews, "transaction_kind"),
            "counts_by_status": _count_by(reviews, "status"),
            "count": len(reviews),
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "topology_transaction_metrics_only",
            },
        }

    def _safe_data_to_skill_trace(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        stages = value.get("stages", [])
        if not isinstance(stages, list):
            stages = []
        return {
            "schema_version": str(
                value.get("schema_version")
                or "skillkernel.data-to-skill-trace.unknown"
            ),
            "operation_kind": value.get("operation_kind"),
            "status": value.get("status"),
            "plan_hash": value.get("plan_hash"),
            "terminal_stage": value.get("terminal_stage"),
            "failure_exit": value.get("failure_exit"),
            "stage_count": value.get("stage_count", len(stages)),
            "stages": [_safe_data_to_skill_stage(stage) for stage in stages[:20]],
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_trace_refs_only",
            },
        }

    def _safe_data_to_skill_stage(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            value = {}
        reason_codes = value.get("reason_codes", [])
        if not isinstance(reason_codes, list):
            reason_codes = []
        return {
            "name": value.get("name"),
            "status": value.get("status"),
            "reason_codes": [str(code) for code in reason_codes[:20]],
            "input_refs": _safe_object_refs(value.get("input_refs")),
            "output_refs": _safe_object_refs(value.get("output_refs")),
        }

    def _safe_object_refs(value: Any) -> list[dict[str, str | None]]:
        if not isinstance(value, list):
            return []
        refs: list[dict[str, str | None]] = []
        for item in value[:20]:
            if not isinstance(item, dict):
                continue
            refs.append(
                {
                    "object_type": str(item.get("object_type") or "unknown"),
                    "object_id": str(item.get("object_id")) if item.get("object_id") else None,
                }
            )
        return refs

    def _safe_transaction_metrics(metrics: Any) -> dict[str, Any]:
        if not isinstance(metrics, dict):
            metrics = {}
        writes = metrics.get("writes", [])
        if not isinstance(writes, list):
            writes = []
        trial_kinds = metrics.get("trial_kinds", [])
        if not isinstance(trial_kinds, list):
            trial_kinds = []
        safe: dict[str, Any] = {
            "metric_key_count": len(metrics),
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "allowlisted_transaction_metrics_only",
            },
        }
        allowlist = (
            "topology_operation_kind",
            "topology_status",
            "plan_hash",
            "evidence_count",
            "planned_trials",
            "blockers",
            "graph_node_count",
            "graph_edge_count",
            "graph_node_roles",
            "graph_edge_kinds",
            "effect_coverage_count",
            "rollback_blockers",
            "rollback_actions",
            "rollback_actions_planned",
            "requires_trial_before_apply",
        )
        for key in allowlist:
            if key in metrics:
                safe[key] = metrics[key]
        safe["trial_kinds"] = [str(kind) for kind in trial_kinds[:20]]
        safe["write_targets"] = [str(target) for target in writes[:20]]
        safe["write_target_count"] = len(writes)
        trace = _safe_data_to_skill_trace(metrics.get("data_to_skill_trace"))
        if trace is not None:
            safe["data_to_skill_trace"] = trace
        return safe

    def _safe_transaction_item(item: Any) -> dict[str, Any]:
        payload = item.to_json()
        rollback_action = payload.get("rollback_action")
        rollback_operation = None
        rollback_key_count = 0
        if isinstance(rollback_action, dict):
            rollback_key_count = len(rollback_action)
            if isinstance(rollback_action.get("operation"), str):
                rollback_operation = rollback_action["operation"]
        return {
            "transaction_item_id": payload["transaction_item_id"],
            "item_kind": payload["item_kind"],
            "item_id": payload.get("item_id"),
            "relative_path": payload.get("relative_path"),
            "before_hash": payload.get("before_hash"),
            "after_hash": payload.get("after_hash"),
            "activation_state": payload["activation_state"],
            "rollback_operation": rollback_operation,
            "rollback_action_key_count": rollback_key_count,
            "created_at": payload["created_at"],
        }

    def _safe_writer_transaction_metrics(metrics: Any) -> dict[str, Any]:
        if not isinstance(metrics, dict):
            metrics = {}
        safe: dict[str, Any] = {
            "metric_key_count": len(metrics),
            "raw_metrics_returned": False,
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "allowlisted_writer_metrics_only",
            },
        }
        for key in (
            "slug",
            "active_relative_path",
            "manifest_sha256",
            "file_count",
            "previous_snapshot",
            "manifest_relative_path",
            "activation_deferred",
        ):
            if key not in metrics:
                continue
            value = metrics.get(key)
            if isinstance(value, str | int | bool) or value is None:
                safe[key] = value
        window = metrics.get("activation_window")
        if isinstance(window, dict):
            safe_window: dict[str, Any] = {
                "raw_window_payload_returned": False,
                "key_count": len(window),
            }
            for key in ("allowed", "status", "reason", "policy", "deferred_until"):
                if key not in window:
                    continue
                value = window.get(key)
                if isinstance(value, str | int | bool | float) or value is None:
                    safe_window[key] = value
            safe["activation_window"] = safe_window
        return safe

    def _is_writer_transaction(payload: dict[str, Any], items: list[dict[str, Any]]) -> bool:
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        transaction_kind = str(payload.get("transaction_kind") or "")
        if transaction_kind in {
            "compile_skill",
            "support_artifact_update",
            "rollback_skill",
            "archive_skill",
            "promote_skill",
        } and any(
            key in metrics
            for key in (
                "manifest_sha256",
                "active_relative_path",
                "previous_snapshot",
                "activation_window",
                "activation_deferred",
            )
        ):
            return True
        return any(
            item.get("item_kind")
            in {
                "compiled_skill_file",
                "artifact_manifest",
                "archive_snapshot",
                "filesystem_path",
                "compiled_bundle",
            }
            for item in items
        )

    def _safe_revocation_traversal_summary(summary: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {
            "summary_keys": sorted(str(key) for key in summary),
            "raw_summary_returned": False,
        }
        for key in (
            "source",
            "root_object_type",
            "root_object_id",
            "impacted_count",
            "truncated",
            "max_depth",
            "max_nodes",
            "rollback_transaction_id",
            "claimed_by",
        ):
            value = summary.get(key)
            if isinstance(value, str | int | bool) or value is None:
                safe[key] = value
        invalidation = summary.get("invalidation")
        if isinstance(invalidation, dict):
            safe["invalidation"] = {
                str(key): value
                for key, value in invalidation.items()
                if isinstance(value, int | bool | float) or value is None
            }
        impacted = summary.get("impacted_objects")
        if isinstance(impacted, list):
            safe["impacted_objects"] = [
                {
                    key: str(item[key]) if item.get(key) is not None else None
                    for key in ("object_type", "object_id", "relation")
                    if key in item
                }
                | (
                    {"depth": item["depth"]}
                    if isinstance(item.get("depth"), int)
                    else {}
                )
                for item in impacted[:100]
                if isinstance(item, dict)
            ]
            safe["impacted_object_limit"] = 100
        edges = summary.get("edges")
        if isinstance(edges, list):
            safe["edges"] = [
                {
                    key: str(item[key]) if item.get(key) is not None else None
                    for key in (
                        "source_kind",
                        "source_id",
                        "derived_kind",
                        "derived_id",
                        "relation",
                    )
                    if key in item
                }
                for item in edges[:100]
                if isinstance(item, dict)
            ]
            safe["edge_limit"] = 100
        return safe

    def _revocation_request_microscope(record: Any) -> dict[str, Any]:
        payload = record.to_json()
        request_id = payload["revocation_request_id"]
        root_ref = {
            "object_type": payload["root_object_type"],
            "object_id": payload["root_object_id"],
            "relationship": "revocation_root",
        }
        job_ref = (
            {
                "object_type": "job",
                "object_id": payload["created_by_job_id"],
                "relationship": "created_by_job",
            }
            if payload.get("created_by_job_id")
            else None
        )
        traversal_summary = (
            payload["traversal_summary"]
            if isinstance(payload.get("traversal_summary"), dict)
            else {}
        )
        safe_summary = _safe_revocation_traversal_summary(traversal_summary)
        downstream_refs: list[dict[str, Any]] = []
        for item in safe_summary.get("impacted_objects", []):
            if not isinstance(item, dict) or not item.get("object_type") or not item.get(
                "object_id"
            ):
                continue
            downstream_refs.append(
                {
                    "object_type": item["object_type"],
                    "object_id": item["object_id"],
                    "relationship": "impacted_by_revocation",
                }
            )
        if safe_summary.get("rollback_transaction_id"):
            downstream_refs.append(
                {
                    "object_type": "evolution_transaction",
                    "object_id": safe_summary["rollback_transaction_id"],
                    "relationship": "rollback_transaction",
                }
            )
        timeline = [
            {
                "at": payload["created_at"],
                "event": "revocation_request_created",
                "status": payload["status"],
                "request_kind": payload["request_kind"],
            }
        ]
        if payload.get("completed_at"):
            timeline.append(
                {
                    "at": payload["completed_at"],
                    "event": "revocation_request_completed",
                    "status": payload["status"],
                }
            )
        return {
            "schema_version": "skillkernel.observatory.revocation-request.v1",
            "object_type": "revocation_request",
            "object_id": request_id,
            "title": f"{payload['request_kind']} revocation {request_id}",
            "summary": (
                f"{payload['request_kind']} / {payload['status']}; "
                f"root={payload['root_object_type']}; "
                f"impacted={safe_summary.get('impacted_count', 'unknown')}"
            ),
            "workspace_key": payload.get("workspace_key"),
            "request_kind": payload["request_kind"],
            "status": payload["status"],
            "root": root_ref,
            "timeline": timeline,
            "provenance": {
                "upstream": [ref for ref in (root_ref, job_ref) if ref is not None],
                "downstream": downstream_refs[:100],
            },
            "effects": {
                "derived_state_revocation_status": payload["status"],
                "traversal": safe_summary,
                "downstream_ref_count": len(downstream_refs),
                "downstream_ref_limit": 100,
            },
            "diagnostics": {
                "supporting_component": "canary_rollback_freeze",
                "request_kind": payload["request_kind"],
                "root_object_type": payload["root_object_type"],
                "status": payload["status"],
                "completed": payload.get("completed_at") is not None,
                "traversal_summary_key_count": len(traversal_summary),
                "raw_traversal_summary_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_revocation_metadata",
            },
            "audit": {
                "links": [{"object_type": "revocation_request", "object_id": request_id}],
                "chain_visible": True,
            },
        }

    def _writer_transaction_microscope(
        transaction: Any,
        items: list[Any],
    ) -> dict[str, Any] | None:
        payload = transaction.to_json()
        transaction_id = payload["evolution_transaction_id"]
        safe_items = [_safe_transaction_item(item) for item in items[:100]]
        if not _is_writer_transaction(payload, safe_items):
            return None
        safe_metrics = _safe_writer_transaction_metrics(payload.get("metrics"))
        rollback_refs = [
            {
                "object_type": item["item_kind"],
                "object_id": item.get("item_id") or item["transaction_item_id"],
                "relationship": item.get("rollback_operation") or "writer_item",
            }
            for item in safe_items
            if item.get("rollback_operation")
        ]
        timeline = [
            {
                "at": payload["started_at"],
                "event": "writer_transaction_started",
                "status": payload["status"],
                "transaction_kind": payload["transaction_kind"],
            }
        ]
        if safe_metrics.get("activation_deferred"):
            timeline.append(
                {
                    "at": payload.get("committed_at") or payload["started_at"],
                    "event": "activation_window_deferred",
                    "status": payload["status"],
                }
            )
        if payload.get("committed_at"):
            timeline.append(
                {
                    "at": payload["committed_at"],
                    "event": "writer_transaction_committed",
                    "status": payload["status"],
                }
            )
        if payload.get("rolled_back_at"):
            timeline.append(
                {
                    "at": payload["rolled_back_at"],
                    "event": "writer_transaction_rolled_back",
                    "status": payload["status"],
                }
            )
        return {
            "schema_version": "skillkernel.observatory.writer-transaction.v1",
            "object_type": "writer_transaction",
            "object_id": transaction_id,
            "title": f"Writer transaction {transaction_id}",
            "summary": (
                f"{payload['transaction_kind']} / {payload['status']}; "
                f"files={safe_metrics.get('file_count', 'unknown')}; "
                f"items={len(safe_items)}"
            ),
            "workspace_key": payload.get("workspace_key"),
            "transaction_kind": payload["transaction_kind"],
            "status": payload["status"],
            "plan_hash": payload["plan_hash"],
            "timeline": timeline,
            "provenance": {
                "upstream": [
                    {
                        "object_type": "evolution_transaction",
                        "object_id": transaction_id,
                        "relationship": "governance_transaction",
                    }
                ],
                "downstream": rollback_refs[:100],
            },
            "effects": {
                "writer_metrics": safe_metrics,
                "items": safe_items,
                "item_count": len(safe_items),
                "transaction_item_limit": 100,
                "rollback_metadata_present": any(
                    item.get("rollback_operation") for item in safe_items
                ),
            },
            "diagnostics": {
                "supporting_component": "deterministic_writer",
                "transaction_kind": payload["transaction_kind"],
                "status": payload["status"],
                "activation_deferred": bool(safe_metrics.get("activation_deferred")),
                "activation_window_visible": "activation_window" in safe_metrics,
                "manifest_hash_visible": bool(safe_metrics.get("manifest_sha256")),
                "raw_metrics_returned": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_writer_transaction_metadata",
            },
            "audit": {
                "links": [
                    {"object_type": "evolution_transaction", "object_id": transaction_id},
                    {"object_type": "writer_transaction", "object_id": transaction_id},
                ],
                "chain_visible": True,
            },
        }

    def _evolution_transaction_microscope(
        transaction: Any,
        items: list[Any],
    ) -> dict[str, Any]:
        payload = transaction.to_json()
        transaction_id = payload["evolution_transaction_id"]
        safe_items = [_safe_transaction_item(item) for item in items[:100]]
        source_refs = [
            {"object_type": "evidence", "object_id": str(evidence_id)}
            for evidence_id in payload.get("source_evidence_ids", [])
        ] + [
            {"object_type": "memory", "object_id": str(memory_id)}
            for memory_id in payload.get("source_memory_ids", [])
        ]
        if payload.get("rollback_of_transaction_id"):
            source_refs.append(
                {
                    "object_type": "evolution_transaction",
                    "object_id": payload["rollback_of_transaction_id"],
                }
            )
        downstream_refs = [
            {
                "object_type": item["item_kind"],
                "object_id": item.get("item_id") or item["transaction_item_id"],
            }
            for item in safe_items
        ]
        timeline = [
            {
                "at": payload["started_at"],
                "event": "evolution_transaction_started",
                "status": payload["status"],
                "transaction_kind": payload["transaction_kind"],
            }
        ]
        if payload.get("committed_at"):
            timeline.append(
                {
                    "at": payload["committed_at"],
                    "event": "evolution_transaction_committed",
                    "status": payload["status"],
                }
            )
        if payload.get("rolled_back_at"):
            timeline.append(
                {
                    "at": payload["rolled_back_at"],
                    "event": "evolution_transaction_rolled_back",
                    "status": payload["status"],
                }
            )
        return {
            "schema_version": "skillkernel.observatory.evolution-transaction.v1",
            "object_type": "evolution_transaction",
            "object_id": transaction_id,
            "title": f"{payload['transaction_kind']} transaction {transaction_id}",
            "summary": (
                f"{payload['transaction_kind']} / {payload['status']}; "
                f"items={len(safe_items)}; evidence={len(payload.get('source_evidence_ids', []))}"
            ),
            "workspace_key": payload.get("workspace_key"),
            "transaction_kind": payload["transaction_kind"],
            "status": payload["status"],
            "plan_hash": payload["plan_hash"],
            "actor": payload["actor"],
            "idempotency_key_hash": sha256_text(payload["idempotency_key"]),
            "timeline": timeline,
            "provenance": {
                "upstream": source_refs,
                "downstream": downstream_refs,
            },
            "effects": {
                "items": safe_items,
                "item_count": len(safe_items),
                "transaction_item_limit": 100,
            },
            "diagnostics": {
                "supporting_component": "audit_trace",
                "transaction_kind": payload["transaction_kind"],
                "status": payload["status"],
                "source_evidence_count": len(payload.get("source_evidence_ids", [])),
                "source_memory_count": len(payload.get("source_memory_ids", [])),
                "policy_snapshot_keys": sorted(
                    str(key)
                    for key in (
                        payload["policy_snapshot"].keys()
                        if isinstance(payload.get("policy_snapshot"), dict)
                        else []
                    )
                ),
                "metrics": _safe_transaction_metrics(payload.get("metrics")),
                "cause_key_count": (
                    len(payload["cause"]) if isinstance(payload.get("cause"), dict) else 0
                ),
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "content_safe_transaction_metadata",
            },
            "audit": {
                "links": [{"object_type": "evolution_transaction", "object_id": transaction_id}],
                "chain_visible": True,
            },
        }

    async def _record_observatory_action(
        request: ObservatoryActionRequest,
        authorization: str | None,
        roles_header: str | None,
        *,
        http_request: Request | None = None,
        csrf_token: str | None = None,
    ) -> ObservatoryActionResponse:
        principal = _require_admin_auth(
            authorization,
            roles_header,
            required_roles={"operator", "admin"},
        )
        _require_admin_csrf(
            request=http_request,
            authorization=authorization,
            csrf_token=csrf_token,
        )
        _require_admin_rate_limit(
            principal,
            bucket="admin-actions",
            limit=ADMIN_ACTION_RATE_LIMIT,
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
            "reveal_raw_content",
            "revoke_source",
        }
        high_impact_actions = {
            "historical_import",
            "quarantine_candidate",
            "freeze_skill",
            "unfreeze_skill",
            "rollback_skill",
            "rollback_transaction",
            "reveal_raw_content",
            "revoke_source",
        }
        accepted = request.action in allowed_actions
        reason_codes: list[str] = [] if accepted else ["unsupported-observatory-action"]
        reveal_grant: dict[str, object] | None = None
        if (
            request.action == "reveal_raw_content"
            and not get_settings().web_admin_raw_content_enabled
        ):
            accepted = False
            reason_codes = ["raw-content-disabled"]
        if request.action == "reveal_raw_content":
            _require_admin_rate_limit(
                principal,
                bucket="raw-reveal",
                limit=ADMIN_RAW_REVEAL_RATE_LIMIT,
            )
            if "admin" not in principal["roles"]:
                accepted = False
                reason_codes = ["admin-role-required"]
            elif not (request.reason or "").strip():
                accepted = False
                reason_codes = ["reveal-reason-required"]
        confirmation_required = request.action in high_impact_actions
        confirmation_hash = (
            f"sha256:{sha256_text(request.confirmation)}"
            if request.confirmation
            else None
        )
        if (
            accepted
            and confirmation_required
            and not request.dry_run
            and request.confirmation != "confirm"
        ):
            accepted = False
            reason_codes = ["confirmation-required"]
        response_meta = _admin_response_meta()
        target_type, target_id = _observatory_action_target(
            request.action,
            request.target,
        )
        request_fingerprint = _observatory_action_request_fingerprint(
            request=request,
            target_type=target_type,
            target_id=target_id,
            confirmation_hash=confirmation_hash,
        )
        existing_action = await observatory_admin.get_action_audit_by_idempotency(
            actor_id=str(principal["subject"]),
            action_kind=request.action,
            target_type=target_type,
            target_id=target_id,
            idempotency_key=request.idempotency_key,
        )
        if existing_action is not None:
            existing_payload = existing_action.request_payload_redacted
            existing_fingerprint = existing_payload.get("request_fingerprint")
            idempotency_collision = (
                isinstance(existing_fingerprint, str)
                and existing_fingerprint != request_fingerprint
            )
            replay_reason_codes = ["idempotency-replay"]
            if idempotency_collision:
                replay_reason_codes.append("idempotency-collision")
            return ObservatoryActionResponse(
                receipt=action_receipt(
                    action=request.action,
                    role=str(principal["role"]),
                    idempotency_key=request.idempotency_key,
                    accepted=existing_action.result in {"accepted", "completed"},
                    reason_codes=replay_reason_codes,
                    action_audit=existing_action.to_json(),
                    action_attribution_check=existing_payload.get(
                        "action_attribution_check"
                    )
                    if isinstance(existing_payload, dict)
                    else None,
                    idempotency_replay=True,
                    idempotency_collision=idempotency_collision,
                ),
                meta=response_meta,
            )
        if accepted and request.action == "reveal_raw_content" and not request.dry_run:
            reveal_token = f"skor_{secrets.token_urlsafe(32)}"
            expires_at = datetime.now(UTC) + timedelta(minutes=5)
            reveal_grant = {
                "schema_version": "skillkernel.observatory.raw-reveal-grant.v1",
                "token": reveal_token,
                "token_hash": f"sha256:{sha256_text(reveal_token)}",
                "expires_at": expires_at.isoformat(),
                "target_type": target_type,
                "target_id": target_id,
                "raw_content_included": False,
            }
        action_request_payload = {
            "schema_version": "skillkernel.observatory.admin-action-request.v1",
            "request_id": response_meta["request_id"],
            "workspace_id": request.workspace_id,
            "target": request.target,
            "dry_run": request.dry_run,
            "metadata_keys": sorted(request.metadata.keys()),
            "confirmation_present": request.confirmation is not None,
            "confirmation_hash": confirmation_hash,
            "confirmation_required": confirmation_required,
            "reason_codes": reason_codes,
            "request_fingerprint": request_fingerprint,
            "source": _source_identity(http_request),
        }
        if reveal_grant is not None:
            action_request_payload["raw_reveal_grant"] = {
                "token_hash": reveal_grant["token_hash"],
                "expires_at": reveal_grant["expires_at"],
                "target_type": target_type,
                "target_id": target_id,
                "raw_content_included": False,
            }
        action_attribution_check = await attribution.record_action_check(
            workspace_key=request.workspace_id,
            session_id=None,
            turn_id=None,
            tool_call_id=response_meta["request_id"],
            action_kind=f"observatory.{request.action}",
            risk_tier=_observatory_action_risk_tier(
                request.action,
                dry_run=request.dry_run,
            ),
            verdict="allowed" if accepted else "blocked",
            user_intent_hash=_observatory_action_intent_hash(
                request=request,
                target_type=target_type,
                target_id=target_id,
                confirmation_hash=confirmation_hash,
            ),
            counterfactual_kind="admin_policy_gate",
            metrics={
                "schema_version": (
                    "skillkernel.observatory.action-attribution-check.v1"
                ),
                "request_id": response_meta["request_id"],
                "workspace_id": request.workspace_id,
                "action": request.action,
                "target_type": target_type,
                "target_id": target_id,
                "dry_run": request.dry_run,
                "accepted": accepted,
                "reason_codes": reason_codes,
                "confirmation_required": confirmation_required,
                "confirmation_hash_present": confirmation_hash is not None,
                "idempotency_key_hash": sha256_text(request.idempotency_key),
                "source": _source_identity(http_request),
                "raw_content_included": False,
            },
        )
        action_attribution_check_receipt = _action_attribution_check_receipt(
            action_attribution_check
        )
        action_request_payload["action_attribution_check"] = (
            action_attribution_check_receipt
        )
        audit_record = await audit.append_record(
            AuditRecord(
                action=f"observatory.{request.action}",
                actor=str(principal["subject"]),
                subject_type="observatory_action",
                subject_id=request.idempotency_key,
                details={
                    "target": request.target,
                    "reason": request.reason or "",
                    "dry_run": request.dry_run,
                    "accepted": accepted,
                    "reason_codes": reason_codes,
                    "metadata": request.metadata,
                    "request_id": response_meta["request_id"],
                    "target_type": target_type,
                    "target_id": target_id,
                    "actor_roles": principal["roles"],
                    "confirmation_hash": confirmation_hash,
                    "confirmation_required": confirmation_required,
                    "action_attribution_check_id": str(
                        action_attribution_check.action_attribution_check_id
                    ),
                    "action_attribution_verdict": action_attribution_check.verdict,
                    "raw_reveal_grant_hash": (
                        reveal_grant["token_hash"] if reveal_grant is not None else None
                    ),
                    "raw_content_included": False,
                },
            ),
            workspace_key=request.workspace_id,
        )
        action_audit = await observatory_admin.record_action_audit(
            actor_id=str(principal["subject"]),
            actor_roles=[str(role) for role in principal["roles"]],
            action_kind=request.action,
            target_type=target_type,
            target_id=target_id,
            idempotency_key=request.idempotency_key,
            request_payload_redacted=action_request_payload,
            reason=request.reason or "",
            result="accepted" if accepted else "rejected",
            linked_audit_id=audit_record.audit_id,
        )
        live_event = await observatory_admin.append_live_event(
            kind=_observatory_live_kind_for_action(request.action, accepted=accepted),
            component_id=_observatory_component_for_action(request.action),
            object_type=target_type,
            object_id=target_id,
            payload={
                "workspace_id": request.workspace_id,
                "action": request.action,
                "accepted": accepted,
                "reason_codes": reason_codes,
                "audit_id": str(audit_record.audit_id),
                "action_id": str(action_audit.action_id),
            },
        )
        return ObservatoryActionResponse(
            receipt=action_receipt(
                action=request.action,
                role=str(principal["role"]),
                idempotency_key=request.idempotency_key,
                accepted=accepted,
                reason_codes=reason_codes,
                audit=audit_record.model_dump(mode="json"),
                action_audit=action_audit.to_json(),
                action_attribution_check=action_attribution_check_receipt,
                live_event=live_event.to_json(),
                raw_reveal_grant=reveal_grant,
                idempotency_replay=False,
                idempotency_collision=False,
            ),
            meta=response_meta,
        )

    def _observatory_live_kind_for_action(action: str, *, accepted: bool) -> str:
        if not accepted:
            return "observatory_self_health_changed"
        if action == "refresh_read_models":
            return "read_model_invalidated"
        if action == "verify_live_stream":
            return "observatory_self_health_changed"
        if action == "verify_audit_chain":
            return "audit_record_appended"
        if action in {"freeze_skill", "unfreeze_skill", "rollback_skill", "rollback_transaction"}:
            return "skill_state_changed"
        if action in {"retry_job", "cancel_job"}:
            return "job_progress"
        return "audit_record_appended"

    def _observatory_component_for_action(action: str) -> str:
        if action in {"verify_audit_chain"}:
            return "audit_trace"
        if action in {"refresh_read_models", "verify_live_stream"}:
            return "observatory_admin"
        if action in {"retry_job", "cancel_job", "pause_schedule", "resume_schedule"}:
            return "scheduler_jobs"
        if "broker" in action:
            return "broker_runtime"
        if "profile" in action:
            return "model_embedding"
        if "storage" in action:
            return "storage_db"
        return "observatory_admin"

    def _trace_component_for_operation(operation_kind: str) -> str:
        return {
            "archive": "activation_curation",
            "broker": "broker_runtime",
            "compiler": "context_compiler",
            "embedding_call": "model_embedding",
            "evaluator": "evaluator_probes",
            "evidence": "evidence_memory",
            "evolution": "topology_operations",
            "ingest": "spool_ingest",
            "job": "scheduler_jobs",
            "llm_call": "model_embedding",
            "memory": "evidence_memory",
            "plugin_capture": "openclaw_live_capture",
            "promotion": "activation_curation",
            "redaction": "redaction_taint",
            "retrieval": "retrieval_indexing",
            "rollback": "canary_rollback",
            "scanner": "scanner_security",
            "scheduler": "scheduler_jobs",
            "tool_attribution": "audit_trace",
            "topology": "topology_operations",
            "writer": "deterministic_writer",
        }.get(operation_kind, "audit_trace")

    def _trace_parse_iso_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _trace_span_duration_ms(span_payload: dict[str, Any]) -> int | None:
        started_at = _trace_parse_iso_datetime(str(span_payload["started_at"]))
        ended_at_raw = span_payload.get("ended_at")
        if ended_at_raw is None:
            return None
        ended_at = _trace_parse_iso_datetime(str(ended_at_raw))
        return max(0, int((ended_at - started_at).total_seconds() * 1000))

    def _trace_policy_badges(span_payload: dict[str, Any]) -> list[dict[str, Any]]:
        attrs = span_payload.get("safe_attributes")
        if not isinstance(attrs, dict):
            return []
        badges: list[dict[str, Any]] = []
        for key in sorted(attrs):
            key_text = str(key)
            lower_key = key_text.lower()
            if not any(
                marker in lower_key
                for marker in (
                    "gate",
                    "policy",
                    "verdict",
                    "scanner",
                    "evaluator",
                    "activation",
                    "canary",
                    "rollback",
                    "blocked",
                )
            ):
                continue
            value = attrs[key]
            if isinstance(value, str | int | float | bool) or value is None:
                safe_value: object = value
            else:
                safe_value = type(value).__name__
            badges.append(
                {
                    "label": key_text,
                    "value": safe_value,
                    "status": _trace_badge_status(key_text, safe_value),
                }
            )
        return badges

    def _trace_badge_status(label: str, value: object) -> str:
        value_text = str(value).lower()
        label_text = label.lower()
        if value is False or any(
            marker in value_text for marker in ("blocked", "failed", "denied", "reject")
        ):
            return "blocked"
        if value is True or any(marker in value_text for marker in ("pass", "ok", "allow")):
            return "passed"
        if any(marker in label_text for marker in ("gate", "policy", "verdict")):
            return "observed"
        return "informational"

    def _trace_diff_panels(span_payload: dict[str, Any]) -> list[dict[str, Any]]:
        attrs = span_payload.get("safe_attributes")
        if not isinstance(attrs, dict):
            return []
        diff_keys = [
            key
            for key in sorted(attrs)
            if any(
                marker in str(key).lower()
                for marker in (
                    "diff",
                    "before_hash",
                    "after_hash",
                    "manifest_hash",
                    "artifact_hash",
                    "compiled_hash",
                    "skillir_hash",
                )
            )
        ]
        if not diff_keys:
            return []
        return [
            {
                "span_id": span_payload["span_id"],
                "title": "Safe artifact/hash diff metadata",
                "metadata": {
                    key: attrs[key]
                    if isinstance(attrs[key], str | int | float | bool) or attrs[key] is None
                    else type(attrs[key]).__name__
                    for key in diff_keys
                },
                "raw_diff_available": False,
            }
        ]

    def _trace_replay_object(
        *,
        trace_id: UUID,
        workspace_id: str,
        spans: list[Any],
    ) -> dict[str, Any]:
        span_payloads = sorted(
            (span.to_json() for span in spans),
            key=lambda payload: (payload["started_at"], payload["span_id"]),
        )
        station_counts: dict[str, int] = {}
        station_statuses: dict[str, set[str]] = {}
        timeline: list[dict[str, Any]] = []
        waterfall: list[dict[str, Any]] = []
        detail_drawer: list[dict[str, Any]] = []
        policy_gate_badges: list[dict[str, Any]] = []
        diff_panels: list[dict[str, Any]] = []
        downstream: list[dict[str, Any]] = []
        seen_refs: set[tuple[str, str]] = set()

        for index, payload in enumerate(span_payloads, start=1):
            component_id = _trace_component_for_operation(str(payload["operation_kind"]))
            station_counts[component_id] = station_counts.get(component_id, 0) + 1
            station_statuses.setdefault(component_id, set()).add(str(payload["status"]))
            duration_ms = _trace_span_duration_ms(payload)
            badges = _trace_policy_badges(payload)
            policy_gate_badges.extend(
                {"span_id": payload["span_id"], "component_id": component_id, **badge}
                for badge in badges
            )
            diff_panels.extend(_trace_diff_panels(payload))
            object_refs = [
                ref for ref in payload.get("object_refs", []) if isinstance(ref, dict)
            ]
            for ref in object_refs:
                ref_key = (str(ref.get("object_type")), str(ref.get("object_id")))
                if ref_key in seen_refs:
                    continue
                seen_refs.add(ref_key)
                downstream.append(
                    {
                        "object_type": ref_key[0],
                        "object_id": ref_key[1],
                    }
                )
            timeline.append(
                {
                    **payload,
                    "index": index,
                    "at": payload["started_at"],
                    "event": "span_observed",
                    "component_id": component_id,
                    "duration_ms": duration_ms,
                    "policy_gate_badges": badges,
                }
            )
            waterfall.append(
                {
                    "span_id": payload["span_id"],
                    "parent_span_id": payload["parent_span_id"],
                    "component_id": component_id,
                    "operation_name": payload["operation_name"],
                    "operation_kind": payload["operation_kind"],
                    "status": payload["status"],
                    "started_at": payload["started_at"],
                    "ended_at": payload["ended_at"],
                    "duration_ms": duration_ms,
                }
            )
            detail_drawer.append(
                {
                    "span_id": payload["span_id"],
                    "component_id": component_id,
                    "safe_attribute_keys": sorted(
                        str(key)
                        for key in (
                            payload.get("safe_attributes")
                            if isinstance(payload.get("safe_attributes"), dict)
                            else {}
                        )
                    ),
                    "object_refs": object_refs,
                    "raw_content_available": False,
                }
            )

        station_highlights = [
            {
                "component_id": component_id,
                "span_count": station_counts[component_id],
                "statuses": sorted(station_statuses[component_id]),
                "highlight": True,
            }
            for component_id in sorted(station_counts)
        ]
        export_payload = {
            "trace_id": str(trace_id),
            "workspace_id": workspace_id,
            "span_count": len(span_payloads),
            "station_ids": [item["component_id"] for item in station_highlights],
            "object_ref_count": len(downstream),
            "raw_content_included": False,
        }
        return {
            "schema_version": "skillkernel.observatory.trace-replay.v1",
            "object_type": "trace",
            "object_id": str(trace_id),
            "workspace_id": workspace_id,
            "title": f"Trace {trace_id}",
            "summary": "Content-safe trace replay assembled from recorded spans.",
            "timeline": timeline,
            "span_waterfall": waterfall,
            "station_highlights": station_highlights,
            "policy_gate_badges": policy_gate_badges,
            "detail_drawer": detail_drawer,
            "diff_panels": diff_panels,
            "provenance": {
                "upstream": [],
                "downstream": downstream,
            },
            "redacted_export_bundle": {
                "schema_version": "skillkernel.observatory.trace-bundle.v1",
                "bundle_hash": sha256_text(json.dumps(export_payload, sort_keys=True)),
                **export_payload,
            },
            "replay_safety": {
                "reexecutes_work": False,
                "raw_content_included": False,
                "uses_persisted_state_only": True,
                "mutates_policy": False,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
            "diagnostics": {
                "span_count": len(span_payloads),
                "station_count": len(station_highlights),
                "object_ref_count": len(downstream),
                "bounded_limit": len(span_payloads),
            },
        }

    def _trace_detail_microscope(
        trace_id: UUID,
        *,
        spans: list[Any],
    ) -> dict[str, Any]:
        span_payloads = sorted(
            (span.to_json() for span in spans),
            key=lambda payload: (payload["started_at"], payload["span_id"]),
        )
        downstream = [
            ref
            for span in span_payloads
            for ref in span.get("object_refs", [])
            if isinstance(ref, dict)
        ]
        return {
            "schema_version": "skillkernel.observatory.trace-detail.v1",
            "object_type": "trace",
            "object_id": str(trace_id),
            "title": f"Trace {trace_id}",
            "summary": "Content-safe trace detail assembled from recorded spans.",
            "timeline": span_payloads,
            "provenance": {
                "upstream": [],
                "downstream": downstream,
            },
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
            },
            "diagnostics": {
                "supporting_component": "audit_trace",
                "span_count": len(span_payloads),
                "operation_kinds": sorted(
                    {
                        str(span.get("operation_kind"))
                        for span in span_payloads
                        if span.get("operation_kind")
                    }
                ),
                "statuses": sorted(
                    {
                        str(span.get("status"))
                        for span in span_payloads
                        if span.get("status")
                    }
                ),
                "object_ref_count": len(downstream),
                "raw_span_attributes_returned": False,
                "replay_reexecutes_work": False,
            },
            "audit": {"links": []},
        }

    def _snapshot_live_fallback(
        snapshot: dict[str, object],
        *,
        last_seq: int | None,
        cursor_seq: int | None = None,
    ) -> dict[str, object]:
        return build_live_envelope(snapshot, last_seq=last_seq, cursor_seq=cursor_seq)

    async def _observatory_starting_outbox_seq(last_seq: int | None) -> int | None:
        latest_seq = await observatory_admin.latest_live_event_seq()
        if latest_seq is None:
            return None
        if last_seq is None:
            return latest_seq
        if last_seq > latest_seq:
            return latest_seq
        return last_seq

    def _observatory_action_target(
        action: str,
        target: dict[str, object],
    ) -> tuple[str, str]:
        target_type = str(
            target.get("object_type")
            or target.get("type")
            or _observatory_action_target_type(action)
        )
        target_id = str(
            target.get("object_id")
            or target.get("id")
            or target.get("target_id")
            or action
        )
        return target_type[:128], target_id[:512]

    def _observatory_action_target_type(action: str) -> str:
        if action.endswith("_job"):
            return "job"
        if action.endswith("_schedule"):
            return "schedule"
        if action.endswith("_skill"):
            return "skill"
        if action.endswith("_evaluation"):
            return "evaluation"
        if action in {"qualify_model_profile", "qualify_embedding_profile"}:
            return "profile"
        if action in {"storage_health_check", "storage_retention_dry_run"}:
            return "storage"
        if action in {"verify_audit_chain"}:
            return "audit"
        if action in {"revoke_source"}:
            return "source"
        return "observatory_action"

    def _register_observatory_action_route(path: str, action: str) -> None:
        @app.post(path, response_model=ObservatoryActionResponse)
        async def observatory_action_alias(
            request: Request,
            authorization: Annotated[str | None, Header()] = None,
            x_skillkernel_roles: Annotated[
                str | None, Header(alias="X-SkillKernel-Roles")
            ] = None,
            x_skillkernel_csrf: Annotated[
                str | None, Header(alias=ADMIN_CSRF_HEADER)
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
                http_request=request,
                csrf_token=x_skillkernel_csrf,
            )

    @app.get("/admin/api/v1/config", response_model=ObservatoryConfigResponse)
    async def observatory_config(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryConfigResponse:
        principal = _require_admin_auth(authorization, x_skillkernel_roles)
        settings = get_settings()
        return ObservatoryConfigResponse(
            config={
                "base_path": _admin_base_path(),
                "api_base_path": f"{_admin_base_path()}/api/v1",
                "live_path": f"{_admin_base_path()}/live",
                "enabled": settings.web_admin_enabled,
                "static_available": _admin_static_available(),
                "static_serving": "observatory_container",
                "principal": principal,
                "raw_content": {"enabled": settings.web_admin_raw_content_enabled},
                "csrf": {
                    "enabled": settings.web_admin_csrf_enabled,
                    "browser_session_header": ADMIN_BROWSER_SESSION_HEADER,
                    "header": ADMIN_CSRF_HEADER,
                    "token": _admin_csrf_token(authorization),
                },
                "rate_limits": {
                    "action_per_actor_per_minute": ADMIN_ACTION_RATE_LIMIT,
                    "raw_reveal_per_actor_per_minute": ADMIN_RAW_REVEAL_RATE_LIMIT,
                },
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
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
    ) -> ObservatorySnapshotResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        response.headers.update(NO_STORE_HEADERS)
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
        cursor: str | None = None,
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
            cursor=cursor,
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
            object=_component_metrics_microscope(component_id, component)
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
        cursor: str | None = None,
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
            cursor=cursor,
            source="observatory_snapshot.reason_code_catalog",
        )

    @app.get("/admin/api/v1/playbooks", response_model=ObservatoryCollectionResponse)
    async def observatory_playbooks(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
        cursor: str | None = None,
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
            cursor=cursor,
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
        return ObservatoryObjectResponse(
            object=playbook_detail(snapshot, playbook_id)
        )

    @app.get("/admin/api/v1/invariants", response_model=ObservatoryCollectionResponse)
    async def observatory_invariants(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 100,
        cursor: str | None = None,
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
            cursor=cursor,
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

    @app.get("/admin/api/v1/opportunities", response_model=ObservatoryCollectionResponse)
    async def observatory_opportunities(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        min_support: int = 2,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        effective_workspace_id = workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID
        bounded_min_support = max(2, min(min_support, 25))
        result = await mine_opportunities(
            evidence,
            retrieval,
            workspace_key=effective_workspace_id,
            limit=500,
            min_support=bounded_min_support,
            record_retrieval=False,
        )
        return _observatory_collection(
            object_type="opportunity",
            title="Opportunity mining candidates",
            items=[
                _opportunity_admin_record(candidate.to_json())
                for candidate in result.candidates
            ],
            limit=limit,
            cursor=cursor,
            source="opportunity_miner.mine_opportunities",
            diagnostics={
                "supporting_component": "opportunity_mining",
                "workspace_id": effective_workspace_id,
                "scanned": result.scanned,
                "min_support": bounded_min_support,
                "candidate_mutation_allowed": False,
                "retrieval_decision_recorded": False,
                "raw_evidence_returned": False,
            },
        )

    @app.get("/admin/api/v1/evidence/fidelity", response_model=ObservatoryCollectionResponse)
    async def observatory_evidence_fidelity(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        decision_family: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_evidence_fidelity_status(
            workspace_key=workspace_id,
            decision_family=decision_family,
            limit=500,
        )
        return _observatory_collection(
            object_type="evidence_fidelity_status",
            title="Evidence fidelity status",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_evidence_fidelity_status",
            diagnostics={
                "supporting_component": "evidence_memory",
                "decision_family": decision_family,
                "raw_content_available": False,
                "status_read_model_only": True,
            },
        )

    @app.get(
        "/admin/api/v1/evidence/fidelity/{fidelity_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_evidence_fidelity_detail(
        fidelity_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        record = await observatory_admin.get_evidence_fidelity_status(object_id=fidelity_id)
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="evidence fidelity status not found",
            )
        return ObservatoryObjectResponse(object=record.to_json())

    @app.get(
        "/admin/api/v1/raw-vault/summary",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_raw_vault_summary(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_evidence_fidelity_status(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="raw_vault_fidelity_summary",
            title="Raw-vault policy and evidence-fidelity summary",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_evidence_fidelity_status",
            diagnostics={
                "supporting_component": "evidence_memory",
                "raw_content_available": False,
                "raw_vault_records_returned": False,
            },
        )

    @app.get("/admin/api/v1/adjudications", response_model=ObservatoryCollectionResponse)
    async def observatory_semantic_adjudications(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        decision_family: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_semantic_adjudications(
            workspace_key=workspace_id,
            decision_family=decision_family,
            limit=500,
        )
        return _observatory_collection(
            object_type="semantic_adjudication",
            title="Semantic adjudications",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_semantic_adjudications",
            diagnostics={
                "supporting_component": "model_embedding",
                "decision_family": decision_family,
                "verdict_payload_returned": False,
            },
        )

    @app.get(
        "/admin/api/v1/adjudications/{adjudication_run_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_semantic_adjudication_detail(
        adjudication_run_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_id = _uuid_or_404(adjudication_run_id, "semantic adjudication")
        record = await observatory_admin.get_semantic_adjudication(
            adjudication_run_id=parsed_id,
        )
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="semantic adjudication not found",
            )
        return ObservatoryObjectResponse(object=record.to_json())

    @app.get(
        "/admin/api/v1/autonomy/decisions",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_autonomy_decisions(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        decision_family: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_autonomy_decisions(
            workspace_key=workspace_id,
            decision_family=decision_family,
            limit=500,
        )
        return _observatory_collection(
            object_type="autonomy_decision",
            title="Autonomy decisions",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_autonomy_decisions",
            diagnostics={
                "supporting_component": "operator_action_gateway",
                "decision_family": decision_family,
                "hard_and_soft_gates_visible": True,
            },
        )

    @app.get(
        "/admin/api/v1/autonomy/decisions/{decision_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_autonomy_decision_detail(
        decision_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_id = _uuid_or_404(decision_id, "autonomy decision")
        record = await observatory_admin.get_autonomy_decision(decision_id=parsed_id)
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="autonomy decision not found",
            )
        return ObservatoryObjectResponse(object=record.to_json())

    @app.get(
        "/admin/api/v1/autonomy/threshold-deadlocks",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_threshold_deadlocks(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_autonomy_decisions(
            workspace_key=workspace_id,
            decision_family=None,
            limit=500,
        )
        deadlocks = [
            _threshold_deadlock_payload(record)
            for record in records
            if _is_threshold_deadlock_decision(record)
        ]
        return _observatory_collection(
            object_type="threshold_deadlock",
            title="Threshold-deadlock findings",
            items=deadlocks,
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_autonomy_decisions",
            diagnostics={
                "supporting_component": "evaluator_probes",
                "derived_from": "admin_autonomy_decision_status",
                "raw_content_available": False,
            },
        )

    @app.get(
        "/admin/api/v1/autonomy/threshold-deadlocks/{decision_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_threshold_deadlock_detail(
        decision_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_id = _uuid_or_404(decision_id, "threshold deadlock")
        record = await observatory_admin.get_autonomy_decision(decision_id=parsed_id)
        if record is None or not _is_threshold_deadlock_decision(record):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="threshold deadlock not found",
            )
        return ObservatoryObjectResponse(object=_threshold_deadlock_payload(record))

    @app.get("/admin/api/v1/escalations", response_model=ObservatoryCollectionResponse)
    async def observatory_administrative_escalations(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        resolution_state: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await observatory_admin.list_administrative_escalations(
            workspace_key=workspace_id,
            resolution_state=resolution_state,
            limit=500,
        )
        return _observatory_collection(
            object_type="administrative_escalation",
            title="Administrative escalations",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_administrative_escalations",
            diagnostics={
                "supporting_component": "operator_action_gateway",
                "hard_boundary_only": True,
                "raw_content_available": False,
            },
        )

    @app.get(
        "/admin/api/v1/escalations/{event_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_administrative_escalation_detail(
        event_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_id = _uuid_or_404(event_id, "administrative escalation")
        record = await observatory_admin.get_administrative_escalation(event_id=parsed_id)
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="administrative escalation not found",
            )
        return ObservatoryObjectResponse(object=record.to_json())

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
        if object_type in {"captured_event", "event"}:
            event_id = _uuid_or_404(object_id, "captured event")
            event = await store.get_event(event_id=event_id, workspace_key=workspace_id)
            if event is not None:
                return ObservatoryObjectResponse(object=_event_microscope(event))
        if object_type in {"opportunity", "candidate_opportunity"}:
            effective_workspace_id = workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID
            opportunities = await mine_opportunities(
                evidence,
                retrieval,
                workspace_key=effective_workspace_id,
                limit=500,
                min_support=2,
                record_retrieval=False,
            )
            for opportunity in opportunities.candidates:
                payload = opportunity.to_json()
                if object_id in {
                    str(payload["key"]),
                    str(payload["candidate_slug"]),
                    sha256_text(str(payload["key"])),
                }:
                    return ObservatoryObjectResponse(
                        object=_opportunity_admin_record(payload)
                    )
        if object_type in {"baseline_comparison", "comparison"}:
            comparison_id = _uuid_or_404(object_id, "baseline comparison")
            comparison = await observatory_admin.get_comparison(
                comparison_id=comparison_id,
                workspace_key=workspace_id,
            )
            if comparison is not None:
                return ObservatoryObjectResponse(object=_comparison_microscope(comparison))
        if object_type in {"diagnostic_bundle", "bundle"}:
            bundle_id = _uuid_or_404(object_id, "diagnostic bundle")
            bundle = await observatory_admin.get_diagnostic_bundle(
                bundle_id=bundle_id,
                workspace_key=workspace_id,
            )
            if bundle is not None:
                return ObservatoryObjectResponse(object=_diagnostic_bundle_microscope(bundle))
        if object_type in {"admin_action", "operator_action", "action_audit"}:
            action_id = _uuid_or_404(object_id, "operator action")
            action = await observatory_admin.get_action_audit(action_id=action_id)
            if action is not None:
                return ObservatoryObjectResponse(object=_admin_action_microscope(action))
        if object_type in {
            "component_metrics",
            "component-metrics",
            "station_metrics",
            "station-metrics",
        }:
            snapshot = await _observatory_snapshot(
                workspace_id=workspace_id,
                window_minutes=window_minutes,
            )
            component = _find_by_id(
                list(snapshot["pipeline"]["stations"]),  # type: ignore[index]
                object_id,
                ("component_id",),
            )
            if component is not None:
                return ObservatoryObjectResponse(
                    object=_component_metrics_microscope(object_id, component)
                )
        if object_type in {"job", "scheduler_job", "sidecar_job"}:
            listed = [
                job.to_json()
                for job in await jobs.list_jobs(
                    workspace_key=workspace_id,
                    limit=500,
                )
            ]
            job = _find_by_id(listed, object_id, ("job_id", "idempotency_key"))
            if job is not None:
                return ObservatoryObjectResponse(object=_job_microscope(object_id, job))
        if object_type in {"schedule", "scheduler_schedule", "sidecar_schedule"}:
            listed = [
                _schedule_admin_record(schedule.to_json())
                for schedule in await scheduler.list_schedules(limit=500)
            ]
            schedule = _find_by_id(listed, object_id, ("schedule_id", "name"))
            if schedule is not None and (
                workspace_id is None or schedule.get("workspace_key") == workspace_id
            ):
                return ObservatoryObjectResponse(
                    object=_schedule_microscope(
                        str(schedule.get("schedule_id") or object_id),
                        schedule,
                    )
                )
        if object_type in {"skill", "runtime_skill"}:
            listed = [
                skill.to_json()
                for skill in await skills.list_skills(
                    workspace_key=workspace_id,
                    lifecycle_state=None,
                    limit=500,
                )
            ]
            skill = _find_by_id(listed, object_id, ("skill_id", "slug", "active_version_id"))
            if skill is not None:
                return ObservatoryObjectResponse(
                    object=_skill_microscope(object_id, skill)
                )
        if object_type in {"skill_version", "skill-version", "skillir_revision"}:
            listed = [
                skill.to_json()
                for skill in await skills.list_skills(
                    workspace_key=workspace_id,
                    lifecycle_state=None,
                    limit=500,
                )
            ]
            skill = _find_by_id(listed, object_id, ("active_version_id",))
            if skill is not None:
                return ObservatoryObjectResponse(
                    object=_skill_microscope(
                        object_id,
                        skill,
                        object_type="skill_version",
                    )
                )
        if object_type in {"candidate", "candidate_skill", "skill_candidate"}:
            listed = [
                candidate.to_json()
                for candidate in await candidates.list_candidate_reviews(
                    workspace_key=workspace_id,
                    lifecycle_state=None,
                    limit=250,
                )
            ]
            candidate = _find_by_id(
                listed,
                object_id,
                ("skill_id", "skill_version_id", "slug", "name"),
            )
            if candidate is not None:
                return ObservatoryObjectResponse(
                    object=_candidate_microscope(object_id, candidate)
                )
        if object_type in {
            "action_attribution_check",
            "action-attribution-check",
            "operator_action_attribution",
        }:
            check_id = _uuid_or_404(object_id, "action attribution check")
            check = await attribution.get_action_check(
                workspace_key=workspace_id,
                action_attribution_check_id=check_id,
            )
            if check is not None:
                return ObservatoryObjectResponse(
                    object=_action_attribution_check_microscope(check)
                )
        if object_type in {"evidence_fidelity_status", "evidence_fidelity"}:
            fidelity = await observatory_admin.get_evidence_fidelity_status(
                object_id=object_id
            )
            if fidelity is not None:
                return ObservatoryObjectResponse(object=fidelity.to_json())
        if object_type in {"autonomy_decision", "autonomy-decision"}:
            decision_id = _uuid_or_404(object_id, "autonomy decision")
            decision = await observatory_admin.get_autonomy_decision(
                decision_id=decision_id
            )
            if decision is not None:
                return ObservatoryObjectResponse(object=decision.to_json())
        if object_type in {"threshold_deadlock", "threshold-deadlock"}:
            decision_id = _uuid_or_404(object_id, "threshold deadlock")
            decision = await observatory_admin.get_autonomy_decision(
                decision_id=decision_id
            )
            if decision is not None and _is_threshold_deadlock_decision(decision):
                return ObservatoryObjectResponse(
                    object=_threshold_deadlock_payload(decision)
                )
        if object_type in {"semantic_adjudication", "adjudication"}:
            adjudication_id = _uuid_or_404(object_id, "semantic adjudication")
            adjudication = await observatory_admin.get_semantic_adjudication(
                adjudication_run_id=adjudication_id,
            )
            if adjudication is not None:
                return ObservatoryObjectResponse(object=adjudication.to_json())
        if object_type in {"administrative_escalation", "escalation"}:
            escalation_id = _uuid_or_404(object_id, "administrative escalation")
            escalation = await observatory_admin.get_administrative_escalation(
                event_id=escalation_id,
            )
            if escalation is not None:
                return ObservatoryObjectResponse(object=escalation.to_json())
        if object_type in {"broker_replay_episode", "replay_episode"}:
            episode_id = _uuid_or_404(object_id, "broker replay episode")
            episode = await broker_policies.get_replay_episode(
                workspace_key=workspace_id,
                broker_replay_episode_id=episode_id,
            )
            if episode is not None:
                return ObservatoryObjectResponse(
                    object=_broker_replay_episode_microscope(episode)
                )
        if object_type in {"broker_decision", "broker-decision", "retrieval_log"}:
            retrieval_log_id = _uuid_or_404(object_id, "broker decision")
            log = await retrieval.get_log(
                workspace_key=workspace_id,
                retrieval_log_id=retrieval_log_id,
            )
            if log is not None:
                return ObservatoryObjectResponse(object=_broker_decision_microscope(log))
        if object_type in {
            "historical_import",
            "historical_import_source",
            "historical-source",
            "historical_source",
        }:
            listed = [
                source.to_json()
                for source in await historical_import.list_sources(
                    workspace_key=workspace_id,
                    limit=500,
                )
            ]
            source = _find_by_id(
                listed,
                object_id,
                (
                    "historical_import_source_id",
                    "external_source_id",
                    "source_kind",
                ),
            )
            if source is not None:
                return ObservatoryObjectResponse(
                    object=_historical_import_source_admin_record(
                        source,
                        requested_id=object_id,
                    )
                )
        if object_type in {
            "context_artifact",
            "context-artifact",
            "artifact",
            "compiled_artifact",
            "compiled-artifact",
        }:
            context_artifact_id = _uuid_or_404(object_id, "context artifact")
            artifact = await context_governance.get_artifact(
                workspace_key=workspace_id,
                context_artifact_id=context_artifact_id,
            )
            if artifact is not None:
                return ObservatoryObjectResponse(
                    object=_context_artifact_admin_record(artifact)
                )
        if object_type in {"context_compile_run", "context-compile-run"}:
            context_compile_run_id = _uuid_or_404(object_id, "context compile run")
            compile_run = await context_governance.get_compile_run(
                workspace_key=workspace_id,
                context_compile_run_id=context_compile_run_id,
            )
            if compile_run is not None:
                return ObservatoryObjectResponse(
                    object=_context_compile_run_admin_record(compile_run)
                )
        if object_type in {"context_budget_event", "context-budget-event"}:
            context_budget_event_id = _uuid_or_404(object_id, "context budget event")
            budget_event = await context_governance.get_budget_event(
                workspace_key=workspace_id,
                context_budget_event_id=context_budget_event_id,
            )
            if budget_event is not None:
                return ObservatoryObjectResponse(
                    object=_context_budget_event_admin_record(budget_event)
                )
        if object_type in {
            "semantic_compression_trial",
            "semantic-compression-trial",
        }:
            semantic_compression_trial_id = _uuid_or_404(
                object_id,
                "semantic compression trial",
            )
            trial = await context_governance.get_semantic_compression_trial(
                workspace_key=workspace_id,
                semantic_compression_trial_id=semantic_compression_trial_id,
            )
            if trial is not None:
                return ObservatoryObjectResponse(
                    object=_semantic_compression_trial_admin_record(trial)
                )
        if object_type in {"llm_invocation", "llm-invocation", "model_invocation"}:
            invocation_id = _uuid_or_404(object_id, "LLM invocation")
            invocation = await llm_invocations.get_invocation(
                workspace_key=workspace_id,
                llm_invocation_id=invocation_id,
            )
            if invocation is not None:
                return ObservatoryObjectResponse(
                    object=_llm_invocation_microscope(invocation)
                )
        if object_type in {"model_profile", "model-profile", "text_model_profile"}:
            profile = await profiles.get_model_profile(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                profile_key=object_id,
            )
            if profile is not None:
                qualification_runs = (
                    await profile_qualifications.list_model_qualification_runs(
                        workspace_key=profile.workspace_key
                        or workspace_id
                        or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                        profile_key=profile.profile_key,
                        limit=25,
                    )
                )
                return ObservatoryObjectResponse(
                    object=_profile_microscope(
                        profile=profile,
                        qualification_runs=qualification_runs,
                        object_type="model_profile",
                    )
                )
        if object_type in {"embedding_profile", "embedding-profile"}:
            profile = await profiles.get_embedding_profile(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                profile_key=object_id,
            )
            if profile is not None:
                qualification_runs = (
                    await profile_qualifications.list_embedding_qualification_runs(
                        workspace_key=profile.workspace_key
                        or workspace_id
                        or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                        profile_key=profile.profile_key,
                        limit=25,
                    )
                )
                return ObservatoryObjectResponse(
                    object=_profile_microscope(
                        profile=profile,
                        qualification_runs=qualification_runs,
                        object_type="embedding_profile",
                    )
                )
        if object_type in {
            "model_profile_qualification_run",
            "model-profile-qualification-run",
            "text_model_qualification_run",
            "profile_qualification_run",
        }:
            qualification_run_id = _uuid_or_404(
                object_id,
                "model profile qualification run",
            )
            run = await profile_qualifications.get_model_qualification_run(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                model_profile_qualification_run_id=qualification_run_id,
            )
            if run is not None:
                return ObservatoryObjectResponse(
                    object=_qualification_run_microscope(
                        run,
                        object_type="model_profile_qualification_run",
                    )
                )
        if object_type in {
            "embedding_profile_qualification_run",
            "embedding-profile-qualification-run",
            "embedding_qualification_run",
        }:
            qualification_run_id = _uuid_or_404(
                object_id,
                "embedding profile qualification run",
            )
            run = await profile_qualifications.get_embedding_qualification_run(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                embedding_profile_qualification_run_id=qualification_run_id,
            )
            if run is not None:
                return ObservatoryObjectResponse(
                    object=_qualification_run_microscope(
                        run,
                        object_type="embedding_profile_qualification_run",
                    )
                )
        if object_type in {"topology_operation", "skill_graph_operation"}:
            operation_id = _uuid_or_404(object_id, "topology operation")
            operation = await topology.get_operation_detail(
                workspace_key=workspace_id,
                skill_graph_operation_id=operation_id,
            )
            if operation is not None:
                return ObservatoryObjectResponse(
                    object=_topology_operation_microscope(operation)
                )
        if object_type in {"evaluation", "evaluation_run", "probe_evaluation"}:
            evaluation_id = _uuid_or_404(object_id, "evaluation")
            listed = [
                evaluation.to_json()
                for evaluation in await evaluations.list_evaluation_reviews(
                    workspace_key=workspace_id,
                    status=None,
                    limit=250,
                )
            ]
            evaluation = _find_by_id(
                listed,
                str(evaluation_id),
                ("evaluation_id", "skill_id", "skill_version_id"),
            )
            if evaluation is not None:
                return ObservatoryObjectResponse(
                    object=_evaluation_microscope(str(evaluation_id), evaluation)
                )
        if object_type in {"memory_quarantine", "quarantined_memory"}:
            quarantine_id = _uuid_or_404(object_id, "memory quarantine")
            memory = await memory_governance.get_memory_quarantine(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                quarantine_id=quarantine_id,
            )
            if memory is not None:
                return ObservatoryObjectResponse(
                    object=_memory_quarantine_admin_record(memory)
                )
        if object_type in {"control_flow_event", "control-flow-event"}:
            event_id = _uuid_or_404(object_id, "control-flow event")
            control_flow_events = await memory_governance.list_control_flow_events(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                limit=500,
            )
            event = next(
                (
                    item
                    for item in control_flow_events
                    if item.control_flow_event_id == event_id
                ),
                None,
            )
            if event is not None:
                return ObservatoryObjectResponse(
                    object=_control_flow_event_admin_record(event)
                )
        if object_type in {"canary_result", "canary-result", "canary"}:
            canary_result_id = _uuid_or_404(object_id, "canary result")
            canary = await lifecycle.get_canary_result(
                workspace_key=workspace_id,
                canary_result_id=canary_result_id,
            )
            if canary is not None:
                return ObservatoryObjectResponse(
                    object=_canary_result_admin_record(canary)
                )
        if object_type in {
            "evolution_transaction",
            "evolution-transaction",
            "transaction",
        }:
            transaction_id = _uuid_or_404(object_id, "evolution transaction")
            transaction = await governance.get_transaction(
                workspace_key=workspace_id,
                evolution_transaction_id=transaction_id,
            )
            if transaction is not None:
                items = await governance.list_transaction_items(
                    evolution_transaction_id=transaction_id,
                )
                return ObservatoryObjectResponse(
                    object=_evolution_transaction_microscope(transaction, items)
                )
        if object_type in {
            "writer_transaction",
            "writer-transaction",
            "writer_manifest",
            "writer-apply",
            "writer_apply",
        }:
            transaction_id = _uuid_or_404(object_id, "writer transaction")
            transaction = await governance.get_transaction(
                workspace_key=workspace_id,
                evolution_transaction_id=transaction_id,
            )
            if transaction is not None:
                items = await governance.list_transaction_items(
                    evolution_transaction_id=transaction_id,
                )
                writer_object = _writer_transaction_microscope(transaction, items)
                if writer_object is not None:
                    return ObservatoryObjectResponse(object=writer_object)
        if object_type in {
            "revocation_request",
            "revocation-request",
            "revocation",
        }:
            revocation_request_id = _uuid_or_404(object_id, "revocation request")
            revocation = await governance.get_revocation_request(
                workspace_key=workspace_id,
                revocation_request_id=revocation_request_id,
            )
            if revocation is not None:
                return ObservatoryObjectResponse(
                    object=_revocation_request_microscope(revocation)
                )
        if object_type in {"trace", "trace_replay", "trace-replay"}:
            trace_id = _uuid_or_404(object_id, "trace")
            spans = await observability.list_trace(
                workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
                trace_id=trace_id,
                limit=500,
            )
            if spans:
                return ObservatoryObjectResponse(
                    object=_trace_detail_microscope(trace_id, spans=spans)
                )
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
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await store.list_events(
            workspace_key=workspace_id,
            event_type=event_type,
            trace_id=trace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="captured_event",
            title="Redacted captured events",
            items=[record.to_json() for record in records],
            limit=limit,
            cursor=cursor,
            source="event_store.list_events",
            diagnostics={
                "supporting_component": "spool_ingest",
                "event_type": event_type,
                "trace_id": str(trace_id) if trace_id else None,
                "raw_payload_available": False,
            },
        )

    @app.get(
        "/admin/api/v1/memory/quarantine",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_memory_quarantine(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        effective_workspace_id = workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID
        records = await memory_governance.list_memory_quarantine(
            workspace_key=effective_workspace_id,
            status=status,
            limit=500,
        )
        return _observatory_collection(
            object_type="memory_quarantine",
            title="Memory quarantine",
            items=[_memory_quarantine_admin_record(record) for record in records],
            limit=limit,
            cursor=cursor,
            source="memory_governance_store.list_memory_quarantine",
            diagnostics={
                "supporting_component": "evidence_memory",
                "filter": {
                    "workspace_id": effective_workspace_id,
                    "status": status,
                },
                "memory_content_returned": False,
            },
        )

    @app.get(
        "/admin/api/v1/memory/quarantine/{quarantine_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_memory_quarantine_detail(
        quarantine_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_quarantine_id = _uuid_or_404(quarantine_id, "memory quarantine")
        memory = await memory_governance.get_memory_quarantine(
            workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
            quarantine_id=parsed_quarantine_id,
        )
        if memory is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="memory quarantine record not found",
            )
        return ObservatoryObjectResponse(object=_memory_quarantine_admin_record(memory))

    @app.get(
        "/admin/api/v1/control-flow/events",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_control_flow_events(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        source_kind: str | None = None,
        influence_kind: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        effective_workspace_id = workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID
        records = await memory_governance.list_control_flow_events(
            workspace_key=effective_workspace_id,
            source_kind=source_kind,
            influence_kind=influence_kind,
            limit=500,
        )
        return _observatory_collection(
            object_type="control_flow_event",
            title="Control-flow integrity events",
            items=[_control_flow_event_admin_record(record) for record in records],
            limit=limit,
            cursor=cursor,
            source="memory_governance_store.list_control_flow_events",
            diagnostics={
                "supporting_component": "evidence_memory",
                "filter": {
                    "workspace_id": effective_workspace_id,
                    "source_kind": source_kind,
                    "influence_kind": influence_kind,
                },
                "content_safe_decisions_only": True,
            },
        )

    @app.get(
        "/admin/api/v1/control-flow/events/{control_flow_event_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_control_flow_event_detail(
        control_flow_event_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_event_id = _uuid_or_404(control_flow_event_id, "control-flow event")
        records = await memory_governance.list_control_flow_events(
            workspace_key=workspace_id or DEFAULT_OBSERVATORY_WORKSPACE_ID,
            limit=500,
        )
        event = next(
            (record for record in records if record.control_flow_event_id == parsed_event_id),
            None,
        )
        if event is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="control-flow event not found",
            )
        return ObservatoryObjectResponse(object=_control_flow_event_admin_record(event))

    @app.get(
        "/admin/api/v1/canary/results",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_canary_results(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        skill_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        records = await lifecycle.list_canary_results(
            workspace_key=workspace_id,
            skill_id=skill_id,
            status=status,
            limit=500,
        )
        return _observatory_collection(
            object_type="canary_result",
            title="Canary results",
            items=[_canary_result_admin_record(record) for record in records],
            limit=limit,
            cursor=cursor,
            source="lifecycle_store.list_canary_results",
            diagnostics={
                "supporting_component": "canary_rollback_freeze",
                "filter": {
                    "workspace_id": workspace_id,
                    "skill_id": str(skill_id) if skill_id else None,
                    "status": status,
                },
                "raw_metrics_returned": False,
                "raw_reason_returned": False,
            },
        )

    @app.get(
        "/admin/api/v1/canary/results/{canary_result_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_canary_result_detail(
        canary_result_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_canary_result_id = _uuid_or_404(canary_result_id, "canary result")
        canary = await lifecycle.get_canary_result(
            workspace_key=workspace_id,
            canary_result_id=parsed_canary_result_id,
        )
        if canary is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="canary result not found",
            )
        return ObservatoryObjectResponse(object=_canary_result_admin_record(canary))

    @app.get("/admin/api/v1/traces", response_model=ObservatoryCollectionResponse)
    async def observatory_traces(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        traces = await observability.list_traces(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="trace",
            title="Trace search",
            items=[trace.to_json() for trace in traces],
            limit=limit,
            cursor=cursor,
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
            object=_trace_detail_microscope(trace_id, spans=spans)
        )

    @app.get("/admin/api/v1/jobs", response_model=ObservatoryCollectionResponse)
    async def observatory_jobs(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        status_filter: Annotated[str | None, Query(alias="status")] = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await jobs.list_jobs(status=status_filter, limit=250)
        return _observatory_collection(
            object_type="job",
            title="Sidecar jobs",
            items=[job.to_json() for job in listed],
            limit=limit,
            cursor=cursor,
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
        return ObservatoryObjectResponse(object=_job_microscope(job_id, job))

    @app.get("/admin/api/v1/schedules", response_model=ObservatoryCollectionResponse)
    async def observatory_schedules(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await scheduler.list_schedules(limit=250)
        return _observatory_collection(
            object_type="schedule",
            title="Sidecar schedules",
            items=[_schedule_admin_record(schedule.to_json()) for schedule in listed],
            limit=limit,
            cursor=cursor,
            source="scheduler_store.list_schedules",
            diagnostics={
                "supporting_component": "scheduler_jobs",
                "payload_available": False,
                "payload_redaction": "metadata-only",
            },
        )

    @app.get("/admin/api/v1/skills", response_model=ObservatoryCollectionResponse)
    async def observatory_skills(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await skills.list_skills(
            workspace_key=workspace_id,
            lifecycle_state=lifecycle_state,
            limit=500,
        )
        return _observatory_collection(
            object_type="skill",
            title="Skill library",
            items=[skill.to_json() for skill in listed],
            limit=limit,
            cursor=cursor,
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
        return ObservatoryObjectResponse(object=_skill_microscope(skill_id, skill))

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
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = [
            skill.to_json()
            for skill in await skills.list_skills(
                workspace_key=workspace_id,
                lifecycle_state=None,
                limit=500,
            )
        ]
        skill = _find_by_id(listed, version_id or skill_id, ("active_version_id",))
        return ObservatoryObjectResponse(
            object=_skill_microscope(
                version_id or skill_id,
                skill,
                object_type="skill_version",
            )
        )

    @app.get("/admin/api/v1/topology", response_model=ObservatoryObjectResponse)
    async def observatory_topology(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 25,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        snapshot = await _observatory_snapshot(
            workspace_id=workspace_id,
            window_minutes=window_minutes,
        )
        topology_metrics = await topology.metrics(
            workspace_key=workspace_id,
            limit=max(1, min(limit, 100)),
        )
        topology_transactions = await governance.list_transactions(
            workspace_key=workspace_id,
            transaction_kind_prefix="topology_",
            limit=max(1, min(limit, 100)),
        )
        return ObservatoryObjectResponse(
            object={
                "schema_version": "skillkernel.observatory.topology.v1",
                "object_type": "skill_topology",
                "object_id": "current",
                "title": "Skill topology",
                "summary": (
                    "Current topology-related stations, flow edges, operation "
                    "states, and planned trial signals."
                ),
                "read_model": {
                    "source": "topology_store.metrics+governance.evolution_transactions.metrics",
                    "workspace_id": workspace_id,
                    "window_minutes": window_minutes,
                    "recent_operation_limit": max(1, min(limit, 100)),
                    "recent_transaction_limit": max(1, min(limit, 100)),
                    "data_quality": "content-safe-derived",
                },
                "operation_metrics": topology_metrics,
                "transaction_review": _topology_transaction_review(
                    topology_transactions
                ),
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

    @app.get(
        "/admin/api/v1/topology/operations/{operation_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_topology_operation_detail(
        operation_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_operation_id = _uuid_or_404(operation_id, "topology operation")
        operation = await topology.get_operation_detail(
            workspace_key=workspace_id,
            skill_graph_operation_id=parsed_operation_id,
        )
        if operation is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="topology operation not found",
            )
        return ObservatoryObjectResponse(
            object=_topology_operation_microscope(operation)
        )

    @app.get("/admin/api/v1/candidates", response_model=ObservatoryCollectionResponse)
    async def observatory_candidates(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        lifecycle_state: str | None = "candidate",
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await candidates.list_candidate_reviews(
            workspace_key=workspace_id,
            lifecycle_state=lifecycle_state,
            limit=250,
        )
        return _observatory_collection(
            object_type="candidate",
            title="Candidate reviews",
            items=[candidate.to_json() for candidate in listed],
            limit=limit,
            cursor=cursor,
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
            object=_candidate_microscope(candidate_id, candidate)
        )

    @app.get("/admin/api/v1/evaluations", response_model=ObservatoryCollectionResponse)
    async def observatory_evaluations(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await evaluations.list_evaluation_reviews(
            workspace_key=workspace_id,
            status=status,
            limit=250,
        )
        return _observatory_collection(
            object_type="evaluation",
            title="Evaluation reviews",
            items=[evaluation.to_json() for evaluation in listed],
            limit=limit,
            cursor=cursor,
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
            object=_evaluation_microscope(evaluation_id, evaluation)
        )

    @app.get("/admin/api/v1/scanner-findings", response_model=ObservatoryCollectionResponse)
    async def observatory_scanner_findings(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        window_minutes: int = 60,
        limit: int = 50,
        cursor: str | None = None,
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
            cursor=cursor,
            source="observatory_snapshot.scanner_security.records",
            diagnostics=scanner
            or _missing_read_model("scanner_finding", supporting_component="scanner_security"),
        )

    @app.get(
        "/admin/api/v1/scanner-findings/{finding_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_scanner_finding_detail(
        finding_id: str,
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
                object_type="scanner_finding",
                object_id=finding_id,
            )
        )

    @app.get("/admin/api/v1/artifacts/{artifact_id}", response_model=ObservatoryObjectResponse)
    async def observatory_artifact_detail(
        artifact_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        with suppress(ValueError):
            context_artifact_id = UUID(artifact_id)
            artifact = await context_governance.get_artifact(
                workspace_key=workspace_id,
                context_artifact_id=context_artifact_id,
            )
            if artifact is not None:
                return ObservatoryObjectResponse(
                    object=_context_artifact_admin_record(artifact)
                )
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
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        sources = await historical_import.list_sources(
            workspace_key=workspace_id,
            status=status,
            limit=250,
        )
        return _observatory_collection(
            object_type="historical_import_source",
            title="Historical import sources",
            items=[_historical_import_source_admin_record(source) for source in sources],
            limit=limit,
            cursor=cursor,
            source="historical_import_store.list_sources",
            diagnostics={
                "supporting_component": "historical_ingestion",
                "source_key_returned": False,
                "metadata_values_returned": False,
                "raw_content_returned": False,
            },
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
        if source is not None:
            return ObservatoryObjectResponse(
                object=_historical_import_source_admin_record(
                    source,
                    requested_id=historical_import_id,
                )
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
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        logs = await retrieval.list_recent_logs(
            workspace_key=workspace_id,
            limit=500,
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
            cursor=cursor,
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
        return ObservatoryObjectResponse(object=_broker_decision_microscope(log))

    @app.get(
        "/admin/api/v1/broker/replay-episodes",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_broker_replay_episodes(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        tags: Annotated[list[str] | None, Query()] = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        effective_workspace_id = (
            workspace_id
            or os.environ.get("AUTOSKILL_WORKSPACE_ID")
            or DEFAULT_OBSERVATORY_WORKSPACE_ID
        )
        episodes = await broker_policies.list_replay_episodes(
            workspace_key=effective_workspace_id,
            tags=tags or [],
            limit=500,
        )
        return _observatory_collection(
            object_type="broker_replay_episode",
            title="Broker replay corpus",
            items=[
                {
                    **episode.to_json(),
                    "object_id": str(episode.broker_replay_episode_id),
                    "object_type": "broker_replay_episode",
                    "title": f"Broker replay episode {episode.episode_key}",
                    "summary": (
                        f"{episode.expected_decision or 'decision-unspecified'}; "
                        f"expected_skills={len(episode.expected_skill_ids)}; "
                        f"tags={len(episode.tags)}"
                    ),
                    "content_policy": {
                        "raw_available": False,
                        "raw_reason": "raw-content-disabled",
                        "raw_prompt_stored": False,
                        "redaction_state": "operator_redacted_replay_intent",
                    },
                    "details_url": (
                        "/admin/broker/replay-episodes/"
                        f"{episode.broker_replay_episode_id}"
                    ),
                }
                for episode in episodes
            ],
            limit=limit,
            cursor=cursor,
            source="broker_policy_store.list_replay_episodes",
            diagnostics={
                "supporting_component": "broker_runtime",
                "workspace_id": effective_workspace_id,
                "tags": tags or [],
                "raw_prompt_stored": False,
            },
        )

    @app.get(
        "/admin/api/v1/broker/replay-episodes/{episode_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_broker_replay_episode_detail(
        episode_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        episode_uuid = _uuid_or_404(episode_id, "broker replay episode")
        episode = await broker_policies.get_replay_episode(
            workspace_key=workspace_id,
            broker_replay_episode_id=episode_uuid,
        )
        if episode is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="broker replay episode not found",
            )
        return ObservatoryObjectResponse(
            object=_broker_replay_episode_microscope(episode)
        )

    @app.get("/admin/api/v1/context/artifacts", response_model=ObservatoryCollectionResponse)
    async def observatory_context_artifacts(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        artifacts = await context_governance.list_artifacts(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="context_artifact",
            title="Context artifacts",
            items=[_context_artifact_admin_record(artifact) for artifact in artifacts],
            limit=limit,
            cursor=cursor,
            source="context_governance_store.list_artifacts",
            diagnostics={
                "supporting_component": "context_compiler",
                "raw_text_returned": False,
                "workspace_id": workspace_id,
            },
        )

    @app.get(
        "/admin/api/v1/context/artifacts/{artifact_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_context_artifact_detail(
        artifact_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        context_artifact_id = _uuid_or_404(artifact_id, "context artifact")
        artifact = await context_governance.get_artifact(
            context_artifact_id=context_artifact_id,
            workspace_key=workspace_id,
        )
        if artifact is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="context artifact not found",
            )
        return ObservatoryObjectResponse(
            object=_context_artifact_admin_record(artifact)
        )

    @app.get(
        "/admin/api/v1/context/compile-runs",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_context_compile_runs(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        runs = await context_governance.list_compile_runs(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="context_compile_run",
            title="Context compile runs",
            items=[_context_compile_run_admin_record(run) for run in runs],
            limit=limit,
            cursor=cursor,
            source="context_governance_store.list_compile_runs",
            diagnostics={
                "supporting_component": "context_compiler",
                "skillir_returned": False,
                "compiled_text_returned": False,
                "workspace_id": workspace_id,
            },
        )

    @app.get(
        "/admin/api/v1/context/compile-runs/{run_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_context_compile_run_detail(
        run_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        context_compile_run_id = _uuid_or_404(run_id, "context compile run")
        run = await context_governance.get_compile_run(
            context_compile_run_id=context_compile_run_id,
            workspace_key=workspace_id,
        )
        if run is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="context compile run not found",
            )
        return ObservatoryObjectResponse(
            object=_context_compile_run_admin_record(run)
        )

    @app.get(
        "/admin/api/v1/context/budget-events",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_context_budget_events(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        events = await context_governance.list_budget_events(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="context_budget_event",
            title="Context budget events",
            items=[_context_budget_event_admin_record(event) for event in events],
            limit=limit,
            cursor=cursor,
            source="context_governance_store.list_budget_events",
            diagnostics={
                "supporting_component": "context_compiler",
                "evidence_payload_returned": False,
                "workspace_id": workspace_id,
            },
        )

    @app.get(
        "/admin/api/v1/context/budget-events/{event_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_context_budget_event_detail(
        event_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        context_budget_event_id = _uuid_or_404(event_id, "context budget event")
        event = await context_governance.get_budget_event(
            context_budget_event_id=context_budget_event_id,
            workspace_key=workspace_id,
        )
        if event is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="context budget event not found",
            )
        return ObservatoryObjectResponse(
            object=_context_budget_event_admin_record(event)
        )

    @app.get(
        "/admin/api/v1/context/compression-trials",
        response_model=ObservatoryCollectionResponse,
    )
    async def observatory_context_compression_trials(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        trials = await context_governance.list_semantic_compression_trials(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="semantic_compression_trial",
            title="Semantic compression trials",
            items=[
                _semantic_compression_trial_admin_record(trial)
                for trial in trials
            ],
            limit=limit,
            cursor=cursor,
            source="context_governance_store.list_semantic_compression_trials",
            diagnostics={
                "supporting_component": "context_compiler",
                "artifact_text_returned": False,
                "workspace_id": workspace_id,
            },
        )

    @app.get(
        "/admin/api/v1/context/compression-trials/{trial_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_context_compression_trial_detail(
        trial_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        semantic_compression_trial_id = _uuid_or_404(
            trial_id,
            "semantic compression trial",
        )
        trial = await context_governance.get_semantic_compression_trial(
            semantic_compression_trial_id=semantic_compression_trial_id,
            workspace_key=workspace_id,
        )
        if trial is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="semantic compression trial not found",
            )
        return ObservatoryObjectResponse(
            object=_semantic_compression_trial_admin_record(trial)
        )

    @app.get("/admin/api/v1/model-profile", response_model=ObservatoryCollectionResponse)
    async def observatory_model_profile(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await profiles.list_model_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=500,
        )
        return _observatory_collection(
            object_type="model_profile",
            title="Text model profiles",
            items=[profile.to_json() for profile in listed],
            limit=limit,
            cursor=cursor,
            source="profile_store.list_model_profiles",
        )

    @app.get(
        "/admin/api/v1/model-profile/{profile_key}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_model_profile_detail(
        profile_key: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        limit: int = 25,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        profile = await profiles.get_model_profile(
            workspace_key=workspace_id,
            profile_key=profile_key,
        )
        if profile is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="model profile not found",
            )
        qualification_runs = await profile_qualifications.list_model_qualification_runs(
            workspace_key=workspace_id,
            profile_key=profile.profile_key,
            limit=max(1, min(limit, 100)),
        )
        return ObservatoryObjectResponse(
            object=_profile_microscope(
                profile=profile,
                qualification_runs=qualification_runs,
                object_type="model_profile",
            )
        )

    @app.get("/admin/api/v1/embedding-profile", response_model=ObservatoryCollectionResponse)
    async def observatory_embedding_profile(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        listed = await profiles.list_embedding_profiles(
            workspace_key=workspace_id,
            status=status,
            limit=500,
        )
        return _observatory_collection(
            object_type="embedding_profile",
            title="Embedding profiles",
            items=[profile.to_json() for profile in listed],
            limit=limit,
            cursor=cursor,
            source="profile_store.list_embedding_profiles",
        )

    @app.get(
        "/admin/api/v1/embedding-profile/{profile_key}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_embedding_profile_detail(
        profile_key: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str = "default",
        limit: int = 25,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        profile = await profiles.get_embedding_profile(
            workspace_key=workspace_id,
            profile_key=profile_key,
        )
        if profile is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="embedding profile not found",
            )
        qualification_runs = (
            await profile_qualifications.list_embedding_qualification_runs(
                workspace_key=workspace_id,
                profile_key=profile.profile_key,
                limit=max(1, min(limit, 100)),
            )
        )
        return ObservatoryObjectResponse(
            object=_profile_microscope(
                profile=profile,
                qualification_runs=qualification_runs,
                object_type="embedding_profile",
            )
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
        return ObservatoryObjectResponse(object=storage_microscope(snapshot))

    @app.get("/admin/api/v1/audit", response_model=ObservatoryCollectionResponse)
    async def observatory_audit(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        bounded_limit = max(1, min(limit, 500))
        records = await audit.list_recent(workspace_key=workspace_id, limit=500)
        return _observatory_collection(
            object_type="audit_record",
            title="Audit trail",
            items=[record.model_dump(mode="json") for record in records],
            limit=bounded_limit,
            cursor=cursor,
            source="audit_store.list_recent",
            diagnostics={
                "chain_valid": await audit.verify_chain(
                    workspace_key=workspace_id,
                    limit=bounded_limit,
                )
            },
        )

    @app.get("/admin/api/v1/actions/audit", response_model=ObservatoryCollectionResponse)
    async def observatory_action_audits(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        actor_id: str | None = None,
        action_kind: str | None = None,
        result: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        action_audits = await observatory_admin.list_action_audits(
            workspace_key=workspace_id,
            actor_id=actor_id,
            action_kind=action_kind,
            result=result,
            limit=500,
        )
        return _observatory_collection(
            object_type="admin_action",
            title="Operator action audit",
            items=[_admin_action_microscope(action) for action in action_audits],
            limit=limit,
            cursor=cursor,
            source="observatory_admin_store.list_action_audits",
            diagnostics={
                "supporting_component": "operator_action_gateway",
                "raw_content_available": False,
                "filter": {
                    "workspace_id": workspace_id,
                    "actor_id": actor_id,
                    "action_kind": action_kind,
                    "result": result,
                },
            },
        )

    @app.get("/admin/api/v1/actions/summary", response_model=ObservatoryObjectResponse)
    async def observatory_action_gateway_summary(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 500,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        bounded_limit = max(1, min(limit, 500))
        action_audits = await observatory_admin.list_action_audits(
            workspace_key=workspace_id,
            limit=bounded_limit,
        )
        return ObservatoryObjectResponse(
            object=_admin_action_gateway_summary(
                action_audits,
                workspace_id=workspace_id,
                limit=bounded_limit,
            )
        )

    @app.get(
        "/admin/api/v1/actions/audit/{action_id}",
        response_model=ObservatoryObjectResponse,
    )
    async def observatory_action_audit_detail(
        action_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
    ) -> ObservatoryObjectResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        parsed_action_id = _uuid_or_404(action_id, "operator action")
        action = await observatory_admin.get_action_audit(action_id=parsed_action_id)
        if action is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="operator action not found",
            )
        return ObservatoryObjectResponse(object=_admin_action_microscope(action))

    @app.get("/admin/api/v1/comparisons", response_model=ObservatoryCollectionResponse)
    async def observatory_comparisons(
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ObservatoryCollectionResponse:
        _require_admin_auth(authorization, x_skillkernel_roles)
        comparisons = await observatory_admin.list_comparisons(
            workspace_key=workspace_id,
            limit=500,
        )
        return _observatory_collection(
            object_type="baseline_comparison",
            title="Saved baseline comparisons",
            items=[comparison.to_json() for comparison in comparisons],
            limit=limit,
            cursor=cursor,
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
        await observatory_admin.append_live_event(
            kind="read_model_invalidated",
            component_id="observatory_admin",
            object_type="baseline_comparison",
            object_id=str(comparison.comparison_id),
            payload={
                "workspace_id": workspace_key,
                "comparison_kind": comparison.comparison_kind,
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
        live_event = await observatory_admin.append_live_event(
            kind="audit_record_appended",
            component_id="observatory_admin",
            object_type="diagnostic_bundle",
            object_id=str(bundle.bundle_id),
            payload={
                "workspace_id": workspace_id,
                "audit_id": str(audit_record.audit_id),
                "bundle_id": str(bundle.bundle_id),
                "redaction_level": bundle.redaction_level,
            },
        )
        payload = bundle.to_json()
        payload["audit"] = audit_record.model_dump(mode="json")
        payload["live_event"] = live_event.to_json()
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
            object=_trace_replay_object(
                trace_id=trace_id,
                workspace_id=workspace_id,
                spans=spans,
            )
        )

    @app.post("/admin/api/v1/actions", response_model=ObservatoryActionResponse)
    async def observatory_action(
        http_request: Request,
        request: ObservatoryActionRequest,
        authorization: Annotated[str | None, Header()] = None,
        x_skillkernel_roles: Annotated[str | None, Header(alias="X-SkillKernel-Roles")] = None,
        x_skillkernel_csrf: Annotated[str | None, Header(alias=ADMIN_CSRF_HEADER)] = None,
    ) -> ObservatoryActionResponse:
        return await _record_observatory_action(
            request,
            authorization,
            x_skillkernel_roles,
            http_request=http_request,
            csrf_token=x_skillkernel_csrf,
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
        last_outbox_seq = (
            int(last_seq_param) if last_seq_param and last_seq_param.isdigit() else None
        )
        last_outbox_seq = await _observatory_starting_outbox_seq(last_outbox_seq)
        last_snapshot_seq: int | None = None
        try:
            while True:
                live_events = await observatory_admin.list_live_events(
                    after_seq=last_outbox_seq,
                    limit=50,
                )
                if live_events:
                    for live_event in live_events:
                        payload = live_event.to_json()
                        payload["cursor_seq"] = live_event.seq
                        await websocket.send_json(payload)
                        last_outbox_seq = live_event.seq
                else:
                    snapshot = await _observatory_snapshot(
                        workspace_id=workspace_id,
                        window_minutes=60,
                    )
                    payload = _snapshot_live_fallback(
                        snapshot,
                        last_seq=last_snapshot_seq,
                        cursor_seq=last_outbox_seq,
                    )
                    await websocket.send_json(payload)
                    last_snapshot_seq = int(payload["seq"])
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
            current_last_outbox_seq = await _observatory_starting_outbox_seq(last_seq)
            current_last_snapshot_seq: int | None = None
            snapshot = await _observatory_snapshot(
                workspace_id=workspace_id,
                window_minutes=60,
            )
            payload = _snapshot_live_fallback(
                snapshot,
                last_seq=current_last_snapshot_seq,
                cursor_seq=current_last_outbox_seq,
            )
            yield f"event: {payload['event_type']}\n"
            yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
            current_last_snapshot_seq = int(payload["seq"])
            while True:
                live_events = await observatory_admin.list_live_events(
                    after_seq=current_last_outbox_seq,
                    limit=50,
                )
                if live_events:
                    for live_event in live_events:
                        payload = live_event.to_json()
                        payload["cursor_seq"] = live_event.seq
                        yield f"event: {payload['event_type']}\n"
                        yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
                        current_last_outbox_seq = live_event.seq
                else:
                    snapshot = await _observatory_snapshot(
                        workspace_id=workspace_id,
                        window_minutes=60,
                    )
                    payload = _snapshot_live_fallback(
                        snapshot,
                        last_seq=current_last_snapshot_seq,
                        cursor_seq=current_last_outbox_seq,
                    )
                    yield f"event: {payload['event_type']}\n"
                    yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
                    current_last_snapshot_seq = int(payload["seq"])
                await asyncio.sleep(5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers=NO_STORE_HEADERS,
        )

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

    # Some existing unit tests inspect app.routes directly and assume every
    # route-like object has .methods. Starlette WebSocket and Mount routes do
    # not need it at runtime, but setting it keeps those tests focused on the
    # route they are exercising.
    for route in app.routes:
        if not hasattr(route, "methods"):
            route.methods = {"WEBSOCKET"} if route.path == "/admin/live" else {"GET"}

    return app
