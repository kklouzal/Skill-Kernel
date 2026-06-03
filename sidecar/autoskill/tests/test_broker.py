import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from autoskill.api.app import create_app
from autoskill.core.config import get_settings
from autoskill.db.memory import NullMemoryGovernanceStore
from autoskill.db.profiles import ModelProfileRecord
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.broker import (
    BrokerPolicy,
    BrokerReplayEpisode,
    ContextHintCache,
    ContextHintRequest,
    build_context_hint,
    evaluate_broker_canary_feedback,
    replay_broker_policy,
)
from autoskill.services.embedding_generation import HashingTextEmbedder


class MemoryBrokerRetrievalStore:
    def __init__(
        self,
        candidates: list[RetrievalCandidate],
        graph_candidates: list[RetrievalCandidate] | None = None,
        semantic_candidates: list[RetrievalCandidate] | None = None,
    ) -> None:
        self.candidates = candidates
        self.graph_candidates = graph_candidates or []
        self.semantic_candidates = semantic_candidates or []
        self.calls: list[dict[str, object]] = []
        self.semantic_calls: list[dict[str, object]] = []
        self.graph_calls: list[dict[str, object]] = []
        self.records: list[dict[str, object]] = []

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id=None,
        span_id=None,
        parent_span_id=None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "query": query,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "limit": limit,
            }
        )
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if self.candidates else "no_candidates",
            candidates=self.candidates,
        )

    async def semantic_query(
        self,
        *,
        workspace_key: str,
        embedding_model: str,
        embedding: list[float],
        embedding_profile_id=None,
        trace_id=None,
        span_id=None,
        parent_span_id=None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.semantic_calls.append(
            {
                "workspace_key": workspace_key,
                "embedding_model": embedding_model,
                "embedding": embedding,
                "embedding_profile_id": embedding_profile_id,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "limit": limit,
            }
        )
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision=(
                "semantic_candidates_found"
                if self.semantic_candidates
                else "semantic_no_candidates"
            ),
            candidates=self.semantic_candidates,
        )

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list,
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        self.graph_calls.append(
            {
                "workspace_key": workspace_key,
                "skill_ids": skill_ids,
                "edge_kinds": edge_kinds,
                "limit": limit,
            }
        )
        return self.graph_candidates[:limit]

    async def record_context_hint(
        self,
        *,
        retrieval_log_id,
        rendered_skill_ids: list,
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
        metadata: dict[str, object] | None = None,
        broker_policy_version_id=None,
    ) -> None:
        self.records.append(
            {
                "retrieval_log_id": retrieval_log_id,
                "rendered_skill_ids": rendered_skill_ids,
                "decision": decision,
                "suppressed": suppressed,
                "reason_codes": reason_codes,
                "metadata": metadata or {},
                "broker_policy_version_id": broker_policy_version_id,
            }
        )


class MemoryContextGovernanceStore:
    def __init__(self) -> None:
        self.artifacts: list[dict[str, object]] = []
        self.ledgers: list[dict[str, object]] = []

    async def record_artifact(self, **kwargs):
        artifact_id = uuid4()
        self.artifacts.append(kwargs | {"context_artifact_id": artifact_id})
        return SimpleNamespace(
            context_artifact_id=artifact_id,
            token_count=max(1, (len(str(kwargs["text"])) + 3) // 4),
        )

    async def record_token_ledger(self, **kwargs):
        self.ledgers.append(kwargs)
        return SimpleNamespace(context_token_ledger_id=uuid4())


class MemoryCompatibilityStore:
    def __init__(self, statuses: dict[tuple[object, object], str]) -> None:
        self.statuses = statuses
        self.calls: list[dict[str, object]] = []

    async def list_statuses(
        self,
        *,
        workspace_key: str,
        executor_profile_id,
        skill_version_ids: list,
    ) -> dict:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "executor_profile_id": executor_profile_id,
                "skill_version_ids": skill_version_ids,
            }
        )
        return {
            skill_version_id: status
            for skill_version_id in skill_version_ids
            if (
                status := self.statuses.get((skill_version_id, executor_profile_id))
            )
            is not None
        }


class MemoryBrokerProfileStore:
    def __init__(self, active_embedding_profile=None) -> None:
        self.active_embedding_profile = active_embedding_profile
        self.calls: list[dict[str, object]] = []

    async def get_active_embedding_profile(self, *, workspace_key: str):
        self.calls.append({"workspace_key": workspace_key})
        return self.active_embedding_profile


def _embedding_profile(*, embedding_dim: int = 8) -> ModelProfileRecord:
    now = datetime.now(UTC)
    return ModelProfileRecord(
        profile_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        profile_key="runtime-hash",
        provider="test-provider",
        model="runtime-hash-model",
        route_kind="hash",
        endpoint_ref=None,
        timeout_seconds=30.0,
        status="active",
        qualification={"verdict": "qualified"},
        kind="embedding",
        embedding_dim=embedding_dim,
        thinking_level="off",
        thinking_fallback_policy="omit",
        created_at=now,
        updated_at=now,
    )


def test_context_broker_renders_scanned_skill_candidates() -> None:
    skill_id = uuid4()
    trace_id = uuid4()
    span_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="Duplicate body for the same skill should be suppressed.",
                rank=0.8,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    context = MemoryContextGovernanceStore()

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                trace_id=trace_id,
                span_id=span_id,
                session_id="session-1",
                turn_id="turn-1",
                user_intent="repair pdf table extraction",
                max_tokens=120,
            ),
            context_governance=context,
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert response.skill_ids == [str(skill_id)]
    assert "AutoSkill broker hint" in response.hint
    assert "PDF tables" in response.hint
    assert "pdf-table-repair" in response.hint
    assert response.suppressed[0]["reason"] == "duplicate-skill"
    assert "exact-rerank" in response.reason_codes
    assert store.calls[0]["limit"] == 8
    assert store.calls[0]["trace_id"] == trace_id
    assert store.calls[0]["span_id"] == span_id
    assert store.graph_calls[0]["limit"] == 12
    assert store.records[0]["decision"] == "skill_hint"
    assert store.records[0]["rendered_skill_ids"] == [skill_id]
    bundle_scan = store.records[0]["metadata"]["bundle_scan"]
    assert bundle_scan["status"] == "passed"
    assert bundle_scan["blocking"] is False
    assert bundle_scan["selected_skill_ids"] == [str(skill_id)]
    assert bundle_scan["bundle_hash"]
    assert context.artifacts[0]["artifact_kind"] == "broker_hint"
    assert context.artifacts[0]["source_object_type"] == "retrieval_log"
    assert context.artifacts[0]["max_tokens"] == 120
    assert context.artifacts[0]["metadata"]["bundle_scan"]["status"] == "passed"
    assert context.ledgers[0]["visibility_state"] == "skill_visible"
    assert context.ledgers[0]["context_artifact_id"] == context.artifacts[0]["context_artifact_id"]
    assert context.ledgers[0]["metadata"]["bundle_scan"]["bundle_hash"] == (
        bundle_scan["bundle_hash"]
    )


def test_context_broker_records_memory_control_flow_without_injecting_memory() -> None:
    skill_id = uuid4()
    evidence_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN logs need triage, use the deterministic incident summary skill.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "incident-summary",
                },
            )
        ]
    )
    memory = NullMemoryGovernanceStore()

    async def run():
        quarantined = await memory.quarantine_memory(
            workspace_key="dev-01",
            source_object_type="evidence",
            source_object_id=evidence_id,
            proposed_memory={
                "summary": "Private operator preference that must not be injected."
            },
            taint={"source": "derived"},
            scanner_findings={"status": "passed"},
        )
        approved = await memory.decide_memory_quarantine(
            workspace_key="dev-01",
            quarantine_id=quarantined.quarantine_id,
            status="approved",
            operator_id="operator",
            rationale="bounded test approval",
        )
        response = await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="summarize the incident logs",
                memory_influence_ids=[approved.quarantine_id],
                memory_influence_run_id="broker-run-1",
                max_tokens=120,
            ),
            memory_governance=memory,
        )
        return approved, response

    approved, response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert "Private operator preference" not in response.hint
    assert len(memory.control_flow_events) == 1
    event = memory.control_flow_events[0]
    assert event.source_kind == "memory"
    assert event.source_id == approved.quarantine_id
    assert event.influence_kind == "retrieval"
    assert event.run_id == "broker-run-1"
    assert event.decision["control_surface"] == "runtime_context_broker"
    assert event.decision["decision"] == "skill_hint"
    assert event.decision["rendered_skill_ids"] == [str(skill_id)]
    assert "exact-rerank" in event.decision["reason_codes"]
    assert "Private operator preference" not in str(event.decision)


def test_context_broker_blocks_unapproved_memory_before_retrieval() -> None:
    evidence_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="WHEN logs need triage, use the deterministic incident summary skill.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "incident-summary",
                },
            )
        ]
    )
    memory = NullMemoryGovernanceStore()

    async def run():
        pending = await memory.quarantine_memory(
            workspace_key="dev-01",
            source_object_type="evidence",
            source_object_id=evidence_id,
            proposed_memory={"summary": "Unapproved memory must not steer retrieval."},
            taint={"source": "derived"},
            scanner_findings={"status": "passed"},
        )
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="summarize the incident logs",
                memory_influence_ids=[pending.quarantine_id],
                memory_influence_run_id="broker-run-2",
            ),
            memory_governance=memory,
        )

    response = asyncio.run(run())

    assert response.decision == "no_skill"
    assert response.cache_status == "memory-influence-blocked"
    assert response.reason_codes == ["memory-influence-not-approved"]
    assert store.calls == []
    assert len(memory.control_flow_events) == 1
    event = memory.control_flow_events[0]
    assert event.decision["decision"] == "blocked_memory_influence"
    assert event.decision["memory_status"] == "pending"
    assert event.run_id == "broker-run-2"
    assert "Unapproved memory" not in str(event.decision)


def test_context_broker_blocks_memory_influence_without_governance_store() -> None:
    store = MemoryBrokerRetrievalStore([])

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="summarize the incident logs",
                memory_influence_ids=[uuid4()],
            ),
            memory_governance=None,
        )

    response = asyncio.run(run())

    assert response.decision == "no_skill"
    assert response.cache_status == "memory-governance-unavailable"
    assert response.reason_codes == ["memory-governance-unavailable"]
    assert store.calls == []


def test_context_broker_can_render_vector_fused_candidates_when_lexical_is_empty() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [],
        semantic_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN diagrams have tiny labels, use the accessibility repair skill.",
                rank=0.88,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "diagram-accessibility-repair",
                    "retrieval_mode": "vector",
                    "semantic_distance": 0.12,
                },
            )
        ],
    )
    embedder = HashingTextEmbedder(model="test-hash", embedding_dim=8)

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="fix unreadable figure labels",
                max_tokens=120,
            ),
            semantic_embedder=embedder,
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert response.skill_ids == [str(skill_id)]
    assert "vector-fused" in response.reason_codes
    assert store.calls[0]["query"] == "fix unreadable figure labels"
    assert store.semantic_calls[0]["embedding_model"] == "test-hash"
    assert len(store.semantic_calls[0]["embedding"]) == 8


def test_context_hint_route_uses_active_embedding_profile_for_semantic_retrieval(
    monkeypatch,
) -> None:
    skill_id = uuid4()
    profile = _embedding_profile()
    store = MemoryBrokerRetrievalStore(
        [],
        semantic_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN diagrams have unreadable labels, repair accessibility annotations.",
                rank=0.91,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "diagram-accessibility",
                    "retrieval_mode": "vector",
                },
            )
        ],
    )
    profiles = MemoryBrokerProfileStore(active_embedding_profile=profile)
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED", "true")
    get_settings.cache_clear()
    app = create_app(retrieval_store=store, profile_store=profiles)
    route = next(route for route in app.routes if route.path == "/v1/runtime/context-hint")

    async def run():
        return await route.endpoint(
            request=ContextHintRequest(
                workspace_id="dev-01",
                user_intent="fix unreadable labels in a generated diagram",
                max_tokens=120,
            )
        )

    try:
        response = asyncio.run(run())
    finally:
        get_settings.cache_clear()

    assert response.decision == "skill_hint"
    assert response.skill_ids == [str(skill_id)]
    assert "vector-fused" in response.reason_codes
    assert profiles.calls == [{"workspace_key": "dev-01"}]
    assert store.semantic_calls[0]["embedding_model"] == "runtime-hash-model"
    assert store.semantic_calls[0]["embedding_profile_id"] == profile.profile_id


def test_context_broker_suppresses_executor_blocked_skill_version() -> None:
    skill_id = uuid4()
    skill_version_id = uuid4()
    executor_profile_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                    "skill_version_id": str(skill_version_id),
                },
            )
        ]
    )
    compatibility = MemoryCompatibilityStore(
        {(skill_version_id, executor_profile_id): "blocked"}
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                executor_profile_id=executor_profile_id,
                user_intent="repair pdf table extraction",
            ),
            compatibility=compatibility,
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.suppressed[0]["reason"] == "executor-blocked"
    assert compatibility.calls[0]["skill_version_ids"] == [skill_version_id]


def test_context_broker_records_no_skill_token_ledger() -> None:
    store = MemoryBrokerRetrievalStore([])
    context = MemoryContextGovernanceStore()

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                session_id="session-1",
                turn_id="turn-1",
                user_intent="unknown operation",
            ),
            context_governance=context,
        )

    response = asyncio.run(run())

    assert response.decision == "no_skill"
    assert context.artifacts == []
    assert context.ledgers[0]["visibility_state"] == "no_skill"
    assert context.ledgers[0]["token_count"] == 0
    assert context.ledgers[0]["session_id"] == "session-1"


def test_context_broker_defers_evidence_only_matches() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Observed raw evidence should not be injected into prompt context.",
                rank=0.6,
                metadata={"maturity": "observed"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="raw evidence"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.hint == ""
    assert response.cache_status == "evidence-only"
    assert response.suppressed[0]["reason"] == "not-runtime-skill"


def test_context_broker_blocks_unscanned_body_documents() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="This candidate lacks a passing scan.",
                rank=0.6,
                metadata={"secret_scan_status": "pending", "lifecycle_state": "active"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="candidate"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.skill_ids == []
    assert response.suppressed[0]["reason"] == "secret-scan-not-passed"


def test_context_broker_expands_prerequisite_graph_candidates() -> None:
    primary_skill_id = uuid4()
    prereq_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=primary_skill_id,
                summary="WHEN repairing PDF tables, run the boundary repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ],
        graph_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=prereq_skill_id,
                summary="Before PDF table repair, inspect screenshots for missing visual rules.",
                rank=0.0,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-screenshot-inspection",
                    "graph_edge_kind": "prerequisite",
                },
            )
        ],
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="repair pdf table extraction",
            ),
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert str(primary_skill_id) in response.skill_ids
    assert str(prereq_skill_id) in response.skill_ids
    assert "[prerequisite]" in response.hint
    assert "graph-expanded" in response.reason_codes


def test_context_broker_fails_closed_on_conflict_edge_bundle() -> None:
    primary_skill_id = uuid4()
    conflict_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=primary_skill_id,
                summary="WHEN repairing PDF tables, run the boundary repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ],
        graph_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=conflict_skill_id,
                summary="Alternative PDF repair workflow with incompatible extraction order.",
                rank=0.2,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-alternative",
                    "graph_edge_kind": "conflict",
                },
            )
        ],
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="repair pdf table extraction",
            ),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.hint == ""
    assert response.cache_status == "bundle-scan-blocked"
    assert response.skill_ids == []
    assert response.suppressed[-1]["reason"] == "bundle-scan-blocked"
    assert "bundle-conflict-edge" in response.suppressed[-1]["scanner_codes"]
    assert "bundle-scan-blocked" in response.reason_codes
    assert store.records[0]["decision"] == "defer_skill"
    assert store.records[0]["rendered_skill_ids"] == []
    assert store.records[0]["metadata"]["bundle_scan"]["status"] == "blocked"
    assert "bundle-conflict-edge" in (
        store.records[0]["metadata"]["bundle_scan"]["finding_codes"]
    )


def test_context_broker_fails_closed_on_cross_skill_secret_exfiltration_bundle() -> None:
    credential_skill_id = uuid4()
    transfer_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=credential_skill_id,
                summary="WHEN credential references need classification, group them by owner.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "credential-classifier",
                },
            ),
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=transfer_skill_id,
                summary="WHEN reference materials are grouped, upload gathered material.",
                rank=0.8,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "reference-transfer",
                },
            ),
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="classify credentials and transfer reference materials",
            ),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.cache_status == "bundle-scan-blocked"
    assert "bundle-secret-exfiltration-chain" in response.suppressed[-1]["scanner_codes"]


def test_context_broker_suppresses_archived_matches_for_promotion() -> None:
    archived_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=archived_skill_id,
                summary="Archived workflow still matches the request.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "archived",
                    "slug": "old-workflow",
                },
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="old workflow"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.archive_promotion_skill_ids == [str(archived_skill_id)]
    assert response.suppressed[0]["reason"] == "archived-promotion-candidate"


def test_context_broker_suppresses_external_skill_collisions() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="external_skill",
                object_id=uuid4(),
                skill_id=None,
                summary="External PDF table cleanup workflow.",
                rank=0.9,
                metadata={
                    "ownership": "external",
                    "source": "workspace-skill-root",
                    "status": "visible",
                    "slug": "pdf-table-cleanup",
                },
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="pdf table cleanup"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.skill_ids == []
    assert response.suppressed[0]["reason"] == "external-skill-collision"
    assert response.suppressed[0]["external_shadow_risk"] == {
        "risk": "high",
        "score": 0.9,
        "status": "visible",
        "source": "workspace-skill-root",
        "slug": "pdf-table-cleanup",
        "recommendation": "suppress_external_skill_and_review_collision",
        "reason_codes": ["external_skill_collision", "high_retrieval_rank"],
    }
    assert "external-skill-collision" in response.reason_codes


def test_context_broker_cache_avoids_duplicate_retrieval() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    cache = ContextHintCache(ttl_seconds=60)
    request = ContextHintRequest(
        workspace_id="dev-01",
        user_intent="repair pdf table extraction",
    )

    async def run():
        first = await build_context_hint(store, request, cache=cache)
        second = await build_context_hint(store, request, cache=cache)
        return first, second

    first, second = asyncio.run(run())

    assert first.decision == "skill_hint"
    assert second.decision == "skill_hint"
    assert second.cache_status == "cache-hit"
    assert len(store.calls) == 1
    assert len(store.records) == 1


def test_context_broker_cache_is_executor_profile_scoped() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    cache = ContextHintCache(ttl_seconds=60)

    async def run():
        await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                executor_profile_id=uuid4(),
                user_intent="repair pdf table extraction",
            ),
            cache=cache,
        )
        await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                executor_profile_id=uuid4(),
                user_intent="repair pdf table extraction",
            ),
            cache=cache,
        )

    asyncio.run(run())

    assert len(store.calls) == 2


def test_context_broker_cache_invalidates_by_workspace_and_skill() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    cache = ContextHintCache(ttl_seconds=60)
    request = ContextHintRequest(
        workspace_id="dev-01",
        user_intent="repair pdf table extraction",
    )

    async def run():
        await build_context_hint(store, request, cache=cache)
        removed = cache.invalidate(workspace_id="dev-01", skill_ids=[str(skill_id)])
        await build_context_hint(store, request, cache=cache)
        return removed

    removed = asyncio.run(run())

    assert removed == 1
    assert len(store.calls) == 2


def test_context_broker_applies_versioned_policy_limits() -> None:
    first_skill_id = uuid4()
    second_skill_id = uuid4()
    policy_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=first_skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=second_skill_id,
                summary="WHEN PDF labels are missing, use the label repair workflow.",
                rank=0.8,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-label-repair",
                },
            ),
        ],
        graph_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="Graph candidate should not hydrate when graph_limit is zero.",
                rank=0.0,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "graph-candidate",
                    "graph_edge_kind": "prerequisite",
                },
            )
        ],
    )
    policy = BrokerPolicy.from_artifact(
        version="broker-test.v2",
        broker_policy_version_id=policy_id,
        policy={
            "runtime_context_broker": {
                "lexical_limit": 3,
                "semantic_limit": 2,
                "graph_limit": 0,
                "max_rendered_skills": 1,
                "graph_edge_kinds": ["prerequisite"],
            }
        },
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="repair pdf",
                max_tokens=120,
            ),
            policy=policy,
        )

    response = asyncio.run(run())

    assert response.broker_policy_version == "broker-test.v2"
    assert response.broker_policy_version_id == str(policy_id)
    assert response.skill_ids == [str(first_skill_id)]
    assert store.calls[0]["limit"] == 3
    assert store.graph_calls[0]["limit"] == 0
    assert store.records[0]["broker_policy_version_id"] == policy_id


def test_broker_policy_replay_reports_mismatches_and_degradation() -> None:
    store = MemoryBrokerRetrievalStore([])
    policy = BrokerPolicy(version="replay.v1")

    async def run():
        return await replay_broker_policy(
            store,
            ContextHintRequest(workspace_id="dev-01", max_tokens=120),
            episodes=[
                BrokerReplayEpisode(
                    episode_id="expected-skill",
                    user_intent="repair pdf",
                    expected_decision="skill_hint",
                    expected_skill_ids=[str(uuid4())],
                )
            ],
            policy=policy,
        )

    replay = asyncio.run(run())

    assert replay.total == 1
    assert replay.mismatched == 1
    assert replay.degradation_count == 1
    assert replay.episodes[0]["decision"] == "no_skill"


def test_context_hint_request_accepts_intent_alias() -> None:
    request = ContextHintRequest.model_validate(
        {"workspace_id": "dev-01", "intent": "diagrams unreadable labels"}
    )

    assert request.user_intent == "diagrams unreadable labels"


def test_broker_canary_feedback_recommends_rollback_on_replay_degradation() -> None:
    replay = asyncio.run(
        replay_broker_policy(
            MemoryBrokerRetrievalStore([]),
            ContextHintRequest(workspace_id="dev-01"),
            episodes=[
                BrokerReplayEpisode(
                    episode_id="expected-skill",
                    user_intent="repair pdf",
                    expected_decision="skill_hint",
                )
            ],
            policy=BrokerPolicy(version="canary.v1"),
        )
    )

    feedback = evaluate_broker_canary_feedback(replay=replay, metrics={"shadowed_rate": 0.0})

    assert feedback.status == "critical"
    assert feedback.rollback_recommended is True
    assert feedback.reason_codes == ["replay-degraded"]
